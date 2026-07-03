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
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

_LOG_FORMAT = (
    "%(asctime)s %(levelname)s %(name)s "
    "[txn=%(transaction_id)s corr=%(correlation_id)s] %(message)s"
)


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
