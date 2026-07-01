# Lorecraft — Next Steps

Working roadmap derived from `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/TODO.md`, HTMX migration (v0.2.0), and parser v1.

Legend: `[x]` done · `[~]` in progress · `[ ]` not started

---

## Current position

Phases **1–6** are implemented (command dispatch, world/time, inventory, NPCs/quests, save/disconnect, admin tools). Version **0.2.0** added parser v1, quantity inventory, and HTMX primary UI with all foundational gameplay commands.

**Sprint 1 (HTMX parity)** is complete: commands execute via `POST /command`, dialogue/quests/multiplayer push work, WebSocket integrates with `ConnectionManager`.

Two gaps discovered during 0.2.0 were not in the original roadmap:
1. **Player identity is dev-mode only**: `get_current_player()` trusts `?player_id=` query param + cookie with no auth. `create character` does not work; security risk flagged in `TODO.md`.
2. **Tailwind/CSS is layered ad-hoc**: `base.html` loads Tailwind Play CDN; utility classes sprawl across 807 lines of templates, layered on top of hand-rolled `static/css/custom.css` (107 lines). Unwinding this has zero gameplay-logic risk but real visual-regression risk — isolate as separate worktree.

---

## Sprint A — Player identity & session safety

**Goal:** Fix character creation (`TODO.md`); stop trusting bare `?player_id=` for identity. Introduce session/signed-cookie pattern at minimum. Ground-floor for `help system` expansion.

**Source:** `TODO.md` (uncaptured gap), `ARCHITECTURE.md` §21/§28

| # | Task | Status |
|---|------|--------|
| A.1 | Session-backed identity: signed cookie or token-based auth (no bare `player_id` trust) | [ ] |
| A.2 | Fix `create character` logic in `frontend.py` / player creation flow | [ ] |
| A.3 | Verify `get_current_player()` uses session-backed identity end-to-end | [ ] |

---

## Sprint B — Command depth

**Goal:** Close `docs/TODO.md` gameplay gaps. Unblock Phase 7+ (polish) and combat.

**Source:** `NEXT_STEPS.md` Sprint 2 (unchanged scope)

| # | Task | Status |
|---|------|--------|
| B.1 | Item `aliases` in YAML/model; wire through `GameContext.get_visible_entities()` | [ ] |
| B.2 | Finish inventory disambiguation bug | [ ] |
| B.3 | Context-aware `help` (dialogue, combat, per-room disabled commands) | [ ] |
| B.4 | `use` command + `InventoryService.use_item()` | [ ] |
| B.5 | 2–3 more parser patterns (`give`, `open`, containers) | [ ] |

---

## Sprint C — Scheduler

**Goal:** DB-backed scheduled jobs on `TIME_ADVANCED` event. Decoupled from combat.

**Source:** `ARCHITECTURE.md` §28 Phase 2.5 (split from combat), `TODO.md` "timer/scheduler system"

| # | Task | Status |
|---|------|--------|
| C.1 | `services/scheduler.py` — job storage, `TIME_ADVANCED` dispatch, retry logic | [ ] |
| C.2 | Wire `scheduler.tick()` into `GameContext.advance_time()` | [ ] |
| C.3 | Integration tests: schedule a job, advance time, verify execution | [ ] |

---

## Sprint D — Tailwind → vanilla CSS

**Goal:** Replace CDN Tailwind + scattered utility classes with self-contained stylesheet extending `static/css/custom.css`. Eliminate visual-regression risk from template refactor. **Handled in separate worktree; review/merge independent of gameplay.**

**Source:** User request; zero gameplay-logic risk, real visual-regression risk.

| # | Task | Status |
|---|------|--------|
| D.1 | Audit all 807 lines of `templates/*.html` for Tailwind classes + custom class usage | [ ] |
| D.2 | Extend `static/css/custom.css` (Terminal Gothic theme per `ARCHITECTURE.md` §22) with consolidated selectors | [ ] |
| D.3 | Remove CDN Tailwind from `base.html`; replace all utility classes with custom CSS classes | [ ] |
| D.4 | Visual regression test: side-by-side screenshot comparison of all screens (lobby, game, partials) | [ ] |

---

## Sprint E — Phase 7 polish remainder

**Goal:** Full-screen map modal, responsive layout, live clock/weather push, browser E2E harness, admin WS tests. Depends on D (CSS settled).

**Source:** `STATUS.md` Phase 7 unchecked items

| # | Task | Status |
|---|------|--------|
| E.1 | Full-screen map modal (pan/zoom) | [ ] |
| E.2 | Responsive mobile tab layout (depends on D: CSS stability) | [ ] |
| E.3 | World clock / weather status bar push via WS | [ ] |
| E.4 | Admin WebSocket integration tests | [ ] |
| E.5 | Browser end-to-end test harness for HTMX UI | [ ] |
| E.6 | Simulation harness MVP (`tests/simulation/`) | [ ] |
| E.7 | Unify 13-step lifecycle across `/ws` and `/command` paths | [ ] |

---

## Sprint F — Combat (Phase 8)

**Goal:** Implement turn-based combat with session/tick management, NPC behavior, and HTMX UI.

**Source:** `ARCHITECTURE.md` §28

| # | Task | Status |
|---|------|--------|
| F.1 | `services/combat.py` — sessions, ticks, damage calc, death/respawn | [ ] |
| F.2 | `npc/combat_ai.py` — behavior modes from YAML config | [ ] |
| F.3 | `commands/combat.py` — `attack`, `flee`; complete condition eval (`NPC_PRESENT`, `HAS_COMBAT_TARGET`) | [ ] |
| F.4 | Combat UI in HTMX feed + status panel | [ ] |
| F.5 | Integration + browser tests for combat loop | [ ] |

---

## Sprint G — Player interaction (Phase 9)

**Goal:** Trading and PvP consent systems.

| # | Task | Status |
|---|------|--------|
| G.1 | `services/trading.py` + trade commands | [ ] |
| G.2 | PvP consent + challenge/accept | [ ] |
| G.3 | Multi-player trade and PvP tests | [ ] |

---

## Backlog (opportunistic, not sequenced)

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| Bug/todo letterbox | In-world or admin-facing feedback |
| Inventory encumbrance / wear slots | After equipment + combat |
| Playback scripts / many-player harness | Tied to simulation harness (Sprint E.6) |
| Sounds, GPT descriptions, online world-building | Wishlist |

---

## Workflow

Per `AGENTS.md`:
- Small, logical commits per unit of work.
- Type hints on all new code.
- Unit tests written alongside features.
- Before moving on: `pytest` (focused on touched files) + `ruff check` + `ruff format --check` + `basedpyright` on modified/new files.
- Update `docs/STATUS.md` and `CHANGELOG.md` as items land.
- For **Sprint D** specifically: spin up a dedicated worktree so CSS refactor can be reviewed/merged independent of gameplay commits.

---

## Playtesting (Ashmoore dev world)

`start.sh` copies `test_dbs/lorecraft-dev-game.db`, built from `world_content/world.yaml`.

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

*Last updated: 2026-07-01 — Roadmap revised post-0.2.0: Sprint 1 complete; gaps discovered (player identity, CSS layering) added as A & D; sprints resequenced per architecture review.*
