"""Phase 3c exit test: a stalled admin consumer is bounded + disconnected by the
gateway's slow-client backpressure without blocking a co-located well-behaved admin.

This exercises the **Rust** gateway's slow-client backpressure end to end (the
mechanism is entirely Rust-side — a Python-direct run would not touch it), so the
whole module is gated on `LORECRAFT_THROUGH_RUST` and skipped otherwise.

Why the admin push-only path (not a player). Admin `/admin/ws` connections are
pure consumers — the server floods them via `AdminBroadcaster` and they never send
commands — so a "stalled consumer" is a socket that simply *stops reading*, with no
inbound processing to perturb the experiment. The flood is real admin traffic:
every executed player command emits a keyless ``audit_appended`` admin broadcast
(see `src/lorecraft/main.py::_push_command_executed`; ``audit_appended`` is left
un-keyed by `src/lorecraft/gateway/coalescing.py`, so each occupies its own
outbound-queue slot rather than coalescing away).

What is asserted (a faithful proof, no mock/stub):

* A **genuinely** stalled admin (a raw socket that performs the WS upgrade by hand
  and then never reads — see ``_connect_stalled_admin_raw``) is **torn down** by the
  gateway's slow-consumer backpressure while the flood runs.
* A co-located **well-behaved** admin (`websockets`, draining continuously) **keeps
  receiving** events throughout the stall and is **never disconnected** — the
  sibling is unaffected (the core non-blocking claim).

Determinism / speed / why a raw socket + the ``SEND_BUFFER_BYTES`` knob. Two facts
make the naive approach neither fast nor reliable:

1. **A `websockets` client cannot model a stalled consumer here.** Even with a
   shallow ``max_queue`` and no ``recv()`` call, its asyncio read task keeps draining
   the transport (verified empirically on this platform), so the server writer never
   blocks. The stalled consumer is therefore a raw TCP socket that never reads.
2. **The trip point is dominated by the OS *send* buffer, not the outbound queue
   depth.** With the default ``SO_SNDBUF`` (megabytes) a non-reading consumer's kernel
   buffer absorbs *thousands* of frames before the writer blocks — so ``QUEUE_DEPTH``
   / ``MAX_OVERFLOW`` barely move the trip count, and it is slow + host-dependent.
   Capping ``SO_SNDBUF`` (via the ``LORECRAFT_GATEWAY_SEND_BUFFER_BYTES`` bin knob)
   to a few KB makes the writer block after a *handful* of frames, so the outbound
   queue overflows into the slow-consumer disconnect promptly and **independent of
   the host's default socket buffers**.

So ``_KNOB_ENV`` caps the send buffer (the load-bearing knob), un-throttles the
command rate (so the few frames needed arrive fast), and shrinks ``MAX_OVERFLOW``;
``QUEUE_DEPTH`` stays at its default so the well-behaved sibling absorbs dispatch
bursts without tripping. The stalled socket cannot observe its own teardown while
frozen (the ``Close``/``FIN`` sit behind a window-blocked backlog, and there is no
RST for a window-blocked graceful close), so the test stalls + floods for a fixed
window that clears the trip plus the writer's fixed (production, 5s) close grace,
then re-opens the window and drains the socket to confirm the teardown
(``_confirm_stalled_torn_down``). A fully non-reading client sees the teardown as an
honest transport drop (equivalent to WS 1006) rather than a clean 1013 close.

The test **always runs and asserts** — no host-dependent skip that could silently
mask a regression: a failure to tear the stalled socket down is a hard failure.
"""

from __future__ import annotations

import asyncio
import base64
import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
import websockets
from websockets.asyncio.client import ClientConnection

from lorecraft.config import Settings
from lorecraft.main import create_app
from tests._rust_gateway import (
    RustGateway,
    ensure_gateway_binary,
    through_rust_enabled,
    unique_socket_path,
)
from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer

pytestmark = pytest.mark.simulation

REPO_ROOT = Path(__file__).resolve().parents[2]
_STARTUP_TIMEOUT_SECONDS = 10.0

_ADMIN_USER = "sim-admin"
_ADMIN_PASS = "sim-admin-pass-1234"

# Env overrides the `lorecraft-gateway` bin honors (see its module docs + this
# module's docstring). These make the stalled consumer trip fast and
# host-independently; when absent, production keeps its OS-tuned defaults.
_KNOB_ENV = {
    # The load-bearing knob: cap the gateway's per-connection send buffer so a
    # non-reading consumer's kernel buffer fills after only a handful of frames and
    # the writer blocks promptly — host-independent (see the module docstring). With
    # the OS default (megabytes) the trip point is dominated by that buffer, not the
    # queue depth, which is why this test is fast and deterministic only with the cap.
    "LORECRAFT_GATEWAY_SEND_BUFFER_BYTES": "4096",
    # Trip promptly once the writer is blocked.
    "LORECRAFT_GATEWAY_MAX_OVERFLOW": "8",
    # Do not rate-limit the flood, so the (few) frames needed to trip arrive fast.
    "LORECRAFT_GATEWAY_COMMAND_BURST": "100000",
    "LORECRAFT_GATEWAY_COMMAND_RATE": "100000",
    # QUEUE_DEPTH is left at its default (256): the well-behaved sibling reader must
    # absorb dispatch bursts without tripping, and the capped send buffer — not the
    # queue depth — is what makes the *stalled* consumer trip quickly.
}

# Tiny receive buffer for the stalled admin so its TCP window closes fast and the
# server writer blocks after buffering little (bounds the kernel-side absorption).
_STALLED_RCVBUF_BYTES = 2048


class _LiveServer:
    """Runs the real FastAPI app under uvicorn on a background thread."""

    def __init__(self, app: Any) -> None:
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            ws="websockets-sansio",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("live slow-client server did not start in time")
            time.sleep(0.01)

    @property
    def base_url(self) -> str:
        port = self._server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


@pytest.fixture
def slow_client_server(
    tmp_path: Path,
) -> Iterator[SimulationServer]:
    """A Rust-fronted live server with a seeded admin, for the slow-client test.

    Boots the Python app with the gateway adapter enabled *and* an admin seeded
    (so a raw client can mint an admin token for `/admin/ws`), spawns the
    `lorecraft-gateway` in front of it, and yields a `SimulationServer` (reused
    from the simulation conftest) bound to the Rust front door so the test can
    create + connect flooding players through the real ticket flow.
    """
    if not through_rust_enabled():
        pytest.skip(
            "slow-client backpressure is Rust-side; set LORECRAFT_THROUGH_RUST=1"
        )

    ensure_gateway_binary()
    socket_path = unique_socket_path()
    game_db = tmp_path / "slow-game.db"
    audit_db = tmp_path / "slow-audit.db"
    settings = Settings(
        database_path=str(game_db),
        audit_database_path=str(audit_db),
        world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
        seed_player_id="",
        seed_player_username="",
        # Rust front door → ticket-only /ws (no ?player_id= fallback).
        allow_query_player_id=False,
        gateway_enabled=True,
        gateway_socket_path=socket_path,
        admin_jwt_secret="sim-admin-session-secret-key-32chars!!",
        admin_seed_username=_ADMIN_USER,
        admin_seed_password=_ADMIN_PASS,
        admin_seed_role="superadmin",
    )
    server = _LiveServer(create_app(settings=settings))
    server.start()
    gateway = RustGateway(
        backend_url=server.base_url,
        socket_path=socket_path,
        extra_env=_KNOB_ENV,
    )
    try:
        gateway.start()
        yield SimulationServer(
            base_url=gateway.base_url,
            game_db_path=game_db,
            audit_db_path=audit_db,
            through_rust=True,
        )
    finally:
        gateway.stop()
        server.stop()
        Path(socket_path).unlink(missing_ok=True)


def _mint_admin_token(base_url: str) -> str:
    """Log the seeded admin in through the proxy and return its access token."""
    response = httpx.post(
        f"{base_url}/admin/auth/token",
        json={"username": _ADMIN_USER, "password": _ADMIN_PASS},
        timeout=5.0,
    )
    response.raise_for_status()
    token = response.json().get("access_token")
    assert token, f"admin login returned no access_token: {response.text!r}"
    return token


async def _connect_reader_admin(ws_url: str, token: str) -> ClientConnection:
    """Open the well-behaved sibling admin `/admin/ws` connection (drains normally)."""
    return await websockets.connect(f"{ws_url}/admin/ws?token={token}")


def _connect_stalled_admin_raw(ws_url: str, token: str) -> socket.socket:
    """Open a **genuinely** stalled admin `/admin/ws` connection as a raw socket.

    A `websockets` client cannot model a stalled consumer on this platform: even
    with a shallow ``max_queue`` and no ``recv()`` call, its asyncio read task keeps
    draining the transport, so the server writer never blocks (verified empirically).
    So the stalled consumer is a **raw TCP socket** that performs the WebSocket
    upgrade by hand, reads the ``101`` response, and then **never reads another
    byte**. Combined with the gateway's capped ``SO_SNDBUF`` (``_KNOB_ENV``), the
    server's send buffer fills after only a handful of pushed frames, the writer
    blocks, and the Rust outbound queue overflows into the slow-consumer disconnect —
    deterministically and independent of the host's *default* socket-buffer size.

    A tiny ``SO_RCVBUF`` shrinks the client receive window too, so the writer blocks
    even sooner. The socket is left in non-blocking mode; the caller confirms the
    teardown after the stall window with ``_confirm_stalled_torn_down``.
    """
    host = ws_url.removeprefix("ws://").split(":")[0]
    port = int(ws_url.rsplit(":", 1)[1])
    sock = socket.create_connection((host, port))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _STALLED_RCVBUF_BYTES)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET /admin/ws?token={token} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode())
    # Read just the handshake response (bounded); then never read again.
    sock.settimeout(10.0)
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            sock.close()
            raise RuntimeError("gateway closed during stalled-admin WS handshake")
        buf += chunk
    status_line = buf.split(b"\r\n", 1)[0]
    if b" 101 " not in status_line:
        sock.close()
        raise RuntimeError(f"stalled-admin WS upgrade failed: {status_line!r}")
    sock.setblocking(False)
    return sock


def _confirm_stalled_torn_down(sock: socket.socket, *, timeout: float) -> bool:
    """Confirm the (previously stalled) raw socket was torn down by the gateway.

    Called **after** the stall window, once the slow-consumer trip has certainly
    fired server-side, so draining is now safe (it cannot prevent a trip that has
    already happened). Draining also opens the receive window, which lets the
    gateway flush its buffered frames + the ``Close`` and then close the socket.

    A genuinely non-reading client can't observe the teardown any other way: the
    ``Close(1013)`` frame and the ``FIN`` sit *behind* the buffered push frames with
    the receive window pinned shut, so a non-consuming ``MSG_PEEK`` never sees them
    (there is no RST for a window-blocked graceful close). Reading drains that
    backlog and reaches the terminal ``FIN`` (``recv`` returns ``b""``) or a reset
    (``ConnectionError``/``OSError``) — either is a teardown. Returns ``False`` only
    if the socket stays open (keeps yielding data, never closing) within ``timeout``.
    """
    # Re-open the receive window wide so the window-blocked backlog (the gateway's
    # unsent frames + terminal FIN) floods in quickly instead of trickling through
    # the tiny stall-time RCVBUF — keeps the confirm-drain to ~1s.
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    except OSError:
        pass
    sock.setblocking(True)
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False  # still delivering data, never closed → not torn down
        sock.settimeout(remaining)
        try:
            data = sock.recv(1 << 16)
        except (ConnectionError, OSError) as exc:
            # A timeout means "still open, no more data" (not torn down); any other
            # OSError is a transport reset (torn down).
            return not isinstance(exc, socket.timeout)
        if data == b"":
            return True  # clean FIN → torn down


async def _run_scenario(server: SimulationServer) -> dict[str, Any]:
    """Drive the stall + flood and collect observations.

    Returns a dict with: ``tripped`` (bool — was the stalled raw socket torn down),
    ``reader_received`` (frames the well-behaved sibling admin got), and
    ``reader_open`` (was the sibling still connected at the end).
    """
    ws_url = server.ws_url
    token = _mint_admin_token(server.base_url)

    # The genuinely-stalled consumer (raw socket, never reads) + the well-behaved
    # sibling (drains continuously). Both are real admin `/admin/ws` connections
    # through the real Rust gateway; they receive the same fan-out.
    stalled_sock = _connect_stalled_admin_raw(ws_url, token)
    reader = await _connect_reader_admin(ws_url, token)

    reader_received = 0
    reader_open = True

    async def _drain_reader() -> None:
        nonlocal reader_received, reader_open
        try:
            while True:
                await reader.recv()
                reader_received += 1
        except websockets.ConnectionClosed:
            reader_open = False

    reader_task = asyncio.create_task(_drain_reader())

    # Flooding players: a pool driven by decoupled send + drain loops so each
    # flooder's own socket never backs up (it drains everything it is sent) — the
    # ONLY stalled consumer is the raw admin socket. Every admitted `look` emits a
    # keyless `audit_appended` admin broadcast delivered to BOTH admin connections,
    # so the stalled socket's kernel buffer fills; with the capped `SO_SNDBUF` the
    # server writer blocks after a handful of frames and the outbound queue overflows
    # into the slow-consumer disconnect.
    players: list[VirtualPlayer] = []
    stop_flood = asyncio.Event()
    # Keep the flood on through a fixed stall window that comfortably exceeds the
    # gateway's trip time *plus* its (production, 5s) slow-client close grace, so the
    # stalled socket is definitely torn down before we look. The trip itself is fast
    # and host-independent (the capped `SO_SNDBUF` fills after a handful of frames);
    # the window is dominated by that fixed 5s grace, not by any host-dependent
    # buffer. We do NOT read the stalled socket during this window (reading would
    # relieve the backpressure and prevent the trip); we only confirm afterwards.
    stall_window_seconds = 11.0
    confirm_timeout_seconds = 6.0

    async def _flood_send(player: VirtualPlayer) -> None:
        while not stop_flood.is_set():
            try:
                await player._ws.send("look")
                await asyncio.sleep(0.02)
            except (websockets.ConnectionClosed, OSError):
                return

    async def _flood_drain(player: VirtualPlayer) -> None:
        while not stop_flood.is_set():
            try:
                await player._ws.recv()
            except (websockets.ConnectionClosed, OSError):
                return

    flood_tasks: list[asyncio.Task[None]] = []
    try:
        pool_size = 8
        for i in range(pool_size):
            player_id, ticket = server.prepare_login(f"flooder-{i}")
            player = await VirtualPlayer.connect(
                ws_url, player_id, f"flooder-{i}", ticket=ticket
            )
            players.append(player)
        for p in players:
            flood_tasks.append(asyncio.create_task(_flood_send(p)))
            flood_tasks.append(asyncio.create_task(_flood_drain(p)))

        # Stall + flood for the fixed window so the slow-consumer trip certainly
        # fires. Capture the sibling's progress at that point (it must have been
        # receiving *during* the stall — proof it was never blocked by the stalled
        # peer), then stop the flood and confirm the stalled socket was torn down.
        await asyncio.sleep(stall_window_seconds)
        reader_received_during_stall = reader_received
        reader_open_during_stall = reader_open
        stop_flood.set()
        for task in flood_tasks:
            task.cancel()
        # Blocking socket reads in a thread so they never block the event loop.
        tripped = await asyncio.to_thread(
            _confirm_stalled_torn_down, stalled_sock, timeout=confirm_timeout_seconds
        )

        return {
            "tripped": tripped,
            "reader_received": reader_received_during_stall,
            "reader_open": reader_open_during_stall,
        }
    finally:
        stop_flood.set()
        for task in flood_tasks:
            task.cancel()
        reader_task.cancel()

        async def _close_quietly(closer: Any) -> None:
            try:
                await asyncio.wait_for(closer(), timeout=2.0)
            except (Exception, asyncio.TimeoutError):
                pass

        # Close every WS client concurrently so a wedged socket can't serialise the
        # teardown into a multi-second stall.
        await asyncio.gather(
            *(_close_quietly(p.close) for p in players),
            _close_quietly(reader.close),
        )
        try:
            stalled_sock.close()
        except OSError:
            pass


def test_stalled_admin_disconnected_without_blocking_sibling(
    slow_client_server: SimulationServer,
) -> None:
    result = asyncio.run(_run_scenario(slow_client_server))

    # The stalled consumer was really torn down by the server. The capped send
    # buffer (`_KNOB_ENV`) makes the writer block after a handful of frames — bounded
    # by that cap, not the host's default socket buffer — so this ALWAYS happens
    # within the generous deadline. A failure to trip is a real backpressure
    # regression, asserted (never skipped) so it can never be silently masked.
    assert result["tripped"], (
        "expected the stalled admin socket to be torn down by the gateway's "
        "slow-consumer backpressure within the deadline; it was not — the teardown "
        "has regressed, or LORECRAFT_GATEWAY_SEND_BUFFER_BYTES/_MAX_OVERFLOW are not "
        "honored by the bin."
    )
    # A fully non-reading raw client never drains the buffered Close(1013) frame, so
    # it observes an honest transport reset (equivalent to WS 1006) rather than a
    # clean 1013 close — either way the gateway closed THIS socket. Asserting a
    # precise 1013 would require a slow-but-not-frozen consumer that reads the close
    # frame; that is deliberately out of scope here (the transport drop is the
    # faithful outcome for a genuinely stalled consumer).
    #
    # Meanwhile the co-located well-behaved admin kept receiving throughout and was
    # never disconnected — the sibling is unaffected (the core non-blocking claim).
    assert result["reader_received"] > 0, "well-behaved admin received no events"
    assert result["reader_open"], "well-behaved admin was wrongly disconnected"
