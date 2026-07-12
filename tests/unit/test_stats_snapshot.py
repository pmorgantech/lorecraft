"""Tests for the player Stats/Score pane snapshot (webui projection).

Sprint 73.9 surfaces unspent `skill_points` in the Stats-pane readout alongside
level/xp; this guards that display projection.
"""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.webui.player.session import stats_snapshot


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def _snapshot(session: Session, player_id: str) -> dict:
    engine = session.get_bind()
    return stats_snapshot(
        session,
        PlayerRepo(session),
        MeterService(engine, GameRng()),
        EffectService(engine, GameRng()),
        player_id,
    )


def test_stats_snapshot_includes_skill_points() -> None:
    with Session(_engine()) as session:
        session.add(
            Player(id="p1", username="hero", current_room_id="r", respawn_room_id="r")
        )
        session.add(
            PlayerStats(player_id="p1", level=3, xp=20, xp_to_next=150, skill_points=4)
        )
        session.commit()

        out = _snapshot(session, "p1")

        assert out["level"] == 3
        assert out["xp"] == 20
        assert out["xp_to_next"] == 150
        assert out["skill_points"] == 4


def test_stats_snapshot_defaults_skill_points_without_stats_row() -> None:
    # Before a PlayerStats row is persisted, the pane shows model defaults
    # (skill_points defaults to 0), the same read-time-default convention
    # level/xp already use.
    with Session(_engine()) as session:
        session.add(
            Player(id="p2", username="fresh", current_room_id="r", respawn_room_id="r")
        )
        session.commit()

        out = _snapshot(session, "p2")

        assert out["skill_points"] == 0
