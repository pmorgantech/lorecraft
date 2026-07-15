"""Content linting rules for authored world YAML.

These run on top of `validate_world_document` (schema + basic referential
integrity, already enforced at import time). Checks here catch authoring
mistakes that are structurally valid YAML but broken in play: dangling
dialogue links, unreachable rooms, dead item references, etc.

Circular quest dependencies are not checked: `QuestStageData` has no
quest-to-quest dependency field today, so there is nothing to scan for a
cycle in. Add a check here once the schema grows one.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from lorecraft.features.combat.definitions import (
    CombatActionRegistry,
    CombatComponentRegistry,
    load_combat_actions_yaml,
    register_standard_combat_components,
)
from lorecraft.features.terrain.definitions import get_registry as get_terrain_registry
from lorecraft.world.validator import WorldDocument


@dataclass
class LintResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: "LintResult") -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)


def check_dialogue_node_references(document: WorldDocument) -> LintResult:
    """Every `root_node` and `choice.next_node` must exist within its own tree."""
    result = LintResult()
    for tree in document.dialogue_trees:
        if tree.root_node not in tree.nodes:
            result.errors.append(
                f"dialogue tree {tree.id!r} root_node {tree.root_node!r} "
                "is not a defined node"
            )
        for node_id, node in tree.nodes.items():
            for choice in node.choices:
                if choice.next_node is not None and choice.next_node not in tree.nodes:
                    result.errors.append(
                        f"dialogue tree {tree.id!r} node {node_id!r} choice "
                        f"{choice.label!r} links to nonexistent node "
                        f"{choice.next_node!r}"
                    )
    return result


def check_room_reachability(document: WorldDocument, start_room_id: str) -> LintResult:
    """Warn about rooms with no directed exit path from `start_room_id`."""
    result = LintResult()
    room_ids = {room.id for room in document.rooms}
    if start_room_id not in room_ids:
        result.warnings.append(
            f"start room {start_room_id!r} not found; skipping reachability check"
        )
        return result

    exits_by_room: dict[str, list[str]] = {room.id: [] for room in document.rooms}
    for room in document.rooms:
        for exit_ in room.exits:
            exits_by_room[room.id].append(exit_.target_room_id)

    visited = {start_room_id}
    queue: deque[str] = deque([start_room_id])
    while queue:
        current = queue.popleft()
        for target in exits_by_room.get(current, []):
            if target in room_ids and target not in visited:
                visited.add(target)
                queue.append(target)

    for room_id in sorted(room_ids - visited):
        result.warnings.append(
            f"room {room_id!r} unreachable (no exit path from {start_room_id!r})"
        )
    return result


def check_dead_item_references(document: WorldDocument) -> LintResult:
    """`usable_with` and NPC `loot_table` entries must reference real items."""
    result = LintResult()
    item_ids = {item.id for item in document.items}

    for item in document.items:
        for other_id in item.usable_with:
            if other_id not in item_ids:
                result.errors.append(
                    f"item {item.id!r} usable_with references missing item {other_id!r}"
                )

    for npc in document.npcs:
        for loot_item_id in npc.loot_table:
            if loot_item_id not in item_ids:
                result.errors.append(
                    f"npc {npc.id!r} loot_table references missing item "
                    f"{loot_item_id!r}"
                )
    return result


def check_duplicate_item_names_per_room(document: WorldDocument) -> LintResult:
    """Warn when a room holds two or more items with the same display name."""
    result = LintResult()
    item_names = {item.id: item.name for item in document.items}

    names_by_room: dict[str, list[str]] = {}
    for room_item in document.room_items:
        name = item_names.get(room_item.item_id)
        if name is not None:
            names_by_room.setdefault(room_item.room_id, []).append(name)

    for room_id, names in names_by_room.items():
        seen: set[str] = set()
        duplicates: set[str] = set()
        for name in names:
            key = name.lower()
            if key in seen:
                duplicates.add(name)
            seen.add(key)
        for name in sorted(duplicates):
            result.warnings.append(
                f"room {room_id!r} has more than one item named {name!r} "
                "(confusing for players)"
            )
    return result


def check_item_quantity_warnings(
    document: WorldDocument, *, threshold: int = 20
) -> LintResult:
    """Warn about a single room_item stack above `threshold` (consider a quantity model)."""
    result = LintResult()
    for room_item in document.room_items:
        if room_item.quantity > threshold:
            result.warnings.append(
                f"room {room_item.room_id!r} has {room_item.quantity} of item "
                f"{room_item.item_id!r} in one stack (consider splitting or "
                "reviewing the quantity)"
            )
    return result


def check_item_definition_fields(document: WorldDocument) -> LintResult:
    """Validate item definition fields (slots, effects, capacity, etc.)."""
    result = LintResult()

    valid_slots = {
        "head",
        "face",
        "neck",
        "shoulders",
        "torso",
        "back",
        "hands",
        "finger_l",
        "finger_r",
        "finger",  # generic: wear command picks whichever of finger_l/finger_r is free
        "waist",
        "legs",
        "feet",
        "main_hand",
        "off_hand",
    }
    valid_qualities = {"common", "fine", "superior", "rare", "legendary"}
    valid_effect_types = {
        "stat_bonus",
        "skill_bonus",
        "carry_bonus",
        "grant_trait",
        "warmth_bonus",
        "weapon_profile",
        "armor_profile",
        # One-shot-on-consume descriptors (eat/drink), see features/consumables.
        "heal",
        "apply_effect",
    }
    stats = {"strength", "agility", "vitality", "intellect", "presence", "fortitude"}

    for item in document.items:
        if item.slot is not None and item.slot not in valid_slots:
            result.errors.append(
                f"item {item.id!r} has unknown slot {item.slot!r}; "
                f"valid slots: {sorted(valid_slots)}"
            )

        if item.wearable and item.slot is None:
            result.errors.append(
                f"item {item.id!r} is wearable but has no slot defined"
            )

        if item.quality not in valid_qualities:
            result.errors.append(
                f"item {item.id!r} has unknown quality {item.quality!r}; "
                f"valid: {sorted(valid_qualities)}"
            )

        if item.capacity is not None and not item.takeable:
            result.errors.append(
                f"item {item.id!r} is a container (capacity set) but not takeable"
            )

        if item.weight < 0:
            result.errors.append(f"item {item.id!r} has negative weight {item.weight}")

        if item.light < 0:
            result.errors.append(
                f"item {item.id!r} has negative light value {item.light}"
            )

        if item.max_durability is not None and item.max_durability <= 0:
            result.errors.append(
                f"item {item.id!r} has invalid max_durability {item.max_durability} "
                "(must be positive or None)"
            )

        for i, effect in enumerate(item.effects):
            effect_type = effect.get("type")
            if effect_type not in valid_effect_types:
                result.errors.append(
                    f"item {item.id!r} effect {i} has unknown type {effect_type!r}; "
                    f"valid: {sorted(valid_effect_types)}"
                )

            if effect_type == "stat_bonus":
                stat = effect.get("stat")
                if stat not in stats:
                    result.errors.append(
                        f"item {item.id!r} effect {i} references unknown stat {stat!r}"
                    )
            elif effect_type == "skill_bonus":
                if "skill" not in effect:
                    result.errors.append(
                        f"item {item.id!r} effect {i} (skill_bonus) missing 'skill' field"
                    )
            elif effect_type == "warmth_bonus":
                if not isinstance(effect.get("amount"), (int, float)):
                    result.errors.append(
                        f"item {item.id!r} effect {i} (warmth_bonus) missing numeric 'amount' field"
                    )
            elif effect_type == "weapon_profile":
                if not isinstance(effect.get("base_damage"), (int, float)):
                    result.errors.append(
                        f"item {item.id!r} effect {i} (weapon_profile) missing numeric "
                        "'base_damage' field"
                    )
                for field in ("accuracy_bonus", "penetration"):
                    if field in effect and not isinstance(
                        effect.get(field), (int, float)
                    ):
                        result.errors.append(
                            f"item {item.id!r} effect {i} (weapon_profile) has "
                            f"non-numeric {field!r} field"
                        )
            elif effect_type == "armor_profile":
                if not isinstance(effect.get("block"), (int, float)):
                    result.errors.append(
                        f"item {item.id!r} effect {i} (armor_profile) missing numeric "
                        "'block' field"
                    )
                if not isinstance(effect.get("resistance_factor"), (int, float)):
                    result.errors.append(
                        f"item {item.id!r} effect {i} (armor_profile) missing numeric "
                        "'resistance_factor' field"
                    )
            elif effect_type == "heal":
                if not isinstance(effect.get("meter"), str):
                    result.errors.append(
                        f"item {item.id!r} effect {i} (heal) missing string 'meter' field"
                    )
                if not isinstance(effect.get("amount"), (int, float)):
                    result.errors.append(
                        f"item {item.id!r} effect {i} (heal) missing numeric 'amount' field"
                    )
            elif effect_type == "apply_effect":
                if not isinstance(effect.get("effect_key"), str):
                    result.errors.append(
                        f"item {item.id!r} effect {i} (apply_effect) missing string "
                        "'effect_key' field"
                    )

    return result


def check_room_terrain(document: WorldDocument) -> LintResult:
    """Every room's `terrain` must be a registered TerrainDef name."""
    result = LintResult()
    registry = get_terrain_registry()
    for room in document.rooms:
        if registry.get(room.terrain) is None:
            result.errors.append(
                f"room {room.id!r} has unknown terrain {room.terrain!r}"
            )
    return result


def check_shop_pricing(document: WorldDocument) -> LintResult:
    """Every shop-stocked item needs a `value` to derive a price from, and
    must be `tradeable` (an untradeable item can never actually change
    hands via buy/sell, whatever a shop's stock list claims)."""
    result = LintResult()
    items_by_id = {item.id: item for item in document.items}
    for npc in document.npcs:
        if npc.shop is None:
            continue
        for stock in npc.shop.stock:
            item = items_by_id.get(stock.item_id)
            if item is None:
                continue  # already flagged by validate_world_document
            if item.value <= 0:
                result.errors.append(
                    f"npc {npc.id!r} shop stocks item {item.id!r} with no `value` set"
                )
            if not item.tradeable:
                result.errors.append(
                    f"npc {npc.id!r} shop stocks item {item.id!r} which is not tradeable"
                )
    return result


def check_combat_action_definitions(path: str | Path) -> LintResult:
    """Validate data-authored combat actions referenced by runtime startup.

    Missing action content is a warning because the server has built-in core
    fallback actions. Malformed content is an error because startup would discard
    the author's file and run fallback behavior instead.
    """
    result = LintResult()
    source = Path(path)
    if not source.exists():
        result.warnings.append(
            f"combat action definitions {str(source)!r} not found; startup will "
            "fall back to built-in attack/shoot/defend/flee actions"
        )
        return result
    try:
        components = CombatComponentRegistry()
        register_standard_combat_components(components)
        registry = CombatActionRegistry(components)
        registry.load_document(load_combat_actions_yaml(source))
    except Exception as exc:
        result.errors.append(
            f"combat action definitions {str(source)!r} are invalid: {exc}"
        )
    return result


def run_all_checks(
    document: WorldDocument, *, start_room_id: str | None = None
) -> LintResult:
    result = LintResult()
    result.merge(check_dialogue_node_references(document))
    result.merge(check_dead_item_references(document))
    result.merge(check_duplicate_item_names_per_room(document))
    result.merge(check_item_quantity_warnings(document))
    result.merge(check_item_definition_fields(document))
    result.merge(check_room_terrain(document))
    result.merge(check_shop_pricing(document))
    if start_room_id is not None:
        result.merge(check_room_reachability(document, start_room_id))
    return result
