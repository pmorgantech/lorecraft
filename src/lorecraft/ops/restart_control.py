"""Filesystem handshake between the admin "request restart" endpoint and the supervisor.

Two independent processes need to agree on a restart with no shared memory:

* the **web host** (running *inside* the uvicorn child) writes a restart
  *request* and reads whether a performer is listening ("armed?"), and
* the **supervisor** (the parent process, ``scripts/supervisor.py``) publishes a
  liveness *heartbeat* and consumes restart requests.

The medium is a small control directory of JSON files. Existence of the request
file *is* the trigger (its contents are audit metadata only), so a torn/partial
write can never mean "half a restart". The heartbeat carries a timestamp the web
host compares against a freshness window to decide "armed" — a stale or missing
heartbeat means no supervisor is watching this instance, so the endpoint can
refuse rather than silently no-op.

Pure stdlib by design (see ``lorecraft.ops`` package docstring): the supervisor
imports this without pulling in the engine.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HEARTBEAT_FILENAME = "supervisor.json"
REQUEST_FILENAME = "restart.request"

# How long a heartbeat stays "fresh". The supervisor refreshes on every poll
# (default 1s), so 10s tolerates a few missed polls before an instance is
# reported unarmed — long enough to avoid flapping, short enough that a crashed
# supervisor is noticed within a UI refresh.
DEFAULT_HEARTBEAT_STALE_SECONDS = 10.0


@dataclass(frozen=True)
class SupervisorStatus:
    """Snapshot of whether a performer is listening, for the "armed?" indicator."""

    armed: bool
    pid: int | None = None
    started_at: float | None = None
    heartbeat_at: float | None = None
    heartbeat_age: float | None = None


@dataclass(frozen=True)
class RestartRequest:
    """A recorded request to restart, carried in the sentinel file for audit."""

    requested_by: str
    reason: str | None
    requested_at: float


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Write JSON atomically so a reader never observes a partial file."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


class RestartControl:
    """Coordinates the restart request/heartbeat files in a control directory.

    Both sides construct one against the same ``control_dir``. Writer methods
    (``request_restart``/``read_status``) are used by the web host; reader
    methods (``write_heartbeat``/``take_request``/``clear``) by the supervisor.
    """

    def __init__(
        self,
        control_dir: str | os.PathLike[str],
        *,
        heartbeat_stale_seconds: float = DEFAULT_HEARTBEAT_STALE_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._dir = Path(control_dir)
        self._stale_seconds = heartbeat_stale_seconds
        self._clock = clock

    @property
    def control_dir(self) -> Path:
        return self._dir

    @property
    def heartbeat_path(self) -> Path:
        return self._dir / HEARTBEAT_FILENAME

    @property
    def request_path(self) -> Path:
        return self._dir / REQUEST_FILENAME

    def ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ writer

    def request_restart(
        self, *, requested_by: str, reason: str | None = None
    ) -> RestartRequest:
        """Record a restart request (touch the sentinel). Idempotent-ish: a second
        call before the supervisor consumes it just overwrites the metadata."""
        self.ensure_dir()
        request = RestartRequest(
            requested_by=requested_by,
            reason=reason,
            requested_at=self._clock(),
        )
        _atomic_write_json(
            self.request_path,
            {
                "requested_by": request.requested_by,
                "reason": request.reason,
                "requested_at": request.requested_at,
            },
        )
        return request

    def read_status(self) -> SupervisorStatus:
        """Report whether a supervisor is currently armed (fresh heartbeat)."""
        try:
            raw = self.heartbeat_path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            return SupervisorStatus(armed=False)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return SupervisorStatus(armed=False)

        heartbeat_at = _as_float(data.get("heartbeat"))
        started_at = _as_float(data.get("started_at"))
        pid = _as_int(data.get("pid"))
        if heartbeat_at is None:
            return SupervisorStatus(armed=False, pid=pid, started_at=started_at)

        age = max(0.0, self._clock() - heartbeat_at)
        return SupervisorStatus(
            armed=age <= self._stale_seconds,
            pid=pid,
            started_at=started_at,
            heartbeat_at=heartbeat_at,
            heartbeat_age=age,
        )

    def is_armed(self) -> bool:
        return self.read_status().armed

    # ------------------------------------------------------------------ reader

    def write_heartbeat(self, *, pid: int, started_at: float) -> None:
        """Publish/refresh the supervisor liveness heartbeat."""
        self.ensure_dir()
        _atomic_write_json(
            self.heartbeat_path,
            {"pid": pid, "started_at": started_at, "heartbeat": self._clock()},
        )

    def take_request(self) -> RestartRequest | None:
        """Consume a pending restart request, if any.

        The *existence* of the file is the trigger; contents are best-effort
        audit metadata. The file is always removed once observed so a single
        request can never re-trigger on the next poll (no spin loop from a stuck
        sentinel).
        """
        try:
            raw = self.request_path.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            return None

        # Remove first so a parse failure can't leave a poison sentinel behind.
        try:
            self.request_path.unlink()
        except FileNotFoundError:
            return None

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            data = {}
        return RestartRequest(
            requested_by=str(data.get("requested_by", "unknown")),
            reason=(str(data["reason"]) if data.get("reason") is not None else None),
            requested_at=_as_float(data.get("requested_at")) or self._clock(),
        )

    def clear(self) -> None:
        """Remove heartbeat + any pending request (supervisor clean shutdown)."""
        for path in (self.heartbeat_path, self.request_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None
