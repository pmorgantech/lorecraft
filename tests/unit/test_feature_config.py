"""Tests for feature enablement resolution + wiring (tier split, step 3):
`resolve_enabled_features` precedence (explicit > env > all) and
`wire_features` calling each loaded feature's register_fn in order."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from lorecraft.features.loader import resolve_enabled_features, wire_features
from lorecraft.features.manifest import FeatureManifest

if TYPE_CHECKING:
    from lorecraft.state import AppState


def test_explicit_list_wins_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LORECRAFT_FEATURES", "from_env")
    assert resolve_enabled_features(["a", "b"], ["a", "b", "c"]) == ["a", "b"]


def test_explicit_empty_list_means_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # An explicit empty list is a real choice ("no features"), not a fallthrough.
    monkeypatch.setenv("LORECRAFT_FEATURES", "from_env")
    assert resolve_enabled_features([], ["a", "b"]) == []


def test_env_used_when_no_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LORECRAFT_FEATURES", " equipment , fatigue ,")
    # Whitespace trimmed; empty entries dropped.
    assert resolve_enabled_features(None, ["equipment", "fatigue", "trading"]) == [
        "equipment",
        "fatigue",
    ]


def test_default_is_all_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LORECRAFT_FEATURES", raising=False)
    assert resolve_enabled_features(None, ["a", "b", "c"]) == ["a", "b", "c"]


def test_blank_env_falls_through_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LORECRAFT_FEATURES", "   ")
    assert resolve_enabled_features(None, ["a", "b"]) == ["a", "b"]


def test_wire_features_calls_register_fns_in_order() -> None:
    calls: list[str] = []

    def make(key: str) -> FeatureManifest:
        return FeatureManifest(
            key=key, name=key, register_fn=lambda _state: calls.append(key)
        )

    # Insertion order mimics load_features' dependency ordering.
    loaded = {k: make(k) for k in ("inventory", "equipment")}
    wire_features(cast("AppState", object()), loaded)
    assert calls == ["inventory", "equipment"]


def test_wire_features_skips_passive_features() -> None:
    calls: list[str] = []
    loaded = {
        "passive": FeatureManifest(key="passive", name="Passive"),
        "active": FeatureManifest(
            key="active", name="Active", register_fn=lambda _s: calls.append("active")
        ),
    }
    wire_features(cast("AppState", object()), loaded)
    assert calls == ["active"]
