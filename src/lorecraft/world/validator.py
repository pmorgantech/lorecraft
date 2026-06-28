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
    exits: list[ExitData] = Field(default_factory=list)


class ItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    takeable: bool = True
    tradeable: bool = True
    usable_with: list[str] = Field(default_factory=list)
    loot_table: dict[str, object] = Field(default_factory=dict)


class RoomItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str
    item_id: str
    quantity: int = 1


class WorldDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rooms: list[RoomData] = Field(default_factory=list)
    items: list[ItemData] = Field(default_factory=list)
    room_items: list[RoomItemData] = Field(default_factory=list)


def validate_world_document(data: object) -> WorldDocument:
    try:
        document = WorldDocument.model_validate(data)
    except ValidationError as exc:
        raise WorldValidationError(str(exc)) from exc

    errors: list[str] = []
    room_ids = {room.id for room in document.rooms}
    item_ids = {item.id for item in document.items}

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

    if errors:
        raise WorldValidationError("; ".join(errors))

    return document
