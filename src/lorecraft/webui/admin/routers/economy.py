"""Admin API router for live-tuning per-zone region pricing (Sprint 76.2).

Mirrors `progression.py`: read + edit the DB-backed `RegionPricing` rows and
commit, so an admin retunes zone price multipliers and per-good bias without a
restart or reseed. Like progression config -- and unlike the clock's
`time_ratio`, which a running background task caches in memory and must be pushed
to -- nothing caches `RegionPricing` in runtime state; `features/economy/service.py`
reads the row fresh from the DB per transaction. So a plain DB read/write is
sufficient here; no runtime push is needed.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from lorecraft.features.economy.models import RegionPricing
from lorecraft.features.economy.repo import EconomyRepo
from lorecraft.webui.admin.auth import Observer, Superadmin

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _serialize(region: RegionPricing) -> dict[str, Any]:
    return {
        "zone": region.zone,
        "region_mult": region.region_mult,
        "bias": dict(region.bias),
    }


@router.get("/economy/regions")
async def get_economy_regions(request: Request, _: Observer) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        regions = EconomyRepo(session).all_regions()
        return [_serialize(region) for region in regions]


class _RegionPricingBody(BaseModel):
    # Both optional: an admin tunes one dial (e.g. region_mult) without restating
    # the other. Only provided fields are applied.
    region_mult: float | None = None
    bias: dict[str, float] | None = None


@router.post("/economy/regions/{zone}")
async def set_economy_region(
    zone: str, body: _RegionPricingBody, request: Request, _: Superadmin
) -> dict[str, Any]:
    if body.region_mult is not None and body.region_mult <= 0:
        raise HTTPException(status_code=422, detail="region_mult must be positive")

    state = _state(request)
    with Session(state.game_engine) as session:
        # Zones come from world content; the admin UI tunes existing rows only and
        # never creates new zones, so a missing zone is a 404 rather than an insert.
        region = EconomyRepo(session).region_for_zone(zone)
        if region is None:
            raise HTTPException(status_code=404, detail=f"Unknown zone: {zone}")
        if body.region_mult is not None:
            region.region_mult = body.region_mult
        if body.bias is not None:
            # Replace the bias map wholesale (simplest semantics -- avoids
            # partial-merge ambiguity over which per-good keys were meant to clear).
            region.bias = dict(body.bias)
        session.add(region)
        session.commit()
        return _serialize(region)
