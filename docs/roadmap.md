# Lorecraft — Roadmap

**A concise list of *remaining* work.** Completed sprints (1–34: foundation hardening, the Tier 1
engine-core primitives, the whole Tier 2 pillar feature band, and the tier-split follow-ons) have
been moved to [`roadmap_completed.md`](roadmap_completed.md) to keep this readable. Per-version
detail is in [`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and
the deferred multiplayer test pass are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-06, v0.41.4)

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

## Sprint 43 — Session record & playback (advanced testing) — ✅ complete

**Goal:** record real/scripted player command streams and replay them — one scenario across **N
simulated players**, or a mix concurrently — for regression (golden audit-trail diff), load
(p50/p95/p99), and soak/fuzz. Mostly a **consolidation** of pieces that already exist: the audit
log (recording), the `VirtualPlayer`/`SimulationServer` harness (playback), `test_load.py` (N-player
fan-out + metrics), and the seeded-`GameRng` audit-regression determinism. **Full plan:
[`session_replay.md`](session_replay.md).** Supersedes the Backlog `lorecraft.tools.simulation` note.

| # | Task | Status |
|---|------|--------|
| 43.1 | **Phase 1** — `record` from the audit log → scenario JSON; single-actor `replay` via one `VirtualPlayer`; assert the normalised audit trail against a golden (data-drives `test_audit_regression.py`). | [x] `lorecraft.tools.session_replay`: versioned scenario JSON (logical actors, `{t, actor, raw}`, `world_yaml`/`rng_seed` stamps), `record_scenario()` + `record` CLI off any audit DB, shared `normalize_events()`. Replay: `tests/simulation/replay.py` (fresh `VirtualPlayer`, fast timing); `test_audit_regression.py` now data-driven off checked-in `scenarios/golden_path.json` with a **checked-in golden trail** (`golden_path.audit.json`; regen via `LORECRAFT_UPDATE_GOLDENS=1`). Sim-server factory takes `rng_seed`. Unit + sim suites green. (v0.39.4) |
| 43.2 | **Phase 2** — N-player fan-out (`--players N`) reusing the load-test percentile report; replace the fixed `test_load.py` script with recorded traffic. | [x] `fan_out_scenario()` in `tests/simulation/replay.py` maps a single-actor scenario onto N fresh concurrent `VirtualPlayer`s; report assembly (`percentile`/`latency_report`) moved to `lorecraft.tools.session_replay` (unit-tested, CLI-reusable). `test_load.py` now replays `scenarios/load_default.json` (the old read-heavy loop) and `LORECRAFT_LOAD_TEST_SCENARIO` points it at any recorded session — verified with `golden_path.json` @5 players. Same report shape/knobs (`_PLAYERS`/`_JITTER_MS`/`_JSON`); numbers match the post-WAL baseline (p50 ~56 ms @10). (v0.39.6) |
| 43.3 | **Phase 3** — mixed concurrent scenarios (`--mix`), longer soak runs, and an opt-in `simulation`-marked CI job. | [x] `mix_scenarios(server, scenarios, repeats=…)` replays distinct recorded sessions concurrently, each looped for soak, over a shared `_run_concurrent` runner (fan-out is now the same-script case); report = shared `percentile_summary()` + mix context. New `test_soak.py` mixes golden-path + load-default (quick 2-repeat default; `LORECRAFT_SOAK_REPEATS` for real soaks — verified @25 = 325 commands, p99 ~30 ms). CI's existing `simulation` job gains a `workflow_dispatch` `soak_repeats` input for opt-in longer runs. (v0.40.0) |

## Sprint 44 — Weather-driven world effects — ✅ complete

**Goal:** the weather/season state machine mostly flavored descriptions — make it drive a real
mechanic. From [`wishlist.md`](wishlist.md) → *Weather-driven world events*.

**Design note (corrected during build):** weather is **global clock state affecting rooms by terrain**,
a natural fit for the **§3.5 modifier resolver** (read-through, like room auras / terrain gating) —
*not* the Sprint 39 timed-room-effect primitive (that is for *localized, TTL* effects, and would mean
materializing a redundant effect row per outdoor room on every weather change). Each behavior keeps one
owner: the clock owns weather, terrain defs own terrain, the resolver composes them.

| # | Task | Status |
|---|------|--------|
| 44.1 | `WeatherTerrainModifierSource` (`features/weather/modifiers.py`): harsh weather (`COLD_WEATHERS` + thunderstorm/heavy_rain) subtracts a penalty from a skill-gated terrain's `required_skill`, read through `resolve_for`. So a **blizzard can push a marginal traveller below a mountain pass's survival requirement** via the *existing* movement terrain gate — no new movement code, no materialized room effects. Registered at module import; unit-tested (penalty in harsh weather on skill-gated terrain, none in clear weather or on sheltered terrain). | [x] |

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
| 45.3 | **Phase 3 (later)** — future global channels (shout/tell) reuse the channel; colored/prefixed per-channel tags; **per-channel mute** (a preferences-blob setting suppressing a channel's messages — folded in 2026-07-05, same rendering/preferences surface as the tags); mobile tab-collapse polish. | [~] **Per-channel mute shipped (v0.40.10):** `PlayerPreferences.mute_chat` (default off, round-trips) + settings checkbox; the game client reads `window.LORECRAFT_MUTE_CHAT` and drops other players' chat broadcasts client-side (own echo still renders). Preference unit tests + a two-player mute e2e. **Deferred (blocked on backlog):** global channels (shout/tell) don't exist yet, so multi-channel colored/prefixed tags and channel-reuse wait on those; mobile tab-collapse is cosmetic polish. Reopen when shout/tell land. |

---

# Reconciled from the unrecorded planning list (2026-07-05)

A 2026-07-03 planning session produced five items that were never written into the repo (follow,
channel colors + mute, contextual hints, item discovery journal, scavenger hunt events). Reconciled
2026-07-05: channel colors were already Sprint 45 Phase 3 and **mute** is now folded in beside them;
**contextual hints** parked in [`wishlist.md`](wishlist.md) pending a design pass; the remaining
three are scheduled below.

## Sprint 46 — Item discovery journal — ✅ complete

**Goal:** the Sprint 25.3 `journal` records places visited, people met, lore learned, and active
quests — but **not items**. Add discovered-item tracking so finding a distinct item is a recorded
exploration payoff (pillar #1).

| # | Task | Status |
|---|------|--------|
| 46.1 | Track first discovery per item *definition* (not per instance): `Player.discovered_items`, set on first `take`/`examine` — same pattern as `met_npcs` (set on first `talk`). | [x] `Player.discovered_items` + `SaveSlot.discovered_items` (save/load parity); `_record_item_discovery()` in `inventory/service.py`, hooked from `_emit_item_taken` (all take paths) and `examine` — per-definition (`item.id`), idempotent. Additive sqlite migrations for both tables. (v0.40.5) |
| 46.2 | `journal` gains an "Items discovered" section (names, matching the journal's existing read-only style); unit tests for first-discovery tracking + journal output. | [x] `JournalService._show_items` between people-met and lore, same read-only style ("Items discovered: …" / "none yet."). 4 new unit tests (take-once idempotent, examine-without-take, journal shows names, empty state). |

## Sprint 47 — Follow command (social movement) — ✅ complete

**Goal:** `follow <player>` — when the target moves, followers move with them; `unfollow` stops.
Overt, not stealthy: both sides see narration. The lightweight slice of the wishlist's *Player
groups / parties* idea, and a natural pairing with transit (board the ferry together) without
building parties.

| # | Task | Status |
|---|------|--------|
| 47.1 | Follow state + movement hook: follower auto-moves on the target's movement event, re-running the standard movement gates (terrain/skill/hidden/locked exits) — a failed gate breaks the follow with a message to both sides. Chains allowed (A→B→C), cycles rejected. | [x] New Tier 2 `follow` feature: `FollowService` holds an **in-memory** follow graph and subscribes to `PLAYER_MOVED`; co-located connected followers are re-moved through the standard `MovementService.move` gates via a `dataclasses.replace` sub-context. Gate failure (detected by not reaching the target's room) breaks the follow and notifies both sides; chains cascade because each auto-move emits its own `PLAYER_MOVED`; cycles rejected at follow-time. Needed a generic engine seam — `GameContext.pending_deliveries` (deferred async WS pushes drained by `broadcast_command_effects`), since the event bus is synchronous but followers need live pushes. (v0.40.6) |
| 47.2 | `follow <player>`/`unfollow` commands (movement feature `commands.py`); narration both sides ("X begins following you."); bare `follow` shows current status; tests incl. a multi-room chain and a gate-failure break. | [x] `follow`/`unfollow` verbs (movement category); both-sides narration on follow/unfollow (target push); bare `follow` shows who you follow + who follows you. 5 unit tests (follower moves, A→B→C chain cascade, self/absent reject, cycle reject, gate-failure break) + a **live two-player WS check** (follower's socket gets "You follow X east." + panel refresh). |

## Sprint 48 — Scavenger hunt events (design-first) — ✅ complete

**Goal:** a scheduled, time-boxed world event: a themed set of items/clues is placed across rooms
and players hunt them for a reward (coins, a collectible mark, lore). Exploration-pillar event
content on existing primitives (scheduler + world clock for the window, item spawns, flags/journal
for progress, news/feed for announcement). The simplest, *non-instanced* slice of the wishlist's
*Instanced minigames / scenarios* idea.

| # | Task | Status |
|---|------|--------|
| 48.1 | **Design spec first** — YAML event definition (item/clue set, spawn room pools, cadence or admin trigger, duration, completion rule, reward), announcement surface (news + feed), and per-player progress storage (flags vs. a small table). No implementation until reviewed. | [x] Spec: [`scavenger_hunt.md`](scavenger_hunt.md). Decisions: **flags** for per-player progress (persist via SaveSlot, journal-visible, no new table); **news items** for announcements (synchronous DB — sidesteps the async-from-scheduler broadcast problem, no live feed ping in v1); YAML defs loaded into an in-memory registry (weather/terrain pattern); completion = "find all" (count variant deferred); reuses scheduler / `ItemLocationService.spawn` / `ITEM_TAKEN` / `LedgerService` / `GameRng` — no new Tier 1 mechanism. (v0.40.7) |
| 48.2 | Implement as a Tier 2 feature package (`features/…` + manifest, auto-discovered) per the spec; content-lint for event YAML references (item keys, room pools). | [x] `features/hunts/` (auto-discovered): `models.py` (Pydantic `HuntDef`/`HuntsDocument`, registry, `lint_hunts`), `service.py` (`open`/`close`/`ITEM_TAKEN` find + reward/`SCHEDULED_JOB_DUE` open-close), `commands.py` (read-only `hunts` verb). Progress in player flags, announcements as news items, coins via ledger. `LORECRAFT_HUNTS_YAML_PATH` config; loaded into the registry at startup. Wired into `ServiceContainer`/`register_all_commands`/`main`. (v0.40.8) |
| 48.3 | Ashmoore example hunt + tests: event opens/closes on schedule, item found → progress → reward, audit-regression stays stable. | [x] `world_content/hunts.yaml` — the Harvest Trinket Hunt (3 trinket items added to `world.yaml` as definitions only) across village_square/market/inn. 10 unit tests (open spawns clues, find→progress→reward+lore, no double-reward, close despawns, scheduled open/close, content-lint clean/dirty, dup-id + negative-coin validation, shipped-content lints against the real world). Audit-regression golden **unchanged** (definitions aren't placed by default). |

---

## Sprint 49 — Encumbrance & analytics dashboard (Tier 2 + observability) — ✅ complete

**Goal:** Ship inventory encumbrance (weight capacity, gating) as a Tier 2 feature, and build an admin analytics dashboard surfacing p50/p95/p99 operation latency (Sprint 35.3 data) with player activity heatmaps and an operation timeline. Together: player progression friction + ops visibility.

**Reconciled (2026-07-06):** the **encumbrance model already existed** as the `encumbrance` feature (`Item.weight`, `resolve_carry_capacity`/`total_carried_weight`/`encumbrance_band` composing the §3.5 modifier resolver, strength-scaled base) with `take` already gated on overload ("You can't carry any more weight.") and fatigue draining by band — so 49.1 was largely done. The design also gates **carrying** (can't pick up more than you can haul), which is kept over the roadmap's speculative "too heavy to *move*" (movement-weight gating would be punishing and duplicate the take gate). This sprint therefore delivered the genuinely-missing pieces: the **weight UI** and the **analytics dashboard**.

| # | Task | Status |
|---|------|--------|
| 49.1 | **Encumbrance model** — weight, carry capacity, bands, overload gate. | [x] **Already shipped** as the `encumbrance` feature (`rules.py`) + `Item.weight`; `take` gates on overload; fatigue drains by band. No change needed beyond the snapshot helper below. |
| 49.2 | **Weight UI** — player sees current/max carried weight + band on the inventory panel. | [x] `encumbrance_snapshot()` (current/capacity/band) + `encumbrance_snapshot_for()` wired into all three inventory renders (game page, HTMX command OOB swap, `/partials/inventory`); weight line in `inventory.html`, colored by band (amber/red). Verified live ("WEIGHT 0.0 / 80.0"). *(The roadmap's "too heavy to move" movement gate was dropped in favour of the existing take-gate — see reconciliation note.)* |
| 49.3 | **Analytics dashboard** (`/admin/analytics/dashboard` + admin console tab): p50/p95/p99 latency by operation, operation timeline (recent ops w/ duration), player-activity-by-hour heatmap. | [x] New `operation_timeline()` + `activity_by_hour()` analytics queries; `/admin/analytics/dashboard` one-call endpoint (Observer auth, `range`/`timeline_limit`); new **Analytics tab** in the admin console (latency table, CSS-bar heatmap, recent-ops table — no charting lib). |
| 49.4 | Tests. | [x] Timeline (order/limit) + heatmap (24-bucket density) analytics unit tests; dashboard endpoint schema + auth integration tests; `encumbrance_snapshot` unit test; audit-regression golden unchanged. (v0.40.9) |

> **Rationale:** Encumbrance ties inventory to character progression; the analytics dashboard keeps ops/player-health visible post-launch. Both low-risk over stable foundations (inventory, traits, audit).

---

## Sprint 50 — E2E browser test coverage (multiplayer & UX layers)

**Goal:** Expand `tests/e2e/` coverage from single-player smoke tests to **multiplayer/WebSocket paths**,
**auth flows**, and **interaction seams** (Alpine/HTMX). Existing e2e tests cover the happy path
(create→move→take) and basic UI (map modal, mobile tab bar). The gaps: **zero coverage of the WS
multiplayer layer** (`broadcast_to_room`, `feed_append`, `player_joined`/`player_left`, cross-client
state updates) and **auth edge cases** (wrong password, unknown username, session reload). These are
high-risk, expensive to verify manually, and only testable end-to-end.

**Guiding principle:** a test belongs in e2e *only if* it depends on real **DOM / HTMX swaps**, **Alpine
reactive state**, or **WebSocket-driven cross-client updates**. Pure command→response correctness
(economy math, parser edge cases) stays in `tests/integration/` — e2e is expensive (real Chromium +
real uvicorn socket, serial). **Full plan: [`e2e_test_plan.md`](e2e_test_plan.md).**

Rollout order: harness prerequisites first (H1–H3), then Priority 1 (multiplayer, the marquee gap),
then P2 (auth), then P3–P4 (interaction + panels), finally P5 (flaky reconnect tests, last with
generous timeouts).

**Status: complete (v0.41.0 → v0.41.5).** Harness (H1–H3) + **15 new e2e tests** shipped: P1 (5,
multiplayer/WS), P2 (5, auth), P3 (4, interaction), P4 (3, panels), P5 (1, reconnect). The three
subtasks first deferred for missing world content / harness capability were then **addressed for
real** (v0.41.5) rather than fabricated around:
- **P3.3** (locked door → key): added a **Vault Hall → Inner Vault** locked-exit area off the
  locksmith gallery, with a matching **Good Key** and non-matching **Bad Key** (obvious names) — real
  world content demonstrating the exit lock/unlock mechanic.
- **P4.2** (equipment): added an **Equippable Helmet** (`slot: head`, `wearable`) in the blacksmith
  forge — closing the "demo world can't exercise equipment" gap; the wear/remove flow moves it out of
  and back into the inventory panel.
- **P5.1** (reconnect): confirmed `set_offline(True)` doesn't sever an open WebSocket, so added a
  clearly-named client debug hook (`window.Lorecraft.debugDropSocket()`) to force a real drop, and
  test that the socket **auto-reconnects and resumes live delivery**. Backfilling messages *missed
  during* an outage is intentionally out of scope — `say`/room narration are transient (not audited to
  the room feed), so replaying them would need durable chatter persistence, a separate design decision.
All new content placed off the audit-regression golden path (golden unchanged); full suite 980 +
e2e 36 green.

| # | Task | Status |
|---|------|--------|
| 50.1 | **Harness H1: two-player fixture & shared helpers.** New `second_page` fixture yielding an independent browser context in the same live server; extract duplicated `_create_character` / `_send_command` helpers from the three existing e2e test files into a centralized `tests/e2e/_helpers.py` (precondition: rotten duplication will diverge otherwise). | [x] Shared helpers centralized in `tests/e2e/_helpers.py` (`create_character`, `send_command`, `send_command_via_enter`, `enable_separate_chat`, `navigate_to_locksmiths_gallery`); `second_page` fixture added to conftest; all existing e2e test files updated to use shared helpers; existing e2e tests verified passing. (v0.41.0) |
| 50.2 | **Harness H2: WS-settled signal.** Document and implement a pattern for multiplayer assertions: `page.wait_for_function(...)` on the receiver's DOM, never synchronous asserts after a cross-client action (WS pushes are async; the next event loop turn is when B's panel updates after A acts). Candidate signal: status dot gaining `bg-emerald-500` in `ws.onopen`, or `page.wait_for_function` on `window`-exposed WS state. | [x] The status dot is server-rendered already carrying `bg-emerald-500`, so it can't signal connection — instead added a minimal `window.Lorecraft.isConnected()` accessor (real WS flag set in `ws.onopen`/`onclose`, also useful for console debugging). `wait_for_ws_connected()` polls it; multiplayer pattern documented in _helpers.py module docstring. (v0.41.0) |
| 50.3 | **Harness H3: offline toggle** (only for P5.1 reconnect test). Playwright `context.set_offline(True/False)` to exercise `app.js` reconnect + `reconnect_sync` backfill. Kept separate because it is timing-sensitive. | [x] `set_offline(page, offline)` added, but **`set_offline(True)` does not sever an already-open WebSocket in this Chromium** (`window.Lorecraft.isConnected()` stays `true` for the whole offline window). Superseded for reconnect testing by `drop_ws()` + the `debugDropSocket()` client hook, which forces a real drop (v0.41.5). See P5 (50.8). |
| 50.4 | **Priority 1 — Multiplayer / WebSocket (`test_multiplayer_realtime.py`):** P1.1 `say` propagates to another player; P1.2 `player_joined` increments "Here Now"; P1.3 `player_left` decrements; P1.4 dropped item becomes visible; P1.5 observer sees third-person narration form (closes the 2026-07-04 actor-only test's other half). | [x] All 5 tests passing. Uses `wait_for_ws_connected()` so the receiver is connected before the actor broadcasts, then asserts on the receiver's DOM. Assertions are username-based on `#players-online` (P1.2/P1.3) rather than `#player-count` — the count is server-rendered and not WS-refreshed, and `village_square` always holds the unconditional `player-2` seed body. (v0.41.0) |
| 50.5 | **Priority 2 — Auth & session lifecycle (`test_auth_flows.py`):** P2.1 log in via the Log In tab (existing char); P2.2 wrong password rejected (401); P2.3 unknown username doesn't silently create an account (404); P2.4 session persists across reload (cookie); P2.5 unauthenticated `/game` redirects to `/lobby`. | [x] All 5 passing (v0.41.1). Reconciled to actual server behavior: the browser login form re-renders the lobby with an inline error + **400** (not 401/404 — those are the JSON `/auth/*` codes), and unauthenticated `/game` returns **401** (not a `/lobby` redirect; `allow_query_player_id` defaults off). Tests assert the security property (stays on lobby / never reaches `/game`). Added `login_character` helper + `new_page` cookie-isolated context factory fixture. |
| 50.6 | **Priority 3 — Interaction flows (extend `test_gameplay_flows.py`):** P3.1 command history ArrowUp/ArrowDown multi-entry + index reset; P3.2 full dialogue traversal + dismiss; P3.3 locked door → key golden path (multi-step regression anchor); P3.4 invalid command robustness. | [x] All 4 passing. P3.1/P3.2/P3.4 (v0.41.2); **P3.3 (v0.41.5)** now backed by real content — a **Vault Hall** (off the locksmith gallery, east) with a locked east exit (`key_item_id: good_key`) to the **Inner Vault**, holding a matching **Good Key** and non-matching **Bad Key**. Test drives the full mechanic: locked with no key → Bad Key rejected → Good Key unlocks → pass through. |
| 50.7 | **Priority 4 — Panel rendering (`test_panel_rendering.py`):** P4.1 minimap current-room highlight moves on movement; P4.2 equipment/wield/wear/unwield flow; P4.3 feed autoscroll + top/bottom controls. | [x] All 3 passing. P4.1/P4.3 (v0.41.3); **P4.2 (v0.41.5)** now backed by a real **Equippable Helmet** (`slot: head`, `wearable`) in the blacksmith forge. Test: `take` → helmet in inventory; `wear` → leaves the loose inventory panel; `remove` → returns. Closes the "demo world can't exercise equipment" gap. |
| 50.8 | **Priority 5 — High-value but flaky (P5.1 reconnect test).** WS reconnect / resync backfill: A and B connected; set B offline; A acts (missed); set B online; `app.js` reconnect + `reconnect_sync` / `feed?since=` should backfill. Assert (with generous polling) B's feed eventually contains the missed line. Implement last with long `wait_for_function` timeouts. | [x] **Reframed & passing (v0.41.5).** `context.set_offline(True)` doesn't sever an open WebSocket here (verified — `isConnected()` stays true, so a "missed" message is a false positive), so the test forces a genuine drop via a clearly-named client debug hook `window.Lorecraft.debugDropSocket()` and asserts the socket **auto-reconnects and resumes live delivery** (`test_reconnect.py`, stable over repeated runs). **Backfill of messages missed *during* the outage is intentionally out of scope:** `say`/room narration are transient — not written to the room audit feed (verified: a reload doesn't show a room-mate's `say`), so neither a reload nor `reconnect_sync` can replay them. Durable chatter replay would be a separate design decision (persist room broadcasts), not a bug this test asserts. |

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| ~~Bug/todo letterbox~~ | Implemented in Sprint 10.5 as the issues tracking system (see [`roadmap_completed.md`](roadmap_completed.md)) |
| ~~Inventory encumbrance / wear slots~~ | **Promoted to [Sprint 49](#sprint-49--encumbrance--analytics-dashboard-tier-2--observability)** |
| ~~`lorecraft.tools.simulation` CLI~~ | **Promoted to [Sprint 43](#sprint-43--session-record--playback-advanced-testing)** (session record & playback) — see [`session_replay.md`](session_replay.md). |
| ~~Analytics dashboard & visualizations~~ | **Promoted to [Sprint 49](#sprint-49--encumbrance--analytics-dashboard-tier-2--observability)** |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| Player-facing bug reports | In-game `/report-bug` command (after core issues system stable) |
| Database inspector / state editor | Admin tool for advanced troubleshooting |
| Multiplayer trade/transit test pass | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Multiplayer sim-test coverage* (was Sprint 65) |
| Combat & PvP | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Combat, reframed* (ready-to-restore specs) |

---

## Sprint numbering (avoid duplicates)

- **Used:** 1–34 (incl. 10.5), 35–38 (performance band), 39 (timed room effects), 40–41 (admin console: live-refresh + registered issue components — **done**, v0.37.0), 42 (Issues tab filter/sort + player-report live-refresh — **done**, v0.38.0), 43–49 (promoted from the wishlist 2026-07-05: session record/playback, weather-driven effects, chat/feed split, item discovery journal, follow command, scavenger hunt events, encumbrance + analytics dashboard), and 50 (e2e browser test coverage — multiplayer/UX layers).
- **Reserved but never used:** 51–60 (left as a gap from an earlier combat renumber).
- **Retired to [`wishlist.md`](wishlist.md):** 61–64 (combat core, combat commands/UI, combat testing, PvP consent), and 65 (multiplayer trade/transit tests). Don't reuse these numbers for unrelated work — if that work returns, restore it under fresh numbers.
- **Next new sprint: 51.** Don't recycle a number that appears here or in [`roadmap_completed.md`](roadmap_completed.md).

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
