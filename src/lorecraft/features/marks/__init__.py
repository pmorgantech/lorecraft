"""Marks feature: discovery-fed collectible badges with optional boons (Sprint 53).

Self-contained Tier 2 package built entirely on existing primitives (player
journal state, player flags, the event bus, the §3.5 modifier resolver) — no
new Tier 1 mechanism, no new table. `models.py` holds the YAML-authored mark
definitions + registry + content-lint; `service.py` evaluates criteria and
awards marks; `commands.py` adds a read-only `marks` verb.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="marks", name="Marks & Attunements")

register_feature(manifest)
