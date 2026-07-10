"""Spawns feature: area population / respawn controllers (scripting engine A6).

Maintains per-area NPC populations from a template (`docs/scripting_engine_design.md` §3.4). The
service holds the live engine/rng, so it is constructed and bus-registered in ``main.py`` (gated
on this feature), like the other tick services.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="spawns", name="Area Spawn Controllers")

register_feature(manifest)
