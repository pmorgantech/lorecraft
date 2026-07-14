"""Phase 4c — Python persistence for Rust-executed movement (Option A).

Covers the four halves of the movement round-trip whose authoritative source is
``src/lorecraft/features/movement/service.py``:

- ``build_move_request`` materializes the documented move-snapshot attribute
  contract (``lorecraft-feature-move``'s module docs), reusing the live move's
  own repo/registry reads so it can't drift.
- The ``MoveEntity`` effect-applier + ``apply_outcome`` reproduce the live move's
  state mutation, its queued ``PLAYER_MOVED`` (flushed before commit), its
  leave/arrival room deliveries, and its ``command_executed`` audit row —
  asserted byte-for-byte against the pure-Python ``handle_ws_command`` path on an
  identically-seeded second world.
- A skill-gated target defers to Python (``DeferToPython``) so its ``record_use``
  RNG draw never enters Rust (migration-plan OPEN ITEM #3).
- ``flush_events`` runs the queued ``PLAYER_MOVED`` handlers *before* the commit,
  so a reaction's state mutation is persisted in the same transaction.

No world content is hardcoded: the traversable direction is discovered from the
seeded world, and the skill-gated case flips a *real* registered terrain
(``swamp``) on a reachable room in the test DB rather than authoring fake content.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from lorecraft.config import Settings
from lorecraft.engine.game.events import Event, GameEvent
from lorecraft.engine.game.grammar import OPPOSITE_DIRECTIONS
from lorecraft.engine.game.holders import Location
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.features.terrain import definitions as terrain_module
from lorecraft.gateway.adapter import GatewayAdapter
from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.gateway.effect_apply import apply_outcome
from lorecraft.gateway.snapshots import build_move_request, move_target_is_skill_gated
from lorecraft.main import create_app
from lorecraft.protocol import PROTOCOL_VERSION, EntitySnapshot, ScriptBudget
from lorecraft.protocol.effects import MoveEntity
from lorecraft.protocol.envelope import CommandEnvelope, CommandOutcome, OutcomeStatus
from lorecraft.protocol.gateway import BuildSnapshot, DeferToPython, SnapshotReady
from lorecraft.protocol.messages import Feed, PanelUpdate
from lorecraft.protocol.script import ScriptRequest
from lorecraft.state import AppState
from lorecraft.types import JsonValue
from lorecraft.webui.player.ws_command import handle_ws_command

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYER_ID = "player-1"


def _settings_in(base: Path) -> Settings:
    """A settings object rooted at ``base`` (its own DBs + content mirrors)."""
    base.mkdir(parents=True, exist_ok=True)
    return Settings(
        database_path=str(base / "game.db"),
        audit_database_path=str(base / "audit.db"),
        world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
        issues_yaml_path=str(base / "issues.yaml"),
        news_yaml_path=str(base / "news.yaml"),
        help_yaml_path=str(base / "help_topics.yaml"),
        admin_jwt_secret="test-admin-secret-at-least-32-bytes!!",
        seed_player_id=PLAYER_ID,
        seed_player_username=PLAYER_ID,
        # Frozen clock (ratio 0) => the `time` panel is identical across worlds, so
        # a two-world reply compare isn't clock-flaky.
        world_time_ratio=0.0,
        gateway_socket_path=str(base / "gateway.sock"),
    )


@pytest.fixture
def state(tmp_path: Path) -> Iterator[AppState]:
    app = create_app(settings=_settings_in(tmp_path / "primary"))
    with TestClient(app):
        yield app.state.lorecraft


def _make_state(stack: contextlib.ExitStack, base: Path) -> AppState:
    """Boot a second, independently-seeded world under ``base`` for parity."""
    app = create_app(settings=_settings_in(base))
    stack.enter_context(TestClient(app))
    return app.state.lorecraft


def _envelope(session_id: str, command_id: str, raw: str) -> CommandEnvelope:
    return CommandEnvelope(
        protocol_version=PROTOCOL_VERSION,
        world_id="world",
        actor_id=PLAYER_ID,
        player_id=PLAYER_ID,
        session_id=session_id,
        command_id=command_id,
        receive_sequence=1,
        deadline_ms=1000,
        raw=raw,
    )


def _pick_open_move(state: AppState) -> tuple[str, str, str]:
    """First traversable, non-skill-gated exit from the seed player's room.

    Returns ``(direction, start_room_id, target_room_id)``, discovered from the
    seeded world — never a hardcoded direction.
    """
    with Session(state.game_engine) as session:
        room_repo = RoomRepo(session)
        player = PlayerRepo(session).get(PLAYER_ID)
        assert player is not None
        registry = terrain_module.get_registry()
        for exit_ in room_repo.exits(player.current_room_id):
            if exit_.locked or exit_.condition_flags:
                continue
            target = room_repo.active(exit_.target_room_id)
            if target is None:
                continue
            terrain_def = registry.get(target.terrain)
            if terrain_def is not None and terrain_def.required_skill is not None:
                continue
            return exit_.direction, player.current_room_id, exit_.target_room_id
    raise AssertionError("seed world has no open exit from the start room")


def _move_outcome(
    command_id: str, direction: str, start: str, target: str
) -> CommandOutcome:
    """The outcome Rust's ``move_effects`` derives for a valid, non-gated move —
    hand-built here to match the crate byte-for-byte (feed + room_id panel, the
    single ``MoveEntity``, and the leave/arrival narration)."""
    opposite = OPPOSITE_DIRECTIONS[direction]
    return CommandOutcome(
        command_id=command_id,
        status=OutcomeStatus.EXECUTED,
        messages=[
            Feed(text=f"You go {direction}.", message_type="system"),
            PanelUpdate(key="room_id", value=target),
        ],
        applied_effects=[MoveEntity(entity=PLAYER_ID, from_=start, to=target)],
        room_narration=[f"{PLAYER_ID} leaves {direction}."],
        arrival_narration=[f"{PLAYER_ID} arrives from the {opposite}."],
    )


def _player_room_and_visited(state: AppState) -> tuple[str, list[str]]:
    with Session(state.game_engine) as session:
        player = PlayerRepo(session).get(PLAYER_ID)
        assert player is not None
        return player.current_room_id, list(player.visited_rooms)


def _command_executed_rows(state: AppState) -> list[AuditEvent]:
    with Session(state.audit_engine) as session:
        return list(
            session.exec(
                select(AuditEvent).where(
                    AuditEvent.event_type == GameEvent.COMMAND_EXECUTED.value
                )
            ).all()
        )


# --- build_move_request contract --------------------------------------------


def test_build_move_request_matches_service_reads(state: AppState) -> None:
    """`build_move_request` populates the documented snapshot contract, and its
    exits map equals what the live move's own repo/registry reads produce — proof
    the snapshot can't drift from the move it feeds."""
    direction, start, _target = _pick_open_move(state)
    request = build_move_request(state, _envelope("s", "c", f"move {direction}"))

    assert request.script_id == "movement"
    assert request.command_or_event == "move"
    assert request.room_snapshot.id == start
    assert request.actor_snapshot.id == PLAYER_ID
    assert request.actor_snapshot.attributes["username"] == PLAYER_ID

    # Recompute the expected exits map independently via the same repos the live
    # MovementService.move reads, then assert build_move_request wired every field.
    with Session(state.game_engine) as session:
        room_repo = RoomRepo(session)
        stack_repo = StackRepo(session)
        player = PlayerRepo(session).get(PLAYER_ID)
        assert player is not None
        registry = terrain_module.get_registry()
        expected: dict[str, object] = {}
        for exit_ in room_repo.exits(start):
            target_room = room_repo.active(exit_.target_room_id)
            required_skill = None
            if target_room is not None:
                terrain_def = registry.get(target_room.terrain)
                if terrain_def is not None:
                    required_skill = terrain_def.required_skill
            has_key = exit_.key_item_id is not None and (
                stack_repo.quantity_of(Location("player", PLAYER_ID), exit_.key_item_id)
                > 0
            )
            expected[exit_.direction] = {
                "target_room_id": exit_.target_room_id,
                "target_active": target_room is not None,
                "locked": exit_.locked,
                "key_item_id": exit_.key_item_id,
                "actor_has_key": has_key,
                "condition_flags": list(exit_.condition_flags),
                "target_required_skill": required_skill,
            }
        expected_flags = dict(player.flags)

    assert request.room_snapshot.attributes["exits"] == expected
    assert request.actor_snapshot.attributes["flags"] == expected_flags
    # The moved direction's open exit is present and ungated (so Rust executes it).
    assert move_target_is_skill_gated(request, direction) is False


# --- MoveEntity applier: state mutation + PLAYER_MOVED + deliveries + audit ---


def test_move_outcome_matches_python_direct_move(tmp_path: Path) -> None:
    """Driving a synthetic move outcome through `apply_outcome` (the Rust path)
    yields byte-identical state mutation, deliveries, direct reply, PLAYER_MOVED,
    and command_executed audit fields to the pure-Python `handle_ws_command` move
    on an identically-seeded world."""
    with contextlib.ExitStack() as stack:
        rust_state = _make_state(stack, tmp_path / "rust")
        direct_state = _make_state(stack, tmp_path / "direct")

        direction, start, target = _pick_open_move(rust_state)

        # Record PLAYER_MOVED on both worlds' buses (flush_events must fire it).
        rust_events: list[Event] = []
        direct_events: list[Event] = []
        rust_state.bus.on(
            GameEvent.PLAYER_MOVED, lambda event, ctx: rust_events.append(event)
        )
        direct_state.bus.on(
            GameEvent.PLAYER_MOVED, lambda event, ctx: direct_events.append(event)
        )

        # Python-direct baseline: the manager captures the same fan-out apply_outcome
        # returns, so the deliveries are directly comparable.
        direct_manager = DirectiveConnectionManager()
        direct_reply = asyncio.run(
            handle_ws_command(
                direct_state, direct_manager, PLAYER_ID, "sd", f"move {direction}"
            )
        )
        direct_deliveries = direct_manager.drain()

        # Rust path: apply the outcome Rust would have derived.
        outcome = _move_outcome("cm", direction, start, target)
        rust_reply, rust_deliveries, rust_moves = asyncio.run(
            apply_outcome(
                rust_state, _envelope("sr", "cm", f"move {direction}"), outcome
            )
        )

        # 4c cutover: a Rust-executed move now returns the registry reconciliation
        # so the adapter can forward it on `OutcomeApplied` (gap-1 for the
        # Rust-execute path). One move, from the origin room to the target.
        assert len(rust_moves) == 1
        assert rust_moves[0].player_id == PLAYER_ID
        assert rust_moves[0].from_room == start
        assert rust_moves[0].to_room == target

        # State mutation: both worlds moved the player identically.
        assert _player_room_and_visited(rust_state) == _player_room_and_visited(
            direct_state
        )
        assert _player_room_and_visited(rust_state)[0] == target

        # The direct reply (command_result) is byte-identical.
        assert rust_reply == direct_reply
        # ...and reflects a move: verb/noun + the leave narration in room_messages.
        assert rust_reply["verb"] == "move"
        assert rust_reply["noun"] == direction
        assert rust_reply["room_messages"] == [f"{PLAYER_ID} leaves {direction}."]

        # Deliveries: leave -> origin room, arrival -> destination, + state_changes.
        assert [d.to_json() for d in rust_deliveries] == [
            d.to_json() for d in direct_deliveries
        ]

        # PLAYER_MOVED fired through flush_events with the same payload both ways.
        assert len(rust_events) == 1
        assert rust_events[0].payload == direct_events[0].payload
        assert rust_events[0].payload == {
            "player_id": PLAYER_ID,
            "from_room_id": start,
            "to_room_id": target,
            "direction": direction,
        }

        # command_executed audit: exactly one row each, identical canonical fields
        # (timing is non-deterministic and intentionally omitted Rust-side).
        (rust_audit,) = _command_executed_rows(rust_state)
        (direct_audit,) = _command_executed_rows(direct_state)
        assert rust_audit.summary == direct_audit.summary
        assert rust_audit.summary == f"Command executed: move {direction}"
        for key in ("verb", "raw", "noun"):
            assert rust_audit.payload_json[key] == direct_audit.payload_json[key]
        assert rust_audit.payload_json["verb"] == "move"
        # duration_ms/perf are Python-direct timing only; the Rust-persist audit
        # omits them (documented) — confirm they are the sole difference.
        assert "duration_ms" not in rust_audit.payload_json
        assert "duration_ms" in direct_audit.payload_json


# --- skill-gated defer -------------------------------------------------------


def _synthetic_request(required_skill: str | None) -> ScriptRequest:
    """A minimal move snapshot with a single north exit carrying ``required_skill``."""
    north_exit: JsonValue = {"target_required_skill": required_skill}
    exits: JsonValue = {"north": north_exit}
    room_attrs: dict[str, JsonValue] = {"exits": exits}
    return ScriptRequest(
        api_version=PROTOCOL_VERSION,
        script_id="movement",
        script_version=1,
        command_or_event="move",
        actor_snapshot=EntitySnapshot(id=PLAYER_ID, kind="player", attributes={}),
        room_snapshot=EntitySnapshot(id="here", kind="room", attributes=room_attrs),
        selected_related_entities=[],
        logical_time=0,
        rng_stream_id="",
        capability_set=[],
        budget=ScriptBudget(wall_ms=0, instructions=0, memory_bytes=0, output_bytes=0),
    )


def test_move_target_is_skill_gated_decision_matrix() -> None:
    """The defer predicate: gated only when the moved direction's exit exists and
    its target terrain carries a required skill."""
    gated = _synthetic_request("survival")
    open_ = _synthetic_request(None)
    assert move_target_is_skill_gated(gated, "north") is True
    assert move_target_is_skill_gated(open_, "north") is False
    assert move_target_is_skill_gated(gated, "south") is False  # no exit that way
    assert move_target_is_skill_gated(gated, None) is False


def test_build_snapshot_defers_skill_gated_move(
    state: AppState, tmp_path: Path
) -> None:
    """`_on_build_snapshot` for a move into skill-gated terrain returns
    `DeferToPython` (RNG stays Python) and executes/mutates nothing."""
    direction, _start, target = _pick_open_move(state)
    # Flip the *real* registered `swamp` terrain (required_skill="survival") onto
    # the reachable target so the move becomes skill-gated — legitimate test setup,
    # not authored fake content.
    with Session(state.game_engine) as session:
        room = session.get(Room, target)
        assert room is not None
        room.terrain = "swamp"
        session.add(room)
        session.commit()

    before = _player_room_and_visited(state)
    adapter = GatewayAdapter(state, socket_path=str(tmp_path / "gw.sock"))
    envelope = _envelope("sg", "c-gated", f"move {direction}")
    (frame,) = asyncio.run(adapter.handle_inbound(BuildSnapshot(envelope=envelope)))

    assert isinstance(frame, DeferToPython)
    assert frame.command_id == "c-gated"
    # No pending entry (no correlated ApplyOutcome will come) and no mutation.
    assert envelope.command_id not in adapter._pending  # pyright: ignore[reportPrivateUsage]
    assert _player_room_and_visited(state) == before


def test_build_snapshot_open_move_returns_snapshot_ready(
    state: AppState, tmp_path: Path
) -> None:
    """A non-gated move builds a `SnapshotReady` (Rust executes it) and remembers
    the envelope for the correlated `ApplyOutcome`."""
    direction, _start, _target = _pick_open_move(state)
    adapter = GatewayAdapter(state, socket_path=str(tmp_path / "gw.sock"))
    envelope = _envelope("so", "c-open", f"move {direction}")
    (frame,) = asyncio.run(adapter.handle_inbound(BuildSnapshot(envelope=envelope)))

    assert isinstance(frame, SnapshotReady)
    assert frame.command_id == "c-open"
    assert frame.request.command_or_event == "move"
    assert adapter._pending[envelope.command_id] is envelope  # pyright: ignore[reportPrivateUsage]


# --- flush_events runs before commit ----------------------------------------


def test_player_moved_reaction_is_flushed_before_commit(state: AppState) -> None:
    """A PLAYER_MOVED handler that mutates state runs *before* the game commit, so
    its mutation is persisted — mirroring engine.py step 9 (flush) -> 10 (commit).
    Without the pre-commit flush the reaction's write would be discarded."""
    direction, start, target = _pick_open_move(state)

    def react(event: Event, ctx: object) -> None:
        # Reassign (not mutate-in-place) so SQLModel flags the JSON column dirty.
        player = ctx.player  # type: ignore[attr-defined]
        player.flags = {**player.flags, "moved_reaction": True}

    state.bus.on(GameEvent.PLAYER_MOVED, react)

    outcome = _move_outcome("cf", direction, start, target)
    asyncio.run(
        apply_outcome(state, _envelope("sf", "cf", f"move {direction}"), outcome)
    )

    # Re-read from a fresh session: the reaction's flag survived the commit.
    with Session(state.game_engine) as session:
        player = PlayerRepo(session).get(PLAYER_ID)
        assert player is not None
        assert player.flags.get("moved_reaction") is True
        assert player.current_room_id == target
