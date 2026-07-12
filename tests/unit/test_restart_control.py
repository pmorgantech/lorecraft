"""Unit tests for the restart-request / heartbeat handshake (Sprint 72.3)."""

from __future__ import annotations

from pathlib import Path

from lorecraft.ops.restart_control import RestartControl


def test_request_then_take_round_trips_metadata(tmp_path: Path) -> None:
    control = RestartControl(tmp_path)
    control.request_restart(requested_by="alice", reason="deploy")

    taken = control.take_request()
    assert taken is not None
    assert taken.requested_by == "alice"
    assert taken.reason == "deploy"


def test_take_request_consumes_the_sentinel(tmp_path: Path) -> None:
    control = RestartControl(tmp_path)
    control.request_restart(requested_by="bob")

    assert control.take_request() is not None
    # A single request must not re-trigger on the next poll (no spin loop).
    assert control.take_request() is None


def test_take_request_none_when_no_request(tmp_path: Path) -> None:
    assert RestartControl(tmp_path).take_request() is None


def test_not_armed_without_heartbeat(tmp_path: Path) -> None:
    status = RestartControl(tmp_path).read_status()
    assert status.armed is False
    assert status.pid is None


def test_fresh_heartbeat_is_armed(tmp_path: Path) -> None:
    now = 1000.0
    control = RestartControl(tmp_path, clock=lambda: now)
    control.write_heartbeat(pid=4321, started_at=990.0)

    status = control.read_status()
    assert status.armed is True
    assert status.pid == 4321
    assert status.started_at == 990.0
    assert status.heartbeat_age == 0.0


def test_stale_heartbeat_is_not_armed(tmp_path: Path) -> None:
    times = iter([100.0, 200.0])  # write@100, then read@200

    def clock() -> float:
        return next(times)

    control = RestartControl(tmp_path, heartbeat_stale_seconds=10.0, clock=clock)
    control.write_heartbeat(pid=1, started_at=1.0)
    status = control.read_status()
    assert status.armed is False
    assert status.heartbeat_age == 100.0


def test_malformed_heartbeat_is_not_armed(tmp_path: Path) -> None:
    control = RestartControl(tmp_path)
    control.ensure_dir()
    control.heartbeat_path.write_text("not json", encoding="utf-8")
    assert control.read_status().armed is False


def test_malformed_request_still_triggers_and_is_removed(tmp_path: Path) -> None:
    # Existence is the trigger; contents are best-effort audit metadata.
    control = RestartControl(tmp_path)
    control.ensure_dir()
    control.request_path.write_text("{ broken", encoding="utf-8")

    taken = control.take_request()
    assert taken is not None
    assert taken.requested_by == "unknown"
    assert not control.request_path.exists()


def test_clear_removes_heartbeat_and_request(tmp_path: Path) -> None:
    control = RestartControl(tmp_path)
    control.write_heartbeat(pid=1, started_at=1.0)
    control.request_restart(requested_by="alice")

    control.clear()
    assert not control.heartbeat_path.exists()
    assert not control.request_path.exists()
    assert control.read_status().armed is False
