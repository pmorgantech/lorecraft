"""Weather-driven difficulty on skill-gated terrain (Sprint 44).

Harsh weather makes dangerous, skill-gated wilderness terrain harder to cross —
a **read-through** modifier over global weather (`WorldClock`) + the player's
room terrain, contributed to the one §3.5 modifier resolver (the same way room
auras and terrain-skill gating already work). Weather is *global clock state*, so
a modifier source reads it; there is no materialized per-room effect (that is the
Sprint 39 timed-room-effect primitive's job — localized, TTL effects). Because
movement's terrain gate already resolves `skill.<terrain.required_skill>`, a
blizzard can push a marginal traveller below a mountain pass's required skill.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session

from lorecraft.engine.game import modifiers as modifiers_module
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.features.terrain import definitions as terrain_module
from lorecraft.features.weather.handlers import COLD_WEATHERS

# Weather that makes exposed, skill-gated terrain more dangerous. Reuses the
# warmth feature's COLD_WEATHERS (snow/blizzard/fog) plus the violent-summer set.
HARSH_WEATHERS = COLD_WEATHERS | frozenset({"thunderstorm", "heavy_rain"})

# Flat penalty subtracted from the terrain's required skill during harsh weather;
# tunable. Sized to matter at the margins against required_skill_min (10–30).
HARSH_WEATHER_SKILL_PENALTY = 10.0


class WeatherTerrainModifierSource:
    """Contributes a skill penalty for a player standing on a skill-gated
    terrain during harsh weather (see module docstring)."""

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> Iterable[Modifier]:
        if entity_type != "player":
            return []
        player = session.get(Player, entity_id)
        if player is None:
            return []
        room = session.get(Room, player.current_room_id)
        if room is None:
            return []
        terrain_def = terrain_module.get_registry().get(room.terrain)
        if terrain_def is None or terrain_def.required_discipline is None:
            return []  # sheltered / generic terrain — unaffected by weather
        clock = RoomRepo(session).world_clock()
        if clock is None or clock.weather not in HARSH_WEATHERS:
            return []
        return [
            Modifier(
                # The discipline id doubles as the `skill.<name>` resolver key for
                # the gated terrain check (survival) — Option A namespace.
                f"skill.{terrain_def.required_discipline}",
                "add",
                -HARSH_WEATHER_SKILL_PENALTY,
                f"weather:{clock.weather}",
            )
        ]


# Registered at module import (the §3.5 registry doesn't dedupe, so register
# once here rather than in a lifespan hook that could run twice).
modifiers_module.get_registry().register(WeatherTerrainModifierSource())
