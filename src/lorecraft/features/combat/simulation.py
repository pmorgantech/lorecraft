"""Headless combat balance simulation helpers."""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.engine.game.rng import GameRng
from lorecraft.features.combat.damage import ArmorProfile, WeaponProfile
from lorecraft.features.combat.definitions import (
    CombatActionRegistry,
    get_action_registry,
)
from lorecraft.features.combat.resolution import CombatantSnapshot, resolve_basic_attack
from lorecraft.types import JsonObject, JsonValue


@dataclass(frozen=True)
class CombatBalanceScenario:
    """Configuration for a deterministic one-action combat balance run."""

    action_key: str = "basic_attack"
    trials: int = 100
    seed: int = 1
    actor_strength: int = 30
    actor_agility: int = 12
    target_strength: int = 10
    target_agility: int = 8
    target_hp: float = 50.0
    weapon_base_damage: float = 4.0
    weapon_accuracy_bonus: float = 0.0
    weapon_penetration: float = 0.0
    armor_block: float = 0.0
    armor_resistance_factor: float = 0.0


def run_combat_balance_report(
    scenario: CombatBalanceScenario,
    *,
    registry: CombatActionRegistry | None = None,
) -> JsonObject:
    """Run a deterministic headless combat balance report.

    The first report shape is intentionally narrow: repeated one-action resolution using the
    same pure opposed-attack resolver as scheduled combat. It is enough to compare action
    definitions, equipment assumptions, and resolver versions without booting a server.
    """

    if scenario.trials <= 0:
        raise ValueError("combat balance trials must be positive")
    action_registry = registry or get_action_registry()
    action_def = action_registry.get(scenario.action_key)
    if action_def is None:
        raise ValueError(f"unknown combat action: {scenario.action_key!r}")

    rng = GameRng(seed=scenario.seed)
    actor = CombatantSnapshot(
        actor_type="player",
        actor_id="sim-player",
        name="Simulator",
        strength=scenario.actor_strength,
        agility=scenario.actor_agility,
    )
    target = CombatantSnapshot(
        actor_type="npc",
        actor_id="sim-target",
        name="Target",
        strength=scenario.target_strength,
        agility=scenario.target_agility,
    )
    weapon = WeaponProfile(
        base_damage=scenario.weapon_base_damage,
        accuracy_bonus=scenario.weapon_accuracy_bonus,
        penetration=scenario.weapon_penetration,
        sources=("simulation",),
    )
    armor = ArmorProfile(
        block=scenario.armor_block,
        resistance_factor=scenario.armor_resistance_factor,
        sources=("simulation",),
    )

    outcomes: dict[str, int] = {}
    damage_values: list[float] = []
    one_shot_defeats = 0
    for trial in range(scenario.trials):
        resolution = resolve_basic_attack(
            action_id=f"sim-{trial}",
            action_key=action_def.id,
            action_range=action_def.action_range,
            actor=actor,
            target=target,
            weapon=weapon,
            armor=armor,
            rng=rng,
            stamina_delta=action_def.stamina_delta or 0.0,
        )
        outcomes[resolution.outcome] = outcomes.get(resolution.outcome, 0) + 1
        damage_values.append(resolution.damage)
        if resolution.damage >= scenario.target_hp:
            one_shot_defeats += 1

    total_damage = sum(damage_values)
    misses = outcomes.get("miss", 0)
    outcome_payload: dict[str, JsonValue] = {
        outcome: count for outcome, count in outcomes.items()
    }
    return {
        "action_key": action_def.id,
        "ruleset_id": action_def.ruleset_id,
        "resolver": action_def.resolver,
        "resolver_version": action_def.resolver_version,
        "trials": scenario.trials,
        "seed": scenario.seed,
        "scenario": {
            "actor_strength": scenario.actor_strength,
            "actor_agility": scenario.actor_agility,
            "target_strength": scenario.target_strength,
            "target_agility": scenario.target_agility,
            "target_hp": scenario.target_hp,
            "weapon_base_damage": scenario.weapon_base_damage,
            "weapon_accuracy_bonus": scenario.weapon_accuracy_bonus,
            "weapon_penetration": scenario.weapon_penetration,
            "armor_block": scenario.armor_block,
            "armor_resistance_factor": scenario.armor_resistance_factor,
        },
        "outcomes": outcome_payload,
        "average_damage": round(total_damage / scenario.trials, 3),
        "min_damage": round(min(damage_values), 3),
        "max_damage": round(max(damage_values), 3),
        "hit_rate": round((scenario.trials - misses) / scenario.trials, 3),
        "one_shot_defeat_rate": round(one_shot_defeats / scenario.trials, 3),
    }
