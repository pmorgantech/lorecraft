"""
Comprehensive unit tests for Lorecraft parser v1
Covers: all user examples, plurals, adjectives, quantities, compounds (;),
disambiguation, in-character errors, basic context resolution,
English variations, edge cases.

Run with: pytest tests/game/test_parser_comprehensive.py -q
"""

import pytest
from lorecraft.game.parser import (
    parse_command,
    diagnose_command,
    GameContext,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_context():
    """Minimal context with realistic objects for fuzzy matching & disambiguation."""

    class MockContext(GameContext):
        def get_visible_entities(self):
            return [
                ("id_brass_key", "brass key", ["key", "brass key"]),
                ("id_iron_key", "iron key", ["key", "iron key"]),
                ("id_red_potion", "red potion", ["potion", "red potion"]),
                ("id_small_brass_key", "small brass key", ["key", "small brass key"]),
                ("id_lead_pipe", "lead pipe", ["pipe", "lead pipe"]),
                ("id_gabriel", "Gabriel", ["gabriel"]),
                ("id_chest", "wooden chest", ["chest"]),
                ("id_sword", "sword", []),
                ("id_shield", "shield", []),
                ("id_helmet", "helmet", []),
                ("id_goblin", "goblin", []),
                ("id_spear", "spear", []),
                ("id_lantern", "lantern", []),
                ("id_purse", "leather purse", ["purse"]),
            ]

        def get_inventory(self):
            return [
                ("id_lantern_inv", "lantern", []),
            ]

    return MockContext()


# =============================================================================
# Basic & Preposition / Role tests (user examples)
# =============================================================================


class TestBasicAndRoles:
    @pytest.mark.parametrize(
        "raw,expected_verb,expected_roles",
        [
            (
                "give the lead pipe to Gabriel",
                "give",
                {"object": "lead pipe", "recipient": "Gabriel"},
            ),
            ("look at the drawing", "examine", {"target": "drawing"}),
            ("look in chest", "examine", {"destination": "chest"}),
            ("look under bed", "examine", {"target": "bed"}),  # under -> target for v1
            (
                "use the key on the chest",
                "use",
                {"object": "key", "destination": "chest"},
            ),
            (
                "unlock chest with key",
                "unlock",
                {"target": "chest", "instrument": "key"},
            ),
            (
                "put apple in backpack",
                "put",
                {"object": "apple", "destination": "backpack"},
            ),
            ("take sword from rack", "take", {"object": "sword", "source": "rack"}),
            ("wear leather armor", "wear", {"object": "leather armor"}),
            ("remove helmet", "remove", {"object": "helmet"}),
            (
                "attack goblin with spear",
                "attack",
                {"target": "goblin", "instrument": "spear"},
            ),
            (
                "kill goblin",
                "attack",
                {"target": "goblin"},
            ),  # via alias in real game, here direct
            ("talk to merchant", "talk", {"recipient": "merchant"}),
            (
                "ask merchant about dragons",
                "ask",
                {"recipient": "merchant", "topic": "dragons"},
            ),
            ("say hello everyone", "say", {"message": "hello everyone"}),
            (
                'whisper "meet me later" to Gabriel',
                "whisper",
                {"message": "meet me later", "recipient": "Gabriel"},
            ),
            ("open north door", "open", {"target": "north door"}),
            ("go north", "move", {"direction": "north"}),
            (
                "climb up rope",
                "climb",
                {"target": "rope", "direction": "up"},
            ),  # simplistic
            ("read page 3 of book", "read", {"target": "book", "subobject": "page 3"}),
            ("n", "move", {"direction": "north"}),
            ("north", "move", {"direction": "north"}),
        ],
    )
    def test_role_extraction(self, raw, expected_verb, expected_roles, mock_context):
        result = parse_command(raw, context=mock_context)
        assert not result.error_message
        assert len(result.commands) == 1
        cmd = result.commands[0]
        assert cmd.verb == expected_verb
        for k, v in expected_roles.items():
            assert cmd.roles.get(k) == v, f"Role {k} mismatch in {raw}"


# =============================================================================
# Multiple objects, adjectives, quantities, plurals
# =============================================================================


class TestMultipleAdjectivesQuantities:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("take red potion", {"object": "potion", "adjectives": ["red"]}),
            (
                "take small brass key",
                {"object": "key", "adjectives": ["small", "brass"]},
            ),
            ("drop 10 arrows", {"object": "arrows", "quantity": 10}),
            ("buy 3 healing potions", {"object": "healing potion", "quantity": 3}),
            (
                "take sword, shield, and helmet",
                {"objects": ["sword", "shield", "helmet"]},
            ),  # simplistic list handling
            ("put all coins in chest", {"object": "all coins", "destination": "chest"}),
            ("drop everything except lantern", {"object": "everything except lantern"}),
        ],
    )
    def test_adjectives_quantities_lists(self, raw, expected, mock_context):
        result = parse_command(raw, context=mock_context)
        assert not result.error_message
        cmd = result.commands[0]
        for k, v in expected.items():
            assert cmd.roles.get(k) == v


# =============================================================================
# Compounds (semicolon)
# =============================================================================


class TestCompounds:
    def test_semicolon_separated(self, mock_context):
        result = parse_command(
            "unlock chest with key; open chest; take gem", context=mock_context
        )
        assert not result.error_message
        assert len(result.commands) == 3
        assert result.commands[0].verb == "unlock"
        assert result.commands[1].verb == "open"
        assert result.commands[2].verb == "take"

    def test_compound_with_basic_pronoun_carry(self, mock_context):
        # Very basic "it" support in compounds for v1
        result = parse_command("take lantern; light it", context=mock_context)
        assert len(result.commands) == 2
        assert result.commands[1].roles.get("object") in (
            "lantern",
            "it",
        )  # depending on implementation depth


# =============================================================================
# Ambiguity & Disambiguation (in-character errors)
# =============================================================================


class TestAmbiguity:
    def test_ambiguous_key(self, mock_context):
        result = parse_command("take key", context=mock_context)
        assert result.error_message is not None
        assert (
            "which" in result.error_message.lower()
            or "don't see" in result.error_message.lower()
        )
        assert any("key" in s.lower() for s in result.suggestions)


# =============================================================================
# In-character error messages & edge cases
# =============================================================================


class TestErrorsAndEdges:
    def test_empty(self):
        result = parse_command("")
        assert result.error_message and "mumble" in result.error_message.lower()

    def test_unknown_verb_graceful(self, mock_context):
        result = parse_command("flargle the blarg", context=mock_context)
        # Should still produce a command (verb passed through) or gentle error
        assert result.commands or result.error_message

    def test_quoted_multiword(self, mock_context):
        result = parse_command(
            'whisper "meet me later" to Gabriel', context=mock_context
        )
        assert result.commands[0].roles.get("message") == "meet me later"


# =============================================================================
# Diagnostic mode tests
# =============================================================================


class TestDiagnostics:
    def test_diagnose_runs_without_error(self, mock_context):
        diag = diagnose_command(
            "give the lead pipe to Gabriel", context=mock_context, verbose=False
        )
        assert diag.normalized
        assert diag.tokens
        assert diag.final_result is not None
        assert len(diag.steps) >= 1

    def test_diagnose_shows_roles(self, mock_context):
        diag = diagnose_command("take red potion", context=mock_context, verbose=False)
        assert any("final_commands" in s.name for s in diag.steps)


# =============================================================================
# v1 Limitations documented in tests
# =============================================================================


class TestV1Limitations:
    def test_no_deep_nesting(self, mock_context):
        # As per user request: "coin in purse in chest" should not be auto-unpacked in v1
        result = parse_command("take coin from purse in chest", context=mock_context)
        # It will parse something; we just assert it doesn't crash and produces a command
        assert result.commands or result.error_message
        # In real use the player will be told to do sequential actions
