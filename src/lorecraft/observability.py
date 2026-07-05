"""Structured logging: correlation/transaction IDs threaded via contextvars.

Every player command passes through exactly one of two entry points
(`main.py`'s `/ws` command loop, `web/frontend.py`'s `POST /command`), each of
which creates one `TransactionContext` per command. `bind_transaction_context()`
publishes that context's IDs to a contextvar for the duration of the call, so
any `log.*` call made anywhere in the resulting call stack — services, event
handlers, repos — picks them up automatically via `_TransactionLogFilter`,
without threading `transaction_id`/`correlation_id` through every function
signature.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

log = logging.getLogger(__name__)

_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "[txn=%(transaction_id)s corr=%(correlation_id)s] %(message)s"
)

# The "slow" line from the perf baseline (scripts/perf_baseline.py): operations
# over this budget are logged at WARNING so they surface without a debug filter.
_SLOW_OPERATION_MS = 50.0


@dataclass(frozen=True)
class _LogContext:
    transaction_id: str
    correlation_id: str


_current: ContextVar[_LogContext | None] = ContextVar(
    "lorecraft_log_context", default=None
)


class _TransactionLogFilter(logging.Filter):
    """Injects transaction_id/correlation_id (or "-" outside a bound command)."""

    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _current.get()
        record.transaction_id = ctx.transaction_id if ctx else "-"  # type: ignore[attr-defined]
        record.correlation_id = ctx.correlation_id if ctx else "-"  # type: ignore[attr-defined]
        return True


def configure_logging(level: str = "INFO") -> None:
    """Attach a correlation-aware formatter to the root logger. Idempotent."""
    root = logging.getLogger()
    already_configured = any(
        isinstance(f, _TransactionLogFilter)
        for handler in root.handlers
        for f in handler.filters
    )
    if already_configured:
        root.setLevel(level)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    handler.addFilter(_TransactionLogFilter())
    root.addHandler(handler)
    root.setLevel(level)


@contextmanager
def bind_transaction_context(
    transaction_id: str, correlation_id: str
) -> Iterator[None]:
    """Bind IDs to the current context for the duration of one command."""
    token = _current.set(_LogContext(transaction_id, correlation_id))
    try:
        yield
    finally:
        _current.reset(token)


@contextmanager
def time_operation(name: str, *, warn_ms: float = _SLOW_OPERATION_MS) -> Iterator[None]:
    """Time a named operation and emit one structured perf log line.

    Logs at DEBUG normally, escalating to WARNING when the block takes longer
    than ``warn_ms`` (default 50 ms). Whatever transaction/correlation IDs are
    bound by ``bind_transaction_context`` are attached automatically by the
    root log filter, so each timing is traceable to the command that produced
    it. Instrumentation only: it never suppresses an exception, and the elapsed
    time is still logged when the block raises.

    The measured durations are what the Sprint 35.3 ``/admin/analytics/performance``
    query aggregates into per-operation p50/p95/p99; call sites stay stable as
    that persistence is layered in here.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        if duration_ms > warn_ms:
            log.warning(
                "perf_operation name=%s duration_ms=%.3f slow_threshold_ms=%.0f",
                name,
                duration_ms,
                warn_ms,
            )
        else:
            log.debug("perf_operation name=%s duration_ms=%.3f", name, duration_ms)
