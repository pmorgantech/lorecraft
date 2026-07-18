---
kindle_doc_weaver: ignore
---

# E2E Browser Test Plan

Status: proposal (not yet implemented). Scope: expand `tests/e2e/` coverage of
the HTMX/Alpine/WebSocket game UI. Author date: 2026-07-06.

## Guiding principle

The e2e tier is expensive (real Chromium + real uvicorn socket, serial). It must
earn that cost. A test belongs here **only if it depends on one of three things
an ASGI-transport integration test cannot see**:

1. Real DOM / HTMX swaps (`hx-swap`, OOB updates).
2. Alpine reactive state (`x-model`, `x-show`, `x-data`).
3. WebSocket-driven cross-client updates (the `/ws` push path in `app.js`).

Anything that is pure command→response correctness (economy math, bank balance,
parser edge cases) stays in `tests/integration/`. This plan deliberately omits
those even though they *run* in a browser.

## Current coverage (baseline)

| File | Covers |
|------|--------|
| `test_gameplay_flows.py` | create→spawn, move+take refresh, one dialogue→quest step, ArrowUp history recall, `help` line-breaks |
| `test_map_and_mobile_ui.py` | map modal open/render, Escape close, mobile tab bar |
| `test_ui_refresh_on_item_actions.py` | `get all` room-pane refresh, actor-only messaging |

**Structural gap:** everything is single-player. The entire WebSocket multiplayer
layer (`broadcast_to_room` in `frontend.py`; `feed_append`, `player_joined`,
`player_left`, `state_change` in `app.js`) has zero end-to-end coverage.

---

## Harness additions required first

These are prerequisites; the test cases below depend on them.

### H1. Two-player fixture (`conftest.py`)

The existing `page` fixture yields one browser context. Multiplayer tests need a
second, independent, logged-in context in the same live server.

```python
@pytest.fixture
def second_page(browser: Any) -> Iterator[Any]:
    context = browser.new_context()
    p = context.new_page()
    yield p
    context.close()
```

Plus a shared helper module (extract the duplicated `_create_character` /
`_send_command` currently copy-pasted across all three test files into
`tests/e2e/_helpers.py`). This dedup is a precondition, not a nice-to-have —
three divergent copies will rot.

### H2. WS-settled signal

WS pushes are async: after Player A acts, Player B's panel updates on the next
event loop turn, not synchronously. Every multiplayer assertion must use
`page.wait_for_function(...)` / `locator.wait_for()` against B's DOM — never a
bare `assert` immediately after A's command. Document this in a helper docstring
so it isn't relitigated per-test.

The WS connection itself is established via the ticket exchange
(`POST /auth/ws-ticket` → `/ws?ticket=...`, see `app.js`). Tests should wait for
the connection to be live before asserting pushes. Candidate signal: the status
dot gaining `bg-emerald-500` in `ws.onopen`, or a `page.wait_for_function` on
`window`-exposed WS state. Pin this down during H1 implementation.

### H3. Offline toggle (only for the reconnect test, P5)

Playwright `context.set_offline(True/False)` to exercise `app.js` reconnect +
`reconnect_sync` backfill. Kept separate because it is timing-sensitive.

---

## Priority 1 — Multiplayer / WebSocket (new file: `test_multiplayer_realtime.py`)

Highest value: unique to e2e, high real-world risk, currently uncovered. All use
the H1 two-context fixture; both characters start in Village Square of Ashmoore.

### P1.1 `say` propagates to another player in the room
- **Why e2e:** exercises the full WS push path; integration tests can't open the socket.
- **Steps:** A and B both in Village Square. A: `say hello there`. B sends nothing.
- **Assert:** `wait_for_function` that B's `#feed` inner text contains `hello there`.

### P1.2 `player_joined` updates "Here Now"
- **Steps:** B in Village Square (`#player-count` == 1). A logs in / walks into the square.
- **Assert:** B's `#player-count` increments and A's username appears in
  `#players-online` — via WS, without B acting.

### P1.3 `player_left` decrements the panel
- **Steps:** A and B in the square. A: `go east`.
- **Assert:** B's `#player-count` drops and A's name disappears.

### P1.4 Dropped item becomes visible to the other player
- **Steps:** A carries an item (take it first). A: `drop <item>`.
- **Assert:** B's `#room-description` "You notice:" gains the item via `state_change`.
  Then A: `take <item>` → B's room pane loses it again.

### P1.5 Observer sees room-narration form (closes the 2026-07-04 bug's other half)
- **Steps:** A and B in a room with a takeable item. A: `take <item>`.
- **Assert:** A's feed shows `You take` (existing single-player test);
  **additionally** B's feed shows the third-person `<A> takes <item>` form, and
  A's feed does **not** contain that third-person line. This pairs with the
  existing actor-only test to prove both sides of the split.

---

## Priority 2 — Auth & session lifecycle (new file: `test_auth_flows.py`)

Real security surface; only the create happy-path is covered today. Selectors
confirmed against `lobby.html` (login tab uses `#enter-username` /
`#enter-password`; create tab uses `#username` / `#create-password`).

### P2.1 Log in to an existing character via the Log In tab
- **Steps:** create a character, then in a fresh context go to `/lobby`, stay on
  the default "Log In" tab, fill `#enter-username`/`#enter-password`, submit.
- **Assert:** lands on `/game` as the same character (same start room, same name).

### P2.2 Wrong password is rejected (401), user stays out of the game
- **Steps:** create character; new context; Log In tab with correct username, wrong password.
- **Assert:** not redirected to `/game` (stays on lobby / shows error). Guards the
  `InvalidCredentialsError → 401` branch in `enter_world`.

### P2.3 Unknown username on Log In tab does NOT silently create an account
- **Why:** `enter_world` docstring explicitly calls this out (`allow_create=False`);
  a typo must 404, not spawn an empty character.
- **Steps:** new context; Log In tab; random never-created username + any password.
- **Assert:** 404 / stays on lobby; no `/game` session established.

### P2.4 Session persists across reload
- **Steps:** create character → `/game`; `page.reload()`.
- **Assert:** still in `/game` as the same character (cookie-backed session).

### P2.5 Unauthenticated `/game` redirects to `/lobby`
- **Steps:** fresh context, navigate straight to `/game` with no session.
- **Assert:** redirected to `/lobby` (or 401/redirect per `get_current_player`).

---

## Priority 3 — Interaction flows touching real JS/Alpine (extend `test_gameplay_flows.py`)

### P3.1 Command history: ArrowDown + multi-entry navigation
- **Gap:** existing test only does single-entry ArrowUp+Enter.
- **Steps:** submit `look`, then `inventory`, then `go east` (all via Enter).
  ArrowUp three times should walk back through them; ArrowDown should walk forward.
- **Assert:** `#command-input` value matches the expected entry at each step, and
  index resets after a submit. Directly guards the Alpine `x-model` seam that
  produced the original recall bug.

### P3.2 Full dialogue traversal then dismiss
- **Gap:** existing test clicks exactly one choice.
- **Steps:** `talk mira`; navigate a multi-choice branch; then `bye` / close.
- **Assert:** `#dialogue-overlay` is present during, and gone after dismissal.

### P3.3 Locked door → key golden path
- **World:** `key_gallery` / "cage key" + `lock`/`unlock`/`open`/`close` commands exist.
- **Steps:** navigate to the key gallery, `take cage key`, `unlock`/`open` the target
  exit, then `go` through it.
- **Assert:** `#room-description` shows the room beyond the previously-locked door.
  Strong multi-step regression anchor.

### P3.4 Invalid command robustness
- **Steps:** submit gibberish (`asdfqwer`).
- **Assert:** feed shows the parser's "don't understand"-style response **and**
  `#command-input` still clears + refocuses (proves `handleCommandSuccess` runs
  even on a non-mutating response).

---

## Priority 4 — Panels that update but aren't asserted rendered

### P4.1 Minimap current-room highlight moves on movement
- **Steps:** note the active node in `#minimap` SVG; `go east`; re-read.
- **Assert:** the highlighted/current node changed. Distinct from the modal-open test.

### P4.2 Equipment flow
- **Steps:** obtain a wieldable/wearable item; `wield`/`wear` it; then `unwield`/`remove`.
- **Assert:** the equipment/inventory panel reflects equipped state and reverts.

### P4.3 Feed autoscroll + top/bottom controls
- **Steps:** generate enough feed messages to overflow; click "↑ top" then "↓ bottom".
- **Assert:** `#feed` scrollTop moves to 0 then back to scrollHeight; new messages
  keep it pinned to bottom.

---

## Priority 5 — High-value but flaky; gate carefully

### P5.1 WS reconnect / resync backfill
- **Uses H3** (`set_offline`). A and B connected; set B offline; A: `say ...` (missed);
  set B online; `app.js` reconnect + `reconnect_sync` / `feed?since=` should backfill.
- **Assert (with generous polling):** B's feed eventually contains the missed line.
- **Caveat:** timing-sensitive; implement last, with long `wait_for_function` timeouts.

### Explicitly deferred (NOT e2e)
- Clock/NPC-schedule-driven movement (`time_update`/`clock_tick`) — too slow/
  non-deterministic; keep in integration or the simulation tier.
- Economy math, bank balances, parser tables — integration tier; no render/socket
  dependency, so they don't justify e2e cost.

---

## Suggested rollout order

1. **H1 + H2** (fixtures, shared helpers, WS-settled signal) — unblocks everything.
2. **P1** multiplayer suite — the marquee gap.
3. **P2** auth suite — small, high-certainty, independent of H1.
4. **P3** interaction extensions.
5. **P4** panel-render assertions.
6. **P5** reconnect (last, isolated, generous timeouts).

## Risks & mitigations

- **Flakiness from async WS pushes** → never assert synchronously after a
  cross-client action; always `wait_for_function` on the receiver's DOM (H2).
- **Selector drift** → centralize selectors/helpers in `_helpers.py` (H1) so a UI
  change updates one place, not four files.
- **Serial runtime growth** → e2e is already serial (`make test-e2e`, no `-n`).
  Keep each test to one golden assertion; push correctness-only checks down to
  integration so the e2e suite stays lean.
- **Fixture DB isolation** → the per-test `live_server` fixture already gives a
  fresh sqlite DB; multiplayer tests must share *one* `live_server` across both
  contexts (same server, two browsers), so both `page` and `second_page` take the
  same `live_server` arg in the test signature.
