# Lorecraft — Roadmap

Working roadmap derived from `docs/architecture.md`, `docs/status.md`, `CODE_AUDIT.md`, and recent 0.2.0 development (HTMX migration + parser v1).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started

Sprints are scoped small (1–2 tasks, one subsystem) on purpose, so each sprint/task can be picked up with minimal context.

---

## Guiding principle (2026-07-01)

**Foundation before features.** The core engine must be very well designed, well tooled, well tested, and internally consistent *before* we expand commands or introduce combat, trading, or PvP. No skimping on code design and quality. Concretely:

- The findings in `CODE_AUDIT.md` are the work queue, not background reading. Foundation sprints below map directly to them.
- New features are gated behind the **Foundation exit criteria** (see below). Combat and trading do not start until the gate is green.
- Every change during the foundation phase should *raise* consistency: one error-handling style, one context-construction path, one event-wiring style, one module-layout convention.
- Partially-finished subsystems get finished or removed — no half-done seams left behind.

---

## Current position

Phases **1–6** are implemented (command dispatch, world/time, inventory, NPCs/quests, save/disconnect, admin tools). Version **0.2.0** added parser v1, quantity inventory, and the HTMX primary UI.

[Sprints 1–3](#sprint-1--htmx-parity-playtesting-unblock-) closed out HTMX parity, command-depth gaps, and the scheduler foundation. A full code audit (`CODE_AUDIT.md`, 2026-07-01, revalidated against source) identified the engineering debt to clear next.

**Current:** [Sprints 4–15](#sprint-4--player-authentication-production-hardening-) complete (player authentication, error handling, type safety, characterization tests, module decomposition, service consistency/wiring, extensibility seams, tooling infrastructure, browser E2E harness, simulation harness MVP, observability & CI quality gates, unified command lifecycle, core UX completion). **Foundation gate is green** — see exit criteria below. The post-foundation work was **re-sequenced 2026-07-03**: first around Lorecraft's design pillars (Exploration > Trading > Questing > Puzzles; combat is a supporting system, not the centerpiece), then split into an **engine-first Tier 1 band** ([`engine_core.md`](engine_core.md)) ahead of the Tier 2 feature modules: **Tier 1 engine primitives (16–21)** → item components & equipment (22–23) → traits/skills & exploration + UI (24–26) → condition/trade/transit (27–29) → quests/puzzles (30) → combat/PvP (31–35). See [`engine_core.md`](engine_core.md) for the Tier boundary and [`wishlist.md`](wishlist.md) for the pillars and mechanics menu.

---

## Sprint 1 — HTMX parity (playtesting unblock) ✅

**Goal:** Commands execute through `POST /command`, social gameplay is visible, and WebSocket push works for multi-player panel refresh.

| # | Task | Status |
|---|------|--------|
| 1.1 | Call `CommandEngine.handle_command()` in `frontend.py` `POST /command` | [x] |
| 1.2 | Disambiguation: bare-number replies via `AppState.pending_disambig` | [x] |
| 1.3 | Dialogue overlay partial + OOB swaps from `ctx.updates["dialogue"]` | [x] |
| 1.4 | Quest tracker partial + active quests on SSR + OOB on `quest_update` | [x] |
| 1.5 | Fix WebSocket URL (`/ws?player_id=…`), handle `feed_append` / `room_event` | [x] |
| 1.6 | `players_here` from `ConnectionManager` when WS connected | [x] |
| 1.7 | Integration tests: move, take, talk via `POST /command` | [x] |

---

## Sprint 2 — Command depth ✅

**Goal:** Close gameplay gaps (item aliases, disambiguation, help, use/give/lock) before combat.

| # | Task | Status |
|---|------|--------|
| 2.1 | Item `aliases` in YAML/model; wire through `GameContext.get_visible_entities()` | [x] |
| 2.2 | Finish inventory disambiguation bug | [x] |
| 2.3 | Context-aware `help` (dialogue, combat, per-room disabled commands) | [x] |
| 2.4 | `use` command + `InventoryService.use_item()` | [x] |
| 2.5 | 2–3 more parser patterns (`give`, `open`, containers) | [~] `give` + `lock`/`unlock` (on the existing `Exit.locked`/`key_item_id` fields) shipped; `open`/container-holding items deferred — needs new Item/state modeling |

---

## Sprint 3 — Scheduler foundation ✅

**Goal:** Phase 8 per `architecture.md` §28 — the scheduling primitive combat will run on.

| # | Task | Status |
|---|------|--------|
| 3.1 | `services/scheduler.py` — DB-backed jobs on `TIME_ADVANCED` | [x] |

---

## Sprint 4 — Player authentication (production hardening) ✅

**Goal:** Phase 7 per `architecture.md` §21 — full account system with password auth, JWT tokens, and signed WebSocket handshake. Foundation for all production deployments.

**See:** [`player_authentication.md`](player_authentication.md) for detailed workflows and code examples.

| # | Task | Status |
|---|------|--------|
| 4.1 | `POST /auth/login` — account creation on first login, password hashing (bcrypt/argon2) | [x] Uses the existing PBKDF2-HMAC-SHA256 primitives in `admin/auth.py` (`hash_password`/`verify_password`) rather than adding bcrypt/argon2 as a new dependency — same security properties, one hashing convention for the whole codebase. New `PlayerAuth` table (provider-agnostic: `provider`/`provider_subject`, ready for OAuth later). `login_or_register()` in `web/auth.py` also *claims* pre-existing passwordless players (e.g. dev-seeded `player-1`) on first authenticated login rather than erroring. |
| 4.2 | JWT access tokens (15min lifetime) + refresh token rotation (8hr lifetime) | [x] Reuses `admin/auth.py`'s `create_token`/`decode_token`, signed with `Settings.player_session_secret` (distinct token `type` from the browser's `lorecraft_session` cookie — can never be replayed as each other). Fixed a latent bug found along the way: tokens only had second-precision `iat`, so two issued in the same second were byte-identical (rotation was a no-op if called twice quickly) — added a `jti` claim, fixing both the new player refresh endpoint and the pre-existing admin one. |
| 4.3 | `POST /auth/ws-ticket` — single-use, 60-second WebSocket ticket exchange | [x] Accepts either `Authorization: Bearer <access_token>` (API clients) or the signed `lorecraft_session` cookie (the browser, which can't easily attach custom headers to a same-origin fetch but sends cookies automatically). Ticket storage is an in-memory dict on `AppState` (`ws_tickets`), matching the existing `pending_disambig` pattern — fine for this engine's single-process deployment target. |
| 4.4 | WebSocket handshake: validate ticket, map to player_id, attach to ConnectionManager | [x] `main.py`'s `_resolve_ws_player_id()`: a `?ticket=` param is authoritative — invalid/expired/reused rejects the connection outright (1008) rather than silently falling back to `?player_id=`, which would defeat the point of tickets. |
| 4.5 | `/auth/refresh` endpoint for refresh token rotation | [x] Also verifies the player still exists (guards against refreshing into a deleted account), mirroring `admin/auth.py`'s `/admin/auth/refresh`. |
| 4.6 | Retire legacy `?player_id=` query param fallback (was gated by `LORECRAFT_ALLOW_QUERY_PLAYER_ID`) | [x] `Settings.allow_query_player_id` now defaults to `False`. Not deleted outright — kept as an explicit opt-in for test fixtures that intentionally exercise the wire protocol directly (`tests/simulation/`'s `VirtualPlayer`, several state-resolution integration tests), since removing it would break the [Sprint 11](#sprint-11--browser-e2e-harness-)/12 harnesses for no real security benefit (trusted local test processes, not real clients). Surfaced and fixed a chicken-and-egg bug: `GET /lobby` depended on `get_current_player`, which now 401s with no session — meaning a brand-new visitor couldn't reach the page that lets them log in. New `get_current_player_optional()` fixes this for `/lobby` only; every other route correctly keeps requiring a session. |
| 4.7 | OAuth extensibility hooks (Google OIDC callback stubs for future LAN-party deployments) | [x] `POST /auth/oauth/{provider}/callback` stub — `PlayerAuth.provider`/`provider_subject` already generalize to non-local providers with no schema change needed. Returns 501 rather than pretending to implement OAuth (needs a registered client id/secret/redirect URI this engine doesn't have configured); not wired into any client. |
| 4.8 | Integration tests: login, token refresh, WS ticket validation, expired token rejection | [x] `tests/integration/test_player_authentication.py` (15 tests) + `tests/unit/test_player_login.py` (9 tests) + updated `tests/integration/test_player_session.py` for the new password-protected lobby. Covers account creation/verification/wrong-password, refresh rotation + expired/garbage/wrong-type rejection, ws-ticket issuance (bearer + cookie) + single-use + TTL expiry + expired-access-token rejection, and the OAuth stub. Full suite (unit/integration/e2e/simulation) green throughout — the e2e run caught the `/lobby` chicken-and-egg bug above before it could ship. |

**Also done, beyond the numbered checklist:** the browser lobby (`/lobby/enter`, `/lobby/create`) is now password-protected — previously `/lobby`'s "Join a World" tab was a one-click player picker with *zero* authentication (anyone could enter as any existing character), which the numbered tasks above don't explicitly cover but would have left the real player-facing surface unprotected even with the API-level auth in place. `login_or_register()` gained `allow_create: bool` so `/lobby/enter` ("Log In") 404s on a genuinely unknown username instead of silently creating one, while `/lobby/create` keeps create-or-claim semantics. `app.js`'s `connectWebSocket()` now fetches a ws-ticket before connecting instead of using a raw `?player_id=`.

---

# Foundation band (Sprints 5–15)

Work queue derived from `CODE_AUDIT.md`. Ordering is deliberate: error/type groundwork first, then **characterization tests before the big refactors**, then structure, then tooling.

**Current progress:** [Sprints 5–15](#sprint-5--error-handling--exception-hierarchy-) complete (error handling, type safety, characterization tests, module decomposition, service consistency/wiring, extensibility seams, tooling infrastructure, browser E2E harness, simulation harness MVP, observability & CI quality gates, unified command lifecycle, core UX completion). Foundation band done — see exit criteria below.

## Sprint 5 — Error handling & exception hierarchy ✅

**Goal:** One error-handling style everywhere. Audit §2.1.

| # | Task | Status |
|---|------|--------|
| 5.1 | `lorecraft/errors.py` — `GameError`, `ValidationError`, `NotFoundError`, `PermissionError`, `ConflictError` (with machine-readable `code`) | [x] |
| 5.2 | Eliminate the 22 silent `except Exception` blocks: catch specific exceptions, log all of them (`web/frontend.py` ×12, `web/player_auth.py`, `admin/websocket.py` ×3, `admin/auth.py` ×2) | [x] |
| 5.3 | Services raise typed errors; command handlers translate to `ctx.say()` in one shared wrapper | [~] prepared via errors.py; integration in [Sprint 9](#sprint-9--service-consistency--wiring-) |
| 5.4 | Guard quantity underflow in `ItemRepo.remove_from_room` (raise/log instead of silent delete) | [x] |
| 5.5 | Unit tests for error paths (every custom exception exercised) | [x] |

## Sprint 6 — Type safety ✅

**Goal:** basedpyright verifies real invariants. Audit §2.2.

| # | Task | Status |
|---|------|--------|
| 6.1 | Type `CommandHandler` as `Callable[[str | None, GameContext], None]` (Protocol in `types.py` or `TYPE_CHECKING` import); delete all 18 `cast(GameContext, ctx)` | [x] |
| 6.2 | Replace `cast(Any, ctx)` + `getattr(..., default)` condition evaluation in `game/registry.py` with typed access — conditions must fail closed, not open | [x] |
| 6.3 | Single `build_game_context()` factory used by all entry points; make `quest_repo`/`dialogue_repo`/`audit` required and delete their None-guards | [x] |
| 6.4 | `TypedDict` schemas for WS payloads and HTMX/JSON responses | [x] |
| 6.5 | Raise basedpyright to `standard` mode on `src/` and hold it there | [x] |

## Sprint 7 — Web & admin characterization tests ✅

**Goal:** Lock in current behavior *before* the [Sprint 8–9](#sprint-8--module-decomposition-) refactors. Audit §2.3.

| # | Task | Status |
|---|------|--------|
| 7.1 | Characterization tests for `web/frontend.py`: state resolution, session reconnect edge cases, feed pagination, error rendering | [x] |
| 7.2 | Admin API endpoint tests (target ~80% of `admin/api.py` routes) | [x] |
| 7.3 | Admin WebSocket integration tests | [x] |
| 7.4 | Event-flow integration tests: command → event → service reaction → client update; handler-ordering assertions | [x] |

## Sprint 8 — Module decomposition ✅

**Goal:** No module over ~400 lines with mixed concerns. Audit §2.6.

| # | Task | Status |
|---|------|--------|
| 8.1 | Split `web/frontend.py` (1,306→780 lines) → `session.py` (380), `rendering.py` (180); replaced `getattr`-chain state access with explicit dependency injection functions | [x] |
| 8.2 | Extract `game/grammar.py` (322 lines) and `game/diagnostics.py` (119 lines) from `game/parser.py` (774→407 lines); re-exports for backwards compatibility | [x] |
| 8.3 | Split `admin/api.py` (817→20 lines) into per-resource routers under `admin/routers/`: `players.py` (191), `audit.py` (93), `world.py` (357, incl. items/NPCs/changesets), `clock.py` (125), `accounts.py` (93); `admin_router` now just mounts them, same route paths and status codes | [x] |

## Sprint 9 — Service consistency & wiring ✅

**Goal:** One way to construct, wire, and use services. Audit §3.1.

| # | Task | Status |
|---|------|--------|
| 9.1 | Service container/registry in `AppState`; remove ad-hoc `Service()` instantiation from the four command modules | [x] |
| 9.2 | One event-wiring convention: every service exposes `register(bus)`; replace the inline `bus.on()` quest wiring in `main.py` | [x] |
| 9.3 | DRY the six near-identical take/drop methods in `services/inventory.py` (shared find→disambiguate→act helper) | [x] |
| 9.4 | Consolidate item-matching logic in `repos/item_repo.py` into one matcher | [x] |

## Sprint 10 — Extensibility seams ✅

**Goal:** New mechanics hook in via data/registration, not core edits. Audit §3.3.

| # | Task | Status |
|---|------|--------|
| 10.1 | Pluggable dialogue side effects (handler registry replacing the hardcoded `set_flags`/`give_item`/`start_quest` branches in `npc/dialogue.py`) | [x] |
| 10.2 | Pluggable dialogue/exit conditions (predicate types beyond flags: level, item, quest state) | [x] |
| 10.3 | Pluggable command conditions (registry instead of the hardcoded `_evaluate_condition` chain) | [x] |
| 10.4 | Decide + document the feature-registration pattern (models/commands/events/rules per feature) — combat will be its first consumer | [x] |

## Sprint 10.5 — Tooling Infrastructure ✅

**Goal:** Admin/dev tooling foundation: repo-tracked issues & news, world CLI suite, analytics API, content validation. Unblocks [Sprint 11](#sprint-11--browser-e2e-harness-)+ (can log failures, record metrics, validate content).

| # | Task | Status |
|---|------|--------|
| 10.5.1 | Issues system: `docs/issues.yaml`, CRUD routes, admin TUI (F6) + web panel tabs | [x] |
| 10.5.2 | News & announcements: `docs/news.yaml`, in-game `/news`, RSS feed, admin UI (TUI F7) | [x] |
| 10.5.3 | World management CLI: import/export/validate/diff/stats commands; call from admin world manager | [x] |
| 10.5.4 | Analytics API foundation: metric queries ready (no dashboard yet, driven by [Sprint 13](#sprint-13--observability--ci-quality-gates-) instrumentation) | [x] |
| 10.5.5 | Content validation & linting: dead references, unreachable rooms, circular quests, etc. | [x] |

**See:** [`tooling_infrastructure.md`](tooling_infrastructure.md) for full architecture and design details. Circular quest dependency checking was scoped out — `QuestStageData` has no quest-to-quest dependency field in the schema today.

## Sprint 11 — Browser E2E harness ✅

**Goal:** Catch UI-specific regressions (HTMX swaps, OOB updates, Alpine state) that ASGI-transport integration tests can't see.

| # | Task | Status |
|---|------|--------|
| 11.1 | Browser end-to-end test harness for HTMX UI | [x] `tests/e2e/` — Playwright-driven tests against a real live uvicorn server (background thread, disposable per-test sqlite DB, real world YAML bootstrap). Optional `e2e` extra (`pip install -e ".[e2e]"` + `playwright install chromium`); excluded from the default `pytest`/`make test` run via `-m "not e2e"`; run explicitly with `make test-e2e`. Covers character creation, movement + room/inventory panel updates, and dialogue → quest-start via the Ashmoore dev world golden path. |

## Sprint 12 — Simulation harness MVP ✅

**Goal:** Real-protocol, multi-player scripted scenarios per `architecture.md` §25 — a third test transport alongside ASGI-transport integration tests and the [Sprint 11](#sprint-11--browser-e2e-harness-) browser E2E harness.

| # | Task | Status |
|---|------|--------|
| 12.1 | Simulation harness MVP (`tests/simulation/`) | [x] `virtual_player.py` — `VirtualPlayer` wraps a real `websockets` client against `/ws` (not an ASGI shortcut); `send_command()`/`run_script()` with optional timing jitter, `wait_for_broadcast()` for pushed (non-reply) messages. `conftest.py` — `simulation_server`/`simulation_server_factory` fixtures boot the real app under `uvicorn` on a background thread against a disposable per-test sqlite DB and the real `world_content/world.yaml` (same pattern as [Sprint 11](#sprint-11--browser-e2e-harness-)'s `live_server`, no synthetic world content). `test_multiplayer_scenarios.py` — two real connections: `player_joined` broadcast fan-out on connect, and concurrent `take` of a single-quantity item (no duplication/loss). `test_audit_regression.py` — runs a fixed script against two independent fresh servers and diffs the normalized audit trail, per the "capture, diff after changes" pattern in `architecture.md` §25. New `simulation` pytest marker, excluded from `make test`/plain `pytest` like `e2e` (`make test-simulation`); no new install required (`websockets`/`httpx` were already transitive via `fastapi[standard]`, now declared explicitly in the `dev` extra). Noted but intentionally not fixed here: the raw `/ws` command loop didn't yet re-broadcast `room_messages` to other occupants the way `POST /command` does — fixed by Sprint 14.1. |

## Sprint 13 — Observability & CI quality gates ✅

**Goal:** Regressions can't land silently. Audit §4.2, §5.2.

| # | Task | Status |
|---|------|--------|
| 13.1 | Structured logging (stdlib `logging` with correlation/transaction IDs from `TransactionContext`) | [x] `observability.py` — `configure_logging()` attaches a correlation-aware formatter/filter to the root logger (idempotent, level from new `Settings.log_level`/`LORECRAFT_LOG_LEVEL`); `bind_transaction_context()` publishes a `TransactionContext`'s `transaction_id`/`correlation_id` to a `contextvars.ContextVar` for the duration of one command, so every `log.*` call anywhere in that call stack (services, event handlers, repos) picks the IDs up automatically — no signature threading needed. Wired into both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`) and `create_app()`. |
| 13.2 | Command latency + event-handler timing instrumentation | [x] `CommandEngine._execute_parsed` times each command handler call and stamps `duration_ms` onto the `COMMAND_EXECUTED` audit event payload (`game/engine.py`); `EventBus.emit()` times each handler dispatch, records it on `HandlerResult.duration_ms`, and logs `event=... handler=... duration_ms=... depth=<handlers registered>` at DEBUG (`game/events.py`). New `analytics.command_latency_percentiles()` (p50/p95/p99 from `duration_ms`) + `GET /admin/analytics/latency`. |
| 13.3 | CI: pytest + coverage threshold + basedpyright + ruff as required checks | [x] `.github/workflows/ci.yml` — three required jobs on push/PR to `main`: `quality` (`make lint` + `make typecheck` + `make test-cov`), `simulation` (`make test-simulation`), `e2e` (Playwright + `pytest tests/e2e`). `make test-cov` runs the default suite with `pytest-cov`; `[tool.coverage.report] fail_under = 80` in `pyproject.toml` (current baseline ~82%). New `make lint`/`make typecheck` targets. Fixed a latent bug found while wiring this up: `tests/simulation/*.py`'s `from tests.simulation.conftest import ...` only worked under `python -m pytest` (which prepends cwd to `sys.path`), not bare `pytest` (what `make test-simulation` and CI actually run) — `pythonpath` in `pyproject.toml` now includes `"."` alongside `"src"`. |

## Sprint 14 — Unify command lifecycle ✅

**Goal:** One 13-step transaction/event/audit lifecycle shared by `/ws` and `/command` paths (long-standing `[~]` STATUS item). Easier after [Sprint 8](#sprint-8--module-decomposition-) decomposition.

| # | Task | Status |
|---|------|--------|
| 14.1 | Extract shared lifecycle; both entry points call it; add rollback-on-error semantics | [x] **Rollback-on-error** — `CommandEngine._execute_parsed` (`game/engine.py`) now catches exceptions from the command handler instead of letting them propagate uncaught. On a crash: `GameContext.rollback_state_changes()` (new `rollback_state` callable, wired at both entry points to the DB session's `.rollback`) undoes any half-applied state; `ctx.messages`/`room_messages`/`updates`/`pending_events` are cleared so no partial narration leaks out (architecture.md §26's golden rule: never tell clients something happened until the DB says it happened); a generic error message replaces it; a new `GameEvent.COMMAND_FAILED` audit event (severity ERROR) records the crash. **Broadcast unification** — new `game/broadcast.py`'s `broadcast_command_effects()` is the one place step 12 (room broadcast) now lives; both `main.py`'s `/ws` command loop (now `async`) and `web/frontend.py`'s `POST /command` call it after `CommandEngine.handle_command()` returns, closing the gap [Sprint 12](#sprint-12--simulation-harness-mvp-)'s simulation tests surfaced (the raw `/ws` path never re-broadcast `ctx.room_messages`/`state_change` to other room occupants the way `POST /command` did). Verified with a new simulation test exercising the previously-broken path over a real socket, plus the full existing suite (unit/integration/e2e/simulation) unchanged. **Construction unification (follow-up)** — `game/context.py`'s `build_game_context()` factory (added Sprint 6.3, meant to be "the" `GameContext` construction path) turned out to be unused by both real entry points. Extended it to accept `audit_session` (a separate `Session`, matching real usage — replacing the old same-session `create_audit_repo` bool) and `rollback_state`, and to pass `clock` straight through rather than synthesizing a fallback `WorldClock` (a fabricated clock would be silently wrong data, not a safe default). `main.py` and `web/frontend.py` now both call it instead of constructing `GameContext` inline. |

## Sprint 15 — Core UX completion ✅

**Goal:** Finish the partially-shipped core UX so nothing is left half-done.

| # | Task | Status |
|---|------|--------|
| 15.1 | World clock / weather status bar push via WS | [x] `ConnectionManager.broadcast_global()` + a `TIME_ADVANCED` handler in `main.py` push `time_update` (hour/minute/day/season/weather) to every connected player, not just on connect/reconnect SSR. |
| 15.2 | Multi-player live lists finished (`[~]` STATUS item) | [x] `game/broadcast.py`'s `broadcast_command_effects()` now sends a second `state_change` (`players-online` panel) to the room a player *left*, not just the room they entered — previously occupants of the old room only saw the departure narration text, not a live players-list refresh. |

---

## Foundation exit criteria (gate for Sprints 16+)

All must be true before combat/trading work starts:

- [x] Zero silent `except Exception` blocks in `src/` ([Sprint 5](#sprint-5--error-handling--exception-hierarchy-))
- [x] Zero `cast(GameContext, ctx)` / `cast(Any, ctx)` in `src/`; basedpyright `standard` mode clean ([Sprint 6](#sprint-6--type-safety-))
- [x] One `GameContext` construction path; no optional repo fields — **fixed (2026-07-02):** `build_game_context()` now accepts `audit_session` (a separate `Session`, matching real usage) instead of the old same-session `create_audit_repo` bool, `rollback_state`, and passes `clock` straight through instead of synthesizing a fallback `WorldClock`. Both `main.py`'s `/ws` loop and `web/frontend.py`'s `POST /command` call it instead of constructing `GameContext` inline.
- [x] No module >~500 lines with mixed concerns ([Sprint 8](#sprint-8--module-decomposition-))
- [x] One service wiring convention; no inline `bus.on()` in `main.py` (Sprint 9.2)
- [x] Web + admin layers have integration coverage; CI enforces coverage, types, and lint ([Sprint 7](#sprint-7--web--admin-characterization-tests-) + Sprint 13.3)
- [x] Feature-registration pattern documented and demonstrated (10.4)
- [x] All `[~]` STATUS partials either finished or explicitly retired — [Sprint 14](#sprint-14--unify-command-lifecycle-) closed the `/ws`/`/command` broadcast-lifecycle gap; [Sprint 15](#sprint-15--core-ux-completion-) closed world clock/weather WS push (15.1) and the multi-player live-lists refresh gap on room-leave (15.2)

---

# Engine core band (Tier 1 primitives) — Sprints 16–21

**Engine-first (2026-07-03).** The eight cross-cutting Tier 1 primitives from
[`engine_core.md`](engine_core.md) are built here, **before** the Tier 2 feature modules that
consume them ([Sprints 22](#sprint-22--standard-item-components--definition-fields)+). Rationale: several feature sprints share these primitives; building
them per-sprint yields N opinionated implementations and blurs the framework/game boundary. Order
follows dependency + leverage ([`engine_core.md`](engine_core.md) §6) — the two most expensive to
retrofit (unified item location/ownership, and a seedable `ctx.rng` the audit-regression harness
depends on) go first. These primitives are **content-agnostic**: no named skills, slots, factions,
or damage formulas live here.

## Sprint 16 — Item location/ownership & instance state ✅

**Goal:** One way to say where an item lives and to move it atomically; per-instance state via
registered components. Highest-leverage primitives — they underpin equipment, containers, shop
stock, corpses, and trade escrow. **See [`engine_core.md`](engine_core.md) §3.1–3.2, §4a/§4f.**

| # | Task | Status |
|---|------|--------|
| 16.1 | `ItemStack` + `(owner_type, owner_id, slot?)` location + holder registry; one atomic `ItemLocationService.move()` (rollback-safe); **replace** `Player.inventory`/`RoomItem` outright (column/table deleted — full blast-radius table in [`engine_core.md`](engine_core.md) §3.2) | [x] |
| 16.2 | `ItemInstance` carrier + pluggable component registry (durability/openable/lit/container register like dialogue side-effects); `bound`/soulbound flag | [x] `ComponentRegistry` (`game/components.py`) ships with zero registered components (Tier 1 registers none, per spec); `Item.bound` field added (enforcement deferred to Tier 2). |

**Delivered beyond the two checklist items:** full blast-radius migration (17 files) onto the new
primitive — `services/inventory.py`, `repos/item_repo.py`, `game/context.py`,
`game/command_conditions.py`, `services/movement.py`, `services/quest.py`,
`npc/side_effects.py`, `services/save.py` (v1-save-compatible load), `world/loader.py`,
`world/versioning.py`, `tools/world_cli.py`, `scripts/import_world.py`,
`admin/routers/players.py`, `main.py`, `web/session.py`, `web/frontend.py`. 23 new invariant
unit tests (`tests/unit/test_item_location_service.py`); full existing suite (431 unit/
integration + 3 e2e + 5 simulation, including the audit-regression diff and the
concurrent-take-no-duplication guarantee) green unchanged. See `CHANGELOG.md` for the full
list of bugs caught along the way (typed-error argument order, a missing `StackRepo` flush,
a pydantic recursion bug in `list[JsonValue]` SQLModel fields). Schema migration for
*existing* production DBs (`scripts/migrate_schema_v2.py`, `WorldMeta.schema_version` 1→2) is
scoped out for now — no production deployment exists yet; the dev flow
(`scripts/import_world.py --fresh`) regenerates disposable DBs from YAML instead.

## Sprint 17 — Determinism: seedable RNG & skill-check ✅

**Goal:** All random resolution reproducible so the [Sprint 12](#sprint-12--simulation-harness-mvp-) audit-regression harness can cover
combat/skills/trade. **See [`engine_core.md`](engine_core.md) §3.6, §4b.**

| # | Task | Status |
|---|------|--------|
| 17.1 | Seedable `ctx.rng` service threaded through `GameContext` (per-run seed); lint-ban module-level `random` in feature code | [x] `game/rng.py`'s `GameRng`; one app-wide instance on `AppState` from `Settings.rng_seed`; required `GameContext.rng`/`build_game_context(rng=...)`; `SchedulerEventContext.rng`; `clock/weather.py` converted off `random.choice`. Ruff `TID251` banned-api rule on `random`, scoped to `src/` (test-harness timing jitter exempted). |
| 17.2 | `skill_check(rng, base, difficulty, modifiers) → CheckResult` helper (roll-under d100, 5/95 bounds — one check path for perception/lockpicking/barter/combat) | [x] `game/checks.py`; resolves `effective` via Sprint 18's modifier resolver, clamps target to `[5, 95]`. Landed after Sprint 18 since it needs the `Modifier` type. |

## Sprint 18 — Modifier resolution ✅

**Goal:** One runtime resolver for bonuses from many sources, with a defined stacking order and
caps. Generalizes the doc's `EquipmentEffects.resolve()`. **See [`engine_core.md`](engine_core.md) §3.5, §4d.**

| # | Task | Status |
|---|------|--------|
| 18.1 | Modifier resolver: buckets **flat add → multiplier → clamp/cap**; collects from equipment `effects`, traits, active effects, region; never stored (recompute on change / lazily) | [x] `game/modifiers.py`: `Modifier`/`resolve()` (pure, bucket-ordered) + `ModifierSource`/`ModifierRegistry`/`resolve_for()` (collection). Tier 1 registers no sources — landed ahead of its listed order (18 has no dependencies, per the doc's own build-order table) specifically to unblock Sprint 17.2's `skill_check()`. |

## Sprint 19 — Meters & timed effects ✅

**Goal:** Named bounded clock-tickable resources, and expiring buffs/debuffs — one primitive each,
not one column per resource. **See [`engine_core.md`](engine_core.md) §3.3–3.4.**

| # | Task | Status |
|---|------|--------|
| 19.1 | `Meter` primitive (bounded, optional regen, scheduler tick, `METER_DEPLETED`); migrate `current_hp` (player + NPC) onto it as the proof — `max_hp` stays as the definitional base | [x] `models/meters.py`'s `Meter` + `game/meters.py`'s `MeterDef`/registry + `services/meters.py`'s `MeterService`. "hp" `MeterDef` registered as bootstrap in `main.py`'s lifespan; `PlayerStats.current_hp`/`NPC.current_hp` deleted outright (not deprecated). |
| 19.2 | `ActiveEffect` (clock-driven expiry, swept by scheduler) + trait registry (named boon/bane modifier-bundles) feeding the resolver | [x] `models/meters.py`'s `ActiveEffect` + `game/effects.py`'s `EffectDef`/registry + `services/effects.py`'s `EffectService`; `game/traits.py`'s `TraitDef`/`TraitSource`/registry. Tier 1 registers one `TraitSource` (active effects' `grants_traits`) and two `ModifierSource`s (active-effect, trait) with Sprint 18's resolver — the §3.5 promise fulfilled. |

**Delivered beyond the two checklist items:** full HP-migration blast radius (`world/loader.py`,
`admin/routers/world.py`, `services/save.py` — v1/v2 save-snapshot compat); `GameContext` gained
required `session`/`meters`/`effects` fields (`build_game_context()` factory pattern held); 25 new
invariant tests caught two real bugs (both `_on_time_advanced` sweeps read ORM attributes after
`session.commit()`'s default `expire_on_commit` invalidated them — fixed by capturing plain values
before the session closes). See `CHANGELOG.md` for the full list.

## Sprint 20 — Ledger & atomic transfer ✅

**Goal:** A coin balance on any holder + one atomic multi-party transfer for coins *and* items.
**See [`engine_core.md`](engine_core.md) §3.7, §4c/§4g.**

| # | Task | Status |
|---|------|--------|
| 20.1 | `CoinBalance` on any registered holder (player/bank/corpse/shop); atomic multi-leg `execute_exchange(legs)` — validate all, then apply all (escrow = accept-time revalidation), reusing the [Sprint 14](#sprint-14--unify-command-lifecycle-) rollback; integrity gates via `RuleEngine` (fail-closed), not conditions | [x] `models/ledger.py`'s `CoinBalance` + `services/ledger.py`'s `LedgerService` (stateless-per-call, no engine/rng held). `execute_exchange(legs)` validates every leg first, then applies all mutations — no partial exchange ever lands. `GameContext` gained a required `ledger` field. 14 new tests, all green first run. |

## Sprint 21 — Scheduled moving entity ("moving room") ✅

**Goal:** The moving-room carrier transit rides on; also serves wandering NPCs/patrols later.
**See [`engine_core.md`](engine_core.md) §3.8.**

| # | Task | Status |
|---|------|--------|
| 21.1 | Scheduled moving-room carrier + position-interpolation state machine (`at_stop → in_transit → arrive`, reverse/loop) + position push; line semantics (express/local, tickets, weather) stay Tier 2 ([Sprint 29](#sprint-29--transit--travel-systems)) | [x] `models/mobile.py`'s `MobileRouteState` (only the runtime state is persisted) + `services/mobile_route.py`'s `Waypoint`/`RouteSpec`/`RouteHooks`/`MobileRouteService` (engine-holding schedulable, exactly the `SchedulerService` shape — reuses it for all timing via `job_type="mobile_route"`). Ping-pong reversal and circular looping both covered; a route whose spec disappears on restart halts instead of crashing. 15 new tests, all green first run. |

---

# Feature band (Sprints 22+) — Tier 2 modules & content, gated on foundation exit criteria

**Re-sequenced 2026-07-03** to reflect Lorecraft's design pillars — **Exploration > Trading >
Questing > Puzzle-solving, with combat as a *supporting* system, not the centerpiece** (see
[`wishlist.md`](wishlist.md) → *Design pillars*). The old sequence front-loaded combat
(Sprints 18–20 of the previous plan); the new sequence front-loads the systems those pillars
depend on — item state, inventory/equipment, exploration, traits/skills — and moves combat
below trading/transit/quests as a fallback resolution path rather than the main loop.

Ordering follows dependencies: item state → equipment → traits/skills/exploration → condition
→ trade → transit → quests/puzzles → combat → PvP. UI polish (map, mobile) sits alongside
exploration, which it serves.

> **Engine-first (2026-07-03):** the feature band decomposes into **Tier 1 engine primitives →
> Tier 2 standard modules → Tier 3 content** per [`engine_core.md`](engine_core.md) — the anchor
> doc for the framework/game boundary. Directive: **design Tier 1 now, implement most of Tier 1
> before Tier 2.** Eight cross-cutting primitives (item location/ownership, component state,
> meters, timed effects, modifier resolver, seedable RNG + skill-check, ledger/atomic transfer,
> moving-entity) sit underneath [Sprints 22–35](#sprint-22--standard-item-components--definition-fields); building them per-sprint would yield N opinionated
> implementations and blur the boundary. The two most expensive to retrofit — the unified item
> location/ownership model and a seedable `ctx.rng` (audit-regression-critical) — go first. See
> [`engine_core.md`](engine_core.md) §3 (primitives), §4 (cross-doc surprises caught), §6 (build
> order). The Tier 1 work is now sequenced as **[Sprints 16–21](#sprint-16--item-locationownership--instance-state)** (the Engine core band below); the
> Tier 2 feature band shifts to **[Sprints 22–35](#sprint-22--standard-item-components--definition-fields)**.

> **Design docs:** [`engine_core.md`](engine_core.md) (Tier boundary + Tier 1 primitives — read first),
> [`inventory_equipment.md`](inventory_equipment.md) ([Sprints 22–23](#sprint-22--standard-item-components--definition-fields)),
> [`combat_system.md`](combat_system.md) (stat/skill model + combat sprints),
> [`death_resurrection.md`](death_resurrection.md) ([Sprint 31](#sprint-31--combat-core-services-supporting-system) death penalty),
> [`dialogue_npcs_quests.md`](dialogue_npcs_quests.md) and
> [`feature-registration.md`](feature-registration.md) (quests/puzzles, pluggable
> registries), [`transit_systems.md`](transit_systems.md) ([Sprint 29](#sprint-29--transit--travel-systems)), and
> [`trade_economy.md`](trade_economy.md) ([Sprint 28](#sprint-28--trading--economy)). The signature systems now all have
> design docs.

## Sprint 22 — Standard item components & definition fields

**Goal:** *Tier 2 realization* of item content on the [Sprint 16](#sprint-16--item-locationownership--instance-state) engine model — the deferred
Sprint 2.5 `open`/container/state prerequisite. The per-instance carrier, item-location model, and
component registry are **Tier 1 ([Sprint 16](#sprint-16--item-locationownership--instance-state))**; this sprint adds the Layer A `Item` definition
fields and the *standard components* (durability, light, container, openable) on top, so items can
be worn, burned, opened, and puzzle-wired. **See [`engine_core.md`](engine_core.md) §3.1–3.2 and
[`inventory_equipment.md`](inventory_equipment.md) §7.**

| # | Task | Status |
|---|------|--------|
| 22.1 | Layer A item fields (`slot`, `weight`, `wearable`, `quality`, `max_durability`, `light`, `capacity`, `effects`, `bound`) on `Item`; YAML loader + validators | [x] |
| 22.2 | Register durability/`is_open`/`lit`/container as **standard components** on the [Sprint 16](#sprint-16--item-locationownership--instance-state) `ItemInstance`/component model; `open` + state verbs (stateless stackables stay as ID stacks) | [x] |

## Sprint 23 — Inventory & equipment ✅

**Goal:** Wear/wield slots, encumbrance, containers. Equipment grants **non-combat** effects
(light, warmth, carry, skill/trait bonuses) resolved at runtime. **See [`inventory_equipment.md`](inventory_equipment.md) §3–6, §9.**

| # | Task | Status |
|---|------|--------|
| 23.1 | `wear`/`remove`/`wield`/`unwield`/`equipment` commands via `InventoryService`; `ITEM_EQUIPPED`/`ITEM_UNEQUIPPED` events | [x] Equipped-ness is a location (slot on the player's own `ItemStack`), not a `Player.equipment` column — supersedes that earlier draft, per `inventory_equipment.md`'s binding "decided" storage spec |
| 23.2 | Encumbrance bands from weight + `carry_bonus`; equipment effects resolved at runtime (never stored) | [x] `game/equipment_source.py` + `game/encumbrance.py` |
| 23.3 | Containers: `put in` / `take from`, nesting, worn-container capacity; light/darkness gate (`Room.light_level` + lit source) | [x] |

## Sprint 24 — Traits & skills ✅

**Goal:** Character identity that gates exploration and social play. Use-based skills, a trait
registry (boons/banes), reputation/NPC-standing. Builds on existing `PlayerStats` (attributes
+ `skills` dict). **See [`combat_system.md`](combat_system.md) stat model + [`wishlist.md`](wishlist.md).**

| # | Task | Status |
|---|------|--------|
| 24.1 | Trait registry (pluggable, like dialogue side-effects); traits from equipment/background/earned; boon+bane modifiers | [x] `game/standard_traits.py`'s `InnateTraitSource` + 5 illustrative traits; `services/traits.py` grant/revoke |
| 24.2 | Use-based skill improvement (perception, lockpicking, bartering, cartography, survival, persuasion); skill-check helper | [x] `game/skills.py` (identity) + `services/skills.py` (improvement); `skill_check()` itself shipped Sprint 17-18 |
| 24.3 | Reputation/standing per NPC + faction; unlocks dialogue/prices/quests (extends flags + NPC memory) | [x] `models/reputation.py` + `game/reputation_conditions.py` |

## Sprint 25 — Exploration depth ✅

**Goal:** Make discovery a first-class reward (the top pillar). Search-gated secrets, terrain,
journal, cartography. Builds on existing minimap fog and `Exit.hidden`/`condition_flags`.

| # | Task | Status |
|---|------|--------|
| 25.1 | `search` command + hidden-exit/secret-room reveal gated on perception skill + traits + light; discovery rewards (knowledge flags, progression tick) | [x] Also fixed: hidden exits were unconditionally blocked and `condition_flags` was never enforced — both pre-existing bugs |
| 25.2 | Terrain types on rooms/exits affecting travel time, fatigue cost, and required skill/gear; environmental `examine` layering | [x] `Room.terrain` + `game/terrain.py`; required-skill gate + `look` description suffix. Travel-time/fatigue-cost hooks deferred to Sprint 27 (fatigue doesn't exist yet) |
| 25.3 | Journal / auto-log panel (discovered places, met NPCs, learned lore, active clues); player cartography reveal | [x] `journal` command. Cartography map-reveal payoff deferred to Sprint 26 (owns the map UI it reveals onto) |

## Sprint 26 — Map & mobile UI ✅

**Goal:** UI polish that serves exploration (was Sprints 16–17 of the previous plan).

| # | Task | Status |
|---|------|--------|
| 26.1 | Full-screen map modal (pan/zoom), integrated with cartography reveal | [x] `partials/map_modal.html`; drag-to-pan/scroll-to-zoom via Alpine; cartography-gated reveal of known-but-unvisited rooms in `build_map_data()` |
| 26.2 | Responsive mobile tab layout | [x] Bottom tab bar (Room/Feed/Players) below `lg`; verified in a real headless-Chromium browser |

## Sprint 27 — Character condition (fatigue / sleep)

**Goal:** Light survival texture that rewards planning; per-world toggle, not punishing. Runs
on `SchedulerService` + `TIME_ADVANCED`. **See [`wishlist.md`](wishlist.md) → Character condition.**

| # | Task | Status |
|---|------|--------|
| 27.1 | Fatigue/stamina drained by travel/encumbrance/actions; low fatigue penalizes skill checks; `rest`/`sleep`/`camp` | [x] `game/fatigue_source.py`'s "fatigue" `MeterDef` (stamina, scales with fortitude) + `FatigueModifierSource` (flat `mult` penalty on every registered skill once stamina drops below 50%/20% thresholds); `services/fatigue.py`'s `FatigueService` drains on `PLAYER_MOVED` (more when burdened/overloaded per Sprint 23.2 encumbrance bands) and backs `rest`/`camp`/`sleep` (`commands/condition.py`) |
| 27.2 | Sleep advances time + restores fatigue + dream/lore hook; safe vs. unsafe sleep; warmth/exposure via weather + worn clothing | [x] New `Room.safe_rest` field: `sleep` there always succeeds (full restore, 8h clock-advance, dream); elsewhere it's a `survival` `skill_check` (harder in cold weather — `clock/weather.py`'s `COLD_WEATHERS` — offset by resolved `warmth`), failing into a shorter, partial, dreamless "interrupted" rest. `game/warmth.py` + a new `warmth_bonus` item effect (`game/item_effects.py`) give worn clothing a non-combat purpose. Dream flavor references a random `lore:`-flagged discovery (Sprint 25.3) when the player has one. |

## Sprint 28 — Trading & economy

**Goal:** A living economy where *where* you buy/sell matters (pillar #2). Currency → NPC shops
→ regional pricing → banks. **Signature pairing:** the transit network ([Sprint 29](#sprint-29--transit--travel-systems)) is the trade
network. **See [`trade_economy.md`](trade_economy.md).**

| # | Task | Status |
|---|------|--------|
| 28.1 | Currency model (carried `coins`); item `value` × `quality` pricing; NPC vendor shops (`buy`/`sell`/`list`), bartering skill + reputation flex price | [x] New `Shop`/`ShopStock` tables (`models/economy.py`) attached to an NPC via world YAML `shop:` block; a shop's cash is `CoinBalance("shop", shop.id)` (new "shop" holder type, `game/economy_holders.py`), seeded once at import (idempotent re-import guard) via `LedgerService.credit`. `services/economy.py`'s `EconomyService` derives `buy_price = value × quality_mult × region_mult × (1 - barter_discount) × (1 - rep_discount)` and `sell_price = buy_price × sell_ratio` at runtime (never stored); every coin/item movement is one `LedgerService.execute_exchange` call (sold items are `destroy()`ed, not held as physical shop stock — `ShopStock.quantity` is listing state only). `list`/`shop`, `buy`, `sell`, `appraise` commands (`commands/economy.py`). Mira the innkeeper is a working shop in `world_content/world.yaml`. 15 new unit tests + a world-loader round-trip test. |
| 28.2 | Regional price differences + per-good bias + finite stock restocking on the world clock (buy-low/sell-high loop) | [x] New `RegionPricing` table (world YAML `economy.regions`) contributes an area-wide `region_mult` + per-item `bias` on top of a shop's own `region_mult`; `EconomyService._demand_mult()` reads current stock against `restock_to` (depleted costs more, flooded costs less, bounded to [0.5, 1.5]). `services/restock.py`'s `RestockService` (scheduler-driven, same shape as `LightFuelService`) counts `TIME_ADVANCED` ticks per `ShopStock` row and jumps `quantity` to `restock_to` once `restock_every_ticks` elapses. 12 new unit tests + a world-loader region round-trip test. |
| 28.3 | Banks: `BankAccount`, `deposit`/`withdraw`/`balance` at branches, one account/many branches (safe from death & robbery) | [ ] |
| 28.4 | Player-to-player `offer`/`accept` trade handshake (atomic escrow swap; multi-player transaction safety) | [ ] |

## Sprint 29 — Transit & travel systems

**Goal:** The signature Materia-Magica-inspired feature — multiple travel modes between areas
(ferry, rail, balloon, caravan) that are slow or fast, run end-to-end (express) or make multiple
stops (local), and animate on the minimap. Built on scheduler + world clock + weather + WS push.
**See [`transit_systems.md`](transit_systems.md).**

| # | Task | Status |
|---|------|--------|
| 29.1 | Data model (`TransitLine`/`TransitStop`/`TransitVehicleState`) + YAML `transit:` section + validators; data-driven modes/speeds/stopping patterns | [ ] |
| 29.2 | Scheduler-driven vehicle state machine (at_stop→in_transit→arrive, reverse/loop); moving-room `board`/`disembark`/`schedule`; ticket-item gating | [ ] |
| 29.3 | `transit_update` WS message + minimap marker animation (interpolated between stop coords); weather grounding/delay (balloon/ferry) | [ ] |

## Sprint 30 — Quests & puzzles depth

**Goal:** Branching, consequence-bearing quests and environmental/lore puzzles (pillars #3–4).
Extends the stage/flag quest system with branch conditions and mechanism puzzles.

| # | Task | Status |
|---|------|--------|
| 30.1 | Branch conditions + consequence side-effects on quests (world-state/standing changes); NPC memory of past interactions | [ ] |
| 30.2 | Mechanism & item-combination puzzles on `ItemInstance.state` (levers, dials, sequences) via pluggable conditions/side-effects; timed clock-driven quest events | [ ] |

## Sprint 31 — Combat core services (supporting system)

**Goal:** Server-side combat resolution, no commands/UI yet. First consumer of the
feature-registration pattern (10.4), reading equipment-derived stats. **Deliberately below
trade/transit/quests** — combat serves stories, it isn't the loop. **See [`combat_system.md`](combat_system.md)
and [`death_resurrection.md`](death_resurrection.md).**

| # | Task | Status |
|---|------|--------|
| 31.1 | `services/combat.py` — sessions, ticks, damage | [ ] |
| 31.2 | Death & resurrection ([`death_resurrection.md`](death_resurrection.md)): resurrect at `respawn_room_id`, lose a % of *carried* coins + drop unequipped loot into a corpse container (banked/equipped/bound safe); corpse retrieval + decay; weakened debuff | [ ] |
| 31.3 | `npc/combat_ai.py` — behavior modes from YAML | [ ] |

## Sprint 32 — Combat commands + UI (avoidance-first)

**Goal:** Combat as one resolution among several — stealth/persuasion/bribery/flee are
first-class alternatives; non-lethal outcomes supported.

| # | Task | Status |
|---|------|--------|
| 32.1 | `commands/combat.py` — `attack`, `flee`; non-lethal outcomes (subdue/intimidate/drive-off); complete condition eval (`NPC_PRESENT`, `HAS_COMBAT_TARGET`) | [ ] |
| 32.2 | Combat UI in HTMX feed + status panel | [ ] |

## Sprint 33 — Combat testing

| # | Task | Status |
|---|------|--------|
| 33.1 | Integration + browser tests for combat loop and avoidance/non-lethal paths | [ ] |

## Sprint 34 — PvP consent

**Goal:** Consent-based, opt-in PvP reusing the combat system. Soft by default.

| # | Task | Status |
|---|------|--------|
| 34.1 | PvP consent + challenge/accept | [ ] |

## Sprint 35 — Multiplayer trade / PvP / transit tests

| # | Task | Status |
|---|------|--------|
| 35.1 | Multi-player trade, PvP consent, and shared-vehicle transit simulation tests | [ ] |

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| ~~Bug/todo letterbox~~ | Implemented in [Sprint 10.5](#sprint-105--tooling-infrastructure-) as issues tracking system |
| Inventory encumbrance / wear slots | After equipment + combat |
| `lorecraft.tools.simulation` CLI (JSON scenario files, N-bot load runs, latency/throughput reports) | Enhancement on top of the Sprint 12.1 pytest-based harness; see `tooling_infrastructure.md` §5 |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| Player-facing bug reports | In-game `/report-bug` command (after core issues system stable) |
| Analytics dashboard & visualizations | After [Sprint 13](#sprint-13--observability--ci-quality-gates-) instrumentation ([Sprint 14](#sprint-14--unify-command-lifecycle-)+) |
| Database inspector / state editor | Admin tool for advanced troubleshooting (Post-foundation) |

---

## Build-order reference

See `docs/architecture.md` §28 for the original phase order, and `CODE_AUDIT.md` for the audit driving the foundation band. Order: player authentication ([Sprint 4](#sprint-4--player-authentication-production-hardening-)) → foundation hardening ([Sprints 5–15](#sprint-5--error-handling--exception-hierarchy-)) → **foundation gate** → **Tier 1 engine primitives ([Sprints 16–21](#sprint-16--item-locationownership--instance-state), [`engine_core.md`](engine_core.md))** → item components & equipment (22–23) → traits/skills & exploration + UI (24–26) → condition/trade/transit (27–29) → quests & puzzles (30) → combat (31–33) → PvP + multiplayer tests (34–35).

**Note (2026-07-03):** the feature band was re-sequenced from the original combat-first order to a pillar-driven order (Exploration > Trading > Questing > Puzzles; combat supporting). `architecture.md` §28's phase list predates this and is kept for historical reference — this roadmap is authoritative for sequencing.

---

## Playtesting (Ashmoore dev world)

`start.sh` copies `test_dbs/lorecraft-dev-game.db`, which is built from `world_content/world.yaml`.

Regenerate after world edits:

```bash
python scripts/import_world.py --fresh --db test_dbs/lorecraft-dev-game.db
```

**Starting room:** `village_square` as `player-1`

| Try | Command |
|-----|---------|
| Move east | `go east` → market stalls |
| Pick up coin | `take coin` |
| Talk to Mira | `go west` → Wandering Crow Inn, then `talk mira` |
| Quest hook | Choose "Any news around town?" in dialogue |

Empty databases import `world_content/world.yaml` on startup (configurable via `LORECRAFT_WORLD_YAML_PATH`). Integration tests use the same Ashmoore data — no parallel hardcoded world in production code.

---

*Last updated: 2026-07-04 — **[Sprints 20](#sprint-20--ledger--atomic-transfer-) and [21](#sprint-21--scheduled-moving-entity-moving-room-) complete**, closing out the Tier 1 engine-core band. `models/ledger.py`'s `CoinBalance` + `services/ledger.py`'s `LedgerService` add coin balances on any registered holder and one atomic multi-leg `execute_exchange()` for coins and items together (validate-all-then-apply-all, no partial exchange). `models/mobile.py`'s `MobileRouteState` + `services/mobile_route.py`'s `MobileRouteService` add the generic scheduled route runner (ping-pong or circular waypoint cycling, position interpolation, pluggable `RouteHooks`) that transit will ride on — reuses `SchedulerService` for all timing, no second timing mechanism. 29 new tests, all green first run; full suite (538 unit/integration + 3 e2e + 5 simulation) green. Version bumped to 0.3.0. Tier 2 feature band now open, starting at [Sprint 22](#sprint-22--standard-item-components--definition-fields).

Earlier — **[Sprint 19](#sprint-19--meters--timed-effects-) complete**: `models/meters.py`'s `Meter`/`ActiveEffect` + `game/meters.py`/`game/effects.py`/`game/traits.py` registries + `services/meters.py`/`services/effects.py` are the meter, timed-effect, and trait primitives — the "hp" `MeterDef` migration deletes `PlayerStats.current_hp`/`NPC.current_hp` outright as the proof, and Tier 1 registers its promised active-effect/trait `ModifierSource`s + `TraitSource` with Sprint 18's resolver. `GameContext` gained required `session`/`meters`/`effects` fields. 25 new tests caught two real bugs (both scheduler sweeps read expired ORM attributes after `session.commit()`). Full suite (509 unit/integration + 3 e2e + 5 simulation) green.

Earlier same day — **[Sprints 17](#sprint-17--determinism-seedable-rng--skill-check-) and [18](#sprint-18--modifier-resolution-) complete**: `game/rng.py`'s `GameRng` is now the one sanctioned randomness source (ruff `TID251` bans bare `random` in `src/`), threaded through `GameContext`/`build_game_context()`/`SchedulerEventContext`/`clock/weather.py`; `game/modifiers.py`'s `resolve()` is the one stacked-bonus resolver (fixed add→mult→clamp bucket order); `game/checks.py`'s `skill_check()` composes both into the one roll-under-d100 helper every future skill/combat/barter check will share. 18 landed ahead of its listed position (it has no dependencies) specifically to unblock 17.2, which needs the `Modifier` type. 21 new unit tests; full suite green.

Earlier same day — **[Sprint 16](#sprint-16--item-locationownership--instance-state) complete**: `ItemStack`/`ItemInstance` unified item location/ownership model + `ItemLocationService` (spawn/destroy/materialize/move) ships, replacing `Player.inventory`/`RoomItem` outright across the full 17-file blast radius (see `engine_core.md` §3.2's table). `ComponentRegistry`/`HolderRegistry` scaffolded per spec (Tier 1 registers no components, three built-in holder types). 23 new invariant tests; full unit/integration/e2e/simulation suite green unchanged (no audit-event schema drift).

Earlier same day — **Design docs are now implementation-ready** (deep-dive revision for handoff): [`engine_core.md`](engine_core.md) §3 carries full Tier 1 specs (schemas, APIs, invariants, migration blast-radius tables, per-sprint tests); [`combat_system.md`](combat_system.md) rewritten off the pre-Tier-1 code (seeded rng, hp meter, slot-based weapon, real event names); [`inventory_equipment.md`](inventory_equipment.md), [`trade_economy.md`](trade_economy.md), [`transit_systems.md`](transit_systems.md), and [`death_resurrection.md`](death_resurrection.md) aligned to the primitives (superseded drafts called out inline; engine_core §4 lists every resolution). Earlier same day: inserted an engine-first **Tier 1 primitives band ([Sprints 16–21](#sprint-16--item-locationownership--instance-state))** ahead of the feature modules per [`engine_core.md`](engine_core.md), and **renumbered the feature band +6 to [Sprints 22–35](#sprint-22--standard-item-components--definition-fields)** (item components 22, equipment 23, traits/skills 24, exploration 25, map/mobile 26, condition 27, trade 28, transit 29, quests/puzzles 30, combat 31–33, PvP 34, multiplayer tests 35). Sprint refs in the feature design docs + `wishlist.md` were updated to match. Earlier same day: added `engine_core.md` (Tier 1/2/3 boundary); re-sequenced the feature band around design pillars (Exploration > Trading > Questing > Puzzles; combat supporting). [Sprints 4–15](#sprint-4--player-authentication-production-hardening-) complete; foundation gate green.*
