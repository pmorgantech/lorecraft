"""Tests for the `use` command and InventoryService.use_item()."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus, GameEvent
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from tests.fixtures.disambig_fixtures import DISAMBIG_ROOM_ID, seed_disambig_gallery


def _build_engine_and_ctx(inventory: list[str]) -> tuple[CommandEngine, GameContext]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    seed_disambig_gallery(session, link=None)
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=DISAMBIG_ROOM_ID,
        respawn_room_id=DISAMBIG_ROOM_ID,
    )
    session.add(player)
    session.commit()
    item_location = ItemLocationService(session)
    for item_id in inventory:
        item_location.spawn(item_id, Location("player", player.id))
    session.commit()
    room = session.get(Room, DISAMBIG_ROOM_ID)
    assert room is not None
    ctx = GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=item_location,
        ledger=LedgerService(),
        rng=GameRng(),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
    registry = CommandRegistry()
    register_all_commands(registry)
    return CommandEngine(registry, RuleEngine()), ctx


def test_use_matching_pair_succeeds() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["cage_key"])

    cmd_engine.handle_command("use cage key on cage lock", ctx)

    assert ctx.messages == ["You use the Cage Key with the Cage Lock. It works!"]


def test_use_non_matching_pair_does_nothing() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["cage_key"])

    cmd_engine.handle_command("use cage key on steel key", ctx)

    assert ctx.messages == ["Using the Cage Key with the Steel Key does nothing."]


def test_use_item_alone_with_no_combos() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["red_rose"])

    cmd_engine.handle_command("use red rose", ctx)

    assert ctx.messages == ["You use the Red Rose, but nothing happens."]


def test_use_item_alone_hints_when_combo_required() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["cage_key"])

    cmd_engine.handle_command("use cage key", ctx)

    assert ctx.messages == ["You need to use the Cage Key with something specific."]


def test_use_missing_item_says_you_dont_have_it() -> None:
    cmd_engine, ctx = _build_engine_and_ctx([])

    cmd_engine.handle_command("use lantern", ctx)

    assert ctx.messages == ["You don't have that."]


def test_use_ambiguous_item_prompts_numbered_choices() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["iron_key"])

    cmd_engine.handle_command("use key", ctx)

    assert ctx.messages[0].startswith("Which do you mean?")
    assert ctx.updates["disambig_pending"]["verb"] == "use"


def test_use_emits_item_used_event_with_both_ids() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["cage_key"])
    seen: list[tuple[str, str | None]] = []
    ctx.bus.on(
        GameEvent.ITEM_USED,
        lambda event, _ctx: seen.append(
            (str(event.payload["item_id"]), event.payload.get("other_item_id"))
        ),
    )

    cmd_engine.handle_command("use cage key on cage lock", ctx)

    assert seen == [("cage_key", "cage_lock")]


def test_use_combination_applies_side_effects() -> None:
    """Sprint 30.2: a successful `use X with Y` can set_flags (or any other
    npc/side_effects.py handler), not just print flavor text."""
    cmd_engine, ctx = _build_engine_and_ctx(["cage_key"])
    ctx.session.add(
        Item(
            id="acid_vial",
            name="acid vial",
            description="A vial of corrosive acid.",
            usable_with=["rusted_hinge"],
            combination_side_effects={
                "rusted_hinge": {"set_flags": ["hinge_dissolved"]}
            },
        )
    )
    ctx.session.add(
        Item(id="rusted_hinge", name="rusted hinge", description="A rusted hinge.")
    )
    ctx.session.commit()
    ctx.item_location.spawn("acid_vial", Location("player", ctx.player.id))
    ctx.item_location.spawn("rusted_hinge", Location("room", ctx.room.id))
    ctx.session.commit()

    cmd_engine.handle_command("use acid vial on rusted hinge", ctx)

    assert any("It works!" in m for m in ctx.messages)
    assert ctx.player.flags.get("hinge_dissolved") is True


def test_use_combination_side_effect_checked_from_either_item() -> None:
    """combination_side_effects declared on the *other* item (not the one
    named first in `use X with Y`) still fires."""
    cmd_engine, ctx = _build_engine_and_ctx([])
    ctx.session.add(
        Item(
            id="gear", name="gear", description="A brass gear.", usable_with=["socket"]
        )
    )
    ctx.session.add(
        Item(
            id="socket",
            name="socket",
            description="An empty socket.",
            combination_side_effects={"gear": {"set_flags": ["gear_seated"]}},
        )
    )
    ctx.session.commit()
    ctx.item_location.spawn("gear", Location("player", ctx.player.id))
    ctx.item_location.spawn("socket", Location("room", ctx.room.id))
    ctx.session.commit()

    cmd_engine.handle_command("use gear on socket", ctx)

    assert ctx.player.flags.get("gear_seated") is True


def test_use_non_matching_pair_does_not_apply_side_effects() -> None:
    cmd_engine, ctx = _build_engine_and_ctx(["cage_key"])

    cmd_engine.handle_command("use cage key on steel key", ctx)

    assert ctx.player.flags == {}
