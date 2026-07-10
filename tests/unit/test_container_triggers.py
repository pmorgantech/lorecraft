"""A4 — container/item effect triggers (the magic chest).

`item_stored`/`item_removed` fire the *container item's* triggers, and `apply_effect` can target
the item just placed inside (`stored_item`), threaded via `ctx.event_payload`. See
`docs/scripting_engine_design.md` §5.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game import effects as effects_module
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.effects import EffectDef
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
from lorecraft.engine.scripting.triggers import Trigger, TriggerService
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.npc.dialogue_conditions import get_registry as dialogue_registry
from lorecraft.features.npc.side_effects import get_registry as effect_registry

ROOM = "vault"
CHEST = "magic_chest"
SWORD = "iron_sword"


@pytest.fixture(autouse=True)
def _hexed_effect() -> None:
    # A minimal registered effect def so `apply_effect: {effect: hexed}` resolves.
    effects_module.get_registry().register(
        EffectDef(key="hexed", modifiers=lambda effect: [])
    )


@pytest.fixture
def session() -> Session:  # type: ignore[misc]
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(Room(id=ROOM, name="Vault", description="d", map_x=0, map_y=0))
        player = Player(
            id="p1", username="Keeper", current_room_id=ROOM, respawn_room_id=ROOM
        )
        session.add(player)
        session.add(PlayerStats(player_id="p1"))
        session.commit()
        yield session


def _ctx(session: Session, bus: EventBus) -> GameContext:
    player = session.get(Player, "p1")
    room = session.get(Room, ROOM)
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


def _store(bus: EventBus, ctx: GameContext) -> None:
    bus.emit(
        Event(
            GameEvent.ITEM_STORED,
            {"container_item_id": CHEST, "item_id": SWORD, "player_id": "p1"},
        ),
        ctx,
    )


def _service(bus: EventBus, trigger: Trigger) -> TriggerService:
    service = TriggerService(when=dialogue_registry(), do=effect_registry())
    service.load([trigger])
    service.register(bus)
    return service


def test_stored_item_gets_the_chest_effect(session: Session) -> None:
    bus = EventBus()
    ctx = _ctx(session, bus)
    _service(
        bus,
        Trigger(
            on="item_stored",
            entity_type="item",
            entity_id=CHEST,
            do=[
                {
                    "apply_effect": {
                        "target": "stored_item",
                        "effect": "hexed",
                        "ticks": 50,
                    }
                }
            ],
        ),
    )
    _store(bus, ctx)

    active = ctx.effects.active_for(session, "item", SWORD)
    assert [e.effect_key for e in active] == ["hexed"]


def test_container_trigger_only_fires_for_its_own_container(session: Session) -> None:
    bus = EventBus()
    ctx = _ctx(session, bus)
    _service(
        bus,
        Trigger(
            on="item_stored",
            entity_type="item",
            entity_id="other_chest",  # not the one we store into
            do=[{"apply_effect": {"target": "stored_item", "effect": "hexed"}}],
        ),
    )
    _store(bus, ctx)
    assert ctx.effects.active_for(session, "item", SWORD) == []


def test_when_gate_on_container_trigger(session: Session) -> None:
    bus = EventBus()
    ctx = _ctx(session, bus)
    _service(
        bus,
        Trigger(
            on="item_stored",
            entity_type="item",
            entity_id=CHEST,
            when={"required_flags": ["attuned"]},
            do=[{"apply_effect": {"target": "stored_item", "effect": "hexed"}}],
        ),
    )
    _store(bus, ctx)
    assert ctx.effects.active_for(session, "item", SWORD) == []  # not attuned

    ctx.player.flags = {**ctx.player.flags, "attuned": True}
    _store(bus, ctx)
    assert [e.effect_key for e in ctx.effects.active_for(session, "item", SWORD)] == [
        "hexed"
    ]


def test_event_payload_cleared_after_firing(session: Session) -> None:
    bus = EventBus()
    ctx = _ctx(session, bus)
    _service(
        bus,
        Trigger(
            on="item_stored",
            entity_type="item",
            entity_id=CHEST,
            do={"set_flags": ["x"]},
        ),
    )
    _store(bus, ctx)
    assert ctx.event_payload == {}  # transient, not left dangling on the shared context


def test_apply_effect_to_actor(session: Session) -> None:
    bus = EventBus()
    ctx = _ctx(session, bus)
    _service(
        bus,
        Trigger(
            on="item_stored",
            entity_type="item",
            entity_id=CHEST,
            do=[{"apply_effect": {"target": "actor", "effect": "hexed"}}],
        ),
    )
    _store(bus, ctx)
    assert [e.effect_key for e in ctx.effects.active_for(session, "player", "p1")] == [
        "hexed"
    ]
