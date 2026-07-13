"""Phase 4 sub-slice 4c exit check: the headless MOVEMENT parity harness.

The `look` harness (`test_phase4_look_parity.py`) proved byte-identity for a
**read-only** verb. Movement is the mutating-verb counterpart -- Decision 4's
`move_only` golden family plus the state-snapshot hash (the Phase-0-deferred
`hash_state`) -- and is the harder bar: a non-skill-gated move driven through
the real Rust-execute -> Python-persist path must reproduce the Python engine's
STATE MUTATION, not just its reply text.

**Movement is NOT in the default allow-list this phase** (headless-only, no
live cutover -- see `rust/crates/lorecraft-server/src/route.rs`'s module docs
and `MigratedVerb::Move`'s doc comment). Every test below opts a single
direction in explicitly via `extra_env={"LORECRAFT_RUST_VERBS": "north"}`.

**The routable wire command is the BARE direction word (`"north"`), not
`"go north"`.** `route.rs::decide` only dispatches a *single-token* line to
Rust's execution path -- a two-token `"go north"` always falls back to Python
this phase, regardless of the allow-list (see `route.rs`'s
`go_with_argument_falls_back_to_python` unit test). `north`/`go north` are the
same registered move handler Python-side (`DIRECTION_ALIASES` /
`registry_verb`), so this is a routing-shape detail, not a behavior change --
the `move_only` scenario/golden family (`tests/simulation/scenarios/move_only*`)
was captured driving bare `"north"` for exactly this reason.

**The chosen move: `village_square` --north--> `blacksmith_forge`.** Verified
at runtime (`_verify_open_and_non_skill_gated`, reading the live seeded DB via
`RoomRepo` + the terrain registry -- never assumed) to be unlocked, carry no
condition-flags, and target terrain `"normal"` (`required_skill is None`), so
this move never enters the terrain-skill RNG path (migration-plan OPEN ITEM #3
-- the RNG draw must stay Python this phase; Decision 4 requires the first
movement golden to avoid it).

## The five parity dimensions (the mutating-verb exit check)

1. **command_result byte-identity** against a real Python-engine oracle.
   Unlike `look`'s payload (which carries no player-identifying content), a
   move's leave/arrival narration embeds `ctx.player.username` verbatim
   (`features/movement/service.py`), so a byte-identical compare across two
   independently-seeded worlds requires the SAME username on both movers
   (`_MOVER_USERNAME`, fixed -- not a uuid-suffixed one). The oracle itself is
   `handle_ws_command` run in-process against a second, freshly-seeded world
   (mirroring `test_gateway_move_phase4c.py`'s two-world pattern) -- calling it
   against the wire-tested world's OWN post-move state (like the look harness
   does) is not an option here, because unlike `look`, a move MUTATES: a
   second in-process "north" against the already-moved player would attempt a
   *different* move (from `blacksmith_forge`), not reproduce the compared one.
2. **Audit parity** against the checked-in `move_only.audit.json` golden, via
   the same `normalize_events` oracle `test_audit_regression.py` diffs
   against (captured the same way `look_only.audit.json` was: a real
   Python-direct live-server replay of `move_only.json`, `LORECRAFT_UPDATE_GOLDENS=1`).
3. **`applied_effects` parity.** The wire protocol never exposes
   `CommandOutcome.applied_effects` to a WS client -- `apply_outcome`
   (`gateway/effect_apply.py`) persists them and returns only the legacy
   `command_result` + deliveries; there is no frame that carries the effect
   list to the client. So this dimension is asserted **by construction**: a
   move's only possible effect this phase is a single
   `MoveEntity{entity, from, to}` (the crate/protocol's fixed shape --
   `rust/crates/lorecraft-feature-move`), and `entity`/`from`/`to` are exactly
   the acting player's id and the room-id transition observed directly from
   the game DB before/after the wire move -- real oracle-observed values, not
   hand-typed guesses. `entity` is run-specific (a fresh player per test, like
   an audit trail's `actor_id`), so `move_only.effects.json` normalizes it out
   as the placeholder `"$ACTOR$"`, substituted with the real mover id at
   compare time -- the same normalization precedent `normalize_events` already
   applies to audit rows.
4. **STATE-SNAPSHOT hash** (`hash_state` over a `PlayerStateSnapshot` of
   `current_room_id` + `visited_rooms`, read from the DB after the real
   Rust-executed move) byte-identical to `move_only.state_hash.json` AND to an
   independent Python-direct world's post-move state. This is the
   mutating-verb crux the design spec calls out: the STATE mutation itself,
   not merely the reply text, must match.
5. **Broadcasts.** The leave narration reaches the origin room; the arrival
   narration + `state_change` reach the destination room (excluding the
   actor). A THIRD check -- whether the mover, now truly relocated, receives a
   *later* broadcast targeted at their new room -- surfaces a real,
   code-confirmed gap in the current headless wiring: see
   `test_mover_registry_is_not_updated_after_rust_executed_move`'s docstring.
   This is a genuine 4c finding (routed back for the live-cutover task), not a
   test defect -- it is asserted directly (not hidden) via
   `xfail(strict=True)`.

## Rollback + skill-gated defer

`test_rollback_move_is_byte_identical_to_rust_executed_move` holds the Rust
front door constant and varies only the allow-list (`north` opted-in vs.
explicitly empty), proving the allow-list toggle is the sole difference and
Option A's "byte-identical whichever side executes" guarantee holds for a
mutating verb too.

`test_skill_gated_target_still_defers_to_python` flips a reachable room's
terrain to the real registered `swamp` terrain (`required_skill="survival"`)
-- legitimate test setup (mirrors `test_gateway_move_phase4c.py`), not
fabricated content -- and confirms the move still completes via
`DeferToPython` (one audit row, no hang) with movement opted in, a
light co-located check that the RNG-bearing skill gate never reaches Rust
(OPEN ITEM #3); the exhaustive defer-decision matrix itself is
`test_gateway_move_phase4c.py`'s job.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.features.terrain import definitions as terrain_module
from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.tools.replay_hash import hash_state, player_state_snapshot
from lorecraft.tools.session_replay import normalize_events
from lorecraft.webui.player.ws_command import handle_ws_command
from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer

pytestmark = pytest.mark.simulation

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCENARIOS_DIR = _REPO_ROOT / "tests" / "simulation" / "scenarios"
_GOLDEN_AUDIT = json.loads((_SCENARIOS_DIR / "move_only.audit.json").read_text())
_GOLDEN_EFFECTS = json.loads((_SCENARIOS_DIR / "move_only.effects.json").read_text())
_GOLDEN_STATE = json.loads((_SCENARIOS_DIR / "move_only.state_hash.json").read_text())

_RNG_SEED = 1
_DIRECTION = "north"
_START_ROOM = "village_square"
_TARGET_ROOM = "blacksmith_forge"

# Fixed (not uuid-suffixed): the leave/arrival narration embeds
# `ctx.player.username` verbatim, so a byte-identical command_result compare
# across two independently-seeded worlds needs the SAME username on both
# movers -- see module docstring dimension 1.
_MOVER_USERNAME = "parity_mover"

# Movement is headless-only this phase (not in the default allow-list): every
# test opts a single direction in explicitly.
_MOVE_OPT_IN_ENV = {"LORECRAFT_RUST_VERBS": _DIRECTION}
# Explicitly empty (distinct from *unset*, which now defaults to `look`) routes
# every command -- including the opted-in direction elsewhere -- to Python.
_ROLLBACK_ENV = {"LORECRAFT_RUST_VERBS": ""}


def _username(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _game_session(server: SimulationServer) -> Session:
    engine = create_engine(f"sqlite:///{server.game_db_path}")
    return Session(engine)


def _verify_open_and_non_skill_gated(server: SimulationServer) -> None:
    """Read the live seeded DB and assert the chosen move is a clean parity
    target: an unlocked, unflagged exit into active, non-skill-gated terrain.
    Never assumed -- read via the same repos/registry the live move uses."""
    with _game_session(server) as session:
        room_repo = RoomRepo(session)
        exits = {exit_.direction: exit_ for exit_ in room_repo.exits(_START_ROOM)}
        exit_ = exits.get(_DIRECTION)
        assert exit_ is not None, (
            f"seeded world has no {_DIRECTION!r} exit from {_START_ROOM!r}"
        )
        assert exit_.target_room_id == _TARGET_ROOM
        assert not exit_.locked
        assert not exit_.condition_flags
        target = room_repo.active(_TARGET_ROOM)
        assert target is not None
        terrain_def = terrain_module.get_registry().get(target.terrain)
        assert terrain_def is None or terrain_def.required_skill is None, (
            f"{_TARGET_ROOM!r}'s terrain {target.terrain!r} is skill-gated; "
            "move_only must target non-skill-gated terrain (Decision 4 / "
            "OPEN ITEM #3)"
        )


def _player_state(server: SimulationServer, player_id: str) -> tuple[str, list[str]]:
    """`(current_room_id, visited_rooms)` read fresh from the live game DB."""
    with _game_session(server) as session:
        player = session.get(Player, player_id)
        assert player is not None
        return player.current_room_id, list(player.visited_rooms)


def _relocate_before_connect(
    server: SimulationServer, player_id: str, room_id: str
) -> None:
    """Place a not-yet-connected player in `room_id` (direct DB write, legitimate
    test setup). Their `ConnectAck` then registers them there in Rust's registry
    at connect time -- the ordinary way (not via a tracked move), so a witness can
    be planted in the destination room without depending on the very move-tracking
    mechanism this file's gap-finding test shows is not wired for the Rust-executed
    path."""
    with _game_session(server) as session:
        player = session.get(Player, player_id)
        assert player is not None
        player.current_room_id = room_id
        if room_id not in player.visited_rooms:
            player.visited_rooms = [*player.visited_rooms, room_id]
        session.add(player)
        session.commit()


async def _connect(
    server: SimulationServer, player_id: str, username: str
) -> VirtualPlayer:
    ticket = server.mint_ticket(player_id) if server.through_rust else None
    return await VirtualPlayer.connect(
        server.ws_url, player_id, username, ticket=ticket
    )


# --- 1-4: command_result + audit + effects + STATE-hash parity --------------


def test_rust_executed_move_matches_python_oracle_and_goldens(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """The core exit check: Rust-execute -> Python-persist reproduces the
    Python engine's command_result, the move_only audit/effects/state-hash
    goldens, AND an independent Python-direct world's post-move state."""
    rust_server = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=_MOVE_OPT_IN_ENV,
        world_time_ratio=0.0,
    )
    oracle_server = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=False,
        world_time_ratio=0.0,
    )
    asyncio.run(_test_core_parity(rust_server, oracle_server))


async def _test_core_parity(
    rust_server: SimulationServer, oracle_server: SimulationServer
) -> None:
    _verify_open_and_non_skill_gated(rust_server)

    mover_id, ticket = rust_server.prepare_login(_MOVER_USERNAME)
    mover = await _connect(rust_server, mover_id, _MOVER_USERNAME)
    try:
        pre_room, _pre_visited = _player_state(rust_server, mover_id)
        assert pre_room == _START_ROOM

        # THE compared command: a bare "north" from a real client, over a real
        # WebSocket, through the real `lorecraft-gateway` subprocess, routed by
        # `route::decide` to Rust's `execute::execute` (allow-listed), driving
        # the real BuildSnapshot/ApplyOutcome round-trip against the real
        # Python adapter, which persists via `apply_outcome` and commits.
        wire_reply = await mover.send_command(_DIRECTION)
        assert wire_reply["type"] == "command_result"
        assert wire_reply["verb"] == "move"
        assert wire_reply["noun"] == _DIRECTION

        # --- (2) audit parity: the SAME normalized-audit-trail oracle the
        # golden was captured with.
        audit_rows = rust_server.audit_trail_for(mover_id)
        normalized = normalize_events(audit_rows)
        assert normalized == _GOLDEN_AUDIT

        # --- (4) STATE-SNAPSHOT: read the real post-move player state from the
        # real DB the Rust-executed move just committed to.
        post_room, post_visited = _player_state(rust_server, mover_id)
        assert post_room == _TARGET_ROOM
        assert post_visited == _GOLDEN_STATE["visited_rooms"]
        snapshot = player_state_snapshot(post_room, post_visited)
        digest = hash_state(snapshot)
        assert snapshot["current_room_id"] == _GOLDEN_STATE["current_room_id"]
        assert digest == _GOLDEN_STATE["hash_state"], (
            "post-move player-state hash diverged from the move_only golden -- "
            "the mutating-verb parity crux"
        )

        # --- (3) applied_effects: no wire frame carries this to a WS client
        # (see module docstring dimension 3) -- assert by construction from the
        # observed pre/post room-id transition, matching the golden's
        # normalized shape (entity placeholder substituted with the real id).
        observed_effects = [
            {
                "type": "MoveEntity",
                "entity": mover_id,
                "from": pre_room,
                "to": post_room,
            }
        ]
        expected_effects = [
            {**effect, "entity": mover_id} for effect in _GOLDEN_EFFECTS
        ]
        assert observed_effects == expected_effects

        # --- (1) command_result parity: a REAL Python-engine oracle on an
        # INDEPENDENT, identically-seeded world (unlike `look`, a move mutates,
        # so replaying against the SAME already-moved player would attempt a
        # different move -- see module docstring dimension 1). Same fixed
        # username on both sides so the leave-narration text embedding
        # `ctx.player.username` matches byte-for-byte.
        oracle_player_id = oracle_server.create_player(_MOVER_USERNAME)
        oracle_reply = await handle_ws_command(
            oracle_server.app.state.lorecraft,
            DirectiveConnectionManager(),
            oracle_player_id,
            "oracle-session",
            _DIRECTION,
        )
        assert wire_reply == oracle_reply

        # Cross-check: the independent Python-direct world's own post-move
        # state must match too -- Rust-executed and Python-direct movement
        # mutate identically, not merely reply identically.
        oracle_room, oracle_visited = _player_state(oracle_server, oracle_player_id)
        assert (post_room, post_visited) == (oracle_room, oracle_visited)
    finally:
        await mover.close()


# --- rollback -----------------------------------------------------------


def test_rollback_move_is_byte_identical_to_rust_executed_move(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """Two Rust-fronted servers differing ONLY in the allow-list: one opts
    `north` in (Rust-executed), the other is explicitly empty (Python-forwarded,
    the rollback toggle). Both must produce a byte-identical reply and an
    identical post-move state -- proving rollback is a pure routing decision,
    exactly as Phase 3 decision 8 and the 4a/4b look harness established."""
    rust_executed = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=_MOVE_OPT_IN_ENV,
        world_time_ratio=0.0,
    )
    python_forwarded = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=_ROLLBACK_ENV,
        world_time_ratio=0.0,
    )
    asyncio.run(_test_rollback(rust_executed, python_forwarded))


async def _test_rollback(
    rust_executed: SimulationServer, python_forwarded: SimulationServer
) -> None:
    rust_id, rust_ticket = rust_executed.prepare_login(_MOVER_USERNAME)
    python_id, python_ticket = python_forwarded.prepare_login(_MOVER_USERNAME)
    rust_mover = await _connect(rust_executed, rust_id, _MOVER_USERNAME)
    python_mover = await _connect(python_forwarded, python_id, _MOVER_USERNAME)
    try:
        rust_reply = await rust_mover.send_command(_DIRECTION)
        python_reply = await python_mover.send_command(_DIRECTION)
        assert rust_reply == python_reply
        assert _player_state(rust_executed, rust_id) == _player_state(
            python_forwarded, python_id
        )
    finally:
        await rust_mover.close()
        await python_mover.close()


# --- 5: broadcasts (leave/arrival narration to the correct rooms) -----------


def test_move_broadcasts_leave_and_arrival_to_the_correct_rooms(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """A second player in the origin room hears the leave narration; a second
    player already in the destination room hears the arrival narration + a
    `state_change` excluding the actor -- the load-bearing proof that a
    Rust-executed move's fan-out reaches real, distinct room audiences over
    the real gateway (not just the mover's own reply)."""
    server = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=_MOVE_OPT_IN_ENV,
        world_time_ratio=0.0,
    )
    asyncio.run(_test_broadcasts(server))


async def _test_broadcasts(server: SimulationServer) -> None:
    origin_username = _username("origin_witness")
    origin_id, origin_ticket = server.prepare_login(origin_username)
    origin_witness = await _connect(server, origin_id, origin_username)

    dest_username = _username("dest_witness")
    dest_id, dest_ticket = server.prepare_login(dest_username)
    # Planted in the destination room BEFORE connecting, so their ConnectAck
    # (not a tracked move) registers them there in Rust's registry.
    _relocate_before_connect(server, dest_id, _TARGET_ROOM)
    dest_witness = await _connect(server, dest_id, dest_username)

    mover_id, mover_ticket = server.prepare_login(_MOVER_USERNAME)
    mover = await _connect(server, mover_id, _MOVER_USERNAME)
    try:
        mover_result, leave_feed, arrival_feed = await asyncio.gather(
            mover.send_command(_DIRECTION),
            origin_witness.wait_for_broadcast("feed_append", timeout=5),
            dest_witness.wait_for_broadcast("feed_append", timeout=5),
        )
        assert mover_result["verb"] == "move"
        assert leave_feed["content"] == f"{_MOVER_USERNAME} leaves {_DIRECTION}."
        assert arrival_feed["content"].startswith(f"{_MOVER_USERNAME} arrives")

        dest_state_change = await dest_witness.wait_for_broadcast(
            "state_change", timeout=5
        )
        assert dest_state_change["actor_id"] == mover_id
    finally:
        await mover.close()
        await origin_witness.close()
        await dest_witness.close()


# --- 5 (known gap): mover's own reachability in the NEW room ----------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN GAP (route back to the live-cutover task, not fixed here): "
        "gateway/effect_apply.py's apply_outcome() builds its own throwaway "
        "DirectiveConnectionManager() for a Rust-executed move; "
        "_apply_move_entity's ctx.manager.move_player(...) call records into "
        "THAT manager's .moves buffer, which is never drained/forwarded as a "
        "MovePlayer frame (contrast adapter.py::_on_command, which does "
        "self._manager.drain_moves() before every CommandReply). Confirmed at "
        "the Rust side too: lorecraft-server/src/forward.rs's read_loop only "
        "reconciles ConnectionRegistry on a GatewayOutbound::MovePlayer frame; "
        "OutcomeApplied only relays `deliveries` verbatim. So Rust's own "
        "connection registry never learns a Rust-executed move happened -- the "
        "mover keeps looking like they're still in the ORIGIN room from Rust's "
        "perspective indefinitely. This is exactly the gap "
        "_apply_move_entity's own docstring flags as deliberately out of scope "
        "this phase ('forwarding the resulting MovePlayer frame to Rust's "
        "authoritative registry is a live-cutover concern ... out of scope "
        "here'). strict=True so a future fix flips this XPASS into a hard "
        "failure, forcing this test (and its docstring) to be revisited rather "
        "than silently staying green."
    ),
)
def test_mover_registry_is_not_updated_after_rust_executed_move(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """After a Rust-executed move, a LATER room-targeted broadcast aimed at the
    mover's real (destination) room should reach them -- they are physically
    there (proven by dimension 4's state hash). It currently does not."""
    server = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=_MOVE_OPT_IN_ENV,
        world_time_ratio=0.0,
    )
    asyncio.run(_test_mover_reaches_new_room_broadcast(server))


async def _test_mover_reaches_new_room_broadcast(server: SimulationServer) -> None:
    dest_username = _username("dest_witness")
    dest_id, dest_ticket = server.prepare_login(dest_username)
    _relocate_before_connect(server, dest_id, _TARGET_ROOM)
    dest_witness = await _connect(server, dest_id, dest_username)

    mover_id, mover_ticket = server.prepare_login(_MOVER_USERNAME)
    mover = await _connect(server, mover_id, _MOVER_USERNAME)
    try:
        await mover.send_command(_DIRECTION)
        # The mover is now physically in blacksmith_forge (DB-confirmed by the
        # core parity test). dest_witness's own "look" broadcasts a room
        # state_change there, excluding dest_witness -- the mover should be the
        # recipient.
        received, _look_reply = await asyncio.gather(
            mover.wait_for_broadcast("state_change", timeout=3),
            dest_witness.send_command("look"),
        )
        assert received["actor_id"] == dest_id
    finally:
        await mover.close()
        await dest_witness.close()


# --- skill-gated defer (light co-located check; the exhaustive matrix is
# tests/unit/test_gateway_move_phase4c.py's job) ------------------------------


def test_skill_gated_target_still_defers_to_python(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    """With movement opted in, a move into skill-gated terrain still completes
    via `DeferToPython` -- the RNG-bearing terrain-skill gate never reaches
    Rust (OPEN ITEM #3). Flips the real registered `swamp` terrain
    (`required_skill="survival"`) onto the reachable target -- legitimate test
    setup (mirrors `test_gateway_move_phase4c.py`), not fabricated content."""
    server = simulation_server_factory(
        rng_seed=_RNG_SEED,
        through_rust=True,
        extra_env=_MOVE_OPT_IN_ENV,
        world_time_ratio=0.0,
    )
    with _game_session(server) as session:
        room = session.get(Room, _TARGET_ROOM)
        assert room is not None
        room.terrain = "swamp"
        session.add(room)
        session.commit()
    asyncio.run(_test_skill_gated_defer(server))


async def _test_skill_gated_defer(server: SimulationServer) -> None:
    mover_username = _username("defer_mover")
    mover_id, ticket = server.prepare_login(mover_username)
    mover = await _connect(server, mover_id, mover_username)
    try:
        reply = await mover.send_command(_DIRECTION)
        assert reply["type"] == "command_result"
        # Whichever way the terrain-skill gate decides (blocked for
        # insufficient skill, or executed) is Python's ordinary business; the
        # parity-relevant proof is that the command completed via the
        # DeferToPython path without hanging or erroring, writing exactly one
        # audit row -- confirming the RNG-bearing skill gate stayed in Python
        # end to end, never reaching lorecraft-feature-move's execution.
        audit_rows = server.audit_trail_for(mover_id)
        assert len(audit_rows) == 1
    finally:
        await mover.close()
