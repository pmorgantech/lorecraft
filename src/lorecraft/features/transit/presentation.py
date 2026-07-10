"""Transit feature presentation layer: UI panels and assets for the web host.

Registers the minimap panel when both the transit feature and the web host are enabled.
This module is loaded *only* by a web host, never by the headless engine — so it imports
web dependencies that the engine doesn't have.

Loaded by: `webui/player/__init__.py` when assembling the web host.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sqlmodel import Session

    from lorecraft.engine.models.player import Player
    from lorecraft.webui.player.host import WebHost


def build_minimap_context(player: Player, db: Session) -> dict[str, Any]:
    """Build template context for the minimap panel.

    Builds map data with cartography reveal (gated on player's exploration progress)
    and current room context. Called whenever the panel refreshes.

    Args:
        player: Current player object.
        db: Database session.

    Returns:
        Dictionary with map_data + room context for partials/minimap.html template.
    """
    # Import here to avoid web-layer deps at module level
    from lorecraft.engine.repos.item_repo import ItemRepo
    from lorecraft.engine.repos.npc_repo import NpcRepo
    from lorecraft.engine.repos.room_repo import RoomRepo
    from lorecraft.webui.player.rendering import build_map_data
    from lorecraft.webui.player.session import room_panel_context

    room_repo = RoomRepo(db)
    room = room_repo.get(player.current_room_id) if player.current_room_id else None

    rpanel = room_panel_context(
        room,
        room_repo,
        ItemRepo(db),
        player,
        npc_repo=NpcRepo(db),
    )
    map_data = build_map_data(
        room_repo, player, room, level=room.map_z if room else None
    )

    return {
        "current_room": room,
        "current_player": player,
        **rpanel,
        **map_data,
    }


def register(web: WebHost) -> None:
    """Register the transit feature's UI panels with the web host.

    Called once at web host startup for each enabled feature that defines
    a presentation module. Never called by the headless engine.

    Args:
        web: WebHost instance to register panels onto.
    """
    from lorecraft.webui.player.host import Panel

    # Register the minimap panel: renders partials/minimap.html, lives in
    # the right-rail slot, context provided by build_minimap_context.
    web.add_panel(
        Panel(
            id="minimap",
            slot="right-rail",
            partial="partials/minimap.html",
            context=build_minimap_context,
        )
    )
