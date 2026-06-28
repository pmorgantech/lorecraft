# Changelog

All notable changes to Lorecraft will be documented in this file.

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

### Verified

- `.venv/bin/python -m pytest` passes with 45 tests.
- `.venv/bin/ruff check src tests` passes.
- `.venv/bin/ruff format --check src tests` passes.
- `.venv/bin/basedpyright --warnings` passes.
