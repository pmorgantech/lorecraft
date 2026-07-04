"""Compile Item.effects descriptors into Tier 1 Modifiers/trait grants.

See docs/inventory_equipment.md §3, §9. Descriptor types are registry-driven
in spirit (each is a small pure function here); unknown descriptor types are
a content-lint error (tools/validators.py), not a runtime fallthrough — this
module assumes it's only ever called on already-linted item effects.
"""

from __future__ import annotations

from lorecraft.game.modifiers import Modifier
from lorecraft.models.world import Item


def compile_item_modifiers(item: Item) -> list[Modifier]:
    """Every stat_bonus/skill_bonus/carry_bonus descriptor as a Modifier.

    grant_trait descriptors feed the trait registry instead (see
    item_granted_traits) — they aren't modifiers themselves.
    """
    modifiers: list[Modifier] = []
    source = f"item:{item.id}"
    for effect in item.effects:
        effect_type = effect.get("type")
        if effect_type == "stat_bonus":
            stat = effect.get("stat")
            amount = effect.get("amount")
            if isinstance(stat, str) and isinstance(amount, (int, float)):
                modifiers.append(
                    Modifier(
                        key=f"stat.{stat}",
                        kind="add",
                        amount=float(amount),
                        source=source,
                    )
                )
        elif effect_type == "skill_bonus":
            skill = effect.get("skill")
            amount = effect.get("amount")
            if isinstance(skill, str) and isinstance(amount, (int, float)):
                modifiers.append(
                    Modifier(
                        key=f"skill.{skill}",
                        kind="add",
                        amount=float(amount),
                        source=source,
                    )
                )
        elif effect_type == "carry_bonus":
            amount = effect.get("amount")
            if isinstance(amount, (int, float)):
                modifiers.append(
                    Modifier(
                        key="carry_capacity",
                        kind="add",
                        amount=float(amount),
                        source=source,
                    )
                )
        elif effect_type == "warmth_bonus":
            amount = effect.get("amount")
            if isinstance(amount, (int, float)):
                modifiers.append(
                    Modifier(
                        key="warmth",
                        kind="add",
                        amount=float(amount),
                        source=source,
                    )
                )
    return modifiers


def item_granted_traits(item: Item) -> set[str]:
    """Every grant_trait descriptor's trait name."""
    names: set[str] = set()
    for effect in item.effects:
        if effect.get("type") == "grant_trait":
            trait = effect.get("trait")
            if isinstance(trait, str):
                names.add(trait)
    return names
