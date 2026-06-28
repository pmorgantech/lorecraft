"""Import validated world authoring data into the runtime database."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlmodel import Session
import yaml

from lorecraft.models.world import Exit, Item, Room, RoomItem
from lorecraft.types import JsonObject
from lorecraft.world.validator import WorldDocument, validate_world_document


def load_world_yaml(path: str | Path, session: Session) -> WorldDocument:
    source_path = Path(path)
    data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    document = validate_world_document(cast(object, data))
    import_world(document, session)
    return document


def import_world(document: WorldDocument, session: Session) -> None:
    for room in document.rooms:
        session.merge(
            Room(
                id=room.id,
                name=room.name,
                description=room.description,
                map_x=room.map_x,
                map_y=room.map_y,
                area_id=room.area_id,
                is_active=room.is_active,
                fallback_room_id=room.fallback_room_id,
                flags=cast(JsonObject, room.flags),
                disabled_commands=room.disabled_commands,
                light_level=room.light_level,
                version=room.version,
            )
        )

    for item in document.items:
        session.merge(
            Item(
                id=item.id,
                name=item.name,
                description=item.description,
                takeable=item.takeable,
                tradeable=item.tradeable,
                usable_with=item.usable_with,
                loot_table=cast(JsonObject, item.loot_table),
            )
        )

    session.flush()

    for room in document.rooms:
        for exit_ in room.exits:
            session.add(
                Exit(
                    room_id=room.id,
                    direction=exit_.direction,
                    target_room_id=exit_.target_room_id,
                    locked=exit_.locked,
                    key_item_id=exit_.key_item_id,
                    hidden=exit_.hidden,
                    condition_flags=exit_.condition_flags,
                )
            )

    for room_item in document.room_items:
        session.add(
            RoomItem(
                room_id=room_item.room_id,
                item_id=room_item.item_id,
                quantity=room_item.quantity,
            )
        )
