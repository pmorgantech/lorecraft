# Lorecraft — Roadmap

**A concise list of *remaining* work.** Completed sprints (1–34: foundation hardening, the Tier 1
engine-core primitives, the whole Tier 2 pillar feature band, and the tier-split follow-ons) have
been moved to [`roadmap_completed.md`](roadmap_completed.md) to keep this readable. Per-version
detail is in [`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog and set-aside combat/PvP specs
are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-05, v0.36.4)

Foundation, the Tier 1 engine-core primitives, the entire pillar-driven Tier 2 feature band
(exploration · trading · questing · puzzles, plus inventory/equipment, traits/skills, character
condition, and transit), and the Tier 1 / Tier 2 / web **tier-split** refactor are all **complete**
(`src/lorecraft/engine/` is import-pure; features live under `features/`; hosts under
`webui/{player,admin}/`). Player onboarding/account UX shipped except the intro walkthrough.

**Combat & PvP are set aside** to [`wishlist.md`](wishlist.md) (ready-to-restore specs) — combat is
a supporting system, not the centerpiece, and it kept forcing roadmap renumbering.

**What's actually left** is small: a multiplayer trade/transit **test pass** (Sprint 65) and a
measure-first **performance & scaling band** (Sprints 66–69). Everything below is that list.

Design anchors: [`engine_core.md`](engine_core.md) (the Tier 1/2/3 boundary) and
[`wishlist.md`](wishlist.md) (design pillars + idea backlog).

---

## Sprint 65 — Multiplayer trade & transit tests

> The trade and transit subsystems are already complete (Sprints 28–29); these simulation tests
> are independent of combat/PvP. The PvP-consent test portion was set aside with combat/PvP to
> [`wishlist.md`](wishlist.md) (2026-07-05); could be pulled forward if multiplayer trade/transit
> regressions need coverage sooner.

| # | Task | Status |
|---|------|--------|
| 65.1 | Multi-player trade and shared-vehicle transit simulation tests | [ ] |

---

# Performance & scaling band (Sprints 66–69) — measure, then optimize; no threading yet

**Goal:** Establish performance telemetry, capture a **baseline before any optimization**, then implement high-ROI single-process optimizations (indexing/batching/caching, pool tuning) to support many concurrent players. No architectural changes; the single-process / single-threaded design (architecture.md §1) is retained until real telemetry proves a hard limit.

**Cross-cutting / schedulable (66–69 is a number, not a strict order).** This band is infrastructure, not a Tier 2 feature; it can be pulled ahead of Sprint 65 — see the **assessment** below.

**Rationale:** Adding multithreading/multiprocessing now would introduce concurrency bugs (shared `GameContext`, SQLite single-writer, `GameRng` determinism) without evidence of a real bottleneck. Measure first (Sprint 66), fix only where the baseline shows cost, and revisit concurrency when telemetry shows contention.

## Sprint 66 — Performance telemetry & baseline ⟵ do first

**Goal:** Make optimization evidence-driven. **Capture the "before" picture before touching any hot path.**

| # | Task | Status |
|---|------|--------|
| 66.1 | Baseline micro-benchmark harness `scripts/perf_baseline.py` — drives real parse / condition / dispatch / commit paths against the Ashmoore world in a disposable DB; reports p50/p95/p99 per operation (checked in, reproducible before/after) | [x] Landed with first baseline. Reveals parser entity-resolution is **O(visible entities)**: `examine` parse is 0.7 ms baseline → **4.8 ms @25 items → 17 ms @100 items** (p99 ~36 ms), while condition eval is ~0.002 ms and a no-op commit ~0.015 ms. |
| 66.2 | Structured perf logging in `observability.py`: `time_operation(name)` ctx-manager; instrument `command_parse`, `condition_evaluate`, `db_commit`, `scheduler_tick`, `broadcast_send` (warn >50 ms) | [ ] |
| 66.3 | Analytics API `/admin/analytics/performance` — p50/p95/p99 by operation from audit `duration_ms` payloads (extends existing latency query) | [ ] |

## Sprint 67 — Parser entity-resolution scaling *(prioritized by the 66.1 baseline)*

**Goal:** The baseline shows parse cost is **linear in visible-entity count**, not a cache-miss problem. Fix the resolution itself before considering memoization.

| # | Task | Status |
|---|------|--------|
| 67.1 | Eliminate the per-item DB round-trips in `GameContext.get_inventory()` (batch-load item rows in one query instead of `item_repo.get()` per stack) | [ ] |
| 67.2 | Index visible entities/inventory by normalized name+alias once per parse (dict/trie) so noun resolution is ~O(1) per phrase instead of scanning every entity | [ ] |
| 67.3 | Re-run `perf_baseline.py`; record before/after in the sprint. Only add result memoization (LRU keyed on `(raw, player_id, entity_hash)`) if resolution is still material after 67.1–67.2 | [ ] |

## Sprint 68 — Scheduler batching, pool tuning & load test

**Goal:** Batch same-epoch jobs into one commit; tune the DB pool; add a repeatable multi-player load test.

| # | Task | Status |
|---|------|--------|
| 68.1 | Batch scheduler execution: accumulate mutations across all due jobs, apply + commit once (preserve atomicity; verify via simulation) | [ ] |
| 68.2 | Connection-pool tuning knobs (`pool_size`/`pool_recycle`) in `config.py`/`Settings` for many concurrent players; document in deployment notes | [ ] |
| 68.3 | Load test (`tests/simulation/test_load.py`): N `VirtualPlayer`s issuing commands concurrently; report p95/p99 command latency before vs. after | [ ] |

## Sprint 69 — Concurrency decision gate *(only if 66–68 telemetry shows a hard limit)*

**Goal:** Revisit multithreading/multiprocessing **with data**, not speculatively. Likely order if needed: async command loop → parser thread-pool → async scheduler → (last resort) region sharding. See the analysis notes captured with Sprint 66.

| # | Task | Status |
|---|------|--------|
| 69.1 | Decide + document, from real load-test telemetry, whether/what concurrency to add and its transaction-isolation plan (own session per worker, serialized commits, `GameRng` determinism preserved) | [ ] |

### Assessment — sequence the perf band ahead of Sprint 65 (2026-07-05)

Only two things remain, so the ordering question is just "perf band vs. Sprint 65 first." **Recommendation: perf first**, because:

- The baseline (66.1) already found a **concrete, evidence-backed** bottleneck — parser resolution is O(visible entities), ~17 ms at 100 items with p99 spiking toward the 50 ms "slow" line. It gets worse as inventories/rooms grow, and it slows *every* command that resolves a noun.
- The first fixes are **low-risk, semantics-preserving wins**: 67.1 (kill the N+1 DB round-trips in `get_inventory()`) and 67.2 (index entities per parse). They need no new infrastructure and are verifiable with the harness we already have.
- Sprint 65 is valuable but **lower urgency**: it adds test coverage to subsystems that are already complete and stable, so it can follow without risk.

**Suggested order:** 67.1 → 67.2 → re-measure (67.3) → 66.2/66.3 (in-app telemetry) → 68 (batching/pool/load test) → 65 (multiplayer test pass) → 69 (concurrency gate, only if the load test shows a wall).

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| ~~Bug/todo letterbox~~ | Implemented in Sprint 10.5 as the issues tracking system (see [`roadmap_completed.md`](roadmap_completed.md)) |
| Inventory encumbrance / wear slots | After equipment + combat |
| `lorecraft.tools.simulation` CLI (JSON scenario files, N-bot load runs, latency/throughput reports) | Enhancement on top of the Sprint 12.1 pytest-based harness; see `tooling_infrastructure.md` §5. Overlaps Sprint 68.3's load test. |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| Player-facing bug reports | In-game `/report-bug` command (after core issues system stable) |
| Analytics dashboard & visualizations | After the Sprint 13 observability instrumentation; overlaps Sprint 66.3 |
| Database inspector / state editor | Admin tool for advanced troubleshooting |
| Combat & PvP | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Combat, reframed* (ready-to-restore specs) |

---

## Sprint numbering (avoid duplicates)

- **Used:** 1–34 (incl. 10.5), 65, 66–69.
- **Reserved but never used:** 35–60 (left as a gap during an earlier combat renumber).
- **Retired to [`wishlist.md`](wishlist.md):** 61–64 (combat core, combat commands/UI, combat testing, PvP consent). Don't reuse these four numbers for unrelated work — if combat/PvP returns, restore them under fresh numbers.
- **Next new sprint: 70.** Don't recycle a number that appears here or in [`roadmap_completed.md`](roadmap_completed.md).

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
