"""Headless combat balance report tests."""

from __future__ import annotations

import json

import pytest

from lorecraft.features.combat.simulation import (
    CombatBalanceScenario,
    run_combat_balance_report,
)
from lorecraft.tools.combat_balance import main as combat_balance_main


def test_combat_balance_report_is_deterministic() -> None:
    scenario = CombatBalanceScenario(trials=12, seed=42)

    assert run_combat_balance_report(scenario) == run_combat_balance_report(scenario)


def test_combat_balance_report_groups_by_ruleset_and_resolver_version() -> None:
    report = run_combat_balance_report(CombatBalanceScenario(trials=20, seed=7))

    assert report["action_key"] == "basic_attack"
    assert report["ruleset_id"] == "core"
    assert report["resolver_version"] == "opposed-v1"
    assert sum(report["outcomes"].values()) == 20
    assert 0.0 <= report["hit_rate"] <= 1.0
    assert 0.0 <= report["one_shot_defeat_rate"] <= 1.0
    assert report["max_damage"] >= report["min_damage"]


def test_combat_balance_report_rejects_non_positive_trials() -> None:
    with pytest.raises(ValueError, match="trials must be positive"):
        run_combat_balance_report(CombatBalanceScenario(trials=0))


def test_combat_balance_cli_writes_json_report(tmp_path) -> None:
    output = tmp_path / "combat-report.json"

    assert combat_balance_main(["--trials", "5", "--seed", "2", "-o", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["trials"] == 5
    assert sum(report["outcomes"].values()) == 5
