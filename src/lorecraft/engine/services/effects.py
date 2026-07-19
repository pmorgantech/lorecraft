"""Active-effect service — apply/remove/query plus a scheduler-driven expiry sweep.

See docs/engine/engine_core.md §3.4. Same hybrid shape as MeterService: the class
holds a game_engine for the expiry sweep, but apply()/remove()/active_for()
are stateless per-call, taking the caller's Session explicitly.
"""

from __future__ import annotations

import logging
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

log = logging.getLogger(__name__)


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
        """Apply a new active effect instance. Never commits.

        Calls the effect's `on_apply` hook (if any) after the row is flushed,
        in the caller's transaction — so a room-state effect's gate-open write
        and a raise from it both belong to the triggering action (§3.9).
        """
        effect_def = effects_module.get_registry().get(effect_key)
        if effect_def is None:
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
        if effect_def.on_apply is not None:
            effect_def.on_apply(session, effect)
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
        registry = effects_module.get_registry()
        expired: list[tuple[str, str, str]] = []
        with Session(self._game_engine) as session:
            statement = select(ActiveEffect).where(
                ActiveEffect.expires_at_epoch.is_not(None),  # type: ignore[union-attr]
                ActiveEffect.expires_at_epoch <= current_epoch,  # type: ignore[operator]
            )
            due = list(session.exec(statement).all())
            for effect in due:
                effect_def = registry.get(effect.effect_key)
                if effect_def is not None and effect_def.on_expire is not None:
                    # §3.9: restore what on_apply changed (e.g. re-close a gate).
                    # Isolate each hook in a savepoint so one failure rolls back
                    # only its own writes; keep the row so the sweep retries it
                    # next tick rather than deleting an un-reverted effect.
                    try:
                        with session.begin_nested():
                            effect_def.on_expire(session, effect)
                    except Exception:
                        log.exception(
                            "effect_on_expire_failed effect_id=%s key=%s",
                            effect.id,
                            effect.effect_key,
                        )
                        continue
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
