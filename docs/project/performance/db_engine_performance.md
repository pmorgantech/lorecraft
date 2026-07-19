# Database and Engine Performance

This file tracks durable performance observations that should stay linked to
release history. Raw `.log` files are intentionally not committed; keep large
query-span logs under `logs/` or `/tmp` and summarize the findings here.

The append-only load-test history lives in
[`load_test_history.jsonl`](load_test_history.jsonl). Each JSONL row records the
package version, changelog heading, git branch/commit/dirty flag, runtime,
scenario, and timing percentiles.

## Current Baseline

### v0.104.1 - 2026-07-14

Broad world/hunt simulation after the post-feature update:

- Command: `make load-test-history PYTHON=.venv/bin/python`
- Scenario: `tests/simulation/scenarios/load_world_hunt.json`
- Players: 50
- Commands per player: 147
- Total commands: 7,350
- Jitter: 0 ms, lockstep worst case
- Open hunt: `harvest_trinkets`
- SQL query-span logging: disabled for baseline timing
- p50: 920.611 ms
- p95: 1410.923 ms
- p99: 1692.804 ms
- max: 1822.741 ms
- Gate: passed under the 3000 ms exploratory p99 ceiling

Interpretation: the current single-process event-loop server handles the broad
50-player lockstep scenario below the exploratory p99 ceiling when query-span
logging is off. This remains a stress profile, not a normal user think-time
profile.

## DB Observations

### Query-Span Logging Overhead

A 50-player run with all SQL query spans logged completed the same 7,350
commands, but failed the default 2000 ms p99 gate:

- p50: 1378.154 ms
- p95: 2182.970 ms
- p99: 2369.927 ms
- max: 2694.636 ms

The generated SQL JSONL log was hundreds of MB. That result is useful as a
logging-overhead measurement, but it should not be mixed with engine baselines.
Use query logging for targeted DB diagnosis, not for the periodic load history.

### 2-Player Query-Log Smoke

The 2-player version of the broad scenario passed:

- Total commands: 294
- p50: 33.347 ms
- p95: 67.109 ms
- p99: 98.038 ms
- max: 168.131 ms
- Query spans: 22,506 statements
- Query total time: 332.968 ms
- Query average: 0.015 ms
- Query max: 6.395 ms, during test DB table creation

Most frequent fingerprints were room, exit, item, player, and item-stack reads.
Individual queries were fast; the higher 50-player latency is primarily event
loop queueing plus optional query-log write volume, not one slow statement.

## Live Server Snapshot

Before this baseline, the running main-worktree server reported:

- Command latency: p50 0.842 ms, p95 4.227 ms, p99 17.366 ms, count 153
- `command_handler`: p50 0.842 ms, p95 4.227 ms, p99 17.366 ms
- `command_parse`: p50 1.197 ms, p95 2.724 ms, p99 3.416 ms
- `condition_evaluate`: p50 0.015 ms, p95 0.019 ms, p99 0.028 ms
- `db_commit`: p50 0.142 ms, p95 0.280 ms, p99 0.712 ms

Interpretation: ordinary live traffic was far below the simulation stress
profile. Use the 50-player lockstep scenario as a regression detector and the
admin analytics endpoint for live-user shape.

## Updating This File

For normal post-feature performance tracking:

```bash
make load-test-history PYTHON=.venv/bin/python
```

Then copy the new JSONL row's headline values into the Current Baseline section
or add a new dated/versioned subsection if behavior changed materially.

For DB diagnosis, run query-span logging with an explicit temporary path:

```bash
LORECRAFT_DB_QUERY_LOG_ENABLED=true \
LORECRAFT_DB_QUERY_LOG_PATH=/tmp/lorecraft-query-spans.jsonl \
make load-test-history PYTHON=.venv/bin/python
```

Analyze the temporary log, summarize the findings here, and leave the raw
`.log` / `.jsonl` artifact untracked unless it is intentionally small and
reviewable.
