"""Admin API router for live-tuning the progression config (Sprint 73.4).

Mirrors `clock.py`'s time-ratio endpoint: read + edit the singleton
`ProgressionConfig` row and commit, so an admin retunes the XP curve and per-level
rewards without a restart or reseed. Unlike the clock's `time_ratio` (which a
running background task caches in memory and must be pushed to), nothing caches
progression config in runtime state yet — the Phase 3 reward interpreter reads the
row fresh from the DB per reward — so a plain DB read/write is sufficient here. No
runtime push is needed until something starts caching it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from lorecraft.features.progression.models import ProgressionConfig
from lorecraft.features.progression.repo import ProgressionRepo
from lorecraft.webui.admin.auth import Observer, Superadmin

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _serialize(config: ProgressionConfig) -> dict[str, int]:
    return {
        "base": config.base,
        "step": config.step,
        "coins_per_level": config.coins_per_level,
        "skill_points_per_level": config.skill_points_per_level,
    }


@router.get("/progression/config")
async def get_progression_config(request: Request, _: Observer) -> dict[str, int]:
    state = _state(request)
    with Session(state.game_engine) as session:
        config = ProgressionRepo(session).config()
    if config is None:
        raise HTTPException(
            status_code=503, detail="Progression config not initialized"
        )
    return _serialize(config)


class _ProgressionConfigBody(BaseModel):
    # All optional: an admin tunes one dial (e.g. coins_per_level) without
    # restating the others. Only provided fields are applied.
    base: int | None = None
    step: int | None = None
    coins_per_level: int | None = None
    skill_points_per_level: int | None = None


@router.post("/progression/config")
async def set_progression_config(
    body: _ProgressionConfigBody, request: Request, _: Superadmin
) -> dict[str, int]:
    if body.base is not None and body.base <= 0:
        raise HTTPException(status_code=422, detail="base must be positive")
    if body.step is not None and body.step < 0:
        raise HTTPException(status_code=422, detail="step must be non-negative")
    if body.coins_per_level is not None and body.coins_per_level < 0:
        raise HTTPException(
            status_code=422, detail="coins_per_level must be non-negative"
        )
    if body.skill_points_per_level is not None and body.skill_points_per_level < 0:
        raise HTTPException(
            status_code=422, detail="skill_points_per_level must be non-negative"
        )

    state = _state(request)
    with Session(state.game_engine) as session:
        config = ProgressionRepo(session).config()
        if config is None:
            raise HTTPException(
                status_code=503, detail="Progression config not initialized"
            )
        if body.base is not None:
            config.base = body.base
        if body.step is not None:
            config.step = body.step
        if body.coins_per_level is not None:
            config.coins_per_level = body.coins_per_level
        if body.skill_points_per_level is not None:
            config.skill_points_per_level = body.skill_points_per_level
        session.add(config)
        session.commit()
        result = _serialize(config)
    return result
