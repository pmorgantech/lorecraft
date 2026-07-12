#!/usr/bin/env python3
"""Import world_content/world.yaml into the Lorecraft game database.

Usage:
    python scripts/import_world.py [--world PATH] [--db PATH] [--fresh]

Options:
    --world PATH    Path to the world YAML file or directory (default: world_content)
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
from lorecraft.engine.models.player import Player  # noqa: E402
from lorecraft.engine.models.world import Room, WorldMeta  # noqa: E402
from lorecraft.engine.repos.stack_repo import StackRepo  # noqa: E402
from lorecraft.world.loader import load_world_yaml  # noqa: E402
from lorecraft.world.reseed import reseed_world_from_yaml  # noqa: E402
from lorecraft.config import Settings, load_settings  # noqa: E402
from lorecraft.world.bootstrap import ensure_seed_player  # noqa: E402


def _resolve_world_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_dir():
        return candidate / "world.yaml"
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--world",
        default="world_content",
        help="Path to world YAML file or directory",
    )
    parser.add_argument(
        "--db", default=None, help="Path to SQLite game DB (overrides settings)"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="Wipe world data before import"
    )
    args = parser.parse_args()

    world_path = _resolve_world_path(args.world)
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

    print("Importing world YAML …")
    if args.fresh:
        # Delegate the wipe + reimport to the shared reseed path so the CLI and
        # the admin endpoint can never drift on what "fresh" means. Dev players
        # are reset separately below, so no `settings` relocation is passed here.
        result = reseed_world_from_yaml(game_engine, world_path)
        print("  Wiped existing world data.")
        print(
            f"  Imported {result.rooms} rooms, {result.items} items, "
            f"{result.room_items} room placements, {result.npcs} npcs, "
            f"{result.quests} quests."
        )
    else:
        with Session(game_engine) as session:
            if session.exec(select(WorldMeta)).first() is None:
                session.add(WorldMeta(schema_version=1))
                session.flush()
            doc = load_world_yaml(world_path, session)
            session.commit()
        print(
            f"  Imported {len(doc.rooms)} rooms, {len(doc.items)} items, "
            f"{len(doc.room_items)} room placements, {len(doc.npcs)} npcs, "
            f"{len(doc.quests)} quests."
        )

    seed_settings = Settings(
        seed_player_id="player-1",
        seed_player_username="player-1",
        seed_player_start_room="village_square",
    )
    with Session(game_engine) as session:
        for dev_id in ("player-1", "player-2"):
            player = session.get(Player, dev_id)
            if player is None:
                ensure_seed_player(
                    session,
                    seed_settings,
                    player_id=dev_id,
                    username=dev_id,
                )
                print(
                    f"  Created test player '{dev_id}' at "
                    f"'{seed_settings.seed_player_start_room}'."
                )
            elif args.fresh:
                player.current_room_id = seed_settings.seed_player_start_room
                player.respawn_room_id = seed_settings.seed_player_start_room
                player.visited_rooms = [seed_settings.seed_player_start_room]
                for stack in StackRepo(session).stacks_for_owner("player", player.id):
                    session.delete(stack)
                player.flags = {}
                print(
                    f"  Reset test player '{dev_id}' to "
                    f"'{seed_settings.seed_player_start_room}'."
                )
        session.commit()

    print("Done.")


if __name__ == "__main__":
    main()
