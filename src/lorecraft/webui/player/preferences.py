"""Per-account presentation preferences (Sprint 32.2).

The engine stores an opaque ``Player.preferences`` JSON blob; this module is the
single place that gives it meaning — the schema, the defaults, validation, and
the template context the render layer reads. Keeping the interpretation here (in
the web host) rather than in the Tier 1 model keeps display concerns out of the
engine: a headless run never needs to know what "feed verbosity" is.

Design contract: the render layer resolves preferences in exactly one place
(``resolve_preferences``) and passes ``PlayerPreferences.to_context()`` into the
base template, so every panel sees a consistent, fully-defaulted view. An empty
or partial stored blob always resolves to valid defaults — a new or legacy
account never renders broken.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from lorecraft.types import JsonObject

# Allowed values for the enum-like preferences. Anything outside these falls
# back to the default, so a hand-edited or stale blob can never inject an
# invalid class name / format string into a template.
# Colour + typography themes (Sprint 58.1). Each maps to a `theme-<name>` body
# class and a CSS-variable token set in static/css/custom.css. "terminal" is the
# default and reproduces today's zinc/emerald look, so an account that never
# picks a theme renders exactly as before.
THEMES = ("terminal", "parchment", "slate", "immersive")
# Panel-arrangement layouts (Sprint 58.5), a *second, independent* axis from
# theme. Each maps to a `layout-<name>` body class. "standard" is the default
# and reproduces today's three-column grid, so an account that never picks a
# layout renders exactly as before.
LAYOUTS = ("standard", "ledger", "dock", "immersive")
DISPLAY_DENSITIES = ("comfortable", "compact")
FEED_VERBOSITIES = ("verbose", "normal", "terse")
TIMESTAMP_FORMATS = ("relative", "clock24", "clock12", "none")
# Accessibility (Sprint 32.3): real font scaling and a high-contrast theme.
FONT_SCALES = ("normal", "large", "xlarge")
# Wishlist quick-win (Sprint 33.2): how many feed entries to load on the game
# screen. A page-length preference that feeds into this same blob.
FEED_PAGE_LENGTHS = (20, 40, 80)

# Panels the player may hide. Kept here (not derived from the WebHost registry)
# so an unknown/removed panel name in a stored blob degrades gracefully.
TOGGLEABLE_PANELS = ("minimap", "inventory", "players_online", "quest_tracker")


@dataclass(frozen=True)
class PlayerPreferences:
    """Fully-resolved, always-valid presentation preferences for one account."""

    # Colour + typography theme (Sprint 58.1). Default reproduces today's look.
    theme: str = "terminal"
    # Panel arrangement (Sprint 58.5), independent of theme. Default = today.
    layout: str = "standard"
    display_density: str = "comfortable"
    feed_verbosity: str = "normal"
    timestamp_format: str = "relative"
    reduced_motion: bool = False
    high_contrast: bool = False
    font_scale: str = "normal"
    feed_page_length: int = 40
    # Chat/feed split (Sprint 45): route chat messages to their own pane
    # instead of the narrative feed. Off = today's single feed.
    separate_chat: bool = False
    # Per-channel subscriptions (Sprint 52.5, generalizing 45.3's mute_chat):
    # channel id -> on/off for *muteable* P2ALL topic channels. A channel
    # absent from the map uses its Channel.default_subscribed; the server
    # drops unsubscribed recipients at broadcast time (engine reads this key
    # from the raw blob — keep the key name in sync with
    # engine/game/broadcast.py's _subscribed).
    channel_subscriptions: dict[str, bool] = field(default_factory=dict)
    # Panel id -> visible. Absent panels default to visible.
    hidden_panels: tuple[str, ...] = ()

    def to_context(self) -> dict[str, Any]:
        """Template context for the base shell (read in one place by the renderer)."""
        data = asdict(self)
        data["hidden_panels"] = list(self.hidden_panels)
        # Convenience booleans/classes so templates stay logic-light.
        data["theme_class"] = f"theme-{self.theme}"
        data["layout_class"] = f"layout-{self.layout}"
        data["is_compact"] = self.display_density == "compact"
        data["density_class"] = f"density-{self.display_density}"
        data["motion_class"] = "reduced-motion" if self.reduced_motion else ""
        data["contrast_class"] = "high-contrast" if self.high_contrast else ""
        data["font_scale_class"] = f"font-{self.font_scale}"
        # A single space-joined class string the <body> can drop straight in.
        data["body_classes"] = " ".join(
            c
            for c in (
                data["theme_class"],
                data["layout_class"],
                data["density_class"],
                data["motion_class"],
                data["contrast_class"],
                data["font_scale_class"],
            )
            if c
        )
        return {"prefs": data}

    def to_stored(self) -> JsonObject:
        """Serialize back to the opaque blob stored on ``Player.preferences``.

        Only non-default values are written, so the stored blob stays small and
        forward-compatible (a future default change is picked up automatically
        for accounts that never overrode it).
        """
        default = PlayerPreferences()
        out: JsonObject = {}
        if self.theme != default.theme:
            out["theme"] = self.theme
        if self.layout != default.layout:
            out["layout"] = self.layout
        if self.display_density != default.display_density:
            out["display_density"] = self.display_density
        if self.feed_verbosity != default.feed_verbosity:
            out["feed_verbosity"] = self.feed_verbosity
        if self.timestamp_format != default.timestamp_format:
            out["timestamp_format"] = self.timestamp_format
        if self.reduced_motion != default.reduced_motion:
            out["reduced_motion"] = self.reduced_motion
        if self.high_contrast != default.high_contrast:
            out["high_contrast"] = self.high_contrast
        if self.font_scale != default.font_scale:
            out["font_scale"] = self.font_scale
        if self.feed_page_length != default.feed_page_length:
            out["feed_page_length"] = self.feed_page_length
        if self.separate_chat != default.separate_chat:
            out["separate_chat"] = self.separate_chat
        if self.channel_subscriptions:
            out["channel_subscriptions"] = dict(self.channel_subscriptions)
        if self.hidden_panels:
            out["hidden_panels"] = list(self.hidden_panels)
        return out


def _clean_enum(value: Any, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def _clean_int(value: Any, allowed: tuple[int, ...], default: int) -> int:
    # Accept ints or numeric strings (form values arrive as strings), but only
    # from the allowed set — anything else falls back to the default.
    try:
        candidate = int(value)
    except (TypeError, ValueError):
        return default
    return candidate if candidate in allowed else default


def resolve_preferences(raw: JsonObject | None) -> PlayerPreferences:
    """Turn a stored (possibly empty/partial/invalid) blob into valid preferences.

    This is the single entry point the render layer uses. Unknown keys are
    ignored; invalid values fall back to their default; hidden-panel names not in
    ``TOGGLEABLE_PANELS`` are dropped. The result is always renderable.
    """
    raw = raw or {}
    hidden_raw = raw.get("hidden_panels", [])
    hidden = (
        tuple(p for p in hidden_raw if isinstance(p, str) and p in TOGGLEABLE_PANELS)
        if isinstance(hidden_raw, list)
        else ()
    )
    subscriptions_raw = raw.get("channel_subscriptions", {})
    subscriptions = (
        {
            key: value
            for key, value in subscriptions_raw.items()
            if isinstance(key, str) and isinstance(value, bool)
        }
        if isinstance(subscriptions_raw, dict)
        else {}
    )
    return PlayerPreferences(
        theme=_clean_enum(raw.get("theme"), THEMES, "terminal"),
        layout=_clean_enum(raw.get("layout"), LAYOUTS, "standard"),
        display_density=_clean_enum(
            raw.get("display_density"), DISPLAY_DENSITIES, "comfortable"
        ),
        feed_verbosity=_clean_enum(
            raw.get("feed_verbosity"), FEED_VERBOSITIES, "normal"
        ),
        timestamp_format=_clean_enum(
            raw.get("timestamp_format"), TIMESTAMP_FORMATS, "relative"
        ),
        reduced_motion=bool(raw.get("reduced_motion", False)),
        high_contrast=bool(raw.get("high_contrast", False)),
        font_scale=_clean_enum(raw.get("font_scale"), FONT_SCALES, "normal"),
        feed_page_length=_clean_int(raw.get("feed_page_length"), FEED_PAGE_LENGTHS, 40),
        separate_chat=bool(raw.get("separate_chat", False)),
        channel_subscriptions=subscriptions,
        hidden_panels=hidden,
    )


def apply_updates(
    current: PlayerPreferences, updates: Mapping[str, Any]
) -> PlayerPreferences:
    """Return a new PlayerPreferences with ``updates`` applied over ``current``.

    Only known fields are honoured, and each value is re-validated through
    ``resolve_preferences`` so an update can never persist an invalid value.
    Accepts loosely-typed values (e.g. straight from form parsing); anything
    invalid falls back to the default. Used by the settings-update route.
    """
    known = {f.name for f in fields(PlayerPreferences)}
    merged: dict[str, Any] = dict(current.to_stored())
    for key, value in updates.items():
        if key in known:
            merged[key] = value
    return resolve_preferences(merged)
