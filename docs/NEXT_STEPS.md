# Lorecraft — Next Steps

Working roadmap derived from `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/TODO.md`, and recent 0.2.0 development (HTMX migration + parser v1).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started

---

## Current position

Phases **1–6** are implemented (command dispatch, world/time, inventory, NPCs/quests, save/disconnect, admin tools). Version **0.2.0** added parser v1, quantity inventory, and the HTMX primary UI.

The engine is ahead of the new browser client: dialogue, quests, and multiplayer push existed in the vanilla client but are not fully ported to HTMX yet.

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

**Goal:** Close `docs/TODO.md` gameplay gaps before combat.

| # | Task | Status |
|---|------|--------|
| 2.1 | Item `aliases` in YAML/model; wire through `GameContext.get_visible_entities()` | [x] |
| 2.2 | Finish inventory disambiguation bug (`docs/TODO.md`) | [x] |
| 2.3 | Context-aware `help` (dialogue, combat, per-room disabled commands) | [x] |
| 2.4 | `use` command + `InventoryService.use_item()` | [x] |
| 2.5 | 2–3 more parser patterns (`give`, `open`, containers) | [~] `give` + `lock`/`unlock` (on the existing `Exit.locked`/`key_item_id` fields) shipped; `open`/container-holding items deferred — needs new Item/state modeling |

---

## Sprint 3 — Scheduler + combat foundation

**Goal:** Phase 8 per `ARCHITECTURE.md` §28.

| # | Task | Status |
|---|------|--------|
| 3.1 | `services/scheduler.py` — DB-backed jobs on `TIME_ADVANCED` | [ ] |
| 3.2 | `services/combat.py` — sessions, ticks, damage, death/respawn | [ ] |
| 3.3 | `npc/combat_ai.py` — behavior modes from YAML | [ ] |
| 3.4 | `commands/combat.py` — `attack`, `flee`; complete condition eval (`NPC_PRESENT`, `HAS_COMBAT_TARGET`) | [ ] |
| 3.5 | Combat UI in HTMX feed + status panel | [ ] |
| 3.6 | Integration + browser tests for combat loop | [ ] |

---

## Sprint 4 — Polish + confidence

**Goal:** Phase 7 completion and test infrastructure.

| # | Task | Status |
|---|------|--------|
| 4.1 | Full-screen map modal (pan/zoom) | [ ] |
| 4.2 | Responsive mobile tab layout | [ ] |
| 4.3 | World clock / weather status bar push via WS | [ ] |
| 4.4 | Admin WebSocket integration tests | [ ] |
| 4.5 | Browser end-to-end test harness for HTMX UI | [ ] |
| 4.6 | Simulation harness MVP (`tests/simulation/`) | [ ] |
| 4.7 | Unify 13-step lifecycle across `/ws` and `/command` paths | [ ] |

---

## Sprint 5 — Player interaction (Phase 9)

| # | Task | Status |
|---|------|--------|
| 5.1 | `services/trading.py` + trade commands | [ ] |
| 5.2 | PvP consent + challenge/accept | [ ] |
| 5.3 | Multi-player trade and PvP tests | [ ] |

---

## Backlog (from `docs/TODO.md`)

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| Bug/todo letterbox | In-world or admin-facing feedback |
| Inventory encumbrance / wear slots | After equipment + combat |
| Playback scripts / many-player harness | Tied to simulation harness (Sprint 4.6) |
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

See `docs/ARCHITECTURE.md` §28. Combat (Phase 8) is the next major architecture milestone after HTMX parity and command depth.

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

*Last updated: 2026-07-02 — Sprint 2 complete (container/open patterns deferred, see 2.5); dev seed aligned to Ashmoore.*
