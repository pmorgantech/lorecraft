"""Phase 4 sub-slice 4a exit check: the headless `look` parity harness.

This IS the 4a deliverable ("Sub-slice 4a — execution-routing protocol +
headless `look` parity harness (NO live cutover)" in
`docs/rust_migration_plan.md`'s Phase 4 kickoff spec). It drives a synthetic
`look` through the REAL two-process stack — a real `lorecraft-gateway`
subprocess, a real Python adapter over the real UDS link, a real WebSocket
client — with the verb allow-list opted in *only* for this test
(`LORECRAFT_RUST_VERBS=look` via `RustGateway`'s `extra_env`), and proves:

1. **command_result parity** — the `look` routed through Rust's execution
   path (`route.rs` -> `execute.rs` -> `BuildSnapshot`/`ApplyOutcome` ->
   `lorecraft.gateway.effect_apply.apply_outcome`) reproduces, byte-for-byte,
   what the *same* pipeline's Python-direct half (`handle_ws_command`) returns
   for the identically-warmed-up player/room state.
2. **audit parity** — the `command_executed` audit row the Rust-executed
   `look` causes Python to persist matches the checked-in
   `tests/simulation/scenarios/look_only.audit.json` golden (the same
   normalized-audit-trail oracle `test_audit_regression.py` diffs against).
3. **actor-exclusion** — the room `state_change` delivery `apply_outcome`
   returns with `exclude=<actor>` (unit-proven in
   `tests/unit/test_gateway_phase4.py::test_apply_outcome_returns_single_state_change_delivery`)
   actually excludes the actor over the real wire: another player in the room
   receives it, the actor does not.

**No live cutover:** every other test in this suite (and every real client)
still routes through the default, empty `rust_verbs` allow-list — see
`test_default_allow_list_still_routes_look_to_python_behavior_preserving`
below, which boots the SAME Rust front door without the opt-in env var and
shows `look` is unaffected. Only this module's fixtures set
`LORECRAFT_RUST_VERBS=look`, and only for the connections under test.

**On "how do we know Rust really executed it":** since the whole point of
Option A is that the reply is byte-identical whichever side executes it, there
is no client-visible signal that distinguishes the two paths by construction.
This harness proves byte-identity end-to-end (the 4a exit check) and proves
the allow-listed and default-allow-list runs are behaviorally
indistinguishable (guarding against a silent fall-through bug); the *routing
mechanics themselves* (that `route::decide` really dispatches an allow-listed
bare `look` to `execute::execute` and not `forward::send_command`) are proven
at the impl level by `rust/crates/lorecraft-server/src/route.rs`'s unit tests
and `rust/crates/lorecraft-server/tests/execute.rs`'s hermetic mock-peer
round-trip test. This test does not re-derive that proof; it composes on top
of it end-to-end.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.tools.session_replay import normalize_events
from lorecraft.webui.player.ws_command import handle_ws_command
from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer

pytestmark = pytest.mark.simulation

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GOLDEN_AUDIT = (
    _REPO_ROOT / "tests" / "simulation" / "scenarios" / "look_only.audit.json"
)

# Matches the world-content/rng-seed precedent set by look_only.json /
# test_look_scriptresult_parity.py, though `look` draws no RNG itself.
_RNG_SEED = 1
_RUST_LOOK_ENV = {"LORECRAFT_RUST_VERBS": "look"}


def _username(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _connect(server: SimulationServer, prefix: str) -> VirtualPlayer:
    username = _username(prefix)
    player_id, ticket = server.prepare_login(username)
    return await VirtualPlayer.connect(
        server.ws_url, player_id, username, ticket=ticket
    )


# --- 1 + 2: command_result byte-identity + audit golden parity --------------


def test_rust_executed_look_matches_python_oracle_and_audit_golden(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """The core 4a exit check: Rust-execute -> Python-persist reproduces the
    Python engine's `command_result` and `look_only.audit.json`'s audit shape."""
    server = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=_RUST_LOOK_ENV,
        # Freeze the world clock: the `updates.time` panel must be identical
        # between the wire look and the in-process oracle call a moment later,
        # not merely close — an unfrozen clock is a real (if rare) source of
        # flakiness the existing gateway parity unit tests avoid the same way.
        world_time_ratio=0.0,
    )
    asyncio.run(_test_core_parity(server))


async def _test_core_parity(server: SimulationServer) -> None:
    player = await _connect(server, "looker")
    try:
        # Warm up: settle first-look state mutations (mirrors
        # tests/unit/test_gateway_phase4.py's `_warm_up_look`) so the *second*
        # (compared) look is deterministic between the wire round-trip and the
        # in-process oracle below. This warm-up look is itself routed to Rust
        # (bare "look", allow-listed) — it just isn't the one under comparison.
        await player.send_command("look")

        audit_before = len(server.audit_trail_for(player.player_id))

        # THE compared command: a bare "look" from a real client, over a real
        # WebSocket, through the real `lorecraft-gateway` subprocess, routed by
        # `route::decide` to Rust's `execute::execute` (allow-listed), which
        # drives the real BuildSnapshot/ApplyOutcome round-trip against the
        # real Python adapter, which persists via `apply_outcome` and commits.
        wire_reply = await player.send_command("look")
        assert wire_reply["type"] == "command_result"
        assert wire_reply["verb"] == "look"
        assert wire_reply["noun"] is None

        # --- audit parity: the SAME normalized-audit-trail oracle the golden
        # was captured with (`lorecraft.tools.session_replay.normalize_events`,
        # what `test_audit_regression.py` diffs `look_only.audit.json` against).
        audit_rows = server.audit_trail_for(player.player_id)
        new_rows = audit_rows[audit_before:]
        assert len(new_rows) == 1, (
            "expected exactly one new audit row for the compared look, got "
            f"{len(new_rows)}"
        )
        normalized = normalize_events(new_rows)
        golden = json.loads(_GOLDEN_AUDIT.read_text())
        assert normalized == golden

        # --- command_result parity: a REAL Python-engine oracle, not a
        # hand-authored expected blob. Two-independent-live-servers risks a
        # spurious diff from nothing more than two different generated player
        # ids/usernames (even though `look`'s payload happens not to carry
        # either — see the routing-behavior-preservation test below, which
        # exploits exactly that fact); to keep this specific compare
        # unimpeachable we instead call the exact same persistence pipeline
        # in-process, against the SAME player/room state, immediately after
        # the wire look completed. `look` derives zero effects (proven at the
        # unit level: tests/unit/test_gateway_phase4.py), so the DB state is
        # byte-identical to just before the wire look — this in-process call
        # is a faithful "what would Python-direct do for this exact state"
        # oracle, reusing `handle_ws_command`, the same function the live
        # `/ws` route and `apply_outcome`'s Python-persistence half both build
        # their reply from.
        state = server.app.state.lorecraft
        oracle_reply = await handle_ws_command(
            state,
            DirectiveConnectionManager(),
            player.player_id,
            "oracle-session",
            "look",
        )
        assert oracle_reply == wire_reply
    finally:
        await player.close()


# --- behavior-preservation guard (see module docstring's routing note) ------


def test_default_allow_list_still_routes_look_to_python_behavior_preserving(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """Same Rust front door, only the allow-list flag differs: `look` behaves
    identically whether Rust executes it (allow-listed) or Python does
    (default empty allow-list, forwarded via the unchanged Phase 3 path).

    This is the honest routing-confirmation signal this harness can give:
    Option A's whole point is a byte-identical reply regardless of which side
    executes, so there is no *client-visible* difference to assert on that
    would prove Rust definitely executed the allow-listed run. What this test
    *can* and does prove is that opting a verb into the allow-list changes
    nothing about its observable behavior — guarding against a routing bug
    that silently changed `look`'s behavior when Rust took it over. The
    routing mechanics themselves (that an allow-listed bare `look` really
    dispatches to `execute::execute`, not `forward::send_command`) are proven
    at the impl level by `route.rs`'s unit tests and `tests/execute.rs`.

    Holding the front door constant (both runs go through a real
    `lorecraft-gateway` subprocess) isolates the allow-list as the only
    variable — unlike comparing against a Python-direct (no-gateway) server,
    which would also change the transport.
    """
    rust_executed = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=_RUST_LOOK_ENV,
        world_time_ratio=0.0,
    )
    python_forwarded = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=None,  # default empty allow-list: look forwards to Python
        world_time_ratio=0.0,
    )
    asyncio.run(_test_behavior_preservation(rust_executed, python_forwarded))


async def _test_behavior_preservation(
    rust_executed: SimulationServer, python_forwarded: SimulationServer
) -> None:
    rust_player = await _connect(rust_executed, "rust_look")
    python_player = await _connect(python_forwarded, "python_look")
    try:
        # Warm up both identically before the compared look, same rationale as
        # the core parity test.
        await rust_player.send_command("look")
        await python_player.send_command("look")

        rust_reply = await rust_player.send_command("look")
        python_reply = await python_player.send_command("look")

        # `look`'s payload carries no player-identifying field (room-derived
        # content only — see `player_ui_updates`/`look_effects`), and both
        # servers seed the same fresh world with the same starting room and an
        # empty inventory, so two independently created players' bare `look`
        # replies are directly comparable.
        assert rust_reply == python_reply
    finally:
        await rust_player.close()
        await python_player.close()


# --- actor exclusion ----------------------------------------------------


def test_look_state_change_excludes_the_actor(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """A second player in the room receives the `look`'s room `state_change`;
    the acting player receives only their own `command_result` — never a
    self-targeted copy of that broadcast (`apply_outcome`'s
    `exclude=<actor>`, unit-proven in
    `test_apply_outcome_returns_single_state_change_delivery`, holds over the
    real wire+gateway round-trip)."""
    server = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=_RUST_LOOK_ENV,
        world_time_ratio=0.0,
    )
    asyncio.run(_test_actor_exclusion(server))


async def _test_actor_exclusion(server: SimulationServer) -> None:
    actor = await _connect(server, "actor")
    witness = await _connect(server, "witness")
    try:
        # Warm-up look (routed to Rust) also broadcasts a room state_change to
        # `witness`; drain it explicitly so the compared exchange below can't
        # be satisfied by this stale message instead.
        await actor.send_command("look")
        warmup_state_change = await witness.wait_for_broadcast(
            "state_change", timeout=5
        )
        assert warmup_state_change["actor_id"] == actor.player_id

        before_actor_message_count = len(actor.messages)
        actor_result, state_change = await asyncio.gather(
            actor.send_command("look"),
            witness.wait_for_broadcast("state_change", timeout=5),
        )

        assert actor_result["type"] == "command_result"
        assert state_change["actor_id"] == actor.player_id
        assert "players-online" in state_change["affected_panels"]

        # The actor must not have received a self-targeted copy of that same
        # broadcast (only their own direct `command_result` reply).
        new_actor_messages = actor.messages[before_actor_message_count:]
        assert not any(
            message.get("type") == "state_change"
            and message.get("actor_id") == actor.player_id
            for message in new_actor_messages
        ), (
            "actor received their own look's room state_change; "
            "apply_outcome's exclude=<actor> was not honored over the wire"
        )
    finally:
        await actor.close()
        await witness.close()
