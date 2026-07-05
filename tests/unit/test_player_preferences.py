"""Unit tests for per-account presentation preferences (Sprint 32.2)."""

from __future__ import annotations

from lorecraft.webui.player.preferences import (
    PlayerPreferences,
    apply_updates,
    resolve_preferences,
)


class TestResolvePreferences:
    def test_empty_blob_gives_all_defaults(self) -> None:
        prefs = resolve_preferences({})
        assert prefs == PlayerPreferences()
        assert prefs.display_density == "comfortable"
        assert prefs.feed_verbosity == "normal"
        assert prefs.timestamp_format == "relative"
        assert prefs.reduced_motion is False
        assert prefs.hidden_panels == ()

    def test_none_blob_gives_defaults(self) -> None:
        assert resolve_preferences(None) == PlayerPreferences()

    def test_partial_blob_fills_missing_with_defaults(self) -> None:
        prefs = resolve_preferences({"display_density": "compact"})
        assert prefs.display_density == "compact"
        assert prefs.feed_verbosity == "normal"  # default

    def test_invalid_enum_value_falls_back_to_default(self) -> None:
        prefs = resolve_preferences({"feed_verbosity": "bogus"})
        assert prefs.feed_verbosity == "normal"

    def test_invalid_types_fall_back(self) -> None:
        prefs = resolve_preferences({"display_density": 123, "timestamp_format": None})
        assert prefs.display_density == "comfortable"
        assert prefs.timestamp_format == "relative"

    def test_reduced_motion_coerced_to_bool(self) -> None:
        assert resolve_preferences({"reduced_motion": True}).reduced_motion is True
        assert resolve_preferences({"reduced_motion": 1}).reduced_motion is True
        assert resolve_preferences({"reduced_motion": 0}).reduced_motion is False

    def test_hidden_panels_filtered_to_known(self) -> None:
        prefs = resolve_preferences(
            {"hidden_panels": ["minimap", "not_a_panel", "inventory"]}
        )
        assert prefs.hidden_panels == ("minimap", "inventory")

    def test_hidden_panels_non_list_ignored(self) -> None:
        assert resolve_preferences({"hidden_panels": "minimap"}).hidden_panels == ()

    def test_unknown_keys_ignored(self) -> None:
        prefs = resolve_preferences({"totally_unknown": "x", "reduced_motion": True})
        assert prefs.reduced_motion is True


class TestToContext:
    def test_context_has_prefs_key_and_derived_classes(self) -> None:
        ctx = PlayerPreferences(
            display_density="compact", reduced_motion=True
        ).to_context()
        assert "prefs" in ctx
        prefs = ctx["prefs"]
        assert prefs["is_compact"] is True
        assert prefs["density_class"] == "density-compact"
        assert prefs["motion_class"] == "reduced-motion"
        assert prefs["hidden_panels"] == []

    def test_default_context_motion_class_empty(self) -> None:
        prefs = PlayerPreferences().to_context()["prefs"]
        assert prefs["motion_class"] == ""
        assert prefs["is_compact"] is False


class TestToStored:
    def test_defaults_serialize_to_empty_blob(self) -> None:
        assert PlayerPreferences().to_stored() == {}

    def test_only_non_default_values_stored(self) -> None:
        stored = PlayerPreferences(
            display_density="compact", reduced_motion=True
        ).to_stored()
        assert stored == {"display_density": "compact", "reduced_motion": True}

    def test_roundtrip_through_resolve(self) -> None:
        original = PlayerPreferences(
            display_density="compact",
            feed_verbosity="terse",
            timestamp_format="clock24",
            reduced_motion=True,
            hidden_panels=("minimap",),
        )
        assert resolve_preferences(original.to_stored()) == original


class TestApplyUpdates:
    def test_apply_single_update(self) -> None:
        updated = apply_updates(PlayerPreferences(), {"display_density": "compact"})
        assert updated.display_density == "compact"
        assert updated.feed_verbosity == "normal"

    def test_apply_invalid_update_falls_back(self) -> None:
        updated = apply_updates(PlayerPreferences(), {"feed_verbosity": "nope"})
        assert updated.feed_verbosity == "normal"

    def test_apply_preserves_existing_non_default(self) -> None:
        current = PlayerPreferences(reduced_motion=True)
        updated = apply_updates(current, {"display_density": "compact"})
        assert updated.reduced_motion is True
        assert updated.display_density == "compact"

    def test_apply_ignores_unknown_field(self) -> None:
        updated = apply_updates(PlayerPreferences(), {"garbage": "x"})
        assert updated == PlayerPreferences()
