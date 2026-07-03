"""Tests for structured logging correlation/transaction ID threading."""

from __future__ import annotations

import logging

from lorecraft.observability import (
    _TransactionLogFilter,
    bind_transaction_context,
    configure_logging,
)


def _make_record() -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )


def test_filter_defaults_to_dash_outside_bound_context() -> None:
    record = _make_record()
    assert _TransactionLogFilter().filter(record) is True
    assert record.transaction_id == "-"  # type: ignore[attr-defined]
    assert record.correlation_id == "-"  # type: ignore[attr-defined]


def test_filter_picks_up_bound_context() -> None:
    with bind_transaction_context("txn-1", "corr-1"):
        record = _make_record()
        _TransactionLogFilter().filter(record)
        assert record.transaction_id == "txn-1"  # type: ignore[attr-defined]
        assert record.correlation_id == "corr-1"  # type: ignore[attr-defined]


def test_context_resets_after_block() -> None:
    with bind_transaction_context("txn-2", "corr-2"):
        pass
    record = _make_record()
    _TransactionLogFilter().filter(record)
    assert record.transaction_id == "-"  # type: ignore[attr-defined]


def test_nested_contexts_restore_outer_value_on_exit() -> None:
    with bind_transaction_context("outer", "outer-corr"):
        with bind_transaction_context("inner", "inner-corr"):
            record = _make_record()
            _TransactionLogFilter().filter(record)
            assert record.transaction_id == "inner"  # type: ignore[attr-defined]

        record = _make_record()
        _TransactionLogFilter().filter(record)
        assert record.transaction_id == "outer"  # type: ignore[attr-defined]


def test_configure_logging_is_idempotent() -> None:
    configure_logging("INFO")
    configure_logging("INFO")

    root = logging.getLogger()
    matching = [
        handler
        for handler in root.handlers
        if any(isinstance(f, _TransactionLogFilter) for f in handler.filters)
    ]
    assert len(matching) == 1
