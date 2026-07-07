"""Sprint 53.4: marks over the real Ashmoore world — walk → award.

Drives the real `MovementService.move` (which emits `PLAYER_MOVED`) across the
imported `world_content/world.yaml` with the shipped `world_content/marks.yaml`
loaded, and asserts the Village Wanderer mark is awarded on the step that
completes its criteria — the full content → event → evaluation → award seam,
no hand-rolled emits.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.rng import GameRng
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
from lorecraft.features.marks.models import MarkRegistry, earned_flag, load_marks_yaml
from lorecraft.features.marks.service import MarkService
from lorecraft.features.movement.service import MovementService
from lorecraft.world.bootstrap import ensure_world_bootstrapped

REPO_ROOT = Path(__file__).resolve().parents[2]

# village_square → W(inn) → E(square) → N(forge) → E(alchemist) → S(market):
# visits all five Village Wanderer rooms (real world.yaml topology).
WALK = ["west", "east", "north", "east", "south"]


def _ctx(session: Session, player: Player, bus: EventBus) -> GameContext:
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
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(actor_id="p1", correlation_id="s1"),
        session_id="s1",
    )


def test_walking_ashmoore_village_awards_village_wanderer() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    ensure_world_bootstrapped(
        engine,
        Settings(world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml")),
    )

    registry = MarkRegistry()
    registry.load_document(load_marks_yaml(REPO_ROOT / "world_content" / "marks.yaml"))
    service = MarkService(registry)
    bus = EventBus()
    service.register(bus)

    movement = MovementService()
    with Session(engine) as session:
        player = Player(
            id="p1",
            username="Strider",
            current_room_id="village_square",
            respawn_room_id="village_square",
            visited_rooms=["village_square"],
        )
        session.add(player)
        session.add(PlayerStats(player_id="p1"))
        session.commit()

        final_messages: list[str] = []
        for direction in WALK:
            ctx = _ctx(session, player, bus)  # fresh ctx per command, as production
            movement.move(direction, ctx)
            ctx.flush_events()  # the engine flushes queued events pre-commit
            final_messages = ctx.messages
        session.commit()

        assert player.flags.get(earned_flag("village_wanderer")) is True
        assert any("Mark of the Village Wanderer" in m for m in final_messages), (
            "award should announce on the completing step"
        )
        # Not yet earned: only 5 distinct rooms visited, no NPC met, no caves.
        assert player.flags.get(earned_flag("far_strider")) is None
        assert player.flags.get(earned_flag("friend_of_the_crow")) is None
        assert player.flags.get(earned_flag("deep_delver")) is None
