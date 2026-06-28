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

### Phase 3 — World & Time

- [ ] `clock/world_clock.py` background clock loop.
- [ ] `clock/weather.py` weather and season state machine.
- [ ] Inventory commands: `look`, `take`, `drop`, `examine`, `inventory`.
- [ ] `services/inventory.py`.
- [ ] World YAML loader.
- [ ] World YAML validator.
- [ ] Clock/weather/item pickup tests.

### Phase 3.5 — World UI

- [ ] Inventory panel.
- [ ] Minimap with fog of war.
- [ ] Basic layout refinement.

### Phase 4 — NPCs & Quests

- [ ] `npc/dialogue.py` dialogue tree walker.
- [ ] `npc/scheduler.py` NPC movement via `HOUR_CHANGED`.
- [ ] `services/dialogue.py`.
- [ ] Social commands: `talk`, `say`.
- [ ] `services/quest.py`.
- [ ] NPC dialogue and quest flag tests.

### Phase 4.5 — Dialogue UI

- [ ] Dialogue overlay.

### Phase 5 — Persistence & Safety

- [ ] `services/save.py`.
- [ ] Save/load commands.
- [ ] Disconnect grace period handling.
- [ ] Reconnect handling.
- [ ] System-controlled disconnected-player state.
- [ ] Save/disconnect/reconnect/load preservation tests.

### Phase 6 — Admin Tools

- [ ] `admin/auth.py`.
- [ ] `admin/api.py`.
- [ ] `admin/websocket.py`.
- [ ] `world/versioning.py`.
- [ ] Admin changeset promotion tests.

### Phase 7 — Frontend Polish

- [ ] Three-column Tailwind layout.
- [ ] Full-screen map modal.
- [ ] Responsive behavior.
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
