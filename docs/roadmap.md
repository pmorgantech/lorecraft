# Lorecraft — Roadmap

**A concise list of *remaining* work.** Completed sprints (1–34: foundation hardening, the Tier 1
engine-core primitives, the whole Tier 2 pillar feature band, and the tier-split follow-ons) have
been moved to [`roadmap_completed.md`](roadmap_completed.md) to keep this readable. Per-version
detail is in [`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and
the deferred multiplayer test pass are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-06, v0.42.3)

Foundation, the Tier 1 engine-core primitives, the entire pillar-driven Tier 2 feature band
(exploration · trading · questing · puzzles, plus inventory/equipment, traits/skills, character
condition, and transit), and the Tier 1 / Tier 2 / web **tier-split** refactor are all **complete**
(`src/lorecraft/engine/` is import-pure; features live under `features/`; hosts under
`webui/{player,admin}/`). Player onboarding/account UX shipped except the intro walkthrough, which
moved to the wishlist.

**Set aside to [`wishlist.md`](wishlist.md):** combat & PvP (ready-to-restore specs — a supporting
system, not the centerpiece), and the multiplayer trade/transit **test pass** (coverage-hardening
of already-complete subsystems).

**The active roadmap is now clear.** The measure-first **performance & scaling band** (Sprints 35–38)
is complete — parser resolution (Sprint 36, 9.3×) and SQLite **WAL mode** (Sprint 37.4, ~20–29× on
commits) landed; scheduler-commit batching (37.1) and the concurrency gate (38.1) were **deferred to
[`wishlist.md`](wishlist.md)** because the evidence showed fsync (not CPU) was the wall and WAL
removed it. **Sprint 39 — timed room effects** (the last planned Tier 1 primitive) is also **✅ complete**:
the §3.9 design, `on_apply`/`on_expire` hooks, occupant auras (`RoomAuraModifierSource`), and the
`passage_open` timed-gate content example all shipped.

**Newly promoted from [`wishlist.md`](wishlist.md) (2026-07-05):** **Sprint 43** — session record &
playback for advanced testing ([`session_replay.md`](session_replay.md)) — **✅ complete, v0.40.0**;
**Sprint 44** — weather-driven world effects (on the Sprint 39 primitive) — **✅ complete**;
**Sprint 45** — split the social/chat feed from the narrative feed (opt-in). See the *Promoted from
the wishlist* section below.

**Reconciled from an unrecorded 2026-07-03 planning list (2026-07-05):** **Sprint 46** — item
discovery journal; **Sprint 47** — `follow` command; **Sprint 48** — scavenger hunt events
(design-first). Per-channel **mute** folded into Sprint 45 Phase 3; **contextual hints** parked in
[`wishlist.md`](wishlist.md) pending a design pass. See the *Reconciled* section below.

**Recently completed (v0.37.0, 2026-07-05):** admin console **live-refresh** on content changes
(Sprint 40) and **registered issue components** as a strict dropdown (Sprint 41) — both born from
admin-console issues raised during dogfooding. Detail in [`roadmap_completed.md`](roadmap_completed.md)
and [`../CHANGELOG.md`](../CHANGELOG.md).

**Recently completed (v0.42.0–v0.42.3, 2026-07-06):** **Sprint 51** — four more Analytics-tab widgets
(timeline chart, top commands, NPC interaction stats, quest completion funnel), plus a real bug fix
found along the way: `AuditEvent.target_id` was never populated, so `npc_interaction_counts` was
always empty against real data — **merged (v0.42.0)**. Follow-ons since: roadmap archive of completed
sprints (v0.42.1), single-concurrent-session auth enforcement + login UX (v0.42.2), and e2e test
parallelization via pytest-xdist (~2.56×, v0.42.3).

**Active work:** every numbered sprint through **54** is complete (2026-07-07): Sprint 52 — global
channels & the channel framework (v0.45.0, finishing chat Phase 3 / Sprint 45.3), Sprint 53 —
collectible marks (v0.43.0), Sprint 54 — celestial cycles (v0.44.0). The numbered roadmap is clear
again; candidate work lives in the *Backlog* table and [`wishlist.md`](wishlist.md). Next new
sprint: **55**.

**Known pre-existing e2e failures (2026-07-07, not Sprint 52 fallout — they fail on v0.44.0 too):**
`test_admin_session.py::test_stale_token_http_401_forces_logout` and
`test_auth_flows.py::test_login_to_existing_character_via_login_tab` (timeout waiting for the
post-login `/game` navigation) — likely interaction with the v0.42.2 single-concurrent-session
enforcement. Needs a dedicated fix pass.

Design anchors: [`engine_core.md`](engine_core.md) (the Tier 1/2/3 boundary) and
[`wishlist.md`](wishlist.md) (design pillars + idea backlog).

---

# Performance & scaling band (Sprints 35–38) — measure, then optimize; no threading yet

**Goal:** Establish performance telemetry, capture a **baseline before any optimization**, then implement high-ROI single-process optimizations (indexing/batching/caching, pool tuning) to support many concurrent players. No architectural changes; the single-process / single-threaded design (architecture.md §1) is retained until real telemetry proves a hard limit.

**Rationale:** Adding multithreading/multiprocessing now would introduce concurrency bugs (shared `GameContext`, SQLite single-writer, `GameRng` determinism) without evidence of a real bottleneck. Measure first (Sprint 35), fix only where the baseline shows cost, and revisit concurrency when telemetry shows contention.

> These sprints fill the reserved 35–60 numbering gap (see *Sprint numbering* below).

## Sprint 35 — Performance telemetry & baseline — ✅ complete

**Goal:** Make optimization evidence-driven. **Capture the "before" picture before touching any hot path.**

| # | Task | Status |
|---|------|--------|
| 35.1 | Baseline micro-benchmark harness `scripts/perf_baseline.py` — drives real parse / condition / dispatch / commit paths against the Ashmoore world in a disposable DB; reports p50/p95/p99 per operation (checked in, reproducible before/after) | [x] Landed with first baseline. Reveals parser entity-resolution is **O(visible entities)**: `examine` parse is 0.7 ms baseline → **4.8 ms @25 items → 17 ms @100 items** (p99 ~36 ms), while condition eval is ~0.002 ms and a no-op commit ~0.015 ms. |
| 35.2 | Structured perf logging in `observability.py`: `time_operation(name)` ctx-manager; instrument `command_parse`, `condition_evaluate`, `db_commit`, `scheduler_tick`, `broadcast_send` (warn >50 ms) | [x] `time_operation(name, *, warn_ms=50.0)` added to `observability.py` — DEBUG normally, WARNING over budget, never swallows exceptions; txn/corr IDs auto-attached by the root filter. Instrumented all five sites (`command_parse`/`condition_evaluate`/`db_commit` in `engine.py`, `scheduler_tick` in `scheduler.py`, `broadcast_send` on both `ConnectionManager` broadcasts). Call sites stay stable for 35.3 to layer persistence into the ctx-manager. |
| 35.3 | Analytics API `/admin/analytics/performance` — p50/p95/p99 by operation from audit `duration_ms` payloads (extends existing latency query) | [x] `time_operation` now yields an `OperationTiming`; `CommandEngine` stamps a per-operation `perf` breakdown (`command_parse`/`condition_evaluate`/`db_commit`) onto each `COMMAND_EXECUTED` payload. New `analytics.operation_latency_percentiles` groups those (plus the top-level handler time as `command_handler`) into p50/p95/p99 per operation, exposed at `GET /admin/analytics/performance` (`Observer` auth, `range` param). End-to-end test asserts the payload; endpoint/query/`OperationTiming` unit-tested. |

## Sprint 36 — Parser entity-resolution scaling *(prioritized by the 35.1 baseline)* — ✅ complete

**Goal:** The baseline shows parse cost is **linear in visible-entity count**, not a cache-miss problem. Fix the resolution itself before considering memoization.

**Outcome:** parse cost is now roughly **flat** in inventory size and the tail is gone — cumulative vs. the 35.1 baseline, `parse:examine@100items` went **16.92 → 1.82 ms p50 (9.3×)** with **p99 ~18 → ~1.9 ms**. Profiling drove the fix: the bottleneck was DB round-trips (36.1) then full-`Item` ORM materialization (36.2), *not* the matcher scan the sprint was originally scoped around — so 36.2 became a column projection rather than a name/alias index, and 36.3's memoization gate came back **negative** (resolution no longer material).

| # | Task | Status |
|---|------|--------|
| 36.1 | Eliminate the per-item DB round-trips in `GameContext.get_inventory()` (batch-load item rows in one query instead of `item_repo.get()` per stack) | [x] Landed via new `ItemRepo.get_many(ids)`; also fixed `_pair_with_items` (room-contents/`get_visible_entities` path). `perf_baseline.py`: `parse:examine@25items` **4.79 → 1.47 ms p50 (3.3×)**, `@100items` **16.92 → 3.01 ms p50 (5.6×)**. |
| 36.2 | ~~Index visible entities/inventory by normalized name+alias once per parse~~ → **column projection** (profiling showed full-`Item` materialization, ~72% of parse, was the residual cost — the matcher scan was only ~6%) | [x] `get_visible_entities`/`get_inventory` now use `ItemRepo.name_index(ids)`, a `select(Item.id, Item.name, Item.aliases)` projection — no ORM instances, no decoding the unused `usable_with`/`loot_table`/`effects` JSON columns. `@25items` **1.47 → 1.13 ms p50**, `@100items` **3.01 → 1.82 ms p50**, and the **p99 tail collapsed ~22 → ~1.9 ms**. Semantics-preserving. |
| 36.3 | Re-run `perf_baseline.py`; record before/after in the sprint. Only add result memoization (LRU keyed on `(raw, player_id, entity_hash)`) if resolution is still material after 36.1–36.2 | [x] Re-measured (above). At ~1.8 ms p50 / ~1.9 ms p99 for 100 items — well under the 50 ms "slow" line and flat in entity count — resolution is **no longer material**, so **no LRU memoization added**. A cross-command immutable-`Item` cache stays available as a future lever but isn't justified by the numbers. |

## Sprint 37 — Pool tuning, load test & the WAL win — ✅ effectively complete

**Goal (as scoped):** batch same-epoch scheduler jobs; tune the DB pool; add a repeatable multi-player load test. **Outcome:** measure-first (37.2 → 37.3 → benchmarks) surfaced that the real bottleneck is **fsync-per-commit on the single SQLite writer**, not the scheduler specifically — so the high-ROI fix turned out to be **SQLite WAL mode (37.4 below)**, which the benchmarks confirm is a broad ~20–29× (scheduler) / ~4–6× (commands) win. **37.1 scheduler batching became marginal after WAL and is deferred to [`wishlist.md`](wishlist.md).**

| # | Task | Status |
|---|------|--------|
| 37.2 | Connection-pool tuning knobs (`pool_size`/`pool_recycle`) in `config.py`/`Settings`; document in deployment notes | [x] `db_pool_size` (5) / `db_pool_recycle` (1800s) + `LORECRAFT_DB_POOL_SIZE`/`_RECYCLE`; `db._pool_kwargs` applies them **only for a networked backend** (Postgres/MySQL). Documented; unit-tested. |
| 37.3 | Load test (`tests/simulation/test_load.py`): N `VirtualPlayer`s concurrently; report p95/p99 before vs. after | [x] `simulation`-marked test, N players (default 10) over real WebSockets, p50/p95/p99/max (+ JSON, + `LORECRAFT_LOAD_TEST_JITTER_MS`). Lockstep baseline p50 254 → **58 ms after WAL**; p99 475 → **83 ms**. Also fixed a pre-existing harness break that had silently broken the whole `simulation` suite. |
| 37.4 | **SQLite WAL mode** (emerged from the 37.3 benchmarks) — `journal_mode=WAL` + tunable `synchronous` so every commit is cheap instead of a full fsync | [x] `db.configure_sqlite_engine` sets WAL + `synchronous` (default `NORMAL`) via a connect-listener on SQLite engines only; `db_sqlite_wal` / `db_sqlite_synchronous` + `LORECRAFT_DB_SQLITE_*`. `perf_baseline.py` `scheduler_tick@50jobs` **1410 → 48 ms (~29×)**; load test p50 **254 → 58 ms**. Documented; unit-tested; full suite + sim suite green. |
| ~~37.1~~ | ~~Batch scheduler execution into one commit/tick~~ → **deferred to [`wishlist.md`](wishlist.md)** | Marginal after WAL (50 jobs/tick ≈ 48 ms). Restore only if a scheduler-heavy workload appears. |

## Sprint 38 — Concurrency decision gate → **deferred to [`wishlist.md`](wishlist.md)**

**Decision (2026-07-05):** the load-test/benchmark evidence shows the wall is **fsync serialization on a single SQLite writer, not CPU** — adding threads/processes wouldn't parallelize SQLite writes, and WAL (37.4) already removed most of the commit cost. So the concurrency gate stays **closed** and the spec moves to the wishlist; reconsider only if a *post-WAL* realistic-load test shows a hard single-process wall.

### Recommended next step (2026-07-05)

**Sprints 35 and 36 are complete.** Parser entity-resolution is no longer a scaling concern (`parse:examine@100items` **16.92 → 1.82 ms p50, 9.3×**, p99 tail gone, cost flat in inventory size), and the telemetry stack is in place: the `perf_baseline.py` harness (35.1), per-operation `time_operation` logging (35.2), and the live `/admin/analytics/performance` p50/p95/p99-by-operation endpoint (35.3), sourced from the `perf` breakdown now stamped on every `COMMAND_EXECUTED` audit event.

**The performance & scaling band (Sprints 35–38) is effectively complete.** Measure-first paid off twice: Sprint 36 (parser resolution, 9.3×) and the fsync/WAL finding. The dominant cost across every path was **fsync-per-commit on the single SQLite writer**; **SQLite WAL mode (37.4)** fixed it broadly — `scheduler_tick@50jobs` **1410 → 48 ms (~29×)**, load-test p50 **254 → 58 ms**. Consequences, now resolved:

- **37.1 (scheduler-commit batching)** — **deferred to [`wishlist.md`](wishlist.md)**; marginal after WAL.
- **38.1 (concurrency/threading)** — **deferred to [`wishlist.md`](wishlist.md)**; the wall was fsync, not CPU — threads don't parallelize a single SQLite writer. Revisit only if a *post-WAL* realistic-load test shows a hard wall.

**Next: Sprint 39 — timed room effects (design-first).** The whole remaining active roadmap. 39.1 (design spec into `engine_core.md`) is the gate; 39.2+ wait on its review.

**Suggested order:** ~~35~~ ✅ · ~~36~~ ✅ · ~~37 (pool/load/WAL)~~ ✅ · 37.1 + 38.1 → wishlist ✅ → **Sprint 39 (next)**.

---

## Sprint 39 — Timed room effects (Tier 1 engine primitive, design-first) — ✅ complete

**Goal:** A general, content-agnostic primitive for applying a **time-limited effect to a room** — puzzle timers (a plate opens a gate for 30s), passive occupant auras (slow travel, drain fatigue), weather hazards, lingering zones, farming growth. From [`wishlist.md`](wishlist.md) → *Timed room effects / auras*.

**Design decided (2026-07-05): reuse the Sprint 19 timed-effect primitive — do _not_ add a new model or a component carrier.** `ActiveEffect` (`engine/models/meters.py`) is already generic over `entity_type`/`entity_id`; `EffectService.apply()` / `active_for(session, entity_type, entity_id)` already exist; the scheduler-driven expiry sweep (`_on_time_advanced` → `EFFECT_EXPIRED`) already runs. **A room effect is just `entity_type="room"`, `entity_id=<room_id>`.**

- A parallel `RoomEffect` model + scheduler runner would **duplicate the expiry-sweep machinery** — this engine deliberately keeps one timing mechanism (cf. transit reusing `SchedulerService`, no second timer).
- A component carrier (like `ItemInstance` components) is the **wrong shape** — components are per-instance *item* state, not timed room state.

**"Room effect" bundles two mechanics with shared storage but different read/hook surfaces** — this is exactly what 39.1 must pin down before any code:
1. **Room-state effects** (gate open, exit sealed) — mutate the *room/exit*; read by movement.
2. **Occupant auras** (fatigue drain, slow travel) — affect *players in* the room; applied on-enter / resolved per action or per tick.

| # | Task | Status |
|---|------|--------|
| 39.1 | **Design spec first.** A room-effect hook interface over the Sprint 19 `EffectDef`/`EffectService`: `on_apply(room)` / `on_expire(room)` for room-state, plus how occupant auras are read (movement gate + a room-scoped `ModifierRegistry` source vs. a per-tick occupant sweep). Settle the two-mechanics split, the trigger surface (a Sprint 30 mechanism/plate calling `apply(...)` with a TTL), and interaction with existing mechanism items. Write it up as a new Tier 1 primitive section in [`engine_core.md`](engine_core.md). **No implementation until this is reviewed.** | [~] **Spec written — [`engine_core.md`](engine_core.md) §3.9; awaiting review before 39.2.** Decisions (revised after a single-owner audit): room-state effects **write the one authoritative `Exit` state** via `on_apply`/`on_expire` (undo stashed in `payload`) — **movement unchanged, no `opens_exits` read-through** (that would fork exit passability into two stores); auras are a new **`RoomAuraModifierSource`** (§3.5), extending the existing multi-source resolver (no per-tick occupant sweep). The engine gains **no exit awareness** — "open the gate" is a Tier 2 `EffectDef` hook over `RoomRepo`. Each behavior keeps one owner (Exit/movement → passability, §3.4 sweep → timing, §3.5 → modifiers); no new model/table/scheduler. |
| 39.2 | Room-effect application + expiry on the existing primitive: register room-scoped `EffectDef`s; `apply(entity_type="room", …, expires_at_epoch=now+ttl)`; `on_expire` reverses room-state (closes the gate). Reuses the existing sweep — no new scheduler, no new model. | [x] Added `on_apply`/`on_expire` hooks to `EffectDef`; `EffectService.apply()` fires `on_apply` after flush (in the caller's txn); the expiry sweep fires `on_expire` before delete, each isolated in a **savepoint** (`begin_nested`) — a failing hook rolls back only its own writes and the row is **kept for retry** (no `EFFECT_EXPIRED` for it). Unit-tested (fire timing, on_apply-raise rollback, on_expire failure isolation). No new model/scheduler. |
| 39.3 | Read/gate points: movement/exit checks and modifier resolution consult `active_for("room", room_id)`; a plate/mechanism (Sprint 30) applying a timed "gate open" room effect is the first content example. | [x] **Modifier read point:** new Tier 1 `RoomAuraModifierSource` (game/effects.py, shares `_effect_modifiers` with `ActiveEffectModifierSource`) — resolving a **player**'s modifiers pulls in their `current_room_id`'s room effects, so `resolve_for` auto-picks-up auras with no call-site change. **Movement read point:** unchanged (per §3.9 the effect writes the authoritative `Exit`). **Content example:** `features/exploration/room_effects.py` — a `passage_open` room `EffectDef` (on_apply opens an exit + stashes prior `locked`; on_expire restores) and an `open_timed_passage` mechanism side-effect handler so a Sprint 30 plate opens a timed gate from world YAML; wired via exploration's new `register_fn`. Gate + aura integration-tested. |
| 39.4 | Tests: expiry sweep closes a gate opened for N ticks; an occupant aura modifies a resolved value; audit-regression stays stable; content-lint validates that world-content references to room-effect keys (e.g. a plate's `passage_open`) resolve to a registered `EffectDef` and name valid exit directions. Plus (from the 39.1 review): `on_expire`-raises isolation in the sweep; aura lifts on room-leave; a normally-open exit isn't stranded when a `seals_exits` effect expires. | [x] Gate open→relock, normally-open-exit-unchanged, aura modify+lift, `on_expire` savepoint isolation, `on_apply`-raise rollback all covered. Audit-regression stable (no room effects in the Ashmoore script → unchanged output). Added `world/validator._validate_open_timed_passage` shape-lint (non-empty `direction`, positive `ticks`) + tests; the direction→exit resolution stays a runtime concern (item room not known statically). |

> **Sequencing:** independent of the performance band — 39.1 (design) can be picked up now; 39.2+ wait on that spec's review. If both progress at once, keep them on separate branches/worktrees to avoid roadmap churn.

---

# Promoted from the wishlist (2026-07-05)

Newly-scheduled work drawn from [`wishlist.md`](wishlist.md) after the performance band + Sprint 39 wrapped.

## Sprint 45 — Split the social/chat feed from the narrative feed (opt-in)

**Goal:** the single biggest client-UX takeaway — chatter must never scroll room/quest/action output
out of view. Split "world/narrative feed" from "social/channel feed" into two panes/tabs, **as a
toggleable player option** (default preserves today's single feed). From [`wishlist.md`](wishlist.md)
→ *Client UI · Separate the communication log from the narrative feed*. **Full plan:
[`chat_feed_split.md`](chat_feed_split.md).**

Key finding (from planning): chat (only `say` today) and ordinary room narration ("X leaves north.")
share **one channel end to end** (`tell_room` → `feed_append`/`room_event`), so there is no
chat-vs-narrative signal — the split must thread a new `chat` category through GameContext → the
broadcast protocol → `command_result` → `app.js`. It's browser-rendered, so **Phase 2 needs a real
browser to verify** (not the headless unit tests).

| # | Task | Status |
|---|------|--------|
| 45.1 | **Phase 1 (headless-testable)** — GameContext chat channel (`say_chat`/`tell_room_chat` + `chat_messages`); `say_command` switches to it; `command_result.chat_messages` + `broadcast` `message_type:"chat"`; `separate_chat` player preference. | [x] `GameContext.say_chat`/`tell_room_chat` (+ `chat_messages`/`room_chat_messages`); `say` switched ("Say what?" stays narrative); `broadcast_command_effects` emits `message_type:"chat"`; `command_result.chat_messages` on the WS path, `type:"chat"` feed items on the HTMX path, dev-client fallback loop; `PlayerPreferences.separate_chat` (default off, round-trips). Default UX unchanged — both render paths degrade the new type into the single feed until Phase 2. 7 new unit tests. (v0.40.3) |
| 45.2 | **Phase 2 (browser)** — `app.js` dual-pane routing, `index.html` pane, `app.css` styling, settings toggle; verify in a real browser + a two-player e2e (A `say`s → B sees it in the chat pane with the pref on, main feed with it off; "A leaves north." always narrative). | [x] `#chat-pane`/`#chat-feed` in `game.html` (rendered only when `separate_chat` is on — the pane's presence is the routing signal); WS `feed_append`/`message_type:"chat"` → `appendToChat()` in `static/js/app.js` (falls back to the feed without a pane); HTMX command responses routed by `routeChatMessages()` on `htmx:afterSwap`; `chat` msg class + cyan style in `feed_items.html`; settings checkbox + form field. Two-player e2e (`test_chat_feed_split.py`) verifies the full plan scenario in a real browser. Parser note: say phrases with "from/with/to" lose the tail to role parsing — pre-existing, surfaced by the e2e. (v0.40.4) |
| 45.3 | **Phase 3 (later)** — future global channels (shout/tell) reuse the channel; colored/prefixed per-channel tags; **per-channel mute** (a preferences-blob setting suppressing a channel's messages — folded in 2026-07-05, same rendering/preferences surface as the tags); mobile tab-collapse polish. | [x] **Completed by Sprint 52 (v0.45.0):** global channels landed (`tell` P2P + the `newbie` P2ALL topic channel; a distinct `shout` verb was folded into named P2ALL channels by design), colored/prefixed per-channel tags shipped (52.7), and the interim v0.40.10 blanket `mute_chat` was superseded by real **per-channel subscriptions** with a server-side drop (52.5/52.8). Only the cosmetic mobile tab-collapse polish remains unscheduled. |

---

## Sprint 52 — Global channels & the channel framework (finish chat Phase 3)

**Goal:** Add the global chat channels the Sprint 45 chat/feed split was built to carry, and use them
to unblock the deferred **Sprint 45.3** work (colored/prefixed per-channel tags, real per-channel
mute). This finishes the last half-done seam. From [`wishlist.md`](wishlist.md) → *Client UI ·
Colour-coded, prefixed channels* + *Separate the communication log from the narrative feed*.

**Design (decided 2026-07-06).** Two orthogonal axes, deliberately separated:

- **Delivery scope** — a fixed `ChatScope` enum: `P2P` (one player), `P2ROOM` (room occupants),
  `P2ALL` (all online). Maps 1:1 onto the existing `ConnectionManager.send_to_player` /
  `broadcast_to_room` / `broadcast_global`. This is the only hardcoded part — pure topology.
- **Named channels** — identities layered on a scope, held in a **`ChannelRegistry`** (the engine
  owns the *mechanism*, mirroring `CommandRegistry`). A channel declares
  `{ id, scope, tag, color, muteable, default_subscribed }`. `newbie` (P2ALL, default-subscribed,
  muteable) is the seed proving capacity; `auction`/`ooc`/… are later rows, no new code.

**Decisions:** ① `tell` to an **offline** player is **rejected** ("X isn't online right now") — no
store-and-forward (that's a future *mail* feature). ② channels are registered as **engine/code
built-ins for now**; the registry is the seam so **data-driven channel definitions in world YAML**
are an additive follow-on, not a retrofit. ③ **per-channel subscription** generalizes the Sprint 45.3
`mute_chat` boolean (P2P/P2ROOM aren't muteable; P2ALL topic channels are). ④ **rate-limiting/spam
control deferred** (note only). ⑤ named channels are spoken by a **verb per channel** — the registry
auto-registers `newbie <msg>` etc. (registry already warns on verb/alias collisions).

**Phasing follows Sprint 45:** Phase 1 is headless-testable; Phase 2 is browser-rendered and needs a
real browser + two-player e2e to verify.

### Phase 1 — channel framework + engine (headless-testable)

| # | Task | Status |
|---|------|--------|
| 52.1 | `ChatScope` enum + `Channel` descriptor + `ChannelRegistry` (engine mechanism); register built-in `say`/`tell` + seed `newbie`. Registry designed so world-YAML channel defs can be added later without a retrofit. | [x] Landed v0.44.1 — `engine/game/channels.py`; muteable-only-P2ALL enforced in the descriptor; `say`/`tell` register at engine module load (the `command_conditions` precedent), `newbie` from composition (52.4). |
| 52.2 | Channel-aware chat outbox on `GameContext` tagged `(channel, scope, target?)` — replaces the two ad-hoc Sprint 45 lists (`chat_messages`/`room_chat_messages`) with one channel-keyed buffer; `say`/`tell_room` chat routes through it. | [x] Landed v0.44.2 — `chat_echoes` + `chat_outbox` (`ChatMessage` entries); `chat_echo`/`chat_out` resolve scope at emit; unknown channels fall back to P2ROOM (never accidentally global); Sprint 45 wrappers kept. |
| 52.3 | `broadcast.py` routes each outbox entry by scope → `send_to_player` / `broadcast_to_room` / `broadcast_global`; stamps `"channel":"<id>"` alongside `message_type:"chat"`. | [x] Landed v0.44.2 — P2ALL delivery iterates `connected_player_ids()` per-recipient (so 52.5's subscription drop happens server-side) instead of `broadcast_global`; WS `command_result.chat_messages` entries became `{text, channel}` objects (dev clients degrade). |
| 52.4 | Verbs in `commands/social.py`: `tell <player> <msg>` (P2P, offline-reject, actor echo); keep `say`; the registry auto-registers a verb per named channel (`newbie <msg>`). Empty-arg errors stay narrative. | [x] Landed v0.44.3 — `tell`/`whisper` with offline/unknown/self rejection; topic verbs auto-register per channel; `(Tag)` prefix baked into server text so every render path shows it. |
| 52.5 | Per-channel subscription in `webui/player/preferences.py` (generalize `mute_chat` → a channel→on/off map, round-trips); server-side drop for muted P2ALL channels. | [x] Landed v0.44.4 — `channel_subscriptions` map (round-trips, invalid entries dropped, absent = channel default). `mute_chat` retired (say/tell aren't muteable by design; legacy blob keys ignored); the client-side drop gate removed — muting is now entirely server-side. |
| 52.6 | Unit tests: scope routing, offline-tell rejection, verb-per-channel dispatch, subscription drop, channel tag on payload, actor-echo vs recipient. | [x] Folded into each subtask's commit — 24 new unit tests across `test_channels` / `test_chat_broadcast` / `test_chat_verbs` / preference tests. |

### Phase 2 — browser (finishes Sprint 45.3)

| # | Task | Status |
|---|------|--------|
| 52.7 | Colored/prefixed per-channel tags: `appendToChat(channel, …)` in `static/js/app.js` prepends the channel tag + color class; `feed_items.html` per-channel styling (extends the existing cyan `chat` class). | [x] Landed v0.44.5 — `chat-<channel>` class on both render paths; say cyan / tell violet / newbie amber, unknown falls back; the textual `(Tag)` prefix is server-side (52.4), the color client-side. |
| 52.8 | Settings UI: per-channel toggle list replacing the single mute checkbox; wire to the subscription prefs from 52.5. | [x] Landed v0.44.5 — one subscribe checkbox per muteable topic channel (sourced from the engine registry), posting the full map through `apply_updates`. |
| 52.9 | Two-player e2e (extends `test_chat_feed_split.py`): A on `newbie` → subscribed B sees it tagged, muted B doesn't; `tell` reaches only its target; `say` stays room-scoped. | [x] Landed v0.45.0 — three-context e2e: newbie reaches a subscribed player *in another room* with the `chat-newbie` class, is server-dropped for an unsubscribed one; `tell` reaches only its target (+ offline rejection); the Sprint 45 say-routing e2e still passes unchanged. |

**✅ Sprint 52 complete (v0.45.0).**

**Deferred to a follow-on:** data-driven channel defs in world YAML; a distinct `shout` verb (folded
into named P2ALL channels instead); channel scrollback/history; mobile tab-collapse polish;
rate-limiting/spam control.

---

## Sprint 53 — Collectible marks / attunements (discovery-fed progression)

**Goal:** Named passive badges earned by *discovering* things ("Mark of the Wanderer — visit every
district of Ashmoore") — a progression track parallel to leveling, fed by exploration, not combat.
Some cosmetic/lore, some carrying small mechanical boons. Pillar #1 (exploration is progression).
From [`wishlist.md`](wishlist.md) → *Collectible "marks" / attunements*.

**Design (decided 2026-07-06): the hunts feature (Sprint 48) is the template — no new table.**
Mark definitions are **world content** (`world_content/marks.yaml`), loaded into an in-memory
registry at startup with fail-fast validation, exactly like `hunts.yaml`. Earned state is a player
flag (`mark:<id>`), following the hunts `hunt:*` / journal `lore:*` flag conventions. Criteria read
the **journal state that already exists on `Player`** (`visited_rooms`, `met_npcs`,
`discovered_items`, `flags`) — the marks service just evaluates criteria when that state changes
(subscribed via the standard `register(bus)` convention to the same events the journal writers
ride: movement, dialogue, item-take, flag-set). Boons are a **`MarkModifierSource`** feeding the
existing `ModifierRegistry` multi-source resolver (the `RoomAuraModifierSource` pattern) — modest,
flat modifiers per the wishlist's soft-cap principle; no new stacking mechanism.

| # | Task | Status |
|---|------|--------|
| 53.1 | **`features/marks/` package + content pipeline:** `MarkDef` (id, name, description, criteria, optional modifier boons, `hidden` teaser flag), `world_content/marks.yaml` loader + fail-fast validation + content-lint (criteria reference real rooms/items/NPCs), in-memory registry, `FeatureManifest`. | [x] Landed v0.42.6 — hunts-def template throughout; `MarkBoon.kind` typed as the engine `ModifierKind` literal so bad kinds fail at load. |
| 53.2 | **`MarkService`:** criteria evaluation over `Player` journal state; award = set `mark:<id>` flag + feed announcement + audit event; `register(bus)` subscriptions on the discovery-driving events; idempotent (never re-awards). | [x] Landed v0.42.7 — rides `PLAYER_MOVED`/`ITEM_TAKEN`/`QUEST_COMPLETED` (the `QuestService.check_progression` precedent; queued pre-commit so award writes land in the command txn — `COMMAND_EXECUTED` fires *post*-commit and was ruled out). Fixpoint loop chains mark-on-mark criteria. Award announces via `ctx.say` (feed; captured by the command's audit like hunts — no separate audit event). Dialogue-only criteria award on the next qualifying event. |
| 53.3 | **Boons + `marks` command:** `MarkModifierSource` over earned marks wired into the modifier resolver; `marks` verb lists earned marks with descriptions and unearned ones as "???" teasers (hidden marks omitted until earned). | [x] Landed v0.42.8 — `MarkBoonModifierSource` (traits `sources.py` pattern: read-through, idempotent manifest registration); `marks` verb in the exploration help category. |
| 53.4 | **Content + tests + docs:** 3–4 Ashmoore marks in `marks.yaml` (at least one with a boon, one hidden); unit tests (criteria eval, idempotent award, modifier resolution, lint) + an integration test (walk Ashmoore → mark awarded); user/admin guide sections. | [x] Landed v0.43.0 — 4 shipped marks (village_wanderer; friend_of_the_crow; far_strider +5 carry_capacity; hidden deep_delver +5 skill.cartography). Integration test walks the real Ashmoore village via `MovementService.move` → award fires on the completing step; shipped-content lint test pins marks.yaml ↔ world.yaml. Guides updated. |

**✅ Sprint 53 complete (v0.43.0).**

---

## Sprint 54 — Celestial cycles: moons & tides (clock-derived world state)

**Goal:** Lunar phase and tide as world state derived from the existing world clock, gating content
across three pillars: moon-keyed doors/dialogue/rituals (puzzles), tides that reveal a causeway or
shift schedules (transit + exploration), night/phase-only encounters. From
[`wishlist.md`](wishlist.md) → *Celestial cycles — moons & tides*.

**Design (decided 2026-07-06): pure derivation, no new persisted state, no new scheduler.**
`season_for_day(day)` is the precedent — moon phase and tide are **pure functions of the clock**
(`moon_phase_for_day(day)`: an 8-phase cycle; `tide_for_hour(hour)`: high/low on a configurable
period), living beside the season calendar as Tier 1 clock concerns. Change detection rides the
**existing** `HOUR_CHANGED`/`DAY_CHANGED` events (the weather feature's `apply_daily_weather`
pattern); `MOON_PHASE_CHANGED`/`TIDE_CHANGED` are emitted from those handlers. Content gating keeps
each behavior's single owner: **moon-keyed doors/dialogue** are condition-registry entries
(`moon_phase_is:<phase>`, `tide_is:<state>`) for command/dialogue conditions; a **tide-gated
causeway** is a `TIDE_CHANGED` handler writing the one authoritative `Exit` state (the §3.9
one-owner rule — movement unchanged). Status surface extends the Sprint 15.1 world-clock/weather
WS status push.

| # | Task | Status |
|---|------|--------|
| 54.1 | **Tier 1 calendar functions:** `moon_phase_for_day` / `tide_for_hour` (+ cycle constants beside `DAYS_PER_SEASON`) in `engine/clock/`; `MOON_PHASE_CHANGED` / `TIDE_CHANGED` `GameEvent`s; unit tests over cycle boundaries. | [x] Landed v0.43.1 — `engine/clock/celestial.py`: 8-phase 16-day lunar month (deliberately drifts against the 30-day season), semi-diurnal tide (6h per state). |
| 54.2 | **`features/celestial/` package:** `HOUR_CHANGED`/`DAY_CHANGED` handlers detecting phase/tide transitions and emitting the celestial events; `moon_phase_is` / `tide_is` condition handlers (command + dialogue registries); moon/tide in the status-bar WS push + `time`/`look` surfacing. | [x] Landed v0.43.2 — transition handlers compare event endpoints (fast-forwards don't replay skipped states); gates fail closed with in-fiction reasons; moon/tide in `time_update` + initial render + status bar (no `time` verb exists — the status bar *is* the clock surface). |
| 54.3 | **Content + tests + docs:** Ashmoore tide-gated causeway (handler writes `Exit` state on tide change) + a moon-gated dialogue/lore beat; content-lint for celestial condition keys; integration tests (tide opens/closes the causeway across clock advance; moon condition gates dialogue); user/admin guide sections. | [x] Landed v0.44.0 — data-driven `world_content/celestial.yaml` (`tide_gates`, the hunts/marks content-file pattern; no room ids in code) drives the new `creek_crossing → tidal_islet` causeway via authoritative-`Exit` writes (§3.9 one-owner; startup sync matches the wake-up tide; the return exit is ungated so the tide never strands anyone). Moon beat: full-moon-only innkeeper choice → `lore:moonlit_tides` — which required aligning the world validator with the dialogue engine's open-keyed choice contract (`DialogueChoiceData` now `extra="allow"` so registry-condition keys validate). Full lint + integration coverage; guides updated. |

**✅ Sprint 54 complete (v0.44.0).**

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| ~~Bug/todo letterbox~~ | Implemented in Sprint 10.5 as the issues tracking system (see [`roadmap_completed.md`](roadmap_completed.md)) |
| ~~Inventory encumbrance / wear slots~~ | **Promoted to [Sprint 49](roadmap_completed.md)** |
| ~~`lorecraft.tools.simulation` CLI~~ | **Promoted to [Sprint 43](roadmap_completed.md)** (session record & playback) — see [`session_replay.md`](session_replay.md). |
| ~~Analytics dashboard & visualizations~~ | **Promoted to [Sprint 49](roadmap_completed.md)** |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| Player-facing bug reports | In-game `/report-bug` command (after core issues system stable) |
| Database inspector / state editor | Admin tool for advanced troubleshooting |
| Multiplayer trade/transit test pass | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Multiplayer sim-test coverage* (was Sprint 65) |
| Combat & PvP | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Combat, reframed* (ready-to-restore specs) |

---

## Sprint numbering (avoid duplicates)

- **Used:** 1–34 (incl. 10.5), 35–38 (performance band), 39 (timed room effects), 40–41 (admin console: live-refresh + registered issue components — **done**, v0.37.0), 42 (Issues tab filter/sort + player-report live-refresh — **done**, v0.38.0), 43–49 (promoted from the wishlist 2026-07-05: session record/playback, weather-driven effects, chat/feed split, item discovery journal, follow command, scavenger hunt events, encumbrance + analytics dashboard), 50 (e2e browser test coverage — multiplayer/UX layers), 51 (four more analytics widgets + the `target_id` audit fix), 52 (global channels & the channel framework — **scheduled**, finishing chat Phase 3 / Sprint 45.3), 53 (collectible marks / attunements — **scheduled**), and 54 (celestial cycles: moons & tides — **scheduled**).
- **Reserved but never used:** 55–60 (left as a gap from an earlier combat renumber).
- **Retired to [`wishlist.md`](wishlist.md):** 61–64 (combat core, combat commands/UI, combat testing, PvP consent), and 65 (multiplayer trade/transit tests). Don't reuse these numbers for unrelated work — if that work returns, restore it under fresh numbers.
- **Next new sprint: 55.** Don't recycle a number that appears here or in [`roadmap_completed.md`](roadmap_completed.md).

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
| Wear armor | `go north` → forge, `take helmet`, `wear helmet`, `remove helmet` |
| Locked door | `north`→`north`→`east` to Vault Hall; `take good key`, `unlock east`, `go east` → Inner Vault (the Bad Key won't work) |

Empty databases import `world_content/world.yaml` on startup (configurable via `LORECRAFT_WORLD_YAML_PATH`). Integration tests use the same Ashmoore data — no parallel hardcoded world in production code.
