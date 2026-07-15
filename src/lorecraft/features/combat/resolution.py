"""Pure combat resolution objects and calculator."""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import PlayerStats
from lorecraft.engine.models.world import NPC
from lorecraft.features.combat.damage import (
    ArmorProfile,
    WeaponProfile,
    apply_damage_stack,
)
from lorecraft.types import JsonObject


@dataclass(frozen=True)
class CombatantSnapshot:
    actor_type: str
    actor_id: str
    name: str
    strength: int
    agility: int
    defense_bonus: int = 0


@dataclass(frozen=True)
class CombatResolution:
    action_id: str
    action_key: str
    actor: CombatantSnapshot
    target: CombatantSnapshot | None
    outcome: str
    damage: float = 0.0
    stamina_delta: float = 0.0
    target_status: str | None = None
    explanation: str = ""
    random_trace: JsonObject | None = None
    damage_trace: JsonObject | None = None


def player_snapshot(
    player_id: str, username: str, stats: PlayerStats | None
) -> CombatantSnapshot:
    return CombatantSnapshot(
        actor_type="player",
        actor_id=player_id,
        name=username,
        strength=stats.strength if stats is not None else 10,
        agility=stats.agility if stats is not None else 10,
    )


def npc_snapshot(npc: NPC) -> CombatantSnapshot:
    return CombatantSnapshot(
        actor_type="npc",
        actor_id=npc.id,
        name=npc.name,
        strength=10,
        agility=8,
    )


def resolve_basic_attack(
    *,
    action_id: str,
    actor: CombatantSnapshot,
    target: CombatantSnapshot,
    weapon: WeaponProfile,
    armor: ArmorProfile,
    rng: GameRng,
    defended: bool = False,
) -> CombatResolution:
    attack_roll = rng.randint(-10, 10) + rng.randint(-10, 10)
    defense_roll = rng.randint(-10, 10) + rng.randint(-10, 10)
    attack_score = actor.strength + weapon.accuracy_bonus + attack_roll
    defense_score = target.agility + target.defense_bonus + defense_roll
    if defended:
        defense_score += 6
    margin = attack_score - defense_score
    if margin < -8:
        outcome = "miss"
        multiplier = 0.0
    elif margin < 0:
        outcome = "glancing"
        multiplier = 0.35
    elif margin >= 12:
        outcome = "strong_hit"
        multiplier = 1.35
    else:
        outcome = "hit"
        multiplier = 1.0
    damage = apply_damage_stack(
        base_damage=weapon.base_damage + max(0.0, margin / 6),
        outcome_multiplier=multiplier,
        armor=armor,
        penetration=weapon.penetration,
    )
    return CombatResolution(
        action_id=action_id,
        action_key="basic_attack",
        actor=actor,
        target=target,
        outcome=outcome,
        damage=damage.amount,
        stamina_delta=-6.0,
        explanation=f"{actor.name} attacks {target.name}: {outcome}.",
        random_trace={
            "attack_roll": attack_roll,
            "defense_roll": defense_roll,
            "margin": margin,
        },
        damage_trace={
            **damage.trace,
            "weapon_sources": list(weapon.sources),
            "weapon_base_damage": weapon.base_damage,
            "weapon_accuracy_bonus": weapon.accuracy_bonus,
        },
    )
