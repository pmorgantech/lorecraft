"""Reputation feature: standing-gated command/dialogue conditions and the
`adjust_reputation` side effect.

This is the first feature migrated to the manifest system (tier split, step 4).
The registration logic still lives in `lorecraft.game.reputation_conditions`
(it moves under this package in a later step); here we wrap it in a manifest so
it loads via the config-driven path instead of a side-effect import in main.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.game.reputation_conditions import register as _register_reputation

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    # Reputation registers on global singleton registries, so it needs nothing
    # from AppState — the parameter is part of the uniform register_fn contract.
    _register_reputation()


manifest = FeatureManifest(
    key="reputation",
    name="Reputation & Standing",
    register_fn=_wire,
)

register_feature(manifest)
