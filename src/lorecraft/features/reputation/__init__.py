"""Reputation feature: standing-gated command/dialogue conditions and the
`adjust_reputation` side effect.

Self-contained Tier 2 feature package (tier split, step 8): its conditions,
service, model, and repo live under this package; the manifest wires it via
the config-driven load path instead of a side-effect import in main.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.reputation.conditions import register as _register_reputation

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
