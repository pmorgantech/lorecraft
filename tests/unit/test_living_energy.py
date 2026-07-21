"""Unit tests for the living_energy Tier 2 feature (roadmap_world.md gap #1, Z4):
YAML seeding of ZoneEnergyChannelConfig, seed-if-absent reseed semantics, the
export round-trip, and the imbalance() policy read."""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.engine.models.zone_energy import (
    ZoneEnergyChannelConfig,
    ZoneEnergyState,
)
from lorecraft.engine.repos.zone_energy_repo import ZoneEnergyRepo
from lorecraft.engine.services.zone_energy import ZoneEnergyService
from lorecraft.errors import NotFoundError
from lorecraft.features.living_energy import CHANNELS, imbalance
from lorecraft.world.loader import export_world_document, load_world_yaml
from lorecraft.world.validator import WorldValidationError, validate_world_document

_WORLD_YAML = """
rooms:
  - id: grove
    name: Grove
    description: A quiet grove.
    map_x: 0
    map_y: 0
    zone: whisperwood
zone_energy_channels:
  - channel: lumenroot
    baseline: 60.0
    max_intensity: 100.0
    regen_per_tick: 2.0
  - channel: dreamveil
    baseline: 40.0
    max_intensity: 100.0
    regen_per_tick: 1.0
  - channel: emberthorn
    baseline: 50.0
    max_intensity: 100.0
    regen_per_tick: 4.0
"""


def _make_engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def _write_world(tmp_path, text: str = _WORLD_YAML):
    source = tmp_path / "world.yaml"
    source.write_text(text, encoding="utf-8")
    return source


# --- Z4: channel constant --------------------------------------------------


def test_channels_are_the_three_living_energies() -> None:
    assert CHANNELS == ("lumenroot", "dreamveil", "emberthorn")


# --- Z4: YAML seeding ------------------------------------------------------


def test_loader_seeds_channel_configs(tmp_path) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        load_world_yaml(_write_world(tmp_path), session)
        session.commit()

        configs = {
            c.channel: c for c in session.exec(select(ZoneEnergyChannelConfig)).all()
        }
    assert set(configs) == {"lumenroot", "dreamveil", "emberthorn"}
    assert configs["lumenroot"].baseline == 60.0
    assert configs["dreamveil"].regen_per_tick == 1.0
    assert configs["emberthorn"].max_intensity == 100.0


def test_loader_seeds_are_absent_when_section_omitted(tmp_path) -> None:
    engine = _make_engine()
    source = _write_world(
        tmp_path,
        """
rooms:
  - id: grove
    name: Grove
    description: A quiet grove.
    map_x: 0
    map_y: 0
""",
    )
    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()
        assert session.exec(select(ZoneEnergyChannelConfig)).all() == []


def test_reimport_does_not_clobber_live_tuned_config(tmp_path) -> None:
    """Seed-if-absent: an admin's live retuning survives a re-import."""
    engine = _make_engine()
    source = _write_world(tmp_path)
    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()

    # Simulate an admin retuning lumenroot live via the admin surface.
    with Session(engine) as session:
        config = session.get(ZoneEnergyChannelConfig, "lumenroot")
        assert config is not None
        config.baseline = 15.0
        config.regen_per_tick = 9.0
        session.add(config)
        session.commit()

    # Re-import the same YAML (baseline 60.0) — the live value must remain.
    with Session(engine) as session:
        load_world_yaml(source, session)
        session.commit()
        config = session.get(ZoneEnergyChannelConfig, "lumenroot")
        assert config is not None
        assert config.baseline == 15.0
        assert config.regen_per_tick == 9.0


def test_reimport_seeds_newly_added_channel(tmp_path) -> None:
    engine = _make_engine()
    # First import with only lumenroot.
    with Session(engine) as session:
        load_world_yaml(
            _write_world(
                tmp_path,
                """
rooms:
  - id: grove
    name: Grove
    description: A quiet grove.
    map_x: 0
    map_y: 0
zone_energy_channels:
  - channel: lumenroot
    baseline: 60.0
    max_intensity: 100.0
    regen_per_tick: 2.0
""",
            ),
            session,
        )
        session.commit()

    # Re-import with a second channel added — seed-if-absent adds only the new one.
    with Session(engine) as session:
        load_world_yaml(_write_world(tmp_path), session)
        session.commit()
        channels = {
            c.channel for c in session.exec(select(ZoneEnergyChannelConfig)).all()
        }
    assert channels == {"lumenroot", "dreamveil", "emberthorn"}


def test_export_round_trips_channel_configs(tmp_path) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        load_world_yaml(_write_world(tmp_path), session)
        session.commit()

        document = export_world_document(session)
    by_channel = {c.channel: c for c in document.zone_energy_channels}
    assert set(by_channel) == {"lumenroot", "dreamveil", "emberthorn"}
    assert by_channel["dreamveil"].baseline == 40.0
    assert by_channel["emberthorn"].regen_per_tick == 4.0
    # Channels export in deterministic channel order.
    assert [c.channel for c in document.zone_energy_channels] == [
        "dreamveil",
        "emberthorn",
        "lumenroot",
    ]


# --- Z4: validator ---------------------------------------------------------


def test_validator_rejects_baseline_above_ceiling() -> None:
    with pytest.raises(WorldValidationError, match="exceeds max_intensity"):
        validate_world_document(
            {
                "zone_energy_channels": [
                    {
                        "channel": "lumenroot",
                        "baseline": 120.0,
                        "max_intensity": 100.0,
                        "regen_per_tick": 2.0,
                    }
                ]
            }
        )


def test_validator_rejects_negative_regen() -> None:
    with pytest.raises(WorldValidationError):
        validate_world_document(
            {
                "zone_energy_channels": [
                    {
                        "channel": "lumenroot",
                        "baseline": 50.0,
                        "max_intensity": 100.0,
                        "regen_per_tick": -1.0,
                    }
                ]
            }
        )


# --- Z4: imbalance() policy ------------------------------------------------


def _seed_all_channels(session: Session) -> None:
    session.add(
        ZoneEnergyChannelConfig(
            channel="lumenroot", baseline=60.0, max_intensity=100.0, regen_per_tick=2.0
        )
    )
    session.add(
        ZoneEnergyChannelConfig(
            channel="dreamveil", baseline=40.0, max_intensity=100.0, regen_per_tick=1.0
        )
    )
    session.add(
        ZoneEnergyChannelConfig(
            channel="emberthorn", baseline=50.0, max_intensity=100.0, regen_per_tick=4.0
        )
    )
    session.commit()


def test_imbalance_uses_config_baseline_for_untouched_zone(tmp_path) -> None:
    """No state rows yet -> each channel contributes its baseline; spread of the
    seeded baselines (60/40/50) is 20.0. imbalance must NOT create rows."""
    engine = _make_engine()
    with Session(engine) as session:
        _seed_all_channels(session)
        assert imbalance(session, "whisperwood") == pytest.approx(20.0)
        # Pure read: no ZoneEnergyState rows materialised.
        assert session.exec(select(ZoneEnergyState)).all() == []


def test_imbalance_zero_when_all_channels_equal(tmp_path) -> None:
    engine = _make_engine()
    with Session(engine) as session:
        for channel in CHANNELS:
            session.add(
                ZoneEnergyChannelConfig(
                    channel=channel,
                    baseline=50.0,
                    max_intensity=100.0,
                    regen_per_tick=1.0,
                )
            )
        session.commit()
        assert imbalance(session, "whisperwood") == pytest.approx(0.0)


def test_imbalance_reflects_drawn_down_channel() -> None:
    engine = _make_engine()
    service = ZoneEnergyService(engine)
    with Session(engine) as session:
        _seed_all_channels(session)
        # Materialise all three at baseline, then draw emberthorn down to 10.
        for channel in CHANNELS:
            service.get(session, "whisperwood", channel)
        ember = ZoneEnergyRepo(session).find("whisperwood", "emberthorn")
        assert ember is not None
        service.adjust(session, ember, -40.0)  # 50 -> 10
        session.commit()
        # Intensities now 60 (lumenroot), 40 (dreamveil), 10 (emberthorn).
        assert imbalance(session, "whisperwood") == pytest.approx(50.0)


def test_imbalance_raises_for_unregistered_channel() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        # Only two of the three channels are seeded.
        session.add(
            ZoneEnergyChannelConfig(
                channel="lumenroot",
                baseline=60.0,
                max_intensity=100.0,
                regen_per_tick=2.0,
            )
        )
        session.add(
            ZoneEnergyChannelConfig(
                channel="dreamveil",
                baseline=40.0,
                max_intensity=100.0,
                regen_per_tick=1.0,
            )
        )
        session.commit()
        with pytest.raises(NotFoundError):
            imbalance(session, "whisperwood")
