"""Escort quests (Sprint 68): an NPC following a player, the
"start_escort"/"end_escort" side effects, and the "npc_following"/
"npc_present" quest conditions.

`NPC.following_player_id` is DB-backed (not `FollowService`'s in-memory
player-follow graph), so the quest conditions can read it via `ctx.npc_repo`
alone -- see the docstrings in `features/follow/service.py` and
`features/follow/conditions.py` for why.
"""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import NPC, Exit, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.follow.conditions import register as register_follow_conditions
from lorecraft.features.follow.service import FollowService
from lorecraft.features.movement.service import MovementService
from lorecraft.features.npc.side_effects import get_registry as side_effect_registry
from lorecraft.features.quests import conditions as quest_conditions

ROOM_A = "square"
ROOM_B = "market"

register_follow_conditions(FollowService())


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def _seed(session: Session, *, npc_room: str = ROOM_A) -> Player:
    session.add(Room(id=ROOM_A, name="Square", description="d", map_x=0, map_y=0))
    session.add(Room(id=ROOM_B, name="Market", description="d", map_x=1, map_y=0))
    session.add(Exit(room_id=ROOM_A, direction="east", target_room_id=ROOM_B))
    session.add(Exit(room_id=ROOM_B, direction="west", target_room_id=ROOM_A))
    session.add(
        NPC(
            id="mira",
            name="Mira",
            description="An innkeeper.",
            current_room_id=npc_room,
            home_room_id=ROOM_A,
            dialogue_tree_id="mira_tree",
        )
    )
    player = Player(
        id="p1", username="hero", current_room_id=ROOM_A, respawn_room_id=ROOM_A
    )
    session.add(player)
    session.commit()
    return player


def _ctx(
    session: Session, player: Player, *, bus: EventBus | None = None
) -> GameContext:
    room = session.get(Room, player.current_room_id)
    assert room is not None
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
        bus=bus or EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s"),
        session_id="s",
    )


class TestStartEscort:
    def test_start_escort_sets_following_player_id(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session)
            ctx = _ctx(session, player)

            ok = FollowService().start_escort("mira", ctx)
            session.commit()

            assert ok is True
            assert session.get(NPC, "mira").following_player_id == "p1"
            assert "Mira agrees to follow you." in ctx.messages

    def test_start_escort_fails_when_npc_absent(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session, npc_room=ROOM_B)  # not co-located
            ctx = _ctx(session, player)

            ok = FollowService().start_escort("mira", ctx)

            assert ok is False
            assert session.get(NPC, "mira").following_player_id is None

    def test_start_escort_fails_when_already_escorting(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session)
            npc = session.get(NPC, "mira")
            assert npc is not None
            npc.following_player_id = "someone-else"
            session.commit()
            ctx = _ctx(session, player)

            ok = FollowService().start_escort("mira", ctx)

            assert ok is False
            assert session.get(NPC, "mira").following_player_id == "someone-else"


class TestEndEscort:
    def test_end_escort_clears_following_player_id(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session)
            npc = session.get(NPC, "mira")
            assert npc is not None
            npc.following_player_id = "p1"
            session.commit()
            ctx = _ctx(session, player)

            ok = FollowService().end_escort("mira", ctx)
            session.commit()

            assert ok is True
            assert session.get(NPC, "mira").following_player_id is None
            assert "Mira stops following you." in ctx.messages

    def test_end_escort_is_noop_for_someone_elses_escort(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session)
            npc = session.get(NPC, "mira")
            assert npc is not None
            npc.following_player_id = "someone-else"
            session.commit()
            ctx = _ctx(session, player)

            ok = FollowService().end_escort("mira", ctx)

            assert ok is False
            assert session.get(NPC, "mira").following_player_id == "someone-else"


class TestEscortMovementCascade:
    def test_escorted_npc_moves_with_player(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session)
            npc = session.get(NPC, "mira")
            assert npc is not None
            npc.following_player_id = "p1"
            session.commit()

            follow = FollowService(MovementService())
            bus = EventBus()
            follow.register(bus)

            ctx = _ctx(session, player, bus=bus)
            MovementService().move("east", ctx)
            ctx.flush_events()

            assert player.current_room_id == ROOM_B
            assert session.get(NPC, "mira").current_room_id == ROOM_B
            assert "Mira follows you." in ctx.messages

    def test_escort_breaks_quietly_when_npc_not_co_located(self) -> None:
        """The escorted NPC wandered off (its own schedule, say) before the
        player moved -- the escort ends instead of teleporting it along."""
        with Session(_engine()) as session:
            player = _seed(session)
            npc = session.get(NPC, "mira")
            assert npc is not None
            npc.following_player_id = "p1"
            npc.current_room_id = ROOM_B  # not with the player in ROOM_A
            session.commit()

            follow = FollowService(MovementService())
            bus = EventBus()
            follow.register(bus)

            ctx = _ctx(session, player, bus=bus)
            MovementService().move("east", ctx)
            ctx.flush_events()

            assert session.get(NPC, "mira").following_player_id is None
            assert any("lost track of Mira" in m for m in ctx.messages)


class TestSideEffects:
    def test_start_escort_side_effect_via_registry(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session)
            session.commit()
            ctx = _ctx(session, player)

            side_effect_registry().apply({"start_escort": "mira"}, ctx)
            session.commit()

            assert session.get(NPC, "mira").following_player_id == "p1"

    def test_end_escort_side_effect_via_registry(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session)
            npc = session.get(NPC, "mira")
            assert npc is not None
            npc.following_player_id = "p1"
            session.commit()
            ctx = _ctx(session, player)

            side_effect_registry().apply({"end_escort": "mira"}, ctx)
            session.commit()

            assert session.get(NPC, "mira").following_player_id is None


class TestQuestConditions:
    def test_npc_following_condition(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session)
            session.commit()
            ctx = _ctx(session, player)
            cond = {"type": "npc_following", "npc_id": "mira"}

            assert quest_conditions.get_registry().evaluate_all([cond], ctx) is False

            npc = session.get(NPC, "mira")
            assert npc is not None
            npc.following_player_id = "p1"
            session.commit()

            assert quest_conditions.get_registry().evaluate_all([cond], ctx) is True

    def test_npc_following_condition_false_for_other_players_escort(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session)
            npc = session.get(NPC, "mira")
            assert npc is not None
            npc.following_player_id = "someone-else"
            session.commit()
            ctx = _ctx(session, player)
            cond = {"type": "npc_following", "npc_id": "mira"}

            assert quest_conditions.get_registry().evaluate_all([cond], ctx) is False

    def test_npc_present_condition(self) -> None:
        with Session(_engine()) as session:
            player = _seed(session, npc_room=ROOM_B)
            session.commit()
            ctx = _ctx(session, player)
            cond = {"type": "npc_present", "npc_id": "mira"}

            assert quest_conditions.get_registry().evaluate_all([cond], ctx) is False

            npc = session.get(NPC, "mira")
            assert npc is not None
            npc.current_room_id = ROOM_A
            session.commit()

            assert quest_conditions.get_registry().evaluate_all([cond], ctx) is True
