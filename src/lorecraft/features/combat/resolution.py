"""Pure combat resolution objects and calculator."""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import PlayerStats
from lorecraft.engine.models.world import NPC
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
    rng: GameRng,
    defended: bool = False,
) -> CombatResolution:
    attack_roll = rng.randint(-10, 10) + rng.randint(-10, 10)
    defense_roll = rng.randint(-10, 10) + rng.randint(-10, 10)
    attack_score = actor.strength + attack_roll
    defense_score = target.agility + target.defense_bonus + defense_roll
    if defended:
        defense_score += 6
    margin = attack_score - defense_score
    if margin < -8:
        outcome = "miss"
        damage = 0.0
    elif margin < 0:
        outcome = "glancing"
        damage = 3.0
    elif margin >= 12:
        outcome = "strong_hit"
        damage = 12.0 + min(6.0, margin / 4)
    else:
        outcome = "hit"
        damage = 8.0 + min(4.0, margin / 5)
    return CombatResolution(
        action_id=action_id,
        action_key="basic_attack",
        actor=actor,
        target=target,
        outcome=outcome,
        damage=round(damage, 2),
        stamina_delta=-6.0,
        explanation=f"{actor.name} attacks {target.name}: {outcome}.",
        random_trace={
            "attack_roll": attack_roll,
            "defense_roll": defense_roll,
            "margin": margin,
        },
    )
