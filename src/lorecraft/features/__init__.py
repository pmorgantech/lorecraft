"""Tier 2 features: optional, self-contained gameplay modules.

Each subpackage here is one feature (equipment, fatigue, trading, ...). A
feature exports a :class:`FeatureManifest` describing itself and calls
:func:`register_feature` at import; the loader then wires only the enabled
subset onto the shared Tier 1 registries. See ``docs/tier_split_refactor.md``.

This package intentionally does no work at import time (no feature discovery
side effects) — importing ``lorecraft.features`` just makes the manifest
primitives available. Discovery/loading is an explicit call on the loader.
"""

from __future__ import annotations

from lorecraft.features.loader import (
    discover_features,
    load_features,
    resolve_enabled_features,
    wire_features,
)
from lorecraft.features.manifest import (
    FEATURE_REGISTRY,
    FeatureManifest,
    RegisterFn,
    get_feature,
    register_feature,
)

__all__ = [
    "FEATURE_REGISTRY",
    "FeatureManifest",
    "RegisterFn",
    "discover_features",
    "get_feature",
    "load_features",
    "register_feature",
    "resolve_enabled_features",
    "wire_features",
]
