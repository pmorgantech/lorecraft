"""Headless integration journeys — the marquee player walkthroughs from
`docs/feature_testing_guide.md`, driven end-to-end through the real
`CommandEngine.handle_command` (parse → conditions → rules → handler →
flush_events → commit) against the shipped `world_content/world.yaml`.

Why these exist (and are not duplicates):
  * The unit suites drive `handle_command` too, but over *synthetic* fixtures
    (a hand-built shop/room/item) to prove one command's logic in isolation.
  * The `golden_path` simulation only replays the light happy path
    (look/go/take/talk/choice/bye) and asserts an *audit-trail* golden, not the
    semantic outcome of a multi-step journey.
  * The e2e suite covers these flows but through a real browser + live uvicorn
    socket (slow, serial).

These tests fill the gap: fast, headless regressions that assert the *composed
outcome* of a real multi-command journey over the actual shipped world content
(the same Vault Hall / Good-Key, Equippable Helmet, and Mira → Investigate the
Lights content the e2e tests use). They exercise the same engine seam production
uses and the same YAML players see — no production special-casing, no bespoke
fixtures.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from lorecraft.commands import register_all_commands
from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.quests.models import PlayerQuestProgress
from lorecraft.services.container import ServiceContainer
from lorecraft.world.bootstrap import ensure_world_bootstrapped

REPO_ROOT = Path(__file__).resolve().parents[2]
WORLD_YAML = str(REPO_ROOT / "world_content" / "world.yaml")


# --------------------------------------------------------------------------- #
# Harness: real world + real CommandEngine, driven by raw command strings.
# --------------------------------------------------------------------------- #
def _bootstrap_world() -> Engine:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    ensure_world_bootstrapped(engine, Settings(world_yaml_path=WORLD_YAML))
    return engine


def _command_engine() -> CommandEngine:
    registry = CommandRegistry()
    register_all_commands(registry, ServiceContainer.build())
    return CommandEngine(registry, RuleEngine())


def _spawn(session: Session, room_id: str) -> Player:
    player = Player(
        id="p1",
        username="Traveller",
        current_room_id=room_id,
        respawn_room_id=room_id,
        visited_rooms=[room_id],
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1"))
    session.commit()
    return player


def _ctx(session: Session, player: Player) -> GameContext:
    room = session.get(Room, player.current_room_id)
    assert room is not None, f"room {player.current_room_id!r} missing"
    return GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=GameRng(seed=1),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id="p1", correlation_id="s1"),
        session_id="s1",
        # Wire the engine's commit hook to the session, exactly as production
        # does (`main.py`/`frontend.py`): `handle_command` calls
        # `commit_state_changes()` after each command, which is a no-op unless
        # this is set — so without it a command's state changes never persist.
        commit_state=session.commit,
    )


def _run(cmd: CommandEngine, session: Session, player: Player, raw: str) -> list[str]:
    """Drive one raw command through the full engine, as production does: a
    fresh context per command (the handler mutates + commits the shared
    session, so `player` reflects the new state on the next call)."""
    ctx = _ctx(session, player)
    cmd.handle_command(raw, ctx)
    return list(ctx.messages)


def _here(session: Session, player: Player) -> str:
    session.refresh(player)
    return player.current_room_id


def _loose_item_ids(session: Session, player: Player) -> set[str]:
    """Item ids the player carries *loose* (in a pack slot, not worn/wielded)."""
    return {
        s.item_id
        for s in StackRepo(session).stacks_for_owner("player", player.id)
        if s.slot is None
    }


def _worn_slots(session: Session, player: Player) -> dict[str, str]:
    """slot -> item_id for everything the player has equipped."""
    return {
        s.slot: s.item_id
        for s in StackRepo(session).stacks_for_owner("player", player.id)
        if s.slot is not None
    }


# --------------------------------------------------------------------------- #
# Journey 1 — locked vault door → wrong key rejected → right key → pass.
# Real content: village_square -N-> blacksmith_forge -N-> key_gallery
#               -E-> vault_hall  (holds Good Key + Bad Key)
#               -E-> inner_vault  (locked: True, key_item_id: good_key)
# --------------------------------------------------------------------------- #
def test_vault_door_only_opens_with_the_good_key() -> None:
    engine = _bootstrap_world()
    cmd = _command_engine()
    with Session(engine) as session:
        player = _spawn(session, "village_square")

        for step in ("go north", "go north", "go east"):
            _run(cmd, session, player, step)
        assert _here(session, player) == "vault_hall", "walk to the vault hall"

        # Locked with no key: movement is refused and the player stays put.
        blocked = _run(cmd, session, player, "go east")
        assert _here(session, player) == "vault_hall"
        assert any("lock" in m.lower() for m in blocked), blocked

        # The Bad Key is the wrong key: unlock does not open the door, so a
        # follow-up move is still blocked.
        _run(cmd, session, player, "take bad key")
        assert "bad_key" in _loose_item_ids(session, player)
        _run(cmd, session, player, "unlock east")
        assert _here(session, player) == "vault_hall"
        still_blocked = _run(cmd, session, player, "go east")
        assert _here(session, player) == "vault_hall", still_blocked

        # The Good Key unlocks the way, and now the move succeeds.
        _run(cmd, session, player, "take good key")
        unlocked = _run(cmd, session, player, "unlock east")
        assert any("unlock" in m.lower() for m in unlocked), unlocked
        _run(cmd, session, player, "go east")
        assert _here(session, player) == "inner_vault", "Good Key opens the vault"


# --------------------------------------------------------------------------- #
# Journey 2 — equip flow: a worn item leaves the loose pack and comes back.
# Real content: blacksmith_forge holds `equippable_helmet` (slot=head).
# --------------------------------------------------------------------------- #
def test_wear_then_remove_helmet_moves_it_between_pack_and_head_slot() -> None:
    engine = _bootstrap_world()
    cmd = _command_engine()
    with Session(engine) as session:
        player = _spawn(session, "blacksmith_forge")

        _run(cmd, session, player, "take helmet")
        assert "equippable_helmet" in _loose_item_ids(session, player)
        assert "head" not in _worn_slots(session, player)

        worn_msgs = _run(cmd, session, player, "wear helmet")
        assert any("wear" in m.lower() for m in worn_msgs), worn_msgs
        # Now worn on the head slot and no longer a loose pack item.
        assert _worn_slots(session, player).get("head") == "equippable_helmet"
        assert "equippable_helmet" not in _loose_item_ids(session, player)

        removed_msgs = _run(cmd, session, player, "remove helmet")
        assert any("remove" in m.lower() for m in removed_msgs), removed_msgs
        assert "head" not in _worn_slots(session, player)
        assert "equippable_helmet" in _loose_item_ids(session, player)


# --------------------------------------------------------------------------- #
# Journey 3 — dialogue side effect: talking to Mira starts a quest.
# Real content: innkeeper "Mira the Innkeeper" in wandering_crow_inn; the
# "Any news around town?" choice sets flag `heard_rumor` and starts the
# `investigate_lights` quest.
# --------------------------------------------------------------------------- #
def test_mira_dialogue_starts_investigate_lights_quest() -> None:
    engine = _bootstrap_world()
    cmd = _command_engine()
    with Session(engine) as session:
        player = _spawn(session, "wandering_crow_inn")

        _run(cmd, session, player, "talk mira")
        # First visible choice is "Any news around town?" (the moon-gated
        # choice is hidden outside a full moon), which fires the quest start.
        _run(cmd, session, player, "choice 1")

        session.refresh(player)
        assert player.flags.get("heard_rumor") is True, player.flags
        assert "innkeeper" in player.met_npcs

        progress = session.exec(
            select(PlayerQuestProgress).where(
                PlayerQuestProgress.player_id == player.id,
                PlayerQuestProgress.quest_id == "investigate_lights",
            )
        ).first()
        assert progress is not None, "the quest should be recorded as started"
        assert progress.status == "active"
