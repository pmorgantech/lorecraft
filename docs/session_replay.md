# Session record & playback — plan (Sprint 43)

**Goal:** record real (or scripted) player command streams and replay them — one scenario
across **N simulated players**, or a mix of scenarios concurrently — to drive *advanced testing*:
regression (golden audit-trail diff), load/throughput (p50/p95/p99), and soak/fuzz (surface
crashes & contention). A consolidation, not new infrastructure: almost every piece already exists.

Roadmap: [Sprint 43](roadmap.md). Supersedes the Backlog `lorecraft.tools.simulation` CLI note and
extends the Sprint 37.3 load test.

## Why this is mostly a consolidation

| Piece needed | Already have |
|---|---|
| The **recording** | The **audit log** — every command is a `COMMAND_EXECUTED` (or `_BLOCKED`/`_FAILED`) event with `actor_id`, `raw`, `roles`, `game_time`/`real_time`, and correlation IDs. "Audit log as source of truth — canonical, replayable history" (wishlist §Architectural patterns). |
| The **playback engine** | `tests/simulation/` — `VirtualPlayer` (real `/ws` client) + `SimulationServer` (a live `uvicorn` on a disposable world). |
| **N concurrent players + metrics** | `tests/simulation/test_load.py` (Sprint 37.3) — fans out N `VirtualPlayer`s, reports p50/p95/p99/max, jitter knob, JSON export. |
| **Deterministic golden diff** | Seeded `GameRng` + `tests/simulation/test_audit_regression.py` — the determinism contract and an audit-trail **normaliser** already exist. |

## Scenario file format (JSON)

```jsonc
{
  "version": 1,
  "description": "petem clears the Wandering Crow quest",
  "world_yaml": "world_content/world.yaml",   // which world this was recorded against
  "rng_seed": 1,                               // for deterministic replay/golden-diff
  "actors": ["player-1"],                      // logical actors (mapped to fresh VirtualPlayers)
  "commands": [
    {"t": 0.0,   "actor": "player-1", "raw": "look"},
    {"t": 1.4,   "actor": "player-1", "raw": "go east"},
    {"t": 3.9,   "actor": "player-1", "raw": "take coin"}
    // t = seconds from scenario start (real time); replay honours or collapses these
  ]
}
```

- **Actors are logical**, not real player ids — replay maps each to a freshly-created
  `VirtualPlayer`, so a one-player recording can be fanned out to N players, and multiple
  recordings can be interleaved by merging their command lists on `t`.

## Record

Two sources, one format:

1. **From the audit log** (`record` from a real session): query the audit DB for an actor /
   correlation id, project `COMMAND_EXECUTED`/`_BLOCKED`/`_FAILED` events → ordered `commands`
   (using `raw` and `real_time` deltas). This captures *real* play with zero new plumbing.
2. **Synthetic** — hand-authored or generated scenario JSON (the old `lorecraft.tools.simulation`
   idea: parametric N-bot scripts).

## Replay

A runner that boots a fresh disposable world (like the load test), creates the scenario's actors
as `VirtualPlayer`s, and feeds each its command stream. **Timing modes:**

- `realtime` — honour the recorded `t` deltas (soak / realistic latency).
- `jitter=<ms>` — spread arrivals (reuse the load-test knob).
- `fast` — as fast as the reply allows (throughput ceiling, regression).

**Fan-out modes (the "many simulated players" part):**

- `--players N --scenario s.json` — replay one scenario across **N** players (load; the current
  `test_load.py` is the degenerate fixed-script case).
- `--mix a.json b.json …` — replay distinct recorded sessions **concurrently** (realistic soak,
  contention surfacing — cf. the existing concurrent-`take` scenario test).

## Three payoffs from one tool

- **Regression** — replay + normalise + diff the resulting audit trail against a checked-in golden
  (extends `test_audit_regression.py`). *Determinism caveat:* single-actor is fully deterministic
  under a fixed `rng_seed`; **multi-actor concurrent interleaving is not** — so the golden diff
  either runs single-actor, or diffs a **per-actor-normalised** trail (sort by actor + logical
  order, drop wall-clock/ids) exactly as the existing normaliser already does.
- **Load / throughput** — reuse `test_load.py`'s percentile reporting, now driven by *real*
  recorded traffic instead of a fixed script.
- **Soak / fuzz** — replay large/varied/mixed scenarios to surface crashes and contention.

## CLI

`python -m lorecraft.tools.simulation` (or `scripts/session_replay.py`):

```
record  --audit-db <path> --actor <id> [--since <range>] -o scenario.json
replay  --scenario s.json [--players N | --mix a.json b.json] \
        [--timing realtime|jitter:<ms>|fast] [--assert-audit golden.json] [--json report.json]
```

`replay` reuses the `SimulationServer`/`VirtualPlayer` harness; `--json` emits the load-test
report shape so before/after diffs are scriptable.

## Phasing

1. **Phase 1 — record + single-actor replay + golden diff.** `record` from the audit log; `replay`
   one scenario through one `VirtualPlayer`; assert the normalised audit trail matches a golden.
   (Turns `test_audit_regression.py` from a hard-coded script into a data-driven one.)
   **✅ Shipped (43.1, v0.39.4):** scenario format + `record` CLI + `normalize_events()` in
   `lorecraft.tools.session_replay`; `replay_scenario()` in `tests/simulation/replay.py`
   (test-side because it drives the live-server harness); golden-path scenario + checked-in
   golden trail under `tests/simulation/scenarios/` (`LORECRAFT_UPDATE_GOLDENS=1` regenerates).
2. **Phase 2 — N-player fan-out + metrics.** `--players N`, reuse the load-test percentile report.
   Replaces the fixed `test_load.py` script with recorded traffic.
3. **Phase 3 — mixed scenarios + soak + CI.** `--mix`, longer runs, an opt-in CI job (marked
   `simulation`, kept out of the default suite).

## Non-goals (initially)

- Not a production traffic-capture-at-scale pipeline (record is dev/test-scoped, off the audit DB).
- Not a distributed load generator — single-box N-player is the target (matches the single-process
  server); revisit only alongside the deferred concurrency work (`wishlist.md`).
- No new engine mechanism — record reads the audit log, replay uses the existing WS harness.
