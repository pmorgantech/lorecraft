"""Traits feature: the trait modifier/condition sources plus the shipped
standard boon/bane trait defs and the innate (background/earned) trait source.

Migrated to the manifest system (tier split, step 5). Registration still lives
in `lorecraft.game.traits` and `lorecraft.game.standard_traits`; the manifest
wraps both so they load via config instead of side-effect imports in main.py.
The trait *registry* itself remains a Tier 1 primitive — only the sources and
standard content are feature-gated here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.game.standard_traits import register as _register_standard_traits
from lorecraft.game.traits import register as _register_traits

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_traits()
    _register_standard_traits()


manifest = FeatureManifest(key="traits", name="Traits", register_fn=_wire)

register_feature(manifest)
