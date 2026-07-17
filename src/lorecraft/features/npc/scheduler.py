"""NPC movement driven by HOUR_CHANGED events."""

from __future__ import annotations

from typing import cast

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.models.world import NPC
from lorecraft.types import JsonObject


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
                        if _apply_schedule_entry(npc, entry):
                            session.add(npc)
                            changed = True
                        break
            if changed:
                session.commit()


def _apply_schedule_entry(npc: NPC, entry: JsonObject) -> bool:
    changed = False

    target = entry.get("target_room_id")
    if isinstance(target, str) and target and target != npc.current_room_id:
        npc.current_room_id = target
        changed = True

    behavior = entry.get("behavior")
    if isinstance(behavior, str) and behavior and behavior != npc.behavior:
        npc.behavior = behavior
        changed = True

    if "ai" in entry:
        raw_ai = entry.get("ai")
        next_ai = cast(JsonObject, dict(raw_ai)) if isinstance(raw_ai, dict) else {}
        if next_ai != npc.ai:
            npc.ai = next_ai
            changed = True

    return changed
