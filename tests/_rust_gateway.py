"""Dual-process test harness for the Rust gateway front door (Phase 3b).

Boots the Rust `lorecraft-gateway` binary as a real subprocess in front of the
Python app so the e2e/simulation exit tests can point their clients at the Rust
origin instead of talking to uvicorn directly. The Rust process terminates
`/ws` itself (redeeming a real ws-ticket over the Python adapter's UDS link) and
reverse-proxies every other HTTP request to the Python backend, exactly as it
does in production Option-A deployment.

Shared by `tests/e2e/conftest.py` and `tests/simulation/conftest.py`; both gate
the Rust path on the `LORECRAFT_THROUGH_RUST` environment flag (see
`through_rust_enabled`) so the default suites keep talking to Python directly
(the rollback path stays exercised) and only an opt-in run fronts with Rust.

Usage sketch (in a conftest fixture)::

    ensure_gateway_binary()
    python = _LiveServer(create_app(settings_with_gateway_enabled))
    python.start()
    gateway = RustGateway(backend_url=python.base_url, socket_path=sock)
    gateway.start()
    try:
        yield gateway.base_url   # the Rust front door
    finally:
        gateway.stop()
        python.stop()
"""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

import httpx

# tests/ is directly under the worktree root; rust/ lives alongside src/.
REPO_ROOT = Path(__file__).resolve().parents[1]
_RUST_DIR = REPO_ROOT / "rust"
_GATEWAY_BIN = _RUST_DIR / "target" / "debug" / "lorecraft-gateway"

_LISTENING_TIMEOUT_SECONDS = 20.0
_HEALTHZ_TIMEOUT_SECONDS = 15.0
_BUILD_TIMEOUT_SECONDS = 600.0
_STOP_GRACE_SECONDS = 5.0

# Build the gateway binary at most once per test-process, guarded by a lock so
# concurrent fixture setups (xdist is off for live-server tests, but be safe)
# don't race two cargo invocations against the same target dir.
_build_lock = threading.Lock()
_built = False


def through_rust_enabled() -> bool:
    """True when tests should route clients through the Rust gateway front door.

    Opt-in via `LORECRAFT_THROUGH_RUST` (accepts `1`/`true`/`yes`, any case) so
    the default e2e/simulation runs stay Python-direct — the Rust path is the
    coordinator's Option-A gate check, not the everyday suite.
    """
    return os.getenv("LORECRAFT_THROUGH_RUST", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def ensure_gateway_binary() -> Path:
    """Build (once) and return the path to the `lorecraft-gateway` binary.

    The Rust front door is a hard dependency of the Rust-fronted tests, so a
    missing `cargo` or a failed build raises immediately with a clear message
    rather than letting a later `subprocess.Popen` fail obscurely.
    """
    global _built
    with _build_lock:
        if _built and _GATEWAY_BIN.exists():
            return _GATEWAY_BIN
        try:
            result = subprocess.run(
                [
                    "cargo",
                    "build",
                    "-p",
                    "lorecraft-server",
                    "--bin",
                    "lorecraft-gateway",
                ],
                cwd=_RUST_DIR,
                capture_output=True,
                text=True,
                timeout=_BUILD_TIMEOUT_SECONDS,
                check=False,
            )
        except FileNotFoundError as exc:  # cargo not on PATH
            raise RuntimeError(
                "cargo is required to build the Rust gateway for the Rust-fronted "
                "tests but was not found on PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"building lorecraft-gateway timed out after {_BUILD_TIMEOUT_SECONDS}s"
            ) from exc
        if result.returncode != 0:
            raise RuntimeError(
                "failed to build lorecraft-gateway "
                f"(exit {result.returncode}):\n{result.stderr}"
            )
        if not _GATEWAY_BIN.exists():
            raise RuntimeError(
                f"cargo build succeeded but {_GATEWAY_BIN} does not exist"
            )
        _built = True
        return _GATEWAY_BIN


def unique_socket_path() -> str:
    """A short, unique UDS path for one Python-adapter <-> Rust-gateway link.

    Kept in the system temp dir (not pytest's `tmp_path`, whose nesting can blow
    past the ~108-byte `sockaddr_un` limit) with a short random stem.
    """
    return str(Path(tempfile.gettempdir()) / f"lc-gw-{uuid.uuid4().hex[:12]}.sock")


class RustGateway:
    """A `lorecraft-gateway` subprocess fronting a running Python backend.

    Spawns the binary bound to an OS-assigned port, learns that port from the
    single `GATEWAY_LISTENING <addr>` stdout line, and waits until `/healthz`
    reports the Python UDS link up before exposing `base_url`. Teardown is
    SIGTERM-then-SIGKILL and never leaks the subprocess.
    """

    def __init__(
        self,
        *,
        backend_url: str,
        socket_path: str,
        world_id: str = "world-1",
        deadline_ms: int = 5000,
    ) -> None:
        self._backend_url = backend_url
        self._socket_path = socket_path
        self._world_id = world_id
        self._deadline_ms = deadline_ms
        self._proc: subprocess.Popen[str] | None = None
        self._addr: str | None = None
        self._stdout_lines: list[str] = []
        self._stderr_lines: list[str] = []
        self._listening: queue.Queue[str] = queue.Queue(maxsize=1)
        self._readers: list[threading.Thread] = []

    @property
    def base_url(self) -> str:
        if self._addr is None:
            raise RuntimeError("RustGateway.start() has not completed")
        return f"http://{self._addr}"

    @property
    def ws_url(self) -> str:
        return "ws://" + self.base_url.removeprefix("http://")

    def start(self) -> None:
        binary = ensure_gateway_binary()
        env = {
            **os.environ,
            "LORECRAFT_GATEWAY_BIND": "127.0.0.1:0",
            "LORECRAFT_GATEWAY_SOCKET_PATH": self._socket_path,
            "LORECRAFT_GATEWAY_BACKEND": self._backend_url,
            "LORECRAFT_GATEWAY_WORLD_ID": self._world_id,
            "LORECRAFT_GATEWAY_DEADLINE_MS": str(self._deadline_ms),
        }
        self._proc = subprocess.Popen(
            [str(binary)],
            cwd=str(_RUST_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # Drain both pipes on background threads so the child never blocks on a
        # full pipe buffer, and so a crash leaves diagnosable output behind.
        self._readers = [
            threading.Thread(target=self._pump_stdout, daemon=True),
            threading.Thread(
                target=self._pump,
                args=(self._proc.stderr, self._stderr_lines),
                daemon=True,
            ),
        ]
        for reader in self._readers:
            reader.start()

        try:
            self._await_listening()
            self._await_healthy()
        except Exception:
            self.stop()
            raise

    def _pump_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        for line in self._proc.stdout:
            self._stdout_lines.append(line)
            stripped = line.strip()
            if stripped.startswith("GATEWAY_LISTENING "):
                addr = stripped.removeprefix("GATEWAY_LISTENING ").strip()
                try:
                    self._listening.put_nowait(addr)
                except queue.Full:
                    pass

    @staticmethod
    def _pump(pipe: object, sink: list[str]) -> None:
        # `pipe` is a text file object; iterate to EOF (child exit / pipe close).
        for line in pipe:  # type: ignore[attr-defined]
            sink.append(line)

    def _await_listening(self) -> None:
        deadline = time.monotonic() + _LISTENING_TIMEOUT_SECONDS
        while True:
            try:
                self._addr = self._listening.get(timeout=0.2)
                return
            except queue.Empty:
                if self._proc is not None and self._proc.poll() is not None:
                    raise RuntimeError(
                        "lorecraft-gateway exited before it started serving "
                        f"(exit {self._proc.returncode}):\n{self._stderr_text()}"
                    )
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "timed out waiting for GATEWAY_LISTENING from "
                        f"lorecraft-gateway:\n{self._stderr_text()}"
                    )

    def _await_healthy(self) -> None:
        deadline = time.monotonic() + _HEALTHZ_TIMEOUT_SECONDS
        url = f"{self.base_url}/healthz"
        last_error = "no response"
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise RuntimeError(
                    "lorecraft-gateway exited during health check "
                    f"(exit {self._proc.returncode}):\n{self._stderr_text()}"
                )
            try:
                response = httpx.get(url, timeout=1.0)
                if response.status_code == 200 and (
                    response.json().get("gateway_link") == "up"
                ):
                    return
                last_error = f"status={response.status_code} body={response.text!r}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            time.sleep(0.1)
        raise RuntimeError(
            f"lorecraft-gateway /healthz never reported the link up ({last_error})"
            f"\n{self._stderr_text()}"
        )

    def _stderr_text(self) -> str:
        return "".join(self._stderr_lines[-40:])

    def stop(self) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=_STOP_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=_STOP_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    pass
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
        for reader in self._readers:
            reader.join(timeout=1.0)
        # NB: the UDS file at `socket_path` is created and owned by the Python
        # adapter, which is still running at this point (the fixture stops it
        # after us). Its removal is the fixture's job, once Python is down.
