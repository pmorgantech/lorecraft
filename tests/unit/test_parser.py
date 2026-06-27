from lorecraft.game.parser import ParsedCommand, parse


def test_direction_alias_becomes_go_command() -> None:
    assert parse("n") == ParsedCommand(verb="go", noun="north", raw="n")


def test_full_direction_becomes_go_command() -> None:
    assert parse("south") == ParsedCommand(verb="go", noun="south", raw="south")


def test_take_strips_articles_from_noun() -> None:
    assert parse("take the old sword") == ParsedCommand(
        verb="take",
        noun="old sword",
        raw="take the old sword",
    )


def test_collapses_whitespace_and_normalizes_case() -> None:
    assert parse("  GET   An   Apple  ") == ParsedCommand(
        verb="take",
        noun="apple",
        raw="  GET   An   Apple  ",
    )


def test_empty_command_has_empty_verb() -> None:
    assert parse("   ") == ParsedCommand(verb="", noun=None, raw="   ")
