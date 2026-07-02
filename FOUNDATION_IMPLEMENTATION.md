# Foundation Sprints Implementation Guide

**For delegation to cheaper models (Haiku, Sonnet).** Comprehensive but concise; each sprint is self-contained.

**Date:** 2026-07-02
**Foundation Phases:** Sprints 5–15 (as per `docs/roadmap.md`)
**Goal:** Harden core engine to 8/10 code quality before feature expansion (combat/trading/PvP)

---

## Roadmap

**Sprint 5 → 6 → 7 are critical path.** (Parallel: Sprint 8 can run with Sprint 7.)

```
Sprint 5: Error Handling [2-3 days]
    ↓ (enables type safety)
Sprint 6: Type Safety [2-3 days]
    ↓ (enables reliable testing)
Sprint 7: Web/Admin Tests + Sprint 8: Decomposition [parallel, 3-4 days each]
    ↓
Sprints 9–15: Service consistency, extensibility, tooling
    ↓
Foundation exit gate → Feature expansion (Sprints 16+)
```

**Graphify insights:** GameContext is the god node (79 connections). Error handling + type safety both improve GameContext reliability, hence the tight coupling of Sprints 5–6.

---

## Sprint 5: Error Handling & Exception Hierarchy

**Goal:** One error-handling style everywhere. Replace 22 silent `except Exception` blocks.

**Impact:** 15+ files affected; 5 god nodes downstream benefit (ItemRepo, repos, services, admin/websocket).

### Deliverables

1. **`src/lorecraft/errors.py`** (new file, ~80 lines)

```python
"""Game domain errors — typed, machine-readable, with codes."""

class GameError(Exception):
    """Base exception for all game logic errors."""
    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code or "unknown_error"
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ValidationError(GameError):
    """User input validation failed. Code: validation_*."""
    def __init__(self, message: str, code: str = "validation_failed"):
        super().__init__(message, code)


class NotFoundError(GameError):
    """Entity not found. Code: not_found_*."""
    def __init__(self, message: str, code: str = "not_found"):
        super().__init__(message, code)


class PermissionError(GameError):
    """User lacks permission. Code: permission_denied."""
    def __init__(self, message: str, code: str = "permission_denied"):
        super().__init__(message, code)


class ConflictError(GameError):
    """Concurrent modification or state conflict. Code: conflict_*."""
    def __init__(self, message: str, code: str = "conflict"):
        super().__init__(message, code)
```

2. **Fix 22 silent `except Exception` blocks** (scan: grep -r "except Exception" src/lorecraft/)
   - **Files:** `web/frontend.py` (12), `web/player_auth.py` (1), `admin/websocket.py` (3), `admin/auth.py` (2), `repos/item_repo.py` (1)
   - **Pattern:** Replace with specific exception type + log before re-raise or translating to domain error
   - **Example:**
     ```python
     # Before
     try:
         payload = decode_token(token, secret)
     except Exception:
         return None

     # After
     import logging
     log = logging.getLogger(__name__)
     try:
         payload = decode_token(token, secret)
     except jwt.InvalidTokenError as e:
         log.error("token_decode_failed", error=str(e))
         raise ValidationError("Invalid token") from e
     except jwt.ExpiredSignatureError:
         raise ValidationError("Token expired")
     ```

3. **Guard quantity underflow in ItemRepo** (`repos/item_repo.py:104-107`)
   - Current: silently deletes row if `quantity < 0`
   - Fix: raise `ConflictError("Attempted to remove more items than exist")`

4. **Unit tests** (`tests/unit/test_errors.py`, ~50 lines)
   - Verify exception hierarchy: `NotFoundError` is-a `GameError`
   - Verify codes are set: `ValidationError("msg", "custom_code").code == "custom_code"`
   - Verify message round-trip: `str(NotFoundError("test")) == "not_found: test"`

### Files to Touch

| File | Change | Why |
|------|--------|-----|
| `src/lorecraft/errors.py` | Create | Define exception hierarchy |
| `web/frontend.py` | 12× except fixes + logging imports | Error handling best-practices |
| `web/player_auth.py` | 1× except fix | Token decode errors now typed |
| `admin/websocket.py` | 3× except fixes | WebSocket errors now typed |
| `admin/auth.py` | 2× except fixes | Auth errors now typed |
| `repos/item_repo.py` | Fix underflow; 1× except fix | Guard race conditions; consistent error handling |
| `tests/unit/test_errors.py` | Create | Verify exception hierarchy |

### Testing Checklist

- [ ] `pytest tests/unit/test_errors.py` passes
- [ ] `grep -r "except Exception" src/lorecraft/ | wc -l` outputs `0` (or only intentional cases in game/events.py, admin/tui/app.py)
- [ ] Run existing integration tests; no regressions
- [ ] Spot-check: one error path per module (e.g., token decode → ValidationError → logs + client message)

### Handoff Notes

- **Difficulty:** Low. Mostly grep + find/replace + logging.
- **Risk:** None if done carefully. All paths already exist; just adding types and logs.
- **Blockers:** None.
- **Time estimate:** 2 hours code + 1 hour testing = 3 hours per person.

---

## Sprint 6: Type Safety

**Goal:** basedpyright verifies real invariants. Remove 18 `cast(GameContext, ctx)` casts.

**Depends on:** Sprint 5 (error handling), so error paths are clear.

**Impact:** GameContext (79 connections) becomes properly typed; all handlers can now be verified by type checker.

### Deliverables

1. **`src/lorecraft/types.py`** (new file, ~50 lines)

```python
"""Protocol and type definitions for type-safe command dispatch."""

from typing import Callable, Protocol

from lorecraft.game.context import GameContext


class CommandHandler(Protocol):
    """A command handler — must accept noun and GameContext, return None."""
    def __call__(self, noun: str | None, ctx: GameContext) -> None:
        ...
```

2. **Update `game/registry.py`**
   - Import `CommandHandler` from `types.py`
   - Change `CommandHandler = Callable[[str | None, object], None]` → `CommandHandler = Callable[[str | None, GameContext], None]`
   - Update registry type hints to use the Protocol

3. **Remove 18 `cast(GameContext, ctx)` calls**
   - Scan: `grep -n "cast(GameContext" src/lorecraft/commands/`
   - All in `commands/` directory (movement.py, inventory.py, social.py, meta.py)
   - **Pattern:** Remove the cast; ctx is now properly typed:
     ```python
     # Before
     def handle_take(noun: str | None, ctx: object) -> None:
         game_ctx = cast(GameContext, ctx)
         player = game_ctx.player

     # After
     def handle_take(noun: str | None, ctx: GameContext) -> None:
         player = ctx.player
     ```

4. **Unify GameContext construction** (`game/context.py` + wherever `GameContext()` is called)
   - Goal: One factory function used by all entry points (websocket handler, scheduler, tests)
   - Currently: 7 fields optional (`clock`, `audit`, `quest_repo`, `dialogue_repo`, `parsed_command`, etc.)
   - Fix: Make a `build_game_context()` factory that wires all 21 fields
   - **Factory location:** `game/context.py` bottom, or new `game/_context_factory.py`
   - **Pattern:**
     ```python
     def build_game_context(
         session: Session,
         player: Player,
         room: Room,
         *,
         bus: EventBus,
         manager: ConnectionManager,
         transaction: TransactionContext,
         clock: WorldClock | None = None,
         audit_service: AuditService | None = None,
     ) -> GameContext:
         """One factory for all GameContext construction. All fields wired."""
         return GameContext(
             player=player, room=room, bus=bus, manager=manager,
             transaction=transaction,
             player_repo=PlayerRepo(session),
             room_repo=RoomRepo(session),
             item_repo=ItemRepo(session),
             npc_repo=NpcRepo(session),
             quest_repo=QuestRepo(session),
             dialogue_repo=DialogueRepo(session),
             clock=clock or WorldClock(),
             audit=audit_service or AuditService(),
             # ... all 21 fields
         )
     ```
   - **Usage:** Replace all `GameContext(...)` calls with `build_game_context(...)`
   - Once done: Remove optional-field None-guards (114 `is None` checks can shrink)

5. **Type `GameContext.optional_fields` as required** (after factory is in place)
   - Remove `| None` from fields that are now always set
   - Update any service code that checks `if ctx.quest_repo is not None` → remove check

6. **TypedDict for API responses** (`web/frontend.py`, `admin/api.py`)
   - Document response schemas at module top
   - **Example:**
     ```python
     from typing import TypedDict

     class FeedMessage(TypedDict):
         type: str
         text: str
         timestamp: int

     class GameScreenResponse(TypedDict):
         feed: list[FeedMessage]
         inventory: list[str]
         room: dict[str, Any]
     ```

7. **Raise basedpyright to `standard` mode**
   - Update `pyproject.toml`: `pyrightConfig.typeCheckingMode = "standard"` (from "basic")
   - Run: `basedpyright src/lorecraft/`
   - Fix remaining type errors until clean

8. **Unit tests** (`tests/unit/test_context.py`, ~30 lines)
   - Verify `build_game_context()` returns fully-wired GameContext
   - Verify all fields are non-None after factory call

### Files to Touch

| File | Change | Why |
|------|--------|-----|
| `src/lorecraft/types.py` | Create | Define CommandHandler protocol |
| `game/registry.py` | Update type hint | Use CommandHandler protocol |
| `commands/movement.py` | Remove 5× cast | Now properly typed |
| `commands/inventory.py` | Remove 5× cast | Now properly typed |
| `commands/social.py` | Remove 4× cast | Now properly typed |
| `commands/meta.py` | Remove 4× cast | Now properly typed |
| `game/context.py` | Add factory + remove None from fields | Centralize construction |
| `web/frontend.py` | Add TypedDict; update GameContext calls | Type API responses |
| `admin/api.py` | Add TypedDict; update GameContext calls | Type API responses |
| `pyproject.toml` | Set basedpyright to standard mode | Enforce type checking |
| `tests/unit/test_context.py` | Create | Verify factory |

### Testing Checklist

- [ ] `basedpyright src/lorecraft/` outputs no errors in standard mode
- [ ] `pytest tests/unit/test_context.py` passes
- [ ] Existing integration tests still pass (no runtime changes)
- [ ] Spot-check: Open a command handler (e.g., `commands/inventory.py`); verify no casts and types are shown in IDE

### Handoff Notes

- **Difficulty:** Medium. Protocol definition is straightforward; factory consolidation is mechanical but affects multiple entry points.
- **Risk:** Low if you test integration paths (websocket, scheduler, tests all still work).
- **Blockers:** Sprint 5 must be complete (error paths need to be clear).
- **Time estimate:** 3 hours code + 1 hour testing = 4 hours per person.

---

## Sprint 7: Web & Admin Characterization Tests

**Goal:** Lock in current behavior before refactors (Sprint 8). Audit §2.3.

**Depends on:** Sprint 6 (types must be reliable for test assertions).

**Impact:** Critical paths now tested; confidence to refactor safely.

### Deliverables

1. **Web Layer Integration Tests** (`tests/integration/test_frontend_integration.py`, ~300 lines)

**Scenarios to cover:**
- `test_player_login_creates_session` — `POST /lobby/create` creates player + session cookie
- `test_player_enter_game_shows_room` — `GET /game` renders current room
- `test_command_execution_via_post` — `POST /command take coin` updates inventory
- `test_session_reconnection` — Disconnect + reconnect preserves state
- `test_command_error_is_user_readable` — `POST /command bad_syntax` shows error message
- `test_room_update_broadcast` — When player1 takes item, player2's room view updates
- `test_feed_pagination` — Feed grows correctly; old messages scroll off
- `test_unknown_command_rejection` — `POST /command frobulate` returns "I don't understand"

**Structure:**
```python
@pytest.fixture
def client():
    """Test client with clean DB."""
    app.state.lorecraft = AppState(...)
    return TestClient(app)

@pytest.mark.asyncio
async def test_player_login_creates_session(client):
    response = client.post("/lobby/create", json={"username": "alice"})
    assert response.status_code == 200
    assert "lorecraft_session" in response.cookies
    player = session.query(Player).filter_by(username="alice").one()
    assert player is not None
```

2. **Admin API Integration Tests** (`tests/integration/test_admin_api_comprehensive.py`, ~250 lines)

**Scenarios:**
- `test_admin_login` — Admin can mint JWT token
- `test_admin_list_players` — `GET /admin/players` returns all online players
- `test_admin_teleport_player` — `POST /admin/players/{id}/teleport` moves player
- `test_admin_edit_room` — `PUT /admin/rooms/{id}` updates room description
- `test_admin_read_audit_log` — `GET /admin/audit?filter=...` paginated, filterable
- `test_admin_clock_control` — `POST /admin/clock/pause` pauses time
- `test_admin_broadcast_message` — `POST /admin/broadcast` sends message to all players
- `test_admin_endpoint_requires_token` — `GET /admin/players` without token returns 401

3. **Event Flow Integration Tests** (`tests/integration/test_event_flow.py`, ~150 lines)

**Scenarios:**
- `test_item_taken_triggers_quest_progression` — Take item → event → quest repo updates
- `test_command_execution_batches_events` — One command → multiple events → all processed
- `test_event_handler_exception_isolation` — One handler fails → other handlers still run
- `test_room_broadcast_on_player_move` — Player moves → `PLAYER_MOVED` event → broadcast to room

### Files to Create

| File | Lines | Purpose |
|------|-------|---------|
| `tests/integration/test_frontend_integration.py` | ~300 | Web layer scenarios |
| `tests/integration/test_admin_api_comprehensive.py` | ~250 | Admin endpoint coverage |
| `tests/integration/test_event_flow.py` | ~150 | Event ordering + handler isolation |
| (Update) `tests/conftest.py` | +fixtures | Shared test setup (client, admin token, players) |

### Testing Checklist

- [ ] `pytest tests/integration/test_frontend_integration.py -v` all pass
- [ ] `pytest tests/integration/test_admin_api_comprehensive.py -v` all pass
- [ ] `pytest tests/integration/test_event_flow.py -v` all pass
- [ ] `pytest --cov=src/lorecraft/ --cov-report=term-missing | grep "^src/"` shows ≥75% coverage on web/, admin/, game/
- [ ] No flaky tests (run twice)

### Handoff Notes

- **Difficulty:** Medium. Testing patterns are straightforward; setting up fixtures takes time.
- **Risk:** Low. Tests don't change production code; they verify behavior.
- **Blockers:** Sprint 6 (types needed for confident assertions).
- **Time estimate:** 4 hours tests + 1 hour debugging = 5 hours per person.

---

## Sprint 8: Module Decomposition (Parallel with Sprint 7)

**Goal:** No module >~400–500 lines with mixed concerns. Audit §2.6.

**Depends on:** Sprint 7 tests (safe to refactor with coverage).

**Impact:** Easier to navigate; clearer responsibilities; faster test feedback.

### Decompositions

#### 1. `web/frontend.py` (1,306 lines) → 4 files

**Before:**
- Lines 1–100: Module state, engine fallback, Jinja2 setup
- Lines 200–415: Route handlers (10+ endpoints)
- Lines 500+: Rendering helpers, feed formatting

**After:**
```
web/
├── routes.py           (~300 lines) — All route handlers
├── session.py          (~150 lines) — Player session logic
├── rendering.py        (~250 lines) — Template helpers, feed formatting
├── __init__.py         (~5 lines) — Export app, router
└── state.py            (exists) — App state
```

**Extract steps:**
1. Move `GET /game`, `POST /command`, `GET /game/feed`, etc. → `routes.py`
2. Move `_get_engines()`, session cookie logic → `session.py`
3. Move `_format_feed_message()`, `_build_room_display()` → `rendering.py`
4. Import all from `main.py` unchanged: `from web.routes import app_router`

**File structure:**
```python
# web/routes.py
from fastapi import APIRouter
router = APIRouter()

@router.get("/game")
async def get_game(request: Request) -> Response:
    ...

@router.post("/command")
async def post_command(request: Request) -> JSONResponse:
    ...

# web/rendering.py
def format_feed_message(msg: FeedMessage) -> dict:
    ...

# web/__init__.py (or main.py)
from web.routes import router
app.include_router(router)
```

#### 2. `game/parser.py` (774 lines) → 3 files

**Before:**
- Lines 1–100: Grammar constants (ARTICLES, PREPOSITIONS, VERB_ALIASES, DIRECTION_ALIASES)
- Lines 100–300: ParseResult/ParsedCommand classes
- Lines 300–600: Parsing logic
- Lines 600+: Context resolution, diagnostics

**After:**
```
game/
├── grammar.py          (~100 lines) — ARTICLES, PREPOSITIONS, aliases (data)
├── parser.py           (~400 lines) — ParsedCommand, parsing logic
└── diagnostics.py      (~100 lines) — Suggestions, error messages
```

**Extract steps:**
1. Move all `ARTICLES`, `PREPOSITIONS`, `VERB_ALIASES`, `DIRECTION_ALIASES` → `grammar.py`
2. Keep parsing logic in `parser.py`
3. Move `get_suggestions()`, spelling-fix logic → `diagnostics.py`
4. Update imports: `from game.grammar import ARTICLES, PREPOSITIONS`

#### 3. `admin/api.py` (817 lines) → 5 files

**Before:** All endpoints in one file (players, rooms, NPCs, world, clock)

**After:**
```
admin/
├── routes/
│   ├── players.py      (~150 lines) — Player endpoints
│   ├── rooms.py        (~150 lines) — Room endpoints
│   ├── npcs.py         (~100 lines) — NPC endpoints
│   ├── world.py        (~150 lines) — World management, reload
│   └── clock.py        (~100 lines) — Clock control
├── api.py              (~100 lines) — Router setup + shared error handling
└── __init__.py
```

**Extract steps:**
1. Split endpoints by resource (players, rooms, etc.)
2. Create `admin/routes/` directory
3. Move player-related routes → `routes/players.py`
4. Import + register all routers in `admin/api.py`

**Example:**
```python
# admin/routes/players.py
from fastapi import APIRouter
router = APIRouter(prefix="/players")

@router.get("/")
async def list_players(state: AppState = Depends(get_app_state)):
    ...

# admin/api.py
from admin.routes.players import router as players_router
admin_router.include_router(players_router)
```

#### 4. `services/inventory.py` (583 lines) → Extract shared helper

**Issue:** 6 near-identical take/drop methods with repeated search + disambiguation logic.

**Solution:** Extract `ItemActionExecutor` helper

```python
# services/inventory.py (top of file, before take/drop methods)
class ItemActionExecutor:
    """Shared item-finding + disambiguation logic."""

    def find_item(
        self,
        query: str,
        search_fn: Callable[[str], list[Item]],
        not_found_msg: str,
    ) -> Item:
        """Find unique item or raise ValidationError."""
        matches = search_fn(query)
        if not matches:
            raise NotFoundError(not_found_msg)
        if len(matches) > 1:
            raise ValidationError(
                f"Multiple matches for '{query}': {[m.name for m in matches]}"
            )
        return matches[0]

# Usage in _take_one, _drop_one, etc.
def _take_one(self, query: str, ctx: GameContext) -> None:
    item = self.executor.find_item(
        query,
        lambda q: ctx.item_repo.search_in_room(ctx.room.id, q),
        "You don't see that here."
    )
    # ... rest of take logic
```

### Files to Create/Move

| File | From | To | Lines |
|------|------|-----|-------|
| `web/routes.py` | `web/frontend.py` lines 200–415 | new | ~300 |
| `web/rendering.py` | `web/frontend.py` lines 500+ | new | ~250 |
| `web/session.py` | `web/frontend.py` lines 1–100 | new | ~150 |
| `game/grammar.py` | `game/parser.py` lines 1–100 | new | ~100 |
| `game/diagnostics.py` | `game/parser.py` lines 600+ | new | ~100 |
| `admin/routes/players.py` | `admin/api.py` (subset) | new | ~150 |
| `admin/routes/rooms.py` | `admin/api.py` (subset) | new | ~150 |
| (etc.) | | |  |

### Testing Checklist

- [ ] `pytest tests/integration/test_frontend_integration.py -v` still passes after web/ split
- [ ] `pytest tests/integration/test_admin_api_comprehensive.py -v` still passes after admin/ split
- [ ] `basedpyright src/lorecraft/` has no new errors
- [ ] No changes to public APIs (imports from main.py work unchanged)

### Handoff Notes

- **Difficulty:** Medium. Mechanical refactoring; tests catch mistakes.
- **Risk:** Low if tests exist (Sprint 7).
- **Blockers:** Sprint 7 tests must pass first.
- **Time estimate:** 3 hours refactoring + 2 hours testing = 5 hours per person.

---

## Sprints 9–15: Service Consistency, Extensibility, Tooling

**Brief outlines only.** These depend on Sprints 5–8.

### Sprint 9: Service Consistency & Wiring (3–4 days)

**Tasks:**
- 9.1: Service container in `AppState`; remove ad-hoc instantiation
- 9.2: One event-wiring convention; replace inline `bus.on()` in `main.py`
- 9.3: DRY six near-identical inventory methods (continue from Sprint 8 `ItemActionExecutor`)
- 9.4: Consolidate item-matching logic in `ItemRepo`

**Files:** `state.py`, `main.py`, `services/inventory.py`, `repos/item_repo.py`

**Graphify insight:** InventoryService (46 edges) is god node; consolidation here ripples to all inventory commands.

---

### Sprint 10: Extensibility Seams (3–4 days)

**Tasks:**
- 10.1: Pluggable dialogue side effects (handler registry replacing hardcoded `set_flags`/`give_item`/`start_quest`)
- 10.2: Pluggable dialogue conditions (predicates beyond flags: level, item, quest state)
- 10.3: Pluggable command conditions (registry instead of hardcoded `_evaluate_condition`)
- 10.4: Document + demonstrate feature-registration pattern (combat will be first consumer)

**Files:** `npc/dialogue.py`, `game/registry.py`, new `features/interface.py`

---

### Sprint 11: Browser E2E Harness (2–3 days)

**Task:**
- 11.1: Playwright/Selenium test harness for HTMX UI (full-flow scenarios: login, move, take, talk, reload)

**Files:** New `tests/e2e/`

---

### Sprint 12: Simulation Harness MVP (3–5 days)

**Task:**
- 12.1: `tests/simulation/` with multi-player scenario runner (load-test 10 concurrent players)

**Files:** New `tests/simulation/`

---

### Sprint 13: Observability & CI Quality Gates (3–4 days)

**Tasks:**
- 13.1: Structured logging (stdlib `logging` with correlation IDs from `TransactionContext`)
- 13.2: Instrumentation: command latency + event-handler timing
- 13.3: CI: pytest + coverage threshold + basedpyright + ruff as required checks

**Files:** `config.py` (logging setup), new `.github/workflows/` CI

---

### Sprint 14: Unify Command Lifecycle (2–3 days)

**Task:**
- 14.1: Extract shared 13-step transaction/event/audit lifecycle; both `/ws` and `/command` paths call it

**Files:** New `game/lifecycle.py` (or extend `engine.py`)

---

### Sprint 15: Core UX Completion (2–3 days)

**Tasks:**
- 15.1: World clock / weather status bar push via WS
- 15.2: Multi-player live lists finished (complete `[~]` STATUS items)

**Files:** `web/frontend.py` (or `web/rendering.py` after Sprint 8), `services/clock.py`

---

## Foundation Exit Criteria (Gate for Sprints 16+)

All must be true before combat/trading work starts:

- [ ] Zero silent `except Exception` blocks in `src/` (Sprint 5)
- [ ] Zero `cast(GameContext, ctx)` / `cast(Any, ctx)` in `src/`; basedpyright `standard` mode clean (Sprint 6)
- [ ] One `GameContext` construction path; no optional repo fields (Sprint 6)
- [ ] No module >~500 lines with mixed concerns (Sprint 8)
- [ ] One service wiring convention; no inline `bus.on()` in `main.py` (Sprint 9)
- [ ] Web + admin layers have integration coverage; CI enforces coverage, types, and lint (Sprints 7, 13)
- [ ] Feature-registration pattern documented and demonstrated (Sprint 10)
- [ ] All `[~]` STATUS partials either finished or explicitly retired (Sprint 15)

---

## Delegation Checklist (For Model Handoff)

**Before delegating a sprint:**

- [ ] Read the sprint section + FILES table
- [ ] Verify all dependencies from prior sprints are done
- [ ] Run the existing test suite to establish baseline
- [ ] Do NOT skip the "Testing Checklist" section
- [ ] Ping back with questions on ambiguous requirements

**Model assignments (suggested):**

| Sprint | Models | Rationale |
|--------|--------|-----------|
| 5 | Haiku + Sonnet | Low complexity; mostly find/replace + logging |
| 6 | Sonnet | Medium complexity; protocol + factory requires careful design |
| 7 | Sonnet | Testing strategy; fixtures need care |
| 8 | Haiku | Mechanical refactoring; good for verifying test coverage |
| 9–15 | Sonnet (for design) + Haiku (for implementation) | Design-heavy early sprints; implementation-heavy later ones |

---

## Success Metrics

**After Sprints 5–8 (estimated 2–3 weeks):**
- `basedpyright src/ --outputjson | jq '.summary.errorCount'` → `0`
- `grep -r "except Exception" src/lorecraft/ | wc -l` → `0` (or ≤ 2 for intentional cases)
- `pytest --cov=src/lorecraft/ --cov-report=term-missing | grep "^src/lorecraft/" | awk '{print $NF}' | sort -u` → no file <75%
- Code audit rating improves from 6.5/10 → 7.5/10

**After Sprints 9–15 (full foundation phase, estimated 5–8 weeks):**
- All foundation exit criteria met
- Ready to start combat (Sprint 18+) without fear of refactoring mid-feature

---

## Questions / Ambiguities

If delegating to another model, call out:
- Fixture strategy for multi-player tests (shared DB vs. per-test isolation)
- Logging format (structured JSON vs. human-readable)
- Coverage threshold enforcement (75% or higher?)
- Protocol vs. ABC for CommandHandler (Python 3.12 supports both)

---

**Document version:** 2026-07-02
**Last updated by:** Claude Haiku 4.5
**For questions, consult:** CODE_AUDIT.md (foundation band §5–15 breakdown)
