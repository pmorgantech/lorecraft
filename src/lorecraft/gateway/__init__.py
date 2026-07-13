"""Rust-port gateway adapter (Phase 3).

Composition/web-host layer: the Python side of the Rust↔Python gateway channel.
The Rust gateway owns client WebSocket sockets; this package runs a Unix-domain
socket listener (`adapter.GatewayAdapter`) that redeems auth, drives session
lifecycle, and executes forwarded commands, replying with the framed
`GatewayOutbound` types from `lorecraft.protocol.gateway`.

Import direction: like `main.py`, this package may import `engine.*`,
`features.*`, and the web hosts — but nothing under `engine/` may import it
(enforced in spirit by `tests/unit/test_tier_boundaries.py`, which keeps the
engine free of feature/web imports). Not wired into the running app this phase;
a later cutover task starts it from the app factory.
"""

from __future__ import annotations

from lorecraft.gateway.adapter import GatewayAdapter
from lorecraft.gateway.connection_manager import DirectiveConnectionManager

__all__ = ["DirectiveConnectionManager", "GatewayAdapter"]
