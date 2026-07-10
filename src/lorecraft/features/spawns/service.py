"""Area spawn / respawn controllers (scripting engine A6).

`docs/scripting_engine_design.md` §3.4. Keeps a zone feeling alive: each spawner maintains up to
``max_count`` clones of a template NPC within an ``area``, topping the population back up every
``every_ticks`` if clones have wandered off, been removed, or slain. Clones are stamped with a
shared id prefix (``<spawn_id>#<n>``) so the controller can recognise its own and count them, and
placed in a random area room via the seeded RNG (so runs replay faithfully).

Tier 2 feature ``spawns``. Like the other tick services it holds the live engine/rng and is wired
in ``main.py``. Clones copy the template's dialogue and ``ai`` config, so a spawned creature can
itself wander (A3).
"""

from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.world import NPC
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.types import JsonObject

log = logging.getLogger(__name__)


class SpawnControllerService:
    """Tops up per-area NPC populations on a periodic tick."""

    def __init__(self, game_engine: Engine, rng: GameRng, config: JsonObject) -> None:
        self._engine = game_engine
        self._rng = rng
        spawns = config.get("spawns")
        self._spawns: dict[str, JsonObject] = (
            {k: v for k, v in spawns.items() if isinstance(v, dict)}
            if isinstance(spawns, dict)
            else {}
        )
        self._ticks: dict[str, int] = {}

    def register(self, bus: EventBus) -> None:
        if self._spawns:
            bus.on(GameEvent.TIME_ADVANCED, self._on_tick)

    def _on_tick(self, event: Event, ctx: object) -> None:
        del event, ctx
        with Session(self._engine) as session:
            changed = False
            for spawn_id, spec in self._spawns.items():
                if self._maybe_spawn(session, spawn_id, spec):
                    changed = True
            if changed:
                session.commit()

    def _maybe_spawn(self, session: Session, spawn_id: str, spec: JsonObject) -> bool:
        every = max(1, _as_int(spec.get("every_ticks"), 1))
        count = self._ticks.get(spawn_id, 0) + 1
        if count < every:
            self._ticks[spawn_id] = count
            return False
        self._ticks[spawn_id] = 0

        area = spec.get("area")
        template_id = spec.get("template")
        if not isinstance(area, str) or not isinstance(template_id, str):
            return False
        template = session.get(NPC, template_id)
        if template is None:
            return False
        max_count = max(0, _as_int(spec.get("max_count"), 0))

        prefix = f"{spawn_id}#"
        live = [
            npc for npc in session.exec(select(NPC)).all() if npc.id.startswith(prefix)
        ]
        rooms = [room.id for room in RoomRepo(session).rooms_in_area(area)]
        if not rooms:
            return False

        spawned = False
        for _ in range(max_count - len(live)):
            room_id = self._rng.choice(sorted(rooms))
            session.add(_clone(template, prefix, room_id))
            spawned = True
        return spawned


def _clone(template: NPC, prefix: str, room_id: str) -> NPC:
    return NPC(
        id=f"{prefix}{uuid4().hex[:8]}",
        name=template.name,
        description=template.description,
        current_room_id=room_id,
        home_room_id=room_id,
        dialogue_tree_id=template.dialogue_tree_id,
        behavior=template.behavior,
        max_hp=template.max_hp,
        loot_table=dict(template.loot_table),
        triggers=list(template.triggers),
        ai=dict(template.ai),
    )


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default
