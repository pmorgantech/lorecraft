# Observability Guide

**Audience:** admins/operators diagnosing a slow command, a bad interaction, or "what actually
happened" during an incident. Player-facing UI (Analytics tab) is covered here too, but the
console/log-level detail is the main subject.

Three things exist today: **structured logging** with correlation IDs, **command latency
instrumentation**, and the **Analytics tab/endpoints** that surface it. Two more —
**request tracing** and **crash reports** — are scoped as roadmap
[Sprint 57](roadmap.md#sprint-57--request-tracing--crash-reports) and not built yet; this doc
will grow a section for them when they ship.

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

**When to reach for Analytics vs. raw logs:** Analytics answers "is the system slow, and where" —
aggregate trends, percentiles, which commands/NPCs get used. Raw structured logs answer "what
exactly happened for this one command" — you still need a `transaction_id` and a log grep for
incident-level detail. Sprint 57's per-command trace view (below) is meant to close that gap
without needing raw log access at all.

## The audit log (related, not the same thing)

The audit log (`GET /admin/audit`, the Audit tab, `LORECRAFT_AUDIT_DB_PATH`) is a separate
concern: it's the canonical, replayable record of **what game-state-changing actions happened**
(who did what, to what, when), not a debugging/performance tool. Use it to answer "did this
happen and who did it," not "why was it slow" or "why did it crash." See
[`admin_builder_guide.md`](admin_builder_guide.md#troubleshooting).

---

## Coming in Sprint 57: request tracing & crash reports

Not built yet — scoped in [`roadmap.md`](roadmap.md#sprint-57--request-tracing--crash-reports).
Two gaps this closes:

- **No structured "what ran" view for one command.** Today, reconstructing what a single command
  did (which conditions were checked, which events fired, which DB commits happened) means
  manually grepping every log line for one `transaction_id` and mentally reassembling the
  sequence. Sprint 57 adds a `GET /admin/trace/<transaction_id>` endpoint returning that sequence
  as structured spans directly — the ordered list `time_operation` already produces, just
  collected and exposed instead of only logged.
- **Nothing is captured when a command crashes.** An unhandled exception today produces whatever
  hits stdout and, worst case, a raw disconnect — there's no saved, browsable record. Sprint 57
  adds a `CrashReport` row (transaction id, correlation id, player, command text, stack trace,
  timestamp) persisted to the audit DB on any unhandled exception, plus `GET /admin/crashes` /
  `GET /admin/crashes/<id>` endpoints and a Crash Reports tab in the admin console — so a crash
  is a lookup, not a log-archaeology exercise.

This section will be filled in with actual usage instructions once Sprint 57 ships.

---

## Related docs

| Doc | Covers |
|-----|--------|
| [admin_builder_guide.md](admin_builder_guide.md#analytics) | Analytics tab/widgets, dashboard endpoints |
| [admin_builder_guide.md](admin_builder_guide.md#troubleshooting) | Audit trail, common startup/config issues |
| [roadmap.md](roadmap.md#sprint-57--request-tracing--crash-reports) | Sprint 57 task breakdown |
| [wishlist.md](wishlist.md) | "Operations, security & deployment" — the broader ops idea backlog this was drawn from |
