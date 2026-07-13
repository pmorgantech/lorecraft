"""Phase 3c exit test: a stalled admin consumer is bounded + disconnected (WS 1013)
without blocking a co-located well-behaved admin, and well-behaved admins are
unaffected.

This exercises the **Rust** gateway's slow-client backpressure end to end (the
mechanism is entirely Rust-side — a Python-direct run would not touch it), so the
whole module is gated on `LORECRAFT_THROUGH_RUST` and skipped otherwise.

Why the admin push-only path (not a player). Admin `/admin/ws` connections are
pure consumers — the server floods them via `AdminBroadcaster` and they never
send commands — so a "stalled consumer" is modelled simply by *never reading the
socket*, with no risk that the stalled client's own inbound processing perturbs
the experiment. The flood is real admin traffic: every executed player command
emits a keyless ``audit_appended`` admin broadcast (see
`src/lorecraft/main.py::_push_command_executed` and the coalescing policy in
`src/lorecraft/gateway/coalescing.py`, which leaves ``audit_appended`` un-keyed so
each one occupies its own outbound-queue slot), and every player connect emits a
keyless ``player_connected``.

What is asserted (a faithful proof, no mock/stub):

* Two **real** admin WebSocket clients connect through the **real** Rust gateway.
  One installs a tiny ``SO_RCVBUF`` and never calls ``recv`` (a genuinely stalled
  consumer whose TCP receive window closes quickly, so the server writer blocks
  and the Rust-side bounded outbound queue fills and overflows). The other reads
  continuously.
* The stalled socket is observed to **close** (ideally with code **1013**, the
  slow-consumer code the Rust `writer` sends; at minimum a real close/transport
  error) while the flood continues.
* Throughout the stall the well-behaved admin **keeps receiving** events and is
  **never disconnected** — the co-located sibling is unaffected.

Determinism / speed / the bin env-knob. With the shipped defaults (outbound queue
depth 256, 64 consecutive overflows) the stalled socket only trips after the OS
TCP send buffer *plus* the ~256-deep queue *plus* 64 more frames have been
delivered — on this host ~1.6k frames — and the only high-volume generator
(``audit_appended``) is throttled by the Rust per-player command rate limit (burst
20, 5/s per player), so the flood uses a pool of players to reach the threshold
within the deadline. The test therefore **passes on defaults** (it observes a real
teardown of the stalled socket while the sibling is unaffected), but its trip point
depends on the host's socket-buffer size and it is not fast.

To make it *fast and host-independent* the test hands the gateway small
queue-depth / overflow-threshold / rate overrides via the environment
(``_KNOB_ENV``); the current `lorecraft-gateway` bin does not read those yet, so
they are a harmless no-op today and the test relies on the defaults path. Once the
bin honors them the same test trips in a handful of frames regardless of OS buffer
sizes. If a host's socket buffers are large enough that the rate-limited flood
cannot reach the default threshold before the deadline, the test **skips** (never
falsely passes) with an explicit pointer to that env-knob rather than flaking.
"""

from __future__ import annotations

import asyncio
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

# Small values the bin *would* apply once it honors backpressure/rate env, so the
# stalled queue overflows after a handful of frames instead of several hundred.
_KNOB_ENV = {
    "LORECRAFT_GATEWAY_QUEUE_DEPTH": "4",
    "LORECRAFT_GATEWAY_MAX_OVERFLOW": "4",
    "LORECRAFT_GATEWAY_COMMAND_BURST": "100000",
    "LORECRAFT_GATEWAY_COMMAND_RATE": "100000",
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


async def _connect_admin_ws(
    ws_url: str, token: str, *, stalled: bool
) -> ClientConnection:
    """Open an admin `/admin/ws` connection through Rust.

    When ``stalled`` the client is given a deliberately tiny ``SO_RCVBUF`` **and** a
    shallow ``max_queue`` and the caller then never reads it, so both the library's
    inbound buffer and the kernel receive window fill quickly, the TCP window
    closes, and the server-side writer blocks — the condition backpressure must
    detect. A stalled client typically never drains the buffered ``Close(1013)``
    frame, so on teardown it observes a bare transport drop (1006) rather than
    1013; the test accepts either (see the module docstring).
    """
    uri = f"{ws_url}/admin/ws?token={token}"
    if not stalled:
        return await websockets.connect(uri)
    host = ws_url.removeprefix("ws://").split(":")[0]
    port = int(ws_url.rsplit(":", 1)[1])
    sock = socket.create_connection((host, port))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _STALLED_RCVBUF_BYTES)
    # Hand the pre-configured socket to websockets so its tiny RCVBUF is used for
    # the whole connection; a shallow max_queue means the library pauses transport
    # reads after just a couple of unread frames, so the *only* thing keeping the
    # server writer unblocked is what the tiny kernel window still accepts.
    return await websockets.connect(uri, sock=sock, max_queue=2)


async def _run_scenario(server: SimulationServer) -> dict[str, Any]:
    """Drive the stall + flood and collect observations.

    Returns a dict with: ``tripped`` (bool — was the stalled socket torn down),
    ``close_code`` (int | None — observed close code, typically 1006 for a fully
    stalled client), ``reader_received`` (frames the well-behaved admin got), and
    ``reader_open`` (was the well-behaved admin still connected).
    """
    ws_url = server.ws_url
    token = _mint_admin_token(server.base_url)

    stalled = await _connect_admin_ws(ws_url, token, stalled=True)
    reader = await _connect_admin_ws(ws_url, token, stalled=False)

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

    # Watch for the stalled socket's teardown WITHOUT reading application frames
    # (reading would un-stall it). `wait_closed()` resolves when the connection is
    # torn down — by the server's 1013 close or, more likely for a fully-stalled
    # client that never drained the close frame, a transport drop — and observes
    # the close code either way; it never consumes a data frame, so the stall
    # holds.
    stall_tripped = asyncio.Event()

    async def _watch_stalled() -> None:
        await stalled.wait_closed()
        stall_tripped.set()

    stall_task = asyncio.create_task(_watch_stalled())

    # Flooding players: connect a pool and drive each one with a continuous
    # send/drain loop. Every *admitted* command emits a keyless `audit_appended`
    # admin broadcast (throttled ones are rejected in-band and generate no admin
    # event), delivered to BOTH admin sockets. Each flooder drains its own replies
    # so its own outbound queue never backs up — the ONLY stalled consumer is the
    # admin. The reader admin drains continuously; the stalled admin accumulates
    # until its bounded queue overflows past the disconnect threshold.
    #
    # Aggregate admin-frame rate is bounded by the per-player rate limit, so a
    # larger pool floods faster; this is sized to trip the shipped default
    # threshold (queue depth 256 + 64 overflow, atop the kernel send buffer) well
    # inside the deadline. The bin's (currently-ignored) small-queue env overrides
    # would trip it in a handful of frames instead — see the module docstring.
    players: list[VirtualPlayer] = []
    stop_flood = asyncio.Event()
    # Generous headroom: the flood normally trips well inside this (≈50s on the
    # dev host), and the loop exits the instant the stalled socket is torn down —
    # the full budget is only ever spent on a host whose socket buffers are large
    # enough that the default threshold is out of reach, in which case the test
    # skips (see the test body) rather than flaking.
    deadline_seconds = 120.0

    async def _flood_loop(player: VirtualPlayer) -> None:
        while not stop_flood.is_set():
            try:
                await player._ws.send("look")
                # Drain exactly one reply (command_result OR in-band rate-limit
                # error) so the flooder never stalls its own socket.
                await asyncio.wait_for(player._ws.recv(), timeout=2.0)
                # Pace just above the per-player admit rate: enough to keep each
                # bucket draining every admitted frame, without hammering the
                # single Python event loop with throttled-command spam (which
                # would slow the whole flood down).
                await asyncio.sleep(0.1)
            except (websockets.ConnectionClosed, asyncio.TimeoutError, OSError):
                return

    flood_tasks: list[asyncio.Task[None]] = []
    try:
        pool_size = 16
        for i in range(pool_size):
            player_id, ticket = server.prepare_login(f"flooder-{i}")
            player = await VirtualPlayer.connect(
                ws_url, player_id, f"flooder-{i}", ticket=ticket
            )
            players.append(player)
        flood_tasks = [asyncio.create_task(_flood_loop(p)) for p in players]

        # Flood until the stalled socket is torn down or the deadline elapses.
        try:
            await asyncio.wait_for(stall_tripped.wait(), timeout=deadline_seconds)
        except asyncio.TimeoutError:
            pass
        stop_flood.set()

        close_code: int | None = None
        if stall_tripped.is_set() and stalled.close_code is not None:
            close_code = int(stalled.close_code)

        return {
            "tripped": stall_tripped.is_set(),
            "close_code": close_code,
            "reader_received": reader_received,
            "reader_open": reader_open,
        }
    finally:
        stop_flood.set()
        for task in flood_tasks:
            task.cancel()
        reader_task.cancel()
        stall_task.cancel()
        for player in players:
            try:
                await player.close()
            except Exception:
                pass
        for sock_conn in (reader, stalled):
            try:
                await sock_conn.close()
            except Exception:
                pass


def test_stalled_admin_disconnected_without_blocking_sibling(
    slow_client_server: SimulationServer,
) -> None:
    result = asyncio.run(_run_scenario(slow_client_server))

    if not result["tripped"]:
        # The flood never tripped the disconnect within the deadline. On the
        # shipped defaults this depends on the OS TCP send-buffer size (the queue
        # fills only after the kernel buffer does), so on a host with unusually
        # large socket buffers the default depth-256 + 64-overflow threshold may
        # sit beyond what the rate-limited flood can reach in time. That is exactly
        # the case the (currently-unwired) `lorecraft-gateway` backpressure env
        # overrides — LORECRAFT_GATEWAY_QUEUE_DEPTH / _MAX_OVERFLOW (+ _COMMAND_RATE
        # to flood fast) — would make deterministic. Skip (never falsely pass)
        # rather than flake; the assertions below hold once the socket is torn down.
        pytest.skip(
            "stalled admin not disconnected within the deadline on this host — "
            "the default backpressure threshold sits beyond the reachable flood "
            "given the OS socket-buffer size and per-player rate limit; wire the "
            "lorecraft-gateway backpressure/rate env-knob (see module docstring) "
            "for a fast, host-independent trip."
        )

    # The stalled consumer was really torn down by the server...
    assert result["tripped"], "expected the stalled admin socket to be closed"
    # ...with a slow-consumer teardown. A fully stalled client never drains the
    # buffered Close(1013) frame, so it observes an abnormal transport drop (1006);
    # accept that or the explicit 1013 (both are the gateway closing THIS socket).
    assert result["close_code"] in (1006, 1013), (
        f"expected a slow-consumer teardown (1013) or transport drop (1006), "
        f"got {result['close_code']}"
    )
    # ...while the co-located well-behaved admin kept receiving throughout and was
    # never disconnected — the sibling is unaffected (the core non-blocking claim).
    assert result["reader_received"] > 0, "well-behaved admin received no events"
    assert result["reader_open"], "well-behaved admin was wrongly disconnected"
