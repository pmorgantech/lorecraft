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

**Current:** Sprints 5–11 complete (error handling, type safety, characterization tests, module decomposition, service consistency/wiring, extensibility seams, tooling infrastructure, browser E2E harness). **Next up: Sprint 12 (simulation harness MVP).** Combat (Sprints 18–20) and trading/PvP (Sprints 21–23) follow only after the foundation gate.

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

## Sprint 4 — Player authentication (production hardening)

**Goal:** Phase 7 per `architecture.md` §21 — full account system with password auth, JWT tokens, and signed WebSocket handshake. Foundation for all production deployments.

**See:** [`player_authentication.md`](player_authentication.md) for detailed workflows and code examples.

| # | Task | Status |
|---|------|--------|
| 4.1 | `POST /auth/login` — account creation on first login, password hashing (bcrypt/argon2) | [ ] |
| 4.2 | JWT access tokens (15min lifetime) + refresh token rotation (8hr lifetime) | [ ] |
| 4.3 | `POST /auth/ws-ticket` — single-use, 60-second WebSocket ticket exchange | [ ] |
| 4.4 | WebSocket handshake: validate ticket, map to player_id, attach to ConnectionManager | [ ] |
| 4.5 | `/auth/refresh` endpoint for refresh token rotation | [ ] |
| 4.6 | Retire legacy `?player_id=` query param fallback (was gated by `LORECRAFT_ALLOW_QUERY_PLAYER_ID`) | [ ] |
| 4.7 | OAuth extensibility hooks (Google OIDC callback stubs for future LAN-party deployments) | [ ] |
| 4.8 | Integration tests: login, token refresh, WS ticket validation, expired token rejection | [ ] |

---

# Foundation band (Sprints 5–15)

Work queue derived from `CODE_AUDIT.md`. Ordering is deliberate: error/type groundwork first, then **characterization tests before the big refactors**, then structure, then tooling.

**Current progress:** Sprints 5–11 complete (error handling, type safety, characterization tests, module decomposition, service consistency/wiring, extensibility seams, tooling infrastructure, browser E2E harness). Sprint 12 (simulation harness MVP) next.

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

## Sprint 12 — Simulation harness MVP

| # | Task | Status |
|---|------|--------|
| 12.1 | Simulation harness MVP (`tests/simulation/` — currently only `.gitkeep`) | [ ] |

## Sprint 13 — Observability & CI quality gates

**Goal:** Regressions can't land silently. Audit §4.2, §5.2.

| # | Task | Status |
|---|------|--------|
| 13.1 | Structured logging (stdlib `logging` with correlation/transaction IDs from `TransactionContext`; today only 2 files log at all) | [ ] |
| 13.2 | Command latency + event-handler timing instrumentation | [ ] |
| 13.3 | CI: pytest + coverage threshold + basedpyright + ruff as required checks | [ ] |

## Sprint 14 — Unify command lifecycle

**Goal:** One 13-step transaction/event/audit lifecycle shared by `/ws` and `/command` paths (long-standing `[~]` STATUS item). Easier after Sprint 8 decomposition.

| # | Task | Status |
|---|------|--------|
| 14.1 | Extract shared lifecycle; both entry points call it; add rollback-on-error semantics | [ ] |

## Sprint 15 — Core UX completion

**Goal:** Finish the partially-shipped core UX so nothing is left half-done.

| # | Task | Status |
|---|------|--------|
| 15.1 | World clock / weather status bar push via WS | [ ] |
| 15.2 | Multi-player live lists finished (`[~]` STATUS item) | [ ] |

---

## Foundation exit criteria (gate for Sprints 16+)

All must be true before combat/trading work starts:

- [ ] Zero silent `except Exception` blocks in `src/`
- [ ] Zero `cast(GameContext, ctx)` / `cast(Any, ctx)` in `src/`; basedpyright `standard` mode clean
- [ ] One `GameContext` construction path; no optional repo fields
- [ ] No module >~500 lines with mixed concerns
- [ ] One service wiring convention; no inline `bus.on()` in `main.py`
- [ ] Web + admin layers have integration coverage; CI enforces coverage, types, and lint
- [ ] Feature-registration pattern documented and demonstrated (10.4)
- [ ] All `[~]` STATUS partials either finished or explicitly retired

---

# Feature band (Sprints 16–23) — gated on foundation exit criteria

## Sprint 16 — Full-screen map

| # | Task | Status |
|---|------|--------|
| 16.1 | Full-screen map modal (pan/zoom) | [ ] |

## Sprint 17 — Mobile layout

| # | Task | Status |
|---|------|--------|
| 17.1 | Responsive mobile tab layout | [ ] |

## Sprint 18 — Combat core services

**Goal:** Server-side combat resolution, no commands or UI yet. Built as the first consumer of the feature-registration pattern (10.4).

| # | Task | Status |
|---|------|--------|
| 18.1 | `services/combat.py` — sessions, ticks, damage, death/respawn | [ ] |
| 18.2 | `npc/combat_ai.py` — behavior modes from YAML | [ ] |

## Sprint 19 — Combat commands + UI

| # | Task | Status |
|---|------|--------|
| 19.1 | `commands/combat.py` — `attack`, `flee`; complete condition eval (`NPC_PRESENT`, `HAS_COMBAT_TARGET`) | [ ] |
| 19.2 | Combat UI in HTMX feed + status panel | [ ] |

## Sprint 20 — Combat testing

| # | Task | Status |
|---|------|--------|
| 20.1 | Integration + browser tests for combat loop | [ ] |

## Sprint 21 — Trading

**Goal:** Phase 9 per `architecture.md` §28.

| # | Task | Status |
|---|------|--------|
| 21.1 | `services/trading.py` + trade commands | [ ] |

## Sprint 22 — PvP consent

| # | Task | Status |
|---|------|--------|
| 22.1 | PvP consent + challenge/accept | [ ] |

## Sprint 23 — Multiplayer trade/PvP tests

| # | Task | Status |
|---|------|--------|
| 23.1 | Multi-player trade and PvP tests | [ ] |

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| ~~Bug/todo letterbox~~ | Implemented in Sprint 10.5 as issues tracking system |
| Inventory encumbrance / wear slots | After equipment + combat |
| Playback scripts / many-player harness | Tied to simulation harness (Sprint 12.1) |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| Player-facing bug reports | In-game `/report-bug` command (after core issues system stable) |
| Analytics dashboard & visualizations | After Sprint 13 instrumentation (Sprint 14+) |
| Database inspector / state editor | Admin tool for advanced troubleshooting (Post-foundation) |

---

## Build-order reference

See `docs/architecture.md` §28 for the original phase order, and `CODE_AUDIT.md` for the audit driving the foundation band. Order: player authentication (Sprint 4) → foundation hardening (Sprints 5–15) → **foundation gate** → UI features + combat (Sprints 16–20) → player interaction (Sprints 21–23).

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

*Last updated: 2026-07-02 — Sprint 11 complete (browser E2E harness: Playwright against a live server, `tests/e2e/`). Next: Sprint 12 (simulation harness MVP).*
