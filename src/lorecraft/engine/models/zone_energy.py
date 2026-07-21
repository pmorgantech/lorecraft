"""Persistent evolving zone energy state (roadmap_world.md gap #1, Tier 1).

Two dedicated tables — deliberately *not* an extension of ``Meter``:

- ``ZoneEnergyState`` is the live, ticked value: one row per ``(zone, channel)``
  drifting bidirectionally toward a baseline (deplete down, recover up), unlike a
  meter's monotone regen-to-max.
- ``ZoneEnergyChannelConfig`` is the live-tunable dial (baseline/max/rate) keyed on
  ``channel`` alone — one config per energy type, applied to every zone.

Tier 1 knows *how* to store and drift per-``(zone, channel)`` values at a
DB-configured rate; it knows nothing of which channels exist ("lumenroot" etc.) —
those identities are DB-seeded strings supplied by a Tier 2 feature, never a Python
constant in ``engine/``.
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class ZoneEnergyState(SQLModel, table=True):
    """The live, ticked energy value for one ``(zone, channel)`` pair.

    Composite primary key on ``(zone, channel)``: there are two independent
    writers (the ``TIME_ADVANCED`` tick sweep and a future admin endpoint), so the
    one-row-per-pair invariant is enforced at the DB level, not by app-level
    discipline alone (unlike ``Meter``, which has a single write path through
    ``MeterService``). The composite PK also serves as the lookup index for all
    read patterns (point lookup, zone-prefix scan, full-table tick sweep), so no
    additional indexes are needed.

    Rows are created lazily by ``ZoneEnergyService.get()`` from the channel's
    registered ``ZoneEnergyChannelConfig`` baseline — there is no row until the
    ``(zone, channel)`` pair is first touched (mirrors ``Meter``'s lazy creation).
    """

    zone: str = Field(primary_key=True)  # from Room.zone (open set)
    channel: str = Field(primary_key=True)  # energy type, DB-seeded (open set)
    intensity: float
    # Epoch of the last drift-sweep update; None until first ticked.
    updated_epoch: float | None = None


class ZoneEnergyChannelConfig(SQLModel, table=True):
    """Live-tunable per-channel dial: baseline, ceiling, and drift rate.

    Keyed on ``channel`` alone (one config per energy type, applied to all zones) —
    the per-``(zone, channel)`` override table is a clean additive extension left
    for later. This table is the live-tunable surface (WorldClock pattern): an admin
    can retune ``baseline``/``max_intensity``/``regen_per_tick`` with no reseed.

    ``regen_per_tick`` is symmetric: state above ``baseline`` decays toward it,
    state below regenerates toward it, by at most this much per tick.
    """

    channel: str = Field(primary_key=True)
    baseline: float
    max_intensity: float
    regen_per_tick: float
