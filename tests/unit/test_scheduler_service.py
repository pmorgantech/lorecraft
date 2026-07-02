"""Unit tests for SchedulerService."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.game.events import Event, EventBus, GameEvent
from lorecraft.models.scheduler import ScheduledJob
from lorecraft.services.scheduler import SchedulerService


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def test_schedule_persists_pending_job() -> None:
    engine = _engine()
    service = SchedulerService(engine)

    job_id = service.schedule(
        "npc_move", at_game_epoch=100.0, payload={"npc_id": "mira"}
    )

    with Session(engine) as session:
        job = session.get(ScheduledJob, job_id)
        assert job is not None
        assert job.status == "pending"
        assert job.job_type == "npc_move"
        assert job.due_at_epoch == 100.0
        assert job.payload == {"npc_id": "mira"}


def test_time_advanced_dispatches_due_jobs_only() -> None:
    engine = _engine()
    service = SchedulerService(engine)
    bus = EventBus()
    service.register(bus)

    due_id = service.schedule("combat_tick", at_game_epoch=50.0)
    future_id = service.schedule("combat_tick", at_game_epoch=500.0)

    observed: list[dict] = []
    bus.on(
        GameEvent.SCHEDULED_JOB_DUE, lambda event, ctx: observed.append(event.payload)
    )

    bus.emit(
        Event(GameEvent.TIME_ADVANCED, {"previous_epoch": 0.0, "current_epoch": 60.0}),
        ctx=None,
    )

    assert len(observed) == 1
    assert observed[0]["job_id"] == due_id
    assert observed[0]["job_type"] == "combat_tick"

    with Session(engine) as session:
        dispatched = session.get(ScheduledJob, due_id)
        pending = session.get(ScheduledJob, future_id)
        assert dispatched is not None and dispatched.status == "dispatched"
        assert pending is not None and pending.status == "pending"


def test_time_advanced_does_not_redispatch_completed_jobs() -> None:
    engine = _engine()
    service = SchedulerService(engine)
    bus = EventBus()
    service.register(bus)

    service.schedule("combat_tick", at_game_epoch=10.0)

    observed: list[dict] = []
    bus.on(
        GameEvent.SCHEDULED_JOB_DUE, lambda event, ctx: observed.append(event.payload)
    )

    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 20.0}), ctx=None)
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 30.0}), ctx=None)

    assert len(observed) == 1


def test_cancel_prevents_dispatch() -> None:
    engine = _engine()
    service = SchedulerService(engine)
    bus = EventBus()
    service.register(bus)

    job_id = service.schedule("npc_move", at_game_epoch=10.0)
    service.cancel(job_id)

    observed: list[dict] = []
    bus.on(
        GameEvent.SCHEDULED_JOB_DUE, lambda event, ctx: observed.append(event.payload)
    )
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 20.0}), ctx=None)

    assert observed == []
    with Session(engine) as session:
        job = session.get(ScheduledJob, job_id)
        assert job is not None
        assert job.status == "cancelled"


def test_time_advanced_with_no_due_jobs_emits_nothing() -> None:
    engine = _engine()
    service = SchedulerService(engine)
    bus = EventBus()
    service.register(bus)

    observed: list[dict] = []
    bus.on(
        GameEvent.SCHEDULED_JOB_DUE, lambda event, ctx: observed.append(event.payload)
    )
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 5.0}), ctx=None)

    assert observed == []
