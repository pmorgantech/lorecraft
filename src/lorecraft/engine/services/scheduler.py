"""DB-backed job scheduler driven by `TIME_ADVANCED`.

Knows *when* work is due and emits `SCHEDULED_JOB_DUE` work events for each
due job. Knows nothing about game rules — owning subsystems (NPC movement,
combat ticks, delayed world effects) perform the actual work in response.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.scheduler import ScheduledJob
from lorecraft.engine.repos.scheduler_repo import SchedulerRepo
from lorecraft.observability import time_operation
from lorecraft.types import JsonObject


@dataclass(frozen=True)
class SchedulerEventContext:
    game_engine: Engine
    bus: EventBus
    rng: GameRng
    audit_engine: Engine | None = None


class SchedulerService:
    def __init__(
        self, game_engine: Engine, rng: GameRng, audit_engine: Engine | None = None
    ) -> None:
        self._game_engine = game_engine
        self._rng = rng
        self._audit_engine = audit_engine
        self._bus: EventBus | None = None

    def register(self, bus: EventBus) -> None:
        self._bus = bus
        bus.on(GameEvent.TIME_ADVANCED, self._on_time_advanced)

    def schedule(
        self, job_type: str, at_game_epoch: float, payload: JsonObject | None = None
    ) -> str:
        job_id = str(uuid4())
        with Session(self._game_engine) as session:
            SchedulerRepo(session).add(
                ScheduledJob(
                    id=job_id,
                    job_type=job_type,
                    due_at_epoch=at_game_epoch,
                    payload=payload or {},
                    created_at=time.time(),
                )
            )
            session.commit()
        return job_id

    def cancel(self, job_id: str) -> None:
        with Session(self._game_engine) as session:
            repo = SchedulerRepo(session)
            job = repo.get(job_id)
            if job is None or job.status != "pending":
                return
            job.status = "cancelled"
            repo.add(job)
            session.commit()

    def _on_time_advanced(self, event: Event, ctx: object) -> None:
        del ctx
        with time_operation("scheduler_tick"):
            current_epoch = float(event.payload.get("current_epoch", 0.0))  # type: ignore[arg-type]

            with Session(self._game_engine) as session:
                repo = SchedulerRepo(session)
                due_jobs = list(repo.due(current_epoch))
                due_snapshot = [
                    (job.id, job.job_type, dict(job.payload)) for job in due_jobs
                ]
                for job in due_jobs:
                    job.status = "dispatched"
                    repo.add(job)
                session.commit()

            if not due_snapshot or self._bus is None:
                return

            event_ctx = SchedulerEventContext(
                game_engine=self._game_engine,
                bus=self._bus,
                rng=self._rng,
                audit_engine=self._audit_engine,
            )
            for job_id, job_type, payload in due_snapshot:
                self._bus.emit(
                    Event(
                        GameEvent.SCHEDULED_JOB_DUE,
                        {
                            "job_id": job_id,
                            "job_type": job_type,
                            "payload": payload,
                            "current_epoch": current_epoch,
                        },
                    ),
                    event_ctx,
                )
