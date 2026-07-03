# Implementation Status

This checklist tracks implementation progress against `docs/architecture.md` phases.
The architecture overview remains the design reference; this file is the working status tracker.

**See [`roadmap.md`](roadmap.md) for the detailed sprint-by-sprint breakdown (Sprints 1–23).**

> **Current focus (2026-07-02):** Foundation-first. The `CODE_AUDIT.md` findings drive
> Sprints 5–15 (errors, types, tests, decomposition, service consistency, extensibility
> seams, tooling). Sprints 5–10 complete (error handling, type safety, characterization
> tests, module decomposition, service consistency/wiring, extensibility seams/patterns).
> Sprint 10.5 (tooling infrastructure: issues/news/world-CLI/analytics/content-linting)
> complete. Sprint 11 (browser E2E harness — Playwright against a live server,
> `tests/e2e/`) complete. Next: Sprint 12 (simulation harness MVP). Combat/trading/PvP
> are gated behind the foundation exit criteria — no feature expansion until the core is
> sound.

## Phase-to-Sprint Mapping

| Architecture Phase | Roadmap Sprints | Status |
|---|---|---|
| Phase 1–3 (Foundation, dispatch, world/time) | Sprint 1 (HTMX parity) | [x] |
| Phase 3.5–4.5 (NPCs, quests, dialogue UI) | Sprint 1–2 | [x] |
| Phase 5–6 (Persistence, admin tools) | Sprint 1–2 | [x] |
| Phase 7 (Auth + frontend polish) | Sprints 4, 15–17 | [ ] |
| Engineering foundation (`CODE_AUDIT.md`) | Sprints 5–15 | [~] Sprints 5–10.5 complete; 11–15 queued |
| Phase 8–8.5 (Combat) | Sprints 18–20 (gated) | [ ] |
| Phase 9 (Player interaction) | Sprints 21–23 (gated) | [ ] |

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
- [~] Multi-player live lists use `ConnectionManager.is_connected()` and `players_in_room()` when WS connected; world clock SSR + WS `time_update` handler added; full clock push from server events still evolving.
- [x] `game/events.py` contains `GameEvent` and synchronous `EventBus`.
- [x] `main.py` FastAPI app.
- [x] `/ws` WebSocket endpoint.
- [x] Startup/shutdown lifecycle wiring.
- [x] WebSocket connect/send/receive integration test.

### Player Identity & Session Safety (Sprint A)

- [x] `web/player_auth.py` — signed JWT player session cookie (`lorecraft_session`, httponly, `samesite=lax`), reusing `admin/auth.py` token primitives with a separate secret and `token_type="player"` so it can never be replayed as an admin token.
- [x] `Settings.player_session_secret` — auto-generated and persisted to `.env` on first real server startup via `config.ensure_persisted_secret()`; ephemeral per-process fallback for tests/router-standalone use (never writes to disk).
- [x] `get_current_player()` prefers the signed cookie; legacy `?player_id=`/unsigned-cookie dev path retained behind `Settings.allow_query_player_id` (default on).
- [x] `POST /lobby/create` — validated username (3-30 chars, `[A-Za-z0-9_-]`), uniqueness check, creates `Player` at `seed_player_start_room`, auto-login.
- [x] `POST /lobby/enter` — verifies the player exists before minting a session; both lobby routes redirect to plain `/game` (no `player_id` in the URL).
- [x] Lobby UI "Create New Character" tab wired to a real form.
- [~] Not a full account system: no password/credential check on `/lobby/enter`, and `/ws?player_id=...` still trusts the raw query param independent of the signed cookie. See backlog in `docs/roadmap.md`.

### Phase 2 — Command Dispatch

- [x] `game/parser.py` converts raw text into `ParsedCommand`.
- [x] Parser supports direction aliases such as `n` to `go north`.
- [x] Parser strips simple articles from nouns.
- [x] `game/registry.py` supports command registration and aliases.
- [~] `game/registry.py` evaluates a first pass of command conditions.
- [x] `game/rules.py` contains `RuleEngine` with ordered rule checks.
- [x] `game/engine.py` contains command dispatch with state commit, audit, and event-flush lifecycle steps.
- [~] Full 13-step transaction/event/audit lifecycle in `handle_command()`.
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
- [x] Analytics API foundation — `lorecraft.analytics` query functions (top commands, NPC interactions, quest completions from the audit log; player-hours from `PlayerSession`) via `GET /admin/analytics/{commands,npcs,quests,player-hours}`. No dashboard yet (by design); latency/event-bus-depth metrics wait on Sprint 13 instrumentation.
- [x] Content validation & linting — `lorecraft.tools.validators`: dangling dialogue node refs, room reachability, dead item refs, duplicate item names per room, oversized item stacks. Wired into `world_cli.py validate --start-room --strict`. Circular quest dependencies not checked — no quest-to-quest dependency field exists in the schema yet.

### Browser E2E Harness (Sprint 11) ✅

- [x] `tests/e2e/conftest.py` — `live_server` fixture boots the real `create_app()` FastAPI app under `uvicorn.Server` on a background thread with a disposable per-test sqlite DB (real `world_content/world.yaml` bootstrap, no test-only fixtures); `browser`/`page` fixtures wrap Playwright (session-scoped Chromium launch, per-test context).
- [x] `tests/e2e/test_gameplay_flows.py` — drives the golden path (create character → move → take item → talk to Mira → dialogue choice starts a quest) through a real browser against `/lobby`, `/game`, `/command`, verifying HTMX OOB swaps of `#room-description`, `#inventory`, `#dialogue-overlay`, `#quest-tracker`.
- [x] Optional `e2e` dependency group (`playwright`) + `pytest.ini_options` marker so `pytest`/`make test` skip the suite by default (`-m "not e2e"`); `make test-e2e` installs the extra, installs the Chromium binary, and runs it explicitly.

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
- [ ] Simulation tests.
