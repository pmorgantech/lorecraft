# Implementation Status

This checklist tracks implementation progress against `docs/ARCHITECTURE.md`.
The architecture overview remains the design reference; this file is the working status tracker.

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

### Phase 1 — Foundation

- [x] `config.py` contains environment-driven settings.
- [x] `models/` SQLModel table definitions.
- [x] `create_tables()` startup database initialization.
- [x] `repos/` data access wrappers.
- [x] `game/context.py` contains `GameContext`.
- [x] `game/transaction.py` contains `TransactionContext`.
- [x] `game/connection_manager.py` contains the WebSocket-style connection pool and room broadcast behavior.

### Web UI (HTMX)

- [x] Jinja2 + HTMX + Alpine server-driven frontend integrated as primary UI (`/lobby`, `/game`, `/command`, partials).
- [x] Command flow with immediate HTML response + OOB + WS push for other players.
- [x] Audit log used as source for narrative feed.
- [~] Full multi-player live lists and world clock push still evolving from core events.
- [x] `game/events.py` contains `GameEvent` and synchronous `EventBus`.
- [x] `main.py` FastAPI app.
- [x] `/ws` WebSocket endpoint.
- [x] Startup/shutdown lifecycle wiring.
- [x] WebSocket connect/send/receive integration test.

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
- [x] `commands/meta.py` with `help` and `quit`.
- [x] `commands/movement.py` with `go` and cardinal directions.
- [x] `services/movement.py` with `MovementService`.
- [x] End-to-end movement test with persistent room change.

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
- [x] Clock/weather/item pickup tests.

### Phase 3.5 — World UI

- [x] Inventory panel.
- [x] Minimap with fog of war.
- [x] Basic layout refinement.
- [x] Browser can show room changes, inventory updates, and visited-room map state.

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
- [ ] Full-screen map modal.
- [ ] Responsive behavior improvements.
- [ ] Browser end-to-end testing.

### Phase 8 — Combat

- [x] Combat models.
- [x] Player stats model.
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
- [x] Connection manager unit tests.
- [x] Database table bootstrap unit tests.
- [x] Repository unit tests.
- [x] Integration tests.
- [ ] Simulation tests.
