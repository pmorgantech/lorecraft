"""Meter and timed-effect table definitions (engine_core.md §3.3–3.4)."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class Meter(SQLModel, table=True):
    """A named, bounded resource (hp, fatigue, ...) for any entity.

    One primitive replaces one column per resource. Rows are created lazily
    by MeterService.get() from a registered MeterDef — there is no row until
    the meter is first touched.

    Invariant: at most one row per (entity_type, entity_id, key).
    """

    id: int | None = Field(default=None, primary_key=True)
    entity_type: str = Field(index=True)  # "player" | "npc" (open set)
    entity_id: str = Field(index=True)
    key: str = Field(index=True)  # "hp", "fatigue", ... (registered via MeterDef)
    current: float
    maximum: float


class ActiveEffect(SQLModel, table=True):
    """A clock-driven buff/debuff on an entity.

    Distinct from equipment effects (last while equipped) and traits
    (semi-permanent): these fade on their own via expires_at_epoch, swept by
    EffectService._on_time_advanced().
    """

    id: str = Field(primary_key=True)  # uuid4
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    effect_key: str  # must be a registered EffectDef
    payload: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    applied_at_epoch: float
    expires_at_epoch: float | None = None  # None = until explicitly removed
