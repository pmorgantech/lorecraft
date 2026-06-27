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

### Changed

- Documented the project package layout as `src/lorecraft` in `docs/ARCHITECTURE.md`.
- Configured pytest to import package code from `src`.
- Added `sqlmodel` as a production dependency for the persistence layer.
- Added a BasedPyright project configuration for the `src` package and local `.venv`.
- Replaced broad `Any` annotations in the command, event, rule, connection, and model layers with narrower protocols and JSON types.

### Verified

- `.venv/bin/python -m pytest` passes with 22 unit tests.
- `.venv/bin/ruff check src tests` passes.
- `.venv/bin/ruff format --check src tests` passes.
- `.venv/bin/basedpyright --warnings` passes.
