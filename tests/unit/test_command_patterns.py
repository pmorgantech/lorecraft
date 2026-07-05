"""Unit tests for command pattern helpers."""

from __future__ import annotations

from lorecraft.engine.game.command_patterns import (
    CommandPattern,
    container_roles,
    gesture_roles,
    object_phrase,
    pattern_for_verb,
    required_roles_for_pattern,
    speech_roles,
    transfer_roles,
)
from lorecraft.engine.game.parser import ParsedCommand


def test_pattern_for_known_verbs() -> None:
    assert pattern_for_verb("give") == CommandPattern.TRANSFER
    assert pattern_for_verb("wave") == CommandPattern.SOCIAL_GESTURE
    assert pattern_for_verb("flargle") == CommandPattern.UNKNOWN


def test_object_phrase_includes_modifiers() -> None:
    cmd = ParsedCommand(
        verb="take",
        raw="take 2 red potion",
        roles={"quantity": 2, "adjectives": ["red"], "object": "potion"},
    )
    assert object_phrase(cmd) == "2 red potion"


def test_speech_roles_directed_and_undirected() -> None:
    room_say = ParsedCommand(
        verb="say",
        raw='say "hello"',
        roles={"message": "hello"},
    )
    directed = ParsedCommand(
        verb="whisper",
        raw='whisper "psst" to Gabriel',
        roles={"message": "psst", "recipient": "Gabriel"},
        resolved_ids={"recipient": "id_gabriel"},
    )
    assert speech_roles(room_say) == speech_roles(room_say)
    assert speech_roles(room_say).message == "hello"
    assert speech_roles(room_say).recipient is None

    whisper = speech_roles(directed)
    assert whisper is not None
    assert whisper.message == "psst"
    assert whisper.recipient == "Gabriel"
    assert whisper.recipient_id == "id_gabriel"


def test_transfer_and_container_helpers() -> None:
    give = ParsedCommand(
        verb="give",
        raw="give apple to Gabriel",
        roles={"object": "apple", "recipient": "Gabriel"},
        resolved_ids={"object": "id_apple", "recipient": "id_gabriel"},
    )
    transfer = transfer_roles(give)
    assert transfer is not None
    assert transfer.object_phrase == "apple"
    assert transfer.recipient == "Gabriel"
    assert transfer.object_id == "id_apple"

    put = ParsedCommand(
        verb="put",
        raw="put apple in chest",
        roles={"object": "apple", "destination": "chest"},
    )
    container = container_roles(put)
    assert container.object_phrase == "apple"
    assert container.container_phrase == "chest"


def test_gesture_roles() -> None:
    undirected = ParsedCommand(verb="wave", raw="wave", roles={})
    directed = ParsedCommand(
        verb="bow",
        raw="bow to Gabriel",
        roles={"recipient": "Gabriel"},
    )
    assert gesture_roles(undirected).target is None
    assert gesture_roles(directed).target == "Gabriel"


def test_required_roles_documents_expectations() -> None:
    assert "object" in required_roles_for_pattern(CommandPattern.TRANSFER)
    assert "message" in required_roles_for_pattern(CommandPattern.SPEECH)
