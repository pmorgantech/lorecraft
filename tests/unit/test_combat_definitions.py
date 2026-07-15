"""Combat action definition schema and registry tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from lorecraft.features.combat.definitions import (
    CALCULATOR_OPPOSED_ATTACK,
    RESOLVER_DEFEND,
    RESOLVER_OPPOSED_ATTACK,
    CombatActionDef,
    CombatActionRegistry,
    CombatActionTiming,
    CombatComponentRegistry,
    load_combat_actions_yaml,
    register_standard_combat_components,
    validate_combat_actions_document,
)


def test_shipped_combat_actions_yaml_loads_into_registry() -> None:
    document = load_combat_actions_yaml(Path("world_content/combat_actions.yaml"))
    registry = CombatActionRegistry(_standard_components())
    registry.load_document(document)

    actions = {action.id: action for action in registry.all()}

    assert set(actions) == {"basic_attack", "ranged_attack", "defend", "flee"}
    assert actions["basic_attack"].resolver == RESOLVER_OPPOSED_ATTACK
    assert actions["basic_attack"].action_range == "engaged"
    assert actions["ranged_attack"].action_range == "ranged"
    assert actions["defend"].resolver == RESOLVER_DEFEND
    assert actions["defend"].timing.recovery == 1.2


def test_combat_action_document_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicate combat action ids"):
        validate_combat_actions_document(
            {
                "actions": [
                    _action_payload("basic_attack"),
                    _action_payload("basic_attack"),
                ]
            }
        )


def test_combat_action_registry_rejects_unknown_resolver() -> None:
    registry = CombatActionRegistry(_standard_components())
    action = CombatActionDef(
        id="custom",
        action_range="engaged",
        calculator=CALCULATOR_OPPOSED_ATTACK,
        resolver="missing",
        timing=CombatActionTiming(windup=0.1, recovery=1.0),
    )

    with pytest.raises(ValueError, match="unknown resolver"):
        registry.register(action)


def _standard_components() -> CombatComponentRegistry:
    registry = CombatComponentRegistry()
    register_standard_combat_components(registry)
    return registry


def _action_payload(action_id: str) -> dict[str, object]:
    return {
        "id": action_id,
        "action_range": "engaged",
        "calculator": CALCULATOR_OPPOSED_ATTACK,
        "resolver": RESOLVER_OPPOSED_ATTACK,
        "timing": {"windup": 0.1, "recovery": 1.0},
    }
