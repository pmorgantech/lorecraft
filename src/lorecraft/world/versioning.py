"""Changeset lifecycle: create, scan conflicts, promote atomically."""

from __future__ import annotations

import time
import uuid

from sqlmodel import Session, select

from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.models.changeset import (
    Changeset,
    ChangesetItem,
    ConflictScanResult,
    WorldMigration,
)
from lorecraft.models.items import ItemStack
from lorecraft.models.player import Player
from lorecraft.models.world import Exit, Item, Room, WorldMeta
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.item_location import ItemLocationService


class VersioningService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Changeset CRUD
    # ------------------------------------------------------------------

    def create_changeset(self, name: str, created_by: str) -> Changeset:
        cs = Changeset(
            id=str(uuid.uuid4()),
            name=name,
            status="draft",
            created_by=created_by,
            created_at=time.time(),
        )
        self._session.add(cs)
        return cs

    def get_changeset(self, changeset_id: str) -> Changeset | None:
        return self._session.get(Changeset, changeset_id)

    def list_changesets(self) -> list[Changeset]:
        return list(self._session.exec(select(Changeset)).all())

    def add_item(self, changeset_id: str, item: ChangesetItem) -> ChangesetItem:
        item.changeset_id = changeset_id
        self._session.add(item)
        return item

    def list_items(self, changeset_id: str) -> list[ChangesetItem]:
        return list(
            self._session.exec(
                select(ChangesetItem).where(ChangesetItem.changeset_id == changeset_id)
            ).all()
        )

    # ------------------------------------------------------------------
    # Conflict scanner
    # ------------------------------------------------------------------

    def scan_conflicts(self, changeset_id: str) -> list[ConflictScanResult]:
        cs = self._session.get(Changeset, changeset_id)
        if cs is None:
            raise ValueError(f"Changeset {changeset_id!r} not found")

        # Clear previous results
        existing = self._session.exec(
            select(ConflictScanResult).where(
                ConflictScanResult.changeset_id == changeset_id
            )
        ).all()
        for row in existing:
            self._session.delete(row)

        items = self.list_items(changeset_id)
        results: list[ConflictScanResult] = []

        deactivating_room_ids = {
            it.entity_id
            for it in items
            if it.entity_type == "room" and it.operation == "deactivate"
        }
        deleting_item_ids = {
            it.entity_id
            for it in items
            if it.entity_type == "item" and it.operation == "delete"
        }

        # 1. Broken exits: exits pointing to rooms being deactivated
        for room_id in deactivating_room_ids:
            target_room = self._session.get(Room, room_id)
            broken_exits = self._session.exec(
                select(Exit).where(Exit.target_room_id == room_id)
            ).all()
            for exit_ in broken_exits:
                if exit_.room_id in deactivating_room_ids:
                    continue  # source room also deactivating — not a conflict
                source_room = self._session.get(Room, exit_.room_id)
                source_name = source_room.name if source_room else exit_.room_id
                target_name = target_room.name if target_room else room_id
                results.append(
                    ConflictScanResult(
                        changeset_id=changeset_id,
                        entity_type="exit",
                        entity_id=str(exit_.id),
                        severity="ERROR",
                        auto_resolvable=False,
                        description=(
                            f"Exit {exit_.direction!r} from {source_name!r} points to "
                            f"{target_name!r} which is being deactivated."
                        ),
                    )
                )

        # 2. Players in rooms being deactivated
        all_players = self._session.exec(select(Player)).all()
        for player in all_players:
            if player.current_room_id in deactivating_room_ids:
                room = self._session.get(Room, player.current_room_id)
                fallback_id = room.fallback_room_id if room else None
                auto_resolvable = fallback_id is not None
                results.append(
                    ConflictScanResult(
                        changeset_id=changeset_id,
                        entity_type="player",
                        entity_id=player.id,
                        severity="WARNING",
                        auto_resolvable=auto_resolvable,
                        description=(
                            f"Player {player.username!r} is in {player.current_room_id!r} "
                            f"which is being deactivated."
                            + (
                                f" Will be displaced to {fallback_id!r}."
                                if auto_resolvable
                                else " No fallback_room_id configured."
                            )
                        ),
                    )
                )

        # 3. Players holding items being deleted
        stack_repo = StackRepo(self._session)
        for item_id in deleting_item_ids:
            for player in all_players:
                if stack_repo.quantity_of(Location("player", player.id), item_id) > 0:
                    results.append(
                        ConflictScanResult(
                            changeset_id=changeset_id,
                            entity_type="item",
                            entity_id=item_id,
                            severity="WARNING",
                            auto_resolvable=True,
                            description=(
                                f"Player {player.username!r} holds item {item_id!r} "
                                "which is being deleted. Item will be removed from inventory."
                            ),
                        )
                    )

        for r in results:
            self._session.add(r)

        has_errors = any(r.severity == "ERROR" and not r.acknowledged for r in results)
        cs.status = "conflicts" if has_errors else "ready"
        self._session.add(cs)

        return results

    # ------------------------------------------------------------------
    # Promotion
    # ------------------------------------------------------------------

    def promote(
        self,
        changeset_id: str,
        bus: EventBus | None = None,
        manager: ConnectionManager | None = None,
    ) -> None:
        cs = self._session.get(Changeset, changeset_id)
        if cs is None:
            raise ValueError(f"Changeset {changeset_id!r} not found")
        if cs.status != "ready":
            raise ValueError(
                f"Changeset must be in 'ready' status to promote (current: {cs.status!r})"
            )

        items = self.list_items(changeset_id)

        # Apply each change
        for item in items:
            self._apply_item(item, manager=manager)

        # Bump WorldMeta schema_version
        meta = self._session.exec(select(WorldMeta)).first()
        if meta is None:
            meta = WorldMeta(schema_version=1)
            self._session.add(meta)
        new_version = meta.schema_version + 1
        meta.schema_version = new_version

        # Record migration
        migration = WorldMigration(
            from_version=new_version - 1,
            to_version=new_version,
            migration_type="changeset_promote",
            payload={"changeset_id": changeset_id},
            applied_at=time.time(),
        )
        self._session.add(migration)

        # Mark changeset live
        cs.status = "live"
        cs.promoted_at = time.time()
        cs.world_version = str(new_version)
        self._session.add(cs)

        if bus is not None:
            bus.emit(
                Event(
                    GameEvent.WORLD_CHANGESET_PROMOTED,
                    {"changeset_id": changeset_id, "world_version": new_version},
                ),
                None,
            )

    def _apply_item(
        self, item: ChangesetItem, manager: ConnectionManager | None = None
    ) -> None:
        op = item.operation
        etype = item.entity_type

        if etype == "room":
            self._apply_room(item, op, manager=manager)
        elif etype == "item":
            self._apply_item_entity(item, op)
        elif etype == "exit":
            self._apply_exit(item, op)

    def _apply_room(
        self, item: ChangesetItem, op: str, manager: ConnectionManager | None = None
    ) -> None:
        room = self._session.get(Room, item.entity_id)
        if op == "create":
            if room is None:
                after = item.after_state
                new_room = Room(
                    id=item.entity_id,
                    name=str(after.get("name", "")),
                    description=str(after.get("description", "")),
                    map_x=int(after.get("map_x", 0)),  # type: ignore[arg-type]
                    map_y=int(after.get("map_y", 0)),  # type: ignore[arg-type]
                )
                self._session.add(new_room)
        elif op == "update" and room is not None:
            after = item.after_state
            for field_name, value in after.items():
                if hasattr(room, field_name):
                    setattr(room, field_name, value)
            room.version += 1
            self._session.add(room)
        elif op == "delete" and room is not None:
            self._session.delete(room)
        elif op == "activate" and room is not None:
            room.is_active = True
            self._session.add(room)
        elif op == "deactivate" and room is not None:
            room.is_active = False
            self._session.add(room)
            # Displace players
            if room.fallback_room_id:
                players = self._session.exec(
                    select(Player).where(Player.current_room_id == item.entity_id)
                ).all()
                for player in players:
                    player.current_room_id = room.fallback_room_id
                    self._session.add(player)
                    # Keep ConnectionManager's room-tracking in sync with the DB
                    # move — otherwise a connected player's broadcast targeting
                    # stays pointed at the now-inactive room until their next
                    # `move()` call happens to self-heal it.
                    if manager is not None:
                        manager.move_player(
                            player.id, item.entity_id, room.fallback_room_id
                        )
            # Remove held items for players (handled in _apply_item_entity for delete op)

    def _apply_item_entity(self, item: ChangesetItem, op: str) -> None:
        entity = self._session.get(Item, item.entity_id)
        if op == "create":
            if entity is None:
                after = item.after_state
                new_item = Item(
                    id=item.entity_id,
                    name=str(after.get("name", "")),
                    description=str(after.get("description", "")),
                )
                self._session.add(new_item)
        elif op == "update" and entity is not None:
            for field_name, value in item.after_state.items():
                if hasattr(entity, field_name):
                    setattr(entity, field_name, value)
            self._session.add(entity)
        elif op == "delete" and entity is not None:
            # Remove every stack of this item (any holder — player, room, container)
            # first: ItemStack.item_id FKs to item.id, so orphans would break the
            # delete outright.
            item_location = ItemLocationService(self._session)
            stacks = self._session.exec(
                select(ItemStack).where(ItemStack.item_id == item.entity_id)
            ).all()
            for stack in stacks:
                assert stack.id is not None
                item_location.destroy(stack.id, stack.quantity)
            self._session.delete(entity)

    def _apply_exit(self, item: ChangesetItem, op: str) -> None:
        if op == "create":
            after = item.after_state
            new_exit = Exit(
                room_id=str(after.get("room_id", "")),
                direction=str(after.get("direction", "")),
                target_room_id=str(after.get("target_room_id", "")),
            )
            self._session.add(new_exit)
        elif op in ("delete", "deactivate"):
            try:
                exit_id = int(item.entity_id)
            except ValueError:
                return
            exit_ = self._session.get(Exit, exit_id)
            if exit_ is not None:
                self._session.delete(exit_)
