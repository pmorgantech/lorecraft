"""NPC feature: dialogue trees, dialogue conditions/side effects, and NPC
movement scheduling.

Self-contained Tier 2 package (tier split, step 8): the dialogue service
(`dialogue.py`), condition predicates (`dialogue_conditions.py`), side-effect
handlers (`side_effects.py`, which reach into inventory/quests), the NPC
scheduler (`scheduler.py`), and the dialogue tree table (`models.py`) + repo
(`repo.py`). Kept out of `engine/` because the side effects depend on Tier 2
features; a future refinement could lift the pure dialogue-tree traversal into
the engine behind a Tier 1 side-effect registry. Passive manifest — the
`NpcScheduler` is wired from `main.py`; conditions/side effects register on
import via their consumers.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="npc", name="NPC Dialogue & Behaviour")

register_feature(manifest)
