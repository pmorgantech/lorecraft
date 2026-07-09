"""Unit tests for per-account presentation preferences (Sprint 32.2)."""

from __future__ import annotations

from lorecraft.webui.player.preferences import (
    LAYOUTS,
    MINIMAP_STYLES,
    THEMES,
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
        assert prefs.high_contrast is False
        assert prefs.font_scale == "normal"
        assert prefs.hidden_panels == ()

    def test_accessibility_fields_resolve(self) -> None:
        prefs = resolve_preferences({"high_contrast": True, "font_scale": "xlarge"})
        assert prefs.high_contrast is True
        assert prefs.font_scale == "xlarge"

    def test_invalid_font_scale_falls_back(self) -> None:
        assert resolve_preferences({"font_scale": "huge"}).font_scale == "normal"

    def test_feed_page_length_resolves_from_int_and_string(self) -> None:
        assert resolve_preferences({"feed_page_length": 80}).feed_page_length == 80
        # Form values arrive as strings.
        assert resolve_preferences({"feed_page_length": "20"}).feed_page_length == 20

    def test_feed_page_length_invalid_falls_back(self) -> None:
        # Not in the allowed set, or non-numeric -> default 40.
        assert resolve_preferences({"feed_page_length": 999}).feed_page_length == 40
        assert resolve_preferences({"feed_page_length": "lots"}).feed_page_length == 40
        assert resolve_preferences({}).feed_page_length == 40

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

    def test_body_classes_combines_only_active(self) -> None:
        # Default: theme + layout + minimap + density + font scale always present.
        default = PlayerPreferences().to_context()["prefs"]
        assert default["body_classes"] == (
            "theme-terminal layout-standard minimap-graph "
            "density-comfortable font-normal"
        )

        full = PlayerPreferences(
            theme="slate",
            layout="dock",
            minimap_style="compass",
            display_density="compact",
            reduced_motion=True,
            high_contrast=True,
            font_scale="large",
        ).to_context()["prefs"]
        assert full["body_classes"] == (
            "theme-slate layout-dock minimap-compass density-compact "
            "reduced-motion high-contrast font-large"
        )
        assert full["contrast_class"] == "high-contrast"
        assert full["font_scale_class"] == "font-large"


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
            high_contrast=True,
            font_scale="xlarge",
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


class TestTheme:
    """Colour + typography theme preference (Sprint 58.1)."""

    def test_defaults_to_terminal(self) -> None:
        assert PlayerPreferences().theme == "terminal"
        assert resolve_preferences({}).theme == "terminal"

    def test_all_named_themes_resolve(self) -> None:
        for name in THEMES:
            assert resolve_preferences({"theme": name}).theme == name

    def test_invalid_theme_falls_back_to_terminal(self) -> None:
        assert resolve_preferences({"theme": "neon"}).theme == "terminal"
        assert resolve_preferences({"theme": 123}).theme == "terminal"

    def test_default_theme_not_written_to_stored_blob(self) -> None:
        assert "theme" not in PlayerPreferences().to_stored()

    def test_non_default_theme_round_trips(self) -> None:
        prefs = resolve_preferences({"theme": "parchment"})
        assert prefs.to_stored() == {"theme": "parchment"}
        assert resolve_preferences(prefs.to_stored()) == prefs

    def test_theme_class_in_context(self) -> None:
        ctx = resolve_preferences({"theme": "immersive"}).to_context()["prefs"]
        assert ctx["theme_class"] == "theme-immersive"
        # The theme class leads the body-class string.
        assert ctx["body_classes"].split()[0] == "theme-immersive"

    def test_apply_updates_switches_theme(self) -> None:
        updated = apply_updates(PlayerPreferences(), {"theme": "slate"})
        assert updated.theme == "slate"
        # An invalid value falls back rather than persisting.
        assert apply_updates(updated, {"theme": "bogus"}).theme == "terminal"


class TestLayout:
    """Panel-arrangement layout preference (Sprint 58.5), independent of theme."""

    def test_defaults_to_standard(self) -> None:
        assert PlayerPreferences().layout == "standard"
        assert resolve_preferences({}).layout == "standard"

    def test_all_named_layouts_resolve(self) -> None:
        for name in LAYOUTS:
            assert resolve_preferences({"layout": name}).layout == name

    def test_invalid_layout_falls_back_to_standard(self) -> None:
        assert resolve_preferences({"layout": "spaceship"}).layout == "standard"
        assert resolve_preferences({"layout": 7}).layout == "standard"

    def test_default_layout_not_written_to_stored_blob(self) -> None:
        assert "layout" not in PlayerPreferences().to_stored()

    def test_non_default_layout_round_trips(self) -> None:
        prefs = resolve_preferences({"layout": "ledger"})
        assert prefs.to_stored() == {"layout": "ledger"}
        assert resolve_preferences(prefs.to_stored()) == prefs

    def test_layout_class_in_context(self) -> None:
        ctx = resolve_preferences({"layout": "dock"}).to_context()["prefs"]
        assert ctx["layout_class"] == "layout-dock"

    def test_theme_and_layout_are_independent(self) -> None:
        prefs = resolve_preferences({"theme": "parchment", "layout": "immersive"})
        assert prefs.theme == "parchment"
        assert prefs.layout == "immersive"
        assert prefs.to_stored() == {"theme": "parchment", "layout": "immersive"}


class TestMinimapStyle:
    """Minimap rendering style (Sprint 59): graph node-map vs compass exit-star."""

    def test_defaults_to_graph(self) -> None:
        assert PlayerPreferences().minimap_style == "graph"
        assert resolve_preferences({}).minimap_style == "graph"

    def test_all_named_styles_resolve(self) -> None:
        for name in MINIMAP_STYLES:
            assert resolve_preferences({"minimap_style": name}).minimap_style == name

    def test_invalid_style_falls_back(self) -> None:
        assert (
            resolve_preferences({"minimap_style": "hologram"}).minimap_style == "graph"
        )

    def test_default_not_written_and_round_trips(self) -> None:
        assert "minimap_style" not in PlayerPreferences().to_stored()
        prefs = resolve_preferences({"minimap_style": "compass"})
        assert prefs.to_stored() == {"minimap_style": "compass"}
        assert resolve_preferences(prefs.to_stored()) == prefs

    def test_class_in_context(self) -> None:
        ctx = resolve_preferences({"minimap_style": "compass"}).to_context()["prefs"]
        assert ctx["minimap_class"] == "minimap-compass"


class TestSeparateChat:
    """Chat/feed split preference (Sprint 45)."""

    def test_defaults_off(self) -> None:
        assert PlayerPreferences().separate_chat is False
        assert resolve_preferences({}).separate_chat is False

    def test_resolves_and_round_trips(self) -> None:
        prefs = resolve_preferences({"separate_chat": True})
        assert prefs.separate_chat is True
        assert prefs.to_stored() == {"separate_chat": True}
        assert resolve_preferences(prefs.to_stored()) == prefs

    def test_default_not_written_to_stored_blob(self) -> None:
        assert "separate_chat" not in PlayerPreferences().to_stored()

    def test_apply_updates_toggles(self) -> None:
        on = apply_updates(PlayerPreferences(), {"separate_chat": True})
        assert on.separate_chat is True
        off = apply_updates(on, {"separate_chat": False})
        assert off.separate_chat is False

    def test_present_in_template_context(self) -> None:
        context = resolve_preferences({"separate_chat": True}).to_context()
        assert context["prefs"]["separate_chat"] is True


class TestChannelSubscriptions:
    """Per-channel subscriptions (Sprint 52.5, generalizing 45.3's mute_chat)."""

    def test_defaults_empty(self) -> None:
        assert PlayerPreferences().channel_subscriptions == {}
        assert resolve_preferences({}).channel_subscriptions == {}

    def test_resolves_and_round_trips(self) -> None:
        prefs = resolve_preferences({"channel_subscriptions": {"newbie": False}})
        assert prefs.channel_subscriptions == {"newbie": False}
        assert prefs.to_stored() == {"channel_subscriptions": {"newbie": False}}
        assert resolve_preferences(prefs.to_stored()) == prefs

    def test_empty_map_not_written_to_stored_blob(self) -> None:
        assert "channel_subscriptions" not in PlayerPreferences().to_stored()

    def test_invalid_entries_dropped(self) -> None:
        prefs = resolve_preferences(
            {
                "channel_subscriptions": {
                    "newbie": False,
                    "auction": "yes",  # non-bool value dropped
                    3: True,  # non-str key dropped
                }
            }
        )
        assert prefs.channel_subscriptions == {"newbie": False}

    def test_non_dict_blob_falls_back_to_empty(self) -> None:
        assert (
            resolve_preferences(
                {"channel_subscriptions": ["newbie"]}
            ).channel_subscriptions
            == {}
        )

    def test_apply_updates_replaces_the_map(self) -> None:
        # The settings form posts the full map (unchecked = False), so an
        # update replaces rather than merges per-key.
        current = resolve_preferences({"channel_subscriptions": {"newbie": False}})
        updated = apply_updates(current, {"channel_subscriptions": {"newbie": True}})
        assert updated.channel_subscriptions == {"newbie": True}

    def test_legacy_mute_chat_key_is_ignored(self) -> None:
        # Pre-52.5 blobs may still carry mute_chat; unknown keys are dropped
        # (the blanket say-mute is superseded by channel subscriptions).
        prefs = resolve_preferences({"mute_chat": True, "separate_chat": True})
        assert prefs.separate_chat is True
        assert "mute_chat" not in prefs.to_stored()
