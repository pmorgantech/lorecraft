"""A2 live wiring — triggers load from world content and fire on the real bus.

Loads the actual `world_content/world.yaml` (which carries the demo `encounter` trigger on the
innkeeper), builds the TriggerService the way `main.py` does, and confirms a player entering
the inn fires it. This is the "see it in-game" path, exercised headlessly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
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
from lorecraft.features.celestial.conditions import register as register_celestial
from lorecraft.scripting_wiring import build_trigger_service, load_triggers
from lorecraft.world.loader import load_world_yaml

_WORLD = Path(__file__).resolve().parents[2] / "world_content" / "world.yaml"
INN = "wandering_crow_inn"


@pytest.fixture(autouse=True)
def _wire_celestial_conditions() -> None:
    # The real world.yaml's `soot_sump` night-glow trigger gates on the celestial
    # feature's `time_of_day_is` condition (gap #5 proof-of-concept). Production wires
    # every enabled feature (`wire_features`) before loading triggers (see main.py's
    # `lifespan`); these tests load triggers directly against `global_vocabulary()`
    # without going through `wire_features`, so they must register it themselves.
    # `register()` is idempotent (name-keyed registries), so this is safe regardless
    # of what earlier tests in this xdist worker already registered.
    register_celestial()


def _seeded_session() -> Session:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    load_world_yaml(str(_WORLD), session)
    player = Player(
        id="p1", username="Walker", current_room_id=INN, respawn_room_id=INN
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1"))
    session.commit()
    return session


def test_world_yaml_triggers_parse_fail_closed() -> None:
    """The whole world file's triggers parse (validates the demo trigger's names)."""
    session = _seeded_session()
    triggers = load_triggers(session)
    # The demo innkeeper encounter trigger is present and bound to the NPC.
    assert any(t.on == "encounter" and t.entity_id == "innkeeper" for t in triggers)
    session.close()


def _ctx(session: Session, bus: EventBus) -> GameContext:
    player = session.get(Player, "p1")
    room = session.get(Room, INN)
    assert player is not None and room is not None
    bind = session.get_bind()
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
        meters=MeterService(bind, GameRng()),
        effects=EffectService(bind, GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(actor_id="p1", correlation_id="s1"),
        session_id="s1",
    )


def test_entering_inn_fires_innkeeper_encounter_trigger() -> None:
    session = _seeded_session()
    # Mira must actually be in the inn for the encounter to fire.
    assert any(npc.id == "innkeeper" for npc in NpcRepo(session).in_room(INN))

    bus = EventBus()
    build_trigger_service(session, bus)
    ctx = _ctx(session, bus)

    # `narrate_room` broadcasts via `broadcast_room_async` (a no-op without a running loop), so
    # capture its calls to prove the trigger fired and targeted the right room. The handler
    # imports the symbol at call time, so patching the module attribute is picked up.
    import lorecraft.engine.game.world_context as wc

    calls: list[tuple[str | None, str]] = []
    original = wc.broadcast_room_async
    wc.broadcast_room_async = lambda manager, room_id, text: calls.append(
        (room_id, text)
    )  # type: ignore[assignment]
    try:
        bus.emit(
            Event(
                GameEvent.PLAYER_MOVED,
                {
                    "player_id": "p1",
                    "from_room_id": "village_square",
                    "to_room_id": INN,
                },
            ),
            ctx,
        )
    finally:
        wc.broadcast_room_async = original  # type: ignore[assignment]

    assert calls, "innkeeper encounter trigger did not narrate"
    room_id, text = calls[0]
    assert room_id == INN
    assert "Mira" in text
    session.close()
