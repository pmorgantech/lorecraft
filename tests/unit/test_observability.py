"""Tests for structured logging correlation/transaction ID threading."""

from __future__ import annotations

import logging
import time

import pytest

from lorecraft.observability import (
    _TRACE_BUFFER_MAX,
    _TransactionLogFilter,
    bind_transaction_context,
    configure_logging,
    get_trace,
    record_span,
    time_operation,
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


def _perf_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if "perf_operation" in r.getMessage()]


def test_time_operation_logs_debug_for_fast_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="lorecraft.observability"):
        with time_operation("fast_op", warn_ms=1000.0):
            pass
    records = _perf_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert "name=fast_op" in records[0].getMessage()


def test_time_operation_warns_when_over_threshold(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="lorecraft.observability"):
        with time_operation("slow_op", warn_ms=0.5):
            time.sleep(0.002)  # >0.5 ms, so the WARNING branch fires deterministically
    records = _perf_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "name=slow_op" in records[0].getMessage()


def test_time_operation_yields_measured_duration() -> None:
    with time_operation("measured", warn_ms=1000.0) as timing:
        time.sleep(0.002)
    assert timing.name == "measured"
    assert timing.duration_ms >= 2.0  # sleep guarantees at least the requested time


def test_time_operation_reraises_and_still_logs_on_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="lorecraft.observability"):
        with pytest.raises(ValueError):
            with time_operation("boom", warn_ms=1000.0):
                raise ValueError("boom")
    records = _perf_records(caplog)
    assert len(records) == 1
    assert "name=boom" in records[0].getMessage()


def test_record_span_is_noop_outside_bound_context() -> None:
    """Nothing to key the span to without a bound transaction — must not raise."""
    record_span("orphan", 1.0)


def test_record_span_and_get_trace_round_trip() -> None:
    with bind_transaction_context("txn-trace-1", "corr-trace-1"):
        record_span("step_a", 1.5)
        record_span("step_b", 2.5)
    spans = get_trace("txn-trace-1")
    assert spans is not None
    assert [s.name for s in spans] == ["step_a", "step_b"]
    assert spans[0].duration_ms == 1.5


def test_time_operation_records_a_span_automatically() -> None:
    with bind_transaction_context("txn-trace-2", "corr-trace-2"):
        with time_operation("op", warn_ms=1000.0):
            pass
    spans = get_trace("txn-trace-2")
    assert spans is not None
    assert spans[-1].name == "op"


def test_get_trace_returns_none_for_unknown_transaction() -> None:
    assert get_trace("never-seen-txn-id") is None


def test_trace_buffer_evicts_oldest_transaction_past_capacity() -> None:
    for i in range(_TRACE_BUFFER_MAX + 5):
        with bind_transaction_context(f"txn-evict-{i}", "corr"):
            record_span("op", 0.1)
    assert get_trace("txn-evict-0") is None
    assert get_trace(f"txn-evict-{_TRACE_BUFFER_MAX + 4}") is not None


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
