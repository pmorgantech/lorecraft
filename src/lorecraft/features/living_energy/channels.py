"""The three living-energy channel identities (Tier 2 policy).

These strings are the *policy* half of gap #1's Tier 1/Tier 2 split: the engine
(``engine/services/zone_energy.py``) knows how to store and drift a
per-``(zone, channel)`` value at a DB-configured rate but is deliberately blind
to *which* channels exist — those identities are owned here, in the
``living_energy`` feature, never as a constant in ``engine/`` (that would be the
exact policy leak the tier split prevents).

The baseline/max/regen numbers for each channel are authored as *data* in
``world_content/world.yaml`` (``zone_energy_channels:``) and seeded into
``ZoneEnergyChannelConfig`` rows by the world loader, then live-tunable via the
admin surface — not hardcoded here. This tuple only fixes the *set* of channels,
which the imbalance policy iterates over.
"""

from __future__ import annotations

# Flavour (see docs/worldbuilding/lore_ideas.md, "Living Energy & Harvesting"):
#   lumenroot  — steady, reliable, long-duration
#   dreamveil  — delicate, temperamental
#   emberthorn — high-output, volatile
CHANNELS: tuple[str, ...] = ("lumenroot", "dreamveil", "emberthorn")
