"""Bootstrap an empty game database from authored world YAML."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.config import Settings
from lorecraft.models.player import Player
from lorecraft.models.world import Room, WorldMeta
from lorecraft.world.loader import load_world_yaml

log = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_world_yaml_path(path: str) -> Path:
    """Resolve a world YAML path relative to the repo root when not absolute."""
    candidate = Path(path)
    if candidate.is_dir():
        return candidate / "world.yaml"
    if candidate.is_file():
        return candidate
    repo_relative = _REPO_ROOT / path
    if repo_relative.is_dir():
        return repo_relative / "world.yaml"
    if repo_relative.is_file():
        return repo_relative
    return candidate


def ensure_world_bootstrapped(game_engine: Engine, settings: Settings) -> None:
    """Ensure WorldMeta exists; import YAML when the DB has no rooms; seed dev player."""
    with Session(game_engine) as session:
        if session.exec(select(WorldMeta)).first() is None:
            session.add(WorldMeta(schema_version=1))

        has_rooms = session.exec(select(Room)).first() is not None
        if not has_rooms:
            world_path = resolve_world_yaml_path(settings.world_yaml_path)
            if not world_path.is_file():
                log.warning(
                    "Database has no rooms and world YAML was not found: %s",
                    world_path,
                )
            else:
                log.info("Importing world from %s", world_path)
                load_world_yaml(world_path, session)

        ensure_seed_player(session, settings)
        ensure_seed_player(
            session,
            settings,
            player_id="player-2",
            username="player-2",
        )
        session.commit()


def ensure_seed_player(
    session: Session,
    settings: Settings,
    *,
    player_id: str | None = None,
    username: str | None = None,
) -> None:
    """Create a configured dev player when missing."""
    resolved_id = player_id or settings.seed_player_id
    if not resolved_id:
        return
    if session.get(Player, resolved_id) is not None:
        return
    start_room = settings.seed_player_start_room
    if session.get(Room, start_room) is None:
        log.warning(
            "Skipping seed player %s: start room %r not in database",
            resolved_id,
            start_room,
        )
        return
    session.add(
        Player(
            id=resolved_id,
            username=username or settings.seed_player_username,
            current_room_id=start_room,
            respawn_room_id=start_room,
            visited_rooms=[start_room],
        )
    )
