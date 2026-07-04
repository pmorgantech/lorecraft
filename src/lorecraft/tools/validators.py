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
    valid_effect_types = {"stat_bonus", "skill_bonus", "carry_bonus", "grant_trait"}
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
    if start_room_id is not None:
        result.merge(check_room_reachability(document, start_room_id))
    return result
