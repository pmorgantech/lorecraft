"""Traits feature: the trait modifier/condition sources plus the shipped
standard boon/bane trait defs and the innate (background/earned) trait source.

Self-contained Tier 2 package (tier split, step 8): the trait sources live in
`sources.py` and the shipped standard boon/bane defs in `standard.py`; the
manifest wires both via config instead of side-effect imports in main.py. The
trait *registry* itself (`lorecraft.engine.game.traits`) remains a Tier 1
primitive — only the sources and standard content are feature-gated here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.traits.standard import register as _register_standard_traits
from lorecraft.features.traits.sources import register as _register_traits

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_traits()
    _register_standard_traits()


manifest = FeatureManifest(key="traits", name="Traits", register_fn=_wire)

register_feature(manifest)
