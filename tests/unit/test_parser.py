from lorecraft.game.parser import ParsedCommand, parse


def test_direction_alias_becomes_go_command() -> None:
    parsed = parse("n")
    assert parsed.verb == "go"
    assert parsed.noun == "north"
    assert parsed.raw == "n"


def test_full_direction_becomes_go_command() -> None:
    parsed = parse("south")
    assert parsed.verb == "go"
    assert parsed.noun == "south"
    assert parsed.raw == "south"


def test_take_strips_articles_from_noun() -> None:
    parsed = parse("take the old sword")
    assert parsed.verb == "take"
    assert parsed.noun == "old sword"
    assert parsed.raw == "take the old sword"


def test_collapses_whitespace_and_normalizes_case() -> None:
    parsed = parse("  GET   An   Apple  ")
    assert parsed.verb == "take"
    assert parsed.noun == "Apple"
    assert parsed.raw == "  GET   An   Apple  "


def test_empty_command_has_empty_verb() -> None:
    parsed = parse("   ")
    assert parsed == ParsedCommand(verb="", raw="   ")
    assert parsed.noun is None


def test_l_alias_becomes_look_command() -> None:
    parsed = parse("l")
    assert parsed.verb == "look"
    assert parsed.noun is None
    assert parsed.raw == "l"


def test_shortest_prefix_resolves_partial_verb() -> None:
    parsed = parse("loo")
    assert parsed.verb == "look"
    assert parsed.noun is None


def test_take_all_parses_bare_all_object() -> None:
    parsed = parse("take all")
    assert parsed.verb == "take"
    assert parsed.noun == "all"


def test_choice_number_parses_as_single_index() -> None:
    parsed = parse("choice 1")
    assert parsed.verb == "choice"
    assert parsed.noun == "1"
    assert parsed.roles["choice_index"] == 1
