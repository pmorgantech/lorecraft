"""Admin API router for live-tuning zone-energy channels (roadmap_world.md gap #1, Z5).

Mirrors `economy.py`: read + edit the DB-backed `ZoneEnergyChannelConfig` dials
(baseline/max_intensity/regen_per_tick) and the live `ZoneEnergyState` rows, so an
admin retunes a channel's drift with no restart or reseed.

Like `RegionPricing` -- and unlike the clock's `time_ratio`, which a running
background task caches in memory and must be pushed to -- nothing caches
`ZoneEnergyChannelConfig` in runtime state: `ZoneEnergyService`'s `TIME_ADVANCED`
drift sweep re-queries each channel's config fresh from the DB every tick. So a
plain DB write is sufficient here; no push-to-running-state is needed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from lorecraft.engine.models.zone_energy import (
    ZoneEnergyChannelConfig,
    ZoneEnergyState,
)
from lorecraft.engine.services.zone_energy import ZoneEnergyService
from lorecraft.errors import NotFoundError
from lorecraft.webui.admin.auth import Observer, Superadmin

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _serialize_config(config: ZoneEnergyChannelConfig) -> dict[str, Any]:
    return {
        "channel": config.channel,
        "baseline": config.baseline,
        "max_intensity": config.max_intensity,
        "regen_per_tick": config.regen_per_tick,
    }


def _serialize_state(state: ZoneEnergyState) -> dict[str, Any]:
    return {
        "zone": state.zone,
        "channel": state.channel,
        "intensity": state.intensity,
        "updated_epoch": state.updated_epoch,
    }


@router.get("/zone-energy")
async def get_zone_energy(
    request: Request, _: Observer, zone: str | None = None
) -> dict[str, Any]:
    """Return channel dials plus current per-`(zone, channel)` state.

    ``zone`` optionally filters the returned state rows (the channel configs are
    global and always returned in full).
    """
    state = _state(request)
    with Session(state.game_engine) as session:
        configs = session.exec(
            select(ZoneEnergyChannelConfig).order_by(
                ZoneEnergyChannelConfig.channel  # type: ignore[arg-type]
            )
        ).all()
        state_query = select(ZoneEnergyState)
        if zone is not None:
            state_query = state_query.where(ZoneEnergyState.zone == zone)
        state_query = state_query.order_by(
            ZoneEnergyState.zone,  # type: ignore[arg-type]
            ZoneEnergyState.channel,  # type: ignore[arg-type]
        )
        states = session.exec(state_query).all()
        return {
            "channels": [_serialize_config(config) for config in configs],
            "states": [_serialize_state(row) for row in states],
        }


class _ChannelConfigBody(BaseModel):
    # All optional: an admin tunes one dial (e.g. regen_per_tick) without
    # restating the others. Only provided fields are applied.
    baseline: float | None = None
    max_intensity: float | None = None
    regen_per_tick: float | None = None


@router.post("/zone-energy/channels/{channel}")
async def set_zone_energy_channel(
    channel: str, body: _ChannelConfigBody, request: Request, _: Superadmin
) -> dict[str, Any]:
    """Retune a channel dial. Channels come from world content; a missing channel
    is a 404 rather than an insert (mirrors the economy region endpoint)."""
    if body.baseline is not None and body.baseline < 0:
        raise HTTPException(status_code=422, detail="baseline must be non-negative")
    if body.max_intensity is not None and body.max_intensity < 0:
        raise HTTPException(
            status_code=422, detail="max_intensity must be non-negative"
        )
    if body.regen_per_tick is not None and body.regen_per_tick < 0:
        raise HTTPException(
            status_code=422, detail="regen_per_tick must be non-negative"
        )

    state = _state(request)
    with Session(state.game_engine) as session:
        config = session.get(ZoneEnergyChannelConfig, channel)
        if config is None:
            raise HTTPException(status_code=404, detail=f"Unknown channel: {channel}")
        if body.baseline is not None:
            config.baseline = body.baseline
        if body.max_intensity is not None:
            config.max_intensity = body.max_intensity
        if body.regen_per_tick is not None:
            config.regen_per_tick = body.regen_per_tick
        # The effective (possibly just-updated) bounds must stay coherent so the
        # drift sweep's [0, max_intensity] clamp keeps working.
        if config.baseline > config.max_intensity:
            raise HTTPException(
                status_code=422,
                detail="baseline must not exceed max_intensity",
            )
        session.add(config)
        session.commit()
        return _serialize_config(config)


class _StateBody(BaseModel):
    intensity: float


@router.post("/zone-energy/state/{zone}/{channel}")
async def set_zone_energy_state(
    zone: str,
    channel: str,
    body: _StateBody,
    request: Request,
    _: Superadmin,
) -> dict[str, Any]:
    """Directly set a zone/channel's current intensity (admin debugging/testing).

    Uses the Tier 1 service's lazy `get()` so an untouched `(zone, channel)` pair
    is materialised at baseline first, then clamped into `[0, max_intensity]` via
    `adjust()` — the same path the drift sweep and future harvest verbs use, so an
    admin cannot poke a value outside the channel's bounds. A `(zone, channel)`
    whose channel has no config is a 404 (the Tier 1 `NotFoundError`).
    """
    if body.intensity < 0:
        raise HTTPException(status_code=422, detail="intensity must be non-negative")

    state = _state(request)
    # The service is stateless (holds only the engine) and the drift sweep reads
    # config fresh from the DB each tick, so a locally-built instance shares the
    # same authoritative state as the always-registered one -- no AppState wiring.
    service = ZoneEnergyService(state.game_engine)
    with Session(state.game_engine) as session:
        try:
            energy = service.get(session, zone, channel)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=exc.message) from exc
        change = service.adjust(session, energy, body.intensity - energy.intensity)
        session.commit()
        return _serialize_state(change.state)
