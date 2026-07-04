"""The reputation feature is the first migrated to the manifest system
(tier split, step 4): it must be auto-discovered, enabled by default, and
genuinely disableable via the enabled-features config."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from lorecraft.features.loader import (
    discover_features,
    load_features,
    resolve_enabled_features,
)

if TYPE_CHECKING:
    from lorecraft.state import AppState


def test_reputation_is_discovered() -> None:
    discovered = discover_features()
    assert "reputation" in discovered
    manifest = discovered["reputation"]
    assert manifest.name
    assert manifest.register_fn is not None
    assert manifest.dependencies == ()


def test_reputation_enabled_by_default() -> None:
    discovered = discover_features()
    enabled = resolve_enabled_features(None, discovered.keys())
    assert "reputation" in enabled
    loaded = load_features(enabled, discovered)
    assert "reputation" in loaded


def test_reputation_can_be_disabled() -> None:
    discovered = discover_features()
    # Explicitly enable nothing: reputation must not be loaded.
    loaded = load_features(resolve_enabled_features([], discovered.keys()), discovered)
    assert "reputation" not in loaded


def test_reputation_register_fn_runs() -> None:
    discovered = discover_features()
    register_fn = discovered["reputation"].register_fn
    assert register_fn is not None
    # Idempotent + side-effect-only; should not raise. AppState is unused by
    # reputation (it registers on global singletons).
    register_fn(cast("AppState", object()))
