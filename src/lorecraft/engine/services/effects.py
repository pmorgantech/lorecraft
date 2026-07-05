"""Active-effect service — apply/remove/query plus a scheduler-driven expiry sweep.

See docs/engine_core.md §3.4. Same hybrid shape as MeterService: the class
holds a game_engine for the expiry sweep, but apply()/remove()/active_for()
are stateless per-call, taking the caller's Session explicitly.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.errors import ValidationError
from lorecraft.engine.game import effects as effects_module
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.meters import ActiveEffect
from lorecraft.engine.services.scheduler import SchedulerEventContext
from lorecraft.types import JsonObject


class EffectService:
    def __init__(self, game_engine: Engine, rng: GameRng) -> None:
        self._game_engine = game_engine
        self._rng = rng
        self._bus: EventBus | None = None

    def register(self, bus: EventBus) -> None:
        self._bus = bus
        bus.on(GameEvent.TIME_ADVANCED, self._on_time_advanced)

    def apply(
        self,
        session: Session,
        entity_type: str,
        entity_id: str,
        effect_key: str,
        *,
        duration_ticks: float | None,
        payload: JsonObject | None = None,
        clock_epoch: float,
    ) -> ActiveEffect:
        """Apply a new active effect instance. Never commits."""
        if effect_key not in effects_module.get_registry():
            raise ValidationError(
                f"Unknown effect_key {effect_key!r}", "validation_unknown_effect"
            )
        effect = ActiveEffect(
            id=str(uuid4()),
            entity_type=entity_type,
            entity_id=entity_id,
            effect_key=effect_key,
            payload=payload or {},
            applied_at_epoch=clock_epoch,
            expires_at_epoch=(
                clock_epoch + duration_ticks if duration_ticks is not None else None
            ),
        )
        session.add(effect)
        session.flush()
        return effect

    def remove(self, session: Session, effect_id: str) -> None:
        """Remove an active effect by ID. Never commits."""
        effect = session.get(ActiveEffect, effect_id)
        if effect is not None:
            session.delete(effect)
            session.flush()

    def active_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> list[ActiveEffect]:
        statement = select(ActiveEffect).where(
            ActiveEffect.entity_type == entity_type,
            ActiveEffect.entity_id == entity_id,
        )
        return list(session.exec(statement).all())

    def _on_time_advanced(self, event: Event, ctx: object) -> None:
        del ctx
        current_epoch = float(event.payload.get("current_epoch", 0.0))  # type: ignore[arg-type]

        # Capture plain values, not the ORM ActiveEffect rows: session.commit()
        # expires every attribute by default, and a deleted+expired row can't
        # be refreshed from a closed session.
        expired: list[tuple[str, str, str]] = []
        with Session(self._game_engine) as session:
            statement = select(ActiveEffect).where(
                ActiveEffect.expires_at_epoch.is_not(None),  # type: ignore[union-attr]
                ActiveEffect.expires_at_epoch <= current_epoch,  # type: ignore[operator]
            )
            due = list(session.exec(statement).all())
            for effect in due:
                expired.append(
                    (effect.entity_type, effect.entity_id, effect.effect_key)
                )
                session.delete(effect)
            session.commit()

        if not expired or self._bus is None:
            return
        event_ctx = SchedulerEventContext(
            game_engine=self._game_engine, bus=self._bus, rng=self._rng
        )
        for entity_type, entity_id, effect_key in expired:
            self._bus.emit(
                Event(
                    GameEvent.EFFECT_EXPIRED,
                    {
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                        "effect_key": effect_key,
                    },
                ),
                event_ctx,
            )
