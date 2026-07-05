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


@dataclass
class OperationTiming:
    """Handle yielded by ``time_operation``.

    ``duration_ms`` is 0.0 while the block runs and is filled in when it exits,
    so a caller that needs the measurement — e.g. to stamp it onto an audit
    payload for the Sprint 35.3 ``/admin/analytics/performance`` query — can read
    it after the ``with`` block. Callers that only want the log line can ignore
    the yielded value entirely.
    """

    name: str
    duration_ms: float = 0.0


@contextmanager
def time_operation(
    name: str, *, warn_ms: float = _SLOW_OPERATION_MS
) -> Iterator[OperationTiming]:
    """Time a named operation and emit one structured perf log line.

    Logs at DEBUG normally, escalating to WARNING when the block takes longer
    than ``warn_ms`` (default 50 ms). Whatever transaction/correlation IDs are
    bound by ``bind_transaction_context`` are attached automatically by the
    root log filter, so each timing is traceable to the command that produced
    it. Instrumentation only: it never suppresses an exception, and the elapsed
    time is still logged when the block raises.

    Yields an :class:`OperationTiming` whose ``duration_ms`` is populated on
    exit; ``with time_operation(name) as t: ...`` then reads ``t.duration_ms``.
    """
    timing = OperationTiming(name)
    start = time.perf_counter()
    try:
        yield timing
    finally:
        timing.duration_ms = (time.perf_counter() - start) * 1000.0
        if timing.duration_ms > warn_ms:
            log.warning(
                "perf_operation name=%s duration_ms=%.3f slow_threshold_ms=%.0f",
                name,
                timing.duration_ms,
                warn_ms,
            )
        else:
            log.debug(
                "perf_operation name=%s duration_ms=%.3f", name, timing.duration_ms
            )
