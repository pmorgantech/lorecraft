"""Tests for the feature manifest descriptor and its global registry
(tier split refactor, step 1). These cover only the additive descriptor +
catalogue; the loader/dependency-validation lives in test_feature_loader.py."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from lorecraft.features.manifest import (
    FEATURE_REGISTRY,
    FeatureManifest,
    clear_registry,
    get_feature,
    register_feature,
)

if TYPE_CHECKING:
    from lorecraft.state import AppState


@pytest.fixture(autouse=True)
def _clean_registry():
    """Give each test an empty global feature registry, then restore whatever
    was there. Restore matters because real feature packages (e.g. reputation)
    self-register on import; a bare clear would wipe them for sibling tests
    sharing this worker process."""
    saved = dict(FEATURE_REGISTRY)
    clear_registry()
    yield
    clear_registry()
    FEATURE_REGISTRY.update(saved)


def test_register_and_get_roundtrip() -> None:
    manifest = FeatureManifest(key="equipment", name="Equipment System")
    register_feature(manifest)

    assert get_feature("equipment") is manifest
    assert FEATURE_REGISTRY["equipment"] is manifest


def test_get_unknown_feature_returns_none() -> None:
    assert get_feature("does-not-exist") is None


def test_duplicate_key_raises() -> None:
    register_feature(FeatureManifest(key="fatigue", name="Fatigue"))
    with pytest.raises(ValueError, match="already registered"):
        register_feature(FeatureManifest(key="fatigue", name="Fatigue (dup)"))


def test_defaults_are_empty() -> None:
    manifest = FeatureManifest(key="skills", name="Skills")
    assert manifest.dependencies == ()
    assert manifest.register_fn is None
    assert manifest.presentation is None


def test_manifest_is_immutable() -> None:
    manifest = FeatureManifest(key="trading", name="Trading")
    with pytest.raises(Exception):
        manifest.key = "changed"  # type: ignore[misc]


def test_dependencies_and_presentation_are_carried() -> None:
    calls: list[str] = []

    def wire(_state: "AppState") -> None:
        calls.append("wired")

    manifest = FeatureManifest(
        key="equipment",
        name="Equipment System",
        dependencies=("inventory",),
        register_fn=wire,
        presentation="lorecraft.features.equipment.presentation",
    )
    register_feature(manifest)

    got = get_feature("equipment")
    assert got is not None
    assert got.dependencies == ("inventory",)
    assert got.presentation == "lorecraft.features.equipment.presentation"
    assert got.register_fn is not None
    got.register_fn(cast("AppState", object()))
    assert calls == ["wired"]


def test_clear_registry_empties_catalogue() -> None:
    register_feature(FeatureManifest(key="economy", name="Economy"))
    assert FEATURE_REGISTRY
    clear_registry()
    assert FEATURE_REGISTRY == {}
