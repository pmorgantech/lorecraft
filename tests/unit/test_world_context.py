"""A1 — the actor-less WorldContext surface (`engine/game/world_context.py`).

A `StandaloneWorldContext` must let autonomous behavior read/mutate world state, emit events,
roll the seedable RNG, and narrate — all without a player — and satisfy the `WorldContext`
protocol that `GameContext` also satisfies. See `docs/scripting_engine_design.md` §3.1.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.game.world_context import (
    StandaloneWorldContext,
    WorldContext,
    build_world_context,
)
from lorecraft.engine.models.world import NPC, Room
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService

ROOM = "plaza"


@pytest.fixture
def session() -> Session:  # type: ignore[misc]
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(Room(id=ROOM, name="Plaza", description="d", map_x=0, map_y=0))
        session.add(
            NPC(
                id="sentinel",
                name="Sentinel",
                description="brass",
                current_room_id=ROOM,
                home_room_id=ROOM,
                dialogue_tree_id="none",
            )
        )
        session.commit()
        yield session


def _build(session: Session, bus: EventBus | None = None) -> StandaloneWorldContext:
    bind = session.get_bind()
    return build_world_context(
        session,
        bus=bus or EventBus(),
        manager=ConnectionManager(),
        transaction=TransactionContext.create(actor_id="world", correlation_id="tick"),
        session_id="tick",
        rng=GameRng(seed=7),
        meters=MeterService(bind, GameRng()),
        effects=EffectService(bind, GameRng()),
        clock=None,
    )


def test_standalone_context_satisfies_world_context_protocol(session: Session) -> None:
    ctx = _build(session)
    # Structural check: the concrete class is accepted where a WorldContext is required.
    accepted: WorldContext = ctx
    assert accepted.session is session
    assert accepted.clock is None


def test_reads_world_state_without_a_player(session: Session) -> None:
    ctx = _build(session)
    npcs = ctx.npc_repo.in_room(ROOM)
    assert [n.id for n in npcs] == ["sentinel"]
    assert not hasattr(ctx, "player")  # actor-less by construction


def test_emit_delivers_the_standalone_context_to_handlers(session: Session) -> None:
    bus = EventBus()
    seen: list[object] = []

    def handler(event: Event, ctx: object) -> None:
        seen.append(ctx)

    bus.on(GameEvent.TIME_ADVANCED, handler)
    ctx = _build(session, bus=bus)
    ctx.emit(GameEvent.TIME_ADVANCED, current_epoch=1.0)
    assert seen == [ctx]


def test_queue_and_flush_events(session: Session) -> None:
    bus = EventBus()
    fired: list[str] = []

    def handler(event: Event, ctx: object) -> None:
        fired.append("tick")

    bus.on(GameEvent.TIME_ADVANCED, handler)
    ctx = _build(session, bus=bus)
    ctx.queue_event(GameEvent.TIME_ADVANCED)
    assert fired == []  # queued, not yet fired
    ctx.flush_events()
    assert fired == ["tick"]
    assert ctx.pending_events == []


def test_rng_is_deterministic(session: Session) -> None:
    a = _build(session).rng.uniform(0.0, 1.0)
    b = _build(session).rng.uniform(0.0, 1.0)  # same seed=7
    assert a == b


def test_narrate_room_is_a_noop_without_event_loop(session: Session) -> None:
    # No running loop in a sync test — must not raise (best-effort autonomous narration).
    _build(session).narrate_room(ROOM, "The bell tolls.")


def test_push_update_records_updates(session: Session) -> None:
    ctx = _build(session)
    ctx.push_update("weather", "storm")
    assert ctx.updates == {"weather": "storm"}
