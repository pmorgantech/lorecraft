"""Tests for feature discovery + loading (tier split refactor, step 2):
dependency validation and topological ordering in `load_features`, and that
`discover_features` runs harmlessly over the (currently feature-less) package."""

from __future__ import annotations

import pytest

from lorecraft.features.loader import discover_features, load_features
from lorecraft.features.manifest import FeatureManifest


def _catalogue(*manifests: FeatureManifest) -> dict[str, FeatureManifest]:
    return {m.key: m for m in manifests}


def test_load_orders_dependencies_before_dependents() -> None:
    catalogue = _catalogue(
        FeatureManifest(key="equipment", name="Equipment", dependencies=("inventory",)),
        FeatureManifest(key="inventory", name="Inventory"),
    )
    # Enabled in the "wrong" order on purpose; loader must reorder.
    ordered = load_features(["equipment", "inventory"], catalogue)
    assert list(ordered) == ["inventory", "equipment"]


def test_transitive_dependencies_ordered() -> None:
    catalogue = _catalogue(
        FeatureManifest(key="a", name="A", dependencies=("b",)),
        FeatureManifest(key="b", name="B", dependencies=("c",)),
        FeatureManifest(key="c", name="C"),
    )
    ordered = load_features(["a", "b", "c"], catalogue)
    keys = list(ordered)
    assert keys.index("c") < keys.index("b") < keys.index("a")


def test_unknown_feature_raises() -> None:
    catalogue = _catalogue(FeatureManifest(key="known", name="Known"))
    with pytest.raises(ValueError, match="not registered"):
        load_features(["known", "mystery"], catalogue)


def test_missing_dependency_raises() -> None:
    catalogue = _catalogue(
        FeatureManifest(key="equipment", name="Equipment", dependencies=("inventory",)),
        FeatureManifest(key="inventory", name="Inventory"),
    )
    with pytest.raises(ValueError, match="requires 'inventory'"):
        load_features(["equipment"], catalogue)


def test_dependency_cycle_raises() -> None:
    catalogue = _catalogue(
        FeatureManifest(key="a", name="A", dependencies=("b",)),
        FeatureManifest(key="b", name="B", dependencies=("a",)),
    )
    with pytest.raises(ValueError, match="cycle"):
        load_features(["a", "b"], catalogue)


def test_empty_enabled_set_is_ok() -> None:
    assert load_features([], _catalogue()) == {}


def test_ordering_is_deterministic_for_independent_features() -> None:
    catalogue = _catalogue(
        FeatureManifest(key="x", name="X"),
        FeatureManifest(key="y", name="Y"),
        FeatureManifest(key="z", name="Z"),
    )
    ordered = load_features(["z", "x", "y"], catalogue)
    # Independent features preserve the enabled-list order.
    assert list(ordered) == ["z", "x", "y"]


def test_discover_features_runs_and_is_idempotent() -> None:
    # No feature subpackages exist yet, so discovery just returns the current
    # catalogue without raising; calling twice is stable.
    first = discover_features()
    second = discover_features()
    assert isinstance(first, dict)
    assert first == second
