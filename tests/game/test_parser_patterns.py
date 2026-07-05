"""Parser tests grouped by command interaction pattern."""

from __future__ import annotations

import pytest

from lorecraft.engine.game.command_patterns import (
    CommandPattern,
    container_roles,
    gesture_roles,
    movement_direction,
    object_phrase,
    pattern_for_verb,
    speech_roles,
    transfer_roles,
)
from lorecraft.engine.game.parser import parse, parse_command


class TestMovementPattern:
    @pytest.mark.parametrize(
        "raw,direction",
        [
            ("n", "north"),
            ("s", "south"),
            ("e", "east"),
            ("w", "west"),
            ("ne", "northeast"),
            ("u", "up"),
            ("d", "down"),
            ("north", "north"),
            ("go north", "north"),
            ("go to north", "north"),
        ],
    )
    def test_direction_commands(self, raw, direction, mock_context):
        result = parse_command(raw, context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        assert cmd.verb == "move"
        assert movement_direction(cmd) == direction
        assert pattern_for_verb(cmd.verb) == CommandPattern.MOVEMENT


class TestBarePattern:
    @pytest.mark.parametrize(
        "raw,verb", [("l", "look"), ("look", "look"), ("i", "inventory")]
    )
    def test_bare_commands_have_no_roles(self, raw, verb, mock_context):
        result = parse_command(raw, context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        assert cmd.verb == verb
        assert cmd.roles == {}
        assert pattern_for_verb(verb) in {
            CommandPattern.BARE,
            CommandPattern.META,
        }


class TestObjectManipulationPattern:
    @pytest.mark.parametrize(
        "raw,expected_phrase",
        [
            ("take sword", "sword"),
            ("take red potion", "red potion"),
            ("take all", "all"),
            ("take everything", "everything"),
            ("take 2 coin", "2 coin"),
            ("drop apple", "apple"),
            ("pick up shield", "shield"),
            ("get helmet", "helmet"),
        ],
    )
    def test_object_phrases(self, raw, expected_phrase, mock_context):
        result = parse_command(raw, context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        assert object_phrase(cmd) == expected_phrase
        assert pattern_for_verb(cmd.verb) == CommandPattern.OBJECT_MANIPULATION

    def test_take_all_without_context(self):
        parsed = parse("take all")
        assert parsed.verb == "take"
        assert parsed.noun == "all"


class TestContainerPattern:
    @pytest.mark.parametrize(
        "raw,obj,container",
        [
            ("put apple in backpack", "apple", "backpack"),
            ("take sword from rack", "sword", "rack"),
            ("look in chest", None, "chest"),
            ("look at sword", None, "sword"),
            ("open chest", None, "chest"),
        ],
    )
    def test_container_role_extraction(self, raw, obj, container, mock_context):
        result = parse_command(raw, context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        roles = container_roles(cmd)
        if obj is not None:
            assert roles.object_phrase == obj
        if container is not None:
            assert (
                roles.container_phrase == container or roles.source_phrase == container
            )


class TestTransferPattern:
    def test_give_to_recipient(self, mock_context):
        result = parse_command("give lead pipe to Gabriel", context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        assert cmd.verb == "give"
        roles = transfer_roles(cmd)
        assert roles is not None
        assert roles.object_phrase == "lead pipe"
        assert roles.recipient == "Gabriel"
        assert pattern_for_verb(cmd.verb) == CommandPattern.TRANSFER


class TestToolUsePattern:
    @pytest.mark.parametrize(
        "raw,expected_roles",
        [
            ("unlock chest with key", {"target": "chest", "instrument": "key"}),
            ("use key on chest", {"object": "key", "destination": "chest"}),
        ],
    )
    def test_tool_and_target_roles(self, raw, expected_roles):
        result = parse_command(raw)
        assert not result.error_message
        cmd = result.commands[0]
        for key, value in expected_roles.items():
            assert cmd.roles.get(key) == value


class TestCombatPattern:
    def test_attack_with_weapon(self, mock_context):
        result = parse_command("attack goblin with spear", context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        assert cmd.roles.get("target") == "goblin"
        assert cmd.roles.get("instrument") == "spear"
        assert pattern_for_verb(cmd.verb) == CommandPattern.COMBAT


class TestSpeechPattern:
    @pytest.mark.parametrize(
        "raw,message,recipient",
        [
            ("say hello everyone", "hello everyone", None),
            ("yell help", "help", None),
            ('whisper "meet me later" to Gabriel', "meet me later", "Gabriel"),
        ],
    )
    def test_speech_roles(self, raw, message, recipient, mock_context):
        result = parse_command(raw, context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        roles = speech_roles(cmd)
        assert roles is not None
        assert roles.message == message
        assert roles.recipient == recipient
        assert pattern_for_verb(cmd.verb) == CommandPattern.SPEECH


class TestSocialGesturePattern:
    @pytest.mark.parametrize(
        "raw,target",
        [
            ("wave", None),
            ("wave at Gabriel", "Gabriel"),
            ("bow to Mira", "Mira"),
            ("nod", None),
        ],
    )
    def test_gesture_targets(self, raw, target, mock_context):
        result = parse_command(raw, context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        roles = gesture_roles(cmd)
        assert roles.gesture == cmd.verb
        assert roles.target == target
        assert pattern_for_verb(cmd.verb) == CommandPattern.SOCIAL_GESTURE


class TestNpcDialoguePattern:
    @pytest.mark.parametrize(
        "raw,recipient,topic",
        [
            ("talk to Mira", "Mira", None),
            ("ask Mira about quests", "Mira", "quests"),
        ],
    )
    def test_npc_dialogue_roles(self, raw, recipient, topic, mock_context):
        result = parse_command(raw, context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        assert cmd.roles.get("recipient") == recipient
        if topic is not None:
            assert cmd.roles.get("topic") == topic
        assert pattern_for_verb(cmd.verb) == CommandPattern.NPC_DIALOGUE


class TestCompoundAndAliasPattern:
    def test_semicolon_compounds(self, mock_context):
        result = parse_command("take lantern; drop apple", context=mock_context)
        assert not result.error_message
        assert len(result.commands) == 2
        assert result.commands[0].verb == "take"
        assert result.commands[1].verb == "drop"

    @pytest.mark.parametrize(
        "raw,verb",
        [
            ("l", "look"),
            ("x sword", "examine"),
            ("inv", "inventory"),
        ],
    )
    def test_token_aliases(self, raw, verb):
        parsed = parse(raw)
        assert parsed.verb == verb
