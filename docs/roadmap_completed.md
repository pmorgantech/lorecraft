# Roadmap — completed sprint history

> **Historical record (last extended 2026-07-07, through v0.46.0).** The active, forward-looking
> roadmap is [`roadmap.md`](roadmap.md) — a concise list of *remaining* work. This file preserves
> the full detail of **completed** sprints (first archived 2026-07-05 so the active roadmap stays
> readable). Per-version detail also lives in [`../CHANGELOG.md`](../CHANGELOG.md).
>
> Covers **every completed sprint: 1–34** (foundation hardening, Tier 1 engine-core primitives, the
> Tier 2 pillar feature band, tier-split follow-ons) **+ the Foundation exit criteria, 35–37** (the
> performance & scaling band), **and 39–55** (timed room effects; admin-console + analytics work;
> the wishlist-promoted content/UX band — chat/feed split → global channels, marks, celestial
> cycles, context-attached commands). Layout note: recent completions are grouped near the top
> (below), the deep 1–34 archive follows under a second `# Lorecraft — Roadmap` header.
>
> **Not here:** 37.1 (scheduler-commit batching) + 38 (concurrency gate) were deferred to
> [`wishlist.md`](wishlist.md), not completed; Combat/PvP (former 61–64) likewise set aside there.
> Do not plan against this file; append newly-completed sprints here as they close.

---

## Sprints 56–69 — observability, client themes/layouts, multi-level map, escort quests, scripting world-building (v0.47.0–v0.75.0, archived 2026-07-10)

> Moved here from the active roadmap on 2026-07-10 once Sprint 69 closed. Full task
> detail preserved below; per-version notes in [`../CHANGELOG.md`](../CHANGELOG.md).

## Sprint 56 — Structured output-type tagging

**Goal:** tag every engine-emitted message with a semantic type (`room_event`, `chat`, `tell`,
`combat`, `quest`, `warning`, `hint`, `system`) at the point of emission, instead of the flat
untyped strings `GameContext.say()` produces today. **Why now:** the direct-response channel
(`ctx.messages`) carries zero type information at all; the room-broadcast channel
(`engine/game/broadcast.py`) only has an ad hoc binary `message_type: "chat" | "room_event"`. This
is a single call-site change today (`ctx.say`) — leaving it untyped through the trading/quest band
was fine, but combat (when it returns) and further quest/social output will multiply call sites
fast, and retrofitting a type onto every existing `ctx.say(...)` later is far more expensive than
adding one now. No new commands or player-visible behavior — this is invisible infrastructure that
unlocks output filtering/routing (mute-by-type prefs, accessible/screen-reader-friendly rendering,
future non-web clients) without further engine work.

| # | Task | Status |
|---|------|--------|
| 56.1 | Define the starter taxonomy (`room_event`, `chat`, `tell`, `combat`, `quest`, `warning`, `hint`, `system`) in one small module. Keep it short and resist one-off types per feature — same "small, named taxonomy" discipline as the `EventBus` event names. | [x] `engine/game/message_types.py` — `MessageType(str, Enum)`. |
| 56.2 | Extend `GameContext.say()` to accept an optional message type (default `"system"`); thread it through `ctx.messages` (currently `list[str]` → a small `(type, text)` pair or frozen dataclass) without changing every call site's required arguments. | [x] `Message(str)` subclass carrying `.type` (`message_types.py`) — `ctx.messages` stays behaviorally `list[str]` (equality/`.startswith`/`in`/JSON serialization all degrade to plain text), so none of the ~280 existing `ctx.say(text)` call sites or their test assertions needed to change. |
| 56.3 | Reuse the same taxonomy on the room-broadcast payload (`broadcast.py`'s `feed_append` messages) in place of the current `"chat"`/`"room_event"` binary, so the direct-response and broadcast channels share one vocabulary. | [x] `broadcast.py`, plus the two duplicate disconnect-narration broadcasts in `main.py`/`frontend.py`, now source `"message_type"` from `MessageType.*.value` instead of separate literal strings. |
| 56.4 | `webui/player/frontend.py`: apply a CSS class per type when rendering the feed (`.msg-combat`, `.msg-warning`, …) — the first real consumer, and the seed for a future per-type mute/filter preference (no new engine work needed later). | [x] Feed messages carry a new `msg_type` field; `feed_item.html`/`feed_items.html` add an additive `msg-<type>` class (new CSS only for types actually in use — `quest`/`warning`/`tell`/`combat`/`hint` — so untouched call sites' current look is unchanged). |
| 56.5 | Sweep existing `ctx.say(...)` call sites in `engine/` and `features/`; assign a type where the intent is clear from context, leave genuinely ambiguous ones on the `"system"` default rather than guessing. | [x] Full sweep of all 28 files with `ctx.say()` calls (283 call sites total): 171 retyped (162 `WARNING`, 7 `QUEST`, 1 `TELL`, 1 `HINT` — first use of `HINT`, decided together for `exploration/service.py`'s hidden-passage discovery message), 112 deliberately left on `SYSTEM`. `WARNING` = precondition failures, disambiguation prompts, exception-message passthroughs, and the core parser/dispatch errors in `engine/game/engine.py` (all 8 of that file). `QUEST` = quest/hunt/mark progression and reward narration. Left on `SYSTEM`: successful-action confirmations ("You take the sword.") across every file; whole read-only report/display commands (`character/service.py` traits/skills/reputation/score, `exploration/journal.py`, `marks/commands.py`, `hunts/commands.py` listings — none of their calls, including empty-states, are warnings); `fatigue/service.py` (sampled, no clean fit); `context_commands/commands.py`'s `binding.say` (arbitrary world-content-authored text, no single type could fit); `follow/service.py`'s `_show_status` (a status check, not an error, despite sharing exact text with `unfollow`'s genuine failure case — caught and reverted after an initial blanket `replace_all` mistake). `follow/service.py`'s `_notify()` helper gained its own `msg_type` passthrough param so `_break_follow`'s two involuntary-disconnect notifications could be tagged `WARNING` without affecting its other (voluntary-action) callers. |

## Sprint 57 — Request tracing & crash reports

**Goal:** extend Sprint 13's structured logging (correlation/transaction IDs) and command latency
percentiles with two admin-facing debugging tools that don't exist today: a per-command trace of
what actually happened (conditions checked, events fired, DB commits) and a saved, browsable record
of unhandled exceptions. Today an admin diagnosing a bad command has only raw log grep by
`transaction_id` — no structured "what ran" view and nothing captured for an exception beyond
whatever hits stdout.

| # | Task | Status |
|---|------|--------|
| 57.1 | Trace buffer: within `bind_transaction_context()`'s scope, collect an ordered list of trace spans (condition evaluations, event dispatches, DB commits — reusing `time_operation`'s existing timing) keyed by `transaction_id`. In-memory ring buffer over the last N commands — not persisted, matching the "measure, don't over-build" caution already applied to the deferred concurrency work. | [x] `observability.py`'s `TraceSpan`/`record_span`/`get_trace` + a 200-entry `OrderedDict` ring buffer; `time_operation()` records automatically, `EventBus.emit()` and the command-handler dispatch call `record_span()` directly since they already compute their own timing. |
| 57.2 | `GET /admin/trace/<transaction_id>` — returns the captured spans for one recent command (404 once it's aged out of the ring buffer). | [x] `webui/admin/routers/observability.py`. |
| 57.3 | Crash capture: a handler at both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`) that, on an unhandled exception, persists a `CrashReport` row (transaction_id, correlation_id, player_id, command text, stack trace, timestamp) to the audit DB and returns a friendly in-game error instead of a raw disconnect/500. | [x] New `CrashReport` model (`engine/models/audit.py`) + `engine/services/crash_reports.record_crash()` (rolls back both sessions first so a crash report never smuggles in unrelated pending writes); both entry points wrap their command-processing body in try/except. |
| 57.4 | `GET /admin/crashes` (list) + `GET /admin/crashes/<id>` (detail) endpoints and a Crash Reports tab in the admin console, reusing the Audit tab's table/detail pattern. | [x] Endpoints in `observability.py`; admin console gets a list-table + detail-panel layout (mirrors the World tab's room-list/room-editor split) wired into `TAB_LOADERS`. |
| 57.5 | Document both features (usage, endpoints, retention) in [`observability.md`](observability.md) and cross-link from the admin guide's Troubleshooting section. | [x] |

---

## Sprint 58 — Selectable client themes & layouts

**Goal:** turn the four client design directions in [`Lorecraft Client.dc.html`](Lorecraft%20Client.dc.html)
— **terminal** (1a), **parchment** (1b), **slate** (1c), **immersive** (1d) — into player-selectable
**themes** *and* **layouts**, persisted through the same `PlayerPreferences` blob as every other
display setting. **Why now:** the foundation gate is green and the display-preference seam
(Sprints 32.2/32.3 — density, font scale, high-contrast, hidden panels) already exists; both are a
natural extension of it, not new engine surface.

**Two orthogonal axes, sequenced.** *Phase 1 (58.1–58.4)* delivers **theme** = palette + typography
on today's three-column layout — small, low-risk, and independently shippable. *Phase 2 (58.5–58.8)*
adds **layout** as a *second, independent preference* (`standard` / `ledger` / `dock` / `immersive`),
so a player can pair any palette with any arrangement — matching the mockups' own "combine 1c layout
with 1d's chronicle" framing. Phase 1 lands first and stands alone; Phase 2 builds on it.

### Phase 1 — Themes (palette + typography)

| # | Task | Status |
|---|------|--------|
| 58.1 | **Theme token layer + preference.** Add a semantic CSS-variable token layer (`--lc-bg`, `--lc-panel`, `--lc-accent`, `--lc-text`, `--lc-text-muted`, `--lc-border`, `--lc-font-body`, `--lc-font-head`, …) to `static/css/custom.css`, defaulting to today's zinc/emerald terminal values (**zero visual change**). Point `base.html`'s Tailwind config semantic colours (`panel`/`accent`/`text`/`text-muted`/`feed-bg`/`border`) at those vars. Add a `theme` enum to `PlayerPreferences` (`THEMES = ("terminal","parchment","slate","immersive")`, default `terminal`), emit `theme-<name>` on `<body>` via `body_classes`, and add the theme `<select>` to the settings form. Unit tests for the pref round-trip/validation + the body-class output. | [x] `theme` field on `PlayerPreferences` (default `terminal`, leads `body_classes`); Tailwind semantic colours resolve to `--lc-*`; settings selector; `TestTheme` unit + `test_game_screen_applies_theme_body_class`/`test_settings_renders_and_persists_theme` integration tests. |
| 58.2 | **Slate & Immersive (dark) themes.** Define the `slate` (1c: `#0a0d15`/`#43c7d8`, Plex Sans) and `immersive` (1d: `#0a0807`/`#e8a13c`, Plex Sans) token sets + the override layer that remaps the raw `zinc-*`/`emerald-*` literals still in the partials (same mechanism as the existing high-contrast block) so both repaint the whole screen. Load the required web fonts. | [x] Shared **`body:not(.theme-terminal)` remap** (one block, specificity 0,2,x — no `!important`) routes every raw literal through the tokens; each theme is just a token block. IBM Plex Sans/Mono + Spectral loaded in `base.html`. |
| 58.3 | **Parchment (light) theme.** The one light theme (1b: `#e3d7bd`/`#8c3b2e`, Spectral serif body + Plex Mono commands) — inverts background/text, needs its own override set and a WCAG-AA contrast pass. | [x] `body.theme-parchment` token block + serif body / mono commands + softened error-red + lifted feed-hover for the light ground. |
| 58.4 | **Theme docs & regression tests.** Document the theme picker in [`user_guide.md`](user_guide.md); changelog; a settings test that a chosen theme persists and re-renders selected; a render assertion that `<body>` carries the right `theme-*` class. | [x] Regression tests landed with 58.1; user-guide "Themes" section + CHANGELOG. |

### Phase 2 — Layouts (panel arrangement)

| # | Task | Status |
|---|------|--------|
| 58.5 | **Layout preference + collapsible-panel mechanism.** Add a `layout` enum to `PlayerPreferences` (`LAYOUTS = ("standard","ledger","dock","immersive")`, default `standard`), emit `layout-<name>` on `<body>` (independent of `theme-*`), and build the shared building block the other three need: an Alpine-driven **collapsible panel rail** (icon-collapsed ↔ expanded), CSS-only where possible. `standard` reproduces today's three-column grid (**zero visual change**). Settings gets a layout `<select>`; unit tests mirror 58.1. | [x] `layout` field (default `standard`) as a second body-class axis; settings picker; `TestLayout` unit + `test_game_screen_applies_layout_body_class` integration tests. Collapsible rail deferred to 58.8, the only layout that needs it. |
| 58.6 | **Ledger layout (1b) + shared right-rail Inventory/Quests.** Left column = Location + Map; Chronicle runs wide in the centre; secondary panels collapse into a slim right rail. | [x] Narrow left (Location + Map) + **wide full-width chronicle** (the 72ch cap that starved it was removed after review). **Inventory now moves into the right rail for *every* layout** (per review), paired with Quests as a **mutually-exclusive** pane (both stay in the DOM so `#inventory`/`#quest-tracker` OOB updates fire while hidden). Two UI patterns to compare: **standard = toggle button** (one titlebar, a button flips Inventory⇄Quests); **dock + ledger = window-shade accordion** (stacked titlebars). `test_inventory_and_quests_share_right_rail`. |
| 58.7 | **Dock layout (1c).** A visible control bar (theme · density · layout · panel toggles surfaced from `/settings` inline) above card-style panels, plus the rarity-coloured **icon-grid inventory** variant. Drag-to-reorder panels is a **stretch** (behind a flag) — the reviewable core is the toolbar + card treatment + icon-grid. | [x] Superseded by the **bespoke Dock rebuild in 59.7** — card shell, rarity **icon-grid** Pack, and Party/Quests are all delivered there; the base-nav Mode/Palette pickers act as the control bar. (Drag-to-reorder remains the deferred stretch.) |
| 58.8 | **Immersive layout (1d) + docs.** Near-full-bleed Chronicle with a soft vignette; everything else collapses to a slim icon rail (58.5) that expands on demand; floating minimap + floating command bar. Document both axes in [`user_guide.md`](user_guide.md); changelog; render tests asserting the `layout-*` body class and that hidden-by-default rail panels are still reachable. | [x] **Reworked to a focused 2-column view** (per review): a slim left column with **Chat on top + Minimap below** and a dominant Chronicle taking the rest; Room/Inventory/Players/Quests dropped; larger type + soft vignette. Chat routes into the left pane (its `#chat-feed` is what the client keys on); the centre pane is suppressed there to keep the id unique. `test_immersive_layout_puts_chat_in_left_column`. |
| 58.9 | **Live theme/layout preview.** The Settings **Theme**/**Layout** dropdowns preview immediately (Alpine swaps the `theme-*`/`layout-*` body classes on change); **Save** persists via the existing POST, **Cancel** returns to `/game` and reloads the last-saved prefs (natural revert). | [x] `settings.html` Alpine `applyPreview()`. |
| 58.10 | **Settings Save→game + [Save][Cancel].** Per review: **Save** uses Post/Redirect/Get to return straight to `/game` (the new look applies immediately, no second click); the button row is just **[Save] [Cancel]** — the top back-to-game link, the saved-banner, and the hint text are removed. | [x] `POST /settings` → 303 `/game`; `settings.html` trimmed; three POST tests updated for the redirect. |
| 58.11 | **Top-bar quick appearance pickers (experimental, flag-gated).** Small **Theme** + **Layout** dropdowns in the nav (left of the player name/Settings) that take effect immediately — Theme swaps the body class client-side, Layout persists + reloads — via a dedicated `POST /settings/appearance` that updates *only* the posted field(s), merged over current prefs. Gated by `APPEARANCE_TOPBAR` + a self-contained partial so it can be peeled back after testing. The settings page keeps its own pickers. | [x] `partials/topbar_appearance.html`, `lcApplyTheme()`, `/settings/appearance` route, `APPEARANCE_TOPBAR` flag; render + partial-update tests. |
| 58.12 | **Own chat routes into the chat pane too, styled as a "sent by me" bubble.** Per review: the actor's own `say`/`tell`/topic-channel echo only ever showed in the main chronicle, never in a chat pane (a latent gap — only *other* players' chat, via WS, ever reached `#chat-feed`). Now routed there via an HTMX OOB append whenever a chat pane exists (`separate_chat`, or always in immersive), and styled distinctly: the colour bar moves to the **right** and the line **right-justifies**, mirroring everyone else's left-barred/left-aligned lines — scoped to `#chat-feed` only, so the plain narrative feed is unaffected. | [x] `route_chat_oob` computed in `handle_command()`; `feed_items.html` marks `type=='chat'` items `mine` + `hx-swap-oob="beforeend:#chat-feed"` (safe unconditionally — a rendered chat item is *always* the actor's own echo; others' chat only ever arrives client-side via WS); `#chat-feed .msg.chat.mine` CSS. `test_immersive_own_chat_routes_to_chat_pane`. |
| 58.13 | **Immersive chronicle reads like an old-school MUD; the right column is gone outright.** Per review: (a) drop the per-line colour gutter and timestamp in immersive's `#feed` — plain scrolling text, telnet-MUD style; (b) narrate the **full room** (name/description/NPCs/items/exits) as chronicle text when entering a new room — movement never narrated any of this before (that was the panel's job, and immersive has no panel); `look` already narrates name/description/exits via the engine's existing output, so only the **players-here** line is added there; (c) the right column (Here Now / Inventory / Quests) is dropped from the DOM entirely for immersive, not just hidden — including its mobile tab. | [x] `mud_room_block()`/`mud_players_here_line()` (`rendering.py`) reuse the same `room_panel`/`players_here()` data the panels render, so they can't drift; wired into both `/game`'s initial load and `handle_command()` (keyed off `room_changed` vs. the `look`/`l` verb, tagged `msg_type=room_event` — no ordinary `ctx.say()` produces that tag, so it's an unambiguous test signal). `game.html`'s right sidebar + its mobile tab are now `{% if prefs.layout != 'immersive' %}`-gated. Tests: `test_immersive_movement_appends_old_school_mud_room_block`, `test_immersive_look_appends_players_here_line_only`, extended `test_immersive_layout_puts_chat_in_left_column`, new `test_standard_layout_keeps_players_column_and_tab`. |

---

## Sprint 59 — Classic mode (old-MUD CRT terminal)

**Goal:** integrate the new **"Classic" mode** (design source: the `Lorecraft Client (standalone).html`
canvas + the `lorecraft-export/classic/` reference, kept local — see the design-export note below) —
a pure old-MUD phosphor-CRT terminal. Added
**alongside** the existing themes/layouts (per review — nothing removed), so it slots onto the same
two orthogonal axes: a **theme** (CRT palette) and a **layout** (MUD arrangement). Reuses the
chronicle-narration machinery from Sprint 58.13 (immersive), which classic also needs.

| # | Task | Status |
|---|------|--------|
| 59.1 | **Classic CRT themes.** Add `classic` (phosphor green) + `classic-amber` to `THEMES`: token overrides from the `lorecraft-export/classic` palette, a text-shadow **phosphor glow**, and a fixed **scanline overlay** (`::after`, `z-index:40` under the modals; suppressed under `reduced-motion`). Caught by the shared `:not(.theme-terminal)` remap like every other theme. | [x] `body.theme-classic{,-amber}` token blocks + glow + CRT overlay in `custom.css`. |
| 59.2 | **Classic layout.** Add `classic` to `LAYOUTS`: a purpose-built shell (`partials/game_classic.html`) — chronicle (`#feed`) + vitals prompt + command input on the left, a ~420px **minimap-over-chat** column on the right (chat has its own input that rewrites `command`→`say …` via `htmx:configRequest`). Chronicle-only, so it drops room/inventory/players/quests and reuses the MUD room-narration (`MUD_CHRONICLE_LAYOUTS = ("immersive","classic")`) + own-chat→pane routing (`route_chat_oob`). `game.html` branches `#main-content`, the mobile tab bar, and the full-width command bar on `layout == 'classic'`. | [x] `game_classic.html`; `game.html` three-way branch; shared `#feed`/`#chat-feed`/`#minimap`/`#command-input` ids preserved so WS/OOB/hotkeys keep working. |
| 59.3 | **Vitals prompt + polish + tests + docs.** A real **vitals line** in the prompt (`session.vitals_snapshot`: fatigue meter as stamina + carried coins via the ledger — Lorecraft has no HP/MP/MV, so surface real meters; OOB-refreshed each command). Nicer picker labels (`classic-amber` → "Classic Amber"). Render + command tests; user guide + changelog. | [x] `partials/vitals.html`; `#vitals` OOB refresh in `handle_command`; `test_classic_layout_renders_mud_terminal`, `test_classic_layout_command_refreshes_vitals_and_routes_chat`; existing parametrized `TestTheme`/`TestLayout` auto-cover the new enum values. |
| 59.6 | **Couple layout + palette into tuned "Modes" (+ optional override).** Per the 2026-07-09 UI direction: the **layout is the primary "Mode"**, and each mode has a tuned default palette (`MODE_DEFAULT_THEME`: standard→terminal, e-reader→parchment, dock→slate, immersive→immersive, classic→classic). The theme pref gains an **`auto`** default (the new zero-config default) that resolves to the mode's palette, and otherwise acts as an **optional override**. Settings/top-bar relabelled (Mode · Palette override); live preview + `lcApplyTheme` resolve `auto` client-side from the current mode. Coupled but reversible — the two prefs still exist underneath. | [x] `resolved_theme`/`MODE_DEFAULT_THEME` in `preferences.py`; `theme` default `auto`; settings + topbar relabel; `TestTheme` auto-resolution tests. **Next:** bespoke **immersive** (slim icon rail + floating minimap/command) rebuild to match `lorecraft-export/` — **dock done in 59.7**. |
| 59.7 | **Bespoke Dock rebuild (closer emulation round 2).** Replace the CSS-only "card treatment over the grid" (58.7 first cut) with a purpose-built shell (`partials/game_dock.html`) matching `lorecraft-export/dock`: three columns of floating **`.dock-card`** panels (gradient bg, rounded, drop shadow, a drag **grip**, uppercase titles) — LEFT Location + Minimap, CENTRE Chronicle (`#feed` + a gradient **Send** button), RIGHT Party + a **Pack** card with the **rarity icon-grid** inventory (4-wide tiles, dashed empty slots, click-to-examine) and a **Quests footer** (replacing the window-shade accordion). `inventory.html` renders both grid + list; CSS reveals the grid only under `body.layout-dock` so `#inventory` stays a single OOB target. Slate palette gains a violet `--lc-accent-2` for the Send gradient. | [x] `game_dock.html`; `game.html` `elif dock` branch + toggle-pane collapsed to standard-only; `.dock-card`/`.dock-send`/`.grip`/`.dock-quests-foot`/`.inv-grid`/`.inv-slot` CSS (old `body.layout-dock .game-col` rules removed); `test_dock_layout_renders_card_shell`, updated right-rail test. **Next:** bespoke **immersive** rebuild (59.8). |
| 59.8 | **Bespoke Immersive rebuild (closer emulation round 3).** Replace the 2-column immersive (chat-in-left-column) with a purpose-built cinematic shell (`partials/game_immersive.html`) matching `lorecraft-export/immersive`: a slim left **icon rail** (glyph buttons that run look/inventory/journal/score into `#feed`), a **full-bleed chronicle**, and a **floating minimap card** + **floating command bar** (amber glass) over it. Chat now **folds into the chronicle** (no separate pane) — `route_chat_oob` drops immersive, so the actor's echo stays in `#feed` and other players' WS chat degrades into it via `appendToChat`. The grid `game.html` branch is simplified to Standard-only (all the `!= immersive` guards and the left chat-pane removed). Still chronicle-only + MUD-narrated (`MUD_CHRONICLE_LAYOUTS`). | [x] `game_immersive.html`; `game.html` `elif immersive` branch + grid de-immersived + command-bar guard; `.immersive-rail`/`.immersive-ico`/`.immersive-map`/`.immersive-cmd` CSS; `route_chat_oob` narrowed to `separate_chat or classic`. Tests: `test_immersive_layout_renders_full_bleed_shell`, `test_immersive_own_chat_folds_into_chronicle` (rewritten from the old chat-pane tests); MUD-narration tests unchanged. **All five modes now have bespoke shells.** |
| 60.1 | **Per-mode typography pass.** Give each Mode a tuned type treatment, scoped by its palette class (the palette carries the mode's typographic identity in the coupled design): Standard → JetBrains Mono, code-literal (`calt` off), 13px/1.7 chronicle; E-reader → Spectral serif 15px/1.8 with oldstyle figures (`onum`) + `text-wrap:pretty` + italic spoken lines; Dock → IBM Plex Sans weight hierarchy + timestamp chips; Immersive → IBM Plex Sans 15px/1.7, 26px room name with amber candlelight glow; Classic → IBM Plex Mono 13.5px/1.62, `calt` off + slashed `zero`. Shared: capped prose measure (`--lc-measure` ~60–66ch) + `tabular-nums` on aligned numbers. The chronicle stops hardcoding `font-serif` so it inherits the Mode font; JetBrains Mono added to the font load. | [x] `base.html` font load + JetBrains Mono; `game.html` `#feed`/`#chat-feed` drop `font-serif`; e-reader layout rule → Spectral-first family; per-mode typography section in `custom.css`. Test: `test_typography_fonts_loaded_and_feed_inherits_mode_font`. **Follow-ups:** self-host fonts (FOUT on parchment/CRT); density axis via a single `--lc-fs` rem base. |
| 60.2 | **Minimap de-boxing + Dock's textual inventory (closer emulation round 4).** Refreshed `lorecraft-export/` reference confirmed a pattern true across all five mockups: `#minimap`/`#inventory` are always bare content — the card border/rounding/title lives in the SURROUNDING template, never inside the swapped partial — so a mode that already wraps the include in its own card (dock, e-reader, immersive) was double-boxing. (a) `partials/minimap.html` now renders bare content only (no border/rounded/header); each mode's own wrapper supplies the title + refresh/full-screen-map buttons in its own idiom (Standard's card head, Dock's `dock-card__head`, E-reader's "THE KNOWN WAYS" kicker, Immersive's new `.immersive-map__head`, Classic's plain "── MINIMAP ──" text) — `mm-graph`/`mm-compass` gained a shared radial-gradient backdrop since they no longer inherit one from a card. (b) Dock's inventory switched from the rarity icon-grid to the reference's **textual row** — item name coloured by type + a small uppercase type tag (weapon/armor/item/coin) + weight, no icon glyph; `_item_icon` gained a `type` field reusing the existing data-driven classification. | [x] `minimap.html` stripped to bare content; `game.html`/`game_dock.html`/`game_ereader.html`/`game_immersive.html`/`game_classic.html` each own their minimap card chrome now; `.mm-graph`/`.mm-compass` radial-gradient backdrop; `.classic-map-box`/`.immersive-map__head`/`.mm-body-dock` CSS; `inventory.html` `.invlist`/`.invlist__row` (replacing `.inv-grid`/`.inv-slot`); `_item_icon` `type` field. Tests: `test_minimap_is_bare_content_no_double_box`, updated dock/right-rail tests for `invlist`. |
| 62 | **Layout/scheme axis split, Standard+Dock rebuild, full Stats pane (v0.54.0, backfilled to this ledger 2026-07-09 — shipped without a roadmap entry).** Per-mode typography (font faces, sizes, leading, features, measure, glow, timestamp chips) moved off the `theme-*` palette classes onto the `layout-*` classes, so picking a colour scheme repaints without reflowing text — a **Theme** is now Layout + Colour scheme. Colour schemes renamed/retuned to the design exports (Classic/Classic Amber → Mono Green/Mono Amber, usable under any layout; Terminal retuned to a green-tinted palette; per-scheme character colours match each export). Standard layout rebuilt to the export design (compact exits readout + ALSO HERE in the Location card, prompt+SEND moved into the chronicle card, one tabbed Inv/Quests/Stats right-hand card). Dock's right column now mirrors Standard's panes as a window-shade accordion. Every layout's map pane gained a `⇄` graph/compass toggle persisted via `/settings/appearance`. The Stats pane became the full "Score" readout (vitals meter bars, attributes, level/xp, trait chips, marks, reputation band, active effects) in both Standard and Dock. | [x] `preferences.py`, `custom.css` token/typography split, `game.html` (Standard) / `partials/game_dock.html`, `partials/stats_panel.html`; CI e2e fixes for the resulting DOM changes shipped separately as v0.55.3 (see the "Sprint 62-era" note in `CHANGELOG.md`). |
| 67 | **`webui-theming` agent skill + `MODE_DEFAULT_THEME` single-sourcing.** Added `.agents/skills/webui-theming/SKILL.md` (mirrored to `.claude/`/`.grok/`/`.codex/` per the repo's multi-platform skill convention) baking in the Layout × Color-scheme architecture so future agents don't have to re-derive it from a full-webui code dive. Writing it surfaced a real bug: `MODE_DEFAULT_THEME` (layout → default scheme) was hand-copied into two client-side JS literals (`base.html`'s `lcApplyTheme()`, `settings.html`'s `applyPreview()`) alongside the authoritative Python dict in `preferences.py`, with nothing keeping the three in sync — editing only the Python dict left both live-preview paths silently showing the *old* default scheme's colours. Fixed by injecting the dict once as JSON (`frontend.py` sets `templates.env.globals["MODE_DEFAULT_THEME_JSON"]`; `base.html` assigns it to `window.LC_MODE_DEFAULT_THEME`) and pointing both JS call sites at that global instead of their own literals — one source of truth, zero JS copies left to drift. | [x] `frontend.py` `MODE_DEFAULT_THEME_JSON` global; `base.html`/`settings.html` read `window.LC_MODE_DEFAULT_THEME`; skill docs updated to match. Test: `test_mode_default_theme_injected_as_single_source_for_client_js`. |
| 66 | **Multi-level map foundation (`map_z`).** Rooms gain `map_z: int = 0` (floor/level; additive column, defaults to ground floor — no migration risk). `build_map_data()` gains a `level: int | None` param (`None` = every floor, matching prior behavior; an int hard-filters candidates to that floor) so a floor that reuses the same `(map_x, map_y)` footprint as another floor no longer overlaps on the minimap/full-map plot. All player-facing call sites (sidebar minimap, post-command refresh, `/partials/minimap`, `/partials/map-full`, the transit minimap panel) now pass `level=current_room.map_z`. Threaded through the whole authoring path too: `RoomData` (validator), `import_world`/`export_world_document` (loader), changeset `create` (versioning), and the admin room editor (REST API, SPA form, TUI table column) all read/write `map_z`. `up`/`down` exits are unaffected — `map_z` only changes what's *drawn*, not traversal. | [x] `engine/models/world.py` `Room.map_z`; `db.py` sqlite compat-column migration; `world/validator.py`/`loader.py`/`versioning.py`; `rendering.py` `build_map_data(level=...)`; 5 call sites (`frontend.py` ×4, `transit/presentation.py`); admin `routers/world.py`/`routers/players.py`/`index.html`/`tui/app.py`; `main.py` `_room_snapshot` WS payload. Tests: `test_level_filters_out_rooms_on_a_different_floor_at_the_same_xy`, loader round-trip, changeset-create, admin API map_z coverage. **Deferred:** full-map level selector / dashed inter-level connection lines (`level=None` is already wired for whenever that UI lands); `world_content/world.yaml` still single-floor (content, not engine). |
| 59.5 | **Closer emulation round 1: E-reader layout, rarity inventory, compass sizing.** From the `lorecraft-export/` reference set: (a) a bespoke **E-reader layout** (renamed from `ledger`) — `partials/game_ereader.html`: left ledger (location + compass) · centre serif folio (chronicle + *Inscribe* prompt) · right **vertical tab rail** (Here/Quests/Pack/Stats → run look/journal/inventory/score); serif forced via `body.layout-e-reader`. (b) **Rarity-chip inventory** — `inventory_snapshot` adds a data-driven type chip (weapon ◆ / armour ▲ / misc ● / coin ¤) + stack weight; the panel becomes `.inv__row` icon rows with an "N items · wt/cap" header. (c) Fix the **compass ballooning on room change** — the minimap OOB now marks the partial's own sized root instead of nesting it in a bare `<div id="minimap">`. | [x] `game_ereader.html`; `game.html` four-way branch; `.ereader*`/`.inv__*` CSS; `_item_icon`; `mark_oob_swap` for the minimap OOB. Tests: `test_ereader_layout_renders_ledger_folio_rail`, updated inventory-rail + snapshot + layout-body-class tests. |
| 59.4 | **Review round: drop the extra chat input, fix chat wrapping, add the switchable compass exit-star.** From the `lorecraft-export/` design references (kept local, gitignored) feedback: (a) the classic chat pane's separate input is removed — chat is sent with `say …` on the main command line (the pane is display-only); (b) fix chat lines running together — HTMX positional OOB appends the OOB element's *child nodes*, so putting `hx-swap-oob` on the `.msg` dropped its block wrapper; now wrapped in an OOB *carrier* div so each line lands as a block; (c) a new **`minimap_style`** preference (`graph` default / `compass`) — the minimap partial renders both a discovered-rooms node-map and the phosphor **exit-star compass** (lit spoke = available exit, clickable to move; theme-token colours), toggled by a `minimap-<style>` body class. | [x] `feed_items.html` OOB carrier + shared `msg_body` macro; `game_classic.html` input removed; `minimap.html` dual view + `.mm-graph`/`.mm-compass` CSS toggle; `MINIMAP_STYLES` pref + settings select; `TestMinimapStyle`, `test_minimap_style_toggles_graph_vs_compass`, strengthened chat-carrier assertion. **Still open (larger follow-up):** closer palette/markup emulation of the `standard`/`dock`/`e-reader`/`immersive` reference front-ends. |

---

## Sprint 68 — Escort quests

**Goal:** let a quest/dialogue send an NPC along with the player instead of only ever standing
still, so a story can task the player with "guide me home" content. Reuses the shipped `follow`
command's movement cascade (Sprint 47) rather than building a second one, and reuses the
pluggable quest-condition/side-effect registries (Sprint 30.1) rather than adding a new mechanism
— per [`wishlist.md`](wishlist.md) → *Quests & puzzles*, dated 2026-07-08.

| # | Task | Status |
|---|------|--------|
| 68.1 | `NPC.following_player_id: str \| None` (additive column, default `None`, no migration risk — same pattern as Sprint 66's `Room.map_z`). DB-backed rather than `FollowService`'s in-memory player-follow dict, so the new quest condition can read it via `ctx.npc_repo` alone with no shared service reference in reach. `NpcRepo.escorting(player_id)` query. | [x] `engine/models/world.py`, `db.py` sqlite compat-column migration, `engine/repos/npc_repo.py`. |
| 68.2 | `FollowService.start_escort`/`end_escort` (co-located + not-already-escorting checks, narration) and the `PLAYER_MOVED` cascade extended to also advance any NPC escorting the mover: moves along if still co-located, otherwise quietly ends the escort with a "you've lost track of them" narration — no movement-gate re-run (NPCs don't have their own move command to re-run against), unlike player-to-player follow. First real emitter of the long-declared, previously-unused `GameEvent.NPC_MOVED`. | [x] `features/follow/service.py`. |
| 68.3 | `"start_escort"`/`"end_escort"` dialogue/quest side effects (npc_id string) on the shared `npc/side_effects.py` registry — the same registry quest-stage `branches[].side_effects` already use (Sprint 30.1), so escort start/stop can be authored identically from a dialogue choice or a quest branch. `"npc_following"`/`"npc_present"` quest condition types (explicit `npc_id`) on `quests/conditions.py`'s registry, mirroring the `npc_present` *command* condition's logic (`engine/game/command_conditions.py`) for quest stages. | [x] New `features/follow/conditions.py`, wired via the `follow` feature manifest's `register_fn` (mirrors the `npc_memory` package's registration pattern). |
| 68.4 | Unit tests: escort start/end (including the co-located and already-escorting rejections), the movement cascade (moves along; quietly ends when co-location is lost), both side effects via the shared registry, both quest conditions. | [x] `tests/unit/test_escort_quests.py` — 12 tests. **Deferred:** `world_content/world.yaml` has no escort-quest content yet (a "guide me home" dialogue/quest using Mira or a new NPC) — the mechanism ships without a playtestable in-game example, same content-vs-engine split as Sprint 66's `map_z`. |

---

## Sprint 69 — Scripting-engine world-building polish

**Goal:** make the Phase A scripting engine (weather fronts, triggers, spawns — branch
`scripting_engine`, v0.57–0.70) usable and consistent from a builder's chair, and fix the
correctness gaps found while play-validating it. Small, reviewable changes; each row is its own
commit + version bump.

| # | Task | Status |
|---|------|--------|
| 69.1 | **Ambient weather narration voice.** `WEATHER_CHANGED` announces the transition to players' feeds ("A light rain begins to fall."); the admin `POST /admin/clock/weather` endpoint now emits `WEATHER_CHANGED` (previously silent). | [x] v0.71.0 — `features/weather/handlers.py`, `webui/admin/routers/clock.py`, `tests/unit/test_weather_narration.py`. |
| 69.2 | **Admin teleport fires room enter/exit behaviour.** Teleport routed through a real `GameContext` + `PLAYER_MOVED` + `broadcast_command_effects`, so encounter triggers, quest/mark progression, `follow`, and the admin dashboard's live location fire instead of a silent field swap. | [x] v0.71.1 — `webui/admin/routers/players.py`, `tests/integration/test_admin_api.py`. |
| 69.3 | **Indoor vs. outdoor rooms.** `Room.indoor` flag (additive migration); ambient weather voice and storm fronts skip sheltered interiors; demo world marks 11 interiors indoor. | [x] v0.72.0 — `engine/models/world.py`, `db.py`, `world/{validator,loader}.py`, `features/weather/{handlers,fronts}.py`, `connection_manager.occupied_rooms()`. |
| 69.4 | **World-building agent skill.** `.agents/skills/worldbuilding/` (+ `.claude/` pointer): authoritative guide to rooms/NPCs/triggers/dialogue/weather/spawns and the generated `docs/scripting_api.md` vocabulary, so any "create an NPC / scripted event" prompt consults how scripting actually works. | [x] |
| 69.5 | **Zone-qualified teleport addressing.** Teleport accepts a bare room id/name **or** `zone.room` (e.g. `town.inner_vault`), resolving ambiguous names by `area_id`. No schema change (uses existing `area_id`); integer room IDs intentionally **not** pursued. | [x] v0.73.0 — `RoomRepo.resolve_ref`, `webui/admin/routers/players.py`, `tests/unit/test_room_ref_resolution.py`. |
| 69.6 | **Admin world-clock auto-refresh.** The admin dashboard's clock panel refreshes periodically so time/weather update without a manual reload. | [x] v0.74.0 — `webui/admin/index.html` (5s poll of the Clock tab). |
| 69.7 | **Admin World panel grouped by zone.** Room list in the admin World tab grouped by `area_id` instead of a flat list. | [x] v0.74.0 — `webui/admin/index.html` + `indoor` in `GET /admin/world/rooms`. |
| 69.8 | **Flag-family rename (Phase A tech-debt #1).** Collapse the `when:`-condition drift `flag_set`/`required_flags` + `flag_not_set`/`forbidden_flags` to the one §8.4 canonical name per capability — `actor_has_flag`/`actor_lacks_flag` — registered on both command and dialogue surfaces. Catalog overlap report now empty. Zero `world_content/` uses (code+test+docs only); validator-guarded. Left as-is: `set_flags`/`clear_flags` effects (no duplicate) and the separate quest-stage `{type: flag_set}` registry. | [x] `command_conditions.py`, `registry.py` enum, `dialogue_conditions.py`, `dialogue.py`, `world/validator.py`; regenerated `docs/scripting_api.md`; updated worldbuilding skill + dialogue docs. |

---

## Sprint 40 — Admin console live-refresh (done, v0.37.0, 2026-07-05)

**Goal:** Content tabs in the admin console (Issues, News, Help) should update on their own when the underlying data changes, instead of going stale until a manual Search/Refresh. Born from admin-console issue *"Admin UI does not auto-update"*.

**Approach — reuse the existing push channel, add nothing new.** The console already opens `/admin/ws` and fans out via `AdminBroadcaster`; it was only wired for `player_*`/`changeset_scan_done`. Content mutations now push a generic `{"type": "content_changed", "resource": "<tab>"}`.

| # | Task | Status |
|---|------|--------|
| 40.1 | Shared helper `webui/admin/routers/_common.notify_content_changed(state, resource)`; called after every issue/news/help create/update/delete (each mutation already funnels through the router's `_sync_yaml`). | [x] |
| 40.2 | Frontend: lift the tab-loader map to module scope (`TAB_LOADERS`), add `refreshIfActive(name)`, and handle `content_changed` in the WS `onmessage` — reload the named tab **only when it's the active one**. | [x] |
| 40.3 | Integration test: a subscribed broadcaster queue receives `content_changed`/`issues` after `POST /admin/issues`. | [x] |

## Sprint 41 — Registered issue components (done, v0.37.0, 2026-07-05)

**Goal:** Replace the free-text issue `component` field with a **registered, strict closed set** surfaced as a dropdown, so components are consistent and filterable. Born from admin-console issue *"Issues components should be a list."*

**Design:** coarse, structural taxonomy (not per-feature) — `engine`, `webui/player`, `webui/admin`, `admin-tui`, `features`, `docs`, `infra`. Single source of truth in `lorecraft/content/components.py`; the empty value ("unassigned") is always allowed.

| # | Task | Status |
|---|------|--------|
| 41.1 | `content/components.py`: `ISSUE_COMPONENTS` + `is_valid_component()`. | [x] |
| 41.2 | API: `GET /admin/issues/components` (serves the list to the dropdown, registered before `/issues/{issue_id}` so the literal path wins); validate `component` on `POST`/`PUT /admin/issues` (unknown → 400). | [x] |
| 41.3 | Frontend: create-form and filter `component` inputs → `<select>`s populated once from the endpoint (cached). | [x] |
| 41.4 | Tests: endpoint returns the set; unknown component rejected; unit tests for `is_valid_component`. | [x] |

> **Interaction with in-game reports:** the `report` command keeps `component="player-report"` (and the matching tag). It uses the content path, which is deliberately *not* API-validated, so player reports are unaffected; those issues store and display their component unchanged. `player-report` is intentionally **not** in the registered structural set — filter such issues by their tag.

## Sprint 42 — Issues tab filter/sort + player-report live-refresh (done, v0.38.0, 2026-07-05)

**Goal:** Make the admin Issues tab usable at volume and truly live. Two dogfooding asks: (1) hide resolved/deferred by default with a way to choose what's filtered out, and sort by priority or date; (2) fix that player-filed reports didn't live-update the tab.

**Filter/sort (client-side).** The tracker is low-volume, so the tab fetches the full list and filters + sorts in the browser for one coherent model: default-hide `resolved`+`deferred` via a **"Hide status" checkbox group** (any status toggleable), a **priority** filter dropdown, and a **sort** selector — *Priority* (priority-first, newest-updated tiebreak), *Recently updated*, *Recently created* (date-first, priority tiebreak). Header shows `N shown · M hidden`; hide/sort prefs persist in `localStorage`. Replaced the old free-text status/priority filter inputs.

**Live-refresh for player reports.** The `report` command created issues via the content path (no `content_changed` push), so an open Issues tab stayed stale. Added `GameEvent.ISSUE_FILED`, emitted by the command; `main.py` forwards it to the admin broadcaster as the same `content_changed`/`issues` message the admin routers send. Now player reports (and any bus-emitting issue source) live-refresh like admin edits.

| # | Task | Status |
|---|------|--------|
| 42.1 | Client-side default filter (hide resolved/deferred), "Hide status" checkbox group, priority filter, sort selector (priority / recently-updated / recently-created); count + `localStorage` persistence. | [x] |
| 42.2 | `GameEvent.ISSUE_FILED` emitted by `report` (one-liner + wizard paths); `main.py` forwards to the admin broadcaster as `content_changed`/`issues`. | [x] |
| 42.3 | Tests: report emits `ISSUE_FILED` (unit); admin **Issues** browser e2e (`tests/e2e/test_admin_issues.py`) for default-hide, sort, and out-of-band live update; shared admin e2e fixture/login helper moved to `tests/e2e/conftest.py` with content-YAML isolation. | [x] |

## Sprint 43 — Session record & playback (advanced testing) — ✅ complete

**Goal:** record real/scripted player command streams and replay them — one scenario across **N
simulated players**, or a mix concurrently — for regression (golden audit-trail diff), load
(p50/p95/p99), and soak/fuzz. Mostly a **consolidation** of pieces that already exist: the audit
log (recording), the `VirtualPlayer`/`SimulationServer` harness (playback), `test_load.py` (N-player
fan-out + metrics), and the seeded-`GameRng` audit-regression determinism. **Full plan:
[`session_replay.md`](session_replay.md).** Supersedes the Backlog `lorecraft.tools.simulation` note.

| # | Task | Status |
|---|------|--------|
| 43.1 | **Phase 1** — `record` from the audit log → scenario JSON; single-actor `replay` via one `VirtualPlayer`; assert the normalised audit trail against a golden (data-drives `test_audit_regression.py`). | [x] `lorecraft.tools.session_replay`: versioned scenario JSON (logical actors, `{t, actor, raw}`, `world_yaml`/`rng_seed` stamps), `record_scenario()` + `record` CLI off any audit DB, shared `normalize_events()`. Replay: `tests/simulation/replay.py` (fresh `VirtualPlayer`, fast timing); `test_audit_regression.py` now data-driven off checked-in `scenarios/golden_path.json` with a **checked-in golden trail** (`golden_path.audit.json`; regen via `LORECRAFT_UPDATE_GOLDENS=1`). Sim-server factory takes `rng_seed`. Unit + sim suites green. (v0.39.4) |
| 43.2 | **Phase 2** — N-player fan-out (`--players N`) reusing the load-test percentile report; replace the fixed `test_load.py` script with recorded traffic. | [x] `fan_out_scenario()` in `tests/simulation/replay.py` maps a single-actor scenario onto N fresh concurrent `VirtualPlayer`s; report assembly (`percentile`/`latency_report`) moved to `lorecraft.tools.session_replay` (unit-tested, CLI-reusable). `test_load.py` now replays `scenarios/load_default.json` (the old read-heavy loop) and `LORECRAFT_LOAD_TEST_SCENARIO` points it at any recorded session — verified with `golden_path.json` @5 players. Same report shape/knobs (`_PLAYERS`/`_JITTER_MS`/`_JSON`); numbers match the post-WAL baseline (p50 ~56 ms @10). (v0.39.6) |
| 43.3 | **Phase 3** — mixed concurrent scenarios (`--mix`), longer soak runs, and an opt-in `simulation`-marked CI job. | [x] `mix_scenarios(server, scenarios, repeats=…)` replays distinct recorded sessions concurrently, each looped for soak, over a shared `_run_concurrent` runner (fan-out is now the same-script case); report = shared `percentile_summary()` + mix context. New `test_soak.py` mixes golden-path + load-default (quick 2-repeat default; `LORECRAFT_SOAK_REPEATS` for real soaks — verified @25 = 325 commands, p99 ~30 ms). CI's existing `simulation` job gains a `workflow_dispatch` `soak_repeats` input for opt-in longer runs. (v0.40.0) |

## Sprint 44 — Weather-driven world effects — ✅ complete

**Goal:** the weather/season state machine mostly flavored descriptions — make it drive a real
mechanic. From [`wishlist.md`](wishlist.md) → *Weather-driven world events*.

**Design note (corrected during build):** weather is **global clock state affecting rooms by terrain**,
a natural fit for the **§3.5 modifier resolver** (read-through, like room auras / terrain gating) —
*not* the Sprint 39 timed-room-effect primitive (that is for *localized, TTL* effects, and would mean
materializing a redundant effect row per outdoor room on every weather change). Each behavior keeps one
owner: the clock owns weather, terrain defs own terrain, the resolver composes them.

| # | Task | Status |
|---|------|--------|
| 44.1 | `WeatherTerrainModifierSource` (`features/weather/modifiers.py`): harsh weather (`COLD_WEATHERS` + thunderstorm/heavy_rain) subtracts a penalty from a skill-gated terrain's `required_skill`, read through `resolve_for`. So a **blizzard can push a marginal traveller below a mountain pass's survival requirement** via the *existing* movement terrain gate — no new movement code, no materialized room effects. Registered at module import; unit-tested (penalty in harsh weather on skill-gated terrain, none in clear weather or on sheltered terrain). | [x] |

## Sprint 46 — Item discovery journal — ✅ complete

**Goal:** the Sprint 25.3 `journal` records places visited, people met, lore learned, and active
quests — but **not items**. Add discovered-item tracking so finding a distinct item is a recorded
exploration payoff (pillar #1).

| # | Task | Status |
|---|------|--------|
| 46.1 | Track first discovery per item *definition* (not per instance): `Player.discovered_items`, set on first `take`/`examine` — same pattern as `met_npcs` (set on first `talk`). | [x] `Player.discovered_items` + `SaveSlot.discovered_items` (save/load parity); `_record_item_discovery()` in `inventory/service.py`, hooked from `_emit_item_taken` (all take paths) and `examine` — per-definition (`item.id`), idempotent. Additive sqlite migrations for both tables. (v0.40.5) |
| 46.2 | `journal` gains an "Items discovered" section (names, matching the journal's existing read-only style); unit tests for first-discovery tracking + journal output. | [x] `JournalService._show_items` between people-met and lore, same read-only style ("Items discovered: …" / "none yet."). 4 new unit tests (take-once idempotent, examine-without-take, journal shows names, empty state). |

## Sprint 47 — Follow command (social movement) — ✅ complete

**Goal:** `follow <player>` — when the target moves, followers move with them; `unfollow` stops.
Overt, not stealthy: both sides see narration. The lightweight slice of the wishlist's *Player
groups / parties* idea, and a natural pairing with transit (board the ferry together) without
building parties.

| # | Task | Status |
|---|------|--------|
| 47.1 | Follow state + movement hook: follower auto-moves on the target's movement event, re-running the standard movement gates (terrain/skill/hidden/locked exits) — a failed gate breaks the follow with a message to both sides. Chains allowed (A→B→C), cycles rejected. | [x] New Tier 2 `follow` feature: `FollowService` holds an **in-memory** follow graph and subscribes to `PLAYER_MOVED`; co-located connected followers are re-moved through the standard `MovementService.move` gates via a `dataclasses.replace` sub-context. Gate failure (detected by not reaching the target's room) breaks the follow and notifies both sides; chains cascade because each auto-move emits its own `PLAYER_MOVED`; cycles rejected at follow-time. Needed a generic engine seam — `GameContext.pending_deliveries` (deferred async WS pushes drained by `broadcast_command_effects`), since the event bus is synchronous but followers need live pushes. (v0.40.6) |
| 47.2 | `follow <player>`/`unfollow` commands (movement feature `commands.py`); narration both sides ("X begins following you."); bare `follow` shows current status; tests incl. a multi-room chain and a gate-failure break. | [x] `follow`/`unfollow` verbs (movement category); both-sides narration on follow/unfollow (target push); bare `follow` shows who you follow + who follows you. 5 unit tests (follower moves, A→B→C chain cascade, self/absent reject, cycle reject, gate-failure break) + a **live two-player WS check** (follower's socket gets "You follow X east." + panel refresh). |

## Sprint 48 — Scavenger hunt events (design-first) — ✅ complete

**Goal:** a scheduled, time-boxed world event: a themed set of items/clues is placed across rooms
and players hunt them for a reward (coins, a collectible mark, lore). Exploration-pillar event
content on existing primitives (scheduler + world clock for the window, item spawns, flags/journal
for progress, news/feed for announcement). The simplest, *non-instanced* slice of the wishlist's
*Instanced minigames / scenarios* idea.

| # | Task | Status |
|---|------|--------|
| 48.1 | **Design spec first** — YAML event definition (item/clue set, spawn room pools, cadence or admin trigger, duration, completion rule, reward), announcement surface (news + feed), and per-player progress storage (flags vs. a small table). No implementation until reviewed. | [x] Spec: [`scavenger_hunt.md`](scavenger_hunt.md). Decisions: **flags** for per-player progress (persist via SaveSlot, journal-visible, no new table); **news items** for announcements (synchronous DB — sidesteps the async-from-scheduler broadcast problem, no live feed ping in v1); YAML defs loaded into an in-memory registry (weather/terrain pattern); completion = "find all" (count variant deferred); reuses scheduler / `ItemLocationService.spawn` / `ITEM_TAKEN` / `LedgerService` / `GameRng` — no new Tier 1 mechanism. (v0.40.7) |
| 48.2 | Implement as a Tier 2 feature package (`features/…` + manifest, auto-discovered) per the spec; content-lint for event YAML references (item keys, room pools). | [x] `features/hunts/` (auto-discovered): `models.py` (Pydantic `HuntDef`/`HuntsDocument`, registry, `lint_hunts`), `service.py` (`open`/`close`/`ITEM_TAKEN` find + reward/`SCHEDULED_JOB_DUE` open-close), `commands.py` (read-only `hunts` verb). Progress in player flags, announcements as news items, coins via ledger. `LORECRAFT_HUNTS_YAML_PATH` config; loaded into the registry at startup. Wired into `ServiceContainer`/`register_all_commands`/`main`. (v0.40.8) |
| 48.3 | Ashmoore example hunt + tests: event opens/closes on schedule, item found → progress → reward, audit-regression stays stable. | [x] `world_content/hunts.yaml` — the Harvest Trinket Hunt (3 trinket items added to `world.yaml` as definitions only) across village_square/market/inn. 10 unit tests (open spawns clues, find→progress→reward+lore, no double-reward, close despawns, scheduled open/close, content-lint clean/dirty, dup-id + negative-coin validation, shipped-content lints against the real world). Audit-regression golden **unchanged** (definitions aren't placed by default). |

## Sprint 49 — Encumbrance & analytics dashboard (Tier 2 + observability) — ✅ complete

**Goal:** Ship inventory encumbrance (weight capacity, gating) as a Tier 2 feature, and build an admin analytics dashboard surfacing p50/p95/p99 operation latency (Sprint 35.3 data) with player activity heatmaps and an operation timeline. Together: player progression friction + ops visibility.

**Reconciled (2026-07-06):** the **encumbrance model already existed** as the `encumbrance` feature (`Item.weight`, `resolve_carry_capacity`/`total_carried_weight`/`encumbrance_band` composing the §3.5 modifier resolver, strength-scaled base) with `take` already gated on overload ("You can't carry any more weight.") and fatigue draining by band — so 49.1 was largely done. The design also gates **carrying** (can't pick up more than you can haul), which is kept over the roadmap's speculative "too heavy to *move*" (movement-weight gating would be punishing and duplicate the take gate). This sprint therefore delivered the genuinely-missing pieces: the **weight UI** and the **analytics dashboard**.

| # | Task | Status |
|---|------|--------|
| 49.1 | **Encumbrance model** — weight, carry capacity, bands, overload gate. | [x] **Already shipped** as the `encumbrance` feature (`rules.py`) + `Item.weight`; `take` gates on overload; fatigue drains by band. No change needed beyond the snapshot helper below. |
| 49.2 | **Weight UI** — player sees current/max carried weight + band on the inventory panel. | [x] `encumbrance_snapshot()` (current/capacity/band) + `encumbrance_snapshot_for()` wired into all three inventory renders (game page, HTMX command OOB swap, `/partials/inventory`); weight line in `inventory.html`, colored by band (amber/red). Verified live ("WEIGHT 0.0 / 80.0"). *(The roadmap's "too heavy to move" movement gate was dropped in favour of the existing take-gate — see reconciliation note.)* |
| 49.3 | **Analytics dashboard** (`/admin/analytics/dashboard` + admin console tab): p50/p95/p99 latency by operation, operation timeline (recent ops w/ duration), player-activity-by-hour heatmap. | [x] New `operation_timeline()` + `activity_by_hour()` analytics queries; `/admin/analytics/dashboard` one-call endpoint (Observer auth, `range`/`timeline_limit`); new **Analytics tab** in the admin console (latency table, CSS-bar heatmap, recent-ops table — no charting lib). |
| 49.4 | Tests. | [x] Timeline (order/limit) + heatmap (24-bucket density) analytics unit tests; dashboard endpoint schema + auth integration tests; `encumbrance_snapshot` unit test; audit-regression golden unchanged. (v0.40.9) |

> **Rationale:** Encumbrance ties inventory to character progression; the analytics dashboard keeps ops/player-health visible post-launch. Both low-risk over stable foundations (inventory, traits, audit).

## Sprint 50 — E2E browser test coverage (multiplayer & UX layers) (done, v0.40.13–v0.41.1, 2026-07-06)

**Goal:** Expand `tests/e2e/` coverage from single-player smoke tests to **multiplayer/WebSocket paths**,
**auth flows**, and **interaction seams** (Alpine/HTMX). Existing e2e tests cover the happy path
(create→move→take) and basic UI (map modal, mobile tab bar). The gaps: **zero coverage of the WS
multiplayer layer** (`broadcast_to_room`, `feed_append`, `player_joined`/`player_left`, cross-client
state updates) and **auth edge cases** (wrong password, unknown username, session reload). These are
high-risk, expensive to verify manually, and only testable end-to-end.

**Guiding principle:** a test belongs in e2e *only if* it depends on real **DOM / HTMX swaps**, **Alpine
reactive state**, or **WebSocket-driven cross-client updates**. Pure command→response correctness
(economy math, parser edge cases) stays in `tests/integration/` — e2e is expensive (real Chromium +
real uvicorn socket, serial). **Full plan: [`e2e_test_plan.md`](e2e_test_plan.md).**

Rollout order: harness prerequisites first (H1–H3), then Priority 1 (multiplayer, the marquee gap),
then P2 (auth), then P3–P4 (interaction + panels), finally P5 (flaky reconnect tests, last with
generous timeouts).

**Status: complete (v0.41.0 → v0.41.5).** Harness (H1–H3) + **15 new e2e tests** shipped: P1 (5,
multiplayer/WS), P2 (5, auth), P3 (4, interaction), P4 (3, panels), P5 (1, reconnect). The three
subtasks first deferred for missing world content / harness capability were then **addressed for
real** (v0.41.5) rather than fabricated around:
- **P3.3** (locked door → key): added a **Vault Hall → Inner Vault** locked-exit area off the
  locksmith gallery, with a matching **Good Key** and non-matching **Bad Key** (obvious names) — real
  world content demonstrating the exit lock/unlock mechanic.
- **P4.2** (equipment): added an **Equippable Helmet** (`slot: head`, `wearable`) in the blacksmith
  forge — closing the "demo world can't exercise equipment" gap; the wear/remove flow moves it out of
  and back into the inventory panel.
- **P5.1** (reconnect): confirmed `set_offline(True)` doesn't sever an open WebSocket, so added a
  clearly-named client debug hook (`window.Lorecraft.debugDropSocket()`) to force a real drop, and
  test that the socket **auto-reconnects and resumes live delivery**. Backfilling messages *missed
  during* an outage is intentionally out of scope — `say`/room narration are transient (not audited to
  the room feed), so replaying them would need durable chatter persistence, a separate design decision.
All new content placed off the audit-regression golden path (golden unchanged); full suite 980 +
e2e 36 green.

| # | Task | Status |
|---|------|--------|
| 50.1 | **Harness H1: two-player fixture & shared helpers.** New `second_page` fixture yielding an independent browser context in the same live server; extract duplicated `_create_character` / `_send_command` helpers from the three existing e2e test files into a centralized `tests/e2e/_helpers.py` (precondition: rotten duplication will diverge otherwise). | [x] Shared helpers centralized in `tests/e2e/_helpers.py` (`create_character`, `send_command`, `send_command_via_enter`, `enable_separate_chat`, `navigate_to_locksmiths_gallery`); `second_page` fixture added to conftest; all existing e2e test files updated to use shared helpers; existing e2e tests verified passing. (v0.41.0) |
| 50.2 | **Harness H2: WS-settled signal.** Document and implement a pattern for multiplayer assertions: `page.wait_for_function(...)` on the receiver's DOM, never synchronous asserts after a cross-client action (WS pushes are async; the next event loop turn is when B's panel updates after A acts). Candidate signal: status dot gaining `bg-emerald-500` in `ws.onopen`, or `page.wait_for_function` on `window`-exposed WS state. | [x] The status dot is server-rendered already carrying `bg-emerald-500`, so it can't signal connection — instead added a minimal `window.Lorecraft.isConnected()` accessor (real WS flag set in `ws.onopen`/`onclose`, also useful for console debugging). `wait_for_ws_connected()` polls it; multiplayer pattern documented in _helpers.py module docstring. (v0.41.0) |
| 50.3 | **Harness H3: offline toggle** (only for P5.1 reconnect test). Playwright `context.set_offline(True/False)` to exercise `app.js` reconnect + `reconnect_sync` backfill. Kept separate because it is timing-sensitive. | [x] `set_offline(page, offline)` added, but **`set_offline(True)` does not sever an already-open WebSocket in this Chromium** (`window.Lorecraft.isConnected()` stays `true` for the whole offline window). Superseded for reconnect testing by `drop_ws()` + the `debugDropSocket()` client hook, which forces a real drop (v0.41.5). See P5 (50.8). |
| 50.4 | **Priority 1 — Multiplayer / WebSocket (`test_multiplayer_realtime.py`):** P1.1 `say` propagates to another player; P1.2 `player_joined` increments "Here Now"; P1.3 `player_left` decrements; P1.4 dropped item becomes visible; P1.5 observer sees third-person narration form (closes the 2026-07-04 actor-only test's other half). | [x] All 5 tests passing. Uses `wait_for_ws_connected()` so the receiver is connected before the actor broadcasts, then asserts on the receiver's DOM. Assertions are username-based on `#players-online` (P1.2/P1.3) rather than `#player-count` — the count is server-rendered and not WS-refreshed, and `village_square` always holds the unconditional `player-2` seed body. (v0.41.0) |
| 50.5 | **Priority 2 — Auth & session lifecycle (`test_auth_flows.py`):** P2.1 log in via the Log In tab (existing char); P2.2 wrong password rejected (401); P2.3 unknown username doesn't silently create an account (404); P2.4 session persists across reload (cookie); P2.5 unauthenticated `/game` redirects to `/lobby`. | [x] All 5 passing (v0.41.1). Reconciled to actual server behavior: the browser login form re-renders the lobby with an inline error + **400** (not 401/404 — those are the JSON `/auth/*` codes), and unauthenticated `/game` returns **401** (not a `/lobby` redirect; `allow_query_player_id` defaults off). Tests assert the security property (stays on lobby / never reaches `/game`). Added `login_character` helper + `new_page` cookie-isolated context factory fixture. |
| 50.6 | **Priority 3 — Interaction flows (extend `test_gameplay_flows.py`):** P3.1 command history ArrowUp/ArrowDown multi-entry + index reset; P3.2 full dialogue traversal + dismiss; P3.3 locked door → key golden path (multi-step regression anchor); P3.4 invalid command robustness. | [x] All 4 passing. P3.1/P3.2/P3.4 (v0.41.2); **P3.3 (v0.41.5)** now backed by real content — a **Vault Hall** (off the locksmith gallery, east) with a locked east exit (`key_item_id: good_key`) to the **Inner Vault**, holding a matching **Good Key** and non-matching **Bad Key**. Test drives the full mechanic: locked with no key → Bad Key rejected → Good Key unlocks → pass through. |
| 50.7 | **Priority 4 — Panel rendering (`test_panel_rendering.py`):** P4.1 minimap current-room highlight moves on movement; P4.2 equipment/wield/wear/unwield flow; P4.3 feed autoscroll + top/bottom controls. | [x] All 3 passing. P4.1/P4.3 (v0.41.3); **P4.2 (v0.41.5)** now backed by a real **Equippable Helmet** (`slot: head`, `wearable`) in the blacksmith forge. Test: `take` → helmet in inventory; `wear` → leaves the loose inventory panel; `remove` → returns. Closes the "demo world can't exercise equipment" gap. |
| 50.8 | **Priority 5 — High-value but flaky (P5.1 reconnect test).** WS reconnect / resync backfill: A and B connected; set B offline; A acts (missed); set B online; `app.js` reconnect + `reconnect_sync` / `feed?since=` should backfill. Assert (with generous polling) B's feed eventually contains the missed line. Implement last with long `wait_for_function` timeouts. | [x] **Reframed & passing (v0.41.5).** `context.set_offline(True)` doesn't sever an open WebSocket here (verified — `isConnected()` stays true, so a "missed" message is a false positive), so the test forces a genuine drop via a clearly-named client debug hook `window.Lorecraft.debugDropSocket()` and asserts the socket **auto-reconnects and resumes live delivery** (`test_reconnect.py`, stable over repeated runs). **Backfill of messages missed *during* the outage is intentionally out of scope:** `say`/room narration are transient — not written to the room audit feed (verified: a reload doesn't show a room-mate's `say`), so neither a reload nor `reconnect_sync` can replay them. Durable chatter replay would be a separate design decision (persist room broadcasts), not a bug this test asserts. |

## Sprint 51 — Four more analytics widgets (observability) (done, v0.42.0, 2026-07-06)

**Goal:** Round out the Sprint 49 Analytics tab with the four widgets requested but not yet built: a timeline chart, a top-commands bar chart, NPC interaction stats, and a quest completion funnel. Built on a `webui`-scoped branch, architected so any one widget can be dropped later without touching the others.

**Discovery mid-sprint:** two of the four requested widgets sit on analytics functions (`npc_interaction_counts`, `quest_completion_counts`) whose backing data was **never actually populated** — `AuditEvent.target_id` was never set on any audit record, and quest lifecycle events (`QUEST_UPDATED`/`COMPLETED`/`FAILED`) are only ever queued on the in-process event bus, never persisted as audit rows. Their existing unit tests only ever exercised fabricated `AuditEvent` rows, masking the gap.

| # | Task | Status |
|---|------|--------|
| 51.1 | **Timeline chart** — SVG scatter/line of command handler latency over time. | [x] `renderTimelineChartWidget`, built from the existing `operation_timeline()` feed (already real data; no backend change). |
| 51.2 | **Top commands bar chart.** | [x] `renderTopCommandsWidget`, wired to the existing (already real, previously unused by the dashboard) `top_commands()` — folded into `/admin/analytics/dashboard` as `top_commands`. |
| 51.3 | **NPC interaction stats** — required fixing the `target_id` gap first. | [x] `CommandEngine` now resolves the parsed command's target/object/recipient id against `NpcRepo` and threads it into `COMMAND_EXECUTED`/`BLOCKED`/`FAILED` audit records (only when it names a real NPC). `renderNpcInteractionsWidget` + `npc_interactions` dashboard key. Verified live: `talk mira` in the Ashmoore dev world → `npc_interactions: [{"npc_id": "innkeeper", ...}]`. |
| 51.4 | **Quest completion funnel** — the audit-log path (`quest_completion_counts`) is a dead end (see discovery above); sourced from live game state instead. | [x] New `analytics.quest_completion_funnel()` reads `PlayerQuestProgress` rows (started/completed/failed/in-progress per quest) directly from the game DB. `renderQuestFunnelWidget` + `quest_funnel` dashboard key + standalone `GET /admin/analytics/quest-funnel`. Verified live (`investigate_lights` funnel populated after a real quest-start dialogue choice). |
| 51.5 | Tests + architecture for removability. | [x] Each of the 4 widgets is a self-contained `{id, render(data)}` entry in `ANALYTICS_WIDGETS`, delimited by `<!-- WIDGET --> ... <!-- /WIDGET -->` HTML comments — delete a widget's block + render function + registry line to drop it without touching the others. Unit tests: engine `target_id` resolution (NPC vs. non-NPC target), `quest_completion_funnel`. Integration test: dashboard payload schema. Full suite + simulation (audit-regression golden) unaffected. |

> **Rationale:** The `target_id` fix is a genuine, narrowly-scoped bug fix (foundation/observability, not new feature surface) uncovered by trying to build the NPC widget honestly rather than against dead data. The quest-audit gap (`quest_completion_counts`) is intentionally left unfixed — tracked here as a known gap rather than expanded into this sprint's scope. Merged after the Sprint 50 e2e work (rebased for version/changelog).

---

# Performance & scaling band (Sprints 35–38) — ✅ 35–37 complete; 37.1 + 38 deferred to wishlist

**Goal:** Establish performance telemetry, capture a baseline before any optimization, then implement high-ROI single-process optimizations. Measure-first paid off twice: **Sprint 36** (parser entity-resolution, 9.3×) and the **fsync/WAL finding**. The dominant cost across every path was fsync-per-commit on the single SQLite writer; **SQLite WAL mode (37.4)** fixed it broadly — `scheduler_tick@50jobs` **1410 → 48 ms (~29×)**, load-test p50 **254 → 58 ms**. Consequently **37.1 (scheduler-commit batching)** and **all of Sprint 38 (concurrency/threading gate)** were **deferred to [`wishlist.md`](wishlist.md)** — the wall was fsync serialization, not CPU, so threads wouldn't help and WAL already removed most of the commit cost. Revisit only if a *post-WAL* realistic-load test shows a hard single-process wall.

## Sprint 35 — Performance telemetry & baseline — ✅ complete

| # | Task | Status |
|---|------|--------|
| 35.1 | Baseline micro-benchmark harness `scripts/perf_baseline.py` (p50/p95/p99 per operation vs. the Ashmoore world). | [x] Revealed parser entity-resolution was O(visible entities): `examine` parse 0.7 ms → 4.8 ms @25 items → 17 ms @100 items. |
| 35.2 | Structured perf logging: `time_operation(name)` ctx-manager; instrument parse/condition/commit/scheduler/broadcast (warn >50 ms). | [x] `time_operation(name, *, warn_ms=50.0)` in `observability.py`; all five sites instrumented. |
| 35.3 | Analytics API `/admin/analytics/performance` — p50/p95/p99 by operation from audit `duration_ms` payloads. | [x] `CommandEngine` stamps a per-operation `perf` breakdown on each `COMMAND_EXECUTED`; `analytics.operation_latency_percentiles` + endpoint, unit + e2e tested. |

## Sprint 36 — Parser entity-resolution scaling — ✅ complete

**Outcome:** `parse:examine@100items` **16.92 → 1.82 ms p50 (9.3×)**, p99 tail gone, flat in inventory size. Profiling drove the fix: DB round-trips (36.1) then full-`Item` ORM materialization (36.2), not the matcher scan — so 36.2 became a column projection and 36.3's memoization gate came back negative.

| # | Task | Status |
|---|------|--------|
| 36.1 | Eliminate per-item DB round-trips in `GameContext.get_inventory()` (batch-load rows). | [x] `ItemRepo.get_many(ids)`; `@25items` 4.79 → 1.47 ms, `@100items` 16.92 → 3.01 ms. |
| 36.2 | ~~Index visible entities by name+alias~~ → **column projection** (full-`Item` materialization was ~72% of parse). | [x] `ItemRepo.name_index(ids)` = `select(Item.id, Item.name, Item.aliases)`; `@100items` 3.01 → 1.82 ms, p99 tail collapsed ~22 → ~1.9 ms. |
| 36.3 | Re-measure; add LRU memoization only if still material. | [x] At ~1.8 ms p50 / ~1.9 ms p99, resolution no longer material — **no memoization added**. |

## Sprint 37 — Pool tuning, load test & the WAL win — ✅ complete (37.1 → wishlist)

| # | Task | Status |
|---|------|--------|
| 37.2 | Connection-pool tuning knobs (`pool_size`/`pool_recycle`) — networked backends only. | [x] `db_pool_size`/`db_pool_recycle` + env vars; documented, unit-tested. |
| 37.3 | Load test (`tests/simulation/test_load.py`): N concurrent `VirtualPlayer`s, p95/p99 before/after. | [x] Lockstep baseline p50 254 → 58 ms after WAL; p99 475 → 83 ms. Fixed a pre-existing sim-harness break. |
| 37.4 | **SQLite WAL mode** (`journal_mode=WAL` + tunable `synchronous`). | [x] `db.configure_sqlite_engine`; `scheduler_tick@50jobs` 1410 → 48 ms (~29×). Documented, unit-tested. |
| ~~37.1~~ | ~~Batch scheduler execution into one commit/tick~~ → **[`wishlist.md`](wishlist.md)** | Marginal after WAL (50 jobs/tick ≈ 48 ms). |

---

## Sprint 39 — Timed room effects (Tier 1 engine primitive) — ✅ complete

**Goal:** A general, content-agnostic primitive for applying a **time-limited effect to a room** — puzzle timers, occupant auras, weather hazards. **Design decided: reuse the Sprint 19 `ActiveEffect`/`EffectService` timed-effect primitive** (`entity_type="room"`, `entity_id=<room_id>`) — no new model/table/scheduler. Two mechanics: room-state effects write the one authoritative `Exit` state (movement unchanged); occupant auras via a new `RoomAuraModifierSource` (§3.5).

| # | Task | Status |
|---|------|--------|
| 39.1 | **Design spec** — room-effect hook interface (`on_apply`/`on_expire` for room-state; auras as a room-scoped `ModifierRegistry` source), written into [`engine_core.md`](engine_core.md) §3.9. | [x] §3.9 spec: room-state effects write the authoritative `Exit` (undo in `payload`, no read-through fork); auras are `RoomAuraModifierSource`; engine gains no exit awareness — "open the gate" is a Tier 2 `EffectDef` hook. Each behavior keeps one owner; no new model/table/scheduler. |
| 39.2 | Room-effect application + expiry on the existing primitive; `on_expire` reverses room-state. | [x] `on_apply`/`on_expire` hooks on `EffectDef`; `apply()` fires `on_apply` after flush; expiry sweep fires `on_expire` before delete, each isolated in a savepoint (failing hook rolls back only itself, row kept for retry). Unit-tested. |
| 39.3 | Read/gate points: modifier resolution consults `active_for("room", room_id)`; a plate/mechanism applying a timed gate is the first content example. | [x] `RoomAuraModifierSource` (shares `_effect_modifiers`) auto-picks-up a player's room auras; movement unchanged (effect writes the `Exit`). Content: `features/exploration/room_effects.py` `passage_open` EffectDef + `open_timed_passage` mechanism side-effect. Integration-tested. |
| 39.4 | Tests: expiry closes a gate; aura modifies a resolved value; audit-regression stable; content-lint of room-effect keys + directions. | [x] Gate open→relock, aura modify+lift, `on_expire` savepoint isolation, `on_apply`-raise rollback covered; audit-regression stable; `world/validator._validate_open_timed_passage` shape-lint + tests. |

---

## Sprint 45 — Split the social/chat feed from the narrative feed (opt-in) — ✅ complete

**Goal:** the single biggest client-UX takeaway — chatter must never scroll room/quest/action output out of view. Split narrative feed from social/channel feed into two panes, as a toggleable player option. **Full plan: [`chat_feed_split.md`](chat_feed_split.md).**

| # | Task | Status |
|---|------|--------|
| 45.1 | **Phase 1 (headless)** — GameContext chat channel (`say_chat`/`tell_room_chat`); `command_result.chat_messages` + broadcast `message_type:"chat"`; `separate_chat` preference. | [x] v0.40.3 — default UX unchanged (both render paths degrade the new type into the single feed until Phase 2). 7 unit tests. |
| 45.2 | **Phase 2 (browser)** — `app.js` dual-pane routing, `game.html` pane, styling, settings toggle; two-player e2e. | [x] v0.40.4 — `#chat-pane`/`#chat-feed` (rendered only when `separate_chat` is on); WS + HTMX routing; two-player e2e (`test_chat_feed_split.py`). |
| 45.3 | **Phase 3** — global channels (shout/tell); colored/prefixed per-channel tags; per-channel mute; mobile tab-collapse. | [x] **Completed by Sprint 52 (v0.45.0):** `tell` P2P + the `newbie` P2ALL channel (a distinct `shout` folded into named P2ALL channels by design); colored/prefixed tags (52.7); the interim v0.40.10 blanket `mute_chat` superseded by real per-channel subscriptions with a server-side drop (52.5/52.8). *Cosmetic mobile tab-collapse polish left as a standalone backlog item.* |

---

## Sprint 52 — Global channels & the channel framework — ✅ complete (v0.45.0)

**Goal:** Add the global chat channels the Sprint 45 split was built to carry; finish chat Phase 3. **Design:** two orthogonal axes — a fixed `ChatScope` enum (`P2P`/`P2ROOM`/`P2ALL`, mapping onto the three `ConnectionManager` sends) × named channels in a `ChannelRegistry` (engine owns the mechanism; `newbie` seeds capacity). Decisions: offline `tell` rejected; channels code-registered for now (world-YAML defs a follow-on); per-channel subscription generalizes `mute_chat`; verb-per-channel; rate-limiting deferred.

| # | Task | Status |
|---|------|--------|
| 52.1 | `ChatScope` + `Channel` + `ChannelRegistry` (engine mechanism); built-in `say`/`tell` + seed `newbie`. | [x] v0.44.1 — muteable-only-P2ALL enforced; `say`/`tell` at module load, `newbie` from composition. |
| 52.2 | Channel-aware chat outbox on `GameContext`, replacing the Sprint 45 lists. | [x] v0.44.2 — `chat_echoes` + `chat_outbox`; unknown channels fall back to P2ROOM (never accidentally global). |
| 52.3 | `broadcast.py` routes each outbox entry by scope; stamps `channel`. | [x] v0.44.2 — P2ALL iterates `connected_player_ids()` per-recipient (server-side subscription drop); WS `chat_messages` entries became `{text, channel}`. |
| 52.4 | `tell <player>` (P2P, offline-reject); registry auto-registers a verb per named channel. | [x] v0.44.3 — `tell`/`whisper`; topic verbs with `(Tag)` prefix baked into server text. |
| 52.5 | Per-channel subscription in prefs (generalize `mute_chat`); server-side drop. | [x] v0.44.4 — `channel_subscriptions` map; `mute_chat` retired (say/tell not muteable); client-side gate removed. |
| 52.6 | Unit tests: routing, offline-tell, verb dispatch, subscription drop, channel tag. | [x] 24 new unit tests across `test_channels`/`test_chat_broadcast`/`test_chat_verbs`/preferences. |
| 52.7 | Colored/prefixed per-channel tags on both render paths. | [x] v0.44.5 — `chat-<channel>` class; say cyan / tell violet / newbie amber. |
| 52.8 | Settings UI: per-channel toggle list replacing the mute checkbox. | [x] v0.44.5 — one subscribe checkbox per muteable topic channel, via `apply_updates`. |
| 52.9 | Two-player e2e: newbie subscribed/muted; tell reaches only target; say room-scoped. | [x] v0.45.0 — three-context e2e; Sprint 45 say-routing e2e still passes. |

**Deferred to a follow-on:** data-driven channel defs in world YAML; a distinct `shout` verb; channel scrollback/history; mobile tab-collapse polish; rate-limiting.

---

## Sprint 53 — Collectible marks / attunements — ✅ complete (v0.43.0)

**Goal:** Named passive badges earned by *discovering* things — a progression track fed by exploration, not combat. **Design:** the hunts feature (Sprint 48) is the template — `world_content/marks.yaml` defs, earned state a `mark:<id>` flag, criteria over existing `Player` journal state, boons via a `MarkModifierSource`. No new table.

| # | Task | Status |
|---|------|--------|
| 53.1 | `features/marks/` package + `marks.yaml` loader + fail-fast validation + content-lint + registry. | [x] v0.42.6 — hunts-def template; `MarkBoon.kind` typed as the engine `ModifierKind` literal. |
| 53.2 | `MarkService`: criteria eval over journal state; idempotent award = flag + announcement; `register(bus)`. | [x] v0.42.7 — rides `PLAYER_MOVED`/`ITEM_TAKEN`/`QUEST_COMPLETED` (queued pre-commit so award writes land in the txn); fixpoint loop chains mark-on-mark criteria. |
| 53.3 | Boons (`MarkModifierSource`) + `marks` command. | [x] v0.42.8 — traits `sources.py` pattern; `marks` verb lists earned + "???" teasers (hidden omitted). |
| 53.4 | Ashmoore marks content + unit/integration tests + docs. | [x] v0.43.0 — 4 marks (village_wanderer; friend_of_the_crow; far_strider +5 carry; hidden deep_delver +5 cartography); integration walk-test; shipped-content lint. |

---

## Sprint 54 — Celestial cycles: moons & tides — ✅ complete (v0.44.0)

**Goal:** Lunar phase and tide as world state derived from the world clock, gating content across pillars. **Design:** pure derivation, no new persisted state, no new scheduler — `moon_phase_for_day`/`tide_for_hour` beside `season_for_day`; change detection rides `HOUR_CHANGED`/`DAY_CHANGED`; content gates via condition registry + a tide-written authoritative `Exit`.

| # | Task | Status |
|---|------|--------|
| 54.1 | Tier 1 calendar functions + `MOON_PHASE_CHANGED`/`TIDE_CHANGED` events. | [x] v0.43.1 — `engine/clock/celestial.py`: 8-phase 16-day lunar month (drifts against the 30-day season), semi-diurnal tide. |
| 54.2 | `features/celestial/`: transition handlers; `moon_phase_is`/`tide_is` gates (command + dialogue); status-bar surfacing. | [x] v0.43.2 — handlers compare event endpoints; gates fail closed with in-fiction reasons; moon/tide in `time_update` + status bar. |
| 54.3 | Ashmoore tide-gated causeway + moon-gated dialogue beat; content-lint; integration tests; docs. | [x] v0.44.0 — data-driven `celestial.yaml` `tide_gates` drives `creek_crossing → tidal_islet` (authoritative-`Exit` writes; ungated return so the tide never strands). Required aligning the validator with the dialogue engine's open-keyed choice contract (`DialogueChoiceData` now `extra="allow"`). |

---

## Sprint 55 — Context-attached commands (object-scoped verbs) — ✅ complete (v0.46.0)

**Goal:** let world content give an **item or NPC its own verbs** that appear and work only when that object is present. Adopt Evennia's object-scoped-verb concept; **skip** its cmdset merge algebra. **Key finding:** Lorecraft already had most of the machinery — the help filter auto-hides out-of-context verbs, the shared side-effect registry provides the actions, `CommandRegistry` already supports per-command conditions. New parts: a presence gate, a content schema, a loader/dispatcher.

| # | Task | Status |
|---|------|--------|
| 55.1 | `object_present:<id>` / `npc_present:<id>` command-condition gates. | [x] v0.45.4 — join the built-in conditions; the help filter then lists a context verb only when its object is present. |
| 55.2 | `context_commands` schema on items/NPCs (validator) + content-lint + registry + loader. | [x] v0.45.5 — `ContextCommandData`, `context_commands` JSON columns (+ SQLite migrations), YAML round-trip, `features/context_commands` registry + `load_from_session` + `lint_context_commands`. |
| 55.3 | Dispatcher: one gated command per verb; resolve the present declaring object; fire side-effects; collision-warning. | [x] v0.45.6 — `context_verb:<verb>` availability condition; noun disambiguates shared verbs; verb/alias shadowing a built-in is skipped with a warning. |
| 55.4 | Ashmoore content + integration/help tests + docs. | [x] v0.46.0 — altar `read`/`study` (→ `lore:chapel_wheel`) in the Ruined Chapel + Mira's `tip` (→ `tipped_mira`); gated to their room, hidden from `help` out of context, shipped content lints clean. |

**Deferred to a follow-on:** Evennia's cmdset merge algebra; optional-prefix matching (`@look`) and per-command permission locks.

---

# Lorecraft — Roadmap

**This is the single source of truth for implementation progress** — what's done and what's next. (`docs/status.md` was retired 2026-07-04 and archived to `docs/.archive/status.md`; its Phase-based tracking had drifted out of sync with this roadmap.)

Working roadmap derived from `docs/architecture.md`, `CODE_AUDIT.md`, and recent 0.2.0 development (HTMX migration + parser v1).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started

Sprints are scoped small (1–2 tasks, one subsystem) on purpose, so each sprint/task can be picked up with minimal context.

---

## Guiding principle (2026-07-01)

**Foundation before features.** The core engine must be very well designed, well tooled, well tested, and internally consistent *before* we expand commands or introduce combat, trading, or PvP. No skimping on code design and quality. Concretely:

- The findings in `CODE_AUDIT.md` are the work queue, not background reading. Foundation sprints below map directly to them.
- New features are gated behind the **Foundation exit criteria** (see below). Combat and trading do not start until the gate is green.
- Every change during the foundation phase should *raise* consistency: one error-handling style, one context-construction path, one event-wiring style, one module-layout convention.
- Partially-finished subsystems get finished or removed — no half-done seams left behind.

---

## Current position

Phases **1–6** are implemented (command dispatch, world/time, inventory, NPCs/quests, save/disconnect, admin tools). Version **0.2.0** added parser v1, quantity inventory, and the HTMX primary UI.

[Sprints 1–3](#sprint-1--htmx-parity-playtesting-unblock-) closed out HTMX parity, command-depth gaps, and the scheduler foundation. A full code audit (`CODE_AUDIT.md`, 2026-07-01, revalidated against source) identified the engineering debt to clear next.

**Current:** Foundation ([Sprints 4–15](#sprint-4--player-authentication-production-hardening-)) and the **entire pillar-driven feature band ([Sprints 16–30](#sprint-16--item-locationownership--instance-state))** are complete — Tier 1 engine primitives (16–21), item components & equipment (22–23), traits/skills & exploration + UI (24–26), condition/trade/transit (27–29), quests & puzzles (30). **Foundation gate is green.**

Since then, the **Tier 1/Tier 2/web split** shipped as a large refactor (v0.15.0–0.31.1, tracked in [`tier_split_refactor.md`](tier_split_refactor.md), off this roadmap): Tier 1 now lives in `src/lorecraft/engine/` (import-pure — it depends on nothing under `features/` or web, enforced by `tests/unit/test_tier_boundaries.py`), the 24 Tier 2 features each own a package under `src/lorecraft/features/`, and the web hosts moved to `src/lorecraft/webui/{player,admin}/`. Player username/password validation also shipped (v0.31.0).

**Current (2026-07-05):** the post-tier-split band (Sprints 31–34) is essentially done — **Sprint 31** (tier split fully complete, v0.31.4–0.32.3), **Sprint 32.2/32.3** (account preferences + accessibility, v0.33.0–0.34.0), **Sprint 33** (guided `/report` + page-length quick-win, v0.35.0), and **Sprint 34** (`help <command>` + `score`, v0.34.0 — both open player reports resolved). **Open roadmap items:** [Sprint 32.1](#sprint-32--player-onboarding--account-ux) (in-game intro walkthrough, deferred pending a product decision on its trigger UX), [Sprint 65](#sprint-65--multiplayer-trade--transit-tests) (multiplayer trade/transit simulation tests), and the new [Performance & scaling band (Sprints 66–69)](#performance--scaling-band-sprints-6669--measure-then-optimize-no-threading-yet). **Combat and PvP are set aside to [`wishlist.md`](wishlist.md)** (2026-07-05) — they kept forcing roadmap renumbering; ready-to-restore specs live there. See [`engine_core.md`](engine_core.md) for the Tier boundary and [`wishlist.md`](wishlist.md) for the pillars and mechanics menu.

---

## Sprint 1 — HTMX parity (playtesting unblock) ✅

**Goal:** Commands execute through `POST /command`, social gameplay is visible, and WebSocket push works for multi-player panel refresh.

| # | Task | Status |
|---|------|--------|
| 1.1 | Call `CommandEngine.handle_command()` in `frontend.py` `POST /command` | [x] |
| 1.2 | Disambiguation: bare-number replies via `AppState.pending_disambig` | [x] |
| 1.3 | Dialogue overlay partial + OOB swaps from `ctx.updates["dialogue"]` | [x] |
| 1.4 | Quest tracker partial + active quests on SSR + OOB on `quest_update` | [x] |
| 1.5 | Fix WebSocket URL (`/ws?player_id=…`), handle `feed_append` / `room_event` | [x] |
| 1.6 | `players_here` from `ConnectionManager` when WS connected | [x] |
| 1.7 | Integration tests: move, take, talk via `POST /command` | [x] |

---

## Sprint 2 — Command depth ✅

**Goal:** Close gameplay gaps (item aliases, disambiguation, help, use/give/lock) before combat.

| # | Task | Status |
|---|------|--------|
| 2.1 | Item `aliases` in YAML/model; wire through `GameContext.get_visible_entities()` | [x] |
| 2.2 | Finish inventory disambiguation bug | [x] |
| 2.3 | Context-aware `help` (dialogue, combat, per-room disabled commands) | [x] |
| 2.4 | `use` command + `InventoryService.use_item()` | [x] |
| 2.5 | 2–3 more parser patterns (`give`, `open`, containers) | [~] `give` + `lock`/`unlock` (on the existing `Exit.locked`/`key_item_id` fields) shipped; `open`/container-holding items deferred — needs new Item/state modeling |

---

## Sprint 3 — Scheduler foundation ✅

**Goal:** Phase 8 per `architecture.md` §28 — the scheduling primitive combat will run on.

| # | Task | Status |
|---|------|--------|
| 3.1 | `services/scheduler.py` — DB-backed jobs on `TIME_ADVANCED` | [x] |

---

## Sprint 4 — Player authentication (production hardening) ✅

**Goal:** Phase 7 per `architecture.md` §21 — full account system with password auth, JWT tokens, and signed WebSocket handshake. Foundation for all production deployments.

**See:** [`player_authentication.md`](player_authentication.md) for detailed workflows and code examples.

| # | Task | Status |
|---|------|--------|
| 4.1 | `POST /auth/login` — account creation on first login, password hashing (bcrypt/argon2) | [x] Uses the existing PBKDF2-HMAC-SHA256 primitives in `admin/auth.py` (`hash_password`/`verify_password`) rather than adding bcrypt/argon2 as a new dependency — same security properties, one hashing convention for the whole codebase. New `PlayerAuth` table (provider-agnostic: `provider`/`provider_subject`, ready for OAuth later). `login_or_register()` in `web/auth.py` also *claims* pre-existing passwordless players (e.g. dev-seeded `player-1`) on first authenticated login rather than erroring. |
| 4.2 | JWT access tokens (15min lifetime) + refresh token rotation (8hr lifetime) | [x] Reuses `admin/auth.py`'s `create_token`/`decode_token`, signed with `Settings.player_session_secret` (distinct token `type` from the browser's `lorecraft_session` cookie — can never be replayed as each other). Fixed a latent bug found along the way: tokens only had second-precision `iat`, so two issued in the same second were byte-identical (rotation was a no-op if called twice quickly) — added a `jti` claim, fixing both the new player refresh endpoint and the pre-existing admin one. |
| 4.3 | `POST /auth/ws-ticket` — single-use, 60-second WebSocket ticket exchange | [x] Accepts either `Authorization: Bearer <access_token>` (API clients) or the signed `lorecraft_session` cookie (the browser, which can't easily attach custom headers to a same-origin fetch but sends cookies automatically). Ticket storage is an in-memory dict on `AppState` (`ws_tickets`), matching the existing `pending_disambig` pattern — fine for this engine's single-process deployment target. |
| 4.4 | WebSocket handshake: validate ticket, map to player_id, attach to ConnectionManager | [x] `main.py`'s `_resolve_ws_player_id()`: a `?ticket=` param is authoritative — invalid/expired/reused rejects the connection outright (1008) rather than silently falling back to `?player_id=`, which would defeat the point of tickets. |
| 4.5 | `/auth/refresh` endpoint for refresh token rotation | [x] Also verifies the player still exists (guards against refreshing into a deleted account), mirroring `admin/auth.py`'s `/admin/auth/refresh`. |
| 4.6 | Retire legacy `?player_id=` query param fallback (was gated by `LORECRAFT_ALLOW_QUERY_PLAYER_ID`) | [x] `Settings.allow_query_player_id` now defaults to `False`. Not deleted outright — kept as an explicit opt-in for test fixtures that intentionally exercise the wire protocol directly (`tests/simulation/`'s `VirtualPlayer`, several state-resolution integration tests), since removing it would break the [Sprint 11](#sprint-11--browser-e2e-harness-)/12 harnesses for no real security benefit (trusted local test processes, not real clients). Surfaced and fixed a chicken-and-egg bug: `GET /lobby` depended on `get_current_player`, which now 401s with no session — meaning a brand-new visitor couldn't reach the page that lets them log in. New `get_current_player_optional()` fixes this for `/lobby` only; every other route correctly keeps requiring a session. |
| 4.7 | OAuth extensibility hooks (Google OIDC callback stubs for future LAN-party deployments) | [x] `POST /auth/oauth/{provider}/callback` stub — `PlayerAuth.provider`/`provider_subject` already generalize to non-local providers with no schema change needed. Returns 501 rather than pretending to implement OAuth (needs a registered client id/secret/redirect URI this engine doesn't have configured); not wired into any client. |
| 4.8 | Integration tests: login, token refresh, WS ticket validation, expired token rejection | [x] `tests/integration/test_player_authentication.py` (15 tests) + `tests/unit/test_player_login.py` (9 tests) + updated `tests/integration/test_player_session.py` for the new password-protected lobby. Covers account creation/verification/wrong-password, refresh rotation + expired/garbage/wrong-type rejection, ws-ticket issuance (bearer + cookie) + single-use + TTL expiry + expired-access-token rejection, and the OAuth stub. Full suite (unit/integration/e2e/simulation) green throughout — the e2e run caught the `/lobby` chicken-and-egg bug above before it could ship. |

**Also done, beyond the numbered checklist:** the browser lobby (`/lobby/enter`, `/lobby/create`) is now password-protected — previously `/lobby`'s "Join a World" tab was a one-click player picker with *zero* authentication (anyone could enter as any existing character), which the numbered tasks above don't explicitly cover but would have left the real player-facing surface unprotected even with the API-level auth in place. `login_or_register()` gained `allow_create: bool` so `/lobby/enter` ("Log In") 404s on a genuinely unknown username instead of silently creating one, while `/lobby/create` keeps create-or-claim semantics. `app.js`'s `connectWebSocket()` now fetches a ws-ticket before connecting instead of using a raw `?player_id=`.

---

# Foundation band (Sprints 5–15)

Work queue derived from `CODE_AUDIT.md`. Ordering is deliberate: error/type groundwork first, then **characterization tests before the big refactors**, then structure, then tooling.

**Current progress:** [Sprints 5–15](#sprint-5--error-handling--exception-hierarchy-) complete (error handling, type safety, characterization tests, module decomposition, service consistency/wiring, extensibility seams, tooling infrastructure, browser E2E harness, simulation harness MVP, observability & CI quality gates, unified command lifecycle, core UX completion). Foundation band done — see exit criteria below.

## Sprint 5 — Error handling & exception hierarchy ✅

**Goal:** One error-handling style everywhere. Audit §2.1.

| # | Task | Status |
|---|------|--------|
| 5.1 | `lorecraft/errors.py` — `GameError`, `ValidationError`, `NotFoundError`, `PermissionError`, `ConflictError` (with machine-readable `code`) | [x] |
| 5.2 | Eliminate the 22 silent `except Exception` blocks: catch specific exceptions, log all of them (`web/frontend.py` ×12, `web/player_auth.py`, `admin/websocket.py` ×3, `admin/auth.py` ×2) | [x] |
| 5.3 | Services raise typed errors; command handlers translate to `ctx.say()` in one shared wrapper | [~] prepared via errors.py; integration in [Sprint 9](#sprint-9--service-consistency--wiring-) |
| 5.4 | Guard quantity underflow in `ItemRepo.remove_from_room` (raise/log instead of silent delete) | [x] |
| 5.5 | Unit tests for error paths (every custom exception exercised) | [x] |

## Sprint 6 — Type safety ✅

**Goal:** basedpyright verifies real invariants. Audit §2.2.

| # | Task | Status |
|---|------|--------|
| 6.1 | Type `CommandHandler` as `Callable[[str | None, GameContext], None]` (Protocol in `types.py` or `TYPE_CHECKING` import); delete all 18 `cast(GameContext, ctx)` | [x] |
| 6.2 | Replace `cast(Any, ctx)` + `getattr(..., default)` condition evaluation in `game/registry.py` with typed access — conditions must fail closed, not open | [x] |
| 6.3 | Single `build_game_context()` factory used by all entry points; make `quest_repo`/`dialogue_repo`/`audit` required and delete their None-guards | [x] |
| 6.4 | `TypedDict` schemas for WS payloads and HTMX/JSON responses | [x] |
| 6.5 | Raise basedpyright to `standard` mode on `src/` and hold it there | [x] |

## Sprint 7 — Web & admin characterization tests ✅

**Goal:** Lock in current behavior *before* the [Sprint 8–9](#sprint-8--module-decomposition-) refactors. Audit §2.3.

| # | Task | Status |
|---|------|--------|
| 7.1 | Characterization tests for `web/frontend.py`: state resolution, session reconnect edge cases, feed pagination, error rendering | [x] |
| 7.2 | Admin API endpoint tests (target ~80% of `admin/api.py` routes) | [x] |
| 7.3 | Admin WebSocket integration tests | [x] |
| 7.4 | Event-flow integration tests: command → event → service reaction → client update; handler-ordering assertions | [x] |

## Sprint 8 — Module decomposition ✅

**Goal:** No module over ~400 lines with mixed concerns. Audit §2.6.

| # | Task | Status |
|---|------|--------|
| 8.1 | Split `web/frontend.py` (1,306→780 lines) → `session.py` (380), `rendering.py` (180); replaced `getattr`-chain state access with explicit dependency injection functions | [x] |
| 8.2 | Extract `game/grammar.py` (322 lines) and `game/diagnostics.py` (119 lines) from `game/parser.py` (774→407 lines); re-exports for backwards compatibility | [x] |
| 8.3 | Split `admin/api.py` (817→20 lines) into per-resource routers under `admin/routers/`: `players.py` (191), `audit.py` (93), `world.py` (357, incl. items/NPCs/changesets), `clock.py` (125), `accounts.py` (93); `admin_router` now just mounts them, same route paths and status codes | [x] |

## Sprint 9 — Service consistency & wiring ✅

**Goal:** One way to construct, wire, and use services. Audit §3.1.

| # | Task | Status |
|---|------|--------|
| 9.1 | Service container/registry in `AppState`; remove ad-hoc `Service()` instantiation from the four command modules | [x] |
| 9.2 | One event-wiring convention: every service exposes `register(bus)`; replace the inline `bus.on()` quest wiring in `main.py` | [x] |
| 9.3 | DRY the six near-identical take/drop methods in `services/inventory.py` (shared find→disambiguate→act helper) | [x] |
| 9.4 | Consolidate item-matching logic in `repos/item_repo.py` into one matcher | [x] |

## Sprint 10 — Extensibility seams ✅

**Goal:** New mechanics hook in via data/registration, not core edits. Audit §3.3.

| # | Task | Status |
|---|------|--------|
| 10.1 | Pluggable dialogue side effects (handler registry replacing the hardcoded `set_flags`/`give_item`/`start_quest` branches in `npc/dialogue.py`) | [x] |
| 10.2 | Pluggable dialogue/exit conditions (predicate types beyond flags: level, item, quest state) | [x] |
| 10.3 | Pluggable command conditions (registry instead of the hardcoded `_evaluate_condition` chain) | [x] |
| 10.4 | Decide + document the feature-registration pattern (models/commands/events/rules per feature) — combat will be its first consumer | [x] |

## Sprint 10.5 — Tooling Infrastructure ✅

**Goal:** Admin/dev tooling foundation: repo-tracked issues & news, world CLI suite, analytics API, content validation. Unblocks [Sprint 11](#sprint-11--browser-e2e-harness-)+ (can log failures, record metrics, validate content).

| # | Task | Status |
|---|------|--------|
| 10.5.1 | Issues system: `docs/issues.yaml`, CRUD routes, admin TUI (F6) + web panel tabs | [x] |
| 10.5.2 | News & announcements: `docs/news.yaml`, in-game `/news`, RSS feed, admin UI (TUI F7) | [x] |
| 10.5.3 | World management CLI: import/export/validate/diff/stats commands; call from admin world manager | [x] |
| 10.5.4 | Analytics API foundation: metric queries ready (no dashboard yet, driven by [Sprint 13](#sprint-13--observability--ci-quality-gates-) instrumentation) | [x] |
| 10.5.5 | Content validation & linting: dead references, unreachable rooms, circular quests, etc. | [x] |

**See:** [`tooling_infrastructure.md`](tooling_infrastructure.md) for full architecture and design details. Circular quest dependency checking was scoped out — `QuestStageData` has no quest-to-quest dependency field in the schema today.

## Sprint 11 — Browser E2E harness ✅

**Goal:** Catch UI-specific regressions (HTMX swaps, OOB updates, Alpine state) that ASGI-transport integration tests can't see.

| # | Task | Status |
|---|------|--------|
| 11.1 | Browser end-to-end test harness for HTMX UI | [x] `tests/e2e/` — Playwright-driven tests against a real live uvicorn server (background thread, disposable per-test sqlite DB, real world YAML bootstrap). Optional `e2e` extra (`pip install -e ".[e2e]"` + `playwright install chromium`); excluded from the default `pytest`/`make test` run via `-m "not e2e"`; run explicitly with `make test-e2e`. Covers character creation, movement + room/inventory panel updates, and dialogue → quest-start via the Ashmoore dev world golden path. |

## Sprint 12 — Simulation harness MVP ✅

**Goal:** Real-protocol, multi-player scripted scenarios per `architecture.md` §25 — a third test transport alongside ASGI-transport integration tests and the [Sprint 11](#sprint-11--browser-e2e-harness-) browser E2E harness.

| # | Task | Status |
|---|------|--------|
| 12.1 | Simulation harness MVP (`tests/simulation/`) | [x] `virtual_player.py` — `VirtualPlayer` wraps a real `websockets` client against `/ws` (not an ASGI shortcut); `send_command()`/`run_script()` with optional timing jitter, `wait_for_broadcast()` for pushed (non-reply) messages. `conftest.py` — `simulation_server`/`simulation_server_factory` fixtures boot the real app under `uvicorn` on a background thread against a disposable per-test sqlite DB and the real `world_content/world.yaml` (same pattern as [Sprint 11](#sprint-11--browser-e2e-harness-)'s `live_server`, no synthetic world content). `test_multiplayer_scenarios.py` — two real connections: `player_joined` broadcast fan-out on connect, and concurrent `take` of a single-quantity item (no duplication/loss). `test_audit_regression.py` — runs a fixed script against two independent fresh servers and diffs the normalized audit trail, per the "capture, diff after changes" pattern in `architecture.md` §25. New `simulation` pytest marker, excluded from `make test`/plain `pytest` like `e2e` (`make test-simulation`); no new install required (`websockets`/`httpx` were already transitive via `fastapi[standard]`, now declared explicitly in the `dev` extra). Noted but intentionally not fixed here: the raw `/ws` command loop didn't yet re-broadcast `room_messages` to other occupants the way `POST /command` does — fixed by Sprint 14.1. |

## Sprint 13 — Observability & CI quality gates ✅

**Goal:** Regressions can't land silently. Audit §4.2, §5.2.

| # | Task | Status |
|---|------|--------|
| 13.1 | Structured logging (stdlib `logging` with correlation/transaction IDs from `TransactionContext`) | [x] `observability.py` — `configure_logging()` attaches a correlation-aware formatter/filter to the root logger (idempotent, level from new `Settings.log_level`/`LORECRAFT_LOG_LEVEL`); `bind_transaction_context()` publishes a `TransactionContext`'s `transaction_id`/`correlation_id` to a `contextvars.ContextVar` for the duration of one command, so every `log.*` call anywhere in that call stack (services, event handlers, repos) picks the IDs up automatically — no signature threading needed. Wired into both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`) and `create_app()`. |
| 13.2 | Command latency + event-handler timing instrumentation | [x] `CommandEngine._execute_parsed` times each command handler call and stamps `duration_ms` onto the `COMMAND_EXECUTED` audit event payload (`game/engine.py`); `EventBus.emit()` times each handler dispatch, records it on `HandlerResult.duration_ms`, and logs `event=... handler=... duration_ms=... depth=<handlers registered>` at DEBUG (`game/events.py`). New `analytics.command_latency_percentiles()` (p50/p95/p99 from `duration_ms`) + `GET /admin/analytics/latency`. |
| 13.3 | CI: pytest + coverage threshold + basedpyright + ruff as required checks | [x] `.github/workflows/ci.yml` — three required jobs on push/PR to `main`: `quality` (`make lint` + `make typecheck` + `make test-cov`), `simulation` (`make test-simulation`), `e2e` (Playwright + `pytest tests/e2e`). `make test` / `make test-cov` run the default suite with `pytest-cov` + `pytest-xdist` (`-n auto --dist=loadfile`) and `[tool.coverage.report] fail_under = 80` in `pyproject.toml` (current baseline ~82%). New `make lint`/`make typecheck` targets. Fixed a latent bug found while wiring this up: `tests/simulation/*.py`'s `from tests.simulation.conftest import ...` only worked under `python -m pytest` (which prepends cwd to `sys.path`), not bare `pytest` (what `make test-simulation` and CI actually run) — `pythonpath` in `pyproject.toml` now includes `"."` alongside `"src"`. |

## Sprint 14 — Unify command lifecycle ✅

**Goal:** One 13-step transaction/event/audit lifecycle shared by `/ws` and `/command` paths (long-standing `[~]` STATUS item). Easier after [Sprint 8](#sprint-8--module-decomposition-) decomposition.

| # | Task | Status |
|---|------|--------|
| 14.1 | Extract shared lifecycle; both entry points call it; add rollback-on-error semantics | [x] **Rollback-on-error** — `CommandEngine._execute_parsed` (`game/engine.py`) now catches exceptions from the command handler instead of letting them propagate uncaught. On a crash: `GameContext.rollback_state_changes()` (new `rollback_state` callable, wired at both entry points to the DB session's `.rollback`) undoes any half-applied state; `ctx.messages`/`room_messages`/`updates`/`pending_events` are cleared so no partial narration leaks out (architecture.md §26's golden rule: never tell clients something happened until the DB says it happened); a generic error message replaces it; a new `GameEvent.COMMAND_FAILED` audit event (severity ERROR) records the crash. **Broadcast unification** — new `game/broadcast.py`'s `broadcast_command_effects()` is the one place step 12 (room broadcast) now lives; both `main.py`'s `/ws` command loop (now `async`) and `web/frontend.py`'s `POST /command` call it after `CommandEngine.handle_command()` returns, closing the gap [Sprint 12](#sprint-12--simulation-harness-mvp-)'s simulation tests surfaced (the raw `/ws` path never re-broadcast `ctx.room_messages`/`state_change` to other room occupants the way `POST /command` did). Verified with a new simulation test exercising the previously-broken path over a real socket, plus the full existing suite (unit/integration/e2e/simulation) unchanged. **Construction unification (follow-up)** — `game/context.py`'s `build_game_context()` factory (added Sprint 6.3, meant to be "the" `GameContext` construction path) turned out to be unused by both real entry points. Extended it to accept `audit_session` (a separate `Session`, matching real usage — replacing the old same-session `create_audit_repo` bool) and `rollback_state`, and to pass `clock` straight through rather than synthesizing a fallback `WorldClock` (a fabricated clock would be silently wrong data, not a safe default). `main.py` and `web/frontend.py` now both call it instead of constructing `GameContext` inline. |

## Sprint 15 — Core UX completion ✅

**Goal:** Finish the partially-shipped core UX so nothing is left half-done.

| # | Task | Status |
|---|------|--------|
| 15.1 | World clock / weather status bar push via WS | [x] `ConnectionManager.broadcast_global()` + a `TIME_ADVANCED` handler in `main.py` push `time_update` (hour/minute/day/season/weather) to every connected player, not just on connect/reconnect SSR. |
| 15.2 | Multi-player live lists finished (`[~]` STATUS item) | [x] `game/broadcast.py`'s `broadcast_command_effects()` now sends a second `state_change` (`players-online` panel) to the room a player *left*, not just the room they entered — previously occupants of the old room only saw the departure narration text, not a live players-list refresh. |

---

## Foundation exit criteria (gate for Sprints 16+)

All must be true before combat/trading work starts:

- [x] Zero silent `except Exception` blocks in `src/` ([Sprint 5](#sprint-5--error-handling--exception-hierarchy-))
- [x] Zero `cast(GameContext, ctx)` / `cast(Any, ctx)` in `src/`; basedpyright `standard` mode clean ([Sprint 6](#sprint-6--type-safety-))
- [x] One `GameContext` construction path; no optional repo fields — **fixed (2026-07-02):** `build_game_context()` now accepts `audit_session` (a separate `Session`, matching real usage) instead of the old same-session `create_audit_repo` bool, `rollback_state`, and passes `clock` straight through instead of synthesizing a fallback `WorldClock`. Both `main.py`'s `/ws` loop and `web/frontend.py`'s `POST /command` call it instead of constructing `GameContext` inline.
- [x] No module >~500 lines with mixed concerns ([Sprint 8](#sprint-8--module-decomposition-))
- [x] One service wiring convention; no inline `bus.on()` in `main.py` (Sprint 9.2)
- [x] Web + admin layers have integration coverage; CI enforces coverage, types, and lint ([Sprint 7](#sprint-7--web--admin-characterization-tests-) + Sprint 13.3)
- [x] Feature-registration pattern documented and demonstrated (10.4)
- [x] All `[~]` STATUS partials either finished or explicitly retired — [Sprint 14](#sprint-14--unify-command-lifecycle-) closed the `/ws`/`/command` broadcast-lifecycle gap; [Sprint 15](#sprint-15--core-ux-completion-) closed world clock/weather WS push (15.1) and the multi-player live-lists refresh gap on room-leave (15.2)

---

# Engine core band (Tier 1 primitives) — Sprints 16–21

**Engine-first (2026-07-03).** The eight cross-cutting Tier 1 primitives from
[`engine_core.md`](engine_core.md) are built here, **before** the Tier 2 feature modules that
consume them ([Sprints 22](#sprint-22--standard-item-components--definition-fields)+). Rationale: several feature sprints share these primitives; building
them per-sprint yields N opinionated implementations and blurs the framework/game boundary. Order
follows dependency + leverage ([`engine_core.md`](engine_core.md) §6) — the two most expensive to
retrofit (unified item location/ownership, and a seedable `ctx.rng` the audit-regression harness
depends on) go first. These primitives are **content-agnostic**: no named skills, slots, factions,
or damage formulas live here.

## Sprint 16 — Item location/ownership & instance state ✅

**Goal:** One way to say where an item lives and to move it atomically; per-instance state via
registered components. Highest-leverage primitives — they underpin equipment, containers, shop
stock, corpses, and trade escrow. **See [`engine_core.md`](engine_core.md) §3.1–3.2, §4a/§4f.**

| # | Task | Status |
|---|------|--------|
| 16.1 | `ItemStack` + `(owner_type, owner_id, slot?)` location + holder registry; one atomic `ItemLocationService.move()` (rollback-safe); **replace** `Player.inventory`/`RoomItem` outright (column/table deleted — full blast-radius table in [`engine_core.md`](engine_core.md) §3.2) | [x] |
| 16.2 | `ItemInstance` carrier + pluggable component registry (durability/openable/lit/container register like dialogue side-effects); `bound`/soulbound flag | [x] `ComponentRegistry` (`game/components.py`) ships with zero registered components (Tier 1 registers none, per spec); `Item.bound` field added (enforcement deferred to Tier 2). |

**Delivered beyond the two checklist items:** full blast-radius migration (17 files) onto the new
primitive — `services/inventory.py`, `repos/item_repo.py`, `game/context.py`,
`game/command_conditions.py`, `services/movement.py`, `services/quest.py`,
`npc/side_effects.py`, `services/save.py` (v1-save-compatible load), `world/loader.py`,
`world/versioning.py`, `tools/world_cli.py`, `scripts/import_world.py`,
`admin/routers/players.py`, `main.py`, `web/session.py`, `web/frontend.py`. 23 new invariant
unit tests (`tests/unit/test_item_location_service.py`); full existing suite (431 unit/
integration + 3 e2e + 5 simulation, including the audit-regression diff and the
concurrent-take-no-duplication guarantee) green unchanged. See `CHANGELOG.md` for the full
list of bugs caught along the way (typed-error argument order, a missing `StackRepo` flush,
a pydantic recursion bug in `list[JsonValue]` SQLModel fields). Schema migration for
*existing* production DBs (`scripts/migrate_schema_v2.py`, `WorldMeta.schema_version` 1→2) is
scoped out for now — no production deployment exists yet; the dev flow
(`scripts/import_world.py --fresh`) regenerates disposable DBs from YAML instead.

## Sprint 17 — Determinism: seedable RNG & skill-check ✅

**Goal:** All random resolution reproducible so the [Sprint 12](#sprint-12--simulation-harness-mvp-) audit-regression harness can cover
combat/skills/trade. **See [`engine_core.md`](engine_core.md) §3.6, §4b.**

| # | Task | Status |
|---|------|--------|
| 17.1 | Seedable `ctx.rng` service threaded through `GameContext` (per-run seed); lint-ban module-level `random` in feature code | [x] `game/rng.py`'s `GameRng`; one app-wide instance on `AppState` from `Settings.rng_seed`; required `GameContext.rng`/`build_game_context(rng=...)`; `SchedulerEventContext.rng`; `clock/weather.py` converted off `random.choice`. Ruff `TID251` banned-api rule on `random`, scoped to `src/` (test-harness timing jitter exempted). |
| 17.2 | `skill_check(rng, base, difficulty, modifiers) → CheckResult` helper (roll-under d100, 5/95 bounds — one check path for perception/lockpicking/barter/combat) | [x] `game/checks.py`; resolves `effective` via Sprint 18's modifier resolver, clamps target to `[5, 95]`. Landed after Sprint 18 since it needs the `Modifier` type. |

## Sprint 18 — Modifier resolution ✅

**Goal:** One runtime resolver for bonuses from many sources, with a defined stacking order and
caps. Generalizes the doc's `EquipmentEffects.resolve()`. **See [`engine_core.md`](engine_core.md) §3.5, §4d.**

| # | Task | Status |
|---|------|--------|
| 18.1 | Modifier resolver: buckets **flat add → multiplier → clamp/cap**; collects from equipment `effects`, traits, active effects, region; never stored (recompute on change / lazily) | [x] `game/modifiers.py`: `Modifier`/`resolve()` (pure, bucket-ordered) + `ModifierSource`/`ModifierRegistry`/`resolve_for()` (collection). Tier 1 registers no sources — landed ahead of its listed order (18 has no dependencies, per the doc's own build-order table) specifically to unblock Sprint 17.2's `skill_check()`. |

## Sprint 19 — Meters & timed effects ✅

**Goal:** Named bounded clock-tickable resources, and expiring buffs/debuffs — one primitive each,
not one column per resource. **See [`engine_core.md`](engine_core.md) §3.3–3.4.**

| # | Task | Status |
|---|------|--------|
| 19.1 | `Meter` primitive (bounded, optional regen, scheduler tick, `METER_DEPLETED`); migrate `current_hp` (player + NPC) onto it as the proof — `max_hp` stays as the definitional base | [x] `models/meters.py`'s `Meter` + `game/meters.py`'s `MeterDef`/registry + `services/meters.py`'s `MeterService`. "hp" `MeterDef` registered as bootstrap in `main.py`'s lifespan; `PlayerStats.current_hp`/`NPC.current_hp` deleted outright (not deprecated). |
| 19.2 | `ActiveEffect` (clock-driven expiry, swept by scheduler) + trait registry (named boon/bane modifier-bundles) feeding the resolver | [x] `models/meters.py`'s `ActiveEffect` + `game/effects.py`'s `EffectDef`/registry + `services/effects.py`'s `EffectService`; `game/traits.py`'s `TraitDef`/`TraitSource`/registry. Tier 1 registers one `TraitSource` (active effects' `grants_traits`) and two `ModifierSource`s (active-effect, trait) with Sprint 18's resolver — the §3.5 promise fulfilled. |

**Delivered beyond the two checklist items:** full HP-migration blast radius (`world/loader.py`,
`admin/routers/world.py`, `services/save.py` — v1/v2 save-snapshot compat); `GameContext` gained
required `session`/`meters`/`effects` fields (`build_game_context()` factory pattern held); 25 new
invariant tests caught two real bugs (both `_on_time_advanced` sweeps read ORM attributes after
`session.commit()`'s default `expire_on_commit` invalidated them — fixed by capturing plain values
before the session closes). See `CHANGELOG.md` for the full list.

## Sprint 20 — Ledger & atomic transfer ✅

**Goal:** A coin balance on any holder + one atomic multi-party transfer for coins *and* items.
**See [`engine_core.md`](engine_core.md) §3.7, §4c/§4g.**

| # | Task | Status |
|---|------|--------|
| 20.1 | `CoinBalance` on any registered holder (player/bank/corpse/shop); atomic multi-leg `execute_exchange(legs)` — validate all, then apply all (escrow = accept-time revalidation), reusing the [Sprint 14](#sprint-14--unify-command-lifecycle-) rollback; integrity gates via `RuleEngine` (fail-closed), not conditions | [x] `models/ledger.py`'s `CoinBalance` + `services/ledger.py`'s `LedgerService` (stateless-per-call, no engine/rng held). `execute_exchange(legs)` validates every leg first, then applies all mutations — no partial exchange ever lands. `GameContext` gained a required `ledger` field. 14 new tests, all green first run. |

## Sprint 21 — Scheduled moving entity ("moving room") ✅

**Goal:** The moving-room carrier transit rides on; also serves wandering NPCs/patrols later.
**See [`engine_core.md`](engine_core.md) §3.8.**

| # | Task | Status |
|---|------|--------|
| 21.1 | Scheduled moving-room carrier + position-interpolation state machine (`at_stop → in_transit → arrive`, reverse/loop) + position push; line semantics (express/local, tickets, weather) stay Tier 2 ([Sprint 29](#sprint-29--transit--travel-systems)) | [x] `models/mobile.py`'s `MobileRouteState` (only the runtime state is persisted) + `services/mobile_route.py`'s `Waypoint`/`RouteSpec`/`RouteHooks`/`MobileRouteService` (engine-holding schedulable, exactly the `SchedulerService` shape — reuses it for all timing via `job_type="mobile_route"`). Ping-pong reversal and circular looping both covered; a route whose spec disappears on restart halts instead of crashing. 15 new tests, all green first run. |

---

# Feature band (Sprints 22+) — Tier 2 modules & content, gated on foundation exit criteria

**Re-sequenced 2026-07-03** to reflect Lorecraft's design pillars — **Exploration > Trading >
Questing > Puzzle-solving, with combat as a *supporting* system, not the centerpiece** (see
[`wishlist.md`](wishlist.md) → *Design pillars*). The old sequence front-loaded combat
(Sprints 18–20 of the previous plan); the new sequence front-loads the systems those pillars
depend on — item state, inventory/equipment, exploration, traits/skills — and moves combat
below trading/transit/quests as a fallback resolution path rather than the main loop.

Ordering follows dependencies: item state → equipment → traits/skills/exploration → condition
→ trade → transit → quests/puzzles → combat → PvP. UI polish (map, mobile) sits alongside
exploration, which it serves.

> **Engine-first (2026-07-03):** the feature band decomposes into **Tier 1 engine primitives →
> Tier 2 standard modules → Tier 3 content** per [`engine_core.md`](engine_core.md) — the anchor
> doc for the framework/game boundary. Directive: **design Tier 1 now, implement most of Tier 1
> before Tier 2.** Eight cross-cutting primitives (item location/ownership, component state,
> meters, timed effects, modifier resolver, seedable RNG + skill-check, ledger/atomic transfer,
> moving-entity) sit underneath [Sprints 22–35](#sprint-22--standard-item-components--definition-fields); building them per-sprint would yield N opinionated
> implementations and blur the boundary. The two most expensive to retrofit — the unified item
> location/ownership model and a seedable `ctx.rng` (audit-regression-critical) — go first. See
> [`engine_core.md`](engine_core.md) §3 (primitives), §4 (cross-doc surprises caught), §6 (build
> order). The Tier 1 work is now sequenced as **[Sprints 16–21](#sprint-16--item-locationownership--instance-state)** (the Engine core band below); the
> Tier 2 feature band shifts to **[Sprints 22–35](#sprint-22--standard-item-components--definition-fields)**.

> **Design docs:** [`engine_core.md`](engine_core.md) (Tier boundary + Tier 1 primitives — read first),
> [`inventory_equipment.md`](inventory_equipment.md) ([Sprints 22–23](#sprint-22--standard-item-components--definition-fields)),
> [`combat_system.md`](combat_system.md) (stat/skill model + combat sprints),
> [`death_resurrection.md`](death_resurrection.md) (death penalty; combat set aside to [`wishlist.md`](wishlist.md)),
> [`dialogue_npcs_quests.md`](dialogue_npcs_quests.md) and
> [`feature-registration.md`](feature-registration.md) (quests/puzzles, pluggable
> registries), [`transit_systems.md`](transit_systems.md) ([Sprint 29](#sprint-29--transit--travel-systems)), and
> [`trade_economy.md`](trade_economy.md) ([Sprint 28](#sprint-28--trading--economy)). The signature systems now all have
> design docs.

## Sprint 22 — Standard item components & definition fields ✅

**Goal:** *Tier 2 realization* of item content on the [Sprint 16](#sprint-16--item-locationownership--instance-state) engine model — the deferred
Sprint 2.5 `open`/container/state prerequisite. The per-instance carrier, item-location model, and
component registry are **Tier 1 ([Sprint 16](#sprint-16--item-locationownership--instance-state))**; this sprint adds the Layer A `Item` definition
fields and the *standard components* (durability, light, container, openable) on top, so items can
be worn, burned, opened, and puzzle-wired. **See [`engine_core.md`](engine_core.md) §3.1–3.2 and
[`inventory_equipment.md`](inventory_equipment.md) §7.**

| # | Task | Status |
|---|------|--------|
| 22.1 | Layer A item fields (`slot`, `weight`, `wearable`, `quality`, `max_durability`, `light`, `capacity`, `effects`, `bound`) on `Item`; YAML loader + validators | [x] |
| 22.2 | Register durability/`is_open`/`lit`/container as **standard components** on the [Sprint 16](#sprint-16--item-locationownership--instance-state) `ItemInstance`/component model; `open` + state verbs (stateless stackables stay as ID stacks) | [x] |

## Sprint 23 — Inventory & equipment ✅

**Goal:** Wear/wield slots, encumbrance, containers. Equipment grants **non-combat** effects
(light, warmth, carry, skill/trait bonuses) resolved at runtime. **See [`inventory_equipment.md`](inventory_equipment.md) §3–6, §9.**

| # | Task | Status |
|---|------|--------|
| 23.1 | `wear`/`remove`/`wield`/`unwield`/`equipment` commands via `InventoryService`; `ITEM_EQUIPPED`/`ITEM_UNEQUIPPED` events | [x] Equipped-ness is a location (slot on the player's own `ItemStack`), not a `Player.equipment` column — supersedes that earlier draft, per `inventory_equipment.md`'s binding "decided" storage spec |
| 23.2 | Encumbrance bands from weight + `carry_bonus`; equipment effects resolved at runtime (never stored) | [x] `game/equipment_source.py` + `game/encumbrance.py` |
| 23.3 | Containers: `put in` / `take from`, nesting, worn-container capacity; light/darkness gate (`Room.light_level` + lit source) | [x] |

## Sprint 24 — Traits & skills ✅

**Goal:** Character identity that gates exploration and social play. Use-based skills, a trait
registry (boons/banes), reputation/NPC-standing. Builds on existing `PlayerStats` (attributes
+ `skills` dict). **See [`combat_system.md`](combat_system.md) stat model + [`wishlist.md`](wishlist.md).**

| # | Task | Status |
|---|------|--------|
| 24.1 | Trait registry (pluggable, like dialogue side-effects); traits from equipment/background/earned; boon+bane modifiers | [x] `game/standard_traits.py`'s `InnateTraitSource` + 5 illustrative traits; `services/traits.py` grant/revoke |
| 24.2 | Use-based skill improvement (perception, lockpicking, bartering, cartography, survival, persuasion); skill-check helper | [x] `game/skills.py` (identity) + `services/skills.py` (improvement); `skill_check()` itself shipped Sprint 17-18 |
| 24.3 | Reputation/standing per NPC + faction; unlocks dialogue/prices/quests (extends flags + NPC memory) | [x] `models/reputation.py` + `game/reputation_conditions.py` |

## Sprint 25 — Exploration depth ✅

**Goal:** Make discovery a first-class reward (the top pillar). Search-gated secrets, terrain,
journal, cartography. Builds on existing minimap fog and `Exit.hidden`/`condition_flags`.

| # | Task | Status |
|---|------|--------|
| 25.1 | `search` command + hidden-exit/secret-room reveal gated on perception skill + traits + light; discovery rewards (knowledge flags, progression tick) | [x] Also fixed: hidden exits were unconditionally blocked and `condition_flags` was never enforced — both pre-existing bugs |
| 25.2 | Terrain types on rooms/exits affecting travel time, fatigue cost, and required skill/gear; environmental `examine` layering | [x] `Room.terrain` + `game/terrain.py`; required-skill gate + `look` description suffix. Travel-time/fatigue-cost hooks deferred to Sprint 27 (fatigue doesn't exist yet) |
| 25.3 | Journal / auto-log panel (discovered places, met NPCs, learned lore, active clues); player cartography reveal | [x] `journal` command. Cartography map-reveal payoff deferred to Sprint 26 (owns the map UI it reveals onto) |

## Sprint 26 — Map & mobile UI ✅

**Goal:** UI polish that serves exploration (was Sprints 16–17 of the previous plan).

| # | Task | Status |
|---|------|--------|
| 26.1 | Full-screen map modal (pan/zoom), integrated with cartography reveal | [x] `partials/map_modal.html`; drag-to-pan/scroll-to-zoom via Alpine; cartography-gated reveal of known-but-unvisited rooms in `build_map_data()` |
| 26.2 | Responsive mobile tab layout | [x] Bottom tab bar (Room/Feed/Players) below `lg`; verified in a real headless-Chromium browser |

## Sprint 27 — Character condition (fatigue / sleep) ✅

**Goal:** Light survival texture that rewards planning; per-world toggle, not punishing. Runs
on `SchedulerService` + `TIME_ADVANCED`. **See [`wishlist.md`](wishlist.md) → Character condition.**

| # | Task | Status |
|---|------|--------|
| 27.1 | Fatigue/stamina drained by travel/encumbrance/actions; low fatigue penalizes skill checks; `rest`/`sleep`/`camp` | [x] `game/fatigue_source.py`'s "fatigue" `MeterDef` (stamina, scales with fortitude) + `FatigueModifierSource` (flat `mult` penalty on every registered skill once stamina drops below 50%/20% thresholds); `services/fatigue.py`'s `FatigueService` drains on `PLAYER_MOVED` (more when burdened/overloaded per Sprint 23.2 encumbrance bands) and backs `rest`/`camp`/`sleep` (`commands/condition.py`) |
| 27.2 | Sleep advances time + restores fatigue + dream/lore hook; safe vs. unsafe sleep; warmth/exposure via weather + worn clothing | [x] New `Room.safe_rest` field: `sleep` there always succeeds (full restore, 8h clock-advance, dream); elsewhere it's a `survival` `skill_check` (harder in cold weather — `clock/weather.py`'s `COLD_WEATHERS` — offset by resolved `warmth`), failing into a shorter, partial, dreamless "interrupted" rest. `game/warmth.py` + a new `warmth_bonus` item effect (`game/item_effects.py`) give worn clothing a non-combat purpose. Dream flavor references a random `lore:`-flagged discovery (Sprint 25.3) when the player has one. |

## Sprint 28 — Trading & economy ✅

**Goal:** A living economy where *where* you buy/sell matters (pillar #2). Currency → NPC shops
→ regional pricing → banks. **Signature pairing:** the transit network ([Sprint 29](#sprint-29--transit--travel-systems)) is the trade
network. **See [`trade_economy.md`](trade_economy.md).**

| # | Task | Status |
|---|------|--------|
| 28.1 | Currency model (carried `coins`); item `value` × `quality` pricing; NPC vendor shops (`buy`/`sell`/`list`), bartering skill + reputation flex price | [x] New `Shop`/`ShopStock` tables (`models/economy.py`) attached to an NPC via world YAML `shop:` block; a shop's cash is `CoinBalance("shop", shop.id)` (new "shop" holder type, `game/economy_holders.py`), seeded once at import (idempotent re-import guard) via `LedgerService.credit`. `services/economy.py`'s `EconomyService` derives `buy_price = value × quality_mult × region_mult × (1 - barter_discount) × (1 - rep_discount)` and `sell_price = buy_price × sell_ratio` at runtime (never stored); every coin/item movement is one `LedgerService.execute_exchange` call (sold items are `destroy()`ed, not held as physical shop stock — `ShopStock.quantity` is listing state only). `list`/`shop`, `buy`, `sell`, `appraise` commands (`commands/economy.py`). Mira the innkeeper is a working shop in `world_content/world.yaml`. 15 new unit tests + a world-loader round-trip test. |
| 28.2 | Regional price differences + per-good bias + finite stock restocking on the world clock (buy-low/sell-high loop) | [x] New `RegionPricing` table (world YAML `economy.regions`) contributes an area-wide `region_mult` + per-item `bias` on top of a shop's own `region_mult`; `EconomyService._demand_mult()` reads current stock against `restock_to` (depleted costs more, flooded costs less, bounded to [0.5, 1.5]). `services/restock.py`'s `RestockService` (scheduler-driven, same shape as `LightFuelService`) counts `TIME_ADVANCED` ticks per `ShopStock` row and jumps `quantity` to `restock_to` once `restock_every_ticks` elapses. 12 new unit tests + a world-loader region round-trip test. |
| 28.3 | Banks: `BankAccount`, `deposit`/`withdraw`/`balance` at branches, one account/many branches (safe from death & robbery) | [x] New `Bank` (an NPC marker, like `Shop`) + `BankAccount` (identity only — balance is `CoinBalance("bank_account", account.id)`, new holder type). `deposit`/`withdraw` require standing in a branch's room (an `execute_exchange` leg each way); `balance` (carried + banked) works anywhere. One account, many branches — `services/bank.py`'s `BankRepo.get_or_create_account()` lazily creates the single account on first use. Mira's inn also runs a strongbox in `world_content/world.yaml`. 8 new unit tests + a world-loader round-trip test. |
| 28.4 | Player-to-player `offer`/`accept` trade handshake (atomic escrow swap; multi-player transaction safety) | [x] Finished the pre-existing `TradeOffer` placeholder table (never wired to any code — extended with coin fields + `[stack_id, quantity]` pledge lists per side) rather than adding a parallel one. `offer <item\|N coins> to <player>` records a pledge (creates or reuses one open `TradeOffer` between the pair) and moves nothing; `accept` composes exactly one `LedgerService.execute_exchange` with every pledge as a leg — that call's own validation *is* the escrow revalidation (a pledge that's gone since offered raises and nothing moves). Room-presence, `tradeable`/`bound`, and TTL are all re-checked at accept time, not just offer time. Also finished the pre-existing unused `GameEvent.TRADE_COMPLETED`. New `offer`/`accept`/`decline` commands (`commands/trade.py`); added `"offer"` to the parser's `OBJECT_VERBS` (grammar.py) so `offer X to Y` splits roles the same way `give X to Y` does. 7 new unit tests. |

## Sprint 29 — Transit & travel systems ✅

**Goal:** The signature Materia-Magica-inspired feature — multiple travel modes between areas
(ferry, rail, balloon, caravan) that are slow or fast, run end-to-end (express) or make multiple
stops (local), and animate on the minimap. Built on scheduler + world clock + weather + WS push.
**See [`transit_systems.md`](transit_systems.md).**

| # | Task | Status |
|---|------|--------|
| 29.1 | Data model (`TransitLine`/`TransitStop`/`TransitVehicleState`) + YAML `transit:` section + validators; data-driven modes/speeds/stopping patterns | [x] `TransitLine`/`TransitStop` tables (`models/transit.py`) — no `TransitVehicleState` table (superseded per `transit_systems.md` §4: runtime position is the Sprint 21 `MobileRouteState`, keyed `route_id=f"transit:{line_id}"`, wired in Sprint 29.2). World YAML `transit.lines` + validators: stop `room_id`/`ticket_item_id` resolve, `vehicle_room_id` exists with no static exits, sequences contiguous from 0, express lines have ≥2 boarding stops, `blocking_weather` values are real weather states. 12 new unit tests (import/export/reimport round-trip + 5 validator-rejection tests). |
| 29.2 | Scheduler-driven vehicle state machine (at_stop→in_transit→arrive, reverse/loop); moving-room `board`/`disembark`/`schedule`; ticket-item gating | [x] `services/transit.py`'s `TransitService` builds a Sprint 21 `RouteSpec`/`RouteHooks` per `TransitLine` at app lifespan (`load_lines()`) and starts it — no new state machine, entirely the Tier 1 route runner. `may_depart` grounds weather-sensitive lines when `WorldClock.weather` is in `blocking_weather`; `on_depart`/`on_arrive` narrate to both the station and the vehicle room. New `board [line]`/`disembark` (`leave`)/`schedule` (`timetable`) commands (`commands/transit.py`) gate on live vehicle status + stop position, validate/consume tickets, and move the player between the station room and the vehicle room. `register_all_commands` gained an optional `transit=` kwarg (`TransitService` needs the game engine + `ConnectionManager` at construction, so it can't live in the no-arg `ServiceContainer`) — every existing call site is unaffected. 10 new unit tests. |
| 29.3 | `transit_update` WS message + minimap marker animation (interpolated between stop coords); weather grounding/delay (balloon/ferry) | [x] Backend: `TransitService._build_hooks()` implements `on_tick` hook that emits `transit_update` messages with interpolated position, progress, ETA, and mode. `_build_spec()` sets `tick_pushes=5` for lines with `animate_minimap: true`. Weather grounding already works via `may_depart` hook checking `WorldClock.weather`. Frontend: `app.js` adds a `transit_update` handler that receives position/progress data, interpolates between stop coords, and renders a mode-specific emoji icon (⛴/🚂/🎈/🐎) on the minimap SVG using the existing coordinate-scaling system. 9 new unit tests verify message format, hook execution, and tick_pushes configuration. |

## Sprint 30 — Quests & puzzles depth ✅

**Goal:** Branching, consequence-bearing quests and environmental/lore puzzles (pillars #3–4).
Extends the stage/flag quest system with branch conditions and mechanism puzzles.

| # | Task | Status |
|---|------|--------|
| 30.1 | Branch conditions + consequence side-effects on quests (world-state/standing changes); NPC memory of past interactions | [x] Stage `branches` (conditions + `next_stage` + `side_effects`) evaluated once a stage's own `conditions` pass; first branch whose extra conditions pass wins, applying its `side_effects` via the existing `npc/side_effects.py` registry and advancing to `next_stage` (`null` completes the quest). Legacy linear stages (no `branches`) unchanged — full backward compat. New `terminal: true` stage flag completes regardless of array position (a branch target isn't necessarily last in `stages`). Quest conditions moved off a hardcoded if/elif chain onto a new pluggable `game/quest_conditions.py` registry (mirrors `npc/dialogue_conditions.py`). New `NpcMemory` table/repo (`models/npc_memory.py`) + `remember` dialogue side effect + `npc_remembers` dialogue/quest condition: a memory key is scoped per-(player, NPC), so the same key ("helped") means something different for each NPC without pre-naming a flag per pair. `game/reputation_conditions.py` gained `adjust_reputation` (the consequence counterpart to its existing `min_reputation` gate). 16 new unit tests. |
| 30.2 | Mechanism & item-combination puzzles on `ItemInstance.state` (levers, dials, sequences) via pluggable conditions/side-effects; timed clock-driven quest events | [x] New `"mechanism"` standard component (`game/standard_components.py`): `Item.mechanism_states` (ordered list) + `mechanism_side_effects` (keyed by state name, fired once on transition-into via the shared side-effects registry — typically `set_flags`, which `Exit.condition_flags`/dialogue/quest gates already consume, so solving is a one-way trigger). New `turn`/`pull`/`activate` commands cycle state. `Item.combination_side_effects` (checked both directions) makes a successful `use X with Y` apply a real consequence, not just flavor text. New `services/quest_timer.py`'s `QuestTimerService` (engine-holding schedulable, `RestockService`'s shape) sweeps active quest progress on `TIME_ADVANCED`: `timeout_ticks`/`on_timeout` (fallback `next_stage`/`message`/`set_flags`) branches or fails a quest if the player doesn't act in time — data-driven, no per-quest code. New `PlayerQuestProgress.stage_started_epoch` (game-epoch) backs the math; a new `/partials/quest-tracker` route + per-player `state_change` push live-refreshes the one affected player's tracker (quest state is private, not room-broadcast). 26 new unit tests total (mechanism, timer, item-combination, world-schema round-trip/validation). |

## Post-tier-split band (Sprints 31–33) — next up

> **Sequencing note (2026-07-05).** The Tier 1/Tier 2/web split shipped in v0.15.0–0.31.1
> (engine/ is import-pure; 24 feature packages under `features/`; `webui/player` + `webui/admin`;
> the boundary is enforced by `tests/unit/test_tier_boundaries.py`). These three sprints capture
> the remaining tier-split follow-ons plus the highest-value UX/wishlist gaps surfaced along the
> way. **Combat and PvP are set aside to [`wishlist.md`](wishlist.md)** (2026-07-05) — they kept
> forcing roadmap renumbering; ready-to-restore specs live there. See
> [`tier_split_refactor.md`](tier_split_refactor.md).

## Sprint 31 — Finish the tier split: feature-UI seam, toggling & doc refresh ✅

**Goal:** Close out the deliberately-deferred, additive pieces of the tier split and make
feature toggling real. Everything here is non-breaking (the app ships and passes today).
**Complete (v0.31.4–0.32.0)** — the tier split is now fully done (all steps 0–13, see
[`tier_split_refactor.md`](tier_split_refactor.md)).

| # | Task | Status |
|---|------|--------|
| 31.1 | `WebHost` abstraction (tier split step 10c): multi-directory Jinja `ChoiceLoader` + a panel/slot registry, so a feature can contribute templates/panels instead of the single hard-coded template dir | [x] `WebHost` + `Panel` classes; `add_template_dir`/`add_panel`/`add_static`/`add_script` + `build_jinja_environment()`. 9 unit tests. |
| 31.2 | Optional `presentation.py` feature-UI seam (tier split §1c / step 11); prove it by re-homing the existing transit minimap (Sprint 29.3) onto the seam — loads only when the feature *and* the web host are enabled | [x] Feature manifests gain optional `presentation` field (dotted path to module with `register(web_host)`). `webui/player.__init__` loads presentations via `create_web_host()` + `load_feature_presentations()`. Wired into main.py lifespan. Transit feature has `presentation.py` registering minimap panel as proof. Tier boundary test updated to allow web imports in presentation.py. |
| 31.3 | Make Tier 2 feature **services** manifest-gated (today only `economy`/`bank`/`fatigue` are; the rest are built unconditionally in `main.py`/`ServiceContainer`), then add feature enable/disable integration tests (tier split step 12b) | [x] All Tier 2 services now gated (`movement`/`inventory`/`dialogue`/`quest`/`character_info`/`exploration`/`journal`/`trade` + main.py's `light_fuel`/`restock`/`quest_timer`/`transit`); only Tier 1 `save` is unconditional. `register_all_commands` + `main.py` guard every feature. 4 new `test_feature_toggling.py` integration tests. |
| 31.4 | Rewrite the tier-split-stale structure docs beyond the current banners — `architecture.md` §4 tree, `tier_modules.md` tables, `architecture_tiers.md` body → engine/features/webui; graduate §1c "adding feature UI" into `admin_builder_guide.md` (step 13b) | [x] `architecture.md` §4 tree + `tier_modules.md` + `architecture_tiers.md` body rewritten to the shipped layout; new "Extending the UI: Feature Panels" chapter in `admin_builder_guide.md` (+ `LORECRAFT_FEATURES` config row). Tier split fully complete. |

## Sprint 32 — Player onboarding & account UX

**Goal:** Make first contact a real arrival and give players an account-level home for
preferences. From [`wishlist.md`](wishlist.md) (Player Creation / Preferences / Accessibility).
Username + password validation already shipped (v0.31.0); this builds on it.
**Status:** 32.2 (preferences) + 32.3 (accessibility) shipped (v0.33.0–0.34.0); **32.1 deferred**
(2026-07-05, user decision — intro-trigger UX to be revisited).

| # | Task | Status |
|---|------|--------|
| 32.1 | In-game character-creation / intro walkthrough — authored like dialogue/quests (YAML + the dialogue & side-effect registries), **skippable and repeatable**, runs once after first spawn (no in-engine special-casing) | [ ] **Deferred** (2026-07-05): trigger UX (opt-in `tutorial` vs. auto-open-once) is a product choice to settle first; needs a guide NPC + onboarding dialogue tree authored in `world.yaml` + a config-driven first-spawn hook. |
| 32.2 | Per-account **preferences layer** — one settings blob on the account (display density, feed verbosity, panel visibility, timestamp format, reduced-motion for transit/map animation) that the render layer reads in exactly one place | [x] Opaque `Player.preferences` blob (engine-stored, webui-interpreted); `webui/player/preferences.py` owns schema/defaults/validation; `resolve_preferences()` read in one place (`/game` SSR context → `prefs`); `/settings` page to view/update; `hidden_panels` gates game.html panels; `.density-compact`/`.reduced-motion` CSS. 24 tests. |
| 32.3 | **Accessibility mode** — semantic HTML/ARIA, high-contrast / screen-reader-friendly, colourblind-safe palette, real font scaling (a genuine browser-client differentiator; cheap now, costly to retrofit) | [ ] |

## Sprint 33 — Reporting & content-tooling polish ✅

**Goal:** Small, self-contained, combat-independent wins surfaced during the split + wishlist.
**Complete** — guided `/report` (33.1) shipped; the page-length wishlist quick-win (33.2) shipped
(further stretch quick-wins remain optional under 33.2).

| # | Task | Status |
|---|------|--------|
| 33.1 | Guided, multi-turn `/report` flow (category → title → detail) replacing the current one-line note; keep the existing Sprint 10.5 issues pipeline underneath | [x] Bare `report` opens a flag-driven wizard (category→title→detail, `cancel` aborts); web input routes to it via `resolve_command_text` (like dialogue). `report <text>` one-liner unchanged. Same `create_issue()` pipeline underneath. 13 tests. |
| 33.2 | (stretch) Prioritized wishlist quick-wins pulled as scoped — e.g. clickable-link and page-length preferences (feed into the Sprint 32.2 blob), lore/journal surfacing | [x] Page-length quick-win: `feed_page_length` preference (20/40/80) added to the 32.2 blob and driving the `/game` feed load limit + settings select. Further quick-wins (clickable links, lore surfacing) remain open under this stretch item. |

## Sprint 34 — Player-reported command polish ✅

**Goal:** Close the two open player reports in `docs/issues.yaml` — small, self-contained
command wins that improve day-to-day play. Both came in via the in-game `/report` pipeline.
**Complete** — both player reports resolved; no open issues remain.

| # | Task | Status |
|---|------|--------|
| 34.1 | `help <command>` shows detailed help for one command (usage, aliases, scope) instead of always dumping the full list; bare `help` unchanged ([`issue-7502f412`](issues.yaml)) | [x] `help <verb>` shows that command's help text, aliases, and scope; unknown verb reports not-found; bare `help` unchanged. issue-7502f412 resolved. 3 tests. |
| 34.2 | `score` command — a player progress report (level/xp, quest completion, coins/net worth, reputation, discoveries) reading existing stats/quest/economy state; no new persistent schema ([`issue-257c6643`](issues.yaml)) | [x] `score` in the character feature aggregates level/xp, quests (completed/active), wealth (carried + banked), reputation count, discoveries (rooms/NPCs). Reads existing tables only; degrades to zeros. issue-257c6643 resolved. 4 tests. |

---

*Updated 2026-07-07 — archived the **performance & scaling band (35–37)**, **Sprint 39** (timed room effects), **Sprint 45** (chat/feed split; its cosmetic mobile tab-collapse leftover kept as a standalone backlog item), and **Sprints 52–55** (global channels, marks, celestial cycles, context-attached commands) here, clearing the active roadmap. 37.1 + Sprint 38 (scheduler batching / concurrency gate) were deferred to [`wishlist.md`](wishlist.md), not completed.*

*Last updated: 2026-07-05 — **Combat & PvP set aside to [`wishlist.md`](wishlist.md)** (former Sprints 61–64 + the PvP-consent portion of 65) to stop them forcing roadmap renumbering; ready-to-restore specs preserved there. Added the **Performance & scaling band (66–69)** and the `scripts/perf_baseline.py` baseline harness (v0.36.3–0.36.4). Earlier (2026-07-04) — **[Sprint 30](#sprint-30--quests--puzzles-depth-) complete**, closing out every non-combat/PvP Tier 2 sprint (22–30). Branching quests (stage `branches`: conditions + `next_stage` + `side_effects`, backward-compatible with pre-existing linear quests), NPC memory (`models/npc_memory.py`, scoped per-player-per-NPC), a new pluggable `game/quest_conditions.py` registry, mechanism items (levers/dials via a new `"mechanism"` standard component + `turn`/`pull`/`activate` commands), item-combination consequences (`Item.combination_side_effects`), and `services/quest_timer.py`'s `QuestTimerService` (timed clock-driven quest stage deadlines, `RestockService`'s scheduler shape). 26 new tests; full suite (739 unit/integration + 10 e2e + 5 simulation) green. Version bumped to 0.14.0. Sprints 31–35 (combat core, combat commands/UI, combat testing, PvP consent, multiplayer trade/PvP/transit tests) remain — deliberately out of scope for this pass.

Earlier — **[Sprints 20](#sprint-20--ledger--atomic-transfer-) and [21](#sprint-21--scheduled-moving-entity-moving-room-) complete**, closing out the Tier 1 engine-core band. `models/ledger.py`'s `CoinBalance` + `services/ledger.py`'s `LedgerService` add coin balances on any registered holder and one atomic multi-leg `execute_exchange()` for coins and items together (validate-all-then-apply-all, no partial exchange). `models/mobile.py`'s `MobileRouteState` + `services/mobile_route.py`'s `MobileRouteService` add the generic scheduled route runner (ping-pong or circular waypoint cycling, position interpolation, pluggable `RouteHooks`) that transit will ride on — reuses `SchedulerService` for all timing, no second timing mechanism. 29 new tests, all green first run; full suite (538 unit/integration + 3 e2e + 5 simulation) green. Version bumped to 0.3.0. Tier 2 feature band now open, starting at [Sprint 22](#sprint-22--standard-item-components--definition-fields).

Earlier — **[Sprint 19](#sprint-19--meters--timed-effects-) complete**: `models/meters.py`'s `Meter`/`ActiveEffect` + `game/meters.py`/`game/effects.py`/`game/traits.py` registries + `services/meters.py`/`services/effects.py` are the meter, timed-effect, and trait primitives — the "hp" `MeterDef` migration deletes `PlayerStats.current_hp`/`NPC.current_hp` outright as the proof, and Tier 1 registers its promised active-effect/trait `ModifierSource`s + `TraitSource` with Sprint 18's resolver. `GameContext` gained required `session`/`meters`/`effects` fields. 25 new tests caught two real bugs (both scheduler sweeps read expired ORM attributes after `session.commit()`). Full suite (509 unit/integration + 3 e2e + 5 simulation) green.

Earlier same day — **[Sprints 17](#sprint-17--determinism-seedable-rng--skill-check-) and [18](#sprint-18--modifier-resolution-) complete**: `game/rng.py`'s `GameRng` is now the one sanctioned randomness source (ruff `TID251` bans bare `random` in `src/`), threaded through `GameContext`/`build_game_context()`/`SchedulerEventContext`/`clock/weather.py`; `game/modifiers.py`'s `resolve()` is the one stacked-bonus resolver (fixed add→mult→clamp bucket order); `game/checks.py`'s `skill_check()` composes both into the one roll-under-d100 helper every future skill/combat/barter check will share. 18 landed ahead of its listed position (it has no dependencies) specifically to unblock 17.2, which needs the `Modifier` type. 21 new unit tests; full suite green.

Earlier same day — **[Sprint 16](#sprint-16--item-locationownership--instance-state) complete**: `ItemStack`/`ItemInstance` unified item location/ownership model + `ItemLocationService` (spawn/destroy/materialize/move) ships, replacing `Player.inventory`/`RoomItem` outright across the full 17-file blast radius (see `engine_core.md` §3.2's table). `ComponentRegistry`/`HolderRegistry` scaffolded per spec (Tier 1 registers no components, three built-in holder types). 23 new invariant tests; full unit/integration/e2e/simulation suite green unchanged (no audit-event schema drift).

Earlier same day — **Design docs are now implementation-ready** (deep-dive revision for handoff): [`engine_core.md`](engine_core.md) §3 carries full Tier 1 specs (schemas, APIs, invariants, migration blast-radius tables, per-sprint tests); [`combat_system.md`](combat_system.md) rewritten off the pre-Tier-1 code (seeded rng, hp meter, slot-based weapon, real event names); [`inventory_equipment.md`](inventory_equipment.md), [`trade_economy.md`](trade_economy.md), [`transit_systems.md`](transit_systems.md), and [`death_resurrection.md`](death_resurrection.md) aligned to the primitives (superseded drafts called out inline; engine_core §4 lists every resolution). Earlier same day: inserted an engine-first **Tier 1 primitives band ([Sprints 16–21](#sprint-16--item-locationownership--instance-state))** ahead of the feature modules per [`engine_core.md`](engine_core.md), and **renumbered the feature band +6 to [Sprints 22–35](#sprint-22--standard-item-components--definition-fields)** (item components 22, equipment 23, traits/skills 24, exploration 25, map/mobile 26, condition 27, trade 28, transit 29, quests/puzzles 30, combat 31–33, PvP 34, multiplayer tests 35). Sprint refs in the feature design docs + `wishlist.md` were updated to match. Earlier same day: added `engine_core.md` (Tier 1/2/3 boundary); re-sequenced the feature band around design pillars (Exploration > Trading > Questing > Puzzles; combat supporting). [Sprints 4–15](#sprint-4--player-authentication-production-hardening-) complete; foundation gate green.*
