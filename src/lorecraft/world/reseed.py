"""Wipe and reseed the game database from authored world YAML.

Single source of truth for the destructive "fresh import" path, shared by
`scripts/import_world.py` (the CLI `--fresh` flag, also used by `start.sh`) and
the admin reseed endpoint (`webui/admin/routers/world.py`). Both call the same
`wipe_world` + `import_world` pair so the wipe set never drifts between them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from lorecraft.config import Settings
from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Exit, Item, NPC, Room, WorldMeta
from lorecraft.features.npc.models import DialogueTree
from lorecraft.features.quests.models import PlayerQuestProgress, Quest
from lorecraft.world.loader import import_world
from lorecraft.world.validator import WorldDocument, validate_world_document
from lorecraft.world.yaml_io import load_world_yaml_text

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReseedResult:
    """Counts summarising a completed reseed."""

    rooms: int
    items: int
    room_items: int
    npcs: int
    quests: int
    relocated_players: int


def wipe_world(session: Session) -> None:
    """Delete world content: rooms, exits, items, room item stacks, NPCs,
    dialogue trees, quests, and per-player quest progress.

    Player rows, their inventories, accounts, and audit data are left intact —
    only authored world content is removed so it can be reimported from YAML.
    """
    for progress in session.exec(select(PlayerQuestProgress)).all():
        session.delete(progress)
    for npc in session.exec(select(NPC)).all():
        session.delete(npc)
    for tree in session.exec(select(DialogueTree)).all():
        session.delete(tree)
    for quest in session.exec(select(Quest)).all():
        session.delete(quest)
    for stack in session.exec(
        select(ItemStack).where(ItemStack.owner_type == "room")
    ).all():
        session.delete(stack)
    for ex in session.exec(select(Exit)).all():
        session.delete(ex)
    session.flush()
    for item in session.exec(select(Item)).all():
        session.delete(item)
    for room in session.exec(select(Room)).all():
        session.delete(room)
    session.flush()


def load_and_validate_world(world_path: str | Path) -> WorldDocument:
    """Parse and validate a world YAML file *before* any destructive write.

    Raises `WorldValidationError` on malformed input without touching the DB, so
    a bad `world.yaml` can never leave the database half-wiped or half-applied.
    """
    text = Path(world_path).read_text(encoding="utf-8")
    data = load_world_yaml_text(text) or {}
    return validate_world_document(data)


def reseed_world_from_document(
    game_engine: Engine,
    document: WorldDocument,
    *,
    settings: Settings | None = None,
) -> ReseedResult:
    """Wipe existing world content and import `document` in one transaction.

    The wipe and reimport share a single session and commit only at the end, so
    an error mid-import rolls the whole thing back rather than half-applying.

    When `settings` is provided, any player whose `current_room_id` no longer
    exists after reimport is relocated to `settings.seed_player_start_room` (when
    that room exists) so live sessions aren't stranded in a deleted room.
    """
    with Session(game_engine) as session:
        wipe_world(session)
        if session.exec(select(WorldMeta)).first() is None:
            session.add(WorldMeta(schema_version=1))
            session.flush()
        import_world(document, session)
        session.flush()
        relocated = (
            _relocate_stranded_players(session, settings) if settings is not None else 0
        )
        session.commit()
    return ReseedResult(
        rooms=len(document.rooms),
        items=len(document.items),
        room_items=len(document.room_items),
        npcs=len(document.npcs),
        quests=len(document.quests),
        relocated_players=relocated,
    )


def reseed_world_from_yaml(
    game_engine: Engine,
    world_path: str | Path,
    *,
    settings: Settings | None = None,
) -> ReseedResult:
    """Validate then wipe-and-reimport a world YAML file (validate-first)."""
    document = load_and_validate_world(world_path)
    return reseed_world_from_document(game_engine, document, settings=settings)


def _relocate_stranded_players(session: Session, settings: Settings) -> int:
    """Move any player pointing at a now-missing room to configured safe rooms."""
    start_room = settings.seed_player_start_room
    if not start_room or session.get(Room, start_room) is None:
        return 0
    respawn_room = settings.seed_player_respawn_room
    if not respawn_room or session.get(Room, respawn_room) is None:
        respawn_room = start_room
    valid_ids = {room.id for room in session.exec(select(Room)).all()}
    relocated = 0
    for player in session.exec(select(Player)).all():
        if player.current_room_id not in valid_ids:
            player.current_room_id = start_room
            if player.respawn_room_id not in valid_ids:
                player.respawn_room_id = respawn_room
            player.visited_rooms = [start_room]
            relocated += 1
    return relocated
