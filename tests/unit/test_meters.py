"""Unit tests for MeterService (engine_core.md §3.3)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.errors import NotFoundError, ValidationError
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.meters import MeterDef
from lorecraft.engine.game.meters import get_registry as get_meter_registry
from lorecraft.engine.game.rng import GameRng
from lorecraft.models.player import Player, PlayerStats
from lorecraft.engine.repos.meter_repo import MeterRepo
from lorecraft.engine.services.meters import MeterService


def _make_engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


@pytest.fixture
def registered_hp_meter() -> Iterator[None]:
    """Registers a test-scoped "__test_hp__" MeterDef and removes it afterward."""
    registry = get_meter_registry()

    def base_maximum(entity_type, entity_id, session):
        if entity_type == "player":
            stats = session.get(PlayerStats, entity_id)
            return float(stats.max_hp) if stats is not None else 100.0
        return 50.0

    registry.register(
        MeterDef(key="__test_hp__", base_maximum=base_maximum, start_full=True)
    )
    yield
    registry._defs.pop("__test_hp__", None)  # type: ignore[attr-defined]


@pytest.fixture
def registered_fatigue_meter() -> Iterator[None]:
    """Registers a test-scoped "__test_fatigue__" MeterDef with regen, not-start-full."""
    registry = get_meter_registry()
    registry.register(
        MeterDef(
            key="__test_fatigue__",
            base_maximum=lambda entity_type, entity_id, session: 100.0,
            regen_per_tick=10.0,
            start_full=False,
        )
    )
    yield
    registry._defs.pop("__test_fatigue__", None)  # type: ignore[attr-defined]


def test_get_creates_lazily_start_full(registered_hp_meter: None) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        session.add(
            Player(id="p1", username="p1", current_room_id="r", respawn_room_id="r")
        )
        session.add(PlayerStats(player_id="p1", max_hp=80))
        session.commit()

        service = MeterService(engine, GameRng())
        meter = service.get(session, "player", "p1", "__test_hp__")

        assert meter.maximum == 80.0
        assert meter.current == 80.0


def test_get_creates_lazily_not_start_full(registered_fatigue_meter: None) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        service = MeterService(engine, GameRng())
        meter = service.get(session, "player", "p1", "__test_fatigue__")

        assert meter.maximum == 100.0
        assert meter.current == 0.0


def test_get_returns_existing_meter(registered_hp_meter: None) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        session.add(
            Player(id="p1", username="p1", current_room_id="r", respawn_room_id="r")
        )
        session.add(PlayerStats(player_id="p1", max_hp=100))
        session.commit()

        service = MeterService(engine, GameRng())
        first = service.get(session, "player", "p1", "__test_hp__")
        service.adjust(session, first, -20)

        second = service.get(session, "player", "p1", "__test_hp__")
        assert second.current == 80.0


def test_get_rejects_unregistered_key() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        service = MeterService(engine, GameRng())
        with pytest.raises(NotFoundError):
            service.get(session, "player", "p1", "no-such-meter")


def test_adjust_clamps_to_maximum(registered_hp_meter: None) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        session.add(
            Player(id="p1", username="p1", current_room_id="r", respawn_room_id="r")
        )
        session.add(PlayerStats(player_id="p1", max_hp=100))
        session.commit()

        service = MeterService(engine, GameRng())
        meter = service.get(session, "player", "p1", "__test_hp__")
        change = service.adjust(session, meter, 500)

        assert meter.current == 100.0
        assert change.previous == 100.0


def test_adjust_clamps_to_zero_and_reports_depleted(registered_hp_meter: None) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        session.add(
            Player(id="p1", username="p1", current_room_id="r", respawn_room_id="r")
        )
        session.add(PlayerStats(player_id="p1", max_hp=100))
        session.commit()

        service = MeterService(engine, GameRng())
        meter = service.get(session, "player", "p1", "__test_hp__")
        change = service.adjust(session, meter, -500)

        assert meter.current == 0.0
        assert change.depleted is True
        assert change.recovered is False


def test_adjust_reports_recovered_when_crossing_above_zero(
    registered_hp_meter: None,
) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        session.add(
            Player(id="p1", username="p1", current_room_id="r", respawn_room_id="r")
        )
        session.add(PlayerStats(player_id="p1", max_hp=100))
        session.commit()

        service = MeterService(engine, GameRng())
        meter = service.get(session, "player", "p1", "__test_hp__")
        service.adjust(session, meter, -100)  # now at 0

        change = service.adjust(session, meter, 10)
        assert change.recovered is True
        assert change.depleted is False


def test_adjust_does_not_report_depleted_when_already_at_zero(
    registered_hp_meter: None,
) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        session.add(
            Player(id="p1", username="p1", current_room_id="r", respawn_room_id="r")
        )
        session.add(PlayerStats(player_id="p1", max_hp=100))
        session.commit()

        service = MeterService(engine, GameRng())
        meter = service.get(session, "player", "p1", "__test_hp__")
        service.adjust(session, meter, -100)  # now at 0

        change = service.adjust(session, meter, -5)  # still at 0, no new crossing
        assert change.depleted is False


def test_set_current_clamps(registered_hp_meter: None) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        session.add(
            Player(id="p1", username="p1", current_room_id="r", respawn_room_id="r")
        )
        session.add(PlayerStats(player_id="p1", max_hp=100))
        session.commit()

        service = MeterService(engine, GameRng())
        meter = service.get(session, "player", "p1", "__test_hp__")
        service.set_current(session, meter, 250)
        assert meter.current == 100.0

        service.set_current(session, meter, -50)
        assert meter.current == 0.0


def test_recompute_maximum_reclamps_current_without_scaling(
    registered_hp_meter: None,
) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        session.add(
            Player(id="p1", username="p1", current_room_id="r", respawn_room_id="r")
        )
        stats = PlayerStats(player_id="p1", max_hp=100)
        session.add(stats)
        session.commit()

        service = MeterService(engine, GameRng())
        meter = service.get(session, "player", "p1", "__test_hp__")
        assert meter.current == 100.0

        stats.max_hp = 50
        session.add(stats)
        session.commit()

        service.recompute_maximum(session, meter)
        assert meter.maximum == 50.0
        assert meter.current == 50.0  # re-clamped, not scaled down proportionally


def test_recompute_maximum_rejects_unregistered_key() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        service = MeterService(engine, GameRng())
        from lorecraft.models.meters import Meter

        orphan = Meter(
            entity_type="player", entity_id="p1", key="ghost", current=1, maximum=1
        )
        with pytest.raises(ValidationError):
            service.recompute_maximum(session, orphan)


def test_regen_sweep_applies_regen_per_tick_to_existing_meters_only(
    registered_fatigue_meter: None,
) -> None:
    engine = _make_engine()
    bus = EventBus()
    service = MeterService(engine, GameRng())
    service.register(bus)

    with Session(engine) as session:
        # Lazily create a fatigue meter for p1 (starts at 0, not full).
        service.get(session, "player", "p1", "__test_fatigue__")
        session.commit()

    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 10.0}), ctx=None)

    with Session(engine) as session:
        meter = MeterRepo(session).find("player", "p1", "__test_fatigue__")
        assert meter is not None
        assert meter.current == 10.0  # regen_per_tick applied once

    # An entity with no lazily-created meter is untouched (no row created).
    with Session(engine) as session:
        assert MeterRepo(session).find("player", "p2", "__test_fatigue__") is None


def test_regen_sweep_emits_recovered_event(registered_fatigue_meter: None) -> None:
    engine = _make_engine()
    bus = EventBus()
    service = MeterService(engine, GameRng())
    service.register(bus)

    observed: list[dict] = []
    bus.on(GameEvent.METER_RECOVERED, lambda event, ctx: observed.append(event.payload))

    with Session(engine) as session:
        service.get(session, "player", "p1", "__test_fatigue__")  # starts at 0
        session.commit()

    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 10.0}), ctx=None)

    assert len(observed) == 1
    assert observed[0]["entity_id"] == "p1"
    assert observed[0]["key"] == "__test_fatigue__"
