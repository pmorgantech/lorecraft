---
kindle_doc_weaver: ignore
---

# World Versioning & Changesets Implementation Guide

## Overview

The changeset system allows admins to group world edits (new rooms, renamed NPCs, disabled areas) into atomic, versioned units before deploying them to live players. It handles conflicts, lazy migration for players with stale state, and rollback.

---

## Core Concepts

### World Schema Version

**GlobalVersion:** `WorldMeta.schema_version` — a single integer that increments on every changeset promotion. All players track their own `Player.world_schema_version`.

**PlayerVersion:** When a player logs in, if `Player.world_schema_version < WorldMeta.schema_version`, apply all pending migrations to their state before loading them.

**Why:** A player's saved quest flag "cave_entrance_unlocked" can be renamed without breaking their save. Migrations rewrite old flag names on login.

---

## Changeset Lifecycle

```
DRAFT → SCANNING → (CONFLICTS | READY) → LIVE → (ROLLED_BACK)
```

### 1. DRAFT

Admin groups edits into a named changeset. Rooms, items, NPCs can be in `is_active=False` within the changeset (invisible to players until promoted).

```python
@dataclass
class Changeset(SQLModel, table=True):
    id: str = Field(primary_key=True)  # UUID
    name: str                          # "Expand the catacombs", etc.
    status: str = "draft"              # draft|scanning|conflicts|ready|live|rolled_back
    created_by: str                    # admin user ID
    created_at: float
    promoted_at: Optional[float] = None
    world_version: Optional[str] = None  # e.g. "1.2.0" — set on promotion

    # Builder-mode clone path (see Builder Mode section below)
    builder_db_path: Optional[str] = None  # path to changeset's private SQLite clone


@dataclass
class ChangesetItem(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    changeset_id: str = Field(index=True)
    entity_type: str        # room|item|npc|flag|exit
    entity_id: str
    operation: str          # create|update|delete|activate|deactivate
    before_state: dict = Field(default_factory=dict, sa_column=Column(JSON))
    after_state: dict = Field(default_factory=dict, sa_column=Column(JSON))
```

Edits are **not immediately live**. They're staged in the `ChangesetItem` table. If an entity is in `is_active=False` state within the changeset, players can't see it.

### 2. SCANNING

Admin triggers conflict scanner. The scanner checks:

- **Broken exit references:** Target room deactivated/deleted → ERROR
- **Players in deactivating rooms:** Auto-resolvable by fallback room, but surface as WARNING
- **Renamed flags in active quests:** Flag condition references old name → ERROR
- **Items held by players being deleted:** Items returning to world or disappearing → WARNING
- **Quest stages referencing removed NPCs:** Stage condition → ERROR

```python
@dataclass
class ConflictScanResult(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    changeset_id: str = Field(index=True)
    entity_type: str
    entity_id: str
    severity: str          # ERROR|WARNING|INFO
    auto_resolvable: bool
    acknowledged: bool = False
    description: str


async def scan_changeset(changeset_id: str, db: Session):
    """
    Check for conflicts between changeset edits and live world state.
    """
    changeset = db.query(Changeset).filter(Changeset.id == changeset_id).first()
    if not changeset:
        raise ValueError("Changeset not found")

    changeset.status = "scanning"
    db.commit()

    conflicts = []

    # 1. Check exit references
    for item in db.query(ChangesetItem).filter(
        ChangesetItem.changeset_id == changeset_id,
        ChangesetItem.entity_type == "exit"
    ).all():
        if item.operation == "create" or item.operation == "update":
            target_room_id = item.after_state.get("target_room_id")
            target_exists = db.query(Room).filter(
                Room.id == target_room_id
            ).first()
            if not target_exists:
                conflicts.append(ConflictScanResult(
                    changeset_id=changeset_id,
                    entity_type="exit",
                    entity_id=item.entity_id,
                    severity="ERROR",
                    auto_resolvable=False,
                    description=f"Exit {item.entity_id} references nonexistent room {target_room_id}"
                ))

    # 2. Check for players in deactivating rooms
    for item in db.query(ChangesetItem).filter(
        ChangesetItem.changeset_id == changeset_id,
        ChangesetItem.entity_type == "room",
        ChangesetItem.operation == "deactivate"
    ).all():
        room_id = item.entity_id
        players_in_room = db.query(Player).filter(
            Player.current_room_id == room_id
        ).all()
        for player in players_in_room:
            room = db.query(Room).filter(Room.id == room_id).first()
            fallback = room.fallback_room_id
            conflicts.append(ConflictScanResult(
                changeset_id=changeset_id,
                entity_type="room",
                entity_id=room_id,
                severity="WARNING",
                auto_resolvable=bool(fallback),
                description=f"Player {player.username} in room {room_id} (auto-displace to {fallback})" if fallback else f"Player {player.username} in room {room_id} (no fallback)"
            ))

    # 3. Check for renamed flags in active quests
    quest_flags = {}
    for quest in db.query(Quest).all():
        for stage in quest.stages:
            for condition in stage.get("conditions", []):
                if condition.get("type") == "flag_set":
                    old_flag = condition.get("flag")
                    quest_flags[old_flag] = quest.id

    for item in db.query(ChangesetItem).filter(
        ChangesetItem.changeset_id == changeset_id,
        ChangesetItem.entity_type == "flag",
        ChangesetItem.operation == "update"
    ).all():
        old_name = item.before_state.get("name")
        new_name = item.after_state.get("name")
        if old_name in quest_flags:
            conflicts.append(ConflictScanResult(
                changeset_id=changeset_id,
                entity_type="flag",
                entity_id=old_name,
                severity="ERROR",
                auto_resolvable=False,
                description=f"Flag {old_name} renamed to {new_name}; quest {quest_flags[old_name]} references old name"
            ))

    # Save conflicts
    for conflict in conflicts:
        db.add(conflict)

    # Update changeset status
    has_errors = any(c.severity == "ERROR" for c in conflicts)
    changeset.status = "conflicts" if has_errors else "ready"
    db.commit()

    return conflicts
```

### 3. CONFLICTS or READY

- **CONFLICTS:** At least one ERROR found. Admin must resolve before re-scan.
- **READY:** Scan clean or all auto-resolvable conflicts acknowledged. Admin can promote.

### 4. LIVE

Changeset promoted atomically. All changes applied simultaneously:

```python
async def promote_changeset(changeset_id: str, db: Session):
    """
    Promote changeset to live. Atomically apply all edits.
    """
    changeset = db.query(Changeset).filter(
        Changeset.id == changeset_id
    ).first()

    if changeset.status not in ("ready",):
        raise ValueError(f"Cannot promote from status {changeset.status}")

    # 1. Apply all ChangesetItem edits
    for item in db.query(ChangesetItem).filter(
        ChangesetItem.changeset_id == changeset_id
    ).all():
        if item.entity_type == "room":
            if item.operation == "create":
                room = Room(**item.after_state)
                db.add(room)
            elif item.operation == "update":
                room = db.query(Room).filter(Room.id == item.entity_id).first()
                for key, value in item.after_state.items():
                    setattr(room, key, value)
            elif item.operation == "delete":
                room = db.query(Room).filter(Room.id == item.entity_id).first()
                db.delete(room)
            elif item.operation == "activate":
                room = db.query(Room).filter(Room.id == item.entity_id).first()
                room.is_active = True
            elif item.operation == "deactivate":
                room = db.query(Room).filter(Room.id == item.entity_id).first()
                room.is_active = False
                # Auto-displace players
                players = db.query(Player).filter(
                    Player.current_room_id == room.id
                ).all()
                for player in players:
                    fallback_id = room.fallback_room_id or config.SPAWN_ROOM_ID
                    player.current_room_id = fallback_id
                    # Notify player
                    audit_service.record(
                        ctx=None,
                        event_type=GameEvent.PLAYER_MOVED,
                        target_id=player.id,
                        severity="INFO",
                        summary=f"{player.username} displaced from {room.id} to {fallback_id} due to changeset promotion"
                    )
        # Similar for other entity types...

    # 2. Increment world version
    world_meta = db.query(WorldMeta).first()
    old_version = world_meta.schema_version
    world_meta.schema_version += 1

    # 3. Create migration record (for lazy player migration)
    migration = WorldMigration(
        from_version=old_version,
        to_version=world_meta.schema_version,
        migration_type="changeset",
        payload={
            "changeset_id": changeset_id,
            "changeset_name": changeset.name,
            "items": [
                {
                    "entity_type": item.entity_type,
                    "entity_id": item.entity_id,
                    "operation": item.operation,
                    "before_state": item.before_state,
                    "after_state": item.after_state,
                }
                for item in db.query(ChangesetItem).filter(
                    ChangesetItem.changeset_id == changeset_id
                ).all()
            ]
        },
        applied_at=time.time()
    )
    db.add(migration)

    # 4. Update changeset
    changeset.status = "live"
    changeset.promoted_at = time.time()
    changeset.world_version = f"{world_meta.schema_version}.0.0"

    db.commit()

    # 5. Notify connected players
    await connection_manager.broadcast_to_all({
        "type": "world_changeset_promoted",
        "changeset_name": changeset.name,
        "world_version": changeset.world_version
    })

    # 6. Emit event for hooks
    bus.emit(GameEvent.WORLD_CHANGESET_PROMOTED, {
        "changeset_id": changeset_id,
        "world_version": world_meta.schema_version
    })
```

### 5. ROLLED_BACK

Changesets can be rolled back by re-importing the previous YAML snapshot and bumping the schema version again. This is a manual process coordinated with admin.

---

## Builder Mode

When a changeset enters **DRAFT**, a separate SQLite clone is created. Admins using the builder UI or TUI edit this clone in isolation. Ghost sessions connect to the builder clone to preview pending changes without affecting live players.

### Builder Database Clone

```python
async def create_builder_clone(changeset_id: str):
    """
    Clone the current game.db to a changeset-scoped builder database.
    """
    original_db_path = config.DB_PATH  # e.g., "game.db"
    builder_db_path = f"builder_{changeset_id}.db"

    # Copy the database file
    shutil.copy2(original_db_path, builder_db_path)

    # Update changeset record
    changeset = db.query(Changeset).filter(
        Changeset.id == changeset_id
    ).first()
    changeset.builder_db_path = builder_db_path
    db.commit()

    return builder_db_path
```

### Ghost Sessions

Ghost sessions are special player connections tied to a specific changeset:

```python
@dataclass
class GhostSession:
    player_id: str
    session_id: str
    changeset_id: str
    builder_db: Session  # Connection to builder clone
    websocket: WebSocket


async def connect_ghost_session(player_id: str, changeset_id: str):
    """
    Create a ghost session for preview.
    """
    changeset = db.query(Changeset).filter(
        Changeset.id == changeset_id
    ).first()

    if not changeset or not changeset.builder_db_path:
        raise ValueError("Changeset has no builder clone")

    # Connect to builder database
    engine = create_engine(f"sqlite:///{changeset.builder_db_path}")
    builder_session = sessionmaker(bind=engine)()

    # Create ghost session record
    ghost = GhostSession(
        player_id=player_id,
        session_id=str(uuid.uuid4()),
        changeset_id=changeset_id,
        builder_db=builder_session,
        websocket=None  # Set on WebSocket connect
    )

    return ghost
```

### Key Distinction: Ghost Sessions Don't Emit Audit Events

Ghost sessions run against the builder clone and **never create audit log entries**. When testing a changeset, the engine instance points to a throwaway `/dev/null`-equivalent audit sink, not `audit.db`.

---

## Lazy Player Migration

When a player logs in, their `Player.world_schema_version` is checked:

```python
async def load_player_with_migrations(player_id: str, db: Session):
    """
    Load player and apply any pending migrations.
    """
    player = db.query(Player).filter(Player.id == player_id).first()

    world_meta = db.query(WorldMeta).first()

    if player.world_schema_version < world_meta.schema_version:
        # Apply migrations
        migrations = db.query(WorldMigration).filter(
            WorldMigration.from_version >= player.world_schema_version,
            WorldMigration.to_version <= world_meta.schema_version
        ).order_by(WorldMigration.from_version).all()

        for migration in migrations:
            apply_migration(player, migration)

        player.world_schema_version = world_meta.schema_version
        db.commit()

    return player


def apply_migration(player: Player, migration: WorldMigration):
    """
    Apply a specific migration to a player's state.
    """
    payload = migration.payload

    # Example: rename a flag
    if "flag_renames" in payload:
        for old_name, new_name in payload["flag_renames"].items():
            if old_name in player.flags:
                player.flags[new_name] = player.flags.pop(old_name)

    # Example: remove a flag
    if "flag_deletes" in payload:
        for flag_name in payload["flag_deletes"]:
            player.flags.pop(flag_name, None)
```

---

## Optimistic Locking

All world entity tables have a `version: int` field. When an admin edits a room, the form includes the `version` they read. If the DB version differs at write time → 409 Conflict.

```python
@dataclass
class Room(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    # ...
    version: int = 1  # Increment on every edit


@app.put("/admin/world/rooms/{room_id}")
async def edit_room(room_id: str, body: RoomEditRequest):
    """
    body.version must match the current DB version.
    """
    room = db.query(Room).filter(Room.id == room_id).first()

    if room.version != body.version:
        # Conflict — show diff to admin
        return {
            "status": "conflict",
            "current_version": room.version,
            "current_state": room.dict(),
            "diff": compute_diff(room, body)
        }

    # Update allowed
    room.name = body.name
    room.description = body.description
    room.version += 1
    db.commit()

    return {"status": "ok", "version": room.version}
```

---

## Configuration

```python
# config.py
BUILDER_DB_ROOT = os.getenv("BUILDER_DB_ROOT", "./builder_dbs/")
CHANGESET_SCAN_TIMEOUT_SECONDS = int(os.getenv("CHANGESET_SCAN_TIMEOUT_SECONDS", "30"))
```

---

## Testing

```python
@pytest.mark.asyncio
async def test_changeset_draft_to_live():
    """Verify full changeset lifecycle."""
    db = create_in_memory_db()

    # 1. Create changeset
    changeset = Changeset(
        id="cs_001",
        name="Add catacombs",
        status="draft",
        created_by="admin1",
        created_at=time.time()
    )
    db.add(changeset)
    db.commit()

    # 2. Add edit
    item = ChangesetItem(
        changeset_id="cs_001",
        entity_type="room",
        entity_id="catacombs_entrance",
        operation="create",
        after_state={
            "name": "Catacombs Entrance",
            "description": "Dark stone stairs descend...",
            "map_x": 10,
            "map_y": 10,
            "is_active": False,
        }
    )
    db.add(item)
    db.commit()

    # 3. Scan
    conflicts = await scan_changeset("cs_001", db)
    assert len(conflicts) == 0
    assert db.query(Changeset).filter(Changeset.id == "cs_001").first().status == "ready"

    # 4. Promote
    old_version = db.query(WorldMeta).first().schema_version
    await promote_changeset("cs_001", db)
    new_version = db.query(WorldMeta).first().schema_version

    assert new_version > old_version
    assert db.query(Changeset).filter(Changeset.id == "cs_001").first().status == "live"
    assert db.query(Room).filter(Room.id == "catacombs_entrance").first() is not None
```

---

*See also: [architecture.md § Persistence](../engine/architecture.md#persistence)*
