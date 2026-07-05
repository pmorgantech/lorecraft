"""NPC movement driven by HOUR_CHANGED events."""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.models.world import NPC


class NpcScheduler:
    def __init__(self, game_engine: Engine) -> None:
        self._game_engine = game_engine

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.HOUR_CHANGED, self._on_hour_changed)

    def _on_hour_changed(self, event: Event, ctx: object) -> None:
        del ctx
        hour = event.payload.get("hour", 0)
        with Session(self._game_engine) as session:
            npcs = session.exec(select(NPC)).all()
            changed = False
            for npc in npcs:
                if not npc.schedule:
                    continue
                for entry in npc.schedule:
                    if entry.get("game_hour") == hour:
                        target_id = str(entry.get("target_room_id", ""))
                        if target_id and target_id != npc.current_room_id:
                            npc.current_room_id = target_id
                            session.add(npc)
                            changed = True
                        break
            if changed:
                session.commit()
