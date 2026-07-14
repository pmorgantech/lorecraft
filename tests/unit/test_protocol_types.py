"""Unit tests for the Python protocol mirror (`lorecraft.protocol`).

The load-bearing checks here are the JSON *shape* assertions on `Effect` and
`OutboundMessage` variants: their serialized form must byte-match what the Rust
`#[serde(tag = "type")]` enums emit, since the two are hand-kept in agreement.
"""

from __future__ import annotations

import dataclasses
import json

from lorecraft.protocol import (
    AdjustMeter,
    AdminAuthResult,
    AdminTarget,
    ApplyOutcome,
    AuthResult,
    BuildSnapshot,
    ClientClose,
    CommandEnvelope,
    CommandOutcome,
    CommandReply,
    ConnectAck,
    Connected,
    DeferToPython,
    Deliver,
    DeliveryDirective,
    Diagnostic,
    Disconnected,
    EmitEvent,
    EmittedEvent,
    EntitySnapshot,
    ExecutionRejected,
    Feed,
    GatewayCommand,
    GlobalTarget,
    GracefulQuit,
    MoveEntity,
    MovePlayer,
    OutcomeApplied,
    OutcomeStatus,
    PanelUpdate,
    PlayerTarget,
    RedeemTicket,
    RoomTarget,
    ScheduledWork,
    ScriptBudget,
    ScriptRequest,
    ScriptResult,
    SendNarration,
    SetFlag,
    SnapshotReady,
    TransferItem,
    ValidateAdminToken,
    delivery_target_from_json,
    disconnect_reason_from_json,
    effect_from_json,
    gateway_inbound_from_json,
    gateway_outbound_from_json,
    message_from_json,
)


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def test_entity_snapshot_holds_arbitrary_json_attributes() -> None:
    snap = EntitySnapshot(
        id="tavern",
        kind="room",
        attributes={
            "name": "Tavern",
            "exits": ["north", "south"],
            "nested": {"a": [1, 2, {"b": True}]},
            "nullable": None,
        },
    )
    dumped = dataclasses.asdict(snap)
    assert _canonical(dumped) == _canonical(dumped)  # stable
    assert dumped["attributes"]["nested"] == {"a": [1, 2, {"b": True}]}


def test_command_envelope_roundtrips_via_asdict() -> None:
    env = CommandEnvelope(
        protocol_version=1,
        world_id="world-1",
        actor_id="actor-1",
        player_id="player-1",
        session_id="session-1",
        command_id="cmd-1",
        receive_sequence=42,
        deadline_ms=5000,
        raw="look",
    )
    dumped = dataclasses.asdict(env)
    assert dumped["world_id"] == "world-1"  # bare string, matches serde(transparent)
    assert _canonical(dumped) == _canonical(json.loads(_canonical(dumped)))


def test_script_request_and_result_construct_and_dump() -> None:
    request = ScriptRequest(
        api_version=1,
        script_id="look",
        script_version=1,
        command_or_event="look",
        actor_snapshot=EntitySnapshot(id="p", kind="player", attributes={}),
        room_snapshot=EntitySnapshot(
            id="tavern", kind="room", attributes={"name": "Tavern"}
        ),
        selected_related_entities=[
            EntitySnapshot(id="sword", kind="item", attributes={"name": "Old Sword"})
        ],
        logical_time=7,
        rng_stream_id="s1",
        capability_set=["read"],
        budget=ScriptBudget(
            wall_ms=50, instructions=100000, memory_bytes=1048576, output_bytes=65536
        ),
    )
    assert dataclasses.asdict(request)["budget"]["wall_ms"] == 50

    result = ScriptResult(
        messages=[Feed(text="Tavern", message_type="system")],
        emitted_events=[EmittedEvent(event_type="looked", payload={"room": "tavern"})],
        scheduled_work=[ScheduledWork(job_id="j1", due_logical_time=99, payload=None)],
        diagnostics=[Diagnostic(level="info", message="ok")],
    )
    assert result.proposed_effects == []
    assert dataclasses.asdict(result)["messages"][0]["text"] == "Tavern"


def test_command_outcome_defaults() -> None:
    outcome = CommandOutcome(command_id="cmd-1", status=OutcomeStatus.EXECUTED)
    assert outcome.messages == []
    assert outcome.applied_effects == []
    assert outcome.room_narration == []
    assert outcome.arrival_narration == []
    # str-enum serializes to the Rust variant name.
    assert outcome.status.value == "Executed"
    assert _canonical({"status": outcome.status.value}) == '{"status":"Executed"}'


def test_command_outcome_omits_empty_narration_on_wire() -> None:
    # A read-only/blocked outcome with no room-directed narration must not emit the
    # additive fields, so its wire shape stays byte-identical to before they existed
    # (mirrors the Rust `skip_serializing_if = "Vec::is_empty"`).
    dumped = CommandOutcome(command_id="cmd-1", status=OutcomeStatus.EXECUTED).to_json()
    assert "room_narration" not in dumped
    assert "arrival_narration" not in dumped


def test_command_outcome_roundtrips_room_and_arrival_narration() -> None:
    # A move carries one origin-room line and one destination-room line; both must
    # survive the JSON round trip and appear on the wire.
    outcome = CommandOutcome(
        command_id="cmd-2",
        status=OutcomeStatus.EXECUTED,
        applied_effects=[MoveEntity(entity="player-1", from_="a", to="b")],
        room_narration=["alice leaves north."],
        arrival_narration=["alice arrives from the south."],
    )
    dumped = outcome.to_json()
    assert dumped["room_narration"] == ["alice leaves north."]
    assert dumped["arrival_narration"] == ["alice arrives from the south."]
    assert CommandOutcome.from_json(dumped) == outcome
    # A legacy outcome missing both keys deserializes with empty narration lists.
    legacy = {
        "command_id": "cmd-3",
        "status": "Executed",
        "commit_sequence": None,
        "messages": [],
        "applied_effects": [],
        "diagnostics": [],
    }
    restored = CommandOutcome.from_json(legacy)
    assert restored.room_narration == []
    assert restored.arrival_narration == []


# --- Effect wire-shape parity (matches Rust #[serde(tag = "type")]) ---


def test_send_narration_matches_rust_wire_shape() -> None:
    effect = SendNarration(text="x", message_type="feed")
    assert effect.to_json() == {
        "type": "SendNarration",
        "text": "x",
        "message_type": "feed",
    }
    assert _canonical(effect.to_json()) == (
        '{"message_type":"feed","text":"x","type":"SendNarration"}'
    )


def test_move_entity_renames_from_field_on_wire() -> None:
    effect = MoveEntity(entity="e", from_="a", to="b")
    assert effect.to_json() == {
        "type": "MoveEntity",
        "entity": "e",
        "from": "a",
        "to": "b",
    }


def test_every_effect_variant_roundtrips_through_json() -> None:
    variants = [
        MoveEntity(entity="e", from_="a", to="b"),
        TransferItem(item="coin", from_="room", to="player", quantity=2),
        AdjustMeter(entity="p", meter="health", delta=-5),
        SetFlag(entity="p", key="seen", value=True),
        EmitEvent(event_type="boom", payload={"n": 1}),
        SendNarration(text="hi", message_type="feed"),
    ]
    for effect in variants:
        rebuilt = effect_from_json(effect.to_json())
        assert rebuilt == effect


def test_transfer_item_json_shape() -> None:
    effect = TransferItem(item="coin", from_="room", to="player", quantity=2)
    assert effect.to_json() == {
        "type": "TransferItem",
        "item": "coin",
        "from": "room",
        "to": "player",
        "quantity": 2,
    }


# --- OutboundMessage wire-shape parity ---


def test_feed_matches_rust_wire_shape() -> None:
    msg = Feed(text="hi", message_type="system")
    assert msg.to_json() == {"type": "Feed", "text": "hi", "message_type": "system"}


def test_panel_update_matches_rust_wire_shape() -> None:
    msg = PanelUpdate(key="room_id", value="tavern")
    assert msg.to_json() == {
        "type": "PanelUpdate",
        "key": "room_id",
        "value": "tavern",
    }


def test_outbound_message_roundtrips_through_json() -> None:
    for msg in (Feed(text="hi", message_type="system"), PanelUpdate(key="k", value=3)):
        assert message_from_json(msg.to_json()) == msg


# --- Container recursive to_json/from_json round-trips (Rust-port Phase 2) ---
#
# These exercise the container types' *recursive* serialization: a naive
# `dataclasses.asdict()` would drop the nested `{"type": ...}` discriminator on
# `Effect`/`OutboundMessage` variants and mangle the `from`/`from_` wire-key
# rename. The Rust `lorecraft-protocol` crate consumes these exact shapes, so
# round-trip fidelity is the cross-language contract.


def _sample_snapshot() -> EntitySnapshot:
    return EntitySnapshot(
        id="tavern",
        kind="room",
        attributes={"name": "Tavern", "exits": ["north"], "nested": {"a": [1, True]}},
    )


def test_entity_snapshot_roundtrips() -> None:
    snap = _sample_snapshot()
    assert EntitySnapshot.from_json(snap.to_json()) == snap


def test_diagnostic_roundtrips() -> None:
    diag = Diagnostic(level="warning", message="something")
    assert Diagnostic.from_json(diag.to_json()) == diag


def test_command_envelope_roundtrips_recursively() -> None:
    env = CommandEnvelope(
        protocol_version=1,
        world_id="world-1",
        actor_id="actor-1",
        player_id="player-1",
        session_id="session-1",
        command_id="cmd-1",
        receive_sequence=42,
        deadline_ms=5000,
        raw="look",
    )
    assert CommandEnvelope.from_json(env.to_json()) == env


def test_script_budget_roundtrips() -> None:
    budget = ScriptBudget(
        wall_ms=50, instructions=100000, memory_bytes=1048576, output_bytes=65536
    )
    assert ScriptBudget.from_json(budget.to_json()) == budget


def test_emitted_event_and_scheduled_work_roundtrip() -> None:
    event = EmittedEvent(event_type="looked", payload={"room": "tavern"})
    work = ScheduledWork(job_id="j1", due_logical_time=99, payload=None)
    assert EmittedEvent.from_json(event.to_json()) == event
    assert ScheduledWork.from_json(work.to_json()) == work


def test_script_request_roundtrips_with_nested_snapshots() -> None:
    request = ScriptRequest(
        api_version=1,
        script_id="look",
        script_version=1,
        command_or_event="look",
        actor_snapshot=EntitySnapshot(id="p", kind="player", attributes={}),
        room_snapshot=_sample_snapshot(),
        selected_related_entities=[
            EntitySnapshot(id="sword", kind="item", attributes={"name": "Old Sword"})
        ],
        logical_time=7,
        rng_stream_id="s1",
        capability_set=["read"],
        budget=ScriptBudget(
            wall_ms=50, instructions=100000, memory_bytes=1048576, output_bytes=65536
        ),
    )
    assert ScriptRequest.from_json(request.to_json()) == request


def test_script_result_roundtrips_with_heterogeneous_messages() -> None:
    """A `ScriptResult` holding a mix of `Feed`/`PanelUpdate` messages must keep
    each variant's own `{"type": ...}` tag through the round-trip."""
    result = ScriptResult(
        messages=[
            Feed(text="Tavern", message_type="system"),
            PanelUpdate(key="room_id", value="tavern"),
        ],
        proposed_effects=[SendNarration(text="hi", message_type="feed")],
        emitted_events=[EmittedEvent(event_type="looked", payload={"n": 1})],
        scheduled_work=[ScheduledWork(job_id="j1", due_logical_time=5, payload=None)],
        diagnostics=[Diagnostic(level="info", message="ok")],
    )
    dumped = result.to_json()
    # (b) each nested variant preserves its own discriminator tag on the wire.
    assert [m["type"] for m in dumped["messages"]] == ["Feed", "PanelUpdate"]
    assert dumped["proposed_effects"][0]["type"] == "SendNarration"
    assert ScriptResult.from_json(dumped) == result


def test_command_outcome_roundtrips_preserving_effect_tags_and_from_key() -> None:
    """A `CommandOutcome` carrying heterogeneous effects must keep each effect's
    tag *and* the `from`/`from_` wire-key rename intact across the round-trip."""
    outcome = CommandOutcome(
        command_id="cmd-1",
        status=OutcomeStatus.EXECUTED,
        commit_sequence=7,
        messages=[Feed(text="You go north.", message_type="system")],
        applied_effects=[
            MoveEntity(entity="player-1", from_="tavern", to="street"),
            TransferItem(item="coin", from_="room", to="player-1", quantity=3),
            AdjustMeter(entity="player-1", meter="health", delta=-2),
        ],
        diagnostics=[Diagnostic(level="info", message="ok")],
    )
    dumped = outcome.to_json()
    # (b) heterogeneous effect tags survive; (c) the `from` wire-key rename holds.
    assert [e["type"] for e in dumped["applied_effects"]] == [
        "MoveEntity",
        "TransferItem",
        "AdjustMeter",
    ]
    assert dumped["applied_effects"][0]["from"] == "tavern"
    assert "from_" not in dumped["applied_effects"][0]
    assert dumped["applied_effects"][1]["from"] == "room"
    assert CommandOutcome.from_json(dumped) == outcome


def test_command_outcome_roundtrips_with_none_commit_sequence() -> None:
    outcome = CommandOutcome(command_id="cmd-1", status=OutcomeStatus.BLOCKED)
    assert CommandOutcome.from_json(outcome.to_json()) == outcome


# --- Gateway framing wire-shape parity (Rust-port Phase 3) ---
#
# These mirror `rust/crates/lorecraft-protocol/src/gateway.rs`. The load-bearing
# checks are the tagged `{"type": ...}` shape assertions (matching serde's
# internally-tagged enums) plus recursive round-trips through the dispatch helpers.
# The Rust and Python sides are hand-kept in agreement, so these shapes are the
# cross-language contract for the gateway transport.


def _sample_directive() -> DeliveryDirective:
    return DeliveryDirective(
        target=RoomTarget(id="tavern"),
        exclude="player-1",
        payload={"type": "feed_append", "text": "You go north."},
    )


def test_disconnect_reason_wire_shapes() -> None:
    assert ClientClose().to_json() == {"type": "ClientClose"}
    assert GracefulQuit().to_json() == {"type": "GracefulQuit"}
    for reason in (ClientClose(), GracefulQuit()):
        assert disconnect_reason_from_json(reason.to_json()) == reason


def test_delivery_target_wire_shapes() -> None:
    cases = [
        (PlayerTarget(id="player-1"), {"type": "Player", "id": "player-1"}),
        (RoomTarget(id="tavern"), {"type": "Room", "id": "tavern"}),
        (GlobalTarget(), {"type": "Global"}),
        (AdminTarget(), {"type": "Admin"}),
    ]
    for target, shape in cases:
        assert target.to_json() == shape
        assert delivery_target_from_json(target.to_json()) == target


def test_delivery_directive_roundtrips_and_keeps_payload_opaque() -> None:
    directive = _sample_directive()
    dumped = directive.to_json()
    # payload relayed verbatim; target is a nested tagged object; exclude preserved.
    assert dumped["payload"] == {"type": "feed_append", "text": "You go north."}
    assert dumped["target"] == {"type": "Room", "id": "tavern"}
    assert dumped["exclude"] == "player-1"
    assert DeliveryDirective.from_json(dumped) == directive


def test_delivery_directive_roundtrips_with_no_exclude() -> None:
    directive = DeliveryDirective(
        target=GlobalTarget(), exclude=None, payload={"tick": 1}
    )
    dumped = directive.to_json()
    assert dumped["exclude"] is None
    assert DeliveryDirective.from_json(dumped) == directive


def test_delivery_directive_coalesce_key_defaults_none_and_is_absent_on_wire() -> None:
    # An unset coalesce_key must not appear in the serialized frame, so every
    # pre-existing directive is byte-identical to before the field was added
    # (mirrors the Rust skip_serializing_if = "Option::is_none").
    directive = _sample_directive()
    assert directive.coalesce_key is None
    dumped = directive.to_json()
    assert "coalesce_key" not in dumped
    # A legacy frame produced without the field still deserializes (default None).
    legacy = {"target": {"type": "Global"}, "exclude": None, "payload": {"tick": 1}}
    assert DeliveryDirective.from_json(legacy).coalesce_key is None


def test_delivery_directive_coalesce_key_present_roundtrips() -> None:
    directive = DeliveryDirective(
        target=PlayerTarget(id="player-1"),
        exclude=None,
        payload={"type": "state_change", "panel": "inventory"},
        coalesce_key="panel:inventory",
    )
    dumped = directive.to_json()
    assert dumped["coalesce_key"] == "panel:inventory"
    assert DeliveryDirective.from_json(dumped) == directive


def _sample_envelope() -> CommandEnvelope:
    return CommandEnvelope(
        protocol_version=1,
        world_id="world-1",
        actor_id="actor-1",
        player_id="player-1",
        session_id="session-1",
        command_id="cmd-1",
        receive_sequence=42,
        deadline_ms=5000,
        raw="look",
    )


def _sample_script_request() -> ScriptRequest:
    """A non-trivial `ScriptRequest` with nested attribute JSON, exercising the
    recursive snapshot/budget serialization the Phase 4 `SnapshotReady` frame
    carries."""
    return ScriptRequest(
        api_version=1,
        script_id="look",
        script_version=1,
        command_or_event="look",
        actor_snapshot=EntitySnapshot(id="player-1", kind="player", attributes={}),
        room_snapshot=EntitySnapshot(
            id="village_square",
            kind="room",
            attributes={
                "name": "Village Square",
                "exits": ["north", "south"],
                "nested": {"a": [1, 2, {"b": True}]},
            },
        ),
        selected_related_entities=[
            EntitySnapshot(id="old_sword", kind="item", attributes={})
        ],
        logical_time=7,
        rng_stream_id="stream-1",
        capability_set=["read"],
        budget=ScriptBudget(
            wall_ms=50, instructions=100000, memory_bytes=1048576, output_bytes=65536
        ),
    )


def _sample_outcome() -> CommandOutcome:
    """A non-trivial `CommandOutcome` carrying a tagged message + tagged effect,
    exercising the recursive nested-container serialization the Phase 4
    `ApplyOutcome` frame carries."""
    return CommandOutcome(
        command_id="cmd-1",
        status=OutcomeStatus.EXECUTED,
        commit_sequence=3,
        messages=[Feed(text="You are in the village square.", message_type="system")],
        applied_effects=[
            MoveEntity(entity="player-1", from_="village_square", to="north_road")
        ],
        diagnostics=[Diagnostic(level="info", message="ok")],
    )


def test_every_gateway_inbound_variant_roundtrips_and_tags() -> None:
    variants: list[tuple[object, str]] = [
        (RedeemTicket(ticket="tkt-1"), "RedeemTicket"),
        (ValidateAdminToken(token="jwt-1"), "ValidateAdminToken"),
        (Connected(player_id="player-1"), "Connected"),
        (Disconnected(player_id="player-1", reason=ClientClose()), "Disconnected"),
        (GatewayCommand(envelope=_sample_envelope()), "Command"),
        (BuildSnapshot(envelope=_sample_envelope()), "BuildSnapshot"),
        (
            ApplyOutcome(command_id="cmd-1", outcome=_sample_outcome()),
            "ApplyOutcome",
        ),
    ]
    for frame, tag in variants:
        dumped = frame.to_json()  # type: ignore[attr-defined]
        assert dumped["type"] == tag
        assert gateway_inbound_from_json(dumped) == frame


def test_gateway_command_flattens_envelope_fields() -> None:
    frame = GatewayCommand(envelope=_sample_envelope())
    dumped = frame.to_json()
    # The envelope is flattened alongside the tag (Rust newtype variant shape).
    assert dumped["type"] == "Command"
    assert dumped["raw"] == "look"
    assert dumped["world_id"] == "world-1"
    assert dumped["command_id"] == "cmd-1"
    assert gateway_inbound_from_json(dumped) == frame


def test_disconnected_nests_reason_tag() -> None:
    frame = Disconnected(player_id="player-1", reason=GracefulQuit())
    assert frame.to_json() == {
        "type": "Disconnected",
        "player_id": "player-1",
        "reason": {"type": "GracefulQuit"},
    }


def test_every_gateway_outbound_variant_roundtrips_and_tags() -> None:
    variants: list[tuple[object, str]] = [
        (AuthResult(accepted=True, player_id="player-1"), "AuthResult"),
        (AdminAuthResult(accepted=True), "AdminAuthResult"),
        (
            ConnectAck(
                session_id="session-1",
                room_id="tavern",
                direct_frames=[{"type": "state_change"}],
            ),
            "ConnectAck",
        ),
        (
            CommandReply(
                command_id="cmd-1",
                direct_reply={"command": "look", "messages": []},
                deliveries=[_sample_directive()],
            ),
            "CommandReply",
        ),
        (
            SnapshotReady(command_id="cmd-1", request=_sample_script_request()),
            "SnapshotReady",
        ),
        (
            OutcomeApplied(
                command_id="cmd-1",
                direct_reply={"command": "look", "messages": []},
                deliveries=[_sample_directive()],
            ),
            "OutcomeApplied",
        ),
        (
            ExecutionRejected(
                command_id="cmd-1",
                direct_reply={"type": "system", "text": "frozen"},
            ),
            "ExecutionRejected",
        ),
        (DeferToPython(command_id="cmd-1"), "DeferToPython"),
        (Deliver(directive=_sample_directive()), "Deliver"),
        (
            MovePlayer(player_id="player-1", from_room="tavern", to_room="square"),
            "MovePlayer",
        ),
    ]
    for frame, tag in variants:
        dumped = frame.to_json()  # type: ignore[attr-defined]
        assert dumped["type"] == tag
        assert gateway_outbound_from_json(dumped) == frame


def test_defer_to_python_wire_shape_carries_only_correlation_id() -> None:
    # The Phase 4c defer frame re-routes a command to Python; it carries just its tag
    # + correlation id (no reply, no deliveries), matching the Rust struct variant.
    frame = DeferToPython(command_id="cmd-skill")
    dumped = frame.to_json()
    assert dumped == {"type": "DeferToPython", "command_id": "cmd-skill"}
    assert "direct_reply" not in dumped
    assert "deliveries" not in dumped
    assert gateway_outbound_from_json(dumped) == frame


def test_execution_rejected_wire_shape_carries_correlation_and_no_deliveries() -> None:
    # The Phase 4b short-circuit frame (frozen rejection / persistence failure) must
    # byte-match the Rust `GatewayOutbound::ExecutionRejected` struct variant:
    # correlated by `command_id`, an opaque `direct_reply`, and NO deliveries field.
    frame = ExecutionRejected(
        command_id="cmd-7",
        direct_reply={
            "type": "system",
            "text": "Your session is frozen. Contact an administrator.",
        },
    )
    dumped = frame.to_json()
    assert dumped == {
        "type": "ExecutionRejected",
        "command_id": "cmd-7",
        "direct_reply": {
            "type": "system",
            "text": "Your session is frozen. Contact an administrator.",
        },
    }
    assert "deliveries" not in dumped
    assert gateway_outbound_from_json(dumped) == frame


def test_move_player_frame_shape_and_optional_from_room() -> None:
    # A move with a known origin serializes both rooms alongside the tag; this must
    # byte-match the Rust `GatewayOutbound::MovePlayer` wire shape.
    with_origin = MovePlayer(player_id="player-1", from_room="tavern", to_room="square")
    assert with_origin.to_json() == {
        "type": "MovePlayer",
        "player_id": "player-1",
        "from_room": "tavern",
        "to_room": "square",
    }
    assert gateway_outbound_from_json(with_origin.to_json()) == with_origin

    # An unknown origin serializes `from_room` as null (mirrors Rust `None`); the
    # registry treats an absent/empty origin as "unset".
    no_origin = MovePlayer(player_id="player-1", from_room=None, to_room="square")
    dumped = no_origin.to_json()
    assert dumped["from_room"] is None
    assert gateway_outbound_from_json(dumped) == no_origin


def test_auth_result_reject_serializes_null_player_id() -> None:
    frame = AuthResult(accepted=False, player_id=None)
    assert frame.to_json() == {
        "type": "AuthResult",
        "accepted": False,
        "player_id": None,
    }
    assert gateway_outbound_from_json(frame.to_json()) == frame


def test_admin_auth_result_has_no_player_id_field() -> None:
    # The admin auth outcome is shape-distinct from the player `AuthResult`: it
    # carries only `accepted`, so a validated admin can never be mistaken for a
    # player (see the resolved admin-push design).
    for accepted in (True, False):
        frame = AdminAuthResult(accepted=accepted)
        dumped = frame.to_json()
        assert dumped == {"type": "AdminAuthResult", "accepted": accepted}
        assert "player_id" not in dumped
        assert gateway_outbound_from_json(dumped) == frame


def test_command_reply_carries_correlation_id() -> None:
    # OPEN ITEM 1: the reply is correlated to its command by `command_id`.
    frame = CommandReply(command_id="cmd-42", direct_reply={"ok": True}, deliveries=[])
    dumped = frame.to_json()
    assert dumped["type"] == "CommandReply"
    assert dumped["command_id"] == "cmd-42"
    assert dumped["deliveries"] == []
    assert gateway_outbound_from_json(dumped) == frame


def test_command_reply_defaults_empty_deliveries() -> None:
    frame = CommandReply(command_id="cmd-1", direct_reply=None)
    assert frame.deliveries == []
    assert gateway_outbound_from_json(frame.to_json()) == frame


# --- Phase 4 execution round-trip frames (Option A) ---


def test_build_snapshot_nests_envelope_under_field_not_flattened() -> None:
    # Unlike `GatewayCommand` (which flattens the envelope beside the tag),
    # `BuildSnapshot` nests it under `envelope` so the reply's `command_id` can
    # correlate against `envelope.command_id`.
    frame = BuildSnapshot(envelope=_sample_envelope())
    dumped = frame.to_json()
    assert dumped["type"] == "BuildSnapshot"
    assert dumped["envelope"]["command_id"] == "cmd-1"
    assert dumped["envelope"]["raw"] == "look"
    # The envelope must NOT be flattened alongside the tag.
    assert "raw" not in dumped
    assert gateway_inbound_from_json(dumped) == frame


def test_apply_outcome_roundtrips_full_nested_outcome() -> None:
    # The nested `outcome`'s tagged message + tagged effect must survive the round
    # trip through the recursive container serialization (not flattened away).
    frame = ApplyOutcome(command_id="cmd-1", outcome=_sample_outcome())
    dumped = frame.to_json()
    assert dumped["type"] == "ApplyOutcome"
    assert dumped["command_id"] == "cmd-1"
    assert dumped["outcome"]["status"] == "Executed"
    assert dumped["outcome"]["messages"][0]["type"] == "Feed"
    assert dumped["outcome"]["applied_effects"][0]["type"] == "MoveEntity"
    # The `from`/`from_` wire-key rename holds through the nested effect.
    assert dumped["outcome"]["applied_effects"][0]["from"] == "village_square"
    assert gateway_inbound_from_json(dumped) == frame


def test_snapshot_ready_roundtrips_full_nested_request() -> None:
    # The nested `ScriptRequest`'s recursive snapshot attributes must survive.
    frame = SnapshotReady(command_id="cmd-1", request=_sample_script_request())
    dumped = frame.to_json()
    assert dumped["type"] == "SnapshotReady"
    assert dumped["command_id"] == "cmd-1"
    assert dumped["request"]["script_id"] == "look"
    assert (
        dumped["request"]["room_snapshot"]["attributes"]["nested"]["a"][2]["b"] is True
    )
    assert gateway_outbound_from_json(dumped) == frame


def test_outcome_applied_carries_correlation_and_opaque_reply() -> None:
    # `direct_reply` is relayed opaquely; `deliveries` round-trip verbatim.
    frame = OutcomeApplied(
        command_id="cmd-42",
        direct_reply={"command": "look", "ok": True},
        deliveries=[_sample_directive()],
    )
    dumped = frame.to_json()
    assert dumped["type"] == "OutcomeApplied"
    assert dumped["command_id"] == "cmd-42"
    assert dumped["direct_reply"]["command"] == "look"
    assert dumped["deliveries"][0]["payload"]["type"] == "feed_append"
    assert gateway_outbound_from_json(dumped) == frame


def test_outcome_applied_defaults_empty_deliveries() -> None:
    # A zero-broadcast verb (e.g. a private `look`) has empty deliveries.
    frame = OutcomeApplied(command_id="cmd-1", direct_reply={"ok": True})
    assert frame.deliveries == []
    dumped = frame.to_json()
    assert dumped["deliveries"] == []
    assert gateway_outbound_from_json(dumped) == frame


def test_outcome_applied_moves_are_absent_when_empty_and_carry_a_move_when_present() -> (
    None
):
    # A zero-move verb (e.g. `look`) must NOT serialize a `moves` key, so its wire
    # shape is byte-identical to before the additive field (mirrors the Rust
    # `skip_serializing_if`).
    no_move = OutcomeApplied(command_id="cmd-1", direct_reply={"ok": True})
    assert no_move.moves == []
    dumped = no_move.to_json()
    assert "moves" not in dumped
    # A legacy frame without the key still deserializes to the empty default.
    assert gateway_outbound_from_json(dumped) == no_move

    # A Rust-executed move carries its registry reconciliation inline, as a PLAIN
    # (untagged) object mirroring the Rust `PlayerMove` struct.
    with_move = OutcomeApplied(
        command_id="cmd-2",
        direct_reply={"command": "move", "noun": "north"},
        deliveries=[_sample_directive()],
        moves=[
            MovePlayer(
                player_id="mover",
                from_room="village_square",
                to_room="blacksmith_forge",
            )
        ],
    )
    dumped = with_move.to_json()
    assert dumped["moves"] == [
        {
            "player_id": "mover",
            "from_room": "village_square",
            "to_room": "blacksmith_forge",
        }
    ]
    # No `type` tag on the inline move (unlike a standalone `MovePlayer` frame).
    assert "type" not in dumped["moves"][0]
    assert gateway_outbound_from_json(dumped) == with_move

    # An unknown origin serializes `from_room` as null and still round-trips.
    no_origin = OutcomeApplied(
        command_id="cmd-3",
        direct_reply={"ok": True},
        moves=[MovePlayer(player_id="mover", from_room=None, to_room="square")],
    )
    dumped = no_origin.to_json()
    assert dumped["moves"][0]["from_room"] is None
    assert gateway_outbound_from_json(dumped) == no_origin
