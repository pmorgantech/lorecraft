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
    CommandEnvelope,
    CommandOutcome,
    Diagnostic,
    EmitEvent,
    EmittedEvent,
    EntitySnapshot,
    Feed,
    MoveEntity,
    OutcomeStatus,
    PanelUpdate,
    ScheduledWork,
    ScriptBudget,
    ScriptRequest,
    ScriptResult,
    SendNarration,
    SetFlag,
    TransferItem,
    effect_from_json,
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
    # str-enum serializes to the Rust variant name.
    assert outcome.status.value == "Executed"
    assert _canonical({"status": outcome.status.value}) == '{"status":"Executed"}'


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
