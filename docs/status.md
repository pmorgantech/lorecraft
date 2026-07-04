# Implementation Status

This checklist tracks implementation progress against `docs/architecture.md` phases.
The architecture overview remains the design reference; this file is the working status tracker.

**See [`roadmap.md`](roadmap.md) for the detailed sprint-by-sprint breakdown (Sprints 1–35).**

> **Current focus (2026-07-03):** Foundation-first, now including production auth.
> Sprint 4 (player authentication — password login, JWT access/refresh tokens,
> single-use WebSocket tickets, `?player_id=` legacy fallback off by default, OAuth
> extensibility stub) is complete. The `CODE_AUDIT.md` findings also drove Sprints
> 5–15 (errors, types, tests, decomposition, service consistency, extensibility
> seams, tooling, UX completion) — all complete: error handling, type safety,
> characterization tests, module decomposition, service consistency/wiring,
> extensibility seams/patterns, tooling infrastructure (issues/news/world-CLI/
> analytics/content-linting), browser E2E harness (`tests/e2e/`), simulation harness
> MVP (`tests/simulation/`), observability & CI quality gates, unified command
> lifecycle (rollback-on-error, shared `/ws`/`POST /command` room-broadcast step), and
> core UX completion (world clock/weather WS push to all players, multi-player live
> lists refresh on room-leave). **Foundation gate is green.** The post-foundation work was
> **re-sequenced twice on 2026-07-03**: first around design pillars (Exploration > Trading >
> Questing > Puzzles; combat is a supporting system, not the centerpiece), then split into an
> **engine-first Tier 1 primitives band** ahead of the Tier 2 feature modules — see
> [`engine_core.md`](engine_core.md) for the framework/game boundary, [`wishlist.md`](wishlist.md)
> for the pillars, and [`inventory_equipment.md`](inventory_equipment.md) for the item/equipment
> design. All six design docs went through a same-day deep-dive revision and are
> **implementation-ready** — `engine_core.md` §3 holds the binding Tier 1 specs (schemas, APIs,
> invariants, migration blast-radius tables); the feature docs are aligned to them with
> superseded drafts called out inline. **Sprint 16 (item location/ownership + component state)
> is now complete**: `ItemStack`/`ItemInstance` model + `ItemLocationService`
> (spawn/destroy/materialize/move) replaces `Player.inventory`/`RoomItem` outright across the
> full blast radius (inventory/movement/quest/dialogue/save/world-import/admin/web layers); 23
> new invariant tests; full suite green unchanged. **Sprints 17 and 18 are also complete**:
> `game/rng.py`'s `GameRng` (the one sanctioned randomness source, ruff-banned elsewhere in
> `src/`) is threaded through `GameContext`/scheduler/weather; `game/modifiers.py`'s `resolve()`
> is the one stacked-bonus resolver; `game/checks.py`'s `skill_check()` composes both.
> **Sprint 19 is also complete**: `Meter`/`ActiveEffect` primitives (`models/meters.py`) plus
> `MeterService`/`EffectService`/trait registry; the "hp" `MeterDef` migration deletes
> `PlayerStats.current_hp`/`NPC.current_hp` outright. **Sprints 20 and 21 are also complete**,
> closing out the Tier 1 engine-core band: `services/ledger.py`'s `LedgerService` (coin balances
> on any holder + one atomic multi-leg `execute_exchange()` for coins and items together) and
> `services/mobile_route.py`'s `MobileRouteService` (the generic scheduled route runner —
> ping-pong/circular waypoint cycling, position interpolation — that transit will ride on).
> **Sprint 22 (item components & definition fields) is now complete**: `Item` model gains 8
> fields (`slot`, `wearable`, `weight`, `quality`, `max_durability`, `light`, `capacity`,
> `effects`), content validators added for all fields, YAML loader updated (22.1); the standard
> `durability`/`openable`/`lit`/`container` components are registered on Sprint 16's
> `ComponentRegistry`, plus `open`/`close` commands (22.2). **Sprint 23 (inventory & equipment)
> is now complete**: equipped-ness is a location (`slot` on a player-owned `ItemStack`), not a
> column; `wear`/`remove`/`wield`/`unwield`/`equipment` commands, an equip-slot move validator,
> and `ITEM_EQUIPPED`/`ITEM_UNEQUIPPED` events (23.1); equipment-derived modifiers/traits
> (`game/equipment_source.py`) feeding the Tier 1 resolver/trait registry live, plus
> `game/encumbrance.py`'s carry-capacity bands (23.2); `put`/`take from` containers, a
> container move validator (open/capacity/nesting), `light`/`extinguish` commands, a
> lit-source fuel-drain scheduler sweep, and a light-gate that now also checks equipped lit
> sources, not just `Room.light_level` (23.3). Caught and fixed two real bugs along the way:
> `ItemLocationService`'s container-cycle check compared item *type* instead of instance
> (any two same-type containers falsely couldn't nest), and equipped items were invisible to
> open/close/light/extinguish (the lookup only searched loose stacks). **Sprint 24 (traits &
> skills) is now complete**: `game/standard_traits.py`'s `InnateTraitSource` (background/earned
> traits via `PlayerStats.traits`, granted/revoked by `services/traits.py`) completes the
> three-source trait picture (innate + equipment + active-effect); `game/skills.py`'s
> `SkillRegistry` defines skill identity (perception, lockpicking, bartering, cartography,
> survival, persuasion) and `services/skills.py`'s use-based improvement rides on Sprint
> 17–18's existing `skill_check()`; `models/reputation.py`'s `Reputation` table +
> `game/reputation_conditions.py` gate commands/dialogue on NPC/faction standing. New
> `traits`/`skills`/`reputation` player-facing commands. **Sprint 25 (exploration depth) is
> now complete**: `search` command reveals per-player hidden-exit discoveries gated on a
> perception `skill_check()`; `Room.terrain` (data-driven registry) gates/flavors movement;
> `journal` command surfaces visited places, met NPCs, `lore:`-flagged learnings, and active
> quests. Fixed two real pre-existing bugs found along the way: hidden exits were always
> unreachable (contradicting the documented behavior) and `Exit.condition_flags` was never
> enforced despite being round-tripped through YAML. **Sprint 26 (map & mobile UI) is now
> complete**: a full-screen, pan/zoomable map modal (`partials/map_modal.html`) integrated
> with the cartography reveal Sprint 25.3 deferred (rooms one non-hidden exit from anywhere
> visited are plotted, dimmed, once cartography skill crosses a threshold); a responsive
> mobile tab layout (Room/Feed/Players) below the `lg` breakpoint. Verified in a real
> headless-Chromium browser (desktop, modal, all three mobile tabs) plus 3 new e2e tests.
> **Sprint 27.1 (fatigue) is now complete**: a "fatigue" `MeterDef` (remaining stamina,
> scales with fortitude) drains on travel (more when encumbered) and saps skill checks once
> low, via a `FatigueModifierSource` on the Tier 1 modifier resolver; `rest`/`camp`/`sleep`
> commands restore it. Also fixed a real pre-existing bug found while building it:
> `CommandEngine` committed game state *before* flushing post-command events, so
> `QuestService.check_progression`'s quest-stage/flag mutations (triggered by
> `PLAYER_MOVED`/`ITEM_TAKEN`/`ITEM_DROPPED`) were silently discarded once a request's
> session closed — existing unit tests never caught it since they read the same
> still-open session. Sprint 27.2 (sleep clock-advance, safe/unsafe risk, warmth/exposure)
> and the rest of the feature band (trading, transit, quests/puzzles) continue next;
> combat/PvP (Sprints 31–35) are deferred per direction.

## Phase-to-Sprint Mapping

| Architecture Phase | Roadmap Sprints | Status |
|---|---|---|
| Phase 1–3 (Foundation, dispatch, world/time) | Sprint 1 (HTMX parity) | [x] |
| Phase 3.5–4.5 (NPCs, quests, dialogue UI) | Sprint 1–2 | [x] |
| Phase 5–6 (Persistence, admin tools) | Sprint 1–2 | [x] |
| Phase 7 (Auth + frontend polish) | Sprints 4, 26 | [x] Sprint 4 (auth) + Sprint 26 (map/mobile UI) both complete |
| Engineering foundation (`CODE_AUDIT.md`) | Sprints 5–15 | [x] |
| Engine core: Tier 1 primitives (`engine_core.md`) | Sprints 16–21 (gated) | [x] |
| Item state / inventory / equipment | Sprints 22–23 (gated) | [x] |
| Traits/skills, exploration, condition | Sprints 24–27 (gated) | [~] Sprints 24–26 (traits/skills, exploration, map/mobile UI) complete; 27 remains |
| Phase 9 (Trading + transit) | Sprints 28–29 (gated) | [ ] |
| Quests & puzzles depth | Sprint 30 (gated) | [ ] |
| Phase 8–8.5 (Combat, supporting) | Sprints 31–33 (gated) | [ ] |
| PvP + multiplayer tests | Sprints 34–35 (gated) | [ ] |

> **Post-foundation work re-sequenced twice on 2026-07-03:** first around design pillars
> (Exploration > Trading > Questing > Puzzles; combat as a supporting system), then split into
> an engine-first Tier 1 primitives band (Sprints 16–21, see [`engine_core.md`](engine_core.md))
> ahead of the Tier 2 feature band (now Sprints 22–35). Roadmap is authoritative for sequencing;
> the architecture-phase numbers above are historical. See [`roadmap.md`](roadmap.md),
> [`wishlist.md`](wishlist.md), and [`inventory_equipment.md`](inventory_equipment.md).

Legend:
- `[x]` Implemented and covered by focused tests where practical.
- `[~]` Partially scaffolded or intentionally incomplete.
- `[ ]` Not implemented.

## 0.1.0 Status

### Project Layout

- [x] Python package uses `src/lorecraft`.
- [x] pytest is configured to import from `src`.
- [x] Unit, integration, and simulation test directories exist.
- [x] `make test` runs the focused test suite.
- [x] Package version is synchronized in `pyproject.toml` and `src/lorecraft/__init__.py`.
- [x] `CHANGELOG.md` exists and includes the current release entry.
- [x] Graphify wired into the workflow: `make install-hooks` now installs a real `.githooks/post-commit` hook, and a Claude Code `SessionStart` hook (`.claude/hooks/session-start.sh`) refreshes `graphify-out/graph.json`. Both no-op cleanly (exit 0) when the `graphify` binary isn't installed locally.

### Phase 1 — Foundation

- [x] `config.py` contains environment-driven settings (including `LORECRAFT_WORLD_YAML_PATH` and dev player seed vars).
- [x] `models/` SQLModel table definitions.
- [x] `create_tables()` startup database initialization.
- [x] `start.sh --init-dbs-if-missing` initializes missing dev seed game/audit DBs
  from `world_content/` (or `--world-dir`) and audit schema helpers.
- [x] `repos/` data access wrappers.
- [x] `game/context.py` contains `GameContext`.
- [x] `game/transaction.py` contains `TransactionContext`.
- [x] `game/connection_manager.py` contains the WebSocket-style connection pool and room broadcast behavior.

### Web UI (HTMX)

- [x] Jinja2 + HTMX + Alpine server-driven frontend integrated as primary UI (`/lobby`, `/game`, `/command`, partials).
- [x] Command flow with immediate HTML response + OOB + WS push for other players.
- [x] Audit log used as source for narrative feed.
- [x] HTMX `POST /command` executes via `CommandEngine` (movement, inventory, dialogue, quest OOB updates).
- [x] Multi-player live lists use `ConnectionManager.is_connected()` and `players_in_room()` when WS connected; world clock SSR + WS `time_update` handler pushes to all connected players on every `TIME_ADVANCED` tick (Sprint 15.1); `broadcast_command_effects()` now also sends a `players-online` `state_change` to the room a player left, not just the room entered (Sprint 15.2), so occupants of the old room see the departure reflected in the live list.
- [x] `game/events.py` contains `GameEvent` and synchronous `EventBus`.
- [x] `main.py` FastAPI app.
- [x] `/ws` WebSocket endpoint.
- [x] Startup/shutdown lifecycle wiring.
- [x] WebSocket connect/send/receive integration test.

### Player Identity & Session Safety (Sprint A, superseded/completed by Sprint 4)

- [x] `web/player_auth.py` — signed JWT player session cookie (`lorecraft_session`, httponly, `samesite=lax`), reusing `admin/auth.py` token primitives with a separate secret and `token_type="player"` so it can never be replayed as an admin token.
- [x] `Settings.player_session_secret` — auto-generated and persisted to `.env` on first real server startup via `config.ensure_persisted_secret()`; ephemeral per-process fallback for tests/router-standalone use (never writes to disk).
- [x] `get_current_player()` prefers the signed cookie; legacy `?player_id=`/unsigned-cookie dev path retained behind `Settings.allow_query_player_id` (default **off** since Sprint 4).
- [x] `POST /lobby/create` — validated username (3-30 chars, `[A-Za-z0-9_-]`) **and password** (Sprint 4), creates-or-claims a `Player` at `seed_player_start_room`, auto-login.
- [x] `POST /lobby/enter` — verifies username+password (Sprint 4; 404s on unknown username rather than silently creating one) before minting a session; both lobby routes redirect to plain `/game` (no `player_id` in the URL).
- [x] Lobby UI "Log In" and "Create New Character" tabs both wired to real password-protected forms.
- [x] **Sprint 4 (player authentication) closed the remaining gaps:** `POST /auth/login`/`/auth/refresh`/`/auth/ws-ticket` JSON API (15min access / 8hr refresh JWTs, single-use 60s WS tickets); `main.py`'s `/ws` endpoint validates a `?ticket=` handshake instead of trusting a raw `?player_id=`; `allow_query_player_id` now defaults off; `PlayerAuth` table + OAuth extensibility stub (`POST /auth/oauth/{provider}/callback`, 501). See `docs/roadmap.md` Sprint 4 and `docs/player_authentication.md`.

### Phase 2 — Command Dispatch

- [x] `game/parser.py` converts raw text into `ParsedCommand`.
- [x] Parser supports direction aliases such as `n` to `go north`.
- [x] Parser strips simple articles from nouns.
- [x] `game/registry.py` supports command registration and aliases.
- [~] `game/registry.py` evaluates a first pass of command conditions.
- [x] `game/rules.py` contains `RuleEngine` with ordered rule checks.
- [x] `game/engine.py` contains command dispatch with state commit, audit, and event-flush lifecycle steps.
- [x] Full 13-step transaction/event/audit lifecycle in `handle_command()`, shared by both `/ws` and `POST /command` (Sprint 14: `game/broadcast.py`'s `broadcast_command_effects()` for step 12; rollback-on-error in `CommandEngine._execute_parsed` for handler crashes; `GameContext` construction itself now goes through `build_game_context()` at both entry points too).
- [x] Blocked command audit events.
- [x] `commands/meta.py` with `help` (context-aware: dialogue/combat/`disabled_commands`) and `quit`.
- [x] `commands/movement.py` with `go`, cardinal directions, `unlock`/`lock` (persist `Exit.locked`).
- [x] `services/movement.py` with `MovementService`.
- [x] End-to-end movement test with persistent room change.
- [x] Item `aliases` (YAML/model/loader) for parser fuzzy resolution and `ItemRepo` search.
- [x] `use <item> [on/with <other>]` + `InventoryService.use_item()`, wiring `Item.usable_with`.
- [x] `give <item> to <name>` + `InventoryService.give_item()` for NPC hand-offs.

### Phase 2.5 — Minimal Web Client

- [x] Browser WebSocket client.
- [x] Message router.
- [x] Plain JavaScript state object.
- [x] Basic text feed and command input.
- [x] Basic room/status display.
- [x] Browser smoke/end-to-end test.
- [x] Repo-local seed test databases copied by `start.sh` into `/tmp` runtime paths for browser harness startup.
- [x] `start.sh` bootstraps `.venv` and installs Lorecraft editably with admin tooling when needed.

### Phase 3 — World & Time

- [x] `clock/world_clock.py` background clock loop.
- [x] `clock/weather.py` weather and season state machine.
- [x] Inventory commands: `look`, `take`, `drop`, `examine`, `inventory`.
- [x] `services/inventory.py`.
- [x] World YAML loader.
- [x] World YAML validator.
- [x] `world/bootstrap.py` — empty-DB YAML import and configurable dev player seed (replaces hardcoded starter world in `main.py`).
- [x] Clock/weather/item pickup tests.

### Phase 3.5 — World UI

- [x] Inventory panel.
- [x] Minimap with fog of war.
- [x] Basic layout refinement.
- [x] Browser can show room changes, inventory updates, and visited-room map state.
- [x] Inventory command text and panels group duplicate carried items with `[quantity]` prefixes.
- [x] `take`/`drop` quantity, all, and indexed selectors (`2 coin`, `all coin`, `2.coin`).
- [x] Room description groups duplicate visible items with `[quantity]` prefixes.

### Phase 4 — NPCs & Quests

- [x] `npc/dialogue.py` dialogue tree walker.
- [x] `npc/scheduler.py` NPC movement via `HOUR_CHANGED`.
- [x] Social commands: `talk`, `say`, `choice`, `bye`.
- [x] `services/quest.py` — `check_progression` subscribed to `ITEM_TAKEN`, `PLAYER_MOVED`, `ITEM_DROPPED`.
- [x] World YAML extended: `npcs`, `dialogue_trees`, `quests` sections with validation.
- [x] `repos/dialogue_repo.py` and `repos/quest_repo.py`.
- [x] NPC dialogue and quest flag tests (14 new unit tests).
- [x] Starter world seeded with Mira the Innkeeper, dialogue tree, and "Lights in the Square" quest.

### Phase 4.5 — Dialogue UI

- [x] Dialogue overlay — appears with NPC name, node text, and clickable choice buttons.
- [x] Quest tracker panel — live active-quest list with stage descriptions.

### Phase 5 — Persistence & Safety

- [x] `services/save.py`.
- [x] Save/load commands.
- [x] Disconnect grace period handling.
- [x] Reconnect handling.
- [x] System-controlled disconnected-player state.
- [x] Save/disconnect/reconnect/load preservation tests.

### Phase 6 — Admin Tools

#### Backend

- [x] `admin/auth.py` — JWT issue, refresh, verify; role extraction middleware.
- [x] `admin/api.py` — FastAPI admin router; all REST endpoints (players, audit, world, changesets, clock, NPCs).
- [x] `admin/websocket.py` — Admin push WebSocket at `/admin/ws`; live player, audit, clock, and changeset-scan streams.
- [x] `world/versioning.py` — Changeset CRUD, conflict scanner, atomic promotion, rollback.
- [x] `state.py` — `AppState` extracted from `main.py`; shared by admin router and WS endpoint.
- [x] `models/admin.py` — `AdminUser` table with role and revocation fields.
- [x] `config.py` — Admin JWT secret, TTLs, and seed admin env vars.
- [x] `main.py` — Mounts admin router and WS; seeds `AdminUser`; pushes events to `AdminBroadcaster`.

#### Textual TUI client (`admin/tui/`)

- [x] `admin/tui/app.py` — Textual app skeleton with `F1`–`F5` screen router and JWT credential bootstrap.
- [x] Players screen (`F1`) — `DataTable` of live players; teleport, freeze, message actions.
- [x] Audit screen (`F2`) — `RichLog` tailing WS push; `/` filter bar; `r` session replay.
- [x] World screen (`F3`) — Room `ListView` + field editor; `Ctrl+S` save with optimistic-lock conflict display.
- [x] Changesets screen (`F4`) — Create, scan, promote workflow; inline conflict list.
- [x] Clock screen (`F5`) — Live WS-fed readout; pause/resume, time-ratio, weather override.
- [x] Credential storage at `~/.config/lorecraft-admin/credentials.json` (mode `0600`); silent refresh.

#### Admin web panel (`src/lorecraft/web/admin/`)

- [x] `admin/index.html` — Login screen; JWT stored in `sessionStorage`; tab panel with live WS push.
- [x] Dashboard panel — Live player table with WS push; auto-refresh.
- [x] Player detail panel — Full state view; moderator actions (teleport, flag edit, freeze, message).
- [x] Audit log panel — Paginated table with filter bar; row-expand payload; correlation-ID session replay link.
- [x] World editor panel — Room search list + inline form editor with optimistic-lock; item and NPC sub-tabs.
- [x] Changesets panel — Status badges; scan → conflict list; promote button gated on `READY`.
- [x] Clock control panel — Live readout via WS push; pause/resume, time-ratio slider, weather dropdown.
- [x] Admin accounts panel — User list; create/revoke; role assignment (superadmin only).

#### Tests

- [x] `admin/auth.py` unit tests — JWT round-trip, expiry, role extraction, invalid-token rejection (14 tests).
- [x] Admin API integration tests — Authenticated requests for player list, teleport, flag edit, freeze, audit filter, room edit, role enforcement, clock, seed admin (16 tests).
- [x] Admin changeset promotion tests — Draft → scan → ready → live lifecycle; conflict detection on broken exits and displaced players (9 tests).
- [~] Admin WebSocket integration tests — Not yet covered; WS endpoint wired and manually tested via web panel.

### Phase 7 — Frontend Polish

- [x] Admin login box visibility fixed (inline `display:flex` no longer fights CSS class toggle — JS controls display directly).
- [x] Admin panel full-height layout (`height:100vh; display:flex; flex-direction:column`) — no viewport scroll needed.
- [x] Admin tab routing hardened (data-tab attributes, `classList.toggle` — no `event.target` fragility).
- [x] Admin login: Enter-key support on username/password inputs.
- [x] Admin WS live indicator (● ws dot turns phosphor green when connected).
- [x] Admin TUI black screen fixed (`pop_screen` → `push_screen("players")` after login).
- [x] Admin TUI login centering fixed (`LoginScreen { align: center middle; }` CSS rule).
- [x] Admin TUI `import urllib.parse` moved to module top.
- [x] Minimap section `overflow-hidden` added — child borders no longer bleed through rounded corners.
- [x] `quit` command now closes the WebSocket (`disconnect: true` update handled in `app.js`).
- [x] Disconnect button added — appears when connected, hides when offline.
- [x] Player ID input disabled while connected (prevents mid-session reconnect confusion).
- [x] HTMX `POST /command` executes via `CommandEngine`; dialogue overlay and quest tracker ported from vanilla client.
- [ ] Full-screen map modal.
- [ ] Responsive behavior improvements.
- [x] Browser end-to-end testing — see Sprint 11 below (`tests/e2e/`, Playwright).

### Tooling & Admin Infrastructure (Sprint 10.5) ✅

**See:** [`tooling_infrastructure.md`](tooling_infrastructure.md) for full design.

- [x] Issue tracking system — `docs/issues.yaml` (YAML↔DB sync via `lorecraft.content.issues`), `GET/POST/PUT /admin/issues`, admin TUI F6, web panel Issues tab
- [x] News & announcements — `docs/news.yaml`, in-game `news` command, unauthenticated `/api/news` (JSON) + `/api/news/feed` (RSS 2.0), admin CRUD, TUI F7, web panel News tab
- [x] World management CLI — `python -m lorecraft.tools.world_cli {import,export,validate,diff,merge,stats}`; `export_world_document()` in `world/loader.py`
- [x] Analytics API foundation — `lorecraft.analytics` query functions (top commands, NPC interactions, quest completions from the audit log; player-hours from `PlayerSession`; command latency percentiles from Sprint 13 instrumentation) via `GET /admin/analytics/{commands,npcs,quests,player-hours,latency}`. No dashboard yet (by design).
- [x] Content validation & linting — `lorecraft.tools.validators`: dangling dialogue node refs, room reachability, dead item refs, duplicate item names per room, oversized item stacks. Wired into `world_cli.py validate --start-room --strict`. Circular quest dependencies not checked — no quest-to-quest dependency field exists in the schema yet.

### Browser E2E Harness (Sprint 11) ✅

- [x] `tests/e2e/conftest.py` — `live_server` fixture boots the real `create_app()` FastAPI app under `uvicorn.Server` on a background thread with a disposable per-test sqlite DB (real `world_content/world.yaml` bootstrap, no test-only fixtures); `browser`/`page` fixtures wrap Playwright (session-scoped Chromium launch, per-test context).
- [x] `tests/e2e/test_gameplay_flows.py` — drives the golden path (create character → move → take item → talk to Mira → dialogue choice starts a quest) through a real browser against `/lobby`, `/game`, `/command`, verifying HTMX OOB swaps of `#room-description`, `#inventory`, `#dialogue-overlay`, `#quest-tracker`.
- [x] Optional `e2e` dependency group (`playwright`) + `pytest.ini_options` marker so `pytest`/`make test` skip the suite by default (`-m "not e2e"`); `make test-e2e` installs the extra, installs the Chromium binary, and runs it explicitly.

### Simulation Harness (Sprint 12) ✅

- [x] `tests/simulation/virtual_player.py` — `VirtualPlayer` wraps a real `websockets` client connection to `/ws` (the actual wire protocol, not an ASGI-transport shortcut); `send_command()` sends one command and returns its `command_result` reply, skipping any interleaved broadcasts; `run_script()` sends a list of commands with optional random timing jitter; `wait_for_broadcast()` blocks for a pushed (non-reply) message of a given type.
- [x] `tests/simulation/conftest.py` — `simulation_server`/`simulation_server_factory` fixtures boot the real `create_app()` app under `uvicorn.Server` on a background thread with a disposable per-test sqlite DB and the real `world_content/world.yaml` (same pattern as `tests/e2e/conftest.py`'s `live_server`); `SimulationServer` also exposes direct DB helpers (`create_player`, `player_inventory`, `audit_trail_for`) for scenario setup/assertions.
- [x] `tests/simulation/test_multiplayer_scenarios.py` — two real concurrent connections: `player_joined` broadcasts to an already-connected player when a second player connects; concurrent `take` of a single-quantity item resolves to exactly one winner with no duplication or loss; a moving player's departure narration and a `state_change` nudge reach other room occupants over the raw `/ws` protocol (Sprint 14 fix, see below).
- [x] `tests/simulation/test_audit_regression.py` — runs a fixed command script against two independent fresh servers and asserts the normalized audit trail (event type, summary, target, room, severity — excluding run-specific IDs/timestamps) is identical, per the "capture, diff after changes" pattern in `architecture.md` §25.
- [x] New `simulation` pytest marker, excluded from `pytest`/`make test` by default (`-m "not simulation"`); `make test-simulation` runs it explicitly. No new install required — `websockets`/`httpx` were already transitive dependencies of `fastapi[standard]`, now declared explicitly in the `dev` extra.
- Known gap surfaced by this sprint's tests (fixed in Sprint 14, see below): the raw `/ws` command loop didn't re-broadcast `room_messages` to other room occupants the way `POST /command` does.

### Observability & CI Quality Gates (Sprint 13) ✅

- [x] `observability.py` — `configure_logging()` attaches a correlation-aware `Formatter`/`Filter` pair to the root logger (idempotent; level from new `Settings.log_level`/`LORECRAFT_LOG_LEVEL` env var, default `INFO`); `bind_transaction_context()` publishes a `TransactionContext`'s `transaction_id`/`correlation_id` to a `contextvars.ContextVar` for the duration of one command, so every `log.*` call in the resulting call stack (services, event handlers, repos) picks the IDs up automatically without threading them through signatures. Wired into `create_app()` and both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`).
- [x] `game/engine.py`'s `CommandEngine._execute_parsed` times each command handler invocation and stamps `duration_ms` onto the `COMMAND_EXECUTED` audit event payload; also logs `command_executed verb=... duration_ms=...` at INFO.
- [x] `game/events.py`'s `EventBus.emit()` times each handler dispatch, records it on a new `HandlerResult.duration_ms` field, and logs `event=... handler=... duration_ms=... depth=<handlers registered for this event type>` at DEBUG.
- [x] `analytics.command_latency_percentiles()` — p50/p95/p99 command latency (ms) computed from `duration_ms` on `COMMAND_EXECUTED` audit events; exposed via `GET /admin/analytics/latency`.
- [x] `.github/workflows/ci.yml` — three required jobs on push/PR to `main`: `quality` (`make lint` → `ruff check` + `ruff format --check`; `make typecheck` → `basedpyright`; `make test-cov` → default suite + coverage gate), `simulation` (`make test-simulation`), `e2e` (Playwright install + `pytest tests/e2e -m e2e`). New `pytest-cov` dev dependency; `[tool.coverage.report] fail_under = 80` in `pyproject.toml` (baseline ~82%).
- [x] Fixed a latent bug surfaced while dry-running the CI commands locally: `tests/simulation/*.py` imports `tests.simulation.conftest`, which only resolved under `python -m pytest` (prepends the repo root to `sys.path`) — bare `pytest` (what `make test-simulation` and CI actually invoke) failed with `ModuleNotFoundError`. Fixed by adding `"."` to `pythonpath` in `[tool.pytest.ini_options]`.

### Unify Command Lifecycle (Sprint 14) ✅

- [x] Rollback-on-error — `CommandEngine._execute_parsed` (`game/engine.py`) catches exceptions from the command handler call instead of letting them propagate uncaught. On a crash: `GameContext.rollback_state_changes()` (new `rollback_state` callable, wired at both entry points to the DB session's `.rollback`) undoes any half-applied game-DB state; `ctx.messages`/`room_messages`/`updates`/`pending_events` are cleared (architecture.md §26's golden rule: never tell clients something happened until the database says it happened); a generic error message replaces them; a new `GameEvent.COMMAND_FAILED` audit event (severity `ERROR`) records the crash on the (separate, still-committing) audit DB.
- [x] Broadcast unification — new `game/broadcast.py`'s `broadcast_command_effects()` is the one place step 12 of the lifecycle (room broadcast) now lives. Both `main.py`'s `/ws` command loop (now `async`, awaited at its one call site) and `web/frontend.py`'s `POST /command` call it after `CommandEngine.handle_command()` returns, closing the gap Sprint 12's simulation tests surfaced: the raw `/ws` path previously never re-broadcast a command's `ctx.room_messages` narration or a `state_change` nudge to other WS-connected room occupants. `web/frontend.py`'s previous inline copy of this logic was deleted outright in favor of the shared function.
- [x] Verified with a new simulation test (`test_command_room_messages_broadcast_to_other_ws_players`) exercising the previously-broken `/ws` broadcast path over a real socket, plus the full existing unit/integration/e2e/simulation suite (behavior preserved exactly for `POST /command`).
- [x] `GameContext` construction unification — `build_game_context()` (Sprint 6.3, previously unused by both real entry points) now accepts `audit_session` (a separate `Session`, matching real production usage — replacing the old same-session `create_audit_repo` bool) and `rollback_state`, and passes `clock` straight through instead of synthesizing a fallback `WorldClock`. `main.py` and `web/frontend.py` both call it instead of constructing `GameContext` inline; both now build zero repos by hand for `ctx`.

### Item Location/Ownership & Instance State (Sprint 16) ✅

**See:** [`engine_core.md`](engine_core.md) §3.1–3.2 for the binding spec.

- [x] `ItemStack` model (`models/items.py`) — `(item_id, owner_type, owner_id, slot?, quantity, instance_id?)`; **replaces** `Player.inventory: list[str]` and the `RoomItem` table outright (both deleted, not deprecated).
- [x] `ItemInstance` model — identity + per-component `state: JsonObject`; a `ComponentRegistry` (`game/components.py`) lets Tier 2/world authors register components (durability, openable, lit, container — Sprint 22) with zero core edits. Tier 1 registers none.
- [x] `HolderRegistry` (`game/holders.py`) — built-in holder types `player`/`room`/`container`; `register_move_validator()` hook for mechanical-capacity checks (slot occupancy, container fullness), none registered yet.
- [x] `ItemLocationService` (`services/item_location.py`) — `spawn()`/`destroy()`/`materialize()`/`move()`. `move()` is the one atomic primitive: validates source quantity, destination holder existence, registered validators, and container-cycle freedom, then splits/merges as needed, all-or-nothing within the caller's transaction.
- [x] Full 17-file blast-radius migration onto the primitive: `services/inventory.py`, `repos/item_repo.py`, `game/context.py`, `game/command_conditions.py`, `services/movement.py`, `services/quest.py`, `npc/side_effects.py`, `services/save.py` (v1-save-compatible on load), `world/loader.py`, `world/versioning.py`, `tools/world_cli.py`, `scripts/import_world.py`, `admin/routers/players.py`, `main.py`, `web/session.py`, `web/frontend.py`.
- [x] `Item.bound: bool` field added (data only; enforcement is Tier 2 policy).
- [x] 23 new invariant unit tests (`tests/unit/test_item_location_service.py`); full existing suite (431 unit/integration + 3 e2e + 5 simulation) green unchanged, including the audit-regression diff and the concurrent-take-no-duplication guarantee — no audit-event schema/ordering drift from this migration.
- [x] Bugs caught and fixed during implementation: typed-error constructor argument order backwards in `ItemLocationService`; `StackRepo.delete_stack()` missing a flush (a stack destroyed to zero was still visible to a same-transaction lookup); a pydantic recursion bug where a bare `list[JsonValue]` SQLModel field type infinite-loops in forward-ref resolution (`SaveSlot.inventory` is typed `list[Any]` instead).
- [ ] Not done: `scripts/migrate_schema_v2.py` one-shot migration for *existing* production DBs, and the `WorldMeta.schema_version` 1→2 bump — scoped out since no production deployment exists yet; the dev flow (`scripts/import_world.py --fresh`) regenerates disposable DBs from YAML instead.

### Determinism: Seedable RNG, Modifier Resolution & Skill-Check (Sprints 17–18) ✅

**See:** [`engine_core.md`](engine_core.md) §3.5–3.6 for the binding spec.

- [x] `GameRng` (`game/rng.py`) — the one sanctioned randomness source in `src/lorecraft`; deterministic when seeded (`randint`/`uniform`/`choice`/`chance`). New ruff `TID251` banned-api rule forbids bare `import random` in `src/` (test-harness timing jitter in `tests/simulation/` is exempted via per-file-ignores — it's not game logic).
- [x] One app-wide `GameRng` instance, constructed in `main.py`'s lifespan from new `Settings.rng_seed` (env `LORECRAFT_RNG_SEED`, default `None` = OS entropy), stored on `AppState`. `GameContext.rng` and `build_game_context(rng=...)` are both required; `SchedulerEventContext.rng` threads it into scheduler-driven work. `clock/weather.py` (previously the only `random` user) now requires an injected `rng` instead of defaulting to `random.choice`.
- [x] `game/modifiers.py` — `Modifier`/`resolve()`: fixed bucket order (add → mult → clamp_max/clamp_min), commutative within each bucket, never stored/cached. `ModifierSource`/`ModifierRegistry`/`resolve_for()` for collection; Tier 1 registers no sources (active-effect/trait sources land with Sprint 19, equipment/terrain with Sprint 23+).
- [x] `game/checks.py`'s `skill_check(rng, *, base, difficulty, modifiers, key)` — roll-under-d100, target clamped to `[5, 95]` (no impossible checks, no sure things); one resolution path for perception/lockpicking/bartering/combat-to-hit. Skill *identity* stays Tier 2 (Sprint 24).
- [x] 21 new unit tests (9 `GameRng`, 12 `modifiers` including the spec's worked example, 9 `skill_check`); full suite green throughout, including the audit-regression diff and concurrent-take guarantee.
- Note: Sprint 18 (modifiers) was implemented before Sprint 17.2 (`skill_check`) despite the roadmap's numbering, because `skill_check()`'s signature needs the `Modifier` type — the roadmap's own dependency table already says 18 has no dependencies and could land in either order.

### Meters, Timed Effects & Traits (Sprint 19) ✅

**See:** [`engine_core.md`](engine_core.md) §3.3–3.4 for the binding spec.

- [x] `Meter` (`models/meters.py`) — named bounded resource, one row per `(entity_type, entity_id, key)`, instead of one column per resource. `game/meters.py`'s `MeterDef`/`MeterRegistry` (key, `base_maximum`, `regen_per_tick`, `start_full`); `services/meters.py`'s `MeterService` — `get()` creates lazily, `adjust()`/`set_current()`/`recompute_maximum()` are stateless per-call (caller's `Session`); `_on_time_advanced()` is a scheduler-driven regen sweep with its own session, emitting `METER_DEPLETED`/`METER_RECOVERED` directly since no `ctx` exists in that path.
- [x] `ActiveEffect` (`models/meters.py`) — clock-driven buff/debuff, distinct from equipment (lasts while equipped) and traits (semi-permanent). `game/effects.py`'s `EffectDef`/`EffectRegistry`; `services/effects.py`'s `EffectService` — `apply()`/`remove()`/`active_for()` stateless per-call; `_on_time_advanced()` sweeps expired rows, emits `EFFECT_EXPIRED`.
- [x] `game/traits.py`'s `TraitDef`/`TraitSource`/`TraitRegistry` — named boon/bane modifier-bundles. Tier 1 ships exactly one `TraitSource` (`ActiveEffectTraitSource`, sourcing from effects' `grants_traits`) and registers both an `ActiveEffectModifierSource` and a `TraitModifierSource` with Sprint 18's `ModifierRegistry` — the "Tier 1 registers the active-effect and trait sources" §3.5 promise, fulfilled. `PlayerStats.traits: list[str]` column added (empty by default; Tier 2 populates it).
- [x] HP migration (the proof-of-primitive): `PlayerStats.current_hp` and `NPC.current_hp` deleted outright — `max_hp` stays as the definitional base fed to the "hp" `MeterDef`'s `base_maximum`, registered as bootstrap in `main.py`'s lifespan. Full blast radius: `world/loader.py` (NPC seeding no longer sets `current_hp` — lazy creation handles it), `admin/routers/world.py` (NPC listing does a read-only `MeterRepo` lookup, falling back to `max_hp` for an as-yet-uncreated meter rather than triggering a write from a GET), `services/save.py` (`stats_snapshot` drops `current_hp`, gains a `"meters": {"hp": ...}` dict; loading converts both the new shape and the old v1 flat `"current_hp"` key).
- [x] `GameContext` gains required `session`/`meters`/`effects` fields; `build_game_context()` gains required `meters`/`effects` keywords (both entry points + every test fixture updated, matching the Sprint 16/17 "factory is the single construction path" precedent). `AppState` gains `meters`/`effects`; new `web/session.py` `get_meters()`/`get_effects()` accessors mirror `get_rng()`'s app-state-with-fallback shape. New `GameEvent` members: `METER_DEPLETED`, `METER_RECOVERED`, `EFFECT_APPLIED`, `EFFECT_EXPIRED`, `EFFECT_REMOVED`.
- [x] 25 new invariant tests; caught two real bugs (both `_on_time_advanced` sweeps read ORM attributes on `Meter`/`ActiveEffect` rows *after* `session.commit()`'s default `expire_on_commit` invalidated them and the session closed — fixed by capturing plain `(str, str, str)` tuples before the session block exits). Full suite (509 unit/integration + 3 e2e + 5 simulation) green.

### Ledger & Atomic Transfer (Sprint 20) ✅

**See:** [`engine_core.md`](engine_core.md) §3.7 for the binding spec.

- [x] `CoinBalance` (`models/ledger.py`) — one row per `(holder_type, holder_id)`, on any holder registered with Sprint 16's `HolderRegistry` (player/bank/corpse/shop). No `Player.coins` column.
- [x] `services/ledger.py`'s `LedgerService` — stateless per-call (every method takes the caller's `Session` explicitly, no engine/rng held; there's no scheduler sweep for this primitive). `balance_of()`/`credit()` (the only way coins enter play) plus `execute_exchange(legs)`: validates every leg first (coin sufficiency, destination holder existence, stack presence/quantity at the declared location), then applies every leg's mutations — nothing partial ever lands. Reuses Sprint 16's `ItemLocationService.move()` for the stack legs.
- [x] `GameContext` gains a required `ledger` field; `build_game_context()` constructs a fresh `LedgerService()` (no engine/rng dependency, so no new required kwarg — a smaller blast radius than Sprint 19's `meters`/`effects`).
- [x] 14 new tests, including a two-way P2P-trade-shaped exchange (coin conservation across both directions) and an atomicity test (a failing second leg leaves the first leg's mutation un-applied). All green first run — no bugs caught, unlike Sprints 16/19.

### Scheduled Mobile Entity ("moving room") (Sprint 21) ✅

**See:** [`engine_core.md`](engine_core.md) §3.8 for the binding spec.

- [x] `models/mobile.py`'s `MobileRouteState` — the only persisted piece (`route_id` PK, `status`, `current_index`/`next_index`, `direction`, `depart_epoch`/`arrive_epoch`). Route *specs* (`Waypoint`/`RouteSpec` in `services/mobile_route.py`) are pure in-memory dataclasses supplied by the owning feature at lifespan — Tier 1 never persists them.
- [x] `services/mobile_route.py`'s `MobileRouteService` — engine-holding schedulable, exactly the `SchedulerService` shape; `register(bus)` listens for `SCHEDULED_JOB_DUE` with `job_type="mobile_route"`. `add_route()`/`start()`/`halt()`/`resume()` plus pure `progress()`/`position()` for minimap interpolation. All timing reuses the existing `SchedulerService` (`job_type="mobile_route"`, actions `depart`/`arrive`/`tick`) — no second timing mechanism.
- [x] State machine: `at_stop` --(dwell elapses, `RouteHooks.may_depart` → `None`)--> `in_transit` --(arrive job)--> `at_stop` at the next waypoint, with index/direction advancing via reverse-at-ends (`reverses=True`, the default) or loop-wraparound (`reverses=False, loop=True`). A `may_depart` halt reason parks the route (`status="halted"`) and reschedules a re-check after `dwell_ticks`; `resume()` forces an immediate re-check. `on_tick` fires `tick_pushes` times per segment with interpolated progress — throttled by design, never per world-tick; Tier 1 pushes nothing to clients itself.
- [x] A route whose spec/hooks disappear on restart (owning feature didn't re-`add_route()` before a pending job fires) halts instead of crashing.
- [x] `AppState` gains a `mobile_routes: MobileRouteService` field; wired into `main.py`'s lifespan alongside the scheduler/meter/effect services.
- [x] 15 new tests covering the full ping-pong round trip, circular looping, halt/resume, tick-push interpolation, and the spec-disappeared-on-restart path. All green first run.

### Phase 8 — Combat

- [x] Combat models.
- [x] Player stats model.
- [x] `services/scheduler.py` — DB-backed `ScheduledJob` table; `SchedulerService.schedule()`/`cancel()`; dispatches due jobs as `GameEvent.SCHEDULED_JOB_DUE` on every `TIME_ADVANCED` tick. The scheduling primitive combat (and NPC/world delayed effects) will run on.
- [ ] `services/combat.py`.
- [ ] `npc/combat_ai.py`.
- [ ] Combat commands: `attack`, `flee`.
- [ ] Combat resolution tests.

### Phase 8.5 — Combat UI

- [ ] Combat message styling.
- [ ] Combat status display.
- [ ] Combat browser update test.

### Phase 9 — Player Interaction

- [ ] `services/trading.py`.
- [ ] Trade commands.
- [ ] PvP challenge and accept commands.
- [ ] PvP consent system.
- [ ] Multi-player trade and PvP consent tests.

## Current Test Coverage

- [x] Parser unit tests.
- [x] Rule engine unit tests.
- [x] Event bus unit tests.
- [x] Game context unit tests.
- [x] Command registry unit tests.
- [x] Command engine dispatch unit tests.
- [~] Connection manager unit tests — `is_connected()` covered; prior async room/broadcast tests removed pending rewrite.
- [x] HTMX command dispatch integration tests (`test_frontend_command.py`).
- [x] World bootstrap unit tests (`test_world_bootstrap.py`).
- [x] Database table bootstrap unit tests.
- [x] Repository unit tests.
- [x] Integration tests.
- [x] Player authentication tests (Sprint 4) — `test_player_authentication.py` (15 tests: login create/verify/wrong-password, refresh rotation + expired/garbage/wrong-type rejection, ws-ticket issuance via bearer/cookie + single-use + TTL expiry + expired-access-token rejection, OAuth stub) + `test_player_login.py` (9 unit tests for `login_or_register()`/token issuance) + updated `test_player_session.py` for the password-protected lobby.
- [x] Simulation tests — `tests/simulation/` (Sprint 12): real WebSocket clients (`VirtualPlayer`) against a real live server; multi-player broadcast fan-out, concurrent-access contention over shared world state, and audit-log regression diffing. Excluded from the default run (`-m "not simulation"`), invoked via `make test-simulation`.
