# Performance History

`load_test_history.jsonl` is an append-only record of periodic simulation load
tests. Each line is one JSON object containing the timing report plus the
package version, changelog heading, git branch/commit, dirty flag, scenario,
and runtime details.

Use [`db_engine_performance.md`](db_engine_performance.md) for the human-readable
performance ledger and interpretation of DB or engine findings.

Run the broad 50-player hunt scenario and append a record:

```bash
make load-test-history PYTHON=.venv/bin/python
```

Useful overrides:

```bash
make load-test-history \
  PYTHON=.venv/bin/python \
  LOAD_TEST_PLAYERS=75 \
  LOAD_TEST_LATENCY_CEILING_MS=5000 \
  LOAD_TEST_HISTORY=docs/performance/load_test_history.jsonl
```

The target disables SQL query-span logging by default so the history measures
command-processing latency rather than JSONL write volume. If you are measuring
query logging overhead intentionally, run the pytest command directly with
`LORECRAFT_DB_QUERY_LOG_ENABLED=true` and an explicit
`LORECRAFT_DB_QUERY_LOG_PATH` under `/tmp`.
