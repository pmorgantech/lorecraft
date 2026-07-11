# Lorecraft — Roadmap

**A concise list of *remaining* work.** Every **completed** sprint — 1–34 (foundation, the Tier 1
engine-core primitives, the Tier 2 pillar feature band, the tier-split follow-ons), the performance
& scaling band (35–37), and everything since (39–55) — lives in
[`roadmap_completed.md`](roadmap_completed.md) with full task-level detail. Per-version detail is in
[`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and the deferred
multiplayer test pass + concurrency/batching gates are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-09, v0.56.0)

**Sprints 56–60, 62, and 66–68 (all tasks, complete) are merged to local `main`.** Everything
through **Sprint 55** was already there. Foundation, the
Tier 1 engine-core primitives, the full Tier 2 pillar feature band
(exploration · trading · questing · puzzles, plus inventory/equipment, traits/skills, character
condition, transit), the tier-split refactor, the performance/WAL band, the observability pair
(56–57), the client themes/layouts band (58–60, including the undocumented-until-now **Sprint 62**
layout/scheme axis split — see its own row below), multi-level map foundation (66), the
webui-theming skill (67), and escort quests (68) have all shipped. See
[`roadmap_completed.md`](roadmap_completed.md).

**Doc-hygiene note (2026-07-09):** this file and [`wishlist.md`](wishlist.md) had drifted from the
shipped code — a sync pass found (a) the "Sprint 62" work below was never logged here despite
shipping in v0.54.0, and (b) `wishlist.md` still framed **Inventory & equipment** (Sprint 23),
**Exploration depth** (Sprint 25), **Travel & transit systems** (Sprint 29), and **Quests &
puzzles** (Sprint 30) as unbuilt "wanted next" pillars when all four fully shipped months ago.
Both fixed in this pass; `wishlist.md`'s dangling `genuine_gaps.md` references (a file that was
never created) were folded inline. Lesson: log sprint numbers into this file *at the time they
ship*, not after the fact — CHANGELOG.md is the accurate source when this file lags.

**Candidate work** also lives in the *Backlog* table below and in [`wishlist.md`](wishlist.md). The
nearest small, well-scoped backlog item is the **`report player <name>` moderation branch** of the
issue-report wizard (the guided flow itself already shipped in Sprint 33.1).

**Sprint 68** (escort quests, complete) extended the shipped `follow` command (Sprint 47) so an
NPC can be the one being followed, gated by new quest-stage conditions, so a quest can fail or
branch if the escorted NPC is lost. **Next new sprint: 69.**

**Set aside to [`wishlist.md`](wishlist.md):** combat & PvP (ready-to-restore specs — a supporting
system, not the centerpiece); the multiplayer trade/transit **test pass**; and the deferred
**scheduler-commit batching (37.1)** + **concurrency/threading gate (38)** — the measured wall was
fsync serialization on a single SQLite writer, which WAL (37.4) already removed, so threads wouldn't
help. Revisit the latter only if a *post-WAL* realistic-load test shows a hard single-process wall.

Design anchors: [`engine_core.md`](engine_core.md) (the Tier 1/2/3 boundary) and
[`wishlist.md`](wishlist.md) (design pillars + idea backlog).

---

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

## Backlog

| Item | Notes |
|------|-------|
| Scripting catalog generator enables features (Phase A tech-debt #2) | `docs/scripting_api.md` is generated after `discover_features()` (import only), so feature-**enable**-time vocabulary (reputation's `actor_reputation_at_least`/`adjust_reputation`, escort, …) is missing from the doc. Fix: have the generator invoke each `FeatureManifest.register_fn` (with a stub/no-op state) after discovery so the catalog reflects the full enabled vocabulary. |
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| Mobile chat tab-collapse polish | Cosmetic leftover from Sprint 45.3 (finished by Sprint 52 otherwise) — on small screens the chat pane should collapse into a tab rather than stack. Purely responsive/CSS. |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| ~~Player-facing bug reports~~ | **Done** — `report` one-liner (v0.12.0) + guided category→title→detail wizard (Sprint 33.1). Only the `report player <name>` moderation branch + an `Issue.target_player_id` field remain — see [`wishlist.md`](wishlist.md) → *Issue-report wizard*. |
| Database inspector / state editor | Admin tool for advanced troubleshooting |
| Multiplayer trade/transit test pass | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Multiplayer sim-test coverage* (was Sprint 65) |
| Combat & PvP | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Combat, reframed* (ready-to-restore specs) |

*Already-implemented items previously listed here (bug/todo letterbox, encumbrance/wear slots, the
simulation CLI, the analytics dashboard) were promoted to shipped sprints — see
[`roadmap_completed.md`](roadmap_completed.md).*

---

## Sprint numbering (avoid duplicates)

- **Used (all complete):** 1–34 (incl. 10.5), 35–37 (performance band; 37.1 deferred to
  [`wishlist.md`](wishlist.md)), 39 (timed room effects), 40–42 (admin console live-refresh,
  registered issue components, Issues-tab filter/sort), 43–49 (session record/playback,
  weather-driven effects, chat/feed split, item discovery journal, follow command, scavenger hunts,
  encumbrance + analytics dashboard), 50 (e2e browser coverage), 51 (four more analytics widgets +
  the `target_id` audit fix), 52 (global channels & the channel framework), 53 (collectible marks),
  54 (celestial cycles), 55 (context-attached commands). Full detail in
  [`roadmap_completed.md`](roadmap_completed.md).
- **Deferred to [`wishlist.md`](wishlist.md):** 37.1 (scheduler-commit batching) and 38
  (concurrency/threading gate) — never developed; fsync, not CPU, was the wall.
- **Used (all complete):** 56 (structured output-type tagging), 57 (request tracing & crash
  reports), 58 (selectable client themes & layouts), 59 (classic old-MUD CRT mode, incl. 59.1–59.8),
  60 (per-mode typography + minimap de-boxing, 60.1–60.2), **62** (layout/scheme axis split,
  Standard+Dock rebuild, full Stats pane — shipped v0.54.0, backfilled to this ledger 2026-07-09;
  see its row under Sprint 59 above), 66 (multi-level map foundation — `map_z`), 67 (webui-theming
  agent skill + `MODE_DEFAULT_THEME` single-sourcing fix), 68 (escort quests).
- **Retired to [`wishlist.md`](wishlist.md):** 61, 63, 64 (combat core, combat commands/UI, combat
  testing, PvP consent — 62 was reclaimed for the unrelated axis-split work above since combat
  stayed shelved), 65 (multiplayer trade/transit tests). Don't reuse 61/63/64/65 for unrelated
  work — restore under fresh numbers if that work returns.
- **In progress:** 69 (scripting-engine world-building polish — 69.1–69.4 shipped v0.71.0–0.72.0;
  69.5–69.7 queued). The Phase A scripting engine itself (v0.57–0.70, branch `scripting_engine`)
  predates this ledger; it is tracked in `docs/scripting_engine_design.md`.
- **Next new sprint: 70.** Don't recycle a number that appears here or in
  [`roadmap_completed.md`](roadmap_completed.md).

---

## Playtesting (Ashmoore dev world)

`start.sh` copies `test_dbs/lorecraft-dev-game.db`, which is built from `world_content/world.yaml`.

Regenerate after world edits:

```bash
python scripts/import_world.py --fresh --db test_dbs/lorecraft-dev-game.db
```

**Starting room:** `village_square` as `player-1`

| Try | Command |
|-----|---------|
| Move east | `go east` → market stalls |
| Pick up coin | `take coin` |
| Talk to Mira | `go west` → Wandering Crow Inn, then `talk mira` |
| Quest hook | Choose "Any news around town?" in dialogue |
| Wear armor | `go north` → forge, `take helmet`, `wear helmet`, `remove helmet` |
| Locked door | `north`→`north`→`east` to Vault Hall; `take good key`, `unlock east`, `go east` → Inner Vault (the Bad Key won't work) |
| Context verb | `go south` past the creek to the Ruined Chapel; `read altar` (reveals lore) |

Empty databases import `world_content/world.yaml` on startup (configurable via `LORECRAFT_WORLD_YAML_PATH`). Integration tests use the same Ashmoore data — no parallel hardcoded world in production code.
