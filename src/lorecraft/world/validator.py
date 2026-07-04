"""Validation for authored world YAML documents."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class WorldValidationError(ValueError):
    """Raised when authored world data is structurally invalid."""


class ExitData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: str
    target_room_id: str
    locked: bool = False
    key_item_id: str | None = None
    hidden: bool = False
    condition_flags: list[str] = Field(default_factory=list)


class RoomData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    map_x: int
    map_y: int
    area_id: str | None = None
    is_active: bool = True
    fallback_room_id: str | None = None
    flags: dict[str, object] = Field(default_factory=dict)
    disabled_commands: list[str] = Field(default_factory=list)
    light_level: int = 1
    version: int = 1
    terrain: str = "normal"
    exits: list[ExitData] = Field(default_factory=list)


class ItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    takeable: bool = True
    tradeable: bool = True
    bound: bool = False
    aliases: list[str] = Field(default_factory=list)
    usable_with: list[str] = Field(default_factory=list)
    loot_table: dict[str, object] = Field(default_factory=dict)
    slot: str | None = None
    wearable: bool = False
    weight: float = 0.0
    quality: str = "common"
    max_durability: int | None = None
    light: int = 0
    capacity: float | None = None
    effects: list[dict[str, object]] = Field(default_factory=list)


class RoomItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str
    item_id: str
    quantity: int = 1


class NpcScheduleEntryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_hour: int
    target_room_id: str


class NpcData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    home_room_id: str
    current_room_id: str | None = None
    dialogue_tree_id: str = ""
    behavior: str = "defensive"
    max_hp: int = 50
    schedule: list[NpcScheduleEntryData] = Field(default_factory=list)
    loot_table: dict[str, object] = Field(default_factory=dict)


class DialogueChoiceData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    next_node: str | None = None
    required_flags: list[str] = Field(default_factory=list)
    forbidden_flags: list[str] = Field(default_factory=list)
    side_effects: dict[str, object] = Field(default_factory=dict)


class DialogueNodeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    side_effects: dict[str, object] = Field(default_factory=dict)
    choices: list[DialogueChoiceData] = Field(default_factory=list)


class DialogueTreeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    root_node: str
    nodes: dict[str, DialogueNodeData]


class QuestConditionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    flag: str | None = None
    room_id: str | None = None
    item_id: str | None = None


class QuestStageData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    conditions: list[QuestConditionData] = Field(default_factory=list)
    completion_flags: dict[str, object] = Field(default_factory=dict)
    rewards: dict[str, object] = Field(default_factory=dict)


class QuestData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str = ""
    stages: list[QuestStageData] = Field(default_factory=list)


class WorldDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rooms: list[RoomData] = Field(default_factory=list)
    items: list[ItemData] = Field(default_factory=list)
    room_items: list[RoomItemData] = Field(default_factory=list)
    npcs: list[NpcData] = Field(default_factory=list)
    dialogue_trees: list[DialogueTreeData] = Field(default_factory=list)
    quests: list[QuestData] = Field(default_factory=list)


def validate_world_document(data: object) -> WorldDocument:
    try:
        document = WorldDocument.model_validate(data)
    except ValidationError as exc:
        raise WorldValidationError(str(exc)) from exc

    errors: list[str] = []
    room_ids = {room.id for room in document.rooms}
    item_ids = {item.id for item in document.items}
    dialogue_tree_ids = {dt.id for dt in document.dialogue_trees}

    for room in document.rooms:
        if room.fallback_room_id is not None and room.fallback_room_id not in room_ids:
            errors.append(
                f"room {room.id} references missing fallback room {room.fallback_room_id}"
            )
        for exit_ in room.exits:
            if exit_.target_room_id not in room_ids:
                errors.append(
                    f"room {room.id} exit {exit_.direction} references missing room "
                    f"{exit_.target_room_id}"
                )
            if exit_.key_item_id is not None and exit_.key_item_id not in item_ids:
                errors.append(
                    f"room {room.id} exit {exit_.direction} references missing key item "
                    f"{exit_.key_item_id}"
                )

    for room_item in document.room_items:
        if room_item.room_id not in room_ids:
            errors.append(f"room item references missing room {room_item.room_id}")
        if room_item.item_id not in item_ids:
            errors.append(f"room item references missing item {room_item.item_id}")
        if room_item.quantity < 1:
            errors.append(
                f"room item {room_item.item_id} in {room_item.room_id} must have quantity >= 1"
            )

    for npc in document.npcs:
        if npc.home_room_id not in room_ids:
            errors.append(
                f"npc {npc.id} references missing home_room_id {npc.home_room_id}"
            )
        if npc.current_room_id and npc.current_room_id not in room_ids:
            errors.append(
                f"npc {npc.id} references missing current_room_id {npc.current_room_id}"
            )
        if npc.dialogue_tree_id and npc.dialogue_tree_id not in dialogue_tree_ids:
            errors.append(
                f"npc {npc.id} references missing dialogue_tree_id {npc.dialogue_tree_id}"
            )
        for entry in npc.schedule:
            if entry.target_room_id not in room_ids:
                errors.append(
                    f"npc {npc.id} schedule references missing room {entry.target_room_id}"
                )

    if errors:
        raise WorldValidationError("; ".join(errors))

    return document
