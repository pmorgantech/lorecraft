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

### Changed

- Documented the project package layout as `src/lorecraft` in `docs/ARCHITECTURE.md`.
- Configured pytest to import package code from `src`.

### Verified

- `make test` passes with 21 unit tests.
