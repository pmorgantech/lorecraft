"""Scheduled mobile entity ("moving room") runtime state (engine_core.md §3.8).

Route *specs* (Waypoint/RouteSpec in services/mobile_route.py) are pure
in-memory dataclasses provided by the owning feature at app lifespan — only
the runtime MobileRouteState is persisted here.
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class MobileRouteState(SQLModel, table=True):
    route_id: str = Field(primary_key=True)
    status: str = "at_stop"  # "at_stop" | "in_transit" | "halted"
    current_index: int = 0
    next_index: int = 1
    direction: int = 1  # +1 / -1
    depart_epoch: float | None = None
    arrive_epoch: float | None = None
