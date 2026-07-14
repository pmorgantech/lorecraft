"""Import validated world authoring data into the runtime database."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from sqlmodel import Session, select

from lorecraft.engine.game.holders import Location
from lorecraft.features.bank.models import Bank
from lorecraft.features.npc.models import DialogueTree
from lorecraft.features.economy.models import RegionPricing, Shop, ShopStock
from lorecraft.engine.models.items import ItemStack
from lorecraft.features.progression.models import ProgressionConfig
from lorecraft.features.quests.models import Quest
from lorecraft.features.transit.models import TransitLine, TransitStop
from lorecraft.engine.models.world import Exit, Item, NPC, Room
from lorecraft.engine.repos.ledger_repo import LedgerRepo
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.types import JsonObject
from lorecraft.world.yaml_io import load_world_yaml_text
from lorecraft.world.validator import (
    ContextCommandData,
    BankBranchData,
    DialogueChoiceData,
    DialogueNodeData,
    DialogueTreeData,
    EconomyConfigData,
    ExitData,
    ItemData,
    NpcData,
    NpcScheduleEntryData,
    ProgressionConfigData,
    QuestData,
    QuestStageData,
    RegionPricingData,
    RoomData,
    RoomItemData,
    ShopData,
    ShopStockData,
    TransitConfigData,
    TransitLineData,
    TransitStopData,
    WorldDocument,
    validate_world_document,
)


def load_world_yaml(path: str | Path, session: Session) -> WorldDocument:
    source_path = Path(path)
    data = load_world_yaml_text(source_path.read_text(encoding="utf-8")) or {}
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
                map_z=room.map_z,
                zone=room.zone,
                room_type=room.room_type,
                is_active=room.is_active,
                fallback_room_id=room.fallback_room_id,
                flags=cast(JsonObject, room.flags),
                disabled_commands=room.disabled_commands,
                light_level=room.light_level,
                version=room.version,
                terrain=room.terrain,
                safe_rest=room.safe_rest,
                indoor=room.indoor,
                loot_table=cast(JsonObject, room.loot_table),
                ambient_events=cast(list[JsonObject], room.ambient_events),
                triggers=cast(list[JsonObject], room.triggers),
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
                bound=item.bound,
                aliases=item.aliases,
                usable_with=item.usable_with,
                loot_table=cast(JsonObject, item.loot_table),
                slot=item.slot,
                wearable=item.wearable,
                weight=item.weight,
                quality=item.quality,
                max_durability=item.max_durability,
                light=item.light,
                capacity=item.capacity,
                effects=cast(list[JsonObject], item.effects),
                value=item.value,
                category=item.category,
                mechanism_states=item.mechanism_states,
                mechanism_side_effects=cast(JsonObject, item.mechanism_side_effects),
                combination_side_effects=cast(
                    JsonObject, item.combination_side_effects
                ),
                context_commands={
                    verb: spec.model_dump()
                    for verb, spec in item.context_commands.items()
                },
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

    item_location = ItemLocationService(session)
    for room_item in document.room_items:
        item_location.spawn(
            room_item.item_id,
            Location("room", room_item.room_id),
            room_item.quantity,
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
                schedule=[e.model_dump() for e in npc.schedule],
                loot_table=cast(JsonObject, npc.loot_table),
                context_commands={
                    verb: spec.model_dump()
                    for verb, spec in npc.context_commands.items()
                },
                triggers=cast(list[JsonObject], npc.triggers),
                ai=cast(JsonObject, npc.ai),
            )
        )
        if npc.shop is not None:
            _import_shop(session, npc.id, npc.shop)
        if npc.bank is not None:
            _import_bank(session, npc.id, npc.bank)

    if document.economy is not None:
        _import_economy(session, document.economy)
    if document.progression is not None:
        _import_progression(session, document.progression)
    if document.transit is not None:
        _import_transit(session, document.transit)


def _import_progression(session: Session, progression: ProgressionConfigData) -> None:
    """Upsert the singleton `ProgressionConfig` row from authored YAML data."""
    existing = session.exec(select(ProgressionConfig)).first()
    if existing is None:
        session.add(
            ProgressionConfig(
                base=progression.base,
                step=progression.step,
                coins_per_level=progression.coins_per_level,
                skill_points_per_level=progression.skill_points_per_level,
            )
        )
    else:
        existing.base = progression.base
        existing.step = progression.step
        existing.coins_per_level = progression.coins_per_level
        existing.skill_points_per_level = progression.skill_points_per_level
        session.add(existing)


def _import_transit(session: Session, transit: TransitConfigData) -> None:
    for line in transit.lines:
        session.merge(
            TransitLine(
                id=line.id,
                name=line.name,
                mode=line.mode,
                service_type=line.service_type,
                vehicle_room_id=line.vehicle_room_id,
                ticket_item_id=line.ticket_item_id,
                ticket_consumed=line.ticket_consumed,
                reverses=line.reverses,
                loop=line.loop,
                animate_minimap=line.animate_minimap,
                weather_sensitive=line.weather_sensitive,
                blocking_weather=list(line.blocking_weather),
            )
        )
        session.flush()
        existing_stops = session.exec(
            select(TransitStop).where(TransitStop.line_id == line.id)
        ).all()
        by_sequence = {stop.sequence: stop for stop in existing_stops}
        for stop in line.stops:
            existing = by_sequence.pop(stop.sequence, None)
            if existing is not None:
                existing.room_id = stop.room_id
                existing.dwell_ticks = stop.dwell_ticks
                existing.travel_ticks = stop.travel_ticks
                existing.boarding = stop.boarding
                session.add(existing)
            else:
                session.add(
                    TransitStop(
                        line_id=line.id,
                        room_id=stop.room_id,
                        sequence=stop.sequence,
                        dwell_ticks=stop.dwell_ticks,
                        travel_ticks=stop.travel_ticks,
                        boarding=stop.boarding,
                    )
                )
        # Any previously-imported stop not present in this reimport is stale.
        for stale_stop in by_sequence.values():
            session.delete(stale_stop)


def _import_bank(session: Session, npc_id: str, bank: BankBranchData) -> None:
    session.merge(
        Bank(
            id=f"bank:{npc_id}",
            npc_id=npc_id,
            name=bank.name,
        )
    )


def _import_economy(session: Session, economy: EconomyConfigData) -> None:
    for region in economy.regions:
        session.merge(
            RegionPricing(
                zone=region.zone,
                region_mult=region.region_mult,
                bias=cast(JsonObject, region.bias),
            )
        )


def _import_shop(session: Session, npc_id: str, shop: ShopData) -> None:
    shop_id = f"shop:{npc_id}"
    is_new_shop = LedgerRepo(session).find("shop", shop_id) is None
    session.merge(
        Shop(
            id=shop_id,
            npc_id=npc_id,
            name=shop.name,
            buys_categories=shop.buys_categories,
            sell_ratio=shop.sell_ratio,
            region_mult=shop.region_mult,
        )
    )
    session.flush()
    if is_new_shop:
        LedgerService().credit(session, "shop", shop_id, shop.starting_coins)
    for entry in shop.stock:
        existing = session.exec(
            select(ShopStock).where(
                ShopStock.shop_id == shop_id, ShopStock.item_id == entry.item_id
            )
        ).first()
        if existing is not None:
            existing.quantity = entry.quantity
            existing.restock_to = entry.restock_to
            existing.restock_every_ticks = entry.restock_every_ticks
            session.add(existing)
        else:
            session.add(
                ShopStock(
                    shop_id=shop_id,
                    item_id=entry.item_id,
                    quantity=entry.quantity,
                    restock_to=entry.restock_to,
                    restock_every_ticks=entry.restock_every_ticks,
                )
            )


def _export_shop(session: Session, npc_id: str) -> ShopData | None:
    shop = session.exec(select(Shop).where(Shop.npc_id == npc_id)).first()
    if shop is None:
        return None
    stock = session.exec(select(ShopStock).where(ShopStock.shop_id == shop.id)).all()
    return ShopData(
        name=shop.name,
        buys_categories=list(shop.buys_categories),
        sell_ratio=shop.sell_ratio,
        region_mult=shop.region_mult,
        starting_coins=LedgerService().balance_of(session, "shop", shop.id),
        stock=[
            ShopStockData(
                item_id=entry.item_id,
                quantity=entry.quantity,
                restock_to=entry.restock_to,
                restock_every_ticks=entry.restock_every_ticks,
            )
            for entry in stock
        ],
    )


def _export_bank(session: Session, npc_id: str) -> BankBranchData | None:
    bank = session.exec(select(Bank).where(Bank.npc_id == npc_id)).first()
    if bank is None:
        return None
    return BankBranchData(name=bank.name)


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
            map_z=room.map_z,
            zone=room.zone,
            room_type=room.room_type,
            is_active=room.is_active,
            fallback_room_id=room.fallback_room_id,
            flags=cast(dict[str, object], room.flags),
            disabled_commands=list(room.disabled_commands),
            light_level=room.light_level,
            version=room.version,
            terrain=room.terrain,
            safe_rest=room.safe_rest,
            indoor=room.indoor,
            loot_table=cast(dict[str, object], room.loot_table),
            ambient_events=cast(list[dict[str, object]], room.ambient_events),
            triggers=cast(list[dict[str, object]], room.triggers),
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
            bound=item.bound,
            aliases=list(item.aliases),
            usable_with=list(item.usable_with),
            loot_table=cast(dict[str, object], item.loot_table),
            slot=item.slot,
            wearable=item.wearable,
            weight=item.weight,
            quality=item.quality,
            max_durability=item.max_durability,
            light=item.light,
            capacity=item.capacity,
            effects=cast(list[dict[str, object]], item.effects),
            value=item.value,
            category=item.category,
            mechanism_states=list(item.mechanism_states),
            mechanism_side_effects=cast(
                dict[str, dict[str, object]], item.mechanism_side_effects
            ),
            combination_side_effects=cast(
                dict[str, dict[str, object]], item.combination_side_effects
            ),
            context_commands={
                verb: ContextCommandData.model_validate(spec)
                for verb, spec in item.context_commands.items()
            },
        )
        for item in session.exec(select(Item)).all()
    ]

    room_item_data = [
        RoomItemData(
            room_id=str(stack.owner_id),
            item_id=stack.item_id,
            quantity=stack.quantity,
        )
        for stack in session.exec(
            select(ItemStack).where(ItemStack.owner_type == "room")
        ).all()
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
            shop=_export_shop(session, npc.id),
            bank=_export_bank(session, npc.id),
            context_commands={
                verb: ContextCommandData.model_validate(spec)
                for verb, spec in npc.context_commands.items()
            },
            triggers=cast(list[dict[str, object]], npc.triggers),
            ai=cast(dict[str, object], npc.ai),
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

    regions = session.exec(select(RegionPricing)).all()
    economy = (
        EconomyConfigData(
            regions=[
                RegionPricingData(
                    zone=region.zone,
                    region_mult=region.region_mult,
                    bias=cast(dict[str, float], region.bias),
                )
                for region in regions
            ]
        )
        if regions
        else None
    )

    progression_row = session.exec(select(ProgressionConfig)).first()
    progression = (
        ProgressionConfigData(
            base=progression_row.base,
            step=progression_row.step,
            coins_per_level=progression_row.coins_per_level,
            skill_points_per_level=progression_row.skill_points_per_level,
        )
        if progression_row is not None
        else None
    )

    lines = session.exec(select(TransitLine)).all()
    transit = (
        TransitConfigData(
            lines=[
                TransitLineData(
                    id=line.id,
                    name=line.name,
                    mode=line.mode,
                    service_type=line.service_type,
                    vehicle_room_id=line.vehicle_room_id,
                    ticket_item_id=line.ticket_item_id,
                    ticket_consumed=line.ticket_consumed,
                    reverses=line.reverses,
                    loop=line.loop,
                    animate_minimap=line.animate_minimap,
                    weather_sensitive=line.weather_sensitive,
                    blocking_weather=list(line.blocking_weather),
                    stops=[
                        TransitStopData(
                            room_id=stop.room_id,
                            sequence=stop.sequence,
                            dwell_ticks=stop.dwell_ticks,
                            travel_ticks=stop.travel_ticks,
                            boarding=stop.boarding,
                        )
                        for stop in session.exec(
                            select(TransitStop)
                            .where(TransitStop.line_id == line.id)
                            .order_by(TransitStop.sequence)  # type: ignore[arg-type]
                        ).all()
                    ],
                )
                for line in lines
            ]
        )
        if lines
        else None
    )

    return WorldDocument(
        rooms=room_data,
        items=item_data,
        room_items=room_item_data,
        npcs=npc_data,
        dialogue_trees=dialogue_tree_data,
        quests=quest_data,
        economy=economy,
        progression=progression,
        transit=transit,
    )
