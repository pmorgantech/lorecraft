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
- [ ] `models/` SQLModel table definitions.
- [ ] `create_tables()` startup database initialization.
- [ ] `repos/` data access wrappers.
- [~] `game/context.py` contains `GameContext`.
- [x] `game/transaction.py` contains `TransactionContext`.
- [~] `game/connection_manager.py` contains the WebSocket-style connection pool and room broadcast behavior.
- [~] `game/events.py` contains `GameEvent` and synchronous `EventBus`.
- [ ] `main.py` FastAPI app.
- [ ] `/ws` WebSocket endpoint.
- [ ] Startup/shutdown lifecycle wiring.
- [ ] WebSocket connect/send/receive integration test.

### Phase 2 — Command Dispatch

- [x] `game/parser.py` converts raw text into `ParsedCommand`.
- [x] Parser supports direction aliases such as `n` to `go north`.
- [x] Parser strips simple articles from nouns.
- [x] `game/registry.py` supports command registration and aliases.
- [~] `game/registry.py` evaluates a first pass of command conditions.
- [x] `game/rules.py` contains `RuleEngine` with ordered rule checks.
- [~] `game/engine.py` contains a command dispatch scaffold.
- [ ] Full 13-step transaction/event/audit lifecycle in `handle_command()`.
- [ ] Blocked command audit events.
- [ ] `commands/meta.py` with `help` and `quit`.
- [ ] `commands/movement.py` with `go` and cardinal directions.
- [ ] `services/movement.py` with `MovementService`.
- [ ] End-to-end movement test with persistent room change.

### Phase 3 — World & Time

- [ ] `clock/world_clock.py` background clock loop.
- [ ] `clock/weather.py` weather and season state machine.
- [ ] Inventory commands: `look`, `take`, `drop`, `examine`, `inventory`.
- [ ] `services/inventory.py`.
- [ ] World YAML loader.
- [ ] World YAML validator.
- [ ] Clock/weather/item pickup tests.

### Phase 4 — NPCs & Quests

- [ ] `npc/dialogue.py` dialogue tree walker.
- [ ] `npc/scheduler.py` NPC movement via `HOUR_CHANGED`.
- [ ] `services/dialogue.py`.
- [ ] Social commands: `talk`, `say`.
- [ ] `services/quest.py`.
- [ ] NPC dialogue and quest flag tests.

### Phase 5 — Combat

- [ ] Combat models.
- [ ] Player stats model.
- [ ] `services/combat.py`.
- [ ] `npc/combat_ai.py`.
- [ ] Combat commands: `attack`, `flee`.
- [ ] Combat resolution tests.

### Phase 6 — Persistence & Safety

- [ ] `services/save.py`.
- [ ] Save/load commands.
- [ ] Disconnect grace period handling.
- [ ] Reconnect handling.
- [ ] System-controlled disconnected-player state.
- [ ] Save/disconnect/reconnect/load preservation tests.

### Phase 7 — Admin Tools

- [ ] `admin/auth.py`.
- [ ] `admin/api.py`.
- [ ] `admin/websocket.py`.
- [ ] `world/versioning.py`.
- [ ] Admin changeset promotion tests.

### Phase 8 — Frontend

- [ ] Browser WebSocket client.
- [ ] Message router.
- [ ] Plain JavaScript state object.
- [ ] Three-column Tailwind layout.
- [ ] Text feed and command input.
- [ ] Minimap with fog of war.
- [ ] Dialogue overlay.
- [ ] Full-screen map modal.
- [ ] Browser end-to-end test.

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
- [ ] Integration tests.
- [ ] Simulation tests.
