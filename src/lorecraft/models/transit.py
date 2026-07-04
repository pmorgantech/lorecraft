"""Transit line data model (Sprint 29.1, docs/transit_systems.md §4).

Line *configuration* only -- runtime vehicle position is the Tier 1
`MobileRouteState` (Sprint 21, engine_core.md §3.8), keyed
`route_id = f"transit:{line_id}"`; there is deliberately no
`TransitVehicleState` table (the design doc's earlier draft superseded).
Sprint 29.2 builds the `RouteSpec`/`RouteHooks` translation and the
board/disembark commands on top of these tables.
"""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class TransitLine(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    mode: str  # "ferry"|"rail"|"balloon"|"caravan"|... (open-ended, data-driven)
    service_type: str = "local"  # "local" | "express"
    vehicle_room_id: str | None = (
        None  # the moving room; None => virtual/3b (not yet built)
    )
    ticket_item_id: str | None = None  # required to board; None => free
    ticket_consumed: bool = True  # consume on board vs. reusable pass
    reverses: bool = True  # A->B->C then C->B->A; else loop
    loop: bool = False  # C->A jump instead of reversing (only when reverses=False)
    animate_minimap: bool = True
    weather_sensitive: bool = False
    blocking_weather: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class TransitStop(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    line_id: str = Field(foreign_key="transitline.id", index=True)
    room_id: str = Field(foreign_key="room.id")  # the station room (has map_x/map_y)
    sequence: int  # order along the route (0-based, contiguous)
    dwell_ticks: int = 5  # wait time at this stop
    travel_ticks: int = 20  # ticks from THIS stop to the next
    boarding: bool = True  # express passes through non-boarding stops with doors closed
