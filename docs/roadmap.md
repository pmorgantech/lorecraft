# Lorecraft — Roadmap

Working roadmap derived from `docs/architecture.md`, `docs/status.md`, and recent 0.2.0 development (HTMX migration + parser v1).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started

Sprints are scoped small (1–2 tasks, one subsystem) on purpose, so each sprint/task can be picked up with minimal context.

---

## Current position

Phases **1–6** are implemented (command dispatch, world/time, inventory, NPCs/quests, save/disconnect, admin tools). Version **0.2.0** added parser v1, quantity inventory, and the HTMX primary UI.

Sprints 1–3 closed out HTMX parity, command-depth gaps, and the scheduler foundation. **Player authentication (Sprint 4) comes next** as the foundation for production security, followed by combat (Sprints 5–7), polish (Sprints 8–14), and player interaction (Sprints 15–17).

---

## Sprint 1 — HTMX parity (playtesting unblock)

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

## Sprint 2 — Command depth

**Goal:** Close gameplay gaps (item aliases, disambiguation, help, use/give/lock) before combat.

| # | Task | Status |
|---|------|--------|
| 2.1 | Item `aliases` in YAML/model; wire through `GameContext.get_visible_entities()` | [x] |
| 2.2 | Finish inventory disambiguation bug | [x] |
| 2.3 | Context-aware `help` (dialogue, combat, per-room disabled commands) | [x] |
| 2.4 | `use` command + `InventoryService.use_item()` | [x] |
| 2.5 | 2–3 more parser patterns (`give`, `open`, containers) | [~] `give` + `lock`/`unlock` (on the existing `Exit.locked`/`key_item_id` fields) shipped; `open`/container-holding items deferred — needs new Item/state modeling |

---

## Sprint 3 — Scheduler foundation

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

## Sprint 5 — Combat core services

**Goal:** Server-side combat resolution, no commands or UI yet.

| # | Task | Status |
|---|------|--------|
| 5.1 | `services/combat.py` — sessions, ticks, damage, death/respawn | [ ] |
| 5.2 | `npc/combat_ai.py` — behavior modes from YAML | [ ] |

---

## Sprint 6 — Combat commands + UI

**Goal:** Expose combat to players.

| # | Task | Status |
|---|------|--------|
| 6.1 | `commands/combat.py` — `attack`, `flee`; complete condition eval (`NPC_PRESENT`, `HAS_COMBAT_TARGET`) | [ ] |
| 6.2 | Combat UI in HTMX feed + status panel | [ ] |

---

## Sprint 7 — Combat testing

**Goal:** Close out Phase 8/8.5 with coverage.

| # | Task | Status |
|---|------|--------|
| 7.1 | Integration + browser tests for combat loop | [ ] |

---

## Sprint 8 — Full-screen map

| # | Task | Status |
|---|------|--------|
| 8.1 | Full-screen map modal (pan/zoom) | [ ] |

---

## Sprint 9 — Mobile layout

| # | Task | Status |
|---|------|--------|
| 9.1 | Responsive mobile tab layout | [ ] |

---

## Sprint 10 — World clock/weather push

| # | Task | Status |
|---|------|--------|
| 10.1 | World clock / weather status bar push via WS | [ ] |

---

## Sprint 11 — Admin WebSocket tests

| # | Task | Status |
|---|------|--------|
| 11.1 | Admin WebSocket integration tests | [ ] |

---

## Sprint 12 — Browser E2E harness

| # | Task | Status |
|---|------|--------|
| 12.1 | Browser end-to-end test harness for HTMX UI | [ ] |

---

## Sprint 13 — Simulation harness MVP

| # | Task | Status |
|---|------|--------|
| 13.1 | Simulation harness MVP (`tests/simulation/`) | [ ] |

---

## Sprint 14 — Unify command lifecycle

| # | Task | Status |
|---|------|--------|
| 14.1 | Unify 13-step lifecycle across `/ws` and `/command` paths | [ ] |

---

## Sprint 15 — Trading

**Goal:** Phase 9 per `architecture.md` §28.

| # | Task | Status |
|---|------|--------|
| 15.1 | `services/trading.py` + trade commands | [ ] |

---

## Sprint 16 — PvP consent

| # | Task | Status |
|---|------|--------|
| 16.1 | PvP consent + challenge/accept | [ ] |

---

## Sprint 17 — Multiplayer trade/PvP tests

| # | Task | Status |
|---|------|--------|
| 17.1 | Multi-player trade and PvP tests | [ ] |

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| Bug/todo letterbox | In-world or admin-facing feedback |
| Inventory encumbrance / wear slots | After equipment + combat |
| Playback scripts / many-player harness | Tied to simulation harness (Sprint 13.1) |
| Sounds, GPT descriptions, online world-building | Wishlist |

---

## Partial STATUS items to close

- `[~]` Full 13-step transaction/event/audit lifecycle in `handle_command()`
- `[~]` Command registry condition evaluation (missing `NPC_PRESENT`, `HAS_COMBAT_TARGET`)
- `[~]` Multi-player live lists and world clock push
- `[~]` Admin WebSocket integration tests
- `[ ]` Simulation tests directory (only `.gitkeep` today)

---

## Build-order reference

See `docs/architecture.md` §28. Player authentication (Sprint 4) must come before combat—it's the foundation for production security. Combat (Sprints 5–7) follows, then polish (Sprints 8–14) and player interaction (Sprints 15–17).

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

*Last updated: 2026-07-02 — Player authentication (Sprint 4) inserted as production-security foundation before combat. Sprints 4–16 renumbered to 5–17.*
