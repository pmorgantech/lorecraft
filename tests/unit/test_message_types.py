"""Sprint 56.1/56.2: the structured output-type taxonomy and `Message`."""

from __future__ import annotations

import json

from lorecraft.engine.game.message_types import Message, MessageType


class TestMessage:
    def test_message_equals_plain_string(self) -> None:
        """`Message` is a `str` subclass so `ctx.messages == ["text"]`-style
        assertions (the pre-Sprint-56 contract, used throughout the test
        suite) keep working unchanged."""
        msg = Message("You move north.", MessageType.SYSTEM)
        assert msg == "You move north."
        assert [msg] == ["You move north."]

    def test_message_carries_its_type(self) -> None:
        msg = Message("You are attacked!", MessageType.COMBAT)
        assert msg.type == MessageType.COMBAT

    def test_message_defaults_to_system(self) -> None:
        assert Message("hi").type == MessageType.SYSTEM

    def test_message_supports_str_operations(self) -> None:
        msg = Message("Quest completed: Find the Key!", MessageType.QUEST)
        assert msg.startswith("Quest completed")
        assert "Find the Key" in msg
        assert str(msg) == "Quest completed: Find the Key!"

    def test_message_json_serializes_as_plain_string(self) -> None:
        """The `/ws` response path (`main.py`) sends `ctx.messages` straight
        through `json.dumps`/`send_json` without converting to dicts — a str
        subclass must degrade to its plain text there, silently dropping
        `.type`, so existing WS clients are unaffected until they opt in."""
        msg = Message("You are attacked!", MessageType.COMBAT)
        assert json.dumps([msg]) == json.dumps(["You are attacked!"])


class TestMessageType:
    def test_taxonomy_is_small_and_named(self) -> None:
        """Pins the ten-entry taxonomy so a future PR adding a one-off
        type notices the list grew (matches the `EventBus`/`ChatScope`
        discipline of a small, deliberate vocabulary)."""
        assert {member.value for member in MessageType} == {
            "room_event",
            "chat",
            "tell",
            "combat",
            "quest",
            "warning",
            "hint",
            "help",
            "level",
            "system",
        }
