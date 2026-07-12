"""Subprocess integration tests for the process supervisor (Sprint 72.3b/72.3c).

These spawn the *real* ``scripts/supervisor.py`` as a child process against a
throwaway control dir and a stub child command, then drive it with the *real*
sentinel-file mechanism the admin endpoint uses. Nothing is mocked away: the
restart trigger, the SIGTERM→relaunch, the crash-recovery relaunch, and the
storm guard are all exercised for real.

The headline test is the 72.3c reseed footgun guard: it uses the real
``lorecraft.ops.coldboot.reset_runtime_db`` for the cold-boot reseed and asserts
that a supervisor-driven *relaunch* leaves a mutated runtime DB untouched — i.e.
the relaunch path never reseeds — while a genuine cold boot still does.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from lorecraft.ops.coldboot import reset_runtime_db
from lorecraft.ops.restart_control import RestartControl

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUPERVISOR = _REPO_ROOT / "scripts" / "supervisor.py"

# A stub child that records each launch and exits 0 on SIGTERM (a graceful
# shutdown, like uvicorn's lifespan shutdown).
_GRACEFUL_CHILD = """
import os, signal, sys, time
log = sys.argv[1]
with open(log, "a") as f:
    f.write("start %d\\n" % os.getpid())
running = True
def _stop(signum, frame):
    global running
    running = False
signal.signal(signal.SIGTERM, _stop)
while running:
    time.sleep(0.02)
sys.exit(0)
"""

# A stub child that records its launch and immediately crashes.
_CRASH_CHILD = """
import os, sys
with open(sys.argv[1], "a") as f:
    f.write("start %d\\n" % os.getpid())
sys.exit(1)
"""


def _write_script(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    return path


def _count_starts(log: Path) -> int:
    if not log.exists():
        return 0
    return sum(1 for line in log.read_text().splitlines() if line.startswith("start"))


def _wait_until(predicate, timeout: float = 15.0, interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _spawn_supervisor(
    tmp_path: Path,
    child_script: Path,
    log: Path,
    *,
    control_dir: Path,
    extra_args: list[str] | None = None,
) -> subprocess.Popen[bytes]:
    args = [
        sys.executable,
        str(_SUPERVISOR),
        "--control-dir",
        str(control_dir),
        "--poll-interval",
        "0.05",
        "--graceful-timeout",
        "10",
        *(extra_args or []),
        "--",
        sys.executable,
        str(child_script),
        str(log),
    ]
    return subprocess.Popen(args, env=os.environ.copy())


def _terminate(proc: subprocess.Popen[bytes]) -> int:
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
        try:
            return proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            return proc.wait(timeout=5)
    return proc.returncode


def test_requested_restart_relaunches_without_reseeding_runtime_db(
    tmp_path: Path,
) -> None:
    """72.3c headline: a supervisor relaunch must NOT reseed the runtime DB."""
    control_dir = tmp_path / "control"
    log = tmp_path / "launches.log"
    child = _write_script(tmp_path / "graceful_child.py", _GRACEFUL_CHILD)

    # (d) A genuine cold boot reseeds: runtime <- seed.
    seed_db = tmp_path / "seed.db"
    runtime_db = tmp_path / "runtime.db"
    seed_db.write_bytes(b"SEED-CONTENT")
    reset_runtime_db(seed_db, runtime_db)
    assert runtime_db.read_bytes() == b"SEED-CONTENT"

    # (a) Mutate live runtime state after the cold boot.
    runtime_db.write_bytes(b"LIVE-MUTATED-STATE")

    proc = _spawn_supervisor(tmp_path, child, log, control_dir=control_dir)
    try:
        control = RestartControl(control_dir)
        # Child launched once and the supervisor is publishing a heartbeat.
        assert _wait_until(lambda: _count_starts(log) == 1), "child never launched"
        assert _wait_until(control.is_armed), "supervisor never became armed"

        # (b) Trigger a restart via the real sentinel mechanism.
        control.request_restart(requested_by="tester", reason="regression")

        # (c) The supervisor relaunches the child (graceful SIGTERM -> relaunch).
        assert _wait_until(lambda: _count_starts(log) >= 2), "child was not relaunched"

        # THE GUARD: the relaunch path never touched the runtime DB.
        assert runtime_db.read_bytes() == b"LIVE-MUTATED-STATE"
    finally:
        code = _terminate(proc)

    # Clean supervisor shutdown clears its heartbeat (no longer armed).
    assert code == 0
    assert not RestartControl(control_dir).is_armed()

    # (d) A subsequent genuine cold boot *does* reseed, wiping the mutation.
    reset_runtime_db(seed_db, runtime_db)
    assert runtime_db.read_bytes() == b"SEED-CONTENT"


def test_supervisor_recovers_from_crash_then_storm_guard_stops_it(
    tmp_path: Path,
) -> None:
    """A crashing child is relaunched (crash recovery); a crash loop is capped."""
    control_dir = tmp_path / "control"
    log = tmp_path / "crash.log"
    child = _write_script(tmp_path / "crash_child.py", _CRASH_CHILD)

    proc = _spawn_supervisor(
        tmp_path,
        child,
        log,
        control_dir=control_dir,
        extra_args=[
            "--storm-max-starts",
            "3",
            "--storm-window",
            "60",
            "--min-healthy-seconds",
            "0",
            "--restart-backoff",
            "0",
        ],
    )
    try:
        # The supervisor relaunches after each crash, then the storm guard trips
        # and it exits with the storm exit code instead of spinning forever.
        code = proc.wait(timeout=15)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)

    assert code == 70, "supervisor should abort with the storm exit code"
    # It relaunched on crash (recovery) up to the guard cap.
    assert _count_starts(log) == 3


def test_supervisor_shuts_down_child_on_sigterm(tmp_path: Path) -> None:
    """SIGTERM to the supervisor gracefully stops the child and exits cleanly."""
    control_dir = tmp_path / "control"
    log = tmp_path / "launches.log"
    child = _write_script(tmp_path / "graceful_child.py", _GRACEFUL_CHILD)

    proc = _spawn_supervisor(tmp_path, child, log, control_dir=control_dir)
    control = RestartControl(control_dir)
    assert _wait_until(lambda: _count_starts(log) == 1)
    assert _wait_until(control.is_armed)

    proc.send_signal(signal.SIGTERM)
    code = proc.wait(timeout=10)

    assert code == 0
    # No relaunch happened on a supervisor shutdown.
    assert _count_starts(log) == 1


def test_supervisor_errors_without_child_command() -> None:
    """A missing child command is a usage error, not a silent no-op."""
    proc = subprocess.run(
        [sys.executable, str(_SUPERVISOR), "--control-dir", "/tmp/x"],
        capture_output=True,
        timeout=10,
    )
    assert proc.returncode != 0
    assert b"child command" in proc.stderr.lower()


def test_supervisor_never_imports_or_calls_the_reseed() -> None:
    """Static guard: the supervisor must not import or call the reseed.

    Parses the AST (docstring mentions of the reseed are fine — an actual import
    or call is not) so a future edit that reintroduces the footgun in the
    relaunch loop fails here.
    """
    import ast

    tree = ast.parse(_SUPERVISOR.read_text(encoding="utf-8"))
    imported: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            called.add(node.func.id)

    assert not any("coldboot" in m for m in imported), imported
    assert "reset_runtime_db" not in called
    assert "prepare_runtime_dbs" not in called
