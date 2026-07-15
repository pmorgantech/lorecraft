"""Combat damage staging and equipment-derived descriptors."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.world import Item
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.types import JsonObject

QUALITY_SCALARS: dict[str, float] = {
    "common": 1.0,
    "fine": 1.15,
    "superior": 1.3,
    "rare": 1.5,
    "legendary": 1.8,
}


@dataclass(frozen=True)
class WeaponProfile:
    base_damage: float
    accuracy_bonus: float
    penetration: float
    sources: tuple[str, ...]


@dataclass(frozen=True)
class ArmorProfile:
    block: float
    resistance_factor: float
    sources: tuple[str, ...]


@dataclass(frozen=True)
class DamageResult:
    amount: float
    trace: JsonObject


def weapon_profile_for(
    session: Session, actor_type: str, actor_id: str
) -> WeaponProfile:
    if actor_type != "player":
        return WeaponProfile(
            base_damage=6.0,
            accuracy_bonus=0.0,
            penetration=0.0,
            sources=("natural_weapon",),
        )
    weapons = [
        item
        for item in _equipped_items(session, actor_id)
        if item.category == "weapon" or item.slot in {"main_hand", "off_hand"}
    ]
    if not weapons:
        return WeaponProfile(
            base_damage=4.0,
            accuracy_bonus=0.0,
            penetration=0.0,
            sources=("unarmed",),
        )
    base = 0.0
    accuracy = 0.0
    penetration = 0.0
    sources: list[str] = []
    for item in weapons:
        scalar = _quality_scalar(item)
        base += (4.0 + min(item.weight, 8.0) * 1.2) * scalar
        accuracy += (
            1.5 if item.quality in {"fine", "superior", "rare", "legendary"} else 0.0
        )
        penetration += min(item.weight * 0.25, 2.0)
        sources.append(f"item:{item.id}")
    # Off-hand weapons help, but do not double full damage.
    return WeaponProfile(
        base_damage=round(max(4.0, base * (0.75 if len(weapons) > 1 else 1.0)), 2),
        accuracy_bonus=round(accuracy, 2),
        penetration=round(penetration, 2),
        sources=tuple(sources),
    )


def armor_profile_for(session: Session, actor_type: str, actor_id: str) -> ArmorProfile:
    if actor_type != "player":
        return ArmorProfile(block=0.0, resistance_factor=0.0, sources=())
    armor = [
        item
        for item in _equipped_items(session, actor_id)
        if item.category == "armor" and item.wearable
    ]
    block = 0.0
    resistance = 0.0
    sources: list[str] = []
    for item in armor:
        scalar = _quality_scalar(item)
        block += min(item.weight * 0.45 * scalar, 6.0)
        resistance += min(0.02 + item.weight * 0.006 * scalar, 0.08)
        sources.append(f"item:{item.id}")
    return ArmorProfile(
        block=round(min(block, 12.0), 2),
        resistance_factor=round(min(resistance, 0.35), 3),
        sources=tuple(sources),
    )


def apply_damage_stack(
    *,
    base_damage: float,
    outcome_multiplier: float,
    armor: ArmorProfile,
    penetration: float,
) -> DamageResult:
    after_base = max(0.0, base_damage)
    after_multiplier = after_base * outcome_multiplier
    effective_block = max(0.0, armor.block - penetration)
    after_block = max(0.0, after_multiplier - effective_block)
    after_resistance = after_block * (1.0 - armor.resistance_factor)
    amount = round(max(0.0, after_resistance), 2)
    return DamageResult(
        amount=amount,
        trace={
            "base_damage": round(after_base, 2),
            "outcome_multiplier": outcome_multiplier,
            "after_multiplier": round(after_multiplier, 2),
            "armor_block": armor.block,
            "penetration": penetration,
            "effective_block": round(effective_block, 2),
            "armor_resistance_factor": armor.resistance_factor,
            "final_damage": amount,
            "armor_sources": list(armor.sources),
        },
    )


def _equipped_items(session: Session, player_id: str) -> list[Item]:
    statement = select(ItemStack).where(
        ItemStack.owner_type == "player",
        ItemStack.owner_id == player_id,
        ItemStack.slot.is_not(None),  # type: ignore[attr-defined]
    )
    item_repo = ItemRepo(session)
    items: list[Item] = []
    for stack in session.exec(statement).all():
        item = item_repo.get(stack.item_id)
        if item is not None:
            items.append(item)
    return items


def _quality_scalar(item: Item) -> float:
    return QUALITY_SCALARS.get(item.quality, 1.0)
