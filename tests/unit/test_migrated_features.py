"""Features migrated to the manifest system (tier split, step 4+) must each be
auto-discovered, enabled by default, genuinely disableable, and have a
register_fn that runs without error. This list grows as more of main.py's old
side-effect imports move to manifests."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from lorecraft.features.loader import (
    discover_features,
    load_features,
    resolve_enabled_features,
)
from lorecraft.features.manifest import FeatureManifest

if TYPE_CHECKING:
    from lorecraft.state import AppState

# Feature keys expected to be live on the manifest path.
MIGRATED_KEYS = [
    "reputation",
    "economy",
    "bank",
    "npc_memory",
    "traits",
    "equipment",
    "fatigue",
    "item_components",
    "containers",
]


def _enabled_without(discovered: dict[str, FeatureManifest], key: str) -> list[str]:
    """Enabled set with `key` and everything that transitively depends on it
    removed — so the result is a valid (dependency-complete) enabled set that
    genuinely excludes `key`."""
    excluded = {key}
    changed = True
    while changed:
        changed = False
        for k, manifest in discovered.items():
            if k not in excluded and any(d in excluded for d in manifest.dependencies):
                excluded.add(k)
                changed = True
    return [k for k in discovered if k not in excluded]


@pytest.mark.parametrize("key", MIGRATED_KEYS)
def test_feature_is_discovered(key: str) -> None:
    discovered = discover_features()
    assert key in discovered, f"{key!r} feature package did not self-register"
    manifest = discovered[key]
    assert manifest.name
    assert manifest.register_fn is not None


def test_all_migrated_enabled_by_default() -> None:
    discovered = discover_features()
    enabled = resolve_enabled_features(None, discovered.keys())
    for key in MIGRATED_KEYS:
        assert key in enabled


@pytest.mark.parametrize("key", MIGRATED_KEYS)
def test_feature_can_be_disabled(key: str) -> None:
    discovered = discover_features()
    # Enable everything except `key` (and its dependents, to keep the set valid);
    # `key` must not be loaded.
    loaded = load_features(_enabled_without(discovered, key), discovered)
    assert key not in loaded


@pytest.mark.parametrize("key", MIGRATED_KEYS)
def test_register_fn_runs(key: str) -> None:
    discovered = discover_features()
    register_fn = discovered[key].register_fn
    assert register_fn is not None
    # Side-effect-only + idempotent; must not raise. Reputation/economy/bank
    # register on global singletons and ignore AppState.
    register_fn(cast("AppState", object()))
