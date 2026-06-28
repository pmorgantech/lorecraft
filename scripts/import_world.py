#!/usr/bin/env python3
"""Import world_content/world.yaml into the Lorecraft game database.

Usage:
    python scripts/import_world.py [--world PATH] [--db PATH] [--fresh]

Options:
    --world PATH    Path to the world YAML file (default: world_content/world.yaml)
    --db    PATH    Path to the SQLite database  (default: game.db)
    --fresh         Wipe existing rooms/exits/items/room_items before import.
                    Without this flag the script will abort if any rooms exist,
                    to avoid accidental double-imports on a live world.

After import, ensures a test player 'player-1' exists at the starting room
(village_square) if no players are present yet.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make sure the package is importable when run from the repo root.
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

from sqlmodel import Session, create_engine, select  # noqa: E402

from lorecraft.db import create_tables  # noqa: E402
from lorecraft.models.world import Exit, Item, Room, RoomItem, WorldMeta  # noqa: E402
from lorecraft.models.player import Player  # noqa: E402
from lorecraft.world.loader import load_world_yaml  # noqa: E402
from lorecraft.config import load_settings  # noqa: E402


def _wipe_world(session: Session) -> None:
    """Delete all room-placement and structural world data."""
    for ri in session.exec(select(RoomItem)).all():
        session.delete(ri)
    for ex in session.exec(select(Exit)).all():
        session.delete(ex)
    session.flush()
    for item in session.exec(select(Item)).all():
        session.delete(item)
    for room in session.exec(select(Room)).all():
        session.delete(room)
    session.flush()
    print("  Wiped existing world data.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--world", default="world_content/world.yaml", help="Path to world YAML"
    )
    parser.add_argument(
        "--db", default=None, help="Path to SQLite game DB (overrides settings)"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="Wipe world data before import"
    )
    args = parser.parse_args()

    world_path = Path(args.world)
    if not world_path.exists():
        sys.exit(f"Error: world file not found: {world_path}")

    # Determine DB path
    if args.db:
        db_url = f"sqlite:///{args.db}"
    else:
        settings = load_settings()
        db_url = f"sqlite:///{settings.database_path}"

    print(f"Database : {db_url}")
    print(f"World    : {world_path}")

    game_engine = create_engine(db_url, connect_args={"check_same_thread": False})
    audit_engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    create_tables(game_engine=game_engine, audit_engine=audit_engine)

    with Session(game_engine) as session:
        existing_rooms = session.exec(select(Room)).first()
        if existing_rooms and not args.fresh:
            sys.exit(
                "Error: rooms already exist in the database.\n"
                "Use --fresh to wipe and re-import, or point --db at a new file."
            )

        if args.fresh:
            _wipe_world(session)

        # Ensure WorldMeta singleton
        if session.exec(select(WorldMeta)).first() is None:
            session.add(WorldMeta(schema_version=1))
            session.flush()

        print("Importing world YAML …")
        doc = load_world_yaml(world_path, session)
        session.commit()

    print(
        f"  Imported {len(doc.rooms)} rooms, {len(doc.items)} items, {len(doc.room_items)} room placements."
    )

    # Ensure a test player exists
    with Session(game_engine) as session:
        if session.exec(select(Player)).first() is None:
            starting_room = "village_square"
            session.add(
                Player(
                    id="player-1",
                    username="player-1",
                    current_room_id=starting_room,
                    respawn_room_id=starting_room,
                    visited_rooms=[starting_room],
                )
            )
            session.commit()
            print(f"  Created test player 'player-1' at '{starting_room}'.")
        else:
            print("  Player(s) already exist — skipping player seed.")

    print("Done.")


if __name__ == "__main__":
    main()
