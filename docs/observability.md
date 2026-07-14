# Observability Guide

**Audience:** admins/operators diagnosing a slow command, a bad interaction, or "what actually
happened" during an incident. Player-facing UI (Analytics tab) is covered here too, but the
console/log-level detail is the main subject.

Six things exist today: **structured logging** with correlation IDs, **command latency
instrumentation**, the **Analytics tab/endpoints** that surface it, **per-command request
tracing**, **crash reports**, and **SQL query-span logging** for database tuning.

---

## Structured logging

Every player command passes through exactly one of two entry points — `main.py`'s `/ws` loop or
`web/frontend.py`'s `POST /command` — and each wraps its work in
`observability.bind_transaction_context(transaction_id, correlation_id)`. That publishes both IDs
to a `contextvars.ContextVar` for the duration of the command, so **every** `log.*` call made
anywhere in the resulting call stack — services, event handlers, repos, rule checks — picks them
up automatically. No function signature needs to thread an id through by hand.

Log lines look like:

```
2026-07-08 14:02:11,331 INFO lorecraft.engine.game.engine [txn=a1b2c3 corr=d4e5f6] command dispatched verb=go
```

- **`transaction_id`** — unique per command. Grep for it to see everything one command touched,
  across every module that logged during its execution.
- **`correlation_id`** — shared across the commands in one player session (or one logical
  operation), letting you follow a player's sequence of actions rather than a single command.
- Outside a bound command (startup, background scheduler ticks not yet wrapped), both fields log
  as `-`.

**Configuring it:**

- Log level: `LORECRAFT_LOG_LEVEL` env var (`Settings.log_level`, default `INFO`).
- Setup is idempotent — `configure_logging()` is safe to call multiple times (tests, reloads)
  without duplicating handlers.
- Implementation: `src/lorecraft/observability.py` (`configure_logging`,
  `bind_transaction_context`, `_TransactionLogFilter`).

**Using it:** given a bug report or a player complaint with a rough timestamp, grep the server
log for the surrounding lines, pull the `txn=` id from the command in question, then grep that id
again to see every log line — including ones from services/repos several calls deep — that
command produced.

## Command & operation latency

`time_operation(name, warn_ms=50.0)` (also in `observability.py`) times a named block, logs it at
DEBUG normally and escalates to WARNING if it exceeds the slow-operation budget (50 ms, the
threshold from `scripts/perf_baseline.py`'s measured baseline). It never suppresses an exception —
the timing is logged even when the block raises.

Two consumers matter operationally:

- **`CommandEngine._execute_parsed`** times each command handler and stamps `duration_ms` onto
  the `COMMAND_EXECUTED` audit event payload — this is what backs the Analytics tab's latency
  widgets (below).
- **`EventBus.emit()`** times each handler dispatch and logs
  `event=... handler=... duration_ms=... depth=<handlers registered>` at DEBUG.

`scheduler_tick` and `broadcast_send` are also timed this way but sit outside the per-command
audit path — they only ever show up in the structured logs (as a WARNING if slow), not in the
Analytics endpoints.

**Using it:** if a WARNING-level `perf_operation` line shows up, the `name=` field tells you which
named operation was slow and `duration_ms=` by how much. Cross-reference the `txn=`/`corr=` on the
same line against the surrounding log lines to see what else that command was doing.

## SQL query-span logging

Every game and audit SQLAlchemy engine created through `db.create_game_engine()` /
`db.create_audit_engine()` attaches cursor-level timing hooks. Each executed statement appends one
JSON object to `logs/sql_queries.log` by default. The log is outside both SQLite databases so
observability does not add more DB writes to the workload being measured.

Each record includes:

| Field | What |
|-------|------|
| `engine_role` | `game` or `audit` |
| `duration_ms` / `slow` / `slow_threshold_ms` | Cursor execution timing and whether it crossed the configured threshold |
| `statement_type` / `statement_hash` / `statement` | Normalized SQL fingerprint and statement text |
| `rowcount` / `executemany` / `parameter_count` | Result/write shape without logging parameter values |

Parameter values are deliberately not logged; the statement SQL may still contain table/column
names, so treat the file as operational telemetry, not player-facing data.

**Configuration:**

- `LORECRAFT_DB_QUERY_LOG_ENABLED` — default `true`; set `false` to disable the hook.
- `LORECRAFT_DB_QUERY_LOG_PATH` — default `logs/sql_queries.log`.
- `LORECRAFT_DB_QUERY_SLOW_MS` — default `50.0`.

**Analyzer:**

```bash
python scripts/analyze_query_log.py --log logs/sql_queries.log --database game.db
```

The report lists the slowest individual statements, most frequent statement fingerprints, and
candidate table/column indexes inferred from `WHERE` / `JOIN` / `ORDER BY` usage. Passing
`--database` lets the tool mark candidates that are already covered by a primary key or SQLite
index. Use this report as evidence before adding or changing schema; do not add indexes purely
from intuition when the query log can show the real workload.

## Analytics tab & endpoints

The admin console's **Analytics tab** (Sprint 49, expanded Sprint 51) is the aggregate,
browsable view of the same underlying data — no log-grepping required for the common case.

```
GET /admin/analytics/dashboard      — combined: latency_by_operation + timeline + heatmap +
                                      top_commands + npc_interactions + quest_funnel
GET /admin/analytics/latency        — command-handler p50/p95/p99 (ms)
GET /admin/analytics/performance    — p50/p95/p99 by operation (command_parse,
                                      condition_evaluate, db_commit, command_handler)
GET /admin/analytics/commands       — most-used commands
GET /admin/analytics/npcs           — NPC interaction counts
GET /admin/analytics/quest-funnel   — per-quest started/completed/failed/in-progress
GET /admin/analytics/player-hours   — playtime from PlayerSession records
```

All accept a `range` query param (`24h`, `7d`, `2w`, `30m`; default varies per endpoint). Full
detail, including the `/quests` vs. `/quest-funnel` gotcha and how to remove a widget, is in
[`admin_builder_guide.md`](admin_builder_guide.md#analytics) — this doc covers the
logging/tracing side; that one covers the dashboard/widget side.

**When to reach for Analytics vs. raw logs vs. tracing:** Analytics answers "is the system slow,
and where" — aggregate trends, percentiles, which commands/NPCs get used. Raw structured logs
answer "what exactly happened, in full detail" via `transaction_id` grep — the most complete view,
but manual. The **request trace** below (Sprint 57.1/57.2) answers the middle case — "what ran,
in order, for this one command" — as a structured JSON list, no log access needed.

## The audit log (related, not the same thing)

The audit log (`GET /admin/audit`, the Audit tab, `LORECRAFT_AUDIT_DB_PATH`) is a separate
concern: it's the canonical, replayable record of **what game-state-changing actions happened**
(who did what, to what, when), not a debugging/performance tool. Use it to answer "did this
happen and who did it," not "why was it slow" or "why did it crash." See
[`admin_builder_guide.md`](admin_builder_guide.md#troubleshooting).

---

## Request tracing (Sprint 57.1/57.2)

A structured, ordered list of what one command actually did — condition checks, DB commits, and
the event handlers it triggered — without grepping logs by hand.

**How it's captured:** `time_operation()` (used for `command_parse`, `condition_evaluate`,
`db_commit`, and the command-handler dispatch itself) automatically records a `TraceSpan` for
whatever transaction is currently bound via `bind_transaction_context()`. `EventBus.emit()` does
the same manually for each event handler it dispatches, named `event:<event_type>:<handler_name>`
so a trace shows exactly which handlers a command's events triggered, not just the top-level
timings. Everything lands in one in-memory ring buffer (`observability._trace_buffer`, last 200
commands server-wide — **not persisted**, so it only covers recent activity and is empty after a
restart).

**Using it:**

```
GET /admin/trace/<transaction_id>
```

Returns `[{"name": "command_parse", "duration_ms": 0.42, "started_at": 1720450931.2}, ...]` in
execution order — no query params. 404 if the id was never bound, or has aged out of the ring
buffer. Get a `transaction_id` from a structured log line (`txn=...`) or from a `COMMAND_EXECUTED`
audit event's `transaction_id` field, then paste it in.

**Why in-memory, not persisted:** matches the deliberate "measure, don't over-build" stance
already applied to the deferred concurrency work — a bounded ring buffer covers the actual use
case (someone just hit a slow/weird command and wants to know why, right now) without adding a
new table, a retention policy, or write volume to the audit DB for data that's rarely looked at
after the fact. Revisit if that assumption turns out wrong in practice.

## Crash reports (Sprint 57.3/57.4)

Before Sprint 57, an unhandled exception anywhere in the command pipeline (outside a command
handler itself, which was already caught and reported gracefully) produced a raw disconnect on
the `/ws` path or a bare 500 on `POST /command`, with nothing captured beyond whatever hit stdout.
Both entry points now catch it, persist a `CrashReport` row, and return a friendly in-game error
(`{"type": "error", "message": "... logged for review."}` over WS; an inline error `<div>` over
HTMX) instead.

**What's captured**, per `CrashReport` row (audit DB, `engine/models/audit.py`):

| Field | What |
|-------|------|
| `transaction_id` / `correlation_id` | Same ids as the structured logs — cross-reference a crash against its log lines or trace. |
| `player_id` | Who ran the command. |
| `command_text` | The raw command text that triggered it. |
| `stack_trace` | Full Python traceback (`traceback.format_exception`). |
| `real_time` | When it happened. |

This is deliberately separate from `AuditEvent`'s `COMMAND_FAILED`/`command_blocked` rows: those
are *expected* failures a handler reports on purpose (bad input, a blocked action); a
`CrashReport` is the pipeline itself blowing up — a bug, not a game-rule outcome.

**Using it — the Crash Reports admin tab** (or directly):

```
GET /admin/crashes             — list, newest first (id, player, command, timestamp — no stack trace)
GET /admin/crashes/<id>        — full detail including stack_trace
```

Click a row in the tab to load its full trace on the right. There's no severity filter or search
yet (traffic has been low enough not to need it) — if crash volume grows, that's the natural next
addition, alongside a retention/cleanup policy (there isn't one yet; rows accumulate in the audit
DB indefinitely).

**Rollback safety:** before writing a `CrashReport`, the handler rolls back both the game session
(any partial, uncommitted state from the failed command) and the audit session (any half-written
audit rows from earlier in that same command) — so a crash report never accidentally commits
unrelated pending writes alongside itself. See `engine/services/crash_reports.py`.

---

## Related docs

| Doc | Covers |
|-----|--------|
| [admin_builder_guide.md](admin_builder_guide.md#analytics) | Analytics tab/widgets, dashboard endpoints |
| [admin_builder_guide.md](admin_builder_guide.md#troubleshooting) | Audit trail, common startup/config issues |
| [roadmap.md](roadmap.md#sprint-57--request-tracing--crash-reports) | Sprint 57 task breakdown |
| [wishlist.md](wishlist.md) | "Operations, security & deployment" — the broader ops idea backlog this was drawn from |
