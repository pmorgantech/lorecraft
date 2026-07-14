"""Room-authored exploration events: loot tables and timed ambient flavor."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import build_game_context
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.exploration.ambient import RoomAmbientService
from lorecraft.features.exploration.loot import RoomLootService


def _engine() -> Engine:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(
            Room(
                id="cache",
                name="Cache",
                description="d",
                map_x=0,
                map_y=0,
                loot_table={
                    "chance": 1.0,
                    "message": "You find a cache.",
                    "entries": [
                        {"item_id": "coin", "weight": 1, "quantity": 2},
                    ],
                },
            )
        )
        session.add(
            Room(
                id="plaza",
                name="Plaza",
                description="d",
                map_x=1,
                map_y=0,
                ambient_events=[
                    {"text": "A bell rings.", "every_ticks": 2, "chance": 1.0}
                ],
            )
        )
        session.add(Item(id="coin", name="Coin", description="d"))
        session.add(
            Player(
                id="p1",
                username="Petem",
                current_room_id="cache",
                respawn_room_id="cache",
            )
        )
        session.commit()
    return engine


def test_room_loot_rolls_once_per_player_room() -> None:
    engine = _engine()
    bus = EventBus()
    RoomLootService().register(bus)
    with Session(engine) as session:
        player = session.get(Player, "p1")
        room = session.get(Room, "cache")
        assert player is not None
        assert room is not None
        ctx = build_game_context(
            session,
            player,
            room,
            bus=bus,
            manager=ConnectionManager(),
            transaction=TransactionContext.create(
                actor_id="p1", correlation_id="loot-test"
            ),
            session_id="loot-test",
            rng=GameRng(seed=1),
            meters=MeterService(engine, GameRng()),
            effects=EffectService(engine, GameRng()),
        )

        event = Event(GameEvent.PLAYER_MOVED, {"to_room_id": "cache"})
        bus.emit(event, ctx)
        bus.emit(event, ctx)
        session.commit()

        stacks = session.exec(select(ItemStack)).all()
        assert [(stack.item_id, stack.quantity) for stack in stacks] == [("coin", 2)]
        assert ctx.messages == ["You find a cache."]
        assert player.flags["room_loot_checked:cache"] is True


def test_room_ambient_events_respect_tick_interval(
    monkeypatch,
) -> None:
    engine = _engine()
    manager = ConnectionManager()
    manager.move_player("p1", None, "plaza")
    seen: list[str] = []
    monkeypatch.setattr(
        "lorecraft.features.exploration.ambient.broadcast_room_async",
        lambda _manager, _room_id, text: seen.append(text),
    )
    service = RoomAmbientService(engine, manager, GameRng(seed=1))
    bus = EventBus()
    service.register(bus)

    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 1.0}), None)
    assert seen == []

    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 2.0}), None)
    assert seen == ["A bell rings."]
