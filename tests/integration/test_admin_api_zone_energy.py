"""Integration tests for the admin zone-energy router (roadmap_world.md gap #1, Z5):
role-gated read of channel dials + live state, live retuning of a channel, and
direct admin set of a zone/channel intensity (clamped)."""

from __future__ import annotations

from typing import Any

import anyio
from sqlmodel import Session

from lorecraft.engine.models.zone_energy import ZoneEnergyChannelConfig
from lorecraft.main import create_app

from tests.integration._admin_api_support import (
    _SETTINGS,
    _access_token,
    _http,
    _lifespan,
    _make_engines,
)


# Seeded AFTER lifespan startup (world bootstrap seeds the real
# lumenroot/dreamveil/emberthorn channels from world_content/world.yaml); this
# test channel uses a unique id so it never collides with real world content.
def _seed_test_channel(game_engine: Any) -> None:
    with Session(game_engine) as session:
        session.add(
            ZoneEnergyChannelConfig(
                channel="test_channel",
                baseline=50.0,
                max_intensity=100.0,
                regen_per_tick=1.0,
            )
        )
        session.commit()


def test_get_zone_energy_returns_channels_and_states() -> None:
    anyio.run(_test_get_zone_energy)


async def _test_get_zone_energy() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_test_channel(game_engine)
        status, data = await _http(app, "GET", "/admin/zone-energy", token=token)
    assert status == 200
    assert "channels" in data and "states" in data
    by_channel = {c["channel"]: c for c in data["channels"]}
    assert by_channel["test_channel"] == {
        "channel": "test_channel",
        "baseline": 50.0,
        "max_intensity": 100.0,
        "regen_per_tick": 1.0,
    }
    # Channels ordered deterministically by channel id.
    channels = [c["channel"] for c in data["channels"]]
    assert channels == sorted(channels)


def test_get_zone_energy_requires_observer() -> None:
    anyio.run(_test_get_zone_energy_requires_auth)


async def _test_get_zone_energy_requires_auth() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    async with _lifespan(app):
        status, _ = await _http(app, "GET", "/admin/zone-energy")
    # HTTPBearer returns 401/403 without credentials.
    assert status in (401, 403)


def test_post_channel_updates_dial_live() -> None:
    anyio.run(_test_post_channel_dial)


async def _test_post_channel_dial() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_test_channel(game_engine)
        status, data = await _http(
            app,
            "POST",
            "/admin/zone-energy/channels/test_channel",
            body={"regen_per_tick": 7.5},
            token=token,
        )
        assert status == 200
        assert data["regen_per_tick"] == 7.5
        # Other dials untouched when only one field is provided.
        assert data["baseline"] == 50.0
        assert data["max_intensity"] == 100.0

        _, after = await _http(app, "GET", "/admin/zone-energy", token=token)
    channel = next(c for c in after["channels"] if c["channel"] == "test_channel")
    assert channel["regen_per_tick"] == 7.5


def test_post_channel_rejects_baseline_above_ceiling() -> None:
    anyio.run(_test_post_channel_bad_bounds)


async def _test_post_channel_bad_bounds() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_test_channel(game_engine)
        status, _ = await _http(
            app,
            "POST",
            "/admin/zone-energy/channels/test_channel",
            body={"baseline": 150.0},
            token=token,
        )
    assert status == 422


def test_post_channel_unknown_is_404() -> None:
    anyio.run(_test_post_channel_unknown)


async def _test_post_channel_unknown() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/zone-energy/channels/no_such_channel",
            body={"regen_per_tick": 1.0},
            token=token,
        )
    assert status == 404


def test_post_channel_requires_superadmin() -> None:
    anyio.run(_test_post_channel_requires_superadmin)


async def _test_post_channel_requires_superadmin() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token("observer")
    async with _lifespan(app):
        _seed_test_channel(game_engine)
        status, _ = await _http(
            app,
            "POST",
            "/admin/zone-energy/channels/test_channel",
            body={"regen_per_tick": 1.0},
            token=token,
        )
    assert status == 403


def test_post_state_sets_intensity_and_clamps() -> None:
    anyio.run(_test_post_state)


async def _test_post_state() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        _seed_test_channel(game_engine)
        # Set within bounds.
        status, data = await _http(
            app,
            "POST",
            "/admin/zone-energy/state/testzone/test_channel",
            body={"intensity": 30.0},
            token=token,
        )
        assert status == 200
        assert data["zone"] == "testzone"
        assert data["channel"] == "test_channel"
        assert data["intensity"] == 30.0

        # Over the ceiling clamps to max_intensity (100).
        status, data = await _http(
            app,
            "POST",
            "/admin/zone-energy/state/testzone/test_channel",
            body={"intensity": 999.0},
            token=token,
        )
        assert status == 200
        assert data["intensity"] == 100.0

        # The state now shows up in the filtered GET.
        _, filtered = await _http(
            app, "GET", "/admin/zone-energy?zone=testzone", token=token
        )
    zones = {s["zone"] for s in filtered["states"]}
    assert zones == {"testzone"}
    state = next(s for s in filtered["states"] if s["channel"] == "test_channel")
    assert state["intensity"] == 100.0


def test_post_state_unknown_channel_is_404() -> None:
    anyio.run(_test_post_state_unknown)


async def _test_post_state_unknown() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token()
    async with _lifespan(app):
        status, _ = await _http(
            app,
            "POST",
            "/admin/zone-energy/state/testzone/no_such_channel",
            body={"intensity": 10.0},
            token=token,
        )
    assert status == 404


def test_post_state_requires_superadmin() -> None:
    anyio.run(_test_post_state_requires_superadmin)


async def _test_post_state_requires_superadmin() -> None:
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=_SETTINGS, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token("observer")
    async with _lifespan(app):
        _seed_test_channel(game_engine)
        status, _ = await _http(
            app,
            "POST",
            "/admin/zone-energy/state/testzone/test_channel",
            body={"intensity": 10.0},
            token=token,
        )
    assert status == 403
