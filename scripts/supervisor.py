#!/usr/bin/env python3
"""Process supervisor for the Lorecraft engine (roadmap Sprint 72.3b, Option A).

The app historically had *no* supervisor: ``start.sh`` ran ``uvicorn`` as a plain
foreground child, so a crash meant permanent downtime and an admin "restart"
had nothing to bring the process back. This script is that missing parent.

Responsibilities:

* Launch ``uvicorn`` (or any given command) as a child and watch it.
* Publish a liveness **heartbeat** so the admin "request restart" endpoint can
  tell an operator whether a performer is actually armed.
* On a restart **request** (a sentinel file written by that endpoint), do a
  *graceful* restart: **SIGTERM the child and wait** for uvicorn's lifespan
  shutdown to run. That clean shutdown is what closes WebSockets with close
  frames so the server's ``begin_grace_period`` fires and players re-attach via
  the reconnect-grace cushion (docs/roadmap.md Sprint 72.3 design). Then
  **relaunch** — crucially **without** re-running the cold-boot DB reseed, so
  live runtime state survives.
* On an **unexpected** child exit (a crash), relaunch it too — the general
  crash-recovery win the process model was missing.
* A **restart-storm guard** covers both paths: too many launches in a short
  window aborts the supervisor instead of spin-looping a stuck trigger or a
  crash loop forever.

The reseed lives only in ``start.sh``'s one-time cold-boot section (which calls
``lorecraft.ops.coldboot``); this loop never touches it. That split is the
whole point of Option A and is guarded by a regression test (72.3c).
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field

# Ensure the in-repo ``src`` is importable when run directly (start.sh invokes
# this via the venv python, where lorecraft is installed; this fallback covers
# a plain ``python scripts/supervisor.py`` from a checkout).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO_ROOT, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from lorecraft.ops.restart_control import RestartControl  # noqa: E402

log = logging.getLogger("lorecraft.supervisor")

_DEFAULT_CONTROL_DIR = "/tmp/lorecraft-control"

# Exit codes
_EXIT_CLEAN = 0
_EXIT_STORM = 70  # EX_SOFTWARE: repeated failures, give up so an operator notices


@dataclass
class SupervisorConfig:
    """Tunables for the watch/relaunch loop (all overridable via CLI/env)."""

    control_dir: str = _DEFAULT_CONTROL_DIR
    poll_interval: float = 1.0
    graceful_timeout: float = 30.0
    # Restart-storm guard: if more than ``storm_max_starts`` child launches
    # happen within ``storm_window`` seconds, abort rather than spin.
    storm_window: float = 60.0
    storm_max_starts: int = 5
    # A child that exits sooner than this ran "unhealthily short"; back off
    # before relaunch so even a sub-guard-threshold crash loop can't tight-spin.
    min_healthy_seconds: float = 5.0
    restart_backoff: float = 2.0


@dataclass
class _WatchResult:
    kind: str  # "requested" | "exited" | "shutdown"
    exit_code: int | None = None
    requested_by: str | None = None


@dataclass
class Supervisor:
    """Owns the child process lifecycle and the restart handshake."""

    child_command: list[str]
    config: SupervisorConfig
    control: RestartControl = field(init=False)
    started_at: float = field(default_factory=time.time)
    _child: subprocess.Popen[bytes] | None = field(default=None, init=False)
    _shutdown: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self.control = RestartControl(self.config.control_dir)

    # -- signal handling ---------------------------------------------------

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)

    def _on_signal(self, signum: int, _frame: object) -> None:
        # Supervisor itself asked to stop: forward to the child so it shuts down
        # gracefully, and let the watch loop unwind (no relaunch).
        log.info("supervisor received signal %s; shutting down", signum)
        self._shutdown = True
        self._signal_child(signal.SIGTERM)

    def _signal_child(self, sig: int) -> None:
        child = self._child
        if child is not None and child.poll() is None:
            try:
                child.send_signal(sig)
            except ProcessLookupError:
                pass

    # -- main loop ---------------------------------------------------------

    def run(self) -> int:
        self.install_signal_handlers()
        starts: deque[float] = deque()
        try:
            while not self._shutdown:
                if self._is_storming(starts):
                    log.error(
                        "restart storm: %d launches within %.0fs — aborting",
                        len(starts),
                        self.config.storm_window,
                    )
                    return _EXIT_STORM

                launched_at = time.time()
                starts.append(launched_at)
                self._child = self._spawn()
                log.info(
                    "launched child pid=%s: %s", self._child.pid, self.child_command
                )

                result = self._watch()

                if result.kind == "shutdown":
                    self._await_child(self.config.graceful_timeout)
                    return _EXIT_CLEAN

                if result.kind == "requested":
                    log.info(
                        "restart requested by %s — graceful SIGTERM + relaunch",
                        result.requested_by,
                    )
                    self._graceful_terminate()
                    continue

                # kind == "exited": unexpected child death -> crash recovery.
                log.warning(
                    "child exited unexpectedly (code=%s) — relaunching",
                    result.exit_code,
                )
                self._backoff_if_unhealthy(launched_at)
        finally:
            self.control.clear()
        return _EXIT_CLEAN

    # -- helpers -----------------------------------------------------------

    def _spawn(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(self.child_command)

    def _watch(self) -> _WatchResult:
        """Poll the child while refreshing the heartbeat and watching for a request."""
        assert self._child is not None
        while True:
            code = self._child.poll()
            if code is not None:
                return _WatchResult(kind="exited", exit_code=code)

            self.control.write_heartbeat(pid=os.getpid(), started_at=self.started_at)

            request = self.control.take_request()
            if request is not None:
                return _WatchResult(kind="requested", requested_by=request.requested_by)

            if self._shutdown:
                return _WatchResult(kind="shutdown")

            time.sleep(self.config.poll_interval)

    def _graceful_terminate(self) -> None:
        """SIGTERM the child and wait for its lifespan shutdown to complete."""
        self._signal_child(signal.SIGTERM)
        if not self._await_child(self.config.graceful_timeout):
            log.warning("child did not exit within grace timeout — SIGKILL")
            self._signal_child(signal.SIGKILL)
            self._await_child(5.0)

    def _await_child(self, timeout: float) -> bool:
        child = self._child
        if child is None:
            return True
        try:
            child.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def _backoff_if_unhealthy(self, launched_at: float) -> None:
        if time.time() - launched_at < self.config.min_healthy_seconds:
            time.sleep(self.config.restart_backoff)

    def _is_storming(self, starts: deque[float]) -> bool:
        cutoff = time.time() - self.config.storm_window
        while starts and starts[0] < cutoff:
            starts.popleft()
        return len(starts) >= self.config.storm_max_starts


def _build_config(args: argparse.Namespace) -> SupervisorConfig:
    return SupervisorConfig(
        control_dir=args.control_dir,
        poll_interval=args.poll_interval,
        graceful_timeout=args.graceful_timeout,
        storm_window=args.storm_window,
        storm_max_starts=args.storm_max_starts,
        min_healthy_seconds=args.min_healthy_seconds,
        restart_backoff=args.restart_backoff,
    )


def _parse_args(argv: list[str] | None) -> tuple[SupervisorConfig, list[str]]:
    parser = argparse.ArgumentParser(
        description="Supervise a child process with graceful admin-requested restart."
    )
    parser.add_argument(
        "--control-dir",
        default=os.getenv("LORECRAFT_CONTROL_DIR", _DEFAULT_CONTROL_DIR),
        help="Directory for the restart-request / heartbeat handshake files.",
    )
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--graceful-timeout", type=float, default=30.0)
    parser.add_argument("--storm-window", type=float, default=60.0)
    parser.add_argument("--storm-max-starts", type=int, default=5)
    parser.add_argument("--min-healthy-seconds", type=float, default=5.0)
    parser.add_argument("--restart-backoff", type=float, default=2.0)
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="The child command to run, after a `--` separator.",
    )
    args = parser.parse_args(argv)

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error(
            "no child command given (expected: supervisor.py [opts] -- CMD ...)"
        )
    return _build_config(args), command


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.getenv("LORECRAFT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config, command = _parse_args(argv)
    return Supervisor(child_command=command, config=config).run()


if __name__ == "__main__":
    raise SystemExit(main())
