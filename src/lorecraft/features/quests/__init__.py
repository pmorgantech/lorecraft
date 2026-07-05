"""Quests feature: quest definitions/progress, quest-condition predicates, and
the quest timer.

Self-contained Tier 2 package (tier split, step 8): service (`service.py`),
timer (`timer.py`), tables (`models.py`), repo (`repo.py`), and the
quest/dialogue condition predicates + their registry (`conditions.py`, whose
standard predicates register on import). Passive manifest — the quest service
and timer are wired from the container/`main.py`.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="quests", name="Quests")

register_feature(manifest)
