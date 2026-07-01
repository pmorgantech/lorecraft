# Lorecraft — Next Steps

Working roadmap derived from `docs/ARCHITECTURE.md`, `docs/STATUS.md`, `docs/TODO.md`, HTMX migration (v0.2.0), and parser v1.

Legend: `[x]` done · `[~]` in progress · `[ ]` not started

---

## Current position

Phases **1–6** are implemented (command dispatch, world/time, inventory, NPCs/quests, save/disconnect, admin tools). Version **0.2.0** added parser v1, quantity inventory, and HTMX primary UI with all foundational gameplay commands.

**Sprint 1 (HTMX parity)** is complete: commands execute via `POST /command`, dialogue/quests/multiplayer push work, WebSocket integrates with `ConnectionManager`.

One gap remains from the original roadmap:
1. **Tailwind/CSS is layered ad-hoc**: `base.html` loads Tailwind Play CDN; utility classes sprawl across 807 lines of templates, layered on top of hand-rolled `static/css/custom.css` (107 lines). Unwinding this has zero gameplay-logic risk but real visual-regression risk — isolate as separate worktree (Sprint D).

**Sprint A (player identity & session safety) is done for its stated scope** — signed session cookies replace bare `player_id` trust as the primary HTTP identity path, and character creation works. It intentionally does **not** implement password/credential accounts (`POST /auth/login` per `ARCHITECTURE.md` §29) or a signed WebSocket handshake; both are tracked as new backlog items below.

---

## Sprint A — Player identity & session safety — DONE

**Goal:** Fix character creation (`TODO.md`); stop trusting bare `?player_id=` for identity. Introduce session/signed-cookie pattern at minimum. Ground-floor for `help system` expansion.

**Source:** `TODO.md` (uncaptured gap), `ARCHITECTURE.md` §21/§28

| # | Task | Status |
|---|------|--------|
| A.1 | Session-backed identity: signed JWT cookie (`lorecraft_session`, httponly), separate secret from admin auth, reuses `admin/auth.py` token primitives via `web/player_auth.py` | [x] |
| A.2 | `POST /lobby/create`: validated username (3-30 chars, `[A-Za-z0-9_-]`), uniqueness check, creates `Player` + auto-login; `/lobby/enter` verifies player exists before minting a session; both redirect to plain `/game` (no `?player_id=` in the URL) | [x] |
| A.3 | `get_current_player()` prefers the signed cookie; legacy `?player_id=`/unsigned-cookie path kept behind `Settings.allow_query_player_id` (default on) for dev/test back-compat | [x] |

**Known gaps intentionally out of scope** (see `docs/TODO.md`):
- No password/credential auth — `/lobby/enter` still lets anyone claim any existing username with no secret.
- `/ws?player_id=...` handshake still trusts the raw query param unconditionally; not covered by the signed-cookie fix.
- `LORECRAFT_ALLOW_QUERY_PLAYER_ID` defaults to `true`, so the legacy bypass is still reachable until flipped off in a later hardening pass.

Session secret (`LORECRAFT_PLAYER_SESSION_SECRET`) is auto-generated and persisted to `.env` on first real server startup (`ensure_persisted_secret()` in `config.py`); test runs always pass explicit `Settings(...)` and never touch disk.

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
| Password/credential accounts (`POST /auth/login`, register-on-first-login) | `ARCHITECTURE.md` §29 original intent; Sprint A shipped signed sessions + character creation but not credentials |
| Signed WebSocket handshake | `/ws?player_id=...` still trusts the raw query param; needs a short-lived ticket or equivalent tied to the session cookie |
| Retire `LORECRAFT_ALLOW_QUERY_PLAYER_ID` legacy fallback | Flip default off once browser + test callers use the signed cookie exclusively (Sprint A follow-up hardening) |
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

*Last updated: 2026-07-01 — Sprint A (player identity & session safety) complete: signed session cookies, working character creation. Password auth and signed WS handshake moved to backlog as explicitly scoped-out follow-ups.*
