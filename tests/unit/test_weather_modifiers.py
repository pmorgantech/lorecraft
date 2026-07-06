"""Sprint 44 — weather-driven terrain difficulty (WeatherTerrainModifierSource).

Harsh weather subtracts a penalty from the required skill of a skill-gated
terrain, read through the same §3.5 resolver movement's terrain gate uses.
"""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.modifiers import resolve_for
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room, WorldClock
from lorecraft.features.weather.modifiers import HARSH_WEATHER_SKILL_PENALTY


def _world(terrain: str, weather: str) -> object:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(
            Room(
                id="pass",
                name="Pass",
                description="",
                map_x=0,
                map_y=0,
                terrain=terrain,
            )
        )
        session.add(
            Player(
                id="p1", username="u", current_room_id="pass", respawn_room_id="pass"
            )
        )
        session.add(WorldClock(game_epoch=0.0, real_epoch=0.0, weather=weather))
        session.commit()
    return engine


def test_harsh_weather_penalizes_skill_gated_terrain() -> None:
    engine = _world(terrain="mountain", weather="blizzard")  # mountain needs survival
    with Session(engine) as session:  # type: ignore[arg-type]
        effective = resolve_for(session, "player", "p1", "skill.survival", 25.0)
    assert effective == 25.0 - HARSH_WEATHER_SKILL_PENALTY


def test_clear_weather_leaves_terrain_skill_unchanged() -> None:
    engine = _world(terrain="mountain", weather="clear")
    with Session(engine) as session:  # type: ignore[arg-type]
        assert resolve_for(session, "player", "p1", "skill.survival", 25.0) == 25.0


def test_sheltered_terrain_is_unaffected_by_harsh_weather() -> None:
    # "normal" terrain has no required_skill, so no weather penalty applies.
    engine = _world(terrain="normal", weather="blizzard")
    with Session(engine) as session:  # type: ignore[arg-type]
        assert resolve_for(session, "player", "p1", "skill.survival", 25.0) == 25.0
