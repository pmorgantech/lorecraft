# Lorecraft — Roadmap

**A concise list of *remaining* work.** Completed sprints (1–34: foundation hardening, the Tier 1
engine-core primitives, the whole Tier 2 pillar feature band, and the tier-split follow-ons) have
been moved to [`roadmap_completed.md`](roadmap_completed.md) to keep this readable. Per-version
detail is in [`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and
the deferred multiplayer test pass are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-05, v0.38.1)

Foundation, the Tier 1 engine-core primitives, the entire pillar-driven Tier 2 feature band
(exploration · trading · questing · puzzles, plus inventory/equipment, traits/skills, character
condition, and transit), and the Tier 1 / Tier 2 / web **tier-split** refactor are all **complete**
(`src/lorecraft/engine/` is import-pure; features live under `features/`; hosts under
`webui/{player,admin}/`). Player onboarding/account UX shipped except the intro walkthrough, which
moved to the wishlist.

**Set aside to [`wishlist.md`](wishlist.md):** combat & PvP (ready-to-restore specs — a supporting
system, not the centerpiece), and the multiplayer trade/transit **test pass** (coverage-hardening
of already-complete subsystems).

**What's actually left:** a measure-first **performance & scaling band** (Sprints 35–38), and one
new **Tier 1 engine primitive** — timed room effects (Sprint 39, design-first). That's the whole
active roadmap below.

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

## Sprint 35 — Performance telemetry & baseline ⟵ do first

**Goal:** Make optimization evidence-driven. **Capture the "before" picture before touching any hot path.**

| # | Task | Status |
|---|------|--------|
| 35.1 | Baseline micro-benchmark harness `scripts/perf_baseline.py` — drives real parse / condition / dispatch / commit paths against the Ashmoore world in a disposable DB; reports p50/p95/p99 per operation (checked in, reproducible before/after) | [x] Landed with first baseline. Reveals parser entity-resolution is **O(visible entities)**: `examine` parse is 0.7 ms baseline → **4.8 ms @25 items → 17 ms @100 items** (p99 ~36 ms), while condition eval is ~0.002 ms and a no-op commit ~0.015 ms. |
| 35.2 | Structured perf logging in `observability.py`: `time_operation(name)` ctx-manager; instrument `command_parse`, `condition_evaluate`, `db_commit`, `scheduler_tick`, `broadcast_send` (warn >50 ms) | [x] `time_operation(name, *, warn_ms=50.0)` added to `observability.py` — DEBUG normally, WARNING over budget, never swallows exceptions; txn/corr IDs auto-attached by the root filter. Instrumented all five sites (`command_parse`/`condition_evaluate`/`db_commit` in `engine.py`, `scheduler_tick` in `scheduler.py`, `broadcast_send` on both `ConnectionManager` broadcasts). Call sites stay stable for 35.3 to layer persistence into the ctx-manager. |
| 35.3 | Analytics API `/admin/analytics/performance` — p50/p95/p99 by operation from audit `duration_ms` payloads (extends existing latency query) | [ ] |

## Sprint 36 — Parser entity-resolution scaling *(prioritized by the 35.1 baseline)* — ✅ complete

**Goal:** The baseline shows parse cost is **linear in visible-entity count**, not a cache-miss problem. Fix the resolution itself before considering memoization.

**Outcome:** parse cost is now roughly **flat** in inventory size and the tail is gone — cumulative vs. the 35.1 baseline, `parse:examine@100items` went **16.92 → 1.82 ms p50 (9.3×)** with **p99 ~18 → ~1.9 ms**. Profiling drove the fix: the bottleneck was DB round-trips (36.1) then full-`Item` ORM materialization (36.2), *not* the matcher scan the sprint was originally scoped around — so 36.2 became a column projection rather than a name/alias index, and 36.3's memoization gate came back **negative** (resolution no longer material).

| # | Task | Status |
|---|------|--------|
| 36.1 | Eliminate the per-item DB round-trips in `GameContext.get_inventory()` (batch-load item rows in one query instead of `item_repo.get()` per stack) | [x] Landed via new `ItemRepo.get_many(ids)`; also fixed `_pair_with_items` (room-contents/`get_visible_entities` path). `perf_baseline.py`: `parse:examine@25items` **4.79 → 1.47 ms p50 (3.3×)**, `@100items` **16.92 → 3.01 ms p50 (5.6×)**. |
| 36.2 | ~~Index visible entities/inventory by normalized name+alias once per parse~~ → **column projection** (profiling showed full-`Item` materialization, ~72% of parse, was the residual cost — the matcher scan was only ~6%) | [x] `get_visible_entities`/`get_inventory` now use `ItemRepo.name_index(ids)`, a `select(Item.id, Item.name, Item.aliases)` projection — no ORM instances, no decoding the unused `usable_with`/`loot_table`/`effects` JSON columns. `@25items` **1.47 → 1.13 ms p50**, `@100items` **3.01 → 1.82 ms p50**, and the **p99 tail collapsed ~22 → ~1.9 ms**. Semantics-preserving. |
| 36.3 | Re-run `perf_baseline.py`; record before/after in the sprint. Only add result memoization (LRU keyed on `(raw, player_id, entity_hash)`) if resolution is still material after 36.1–36.2 | [x] Re-measured (above). At ~1.8 ms p50 / ~1.9 ms p99 for 100 items — well under the 50 ms "slow" line and flat in entity count — resolution is **no longer material**, so **no LRU memoization added**. A cross-command immutable-`Item` cache stays available as a future lever but isn't justified by the numbers. |

## Sprint 37 — Scheduler batching, pool tuning & load test

**Goal:** Batch same-epoch jobs into one commit; tune the DB pool; add a repeatable multi-player load test.

| # | Task | Status |
|---|------|--------|
| 37.1 | Batch scheduler execution: accumulate mutations across all due jobs, apply + commit once (preserve atomicity; verify via simulation) | [ ] |
| 37.2 | Connection-pool tuning knobs (`pool_size`/`pool_recycle`) in `config.py`/`Settings` for many concurrent players; document in deployment notes | [ ] |
| 37.3 | Load test (`tests/simulation/test_load.py`): N `VirtualPlayer`s issuing commands concurrently; report p95/p99 command latency before vs. after | [ ] |

## Sprint 38 — Concurrency decision gate *(only if 35–37 telemetry shows a hard limit)*

**Goal:** Revisit multithreading/multiprocessing **with data**, not speculatively. Likely order if needed: async command loop → parser thread-pool → async scheduler → (last resort) region sharding. See the analysis notes captured with Sprint 35.

| # | Task | Status |
|---|------|--------|
| 38.1 | Decide + document, from real load-test telemetry, whether/what concurrency to add and its transaction-isolation plan (own session per worker, serialized commits, `GameRng` determinism preserved) | [ ] |

### Recommended next step (2026-07-05)

**Sprint 36 is complete** — parser entity-resolution is no longer a scaling concern (`parse:examine@100items` **16.92 → 1.82 ms p50, 9.3×**, p99 tail gone, cost flat in inventory size). The evidenced bottleneck the 35.1 baseline surfaced is fixed, and 36.3's memoization gate came back negative, so there's no further parser work to do here.

**35.2 is done** — `time_operation(name)` now wraps the five hot operations and emits structured perf logs (WARNING over the 50 ms budget). Next is **35.3**: surface those measurements as p50/p95/p99 by operation via `/admin/analytics/performance`, extending the existing `command_latency_percentiles` query. That needs the per-operation durations to reach the audit log — the 35.2 call sites are already placed so the persistence can be layered into `time_operation` without touching them. After 35.3, **Sprint 37** (scheduler batching, pool tuning, and the multi-player load test) is the remaining measured-optimization work, feeding the Sprint 38 concurrency gate.

**Suggested order:** ~~36.1 → 36.2 → 36.3~~ ✅ → **35.2/35.3 (in-app telemetry, next)** → 37 (batching/pool/load test) → 38 (concurrency gate, only if the load test shows a wall).

---

## Sprint 39 — Timed room effects (Tier 1 engine primitive, design-first)

**Goal:** A general, content-agnostic primitive for applying a **time-limited effect to a room** — puzzle timers (a plate opens a gate for 30s), passive occupant auras (slow travel, drain fatigue), weather hazards, lingering zones, farming growth. From [`wishlist.md`](wishlist.md) → *Timed room effects / auras*.

**Design decided (2026-07-05): reuse the Sprint 19 timed-effect primitive — do _not_ add a new model or a component carrier.** `ActiveEffect` (`engine/models/meters.py`) is already generic over `entity_type`/`entity_id`; `EffectService.apply()` / `active_for(session, entity_type, entity_id)` already exist; the scheduler-driven expiry sweep (`_on_time_advanced` → `EFFECT_EXPIRED`) already runs. **A room effect is just `entity_type="room"`, `entity_id=<room_id>`.**

- A parallel `RoomEffect` model + scheduler runner would **duplicate the expiry-sweep machinery** — this engine deliberately keeps one timing mechanism (cf. transit reusing `SchedulerService`, no second timer).
- A component carrier (like `ItemInstance` components) is the **wrong shape** — components are per-instance *item* state, not timed room state.

**"Room effect" bundles two mechanics with shared storage but different read/hook surfaces** — this is exactly what 39.1 must pin down before any code:
1. **Room-state effects** (gate open, exit sealed) — mutate the *room/exit*; read by movement.
2. **Occupant auras** (fatigue drain, slow travel) — affect *players in* the room; applied on-enter / resolved per action or per tick.

| # | Task | Status |
|---|------|--------|
| 39.1 | **Design spec first.** A room-effect hook interface over the Sprint 19 `EffectDef`/`EffectService`: `on_apply(room)` / `on_expire(room)` for room-state, plus how occupant auras are read (movement gate + a room-scoped `ModifierRegistry` source vs. a per-tick occupant sweep). Settle the two-mechanics split, the trigger surface (a Sprint 30 mechanism/plate calling `apply(...)` with a TTL), and interaction with existing mechanism items. Write it up as a new Tier 1 primitive section in [`engine_core.md`](engine_core.md). **No implementation until this is reviewed.** | [ ] |
| 39.2 | Room-effect application + expiry on the existing primitive: register room-scoped `EffectDef`s; `apply(entity_type="room", …, expires_at_epoch=now+ttl)`; `on_expire` reverses room-state (closes the gate). Reuses the existing sweep — no new scheduler, no new model. | [ ] |
| 39.3 | Read/gate points: movement/exit checks and modifier resolution consult `active_for("room", room_id)`; a plate/mechanism (Sprint 30) applying a timed "gate open" room effect is the first content example. | [ ] |
| 39.4 | Tests: expiry sweep closes a gate opened for N ticks; an occupant aura modifies a resolved value; audit-regression stays stable; content-lint validates room `EffectDef` state. | [ ] |

> **Sequencing:** independent of the performance band — 39.1 (design) can be picked up now; 39.2+ wait on that spec's review. If both progress at once, keep them on separate branches/worktrees to avoid roadmap churn.

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| ~~Bug/todo letterbox~~ | Implemented in Sprint 10.5 as the issues tracking system (see [`roadmap_completed.md`](roadmap_completed.md)) |
| Inventory encumbrance / wear slots | After equipment + combat |
| `lorecraft.tools.simulation` CLI (JSON scenario files, N-bot load runs, latency/throughput reports) | Enhancement on top of the Sprint 12.1 pytest-based harness; see `tooling_infrastructure.md` §5. Overlaps Sprint 37.3's load test and the multiplayer sim-test pass in [`wishlist.md`](wishlist.md). |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| Player-facing bug reports | In-game `/report-bug` command (after core issues system stable) |
| Analytics dashboard & visualizations | After the Sprint 13 observability instrumentation; overlaps Sprint 35.3 |
| Database inspector / state editor | Admin tool for advanced troubleshooting |
| Multiplayer trade/transit test pass | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Multiplayer sim-test coverage* (was Sprint 65) |
| Combat & PvP | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Combat, reframed* (ready-to-restore specs) |

---

## Sprint numbering (avoid duplicates)

- **Used:** 1–34 (incl. 10.5), 35–38 (performance band), 39 (timed room effects), 40–41 (admin console: live-refresh + registered issue components — **done**, v0.37.0), and 42 (Issues tab filter/sort + player-report live-refresh — **done**, v0.38.0).
- **Reserved but never used:** 43–60 (left as a gap from an earlier combat renumber).
- **Retired to [`wishlist.md`](wishlist.md):** 61–64 (combat core, combat commands/UI, combat testing, PvP consent), and 65 (multiplayer trade/transit tests). Don't reuse these numbers for unrelated work — if that work returns, restore it under fresh numbers.
- **Next new sprint: 43.** Don't recycle a number that appears here or in [`roadmap_completed.md`](roadmap_completed.md).

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
