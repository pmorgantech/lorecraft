# Changelog

All notable changes to Lorecraft will be documented in this file.

## [Unreleased]

### Added (Web UI refresh)

- Replaced the primary player web UI with the HTMX + Alpine.js + Jinja2 server-rendered template (lorecraft_frontend_starter).
- Added `src/lorecraft/web/frontend.py` — lobby, game screen, command POST (with OOB updates), and all partial endpoints (`/partials/*`).
- Added `templates/` (base, game, lobby, partials for feed/room/inventory/minimap/players) and `static/css+js`.
- Wired Jinja2Templates + StaticFiles mount in `main.py`; root `/` now redirects to new lobby.
- Lobby provides player selector using existing seeded players; game screen SSRs panels using real repos + audit log for feed.
- `/command` executes via core CommandEngine/GameContext, returns feed items + OOB swaps for changed panels, and broadcasts `state_change` via ConnectionManager.
- Added `recent_for_room` / `recent_for_actor` + `get_exits_with_names` + `list_all` helpers to support the UI.
- Old vanilla client assets preserved under `/static` (flat) for backward compat during transition.
- Command processing, feed (audit-backed), movement, inventory, and minimap exits now work via the new UI.

### Added (Phase 4 — NPCs & Quests)

- Added `models/dialogue.py` — `DialogueTree` SQLModel table storing full dialogue tree as a JSON blob.
- Added `repos/dialogue_repo.py` and `repos/quest_repo.py` — data access for dialogue trees and quest progress.
- Added `npc/dialogue.py` — `DialogueService` with `start`, `choose`, and `end` methods; flag-gated choices; side effects (`set_flags`, `clear_flags`, `give_item`, `start_quest`, `end_dialogue`); dialogue state stored in `player.flags`.
- Added `npc/scheduler.py` — `NpcScheduler` subscribes to `HOUR_CHANGED` and moves NPCs according to their schedule.
- Added `services/quest.py` — `QuestService.check_progression` subscribes to `ITEM_TAKEN`, `PLAYER_MOVED`, and `ITEM_DROPPED`; evaluates stage conditions (`flag_set`, `flag_clear`, `room_visited`, `item_in_inventory`); advances or completes quests and awards rewards.
- Added `commands/social.py` — `talk`/`speak`, `choice`/`choose`, `say`, `bye`/`farewell`/`goodbye` commands.
- Extended world YAML validator and loader to accept `npcs`, `dialogue_trees`, and `quests` sections.
- Seeded starter world with Mira the Innkeeper (NPC), her dialogue tree, and a sample "Lights in the Square" quest.
- Added dialogue overlay to game client — appears with NPC name, node text, and clickable choice buttons; hides when dialogue ends; "End conversation" button closes via `bye` command.
- Added live quest tracker to game client right panel — shows active quest titles and current stage descriptions; updates on quest start, stage advance, and completion.
- Added `quest_repo` and `dialogue_repo` fields to `GameContext` (optional, backward-compatible).
- Added 14 new unit tests in `test_dialogue.py` and `test_quest_service.py`.

### Added (Phase 6 — Admin Tools)

- Added Phase 6 admin tools: JWT auth, role-based REST API, and admin push WebSocket at `/admin/ws`.
- Added `admin/auth.py` — PBKDF2-HMAC-SHA256 password hashing, PyJWT access/refresh token issue and verify, role hierarchy (`observer < moderator < world-builder < superadmin`), FastAPI dependency shortcuts.
- Added `admin/api.py` — admin router with endpoints for player management (list, state, teleport, flags, freeze/unfreeze), audit log query, world rooms/items/NPCs, changeset lifecycle (create, scan, promote), clock control (pause/resume, time-ratio, weather), and admin account management.
- Added `admin/websocket.py` — per-connection async queue, `AdminBroadcaster` fan-out, JWT auth via `?token=` query param.
- Added `admin/broadcaster.py` — `AdminBroadcaster` for safe push from synchronous EventBus handlers to async WS clients.
- Added `world/versioning.py` — `VersioningService` with changeset CRUD, conflict scanner (broken exits, displaced players, held items), and atomic promotion with `WorldMeta.schema_version` bump.
- Added `models/admin.py` — `AdminUser` SQLModel table with role and revocation support.
- Added `state.py` — `AppState` dataclass extracted from `main.py` to break circular imports.
- Added admin web panel at `/admin` — single-file SPA (Terminal Gothic styling) with login, live WS push, and tabs for all admin sections.
- Added Textual TUI (`admin/tui/app.py`) as an optional `admin-tui` dependency group; F1–F5 screen routing; credential storage at `~/.config/lorecraft-admin/credentials.json`.
- Added `LORECRAFT_ADMIN_JWT_SECRET`, `LORECRAFT_ADMIN_SEED_USERNAME`, `LORECRAFT_ADMIN_SEED_PASSWORD`, `LORECRAFT_ADMIN_SEED_ROLE` config env vars.
- Added `pyjwt>=2.9.0` as a production dependency.
- Added 39 new tests across `tests/unit/test_admin_auth.py`, `tests/integration/test_admin_api.py`, and `tests/integration/test_versioning.py`.

### Changed

- Updated `start.sh` to create `.venv` when missing and install Lorecraft editably with the admin TUI extra when dependencies are absent or incomplete.
- Excluded `admin/tui` from basedpyright checks (optional Textual dependency not installed in base venv).
- Extracted `AppState` from `main.py` into `lorecraft/state.py` to allow admin router import without circular dependency.
- Seeded `WorldMeta` singleton in `_ensure_starter_world` to support changeset promotion.

### Verified

- `.venv/bin/python -m pytest` passes with 89 tests.
- `.venv/bin/ruff check src tests` passes.
- `.venv/bin/ruff format --check src tests` passes.
- `.venv/bin/basedpyright --warnings` passes (TUI excluded).

## [0.1.0] - 2026-06-27

### Added

- Added `docs/STATUS.md` to track implementation progress against the architecture overview.
- Added initial `src/lorecraft` package scaffold for the multiplayer text adventure engine.
- Added environment-driven settings in `lorecraft.config`.
- Added core game primitives:
  - `GameContext` for per-command execution state.
  - `TransactionContext` and transaction source types.
  - `GameEvent`, `Event`, and synchronous `EventBus`.
  - `RuleEngine` and `RuleResult`.
  - `CommandRegistry`, command scopes, command conditions, and condition evaluation.
  - `ParsedCommand` parser with direction aliases, verb aliases, and article stripping.
  - `CommandEngine` dispatch scaffold.
  - `ConnectionManager` for WebSocket-style player connections and room broadcasts.
- Added pytest-based unit test structure under `tests/unit`.
- Added placeholder `tests/integration` and `tests/simulation` directories for future database and WebSocket coverage.
- Added `make test` for focused local verification.
- Added repository agent instructions in `AGENTS.md`, with `CLAUDE.md` importing them for Claude Code compatibility.
- Added guidance to keep `CHANGELOG.md` current and synchronize package versions in `pyproject.toml` and `src/lorecraft/__init__.py`.
- Added guidance to aim for type hints in new and changed Python code while allowing pragmatic omissions.
- Added a `dev` optional dependency group for local development tools: BasedPyright, pytest, and Ruff.
- Added pre-commit configuration for file hygiene, secrets detection, Ruff, YAML linting, Prettier for JavaScript/TypeScript files, and BasedPyright push checks.
- Added SQLModel table definitions for world, player, session, quest, combat, versioning, interaction, and audit persistence.
- Added database bootstrap helpers for creating game tables and audit tables in separate SQLite databases.
- Added shared structural typing aliases and protocols for JSON payloads, WebSocket connections, command contexts, players, and rooms.
- Added thin SQLModel repository wrappers for players, rooms, items, NPCs, and audit events.
- Added repository unit tests covering core game model and audit event round trips.
- Added FastAPI service wiring with startup table initialization and shared app state.
- Added `/health` and `/ws` endpoints for service health checks and player command WebSocket sessions.
- Added direct ASGI integration tests for lifespan startup, health checks, WebSocket connection, and command dispatch.
- Added audit recording for blocked and executed commands.
- Added meta commands for `help` and `quit`.
- Added movement commands and `MovementService` room transitions.
- Added WebSocket movement integration coverage for persisted room changes.
- Added a minimal browser client harness with WebSocket connection, message routing, state tracking, text feed, command input, and room/session status display.
- Added static asset routes for the browser client.
- Added starter world bootstrap for empty databases so the browser harness can connect as `player-1`.
- Added browser client smoke coverage for the served HTML, CSS, and JavaScript contract.
- Added repo-local seed test database files that `start.sh` copies into `/tmp` for browser harness startup.
- Added a persistent world clock runner with startup fast-forwarding and boundary events.
- Added weather and season state transitions driven by day changes.
- Added inventory inspection and item movement commands for `look`, `examine`, `take`, `drop`, and `inventory`.
- Added YAML world validation and import helpers for rooms, exits, items, and room item placement.
- Added a Tailwind-powered world UI layout with minimap, status, feed, inventory, and quest panels.
- Added SVG minimap rendering for visited rooms and fog-of-war adjacent rooms.
- Added structured WebSocket UI snapshots for room, visited-room, inventory, and time state.
- Added save/load commands and `SaveSlotService` for player-owned state.
- Added WebSocket disconnect grace, reconnect session reuse, reconnect sync payloads, and grace-expiry state handling.
- Added system audit events for disconnect, reconnect, and expired grace transitions.

### Changed

- Documented the project package layout as `src/lorecraft` in `docs/ARCHITECTURE.md`.
- Configured pytest to import package code from `src`.
- Added `sqlmodel` as a production dependency for the persistence layer.
- Added a BasedPyright project configuration for the `src` package and local `.venv`.
- Replaced broad `Any` annotations in the command, event, rule, connection, and model layers with narrower protocols and JSON types.
- Preserved full SQLAlchemy database URLs while retaining existing SQLite path handling.
- Added FastAPI and Starlette as production dependencies for the service layer.
- Tightened `GameContext` to use concrete repository, model, event bus, and connection manager types.
- Extended `CommandEngine` to commit state changes, write audit events, and flush queued domain events.
- Packaged the browser client assets with the Python package.
- Declared PyYAML as a production dependency for world authoring imports.
- Updated the browser client router to render inventory and minimap state from structured updates.
- Added SQLite compatibility handling for the save-slot `visited_rooms` column.

### Verified

- `.venv/bin/python -m pytest` passes with 49 tests.
- `.venv/bin/ruff check src tests` passes.
- `.venv/bin/ruff format --check src tests` passes.
- `.venv/bin/basedpyright --warnings` passes.
