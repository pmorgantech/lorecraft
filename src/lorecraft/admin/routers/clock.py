"""Admin API router for world clock control (pause, resume, time ratio, weather)."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from lorecraft.admin.auth import Observer, Superadmin
from lorecraft.engine.repos.room_repo import RoomRepo

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


@router.get("/clock")
async def get_clock(request: Request, _: Observer) -> dict[str, Any]:
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
    if clock is None:
        raise HTTPException(status_code=503, detail="World clock not initialized")
    return {
        "game_epoch": clock.game_epoch,
        "real_epoch": clock.real_epoch,
        "time_ratio": clock.time_ratio,
        "paused": clock.paused,
        "current_hour": clock.current_hour,
        "current_minute": clock.current_minute,
        "current_day": clock.current_day,
        "current_season": clock.current_season,
        "weather": clock.weather,
    }


@router.post("/clock/pause")
async def pause_clock(request: Request, _: Superadmin) -> dict[str, bool]:
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
        if clock is None:
            raise HTTPException(status_code=503, detail="World clock not initialized")
        clock.paused = True
        session.add(clock)
        session.commit()
    return {"paused": True}


@router.post("/clock/resume")
async def resume_clock(request: Request, _: Superadmin) -> dict[str, bool]:
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
        if clock is None:
            raise HTTPException(status_code=503, detail="World clock not initialized")
        clock.paused = False
        clock.real_epoch = time.time()
        session.add(clock)
        session.commit()
    return {"paused": False}


class _TimeRatioBody(BaseModel):
    ratio: float


@router.post("/clock/time-ratio")
async def set_time_ratio(
    body: _TimeRatioBody, request: Request, _: Superadmin
) -> dict[str, float]:
    if body.ratio <= 0:
        raise HTTPException(status_code=422, detail="ratio must be positive")
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
        if clock is None:
            raise HTTPException(status_code=503, detail="World clock not initialized")
        clock.time_ratio = body.ratio
        session.add(clock)
        session.commit()
    state.clock_runner.time_ratio = body.ratio
    return {"time_ratio": body.ratio}


class _WeatherBody(BaseModel):
    weather: str


_VALID_WEATHER = {
    "clear",
    "light_rain",
    "overcast",
    "hot",
    "thunderstorm",
    "heavy_rain",
    "fog",
    "snow",
    "blizzard",
}


@router.post("/clock/weather")
async def set_weather(
    body: _WeatherBody, request: Request, _: Superadmin
) -> dict[str, str]:
    if body.weather not in _VALID_WEATHER:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown weather. Valid: {sorted(_VALID_WEATHER)}",
        )
    state = _state(request)
    with Session(state.game_engine) as session:
        clock = RoomRepo(session).world_clock()
        if clock is None:
            raise HTTPException(status_code=503, detail="World clock not initialized")
        clock.weather = body.weather
        session.add(clock)
        session.commit()
    return {"weather": body.weather}
