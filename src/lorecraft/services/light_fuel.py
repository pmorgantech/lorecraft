"""Lit light-source fuel drain (docs/inventory_equipment.md §8).

Engine-holding schedulable, same shape as MeterService/EffectService's
regen/expiry sweeps: on every TIME_ADVANCED tick, every item instance with
`lit.lit == true` drains one point of durability; hitting zero extinguishes
it. Opens its own short-lived session and commits it directly (no
GameContext exists in this scheduler-driven sweep).
"""

from __future__ import annotations

from sqlalchemy import Engine
from sqlmodel import Session, select

from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.models.items import ItemInstance
from lorecraft.engine.services.item_components import (
    get_component_state,
    set_component_state,
)


class LightFuelService:
    def __init__(self, game_engine: Engine) -> None:
        self.game_engine = game_engine

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.TIME_ADVANCED, self._on_time_advanced)

    def _on_time_advanced(self, event: Event, ctx: object) -> None:
        del event, ctx
        with Session(self.game_engine) as session:
            for instance in session.exec(select(ItemInstance)).all():
                lit_state = get_component_state(instance, "lit")
                if not isinstance(lit_state, dict) or not lit_state.get("lit"):
                    continue

                durability_state = get_component_state(instance, "durability")
                if not isinstance(durability_state, dict):
                    continue
                current = durability_state.get("current")
                if not isinstance(current, (int, float)):
                    continue

                new_current = max(0.0, current - 1)
                set_component_state(
                    session, instance, "durability", {"current": new_current}
                )
                if new_current <= 0:
                    set_component_state(session, instance, "lit", {"lit": False})
            session.commit()
