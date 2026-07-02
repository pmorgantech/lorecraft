"""Broad parser regression tests (roles, compounds, ambiguity, diagnostics)."""

from __future__ import annotations

import pytest

from lorecraft.game.parser import diagnose_command, parse_command


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
            ("look under bed", "examine", {"target": "bed"}),
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
            ("n", "move", {"direction": "north"}),
            ("north", "move", {"direction": "north"}),
        ],
    )
    def test_role_extraction(self, raw, expected_verb, expected_roles):
        result = parse_command(raw)
        assert not result.error_message
        assert len(result.commands) == 1
        cmd = result.commands[0]
        assert cmd.verb == expected_verb
        for key, value in expected_roles.items():
            assert cmd.roles.get(key) == value, f"Role {key} mismatch in {raw}"


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
            ("buy 3 healing potions", {"object": "healing potions", "quantity": 3}),
            ("put all coins in chest", {"object": "all coins", "destination": "chest"}),
            ("drop everything except lantern", {"object": "everything except lantern"}),
        ],
    )
    def test_adjectives_quantities_lists(self, raw, expected):
        result = parse_command(raw)
        assert not result.error_message
        cmd = result.commands[0]
        for key, value in expected.items():
            assert cmd.roles.get(key) == value


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
        result = parse_command("take lantern; light it", context=mock_context)
        assert len(result.commands) == 2
        lit_target = result.commands[1].roles.get("object") or result.commands[
            1
        ].roles.get("target")
        assert lit_target in ("lantern", "it")


class TestAmbiguity:
    def test_ambiguous_take_defers_to_inventory_layer(self, mock_context):
        result = parse_command("take key", context=mock_context)
        assert not result.error_message
        assert result.commands[0].verb == "take"
        assert result.commands[0].roles.get("object") == "key"
        assert "object" not in result.commands[0].resolved_ids

    def test_ambiguous_examine_defers_to_inventory_layer(self, mock_context):
        result = parse_command("examine key", context=mock_context)
        assert not result.error_message
        assert result.commands[0].verb == "examine"
        assert result.commands[0].roles.get("target") == "key"
        assert "target" not in result.commands[0].resolved_ids


class TestAliasResolution:
    def test_examine_resolves_item_by_alias(self, mock_context):
        result = parse_command("examine blade", context=mock_context)
        assert not result.error_message
        assert result.commands[0].resolved_ids.get("target") == "rusty_iron_sword"

    def test_examine_resolves_item_by_second_alias(self, mock_context):
        result = parse_command("examine shortsword", context=mock_context)
        assert not result.error_message
        assert result.commands[0].resolved_ids.get("target") == "rusty_iron_sword"


class TestErrorsAndEdges:
    def test_empty(self):
        result = parse_command("")
        assert result.error_message and "mumble" in result.error_message.lower()

    def test_unknown_verb_graceful(self, mock_context):
        result = parse_command("flargle the blarg", context=mock_context)
        assert result.commands or result.error_message

    def test_quoted_multiword(self, mock_context):
        result = parse_command(
            'whisper "meet me later" to Gabriel', context=mock_context
        )
        assert result.commands[0].roles.get("message") == "meet me later"


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
        assert any("final_commands" in step.name for step in diag.steps)


class TestV1Limitations:
    def test_no_deep_nesting(self, mock_context):
        result = parse_command("take coin from purse in chest", context=mock_context)
        assert result.commands or result.error_message
