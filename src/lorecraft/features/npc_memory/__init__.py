"""NPC memory feature: per-(player, NPC) memory keys backing the `npc_remembers`
dialogue/quest conditions and the `remember` dialogue side effect.

Self-contained Tier 2 package (tier split, step 8): the conditions/side effect
(`conditions.py`), model (`models.py`), and repo (`repo.py`) live here; the
manifest registers them via config instead of a side-effect import in main.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.npc_memory.conditions import register as _register_npc_memory

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_npc_memory()


manifest = FeatureManifest(key="npc_memory", name="NPC Memory", register_fn=_wire)

register_feature(manifest)
