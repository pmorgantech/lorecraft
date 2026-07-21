"""Unit tests for ZoneEnergyState/ZoneEnergyChannelConfig, ZoneEnergyRepo, and
ZoneEnergyService (roadmap_world.md gap #1, Tier 1 — tasks Z1/Z2/Z3)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.models.zone_energy import (
    ZoneEnergyChannelConfig,
)
from lorecraft.engine.repos.zone_energy_repo import ZoneEnergyRepo
from lorecraft.engine.services.zone_energy import ZoneEnergyService
from lorecraft.errors import NotFoundError


def _make_engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def _seed_config(
    session: Session,
    channel: str,
    *,
    baseline: float,
    max_intensity: float,
    regen_per_tick: float,
) -> None:
    session.add(
        ZoneEnergyChannelConfig(
            channel=channel,
            baseline=baseline,
            max_intensity=max_intensity,
            regen_per_tick=regen_per_tick,
        )
    )
    session.commit()


# --- Z1: model + repo ------------------------------------------------------


def test_repo_find_channel_config_returns_none_when_absent() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        assert ZoneEnergyRepo(session).find_channel_config("lumenroot") is None


def test_repo_find_channel_config_returns_seeded_config() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        config = ZoneEnergyRepo(session).find_channel_config("lumenroot")
        assert config is not None
        assert config.baseline == 50.0
        assert config.max_intensity == 100.0
        assert config.regen_per_tick == 5.0


def test_repo_create_and_find_roundtrip() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        repo = ZoneEnergyRepo(session)
        assert repo.find("grove", "lumenroot") is None
        created = repo.create("grove", "lumenroot", 40.0)
        assert created.intensity == 40.0
        assert created.updated_epoch is None

        found = repo.find("grove", "lumenroot")
        assert found is not None
        assert found.zone == "grove"
        assert found.channel == "lumenroot"
        assert found.intensity == 40.0


def test_repo_composite_pk_rejects_duplicate_zone_channel() -> None:
    """The (zone, channel) composite PK is enforced at the DB level: a second
    row for the same pair raises rather than silently overwriting."""
    engine = _make_engine()
    with Session(engine) as session:
        repo = ZoneEnergyRepo(session)
        repo.create("grove", "lumenroot", 40.0)
        with pytest.raises(IntegrityError):
            repo.create("grove", "lumenroot", 99.0)


def test_repo_same_channel_different_zones_coexist() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        repo = ZoneEnergyRepo(session)
        repo.create("grove", "lumenroot", 40.0)
        repo.create("marsh", "lumenroot", 10.0)
        session.commit()

        states = repo.all_states()
        assert {(s.zone, s.channel) for s in states} == {
            ("grove", "lumenroot"),
            ("marsh", "lumenroot"),
        }


# --- Z2: service get/adjust ------------------------------------------------


def test_get_creates_lazily_at_baseline() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        service = ZoneEnergyService(engine)
        state = service.get(session, "grove", "lumenroot")
        assert state.intensity == 50.0
        assert state.zone == "grove"
        assert state.channel == "lumenroot"


def test_get_returns_existing_state() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        service = ZoneEnergyService(engine)
        first = service.get(session, "grove", "lumenroot")
        service.adjust(session, first, -20.0)

        second = service.get(session, "grove", "lumenroot")
        assert second.intensity == 30.0


def test_get_rejects_unregistered_channel() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        service = ZoneEnergyService(engine)
        with pytest.raises(NotFoundError):
            service.get(session, "grove", "no-such-channel")


def test_adjust_within_bounds_reports_no_clamp() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        service = ZoneEnergyService(engine)
        state = service.get(session, "grove", "lumenroot")
        change = service.adjust(session, state, -10.0)

        assert change.previous == 50.0
        assert change.new == 40.0
        assert change.delta == -10.0
        assert change.clamped_low is False
        assert change.clamped_high is False
        assert state.intensity == 40.0


def test_adjust_clamps_at_zero() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        service = ZoneEnergyService(engine)
        state = service.get(session, "grove", "lumenroot")
        change = service.adjust(session, state, -500.0)

        assert state.intensity == 0.0
        assert change.new == 0.0
        assert change.clamped_low is True
        assert change.clamped_high is False


def test_adjust_clamps_at_max_intensity() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        service = ZoneEnergyService(engine)
        state = service.get(session, "grove", "lumenroot")
        change = service.adjust(session, state, 500.0)

        assert state.intensity == 100.0
        assert change.new == 100.0
        assert change.clamped_high is True
        assert change.clamped_low is False


# --- Z3: TIME_ADVANCED drift sweep -----------------------------------------


def _tick(engine, bus: EventBus, epoch: float = 10.0) -> None:
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": epoch}), ctx=None)


def test_sweep_regens_depleted_zone_toward_baseline() -> None:
    engine = _make_engine()
    bus = EventBus()
    service = ZoneEnergyService(engine)
    service.register(bus)

    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        state = service.get(session, "grove", "lumenroot")
        service.adjust(session, state, -30.0)  # now 20, below baseline 50
        session.commit()

    _tick(engine, bus, epoch=42.0)

    with Session(engine) as session:
        state = ZoneEnergyRepo(session).find("grove", "lumenroot")
        assert state is not None
        assert state.intensity == 25.0  # drifted up by regen_per_tick
        assert state.updated_epoch == 42.0


def test_sweep_decays_over_baseline_zone_toward_baseline() -> None:
    engine = _make_engine()
    bus = EventBus()
    service = ZoneEnergyService(engine)
    service.register(bus)

    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        state = service.get(session, "grove", "lumenroot")
        service.adjust(session, state, 30.0)  # now 80, above baseline 50
        session.commit()

    _tick(engine, bus)

    with Session(engine) as session:
        state = ZoneEnergyRepo(session).find("grove", "lumenroot")
        assert state is not None
        assert state.intensity == 75.0  # drifted down by regen_per_tick


def test_sweep_does_not_overshoot_baseline() -> None:
    engine = _make_engine()
    bus = EventBus()
    service = ZoneEnergyService(engine)
    service.register(bus)

    with Session(engine) as session:
        _seed_config(
            session,
            "lumenroot",
            baseline=50.0,
            max_intensity=100.0,
            regen_per_tick=5.0,
        )
        state = service.get(session, "grove", "lumenroot")
        service.adjust(session, state, -2.0)  # now 48, only 2 below baseline
        session.commit()

    _tick(engine, bus)

    with Session(engine) as session:
        state = ZoneEnergyRepo(session).find("grove", "lumenroot")
        assert state is not None
        assert state.intensity == 50.0  # snapped exactly to baseline, no overshoot


def test_sweep_noop_at_baseline_leaves_row_untouched() -> None:
    engine = _make_engine()
    bus = EventBus()
    service = ZoneEnergyService(engine)
    service.register(bus)

    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        service.get(session, "grove", "lumenroot")  # created exactly at baseline 50
        session.commit()

    _tick(engine, bus)

    with Session(engine) as session:
        state = ZoneEnergyRepo(session).find("grove", "lumenroot")
        assert state is not None
        assert state.intensity == 50.0
        assert state.updated_epoch is None  # untouched — no drift, no epoch stamp


def test_sweep_channels_and_zones_do_not_interfere() -> None:
    engine = _make_engine()
    bus = EventBus()
    service = ZoneEnergyService(engine)
    service.register(bus)

    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        _seed_config(
            session, "emberthorn", baseline=20.0, max_intensity=40.0, regen_per_tick=2.0
        )
        # grove/lumenroot depleted, marsh/lumenroot over baseline,
        # grove/emberthorn depleted.
        grove_lumen = service.get(session, "grove", "lumenroot")
        service.adjust(session, grove_lumen, -30.0)  # 20
        marsh_lumen = service.get(session, "marsh", "lumenroot")
        service.adjust(session, marsh_lumen, 30.0)  # 80
        grove_ember = service.get(session, "grove", "emberthorn")
        service.adjust(session, grove_ember, -20.0)  # 0
        session.commit()

    _tick(engine, bus)

    with Session(engine) as session:
        repo = ZoneEnergyRepo(session)
        gl = repo.find("grove", "lumenroot")
        ml = repo.find("marsh", "lumenroot")
        ge = repo.find("grove", "emberthorn")
        assert gl is not None and gl.intensity == 25.0  # regen +5 toward 50
        assert ml is not None and ml.intensity == 75.0  # decay -5 toward 50
        assert ge is not None and ge.intensity == 2.0  # regen +2 toward 20 (own rate)


def test_sweep_touches_only_existing_rows() -> None:
    engine = _make_engine()
    bus = EventBus()
    service = ZoneEnergyService(engine)
    service.register(bus)

    with Session(engine) as session:
        _seed_config(
            session, "lumenroot", baseline=50.0, max_intensity=100.0, regen_per_tick=5.0
        )
        session.commit()

    _tick(engine, bus)

    # No (zone, channel) pair was ever touched, so no row exists to drift.
    with Session(engine) as session:
        assert ZoneEnergyRepo(session).all_states() == []
