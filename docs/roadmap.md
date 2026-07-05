# Lorecraft — Roadmap

**A concise list of *remaining* work.** Completed sprints (1–34: foundation hardening, the Tier 1
engine-core primitives, the whole Tier 2 pillar feature band, and the tier-split follow-ons) have
been moved to [`roadmap_completed.md`](roadmap_completed.md) to keep this readable. Per-version
detail is in [`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and
the deferred multiplayer test pass are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-05, v0.36.5)

Foundation, the Tier 1 engine-core primitives, the entire pillar-driven Tier 2 feature band
(exploration · trading · questing · puzzles, plus inventory/equipment, traits/skills, character
condition, and transit), and the Tier 1 / Tier 2 / web **tier-split** refactor are all **complete**
(`src/lorecraft/engine/` is import-pure; features live under `features/`; hosts under
`webui/{player,admin}/`). Player onboarding/account UX shipped except the intro walkthrough, which
moved to the wishlist.

**Set aside to [`wishlist.md`](wishlist.md):** combat & PvP (ready-to-restore specs — a supporting
system, not the centerpiece), and the multiplayer trade/transit **test pass** (coverage-hardening
of already-complete subsystems).

**What's actually left** is one thing: a measure-first **performance & scaling band**
(Sprints 35–38). That's the whole active roadmap below.

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
| 35.2 | Structured perf logging in `observability.py`: `time_operation(name)` ctx-manager; instrument `command_parse`, `condition_evaluate`, `db_commit`, `scheduler_tick`, `broadcast_send` (warn >50 ms) | [ ] |
| 35.3 | Analytics API `/admin/analytics/performance` — p50/p95/p99 by operation from audit `duration_ms` payloads (extends existing latency query) | [ ] |

## Sprint 36 — Parser entity-resolution scaling *(prioritized by the 35.1 baseline)*

**Goal:** The baseline shows parse cost is **linear in visible-entity count**, not a cache-miss problem. Fix the resolution itself before considering memoization.

| # | Task | Status |
|---|------|--------|
| 36.1 | Eliminate the per-item DB round-trips in `GameContext.get_inventory()` (batch-load item rows in one query instead of `item_repo.get()` per stack) | [ ] |
| 36.2 | Index visible entities/inventory by normalized name+alias once per parse (dict/trie) so noun resolution is ~O(1) per phrase instead of scanning every entity | [ ] |
| 36.3 | Re-run `perf_baseline.py`; record before/after in the sprint. Only add result memoization (LRU keyed on `(raw, player_id, entity_hash)`) if resolution is still material after 36.1–36.2 | [ ] |

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

The band's baseline (35.1) is already done and it surfaced a **concrete, evidence-backed** bottleneck: parser resolution is O(visible entities) — ~17 ms at 100 inventory items, p99 spiking toward the 50 ms "slow" line, and it slows *every* noun-resolving command. So the highest-value next move is **Sprint 36.1** (kill the N+1 DB round-trips in `get_inventory()`) then **36.2** (index entities per parse) — both low-risk, semantics-preserving, and verifiable with the harness we already have. In-app telemetry (35.2/35.3) can follow; the baseline harness already gives us the before/after data for the parser fix.

**Suggested order:** 36.1 → 36.2 → re-measure (36.3) → 35.2/35.3 (in-app telemetry) → 37 (batching/pool/load test) → 38 (concurrency gate, only if the load test shows a wall).

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

- **Used:** 1–34 (incl. 10.5) and 35–38 (this performance band).
- **Reserved but never used:** 39–60 (left as a gap from an earlier combat renumber).
- **Retired to [`wishlist.md`](wishlist.md):** 61–64 (combat core, combat commands/UI, combat testing, PvP consent), and 65 (multiplayer trade/transit tests). Don't reuse these numbers for unrelated work — if that work returns, restore it under fresh numbers.
- **Next new sprint: 39.** Don't recycle a number that appears here or in [`roadmap_completed.md`](roadmap_completed.md).

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
