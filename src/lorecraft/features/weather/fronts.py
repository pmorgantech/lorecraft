"""Traveling weather fronts — per-zone storms that roll, time out, and rotate (A5).

`docs/scripting_engine_design.md` §A.4. Generalizes the single global weather roll into
*localized storm fronts*: each hour, dormant storms roll their `chance` (seeded RNG, so runs
replay faithfully); on a hit a front activates over the first zone in its `path`, applying a
room `ActiveEffect` to every room there and narrating the zone. The front then travels zone to
zone every `travel_ticks` hours and expires after its rolled duration, cleaning up its effects.

Front state is tracked in memory for the run; determinism lives in the *rolls* (all through
`GameRng`), which is what an audit-log replay reconstructs. Restart-persistent, scheduler-backed
fronts are a later refinement; the roll/travel/expire shape is unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.engine.game import effects as effects_module
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.effects import EffectDef
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.world_context import broadcast_room_async
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.types import JsonObject

log = logging.getLogger(__name__)


def register_storm_effects() -> None:
    """Register the built-in ``storm_lashed`` room effect a weather front applies.

    A marker room-state effect (no stat modifiers yet — those are content detail); its presence
    is what weather-aware systems and the `storm_lashed` room feed read. Idempotent: the effect
    registry overwrites on re-register.
    """
    effects_module.get_registry().register(
        EffectDef(key="storm_lashed", modifiers=lambda effect: [])
    )


@dataclass
class _ActiveFront:
    storm_id: str
    path: list[str]  # area ids, in travel order
    room_effect: str | None
    on_leave: str | None
    travel_ticks: int
    zone_index: int = 0
    ticks_to_travel: int = 0
    ticks_to_expire: int = 0
    applied_effect_ids: list[str] = field(default_factory=list)


class WeatherFrontService:
    """Rolls, advances, and expires localized storm fronts on ``HOUR_CHANGED``."""

    def __init__(
        self,
        game_engine: Engine,
        manager: ConnectionManager,
        rng: GameRng,
        effects: EffectService,
        config: JsonObject,
    ) -> None:
        self._engine = game_engine
        self._manager = manager
        self._rng = rng
        self._effects = effects
        storms = config.get("storms")
        self._storms: dict[str, JsonObject] = (
            {k: v for k, v in storms.items() if isinstance(v, dict)}
            if isinstance(storms, dict)
            else {}
        )
        self._active: dict[str, _ActiveFront] = {}

    def register(self, bus: EventBus) -> None:
        if self._storms:
            bus.on(GameEvent.HOUR_CHANGED, self._on_hour_changed)

    def _on_hour_changed(self, event: Event, ctx: object) -> None:
        del event, ctx
        with Session(self._engine) as session:
            clock = RoomRepo(session).world_clock()
            season = clock.current_season if clock is not None else ""
            epoch = clock.game_epoch if clock is not None else 0.0
            self._advance_fronts(session, epoch)
            self._roll_new_storms(session, season, epoch)
            session.commit()

    # -- rolling -------------------------------------------------------------

    def _roll_new_storms(self, session: Session, season: str, epoch: float) -> None:
        for storm_id, spec in self._storms.items():
            if storm_id in self._active:
                continue
            seasons = spec.get("seasons")
            if isinstance(seasons, list) and season and season not in seasons:
                continue
            chance = spec.get("chance")
            p = float(chance) if isinstance(chance, (int, float)) else 0.0
            if not self._rng.chance(p):
                continue
            self._activate(session, storm_id, spec, epoch)

    def _activate(
        self, session: Session, storm_id: str, spec: JsonObject, epoch: float
    ) -> None:
        raw_path = spec.get("path")
        path = [str(z) for z in raw_path] if isinstance(raw_path, list) else []
        if not path:
            return
        front = _ActiveFront(
            storm_id=storm_id,
            path=path,
            room_effect=_opt_str(spec.get("room_effect")),
            on_leave=_opt_str(spec.get("on_leave")),
            travel_ticks=max(1, _as_int(spec.get("travel_ticks"), 1)),
            ticks_to_expire=self._roll_duration(spec),
        )
        front.ticks_to_travel = front.travel_ticks
        self._active[storm_id] = front
        self._enter_zone(session, front, _opt_str(spec.get("on_enter")), epoch)

    def _roll_duration(self, spec: JsonObject) -> int:
        dur = spec.get("duration_ticks")
        if isinstance(dur, dict):
            lo = _as_int(dur.get("min"), 1)
            hi = _as_int(dur.get("max"), lo)
            return self._rng.randint(min(lo, hi), max(lo, hi))
        return max(1, _as_int(dur, 1))

    # -- lifecycle -----------------------------------------------------------

    def _advance_fronts(self, session: Session, epoch: float) -> None:
        for storm_id in list(self._active):
            front = self._active[storm_id]
            front.ticks_to_expire -= 1
            if front.ticks_to_expire <= 0:
                self._expire(session, front)
                del self._active[storm_id]
                continue
            front.ticks_to_travel -= 1
            if front.ticks_to_travel <= 0 and front.zone_index + 1 < len(front.path):
                self._leave_zone(session, front)
                front.zone_index += 1
                front.ticks_to_travel = front.travel_ticks
                self._enter_zone(session, front, None, epoch)

    def _enter_zone(
        self, session: Session, front: _ActiveFront, on_enter: str | None, epoch: float
    ) -> None:
        zone = front.path[front.zone_index]
        rooms = RoomRepo(session).rooms_in_area(zone)
        front.applied_effect_ids = []
        if front.room_effect:
            for room in rooms:
                try:
                    effect = self._effects.apply(
                        session,
                        entity_type="room",
                        entity_id=room.id,
                        effect_key=front.room_effect,
                        duration_ticks=None,
                        clock_epoch=epoch,
                    )
                    front.applied_effect_ids.append(effect.id)
                except Exception:
                    log.exception(
                        "storm_room_effect_failed storm=%s room=%s",
                        front.storm_id,
                        room.id,
                    )
        text = on_enter or f"A {front.storm_id.replace('_', ' ')} rolls in."
        for room in rooms:
            if not room.indoor:  # sheltered interiors don't see the storm
                broadcast_room_async(self._manager, room.id, text)

    def _leave_zone(self, session: Session, front: _ActiveFront) -> None:
        for effect_id in front.applied_effect_ids:
            self._effects.remove(session, effect_id)
        front.applied_effect_ids = []
        if front.on_leave:
            zone = front.path[front.zone_index]
            for room in RoomRepo(session).rooms_in_area(zone):
                if not room.indoor:  # sheltered interiors don't see the storm
                    broadcast_room_async(self._manager, room.id, front.on_leave)

    def _expire(self, session: Session, front: _ActiveFront) -> None:
        self._leave_zone(session, front)


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default
