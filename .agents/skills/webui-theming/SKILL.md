---
name: webui-theming
description: Create or modify Lorecraft player-webui theming — Layouts (panel arrangement + typography) and Color schemes (colours only), the CSS custom-property token architecture in custom.css, per-mode template shells (game_dock/game_ereader/game_immersive/game_classic.html), preferences.py, and the settings/top-bar pickers. Use when asked to add a layout, add a color scheme, retint a scheme, restyle a panel, fix minimap/compass rendering, or make the UI match a docs/lorecraft-export/ reference mockup.
---

# Lorecraft webui theming

Everything here concerns `src/lorecraft/webui/player/` — the **player** web client
(Jinja2 + HTMX + Alpine.js + Tailwind Play CDN). The admin console is a separate,
unthemed SPA and is out of scope.

## The mental model: Theme = Layout × Color scheme

Two **independent** axes, deliberately decoupled (2026-07-09 axis split, Sprint 62):

- **Layout** — panel arrangement **and** typography (font faces, sizes, line-height,
  measure, letter-spacing). Picking a layout reflows the page.
- **Color scheme** — colours **only**. Picking a scheme repaints instantly, never reflows
  text. Default `auto` means "use this layout's tuned scheme."

A **Theme** (the term used in `docs/guides/user_guide.md`) is the resolved pair. Never add
typography rules to a scheme block, and never add colour literals to a layout block —
that's the one rule this whole architecture exists to enforce.

```
LAYOUTS = ("standard", "e-reader", "dock", "immersive", "classic")
THEMES  = ("auto", "terminal", "parchment", "slate", "immersive", "mono-green", "mono-amber")
```
(`src/lorecraft/webui/player/preferences.py`)

| Layout | Default scheme | Shell template | Chronicle-only? |
|---|---|---|---|
| `standard` | `terminal` | `game.html` (the `{% else %}` branch — no separate partial) | no |
| `e-reader` | `parchment` | `partials/game_ereader.html` | no |
| `dock` | `slate` | `partials/game_dock.html` | no |
| `immersive` | `immersive` | `partials/game_immersive.html` | **yes** |
| `classic` | `mono-green` | `partials/game_classic.html` | **yes** |

`mono-green`/`mono-amber` (renamed from `classic`/`classic-amber`, Sprint 59) are
phosphor-CRT overrides usable under **any** layout, not tied to one. Legacy stored
values `"classic"`/`"classic-amber"` alias transparently via `THEME_ALIASES` — don't
break old accounts when touching this.

## Where each axis actually lives

**1. `preferences.py`** — the single source of truth for valid values and defaults.
- `LAYOUTS`, `THEMES`, `THEME_ALIASES`, `MODE_DEFAULT_THEME` (layout → its tuned scheme),
  `MINIMAP_STYLES = ("graph", "compass")`.
- `PlayerPreferences` (frozen dataclass) + `resolve_preferences(raw_json)` (the only
  place a stored blob becomes valid data — unknown/invalid values silently fall back to
  defaults, so a hand-edited or legacy blob can never break rendering).
- `PlayerPreferences.to_context()` builds `body_classes`: a single space-joined string
  combining `theme-<resolved>`, `layout-<x>`, `minimap-<style>`, `density-<x>`,
  `reduced-motion`, `high-contrast`, `font-<scale>`. This is what `base.html` drops onto
  `<body class="... {{ prefs.body_classes }}">`. If you add a new preference that needs a
  body class, wire it here — nowhere else computes this string.
- `apply_updates(current, updates)` — merges partial updates (e.g. from a form) back
  through `resolve_preferences`, so an update can never persist an invalid value.

**2. `static/css/custom.css`** (~870 lines) — the token architecture. Two clearly
separated sections, each with a banner comment:
- **`:root`** (top of file) — default `--lc-*` tokens (the `terminal` scheme's colours)
  plus `--lc-font-body`/`--lc-font-head` (the `standard` layout's fonts, so pages with no
  layout class — lobby, login — still render sensibly).
- **"Selectable colour schemes" section** — one `body.theme-<name> { --lc-* : ... }`
  block per scheme, colours only (`--lc-bg`, `--lc-panel`, `--lc-accent`,
  `--lc-accent-strong`, `--lc-text`, `--lc-text-muted`, `--lc-highlight`, `--lc-npc`).
  Preceded by a **"raw-literal → token remap"** layer: templates still use plain
  Tailwind utility classes (`bg-zinc-900`, `text-emerald-400`, `border-zinc-700`,
  `text-amber-400`) in a lot of places, so `body .bg-zinc-900 { background-color:
  var(--lc-panel); }` etc. reroutes those raw literals through the active scheme's
  tokens at `(0,1,1)` specificity — no `!important` needed, beats the bare utility's
  `(0,1,0)`. **When writing new markup prefer the semantic Tailwind names** (`bg-panel`,
  `text-accent`, `border-border`, see the Tailwind config below) so it's scheme-correct
  without relying on the remap net; the net exists mainly for older markup and
  Tailwind-utility muscle memory.
- **Per-layout typography blocks**, one `body.layout-<name> { ... }` per layout, each
  setting `--lc-font-body`/`--lc-font-head`, `--lc-measure` (prose width), base
  `font-size`/`line-height`, and `#feed` / `.room-card__name` overrides. This is also
  where a layout's *bespoke shell CSS* lives (e.g. `.dock-card`, `.dock-shade__head`,
  `.immersive-rail`, `.immersive-map`, `.ereader-rail`, `.mm-compass`/`.mm-graph`).
  Shared cross-layout rules (tabular-nums, measure-capping) sit just above these blocks.
- Root-level, **not** per-scheme: `--lc-hp`, `--lc-copper` (Stats-pane accents — read
  fine on every scheme, deliberately not themed per-scheme).

**3. `templates/base.html`** — the Tailwind config (`tailwind.config.extend.colors`)
maps semantic names to the CSS vars: `panel`/`panel-light`/`accent`/`accent-dark`/
`text`/`text-muted`/`feed-bg`/`border`/`npc` → `var(--lc-*)`. Also owns:
- `window.LC_MODE_DEFAULT_THEME` — the server's `MODE_DEFAULT_THEME` dict, injected as
  JSON (`{{ MODE_DEFAULT_THEME_JSON | safe }}`, set via `templates.env.globals` in
  `frontend.py`) so client-side code never hand-copies the mapping — see "Single-sourcing
  MODE_DEFAULT_THEME to the client" below.
- `window.lcApplyTheme(theme)` — instant client-side scheme swap (no reload) for the
  top-bar quick picker; resolves `'auto'` by reading `window.LC_MODE_DEFAULT_THEME`.
- `window.lcToggleMinimapStyle()` — flips `minimap-graph`/`minimap-compass` on `<body>`
  and persists via `POST /settings/appearance`.
- `<body class="bg-zinc-950 text-zinc-200 font-mono {{ prefs.body_classes }}">` — the one
  place all resolved preference classes land.

**4. `templates/game.html`** — dispatches on `prefs.layout`:
```jinja
{% if prefs.layout == 'classic' %}{% include "partials/game_classic.html" %}
{% elif prefs.layout == 'e-reader' %}{% include "partials/game_ereader.html" %}
{% elif prefs.layout == 'dock' %}{% include "partials/game_dock.html" %}
{% elif prefs.layout == 'immersive' %}{% include "partials/game_immersive.html" %}
{% else %}{# Standard: the default 3-column grid lives inline here, no partial #}
```
Every shell — bespoke or the inline Standard grid — **must** preserve the shared ids/
targets that JS (`static/js/app.js`), HTMX responses, and OOB swaps key on:
`#main-content`, `#feed` (chronicle log), `#chat-feed` (only when `prefs.separate_chat`
or the layout has its own always-on chat pane, e.g. Classic), `#command-input`,
`#minimap`, `#inventory`, `#quest-tracker`. Renaming or dropping one of these breaks
live command responses and WS pushes silently (no error — the swap target just isn't
found), so grep every existing shell for an id before renaming it.

**5. `partials/minimap.html` is bare content only** (Sprint 60) — no border, no card
chrome, no title. Every layout's own template supplies the surrounding card/border/
title/buttons in its own idiom (Standard's card head, Dock's `.dock-card__head`,
E-reader's kicker text, Immersive's `.immersive-map__head`, Classic's plain
`── MINIMAP ──` text). If you wrap `{% include "partials/minimap.html" %}` in another
border, you've double-boxed it — this was a real bug fixed in Sprint 60,
`test_minimap_is_bare_content_no_double_box` guards it.

**6. `MUD_CHRONICLE_LAYOUTS = ("immersive", "classic")`**
(`webui/player/session.py`) — layouts with **no** dedicated room/inventory/players
panel. For these, `frontend.py` narrates room state as a structured `room_card` feed
message (`rendering.py`'s `room_card_message()` + `partials/feed_room_card.html`,
styled but borderless per user feedback) instead of relying on a side panel. The
`mud_layout` guard in `frontend.py`'s command handler gates this — it must only fire for
these two layouts; a past regression made it fire everywhere and ate all `look` output
outside these layouts (regression test:
`test_standard_look_narrates_in_feed_without_room_card`). If you add a 3rd
chronicle-only layout, add it to this tuple, not a new parallel check.

**7. `docs/lorecraft-export/`** — **gitignored, local-only** reference mockups (5
folders: `standard/`, `e-reader/`, `dock/`, `immersive/`, `classic/`, each a
self-contained framework-free HTML+CSS+htmx export with its own README). This is the
design source of truth for fidelity work. **It may not exist in a given checkout** —
that's expected, not a bug; don't try to "restore" it. If present, its README documents
shared swap-target ids (`#chronicle`, `#location`, `#minimap`, `#inventory`, `#party`,
`#quests`, `#chat`) that *inspired* but don't exactly match this codebase's actual ids
(listed in point 4 above) — cross-check against the real templates, not just the export
READMEs, before wiring anything.

## Single-sourcing MODE_DEFAULT_THEME to the client

`MODE_DEFAULT_THEME` (layout → its tuned default scheme) needs to be resolvable
**client-side without a round-trip**, for two instant-preview use cases: the top-bar
quick picker (`lcApplyTheme()`) and the settings page's live preview before Save
(`applyPreview()`). Until Sprint 67 this meant the dict was hand-copied into two JS
object literals — a real, previously-shipped bug class, since nothing enforced the
copies staying in sync (editing only `preferences.py` left both previews silently
flashing the *old* default scheme for a layout).

**Fixed (Sprint 67): single-sourced, not hand-copied.** `frontend.py` sets
`templates.env.globals["MODE_DEFAULT_THEME_JSON"] = json.dumps(MODE_DEFAULT_THEME)`
right after constructing its `Jinja2Templates` instance (this is the templates instance
that renders every `base.html`-extending page — `rendering.py` has its own separate
`Jinja2Templates` instance, but it's only ever used for
`get_template("partials/feed_items.html").render(...)`, never a full page, so it doesn't
need the global too). `base.html`'s `<head>` script then does:
```jinja
window.LC_MODE_DEFAULT_THEME = {{ MODE_DEFAULT_THEME_JSON | safe }};
```
(`| safe` is required — FastAPI's `Jinja2Templates` autoescapes by default, so without it
the JSON's `"` characters get HTML-entity-escaped into `&#34;` and the JS breaks.
`MODE_DEFAULT_THEME`'s values are a hardcoded server constant, never user input, so
`| safe` here is not an XSS risk.) Both `lcApplyTheme()` (`base.html`) and
`applyPreview()` (`settings.html`) now read `window.LC_MODE_DEFAULT_THEME` instead of
carrying their own literal — **there is exactly one place to edit** (`preferences.py`)
when adding a layout or changing a default scheme; both client-side previews pick it up
automatically on next page load.

## Persistence & picker flow

Three UI entry points, two backing routes:
- **Settings page** (`GET /settings`, `templates/settings.html`) — full form, `POST
  /settings` (`frontend.py`'s settings route) replaces the *entire* stored blob via
  `apply_updates` + redirect. Has live preview (`applyPreview()`, Alpine) before Save.
- **Top-bar quick pickers** (`partials/topbar_appearance.html`, gated by the
  `APPEARANCE_TOPBAR` flag in `frontend.py`) and the **minimap ⇄ toggle button** in every
  layout's map-pane head — both hit `POST /settings/appearance`
  (`frontend.py::update_appearance`), a **merge-one-field** endpoint: only the field(s)
  actually posted are updated, everything else in the stored blob is untouched. Returns
  `204`; the caller updates the DOM itself (`lcApplyTheme`/`lcToggleMinimapStyle` for an
  instant scheme/minimap swap, or `window.location.reload()` for a layout change, since
  layout changes need a full structural reflow).
- To remove the top-bar experiment entirely: delete `APPEARANCE_TOPBAR`, its
  `{% include %}` in `base.html`, and `partials/topbar_appearance.html` — the settings
  page's own pickers are independent and unaffected (documented in that partial's own
  comment header).

## How to add a new color scheme

1. Add the name to `THEMES` in `preferences.py`. If replacing/renaming an old one, add
   an entry to `THEME_ALIASES` so existing stored accounts don't silently revert to a
   default.
2. Add a `body.theme-<name> { --lc-bg: ...; --lc-panel: ...; --lc-accent: ...;
   --lc-accent-strong: ...; --lc-text: ...; --lc-text-muted: ...; --lc-highlight: ...;
   --lc-npc: ...; }` block in `custom.css`'s "Selectable colour schemes" section. Do
   **not** set any `--lc-font-*` or size/spacing property here — that's a layout concern.
3. If some layout should default to it, add a `MODE_DEFAULT_THEME` entry in
   `preferences.py` — that's the only file to touch; both client-side previews read it
   through the injected `window.LC_MODE_DEFAULT_THEME` global automatically (see
   "Single-sourcing MODE_DEFAULT_THEME to the client" above).
4. Add the option to any select loop that iterates `theme_options`/`THEMES` — this is
   automatic (`settings.html` and `topbar_appearance.html` both `{% for opt in
   theme_options %}`), so no template change needed there.
5. Update the scheme table in `docs/guides/user_guide.md`'s "Themes & Display" section.
6. Test: extend `tests/unit/test_player_preferences.py`'s `TestResolvePreferences`/
   `TestTheme` classes; if it's a rename, add an alias round-trip test like
   `test_legacy_theme_names_alias_to_renamed_schemes`.

## How to add a new layout

This is the bigger lift — a new arrangement usually means a new bespoke shell partial:

1. Add the name to `LAYOUTS` in `preferences.py` and a `MODE_DEFAULT_THEME` entry (its
   tuned default scheme) — that single dict is all you need to touch; the client-side
   previews read it via the injected `window.LC_MODE_DEFAULT_THEME` global (see
   "Single-sourcing MODE_DEFAULT_THEME to the client" above).
2. Decide: chronicle-only (no room/inventory/players panel, add to
   `MUD_CHRONICLE_LAYOUTS` in `session.py`) or panel-based (needs `#inventory`/
   `#quest-tracker`/room panel like Standard/Dock/E-reader)?
3. Create `templates/partials/game_<name>.html`. Reuse `partials/inventory.html`,
   `partials/quest_tracker.html`, `partials/minimap.html` (bare, wrap your own card
   chrome around it — see point 5 above), `partials/stats_panel.html` where applicable.
   Preserve every shared id from point 4 in "Where each axis lives" above.
4. Add the `{% elif prefs.layout == '<name>' %}` branch in `game.html`'s dispatch.
5. Add a `body.layout-<name> { --lc-font-body: ...; --lc-font-head: ...; --lc-measure:
   ...; font-size: ...; }` block (+ `#feed`, `.room-card__name` overrides, + any bespoke
   shell classes like `.dock-card`) in `custom.css`'s per-layout typography section.
   Colours must come only from `var(--lc-*)`/semantic Tailwind classes — never a literal
   hex — so every existing scheme (including future ones) repaints it correctly.
6. If it's chronicle-only, verify `frontend.py`'s `mud_layout` guard picks it up via the
   `MUD_CHRONICLE_LAYOUTS` tuple (no separate code path to add).
7. Add it to any `{% for opt in layout_options %}` loop — automatic, same as schemes.
8. Update `docs/guides/user_guide.md`'s layout table and `docs/project/roadmap.md` (a new layout is
   sprint-worthy; see the sprint-numbering convention at the bottom of `roadmap.md`).
9. Test + verify (see below).

## Testing & live verification

- **Unit**: `tests/unit/test_player_preferences.py` — pure `preferences.py` logic
  (resolution, defaults, aliasing, `to_context`/`to_stored` round-trips). Grouped by
  `class TestResolvePreferences`/`TestToContext`/`TestToStored`/`TestApplyUpdates`/
  `TestTheme`.
- **Integration/characterization**: `tests/integration/test_frontend_characterization.py`
  (large file) — full-page HTML assertions per layout, e.g.
  `test_immersive_layout_renders_full_bleed_shell`,
  `test_dock_layout_renders_card_shell`, `test_ereader_layout_renders_ledger_folio_rail`,
  `test_classic_layout_renders_mud_terminal`, `test_game_screen_applies_theme_body_class`,
  `test_game_screen_applies_layout_body_class`, `test_minimap_style_toggles_graph_vs_compass`,
  `test_minimap_is_bare_content_no_double_box`, `test_settings_renders_and_persists_theme`.
  When adding/changing a shell, add or update an assertion here that checks for the
  layout's signature markup (a distinctive class or the absence of a panel it doesn't
  have) — these tests are what catch a shared-id rename or a double-boxed panel.
- **Live browser verification** (required for anything visual — screenshots alone don't
  catch reflow/overlap bugs): boot the dev server per this repo's worktree convention
  (`MAIN=$(dirname "$(git rev-parse --git-common-dir)"); source "$MAIN/.venv/bin/activate"`,
  then run uvicorn with `LORECRAFT_DB_PATH`/`LORECRAFT_AUDIT_DB_PATH` — not
  `LORECRAFT_DATABASE_PATH`, a real footgun — pointed at a scratch sqlite file) and drive
  it with Playwright (Python sync API), checking each of the 5 layouts × a couple of
  schemes, both the sidebar minimap and the full-map modal, and at least one
  `MUD_CHRONICLE_LAYOUTS` `look` command to confirm the room card renders and isn't boxed.
- Run focused tests from the worktree with the standard `PYTHONPATH` recipe (see
  `AGENTS.md`'s "Running tests from a git worktree" section) — do not run bare `pytest`.

## Common pitfalls (all previously real bugs, now guarded by name where noted)

- Adding a colour literal (hex, `rgb()`, a raw Tailwind colour utility not covered by the
  remap layer) inside a `body.layout-*` block — leaks a fixed colour that won't repaint
  under other schemes. Layout blocks may only touch typography/spacing/measure/font vars.
- Adding a font-size/spacing rule inside a `body.theme-*` block — the inverse mistake;
  schemes are colours-only, so a size change there silently reflows text whenever someone
  switches scheme, defeating the whole point of the axis split.
- Wrapping `partials/minimap.html`'s include in another bordered container — it's bare
  content by design (point 5 above); the surrounding layout template owns the one box.
- Reintroducing a hand-copied JS literal of `MODE_DEFAULT_THEME` (e.g. "just inline it,
  it's faster") instead of reading `window.LC_MODE_DEFAULT_THEME` — this was a real bug
  (three out-of-sync copies) fixed in Sprint 67 by injecting the dict once via
  `templates.env.globals`; don't re-add a second source of truth.
- Renaming a shared DOM id (`#feed`, `#minimap`, `#inventory`, `#quest-tracker`,
  `#command-input`, `#main-content`) inside one shell without checking `static/js/app.js`
  and the HTMX `hx-target`/OOB swap markers elsewhere — breaks live updates silently
  (no console error, the swap target is just never found).
- Letting the `mud_layout`/`MUD_CHRONICLE_LAYOUTS` room-card-narration logic in
  `frontend.py` apply outside `("immersive", "classic")` — it previously ate all `look`
  output on every layout when this guard was missing; see
  `test_standard_look_narrates_in_feed_without_room_card`.
- Assuming `docs/lorecraft-export/` exists — it's gitignored/local-only; treat its
  absence as normal, and when it IS present, verify its documented ids against the real
  templates rather than trusting the export README verbatim (they've drifted before).
