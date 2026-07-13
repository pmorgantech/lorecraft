"""Rust gateway WS auth rejection (Phase 3b exit check, auth-rejection half).

Complements the multiplayer scenarios (which prove the *happy* ticket path
round-trips: create -> cookie -> `/auth/ws-ticket` -> `?ticket=` -> live `/ws`)
with the *sad* path: an absent/garbage/expired ticket must be rejected. This
drives the real dual-process stack — a `lorecraft-gateway` subprocess in front
of the Python adapter — so it exercises `auth::redeem_player_ticket` -> reject
-> WS close **1008** through the actual UDS link, not a unit stub.

These always front with Rust (via the `rust_gateway_server` fixture), regardless
of `LORECRAFT_THROUGH_RUST`, since the whole point is the Rust front door.
"""

from __future__ import annotations

import asyncio

import pytest
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatus

from tests.simulation.conftest import SimulationServer

pytestmark = pytest.mark.simulation

# RFC 6455 policy-violation close code — how both the Python `/ws` endpoint and
# the Rust gateway signal a rejected ticket (distinct from a 1006 abnormal drop).
_WS_POLICY_VIOLATION = 1008


def _closed_code(exc: ConnectionClosed) -> int | None:
    """Best-effort extraction of the peer's close code across websockets shapes."""
    rcvd = getattr(exc, "rcvd", None)
    if rcvd is not None and getattr(rcvd, "code", None) is not None:
        return int(rcvd.code)
    code = getattr(exc, "code", None)
    return int(code) if code is not None else None


async def _expect_policy_close(ws_url: str, query: str) -> None:
    """Connect to `<ws_url>/ws?<query>` and assert a 1008 policy close.

    The gateway accepts the upgrade (101) and then closes with 1008, so the
    connect may succeed and the first `recv()` raise `ConnectionClosed`, or —
    depending on timing — the close arrives during the handshake. Both surface
    the same peer close code, which is what we assert on.
    """
    try:
        async with websockets.connect(f"{ws_url}/ws?{query}") as ws:
            with pytest.raises(ConnectionClosed) as exc_info:
                await asyncio.wait_for(ws.recv(), timeout=5)
        code = _closed_code(exc_info.value)
    except ConnectionClosed as exc:  # close observed during the handshake
        code = _closed_code(exc)
    except InvalidStatus as exc:  # upgrade refused outright (still a rejection)
        pytest.fail(f"expected a 1008 WS close, got HTTP rejection: {exc}")
        return
    assert code == _WS_POLICY_VIOLATION, (
        f"expected WS close {_WS_POLICY_VIOLATION}, got {code}"
    )


def test_garbage_ticket_is_rejected_with_1008(
    rust_gateway_server: SimulationServer,
) -> None:
    """A ticket that was never minted is rejected: redeem fails -> 1008."""
    asyncio.run(
        _expect_policy_close(
            rust_gateway_server.ws_url, "ticket=this-ticket-was-never-issued"
        )
    )


def test_absent_ticket_is_rejected_with_1008(
    rust_gateway_server: SimulationServer,
) -> None:
    """No `?ticket=` at all (and no legacy `?player_id=`) closes with 1008."""
    asyncio.run(_expect_policy_close(rust_gateway_server.ws_url, ""))


def test_reused_ticket_is_rejected_with_1008(
    rust_gateway_server: SimulationServer,
) -> None:
    """A single-use ticket redeemed once is rejected on a second use -> 1008.

    Also proves the happy path once: the first connect with a freshly minted
    ticket completes the `connected` handshake, and only the *replay* is
    rejected — the single-use invariant enforced end-to-end through Rust.
    """
    asyncio.run(_test_reused_ticket(rust_gateway_server))


async def _test_reused_ticket(server: SimulationServer) -> None:
    from tests.simulation.virtual_player import VirtualPlayer

    player_id, ticket = server.prepare_login("replay_probe")
    assert ticket is not None, "rust_gateway_server must mint a real ticket"

    # First use succeeds and consumes the single-use ticket.
    player = await VirtualPlayer.connect(
        server.ws_url, player_id, "replay_probe", ticket=ticket
    )
    await player.close()

    # Second use of the same (now-consumed) ticket is rejected with 1008.
    await _expect_policy_close(server.ws_url, f"ticket={ticket}")
