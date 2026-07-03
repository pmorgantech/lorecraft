# Changelog

All notable changes to Lorecraft will be documented in this file.

## [Unreleased]

### Summary

**Sprints 4–15 Complete — Player authentication shipped, foundation gate is green.** Player authentication (password login, JWT access/refresh tokens, single-use WebSocket tickets, retired the `?player_id=` trust-by-default, OAuth extensibility stub), module decomposition (web/parser/admin split into 9 focused modules), service consistency (ServiceContainer, register(bus) convention), extensibility seams (pluggable registries for dialogue side effects, dialogue/command conditions, feature-registration pattern documented), tooling infrastructure (repo-tracked issues/news, world content CLI, analytics query API, content linting), a browser E2E harness (Playwright against a live server), a simulation harness (real WebSocket clients against a live server, multi-player scenarios, audit-log regression diffing), observability + CI quality gates (structured logging with correlation IDs, command/event timing instrumentation, required GitHub Actions checks), a unified command lifecycle (rollback-on-error, shared `/ws`/`POST /command` room-broadcast step, unified `GameContext` construction), and core UX completion (world clock/weather WS push to all connected players, multi-player live lists refreshed on room-leave). 431 focused tests + 3 E2E tests + 5 simulation tests passing; basedpyright 0 errors on `src/`; ruff clean. All 8 foundation exit criteria now met — Sprints 16+ (engine-first Tier 1 primitives, then item/equipment/trading/exploration/combat/PvP; see `docs/engine_core.md` and `docs/roadmap.md`) are unblocked.

### Added

- **Sprint 4: Player Authentication** — Real password auth replacing the previous zero-authentication lobby (anyone could one-click enter as any existing character). New `PlayerAuth` table (provider-agnostic `provider`/`provider_subject`/`credential_hash`, ready for OAuth without a schema change). `web/auth.py`'s `login_or_register()` creates an account atomically on first login, verifies the stored password hash on repeat login, and *claims* pre-existing passwordless players (e.g. dev-seeded `player-1`) on first authenticated login — shared by `POST /auth/login` (JSON API) and the browser's `/lobby/enter`/`/lobby/create` (one password-checking code path for both). Password hashing reuses `admin/auth.py`'s existing PBKDF2-HMAC-SHA256 primitives rather than adding bcrypt/argon2 as a second hashing convention. `POST /auth/login` issues 15-minute access + 8-hour refresh JWTs (reusing `admin/auth.py`'s `create_token`/`decode_token`, signed with `Settings.player_session_secret`, a distinct token `type` from the browser's `lorecraft_session` cookie so neither can be replayed as the other); `POST /auth/refresh` rotates them, verifying the player still exists. `POST /auth/ws-ticket` mints a single-use, 60-second ticket (in-memory on `AppState.ws_tickets`, matching the existing `pending_disambig` pattern) — accepts either a bearer access token or the browser's signed session cookie, since browsers can't easily attach custom headers to a WebSocket upgrade. `main.py`'s `/ws` endpoint now resolves the connecting player via `?ticket=` first, rejecting outright on an invalid/expired/reused ticket rather than silently falling back to `?player_id=`. `Settings.allow_query_player_id` now defaults to `False`; kept as an explicit opt-in for test fixtures that intentionally exercise the wire protocol directly (`tests/simulation/`'s `VirtualPlayer`, several state-resolution integration tests) rather than the login UI. `POST /auth/oauth/{provider}/callback` is a genuine 501 stub marking the extension point — `PlayerAuth`'s shape already supports it, nothing is wired up. Fixed two bugs surfaced along the way: (1) JWT `create_token()` only had second-precision `iat`, so two tokens issued for the same subject within the same second were byte-for-byte identical — added a `jti` claim, fixing both the new player refresh endpoint and the pre-existing admin one; (2) flipping `allow_query_player_id` off exposed that `GET /lobby` depended on `get_current_player` (which now 401s with no session), so a brand-new visitor couldn't reach the page that lets them log in — a real e2e browser test failure caught this before unit tests would have; new `get_current_player_optional()` fixes it for `/lobby` only. 44 new/updated tests across `test_player_authentication.py` (15), `test_player_login.py` (9), and updated lobby/session/simulation/characterization tests for the password requirement.

- **Sprint 15: Core UX Completion** — Closed the last two `[~]` STATUS partials. **15.1 World clock/weather WS push:** `ConnectionManager.broadcast_global()` sends a message to every connected player regardless of room; `main.py` wires a `TIME_ADVANCED` handler that broadcasts current clock/weather state (`time_update`: hour, minute, day, season, weather) to all players on every tick, not just on connect/reconnect SSR. **15.2 Multi-player live lists:** `game/broadcast.py`'s `broadcast_command_effects()` now sends a second `state_change` (`players-online` panel) to the room a player *left*, not just the room they entered — previously, occupants of the old room only saw the departure narration text in the feed, with no live players-list refresh until they took some other action. Both verified with new/updated simulation tests exercising the real WS broadcast path over a live server.

- **Sprint 14: Unify Command Lifecycle** — `CommandEngine._execute_parsed` (`game/engine.py`) now catches exceptions from the command handler instead of letting them propagate uncaught: on a crash it rolls back the game DB session (new `GameContext.rollback_state`/`rollback_state_changes()`, wired at both entry points), discards any partial `ctx.messages`/`room_messages`/`updates`/`pending_events` the crashed handler produced (never tell clients something happened until the DB says it happened), replaces them with a generic error message, and records a new `GameEvent.COMMAND_FAILED` audit event (severity `ERROR`). New `game/broadcast.py`'s `broadcast_command_effects()` is now the one place step 12 of the architecture.md §26 lifecycle (room broadcast) lives — both `main.py`'s `/ws` command loop (now `async`) and `web/frontend.py`'s `POST /command` call it after `CommandEngine.handle_command()` returns, closing the gap Sprint 12's simulation tests surfaced: the raw `/ws` path never re-broadcast a command's `ctx.room_messages` narration or a `state_change` nudge to other WS-connected room occupants the way `POST /command` did. `web/frontend.py`'s previous inline copy of that logic is gone in favor of the shared function. New simulation test exercises the previously-broken `/ws` path over a real socket; full existing suite (unit/integration/e2e/simulation) confirms `POST /command` behavior is unchanged. **Follow-up:** `game/context.py`'s `build_game_context()` factory (Sprint 6.3) turned out to be unused by both real entry points, which still constructed `GameContext` inline — extended it to accept `audit_session` (a separate `Session`, matching real usage, replacing the old same-session `create_audit_repo` bool) and `rollback_state`, stopped it from synthesizing a fallback `WorldClock` when `clock` isn't given (a fabricated clock is silently wrong data, not a safe default — real callers pass `room_repo.world_clock()`, which can legitimately be `None`), and switched both `main.py` and `web/frontend.py` to call it. Neither entry point builds any repo by hand for `GameContext` anymore.

- **Sprint 13: Observability & CI Quality Gates** — `observability.py`: `configure_logging()` attaches a correlation-aware log formatter/filter to the root logger (idempotent; level from new `Settings.log_level`/`LORECRAFT_LOG_LEVEL`, default `INFO`), and `bind_transaction_context()` publishes a `TransactionContext`'s IDs to a `contextvars.ContextVar` for the duration of one command so every log call anywhere in that call stack picks them up automatically — wired into `create_app()` and both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`). `CommandEngine._execute_parsed` (`game/engine.py`) now times each command handler and stamps `duration_ms` onto the `COMMAND_EXECUTED` audit event payload; `EventBus.emit()` (`game/events.py`) times each handler dispatch onto a new `HandlerResult.duration_ms` field and logs handler timing + registered-handler count ("depth") at DEBUG. New `analytics.command_latency_percentiles()` (p50/p95/p99) + `GET /admin/analytics/latency`. `.github/workflows/ci.yml`: three required jobs on push/PR to `main` — `quality` (`make lint` + `make typecheck` + `make test-cov`), `simulation` (`make test-simulation`), `e2e` (Playwright + `pytest tests/e2e`); new `make lint`/`make typecheck`/`test-cov` targets; new `pytest-cov` dev dependency with `[tool.coverage.report] fail_under = 80` (baseline ~82%). Fixed a latent bug found while dry-running the CI commands locally: `tests/simulation/*.py`'s `from tests.simulation.conftest import ...` only resolved under `python -m pytest`, not the bare `pytest` that `make test-simulation`/CI actually invoke — fixed by adding `"."` to `pythonpath` in `pyproject.toml`.

- **Sprint 12: Simulation Harness MVP** — `tests/simulation/`, a third test transport alongside the ASGI-transport integration tests and the Sprint 11 browser E2E harness: real `websockets` clients against a real, live `uvicorn` server, per `architecture.md` §25. `virtual_player.py`'s `VirtualPlayer` wraps one real `/ws` connection (`send_command()`/`run_script()` with optional timing jitter, `wait_for_broadcast()` for pushed messages). `conftest.py`'s `simulation_server`/`simulation_server_factory` fixtures boot the real app against a disposable per-test sqlite DB and the real `world_content/world.yaml` (same no-synthetic-world-content pattern as `tests/e2e/`). `test_multiplayer_scenarios.py` covers `player_joined` broadcast fan-out and concurrent `take` of a single-quantity item (exactly one winner, no duplication). `test_audit_regression.py` runs a fixed script against two independent fresh servers and diffs the normalized audit trail for determinism. New `simulation` pytest marker excluded from `pytest`/`make test` by default (`-m "not simulation"`, run via `make test-simulation`); no new install required (`websockets`/`httpx` were already transitive via `fastapi[standard]`, now declared explicitly in the `dev` extra). Surfaced but intentionally left unfixed: the raw `/ws` command loop doesn't yet re-broadcast `room_messages` to other room occupants the way `POST /command` does — tracked by Sprint 14 (unify command lifecycle).

- Launcher DB initialization: `./start.sh --init-dbs-if-missing` creates missing seed
  game/audit DBs before launch; `--init-dbs-only` performs setup and exits. Game DB
  import reads `world.yaml` from `--world-dir`/`--world`, defaulting to
  `world_content/`. Added `scripts/create_audit_db.py` for standalone audit schema
  creation.

- **Sprint 11: Browser E2E Harness** — `tests/e2e/` drives the HTMX/Alpine UI through a real headless-Chromium browser against a real, live `uvicorn` server, catching regressions (HTMX swaps, OOB panel updates) that the ASGI-transport integration tests can't see. `conftest.py`'s `live_server` fixture boots `create_app()` on a background thread with a disposable per-test sqlite DB and the real `world_content/world.yaml`; `test_gameplay_flows.py` covers character creation, movement with room/inventory panel updates, and dialogue → quest-start, exercising the same Ashmoore golden path documented in `docs/roadmap.md`. New optional `e2e` dependency group (`playwright`) and a `pytest` marker keep the suite out of the default `pytest`/`make test` run (`-m "not e2e"`); `make test-e2e` installs the extra + Chromium binary and runs it explicitly.

- **Sprint 10.5: Tooling Infrastructure** — `docs/tooling_infrastructure.md` design, implemented across five sub-sprints:
  - **10.5.1 Issues** — `docs/issues.yaml` (repo-tracked, git-blame-able) imported into the DB on first startup and re-exported on every admin mutation. `GET/POST/PUT /admin/issues` CRUD, TUI F6 screen, web panel Issues tab.
  - **10.5.2 News** — `docs/news.yaml` announcements with the same YAML↔DB sync pattern. In-game `news` command, public unauthenticated `/api/news` (JSON) and `/api/news/feed` (RSS 2.0), admin CRUD, TUI F7 screen, web panel News tab. `GameContext` gained an optional `news_repo`, wired at both direct construction sites and the `build_game_context()` factory.
  - **10.5.3 World CLI** — `python -m lorecraft.tools.world_cli {import,export,validate,diff,merge,stats}`. Added `export_world_document()` to `world/loader.py` (inverse of `import_world()`) as the shared basis for export/diff/merge/stats. Smoke-tested against the real `world_content/world.yaml`.
  - **10.5.4 Analytics** — `lorecraft.analytics` query functions over the audit log (top commands, NPC interaction counts, quest completions) and `PlayerSession` rows (player-hours), exposed via `GET /admin/analytics/{commands,npcs,quests,player-hours}`. No dashboard yet, per the design doc; command latency/event-bus-depth metrics wait on Sprint 13 instrumentation.
  - **10.5.5 Content linting** — `lorecraft.tools.validators`: dangling dialogue node references, room reachability from a start room, dead item references (`usable_with`, NPC `loot_table`), duplicate item names per room, oversized item stacks. Wired into `world_cli.py validate` via `--start-room`/`--strict`.

- **Sprint 10.4: Feature Registration Pattern** — `docs/feature-registration.md` documents the pattern for adding new gameplay features (combat, trading, PvP) without core edits: features define models, services, commands, and register with pluggable registries (CommandRegistry, CommandConditionRegistry, SideEffectRegistry, dialogue ConditionRegistry, RuleEngine, and ServiceContainer). Example structure shown for future combat feature (Sprint 18).

- **Sprint 10.3: Pluggable Command Conditions** — `game/command_conditions.py` — CommandConditionRegistry with pluggable condition predicates. Replaced hardcoded `_evaluate_condition` if/elif chain in registry.py with registry.evaluate(). Built-in conditions (requires_light, not_in_combat, flag_set, item_in_inventory, etc.) registered at module load; new predicates can be added without core edits.

- **Sprint 10.2: Pluggable Dialogue Conditions** — `npc/dialogue_conditions.py` — ConditionRegistry for dialogue choice/exit visibility. Replaced hardcoded flag checks in _visible_choices with registry-based _choice_visible() that evaluates all condition fields via registered predicates (required_flags, forbidden_flags initially; level_check, has_item, etc. can be added).

- **Sprint 10.1: Pluggable Dialogue Side Effects** — `npc/side_effects.py` — SideEffectRegistry replacing hardcoded if/elif branches in _apply_side_effects. Built-in handlers (set_flags, clear_flags, give_item, start_quest, end_dialogue) registered at module load; new effects can be added without touching dialogue.py.

- **Sprint 9.4: Item Matcher Consolidation** — Replaced three near-identical inline matching loops in `repos/item_repo.py` with one `_match_kind()` classifier plus two thin aggregators: `_best_matches()` (exact-wins, fuzzy-fallback; used by `search_in_room`/`search_player_items`) and `_any_matches()` (position-preserving any-match filter; used by `inventory_slots_matching`, which must stay positionally addressable for indexed take/drop like "2.sword"). Verified position ordering is unchanged with a mixed exact/fuzzy manual check. Same public API, same behavior.

- **Sprint 9.3: Inventory Take/Drop DRY** — Added `InventoryService._resolve_single()` (shared find→disambiguate step, generic over match shape via an `item_of` extractor) and `_do_take()`/`_do_drop()` (shared act step: remove, say, tell_room, emit event). Applied to `_take_one`, `_take_quantity`, `_take_indexed`, `_drop_one`, `_drop_quantity`, `_drop_indexed`, plus `examine`/`use_item`/`give_item` which had the same boilerplate. Behavior preserved exactly (same messages, same disambiguation prompts, same event counts).

- **Sprint 9.2: Event-Wiring Convention** — `QuestService.register(bus)` added, matching the convention already used by `NpcScheduler`/`SchedulerService`. Replaces the three inline `bus.on(GameEvent.X, quest_service.check_progression)` calls in `main.py`'s lifespan with one `services.quest.register(bus)` call.

- **Sprint 9.1: Service Container** — `services/container.py` — `ServiceContainer` dataclass holding the five stateless gameplay services (movement, inventory, save, dialogue, quest), built once via `ServiceContainer.build()`. `AppState` now carries a `services` field; `main.py` builds one container per app lifespan and passes it to both command registration and event wiring instead of each command module (and `main.py`'s inline `QuestService()`) constructing its own. `register_all_commands(registry, services=None)` defaults to a fresh container so existing direct-call test sites and the `web/session.py` standalone fallback keep working unchanged. `register_social_commands` gained an optional `dialogue_service` parameter, matching the other three command modules.

- **Sprint 8.3: Admin API Decomposition** — Split `admin/api.py` (817 lines) into per-resource routers under `admin/routers/`:
  - `players.py` (191 lines) — list/state/teleport/flags/freeze/unfreeze
  - `audit.py` (93 lines) — query_audit, session_replay
  - `world.py` (357 lines) — rooms, items, NPCs, and changesets (create/scan/promote)
  - `clock.py` (125 lines) — get/pause/resume/time-ratio/weather
  - `accounts.py` (93 lines) — list/create/revoke admin accounts
  - `admin/api.py` now 20 lines: mounts `auth_router` + the 5 resource routers onto `admin_router`. Same route paths, same `admin_router` export, so `main.py` required no changes.
  - HTTPException raises remain at the route layer per router (already separated from game-state logic — no service-layer HTTP leakage to fix).
  - All 23 admin API integration tests pass unchanged; basedpyright 0 errors on `admin/`.

- **Sprint 8.2: Parser Grammar Extraction** — Split `game/parser.py` (778 lines) into:
  - `game/grammar.py` (322 lines) — Grammar constants (ARTICLES, PREPOSITIONS, PHRASAL_VERBS, DIRECTIONS, VERB_ALIASES, etc), text processing (normalize, tokenize, make_phrase), semantic rules (extract_quantity_and_adjectives, direct_role_for_verb, find_first_preposition, map_prep_to_role), fuzzy matching (score_match).
  - `game/diagnostics.py` (119 lines) — ParseDiagnostics dataclass, diagnose_command, print_diagnostics for parser debugging.
  - `parser.py` now 399 lines, focused on command parsing (ParsedCommand, ParseResult, parse_command, parse). Re-exports diagnostics for backwards compatibility.
- Fuzzy matching and grammar rules now reusable for alternative parsers or CLI modes.
- All parser tests passing (37 comprehensive tests + full integration suite).

- **Sprint 8.1: Web Frontend Decomposition** — Split `web/frontend.py` (1,306 lines) into three focused modules:
  - `web/session.py` (380 lines) — Dependency injection (get_engines, get_app_state, get_command_engine, get_manager, get_bus), session auth (player_session_secret, set_player_session_cookie, ensure_player_session), state snapshots (inventory_snapshot, room_panel_context, active_quests_snapshot, world_time_snapshot), presence helpers (format_idle_duration, presence_for_player, players_here), grace period expiration, CommandResult dataclass.
  - `web/rendering.py` (180 lines) — Template rendering (build_map_data, audit_to_feed, feed_items_html), HTML output formatting (mark_oob_swap), command resolution (resolve_command_text), dev player creation.
  - `frontend.py` (784 lines) — Focuses exclusively on FastAPI routing and HTTP endpoints. Updated all endpoint handlers and test imports.
- Replaced `getattr`-chain state access in dependency injection with explicit functions (FastAPI `Depends()` ready for Sprint 9).

### Added

- **Sprint 7.4: Event-Flow Characterization Tests** — 10 unit tests locking in event-bus behavior before Sprint 8–9 refactors. Covers: event emission order and priority-based handler execution (higher priority runs first); exception isolation (one handler's error doesn't block others); multiple event types and handlers per event; handler result collection with success/error status; work-event classification. Tests verify core event dispatch guarantees. Tests in `tests/integration/test_event_flow.py`.
- **Sprint 7.3: Admin WebSocket Characterization Tests** — 7 integration tests locking in current behavior of `/admin/ws` endpoint before Sprint 8–9 refactors. Coverage: token validation (JWT accept/reject with code 1008), connection lifecycle (accept, receive, disconnect), multiple concurrent clients, error handling (malformed messages, connection errors). Verifies graceful error handling and state cleanup on disconnect. Tests in `tests/integration/test_admin_websocket.py`.
- **Sprint 7.2: Admin API Characterization Tests** — 6 additional integration tests extending admin endpoint coverage to 23/28 endpoints (~82% coverage) in `test_admin_api.py`. New coverage: player state manipulation (freeze/unfreeze with session status), world data queries (items, NPCs), clock management (time ratio), admin account management (list accounts). Tests verify proper HTTP status codes, role-based access control, and state mutations.
- **Sprint 7.1: Web Characterization Tests** — 23 integration tests locking in current behavior of `web/frontend.py` before Sprint 8–9 refactors. Coverage areas: (1) State resolution — game screen SSR with player/room/inventory/feed snapshots, error handling for missing rooms/players; (2) Session reconnect edge cases — grace period handling, presence status rendering (`online`/`grace`/`away`/idle duration); (3) Feed pagination — `/partials/feed?since=X` filtering, chronological ordering, COMMAND event exclusion; (4) Error rendering — missing room/player handling, empty inventory, many items, multiline OOB swap attributes. Tests in `tests/integration/test_frontend_characterization.py`.

### Fixed

- **Sprint 6: Type Safety Foundation** — Removed 18 `cast(GameContext, ctx)` calls from command handlers by properly typing the context parameter as `GameContext` instead of `object`. Command handlers are now type-checked by basedpyright to ensure safe context access. Replaced `cast(Any, ctx)` + unsafe `getattr()` in `game/registry.py` condition evaluation with direct `GameContext` attribute access. Upgraded basedpyright to `standard` mode (was `basic`); 0 errors.
- **Sprint 5: Error Handling Foundation** — Replaced 20 silent `except Exception` blocks with specific exception types and logging across auth, websocket, frontend, and parser modules (improves debuggability in production). Added guards against quantity underflow in `ItemRepo.remove_from_room()` (now raises `ConflictError` instead of silently deleting).
- Ambiguous `examine`/`inspect`/`x` targets now defer to `InventoryService`'s numbered disambiguation prompt (`disambig_pending` + choice number) instead of blocking at parse time with a plain "Perhaps you meant" list — matching `take`/`drop` behavior.
- HTMX `POST /command` now calls `CommandEngine.handle_command()` (commands were previously not executed).
- WebSocket client connects to `/ws?player_id=…` instead of the non-existent `/ws/game` path.
- Dev seed DB (`test_dbs/`) regenerated from Ashmoore `world_content/world.yaml`; `player-1` now starts at `village_square` with working exits.
- Removed hardcoded tavern/Mira/sword quest seed from `main.py`; empty databases bootstrap from `world_content/world.yaml` via `lorecraft.world.bootstrap`.
- Lobby and game templates use `current_player.username` instead of the nonexistent `name` field.
- Dialogue `choice 1` / numeric replies parse correctly (`choice_index`); bare digits during conversation map to `choice N`.
- HTMX out-of-band swaps for the dialogue overlay (and other panels) now attach `hx-swap-oob` even when partial markup splits attributes across lines.
- Dialogue overlay hides reliably on `bye` / End conversation (no conflicting Tailwind `flex` + `hidden` classes).
- Terminal dialogue nodes (e.g. Mira’s farewell) show their final line in the overlay instead of closing before the text appears.
- `quit` starts the disconnect grace period, notifies the room, and refreshes Here Now for other clients.
- WebSocket disconnect broadcasts feed text and refreshes the player list for roommates.

### Added

- **Sprint 6: Type Safety Foundation** — `CommandHandler` protocol in `types.py` for type-safe command dispatch. All 22 command handlers now use `ctx: GameContext` instead of `ctx: object`, enabling the type checker to verify context usage and catch errors at type-check time rather than runtime. Added `build_game_context()` factory in `game/context.py` for centralized GameContext construction (all entry points: websocket, scheduler, tests). Added TypedDict schemas for WebSocket and API payloads: `WsFeedAppend`, `WsStateChange`, `WsPlayerLeft`, `WsNarrative`, `ApiStatusResponse`.
- **Sprint 5: Error Hierarchy** — `lorecraft/errors.py` with `GameError` base class (machine-readable error codes) and five domain-specific exceptions: `ValidationError`, `NotFoundError`, `PermissionError`, `ConflictError`. Enables typed error handling, analytics tracking, and error-based testing. Comprehensive unit tests in `tests/unit/test_errors.py`.
- `services/scheduler.py` — `SchedulerService`, a persistent DB-backed job scheduler (Sprint 3, roadmap). `schedule(job_type, at_game_epoch, payload)` persists a `ScheduledJob` row; on every `TIME_ADVANCED` tick it marks due jobs `dispatched` and emits `GameEvent.SCHEDULED_JOB_DUE` for each so owning subsystems (combat, NPC movement, delayed world effects) can react without the scheduler knowing any game rules. `cancel(job_id)` marks a pending job cancelled. Wired into `AppState.scheduler` / `main.py` alongside the clock runner and NPC scheduler.
- `models/scheduler.py` — `ScheduledJob` table (`job_type`, `due_at_epoch`, `status`, `payload`, `created_at`), registered in `db.GAME_TABLE_MODELS`.
- `repos/scheduler_repo.py` — `SchedulerRepo.due(current_epoch)` for querying pending jobs at or before a game epoch.
- Graphify actually connected to the dev workflow: `make install-hooks` previously pointed `core.hooksPath` at a `.githooks/` directory that didn't exist. Added `.githooks/post-commit` (refreshes `graphify-out/graph.json` after each commit) and a Claude Code `SessionStart` hook (`.claude/settings.json` + `.claude/hooks/session-start.sh`) so web sessions get the graph refreshed automatically. `scripts/graphify-refresh.sh` now skips gracefully (exit 0) instead of failing when the `graphify` binary isn't installed.
- Item `aliases` (YAML/model/loader/validator) so players can refer to an item by a nickname sharing no words with its name (e.g. "blade"/"shortsword" for Rusty Iron Sword); wired through `GameContext.get_visible_entities()`/`get_inventory()` for parser fuzzy resolution and `ItemRepo` room/inventory search.
- Context-aware `help`: generated from real command metadata (`CommandDefinition.help_text`, `CommandRegistry.all_commands()`) instead of a hardcoded string; varies by dialogue (social + global only), combat (`NOT_IN_COMBAT`-gated commands drop out), and `Room.disabled_commands`.
- `use <item> [on/with <other>]` + `InventoryService.use_item()` — wires the previously-orphaned `Item.usable_with` field into gameplay; combining two items whose `usable_with` lists reference each other emits `GameEvent.ITEM_USED`. Added a `cage_key`/`cage_lock` `usable_with` example to `world_content/world.yaml`.
- `GameContext.parsed_command` — the dispatch loop now stashes the current `ParsedCommand` on context before invoking a handler, so handlers can read secondary roles (e.g. `use X on Y`, `give X to Y`) via `command_patterns.py` helpers instead of only the single noun string.
- `give <item> to <name>` + `InventoryService.give_item()` — hands a carried item to an NPC in the room and emits `GameEvent.ITEM_GIVEN`.
- `unlock <direction>` / `lock <direction>` + `MovementService.unlock()`/`lock()` — persist `Exit.locked` (while carrying `key_item_id`) so an exit unlocked once no longer needs the key for later movement, including by other players.
- `NpcRepo.find_in_room()` — shared NPC name lookup used by `talk` and `give`.
- `lorecraft.world.bootstrap` — YAML-driven empty-DB import and configurable dev player seeding.
- Config env vars: `LORECRAFT_WORLD_YAML_PATH`, `LORECRAFT_SEED_PLAYER_ID`, `LORECRAFT_SEED_PLAYER_USERNAME`, `LORECRAFT_SEED_PLAYER_START_ROOM`.
- NPC (Mira), dialogue tree, and sample quest in `world_content/world.yaml` for Ashmoore playtesting.
- Dialogue overlay and quest tracker partials for the HTMX game UI (OOB swaps on talk/quest updates).
- `dialogue_panel_state()` — rebuilds overlay content from persisted dialogue flags (node text and choices).
- `ConnectionManager.is_connected()` and Here Now presence from DB room occupancy plus live WS status.
- Here Now labels: online (green), grace **(Reconnecting…)**, away/idle (grey, e.g. `Idle 2h4m`).
- Dev `player-2` seeded for multi-player testing; `?player_id=` overrides the lobby cookie.
- World clock SSR in the game header; WS client handlers for `time_update` and `clock_tick`.
- Integration tests for HTMX command dispatch, dialogue choices, farewell nodes, and `bye` (`tests/integration/test_frontend_command.py`).
- Unit tests for world bootstrap, dialogue panel state, player presence, OOB markup, and `choice` parsing.

### Changed

- `import_world.py` wipes NPCs, dialogue trees, and quests on `--fresh`; seeds `player-1` and `player-2`; resets players on fresh import.
- `start.sh` copies `test_dbs/` seed databases again (not `game.db`).
- Admin and integration tests updated for Ashmoore room IDs (`village_square`, `wandering_crow_inn`, `market_stalls`, etc.).
- Key gallery disambiguation fixture exit link updated for Ashmoore topology (`blacksmith_forge`).
- Dialogue overlay styles NPC lines as a quoted blockquote; End conversation is a numbered option matching other choices.
- Removed duplicate panel wrapper IDs in `game.html` (inventory, Here Now) so OOB swaps target a single element.

## [0.2.0] - 2026.06.29

### Fixed

- `take`/`drop` item matching now singularizes item names as well as player input, so plural queries like `take herbs` match items named `Bundle of Dried Herbs`.
- Inventory command text and all inventory panels now group duplicate carried items with `[quantity]` prefixes (e.g. `[2] Worn Copper Coin`).

### Added

- Integrated Lorecraft parser v1 (`lorecraft_parser_v1`): semantic roles, prepositions, adjectives, quantities, quoted strings, phrasal verbs, compound commands (`;`), optional `GameContext` fuzzy resolution with disambiguation, in-character parse errors, and diagnostic tracing.
- Added `parse_command`, `ParseResult`, `diagnose_command`, and `registry_verb` helpers in `src/lorecraft/game/parser.py`; kept `parse()` as a backward-compatible wrapper for legacy callers.
- Added `GameContext.get_visible_entities()` and `GameContext.get_inventory()` for parser entity resolution.
- Wired `CommandEngine` and the HTMX frontend command path through `parse_command` (including compound execution and suggestion messages).
- Added comprehensive parser tests in `tests/game/test_parser_comprehensive.py`.
- Added offline parser diagnostic CLI at `tools/parser_diag.py`.
- Added `docs/command_parser.md` — parser output model, command pattern taxonomy, and handler integration guidance.
- Added `src/lorecraft/game/command_patterns.py` — `CommandPattern` enum, verb mapping, and typed role helpers (`speech_roles`, `transfer_roles`, `container_roles`, …).
- Added pattern-grouped parser tests in `tests/game/test_parser_patterns.py` and `tests/unit/test_command_patterns.py`; shared fixture in `tests/game/conftest.py`.
- Added `docs/parser_and_commands.md` — command authoring guide, item disambiguation layers, and Key Gallery testing notes.
- Added `key_gallery` room (Red Key, Iron Key, Rusty Iron Key, Steel Key, Cage Key, Cage Lock, Rusty Iron Sword, Red Rose) in `world_content/world.yaml` for in-game disambiguation testing; pytest helpers live in `tests/fixtures/disambig_fixtures.py`.
- Added `tests/unit/test_inventory_disambiguation.py` for shortened-name matching and numbered ambiguity prompts.
- `take`/`drop` object ambiguity now defers to `InventoryService` numbered disambiguation instead of blocking at parse time.
- `take` and `drop` now accept quantity, all, and indexed selectors: `take 2 coin`, `take 2 coins`, `take all coin`, `drop all coin`, and `take 2.coin` (second matching instance).
- Room `look` text and web room panel now group duplicate visible items with `[quantity]` prefixes, matching inventory display.
- HTMX inventory panel now refreshes when picking up another copy of an already-carried item (fixed set-based change detection).
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

- Added `docs/status.md` to track implementation progress against the architecture overview.
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

- Documented the project package layout as `src/lorecraft` in `docs/architecture.md`.
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
