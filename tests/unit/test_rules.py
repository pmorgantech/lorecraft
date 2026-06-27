from lorecraft.game.rules import RuleEngine, RuleResult


def test_rule_engine_allows_when_no_rules_registered() -> None:
    result = RuleEngine().check("take_item", ctx=None, payload={"item_id": "coin"})

    assert result.allowed is True
    assert result.modified_payload == {"item_id": "coin"}


def test_rule_engine_returns_first_blocking_rule() -> None:
    engine = RuleEngine()
    engine.register_rule("take_item", lambda ctx, payload: RuleResult.block("Bound to the altar."))
    engine.register_rule("take_item", lambda ctx, payload: RuleResult.allow())

    result = engine.check("take_item", ctx=None, payload={"item_id": "gem"})

    assert result.allowed is False
    assert result.reason == "Bound to the altar."


def test_rule_engine_carries_modified_payload_between_rules() -> None:
    engine = RuleEngine()
    engine.register_rule("move", lambda ctx, payload: RuleResult.allow({"direction": "north"}))
    engine.register_rule(
        "move",
        lambda ctx, payload: RuleResult.allow({"summary": f"go {payload['direction']}"}),
    )

    result = engine.check("move", ctx=None, payload={"direction": "n"})

    assert result.allowed is True
    assert result.modified_payload == {"direction": "north", "summary": "go north"}
