"""Timed room flavor events for exploration."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.world_context import broadcast_room_async
from lorecraft.engine.models.world import Room


class RoomAmbientService:
    """Broadcasts authored ``ambient_events`` for occupied rooms on world ticks."""

    def __init__(
        self, game_engine: Engine, manager: ConnectionManager, rng: GameRng
    ) -> None:
        self._engine = game_engine
        self._manager = manager
        self._rng = rng
        self._ticks: dict[tuple[str, int], int] = {}

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.TIME_ADVANCED, self._on_time_advanced)

    def _on_time_advanced(self, event: Event, ctx: object) -> None:
        del event, ctx
        occupied = self._manager.occupied_rooms()
        if not occupied:
            return
        with Session(self._engine) as session:
            rooms = session.exec(select(Room).where(col(Room.id).in_(occupied))).all()
        for room in rooms:
            self._tick_room(room)

    def _tick_room(self, room: Room) -> None:
        for index, spec in enumerate(room.ambient_events):
            text = spec.get("text")
            if not isinstance(text, str) or not text:
                continue
            every_ticks = max(1, _as_int(spec.get("every_ticks"), 1))
            key = (room.id, index)
            count = self._ticks.get(key, 0) + 1
            if count < every_ticks:
                self._ticks[key] = count
                continue
            self._ticks[key] = 0

            chance = _as_float(spec.get("chance"), 1.0)
            if self._rng.chance(max(0.0, min(1.0, chance))):
                broadcast_room_async(self._manager, room.id, text)


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _as_float(value: object, default: float) -> float:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else default
    )
