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

Sprints 1–3 closed out HTMX parity, command-depth gaps, and the scheduler foundation. A full code audit (`CODE_AUDIT.md`, 2026-07-01, revalidated against source) identified the engineering debt to clear next.

**Current:** Sprints 4–15 complete (player authentication, error handling, type safety, characterization tests, module decomposition, service consistency/wiring, extensibility seams, tooling infrastructure, browser E2E harness, simulation harness MVP, observability & CI quality gates, unified command lifecycle, core UX completion). **Foundation gate is green** — see exit criteria below. The feature band (Sprints 16+) was **re-sequenced 2026-07-03** around Lorecraft's design pillars (Exploration > Trading > Questing > Puzzles; combat is a supporting system, not the centerpiece): item state & inventory/equipment (16–17) → traits/skills & exploration (18–20) → condition/trade/transit (21–23) → quests/puzzles (24) → combat/PvP (25–29). See [`wishlist.md`](wishlist.md) for the pillars and mechanics menu.

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
| 4.6 | Retire legacy `?player_id=` query param fallback (was gated by `LORECRAFT_ALLOW_QUERY_PLAYER_ID`) | [x] `Settings.allow_query_player_id` now defaults to `False`. Not deleted outright — kept as an explicit opt-in for test fixtures that intentionally exercise the wire protocol directly (`tests/simulation/`'s `VirtualPlayer`, several state-resolution integration tests), since removing it would break the Sprint 11/12 harnesses for no real security benefit (trusted local test processes, not real clients). Surfaced and fixed a chicken-and-egg bug: `GET /lobby` depended on `get_current_player`, which now 401s with no session — meaning a brand-new visitor couldn't reach the page that lets them log in. New `get_current_player_optional()` fixes this for `/lobby` only; every other route correctly keeps requiring a session. |
| 4.7 | OAuth extensibility hooks (Google OIDC callback stubs for future LAN-party deployments) | [x] `POST /auth/oauth/{provider}/callback` stub — `PlayerAuth.provider`/`provider_subject` already generalize to non-local providers with no schema change needed. Returns 501 rather than pretending to implement OAuth (needs a registered client id/secret/redirect URI this engine doesn't have configured); not wired into any client. |
| 4.8 | Integration tests: login, token refresh, WS ticket validation, expired token rejection | [x] `tests/integration/test_player_authentication.py` (15 tests) + `tests/unit/test_player_login.py` (9 tests) + updated `tests/integration/test_player_session.py` for the new password-protected lobby. Covers account creation/verification/wrong-password, refresh rotation + expired/garbage/wrong-type rejection, ws-ticket issuance (bearer + cookie) + single-use + TTL expiry + expired-access-token rejection, and the OAuth stub. Full suite (unit/integration/e2e/simulation) green throughout — the e2e run caught the `/lobby` chicken-and-egg bug above before it could ship. |

**Also done, beyond the numbered checklist:** the browser lobby (`/lobby/enter`, `/lobby/create`) is now password-protected — previously `/lobby`'s "Join a World" tab was a one-click player picker with *zero* authentication (anyone could enter as any existing character), which the numbered tasks above don't explicitly cover but would have left the real player-facing surface unprotected even with the API-level auth in place. `login_or_register()` gained `allow_create: bool` so `/lobby/enter` ("Log In") 404s on a genuinely unknown username instead of silently creating one, while `/lobby/create` keeps create-or-claim semantics. `app.js`'s `connectWebSocket()` now fetches a ws-ticket before connecting instead of using a raw `?player_id=`.

---

# Foundation band (Sprints 5–15)

Work queue derived from `CODE_AUDIT.md`. Ordering is deliberate: error/type groundwork first, then **characterization tests before the big refactors**, then structure, then tooling.

**Current progress:** Sprints 5–15 complete (error handling, type safety, characterization tests, module decomposition, service consistency/wiring, extensibility seams, tooling infrastructure, browser E2E harness, simulation harness MVP, observability & CI quality gates, unified command lifecycle, core UX completion). Foundation band done — see exit criteria below.

## Sprint 5 — Error handling & exception hierarchy ✅

**Goal:** One error-handling style everywhere. Audit §2.1.

| # | Task | Status |
|---|------|--------|
| 5.1 | `lorecraft/errors.py` — `GameError`, `ValidationError`, `NotFoundError`, `PermissionError`, `ConflictError` (with machine-readable `code`) | [x] |
| 5.2 | Eliminate the 22 silent `except Exception` blocks: catch specific exceptions, log all of them (`web/frontend.py` ×12, `web/player_auth.py`, `admin/websocket.py` ×3, `admin/auth.py` ×2) | [x] |
| 5.3 | Services raise typed errors; command handlers translate to `ctx.say()` in one shared wrapper | [~] prepared via errors.py; integration in Sprint 9 |
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

**Goal:** Lock in current behavior *before* the Sprint 8–9 refactors. Audit §2.3.

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

**Goal:** Admin/dev tooling foundation: repo-tracked issues & news, world CLI suite, analytics API, content validation. Unblocks Sprint 11+ (can log failures, record metrics, validate content).

| # | Task | Status |
|---|------|--------|
| 10.5.1 | Issues system: `docs/issues.yaml`, CRUD routes, admin TUI (F6) + web panel tabs | [x] |
| 10.5.2 | News & announcements: `docs/news.yaml`, in-game `/news`, RSS feed, admin UI (TUI F7) | [x] |
| 10.5.3 | World management CLI: import/export/validate/diff/stats commands; call from admin world manager | [x] |
| 10.5.4 | Analytics API foundation: metric queries ready (no dashboard yet, driven by Sprint 13 instrumentation) | [x] |
| 10.5.5 | Content validation & linting: dead references, unreachable rooms, circular quests, etc. | [x] |

**See:** [`tooling_infrastructure.md`](tooling_infrastructure.md) for full architecture and design details. Circular quest dependency checking was scoped out — `QuestStageData` has no quest-to-quest dependency field in the schema today.

## Sprint 11 — Browser E2E harness ✅

**Goal:** Catch UI-specific regressions (HTMX swaps, OOB updates, Alpine state) that ASGI-transport integration tests can't see.

| # | Task | Status |
|---|------|--------|
| 11.1 | Browser end-to-end test harness for HTMX UI | [x] `tests/e2e/` — Playwright-driven tests against a real live uvicorn server (background thread, disposable per-test sqlite DB, real world YAML bootstrap). Optional `e2e` extra (`pip install -e ".[e2e]"` + `playwright install chromium`); excluded from the default `pytest`/`make test` run via `-m "not e2e"`; run explicitly with `make test-e2e`. Covers character creation, movement + room/inventory panel updates, and dialogue → quest-start via the Ashmoore dev world golden path. |

## Sprint 12 — Simulation harness MVP ✅

**Goal:** Real-protocol, multi-player scripted scenarios per `architecture.md` §25 — a third test transport alongside ASGI-transport integration tests and the Sprint 11 browser E2E harness.

| # | Task | Status |
|---|------|--------|
| 12.1 | Simulation harness MVP (`tests/simulation/`) | [x] `virtual_player.py` — `VirtualPlayer` wraps a real `websockets` client against `/ws` (not an ASGI shortcut); `send_command()`/`run_script()` with optional timing jitter, `wait_for_broadcast()` for pushed (non-reply) messages. `conftest.py` — `simulation_server`/`simulation_server_factory` fixtures boot the real app under `uvicorn` on a background thread against a disposable per-test sqlite DB and the real `world_content/world.yaml` (same pattern as Sprint 11's `live_server`, no synthetic world content). `test_multiplayer_scenarios.py` — two real connections: `player_joined` broadcast fan-out on connect, and concurrent `take` of a single-quantity item (no duplication/loss). `test_audit_regression.py` — runs a fixed script against two independent fresh servers and diffs the normalized audit trail, per the "capture, diff after changes" pattern in `architecture.md` §25. New `simulation` pytest marker, excluded from `make test`/plain `pytest` like `e2e` (`make test-simulation`); no new install required (`websockets`/`httpx` were already transitive via `fastapi[standard]`, now declared explicitly in the `dev` extra). Noted but intentionally not fixed here: the raw `/ws` command loop didn't yet re-broadcast `room_messages` to other occupants the way `POST /command` does — fixed by Sprint 14.1. |

## Sprint 13 — Observability & CI quality gates ✅

**Goal:** Regressions can't land silently. Audit §4.2, §5.2.

| # | Task | Status |
|---|------|--------|
| 13.1 | Structured logging (stdlib `logging` with correlation/transaction IDs from `TransactionContext`) | [x] `observability.py` — `configure_logging()` attaches a correlation-aware formatter/filter to the root logger (idempotent, level from new `Settings.log_level`/`LORECRAFT_LOG_LEVEL`); `bind_transaction_context()` publishes a `TransactionContext`'s `transaction_id`/`correlation_id` to a `contextvars.ContextVar` for the duration of one command, so every `log.*` call anywhere in that call stack (services, event handlers, repos) picks the IDs up automatically — no signature threading needed. Wired into both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`) and `create_app()`. |
| 13.2 | Command latency + event-handler timing instrumentation | [x] `CommandEngine._execute_parsed` times each command handler call and stamps `duration_ms` onto the `COMMAND_EXECUTED` audit event payload (`game/engine.py`); `EventBus.emit()` times each handler dispatch, records it on `HandlerResult.duration_ms`, and logs `event=... handler=... duration_ms=... depth=<handlers registered>` at DEBUG (`game/events.py`). New `analytics.command_latency_percentiles()` (p50/p95/p99 from `duration_ms`) + `GET /admin/analytics/latency`. |
| 13.3 | CI: pytest + coverage threshold + basedpyright + ruff as required checks | [x] `.github/workflows/ci.yml` — three required jobs on push/PR to `main`: `quality` (`make lint` + `make typecheck` + `make test-cov`), `simulation` (`make test-simulation`), `e2e` (Playwright + `pytest tests/e2e`). `make test-cov` runs the default suite with `pytest-cov`; `[tool.coverage.report] fail_under = 80` in `pyproject.toml` (current baseline ~82%). New `make lint`/`make typecheck` targets. Fixed a latent bug found while wiring this up: `tests/simulation/*.py`'s `from tests.simulation.conftest import ...` only worked under `python -m pytest` (which prepends cwd to `sys.path`), not bare `pytest` (what `make test-simulation` and CI actually run) — `pythonpath` in `pyproject.toml` now includes `"."` alongside `"src"`. |

## Sprint 14 — Unify command lifecycle ✅

**Goal:** One 13-step transaction/event/audit lifecycle shared by `/ws` and `/command` paths (long-standing `[~]` STATUS item). Easier after Sprint 8 decomposition.

| # | Task | Status |
|---|------|--------|
| 14.1 | Extract shared lifecycle; both entry points call it; add rollback-on-error semantics | [x] **Rollback-on-error** — `CommandEngine._execute_parsed` (`game/engine.py`) now catches exceptions from the command handler instead of letting them propagate uncaught. On a crash: `GameContext.rollback_state_changes()` (new `rollback_state` callable, wired at both entry points to the DB session's `.rollback`) undoes any half-applied state; `ctx.messages`/`room_messages`/`updates`/`pending_events` are cleared so no partial narration leaks out (architecture.md §26's golden rule: never tell clients something happened until the DB says it happened); a generic error message replaces it; a new `GameEvent.COMMAND_FAILED` audit event (severity ERROR) records the crash. **Broadcast unification** — new `game/broadcast.py`'s `broadcast_command_effects()` is the one place step 12 (room broadcast) now lives; both `main.py`'s `/ws` command loop (now `async`) and `web/frontend.py`'s `POST /command` call it after `CommandEngine.handle_command()` returns, closing the gap Sprint 12's simulation tests surfaced (the raw `/ws` path never re-broadcast `ctx.room_messages`/`state_change` to other room occupants the way `POST /command` did). Verified with a new simulation test exercising the previously-broken path over a real socket, plus the full existing suite (unit/integration/e2e/simulation) unchanged. **Construction unification (follow-up)** — `game/context.py`'s `build_game_context()` factory (added Sprint 6.3, meant to be "the" `GameContext` construction path) turned out to be unused by both real entry points. Extended it to accept `audit_session` (a separate `Session`, matching real usage — replacing the old same-session `create_audit_repo` bool) and `rollback_state`, and to pass `clock` straight through rather than synthesizing a fallback `WorldClock` (a fabricated clock would be silently wrong data, not a safe default). `main.py` and `web/frontend.py` now both call it instead of constructing `GameContext` inline. |

## Sprint 15 — Core UX completion ✅

**Goal:** Finish the partially-shipped core UX so nothing is left half-done.

| # | Task | Status |
|---|------|--------|
| 15.1 | World clock / weather status bar push via WS | [x] `ConnectionManager.broadcast_global()` + a `TIME_ADVANCED` handler in `main.py` push `time_update` (hour/minute/day/season/weather) to every connected player, not just on connect/reconnect SSR. |
| 15.2 | Multi-player live lists finished (`[~]` STATUS item) | [x] `game/broadcast.py`'s `broadcast_command_effects()` now sends a second `state_change` (`players-online` panel) to the room a player *left*, not just the room they entered — previously occupants of the old room only saw the departure narration text, not a live players-list refresh. |

---

## Foundation exit criteria (gate for Sprints 16+)

All must be true before combat/trading work starts:

- [x] Zero silent `except Exception` blocks in `src/` (Sprint 5)
- [x] Zero `cast(GameContext, ctx)` / `cast(Any, ctx)` in `src/`; basedpyright `standard` mode clean (Sprint 6)
- [x] One `GameContext` construction path; no optional repo fields — **fixed (2026-07-02):** `build_game_context()` now accepts `audit_session` (a separate `Session`, matching real usage) instead of the old same-session `create_audit_repo` bool, `rollback_state`, and passes `clock` straight through instead of synthesizing a fallback `WorldClock`. Both `main.py`'s `/ws` loop and `web/frontend.py`'s `POST /command` call it instead of constructing `GameContext` inline.
- [x] No module >~500 lines with mixed concerns (Sprint 8)
- [x] One service wiring convention; no inline `bus.on()` in `main.py` (Sprint 9.2)
- [x] Web + admin layers have integration coverage; CI enforces coverage, types, and lint (Sprint 7 + Sprint 13.3)
- [x] Feature-registration pattern documented and demonstrated (10.4)
- [x] All `[~]` STATUS partials either finished or explicitly retired — Sprint 14 closed the `/ws`/`/command` broadcast-lifecycle gap; Sprint 15 closed world clock/weather WS push (15.1) and the multi-player live-lists refresh gap on room-leave (15.2)

---

# Feature band (Sprints 16+) — gated on foundation exit criteria

**Re-sequenced 2026-07-03** to reflect Lorecraft's design pillars — **Exploration > Trading >
Questing > Puzzle-solving, with combat as a *supporting* system, not the centerpiece** (see
[`wishlist.md`](wishlist.md) → *Design pillars*). The old sequence front-loaded combat
(Sprints 18–20 of the previous plan); the new sequence front-loads the systems those pillars
depend on — item state, inventory/equipment, exploration, traits/skills — and moves combat
below trading/transit/quests as a fallback resolution path rather than the main loop.

Ordering follows dependencies: item state → equipment → traits/skills/exploration → condition
→ trade → transit → quests/puzzles → combat → PvP. UI polish (map, mobile) sits alongside
exploration, which it serves.

> **Design docs:** [`inventory_equipment.md`](inventory_equipment.md) (Sprints 16–17),
> [`combat_system.md`](combat_system.md) (stat/skill model + combat sprints),
> [`dialogue_npcs_quests.md`](dialogue_npcs_quests.md) and
> [`feature-registration.md`](feature-registration.md) (quests/puzzles, pluggable
> registries). Transit and trade-economy design docs are still TBD — see
> [`wishlist.md`](wishlist.md) for their current specs.

## Sprint 16 — Item & world state modeling

**Goal:** The deferred Sprint 2.5 `open`/container/state prerequisite. Per-instance item state
so items can be worn, burned, opened, and puzzle-wired. Foundation for equipment, containers,
durability, light sources, and mechanism puzzles. **See [`inventory_equipment.md`](inventory_equipment.md) §7.**

| # | Task | Status |
|---|------|--------|
| 16.1 | Layer A item fields (`slot`, `weight`, `wearable`, `quality`, `max_durability`, `light`, `capacity`, `effects`) on `Item`; YAML loader + validators | [ ] |
| 16.2 | `ItemInstance` table (durability/`is_open`/`lit`/`state`) for items that need state; stateless stackables stay as ID lists | [ ] |

## Sprint 17 — Inventory & equipment

**Goal:** Wear/wield slots, encumbrance, containers. Equipment grants **non-combat** effects
(light, warmth, carry, skill/trait bonuses) resolved at runtime. **See [`inventory_equipment.md`](inventory_equipment.md) §3–6, §9.**

| # | Task | Status |
|---|------|--------|
| 17.1 | `Player.equipment` slot map; `wear`/`remove`/`wield`/`equipment` commands via `InventoryService`; `ITEM_EQUIPPED`/`ITEM_UNEQUIPPED` events | [ ] |
| 17.2 | Encumbrance bands from weight + `carry_bonus`; `EquipmentEffects.resolve()` (runtime-derived, never stored) | [ ] |
| 17.3 | Containers: `put in` / `take from`, nesting, worn-container capacity; light/darkness gate (`Room.light_level` + lit source) | [ ] |

## Sprint 18 — Traits & skills

**Goal:** Character identity that gates exploration and social play. Use-based skills, a trait
registry (boons/banes), reputation/NPC-standing. Builds on existing `PlayerStats` (attributes
+ `skills` dict). **See [`combat_system.md`](combat_system.md) stat model + [`wishlist.md`](wishlist.md).**

| # | Task | Status |
|---|------|--------|
| 18.1 | Trait registry (pluggable, like dialogue side-effects); traits from equipment/background/earned; boon+bane modifiers | [ ] |
| 18.2 | Use-based skill improvement (perception, lockpicking, bartering, cartography, survival, persuasion); skill-check helper | [ ] |
| 18.3 | Reputation/standing per NPC + faction; unlocks dialogue/prices/quests (extends flags + NPC memory) | [ ] |

## Sprint 19 — Exploration depth

**Goal:** Make discovery a first-class reward (the top pillar). Search-gated secrets, terrain,
journal, cartography. Builds on existing minimap fog and `Exit.hidden`/`condition_flags`.

| # | Task | Status |
|---|------|--------|
| 19.1 | `search` command + hidden-exit/secret-room reveal gated on perception skill + traits + light; discovery rewards (knowledge flags, progression tick) | [ ] |
| 19.2 | Terrain types on rooms/exits affecting travel time, fatigue cost, and required skill/gear; environmental `examine` layering | [ ] |
| 19.3 | Journal / auto-log panel (discovered places, met NPCs, learned lore, active clues); player cartography reveal | [ ] |

## Sprint 20 — Map & mobile UI

**Goal:** UI polish that serves exploration (was Sprints 16–17 of the previous plan).

| # | Task | Status |
|---|------|--------|
| 20.1 | Full-screen map modal (pan/zoom), integrated with cartography reveal | [ ] |
| 20.2 | Responsive mobile tab layout | [ ] |

## Sprint 21 — Character condition (fatigue / sleep)

**Goal:** Light survival texture that rewards planning; per-world toggle, not punishing. Runs
on `SchedulerService` + `TIME_ADVANCED`. **See [`wishlist.md`](wishlist.md) → Character condition.**

| # | Task | Status |
|---|------|--------|
| 21.1 | Fatigue/stamina drained by travel/encumbrance/actions; low fatigue penalizes skill checks; `rest`/`sleep`/`camp` | [ ] |
| 21.2 | Sleep advances time + restores fatigue + dream/lore hook; safe vs. unsafe sleep; warmth/exposure via weather + worn clothing | [ ] |

## Sprint 22 — Trading & economy

**Goal:** A living economy where *where* you buy/sell matters (pillar #2). Currency → NPC shops
→ regional pricing. **Signature pairing:** the transit network (Sprint 23) is the trade network.

| # | Task | Status |
|---|------|--------|
| 22.1 | Currency model; item value from `quality`; NPC vendor shops (buy/sell), bartering skill affects price | [ ] |
| 22.2 | Regional price differences + finite stock restocking on the world clock (buy-low/sell-high loop) | [ ] |
| 22.3 | Player-to-player `offer`/`accept` trade handshake (multi-player transaction safety) | [ ] |

## Sprint 23 — Transit & travel systems

**Goal:** The signature Materia-Magica-inspired feature — ferries, balloons, rail with tickets
and travel animation. Built on scheduler + world clock + weather + WS push. **See [`wishlist.md`](wishlist.md) → Featured idea** (dedicated design doc TBD before this sprint).

| # | Task | Status |
|---|------|--------|
| 23.1 | Scheduled vehicle as a moving room (dynamic exits on clock cadence); ticket items gate boarding | [ ] |
| 23.2 | Travel animation (timed narrative beats via WS push); weather interplay (grounded balloon, fogged ferry) | [ ] |

## Sprint 24 — Quests & puzzles depth

**Goal:** Branching, consequence-bearing quests and environmental/lore puzzles (pillars #3–4).
Extends the stage/flag quest system with branch conditions and mechanism puzzles.

| # | Task | Status |
|---|------|--------|
| 24.1 | Branch conditions + consequence side-effects on quests (world-state/standing changes); NPC memory of past interactions | [ ] |
| 24.2 | Mechanism & item-combination puzzles on `ItemInstance.state` (levers, dials, sequences) via pluggable conditions/side-effects; timed clock-driven quest events | [ ] |

## Sprint 25 — Combat core services (supporting system)

**Goal:** Server-side combat resolution, no commands/UI yet. First consumer of the
feature-registration pattern (10.4), reading equipment-derived stats. **Deliberately below
trade/transit/quests** — combat serves stories, it isn't the loop. **See [`combat_system.md`](combat_system.md).**

| # | Task | Status |
|---|------|--------|
| 25.1 | `services/combat.py` — sessions, ticks, damage, death/respawn (soft-respawn default; death penalty TBD) | [ ] |
| 25.2 | `npc/combat_ai.py` — behavior modes from YAML | [ ] |

## Sprint 26 — Combat commands + UI (avoidance-first)

**Goal:** Combat as one resolution among several — stealth/persuasion/bribery/flee are
first-class alternatives; non-lethal outcomes supported.

| # | Task | Status |
|---|------|--------|
| 26.1 | `commands/combat.py` — `attack`, `flee`; non-lethal outcomes (subdue/intimidate/drive-off); complete condition eval (`NPC_PRESENT`, `HAS_COMBAT_TARGET`) | [ ] |
| 26.2 | Combat UI in HTMX feed + status panel | [ ] |

## Sprint 27 — Combat testing

| # | Task | Status |
|---|------|--------|
| 27.1 | Integration + browser tests for combat loop and avoidance/non-lethal paths | [ ] |

## Sprint 28 — PvP consent

**Goal:** Consent-based, opt-in PvP reusing the combat system. Soft by default.

| # | Task | Status |
|---|------|--------|
| 28.1 | PvP consent + challenge/accept | [ ] |

## Sprint 29 — Multiplayer trade / PvP / transit tests

| # | Task | Status |
|---|------|--------|
| 29.1 | Multi-player trade, PvP consent, and shared-vehicle transit simulation tests | [ ] |

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| ~~Bug/todo letterbox~~ | Implemented in Sprint 10.5 as issues tracking system |
| Inventory encumbrance / wear slots | After equipment + combat |
| `lorecraft.tools.simulation` CLI (JSON scenario files, N-bot load runs, latency/throughput reports) | Enhancement on top of the Sprint 12.1 pytest-based harness; see `tooling_infrastructure.md` §5 |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| Player-facing bug reports | In-game `/report-bug` command (after core issues system stable) |
| Analytics dashboard & visualizations | After Sprint 13 instrumentation (Sprint 14+) |
| Database inspector / state editor | Admin tool for advanced troubleshooting (Post-foundation) |

---

## Build-order reference

See `docs/architecture.md` §28 for the original phase order, and `CODE_AUDIT.md` for the audit driving the foundation band. Order: player authentication (Sprint 4) → foundation hardening (Sprints 5–15) → **foundation gate** → item state & inventory/equipment (16–17) → traits/skills & exploration + UI (18–20) → condition/trade/transit (21–23) → quests & puzzles (24) → combat (25–27) → PvP + multiplayer tests (28–29).

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

*Last updated: 2026-07-03 — Feature band (Sprints 16+) re-sequenced around design pillars (Exploration > Trading > Questing > Puzzles; combat as a supporting system, not the centerpiece); combat moved from Sprints 18–20 down to 25–27. See [`wishlist.md`](wishlist.md) (pillars + mechanics menu) and [`inventory_equipment.md`](inventory_equipment.md) (Sprints 16–17 design). Sprints 4–15 complete; foundation gate green. Next: Sprint 16 (item & world state modeling).*
