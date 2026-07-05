"""Items feature: item modifier compilation (`effects.py`) and item-behaviour
rules (`rules.py`, e.g. bound-item enforcement).

Self-contained Tier 2 package (tier split, step 8). Passive manifest —
`register_item_rules` needs the live `RuleEngine`, so it is called from
`main.py`; `compile_item_modifiers` is imported directly by the features that
resolve item modifiers (e.g. equipment).
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="items", name="Item Effects & Rules")

register_feature(manifest)
