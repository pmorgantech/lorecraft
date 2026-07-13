"""Unit tests for the canonical event-trail hashing tool (Rust-port Phase 0).

Covers the three guarantees `replay_hash` exists to provide:
- determinism: identical trails hash to the same digest;
- sensitivity: any change to a normalised field (or order) changes the digest;
- the float-rejection policy on `canonical_json`.
"""

from __future__ import annotations

import pytest

from lorecraft.engine.models.audit import AuditEvent
from lorecraft.tools.replay_hash import canonical_json, hash_events


def _event(
    *,
    event_type: str = "command_executed",
    summary: str = "Command executed: look",
    target_id: str | None = None,
    room_id: str = "village_square",
    severity: str = "INFO",
) -> AuditEvent:
    """Build an in-memory AuditEvent (only the normalised fields vary)."""
    return AuditEvent(
        transaction_id="txn",
        correlation_id="corr",
        actor_id="player-1",
        event_type=event_type,
        source_type="command",
        target_id=target_id,
        room_id=room_id,
        game_time=0.0,
        real_time=0.0,
        severity=severity,
        summary=summary,
    )


def test_same_trail_hashes_identically() -> None:
    trail_a = [_event(summary="look"), _event(summary="go east", room_id="market")]
    trail_b = [_event(summary="look"), _event(summary="go east", room_id="market")]

    assert hash_events(trail_a) == hash_events(trail_b)


def test_run_specific_fields_do_not_affect_the_hash() -> None:
    """Only the normalised projection matters — ids/timestamps are stripped."""
    baseline = [_event()]
    noisy = [_event()]
    # Mutate fields normalize_events deliberately excludes.
    noisy[0].transaction_id = "different"
    noisy[0].real_time = 999.0
    noisy[0].game_time = 42.0

    assert hash_events(baseline) == hash_events(noisy)


def test_changed_event_changes_the_hash() -> None:
    baseline = [_event(summary="look")]
    changed = [_event(summary="go east")]

    assert hash_events(baseline) != hash_events(changed)


def test_reordered_trail_changes_the_hash() -> None:
    forward = [_event(summary="look"), _event(summary="go east")]
    reversed_ = [_event(summary="go east"), _event(summary="look")]

    assert hash_events(forward) != hash_events(reversed_)


def test_canonical_json_is_sorted_and_compact() -> None:
    assert canonical_json({"b": 1, "a": None}) == b'{"a":null,"b":1}'


def test_canonical_json_preserves_non_ascii_as_utf8() -> None:
    # ensure_ascii=False keeps the raw UTF-8 bytes rather than \uXXXX escapes.
    assert canonical_json({"name": "café"}) == '{"name":"café"}'.encode()


def test_canonical_json_rejects_top_level_float() -> None:
    with pytest.raises(TypeError):
        canonical_json(1.5)


def test_canonical_json_rejects_nested_float() -> None:
    with pytest.raises(TypeError):
        canonical_json({"stats": {"hp": 3, "ratio": 0.5}})


def test_canonical_json_rejects_float_in_list() -> None:
    with pytest.raises(TypeError):
        canonical_json([1, 2, 3.0])


def test_canonical_json_allows_bools_and_ints() -> None:
    # bool is an int subclass, not a float — must not be rejected.
    assert canonical_json({"flag": True, "count": 0}) == b'{"count":0,"flag":true}'
