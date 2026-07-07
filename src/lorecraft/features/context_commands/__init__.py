"""Context-attached commands feature: object-scoped verbs (Sprint 55).

Items and NPCs declare a `context_commands` map in world content; verbs
register into the flat `CommandRegistry` gated by the Sprint 55.1
`object_present`/`npc_present` conditions and fire the shared side-effect
registry. `models.py` holds the bindings/registry/loader/lint; `commands.py`
the dispatcher. Built entirely on existing primitives — no new Tier 1
mechanism, no new table beyond the `context_commands` JSON columns.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="context_commands", name="Context-attached commands")

register_feature(manifest)
