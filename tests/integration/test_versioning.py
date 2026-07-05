"""Integration tests for world versioning (changeset lifecycle)."""

from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.models.changeset import ChangesetItem, ConflictScanResult
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Exit, Room, WorldMeta
from lorecraft.world.versioning import VersioningService


def _make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    audit_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_tables(
        game_engine=engine,
        audit_engine=audit_engine,
        settings=Settings(database_path=":memory:", audit_database_path=":memory:"),
    )
    return Session(engine)


def _seed_world(session: Session) -> None:
    session.add(WorldMeta(schema_version=1))
    session.add(Room(id="room_a", name="Room A", description=".", map_x=0, map_y=0))
    session.add(
        Room(
            id="room_b",
            name="Room B",
            description=".",
            map_x=1,
            map_y=0,
            fallback_room_id="room_a",
        )
    )
    session.add(Exit(room_id="room_a", direction="east", target_room_id="room_b"))
    session.add(
        Player(
            id="p1",
            username="alice",
            current_room_id="room_a",
            respawn_room_id="room_a",
            visited_rooms=["room_a"],
        )
    )
    session.commit()


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_changeset() -> None:
    with _make_session() as session:
        svc = VersioningService(session)
        cs = svc.create_changeset("Patch 1.1", "admin")
        session.commit()
        assert cs.id
        assert cs.name == "Patch 1.1"
        assert cs.status == "draft"
        assert cs.created_by == "admin"


def test_list_changesets() -> None:
    with _make_session() as session:
        svc = VersioningService(session)
        svc.create_changeset("A", "admin")
        svc.create_changeset("B", "admin")
        session.commit()
        changesets = svc.list_changesets()
    assert len(changesets) == 2


# ---------------------------------------------------------------------------
# Scan — no conflicts
# ---------------------------------------------------------------------------


def test_scan_empty_changeset_is_ready() -> None:
    with _make_session() as session:
        _seed_world(session)
        svc = VersioningService(session)
        cs = svc.create_changeset("Empty CS", "admin")
        session.commit()
        results = svc.scan_conflicts(cs.id)
        session.commit()
        assert svc.get_changeset(cs.id).status == "ready"
        assert results == []


# ---------------------------------------------------------------------------
# Scan — broken exit conflict
# ---------------------------------------------------------------------------


def test_scan_detects_broken_exit_when_deactivating_target_room() -> None:
    with _make_session() as session:
        _seed_world(session)
        svc = VersioningService(session)
        cs = svc.create_changeset("Deactivate B", "admin")
        svc.add_item(
            cs.id,
            ChangesetItem(
                changeset_id=cs.id,
                entity_type="room",
                entity_id="room_b",
                operation="deactivate",
                before_state={},
                after_state={},
            ),
        )
        session.commit()
        results = svc.scan_conflicts(cs.id)
        session.commit()
        # Read attributes while session is open
        error_descriptions = [r.description for r in results if r.severity == "ERROR"]

    assert any("room_b" in d or "east" in d for d in error_descriptions)


# ---------------------------------------------------------------------------
# Scan — displaced player
# ---------------------------------------------------------------------------


def test_scan_detects_player_in_deactivating_room() -> None:
    with _make_session() as session:
        _seed_world(session)
        svc = VersioningService(session)
        cs = svc.create_changeset("Remove A", "admin")
        svc.add_item(
            cs.id,
            ChangesetItem(
                changeset_id=cs.id,
                entity_type="room",
                entity_id="room_a",
                operation="deactivate",
                before_state={},
                after_state={},
            ),
        )
        session.commit()
        results = svc.scan_conflicts(cs.id)
        session.commit()
        # Read while session open
        player_warnings = [(r.severity, r.entity_type, r.description) for r in results]

    pw = [
        (sev, et, d)
        for sev, et, d in player_warnings
        if et == "player" and sev == "WARNING"
    ]
    assert len(pw) == 1
    assert "alice" in pw[0][2]


# ---------------------------------------------------------------------------
# Promotion
# ---------------------------------------------------------------------------


def test_promote_empty_changeset_bumps_schema_version() -> None:
    with _make_session() as session:
        _seed_world(session)
        svc = VersioningService(session)
        cs = svc.create_changeset("Version bump", "admin")
        session.commit()
        svc.scan_conflicts(cs.id)  # moves to "ready"
        session.commit()
        svc.promote(cs.id)
        session.commit()
        meta = session.exec(select(WorldMeta)).first()
        refreshed_cs = svc.get_changeset(cs.id)

    assert meta is not None
    assert meta.schema_version == 2
    assert refreshed_cs is not None
    assert refreshed_cs.status == "live"
    assert refreshed_cs.world_version == "2"


def test_promote_requires_ready_status() -> None:
    with _make_session() as session:
        _seed_world(session)
        svc = VersioningService(session)
        cs = svc.create_changeset("Draft CS", "admin")
        session.commit()
        with pytest.raises(ValueError, match="ready"):
            svc.promote(cs.id)


def test_promote_update_room_changes_name_in_db() -> None:
    with _make_session() as session:
        _seed_world(session)
        svc = VersioningService(session)
        cs = svc.create_changeset("Rename A", "admin")
        svc.add_item(
            cs.id,
            ChangesetItem(
                changeset_id=cs.id,
                entity_type="room",
                entity_id="room_a",
                operation="update",
                before_state={"name": "Room A"},
                after_state={"name": "Renamed Room A"},
            ),
        )
        session.commit()
        svc.scan_conflicts(cs.id)
        session.commit()
        svc.promote(cs.id)
        session.commit()
        room = session.get(Room, "room_a")

    assert room is not None
    assert room.name == "Renamed Room A"


def test_promote_deactivate_displaces_player_to_fallback() -> None:
    with _make_session() as session:
        _seed_world(session)
        # Move player to room_b (has fallback_room_id="room_a")
        p = session.get(Player, "p1")
        assert p is not None
        p.current_room_id = "room_b"
        session.commit()

        svc = VersioningService(session)
        cs = svc.create_changeset("Deactivate B", "admin")
        svc.add_item(
            cs.id,
            ChangesetItem(
                changeset_id=cs.id,
                entity_type="room",
                entity_id="room_b",
                operation="deactivate",
                before_state={},
                after_state={},
            ),
        )
        session.commit()
        svc.scan_conflicts(cs.id)
        session.commit()

        # Acknowledge the broken exit error manually (since room_a exits to room_b)
        conflict = session.exec(
            select(ConflictScanResult).where(ConflictScanResult.changeset_id == cs.id)
        ).first()
        # Deactivating room_b creates broken exit from room_a — mark it acknowledged
        if conflict and conflict.severity == "ERROR":
            conflict.acknowledged = True
            session.commit()
            # Re-scan to see if acknowledged errors clear the "conflicts" status
            cs_obj = svc.get_changeset(cs.id)
            if cs_obj:
                cs_obj.status = "ready"
                session.commit()

        svc.promote(cs.id)
        session.commit()
        player = session.get(Player, "p1")
        room = session.get(Room, "room_b")

    assert player is not None
    assert player.current_room_id == "room_a"  # displaced to fallback
    assert room is not None
    assert not room.is_active


def test_promote_deactivate_updates_connection_manager_tracking() -> None:
    """A displaced player's ConnectionManager room-tracking must move in step
    with the DB, or `broadcast_to_room` keeps targeting the now-inactive room
    for them until their next `move()` call happens to self-heal it."""
    with _make_session() as session:
        _seed_world(session)
        p = session.get(Player, "p1")
        assert p is not None
        p.current_room_id = "room_b"
        session.commit()

        manager = ConnectionManager()
        manager.move_player("p1", None, "room_b")
        assert manager.players_in_room("room_b") == ["p1"]

        svc = VersioningService(session)
        cs = svc.create_changeset("Deactivate B", "admin")
        svc.add_item(
            cs.id,
            ChangesetItem(
                changeset_id=cs.id,
                entity_type="room",
                entity_id="room_b",
                operation="deactivate",
                before_state={},
                after_state={},
            ),
        )
        session.commit()
        svc.scan_conflicts(cs.id)
        session.commit()

        conflict = session.exec(
            select(ConflictScanResult).where(ConflictScanResult.changeset_id == cs.id)
        ).first()
        if conflict and conflict.severity == "ERROR":
            conflict.acknowledged = True
            session.commit()
            cs_obj = svc.get_changeset(cs.id)
            if cs_obj:
                cs_obj.status = "ready"
                session.commit()

        svc.promote(cs.id, manager=manager)
        session.commit()

    assert manager.players_in_room("room_b") == []
    assert manager.players_in_room("room_a") == ["p1"]
