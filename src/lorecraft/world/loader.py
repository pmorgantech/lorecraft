"""Import validated world authoring data into the runtime database."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlmodel import Session, select
import yaml

from lorecraft.models.dialogue import DialogueTree
from lorecraft.models.quest import Quest
from lorecraft.models.world import Exit, Item, NPC, Room, RoomItem
from lorecraft.types import JsonObject
from lorecraft.world.validator import (
    DialogueChoiceData,
    DialogueNodeData,
    DialogueTreeData,
    ExitData,
    ItemData,
    NpcData,
    NpcScheduleEntryData,
    QuestData,
    QuestStageData,
    RoomData,
    RoomItemData,
    WorldDocument,
    validate_world_document,
)


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
                aliases=item.aliases,
                usable_with=item.usable_with,
                loot_table=cast(JsonObject, item.loot_table),
            )
        )

    for tree in document.dialogue_trees:
        nodes_dict: dict[str, object] = {}
        for node_id, node in tree.nodes.items():
            nodes_dict[node_id] = {
                "text": node.text,
                "side_effects": node.side_effects,
                "choices": [c.model_dump() for c in node.choices],
            }
        session.merge(
            DialogueTree(
                id=tree.id,
                tree_data=cast(
                    JsonObject,
                    {"root_node": tree.root_node, "nodes": nodes_dict},
                ),
            )
        )

    for quest in document.quests:
        session.merge(
            Quest(
                id=quest.id,
                title=quest.title,
                description=quest.description,
                stages=[s.model_dump() for s in quest.stages],
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

    for npc in document.npcs:
        session.merge(
            NPC(
                id=npc.id,
                name=npc.name,
                description=npc.description,
                current_room_id=npc.current_room_id or npc.home_room_id,
                home_room_id=npc.home_room_id,
                dialogue_tree_id=npc.dialogue_tree_id,
                behavior=npc.behavior,
                max_hp=npc.max_hp,
                current_hp=npc.max_hp,
                schedule=[e.model_dump() for e in npc.schedule],
                loot_table=cast(JsonObject, npc.loot_table),
            )
        )


def export_world_document(session: Session) -> WorldDocument:
    """Rebuild a `WorldDocument` from the current DB state (inverse of `import_world`)."""
    rooms = session.exec(select(Room)).all()
    exits_by_room: dict[str, list[Exit]] = {}
    for exit_ in session.exec(select(Exit)).all():
        exits_by_room.setdefault(exit_.room_id, []).append(exit_)

    room_data = [
        RoomData(
            id=room.id,
            name=room.name,
            description=room.description,
            map_x=room.map_x,
            map_y=room.map_y,
            area_id=room.area_id,
            is_active=room.is_active,
            fallback_room_id=room.fallback_room_id,
            flags=cast(dict[str, object], room.flags),
            disabled_commands=list(room.disabled_commands),
            light_level=room.light_level,
            version=room.version,
            exits=[
                ExitData(
                    direction=exit_.direction,
                    target_room_id=exit_.target_room_id,
                    locked=exit_.locked,
                    key_item_id=exit_.key_item_id,
                    hidden=exit_.hidden,
                    condition_flags=list(exit_.condition_flags),
                )
                for exit_ in exits_by_room.get(room.id, [])
            ],
        )
        for room in rooms
    ]

    item_data = [
        ItemData(
            id=item.id,
            name=item.name,
            description=item.description,
            takeable=item.takeable,
            tradeable=item.tradeable,
            aliases=list(item.aliases),
            usable_with=list(item.usable_with),
            loot_table=cast(dict[str, object], item.loot_table),
        )
        for item in session.exec(select(Item)).all()
    ]

    room_item_data = [
        RoomItemData(
            room_id=room_item.room_id,
            item_id=room_item.item_id,
            quantity=room_item.quantity,
        )
        for room_item in session.exec(select(RoomItem)).all()
    ]

    npc_data = [
        NpcData(
            id=npc.id,
            name=npc.name,
            description=npc.description,
            home_room_id=npc.home_room_id,
            current_room_id=npc.current_room_id,
            dialogue_tree_id=npc.dialogue_tree_id,
            behavior=npc.behavior,
            max_hp=npc.max_hp,
            schedule=[
                NpcScheduleEntryData.model_validate(entry) for entry in npc.schedule
            ],
            loot_table=cast(dict[str, object], npc.loot_table),
        )
        for npc in session.exec(select(NPC)).all()
    ]

    dialogue_tree_data = [
        DialogueTreeData(
            id=tree.id,
            root_node=str(tree.tree_data.get("root_node", "")),
            nodes={
                node_id: DialogueNodeData(
                    text=str(node.get("text", "")),
                    side_effects=cast(dict[str, object], node.get("side_effects", {})),
                    choices=[
                        DialogueChoiceData.model_validate(choice)
                        for choice in cast(list[object], node.get("choices", []))
                    ],
                )
                for node_id, node in cast(
                    dict[str, dict[str, object]], tree.tree_data.get("nodes", {})
                ).items()
            },
        )
        for tree in session.exec(select(DialogueTree)).all()
    ]

    quest_data = [
        QuestData(
            id=quest.id,
            title=quest.title,
            description=quest.description,
            stages=[QuestStageData.model_validate(stage) for stage in quest.stages],
        )
        for quest in session.exec(select(Quest)).all()
    ]

    return WorldDocument(
        rooms=room_data,
        items=item_data,
        room_items=room_item_data,
        npcs=npc_data,
        dialogue_trees=dialogue_tree_data,
        quests=quest_data,
    )
