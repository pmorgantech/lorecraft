"""Meter service — command-path get/adjust API plus a scheduler-driven regen sweep.

See docs/engine_core.md §3.3. Hybrid shape (like SchedulerService): the
class holds a game_engine for the regen sweep, but get()/adjust()/
set_current()/recompute_maximum() are stateless per-call, taking the
caller's Session explicitly (command-path code, e.g. Sprint 27 fatigue
drain, Sprint 31 combat damage).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.errors import NotFoundError, ValidationError
from lorecraft.engine.game import meters as meters_module
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.modifiers import resolve_for
from lorecraft.engine.game.rng import GameRng
from lorecraft.models.meters import Meter
from lorecraft.repos.meter_repo import MeterRepo
from lorecraft.services.scheduler import SchedulerEventContext


@dataclass(frozen=True)
class MeterChange:
    """Result of an adjust() call — the caller decides what to do with the
    depleted/recovered flags (primitives emit nothing per the Sprint 16
    convention; queue a domain event from command-path code if you care)."""

    meter: Meter
    previous: float
    delta: float
    depleted: bool  # crossed to 0 on this adjust (not "is currently 0")
    recovered: bool  # crossed above 0 on this adjust


class MeterService:
    def __init__(self, game_engine: Engine, rng: GameRng) -> None:
        self._game_engine = game_engine
        self._rng = rng
        self._bus: EventBus | None = None

    def register(self, bus: EventBus) -> None:
        self._bus = bus
        bus.on(GameEvent.TIME_ADVANCED, self._on_time_advanced)

    def get(
        self, session: Session, entity_type: str, entity_id: str, key: str
    ) -> Meter:
        """Fetch a meter, creating it lazily from its registered MeterDef."""
        repo = MeterRepo(session)
        existing = repo.find(entity_type, entity_id, key)
        if existing is not None:
            return existing

        meter_def = meters_module.get_registry().get(key)
        if meter_def is None:
            raise NotFoundError(
                f"No MeterDef registered for key {key!r}", "not_found_meter_def"
            )
        base = meter_def.base_maximum(entity_type, entity_id, session)
        maximum = resolve_for(session, entity_type, entity_id, f"meter.{key}.max", base)
        current = maximum if meter_def.start_full else 0.0
        return repo.create(entity_type, entity_id, key, current, maximum)

    def adjust(self, session: Session, meter: Meter, delta: float) -> MeterChange:
        """Apply delta, clamped to [0, maximum]."""
        previous = meter.current
        new_current = max(0.0, min(meter.maximum, previous + delta))
        meter.current = new_current
        MeterRepo(session).save(meter)
        return MeterChange(
            meter=meter,
            previous=previous,
            delta=delta,
            depleted=previous > 0 and new_current <= 0,
            recovered=previous <= 0 and new_current > 0,
        )

    def set_current(self, session: Session, meter: Meter, value: float) -> None:
        """Set current directly, clamped to [0, maximum]. Never commits."""
        meter.current = max(0.0, min(meter.maximum, value))
        MeterRepo(session).save(meter)

    def recompute_maximum(self, session: Session, meter: Meter) -> None:
        """Re-resolve maximum from the registered MeterDef + modifiers.

        current is re-clamped to the new maximum, never scaled proportionally.
        """
        meter_def = meters_module.get_registry().get(meter.key)
        if meter_def is None:
            raise ValidationError(
                f"No MeterDef registered for key {meter.key!r}",
                "validation_unknown_meter",
            )
        base = meter_def.base_maximum(meter.entity_type, meter.entity_id, session)
        meter.maximum = resolve_for(
            session, meter.entity_type, meter.entity_id, f"meter.{meter.key}.max", base
        )
        meter.current = max(0.0, min(meter.current, meter.maximum))
        MeterRepo(session).save(meter)

    def _on_time_advanced(self, event: Event, ctx: object) -> None:
        del event, ctx  # regen is per-tick, not epoch-scaled

        registry = meters_module.get_registry()
        # Capture plain values, not the ORM Meter rows: session.commit() expires
        # every attribute by default, and accessing them after the `with` block
        # closes the session raises (can't refresh from a closed session).
        crossings: list[tuple[str, str, str, bool, bool]] = []

        with Session(self._game_engine) as session:
            repo = MeterRepo(session)
            for key in registry.all_keys():
                meter_def = registry.get(key)
                if meter_def is None or meter_def.regen_per_tick == 0:
                    continue
                for meter in repo.all_for_key(key):
                    previous = meter.current
                    new_current = max(
                        0.0, min(meter.maximum, previous + meter_def.regen_per_tick)
                    )
                    if new_current == previous:
                        continue
                    meter.current = new_current
                    repo.save(meter)
                    crossings.append(
                        (
                            meter.entity_type,
                            meter.entity_id,
                            meter.key,
                            previous <= 0 and new_current > 0,
                            previous > 0 and new_current <= 0,
                        )
                    )
            session.commit()

        if self._bus is None:
            return
        event_ctx = SchedulerEventContext(
            game_engine=self._game_engine, bus=self._bus, rng=self._rng
        )
        for entity_type, entity_id, key, recovered, depleted in crossings:
            if recovered:
                self._bus.emit(
                    Event(
                        GameEvent.METER_RECOVERED,
                        {
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "key": key,
                        },
                    ),
                    event_ctx,
                )
            if depleted:
                self._bus.emit(
                    Event(
                        GameEvent.METER_DEPLETED,
                        {
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "key": key,
                        },
                    ),
                    event_ctx,
                )
