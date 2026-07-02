"""
Lorecraft Web Rendering

Template rendering, feed formatting, and HTML output generation.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi.templating import Jinja2Templates
from sqlmodel import Session as DBSession

from lorecraft.models.audit import AuditEvent
from lorecraft.models.player import Player
from lorecraft.models.world import Room
from lorecraft.repos.room_repo import RoomRepo

templates = Jinja2Templates(directory="src/lorecraft/web/templates")


def build_map_data(
    room_repo: RoomRepo, player: Player, current_room: Room | None
) -> dict:
    """Build data for the graphical mini-map of nearby discovered rooms + connections."""
    if not current_room:
        return {"nearby_rooms": [], "map_lines": []}
    visited = set(getattr(player, "visited_rooms", []) or [])
    if current_room.id:
        visited.add(current_room.id)
    cx = getattr(current_room, "map_x", 0) or 0
    cy = getattr(current_room, "map_y", 0) or 0
    cands = []
    for rid in visited:
        r = room_repo.get(rid)
        if (
            r
            and getattr(r, "map_x", None) is not None
            and getattr(r, "map_y", None) is not None
        ):
            d = abs((r.map_x or 0) - cx) + abs((r.map_y or 0) - cy)
            cands.append((d, r))
    cands.sort(key=lambda item: item[0])
    nearby = []
    for _, r in cands[:7]:
        nearby.append(
            {
                "id": r.id,
                "name": r.name,
                "x": r.map_x or 0,
                "y": r.map_y or 0,
                "current": r.id == current_room.id,
            }
        )
    # Connections among shown rooms
    nids = {n["id"] for n in nearby}
    conns = []
    for rid in nids:
        for ex in room_repo.exits(rid):
            tid = ex.target_room_id
            if tid in nids:
                pair = tuple(sorted([rid, tid]))
                if pair not in conns:
                    conns.append(pair)
    # Pixel positions for SVG
    if not nearby:
        return {"nearby_rooms": [], "map_lines": []}
    c = next((n for n in nearby if n["current"]), nearby[0])
    ccx, ccy = c["x"], c["y"]
    SCALE = 8
    OX = 42
    OY = 26
    for n in nearby:
        n["px"] = OX + (n["x"] - ccx) * SCALE
        # World Y increases northward; SVG Y increases downward.
        n["py"] = OY - (n["y"] - ccy) * SCALE
    lines = []
    for a, b in conns:
        ra = next((n for n in nearby if n["id"] == a), None)
        rb = next((n for n in nearby if n["id"] == b), None)
        if ra and rb:
            lines.append(
                {"x1": ra["px"], "y1": ra["py"], "x2": rb["px"], "y2": rb["py"]}
            )
    return {"nearby_rooms": nearby, "map_lines": lines}


def audit_to_feed(event: AuditEvent, current_player: Player) -> dict[str, Any]:
    """Convert an audit event to a feed message for display."""
    ts = time.strftime("%H:%M", time.localtime(event.real_time))
    actor = event.actor_id
    et = (event.event_type or "").upper()

    text = event.summary or event.event_type
    if "COMMAND" not in et and event.payload_json:
        raw = event.payload_json.get("raw") or event.payload_json.get("text")
        if raw:
            text = str(raw)

    typ = "narrative"
    if "COMMAND" in et:
        typ = "system"
    elif "player" in (event.summary or "").lower():
        typ = "player_action"

    return {
        "id": event.id or f"a-{event.real_time}",
        "timestamp": ts,
        "actor": None
        if "COMMAND" in et
        else (actor if actor != current_player.id else current_player.username),
        "text": text,
        "type": typ,
    }


def mark_oob_swap(html: str, element_id: str) -> str:
    """Mark a rendered partial for HTMX out-of-band swap by element id."""
    needle = f'id="{element_id}"'
    if needle not in html:
        return html
    return html.replace(needle, f'{needle} hx-swap-oob="true"', 1)


def create_dev_player(db: DBSession, room_repo: RoomRepo, player_id: str) -> Any | None:
    """Create a dev/test player at village_square when explicitly requested."""
    from lorecraft.models.player import Player

    start_room = "village_square"
    if room_repo.get(start_room) is None:
        return None
    player = Player(
        id=player_id,
        username=player_id,
        current_room_id=start_room,
        respawn_room_id=start_room,
        visited_rooms=[start_room],
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def resolve_command_text(
    raw: str,
    player_id: str,
    app_state: Any | None,
    player_flags: Any | None = None,
) -> str:
    """Resolve disambiguated/numeric command input to full command text."""
    from lorecraft.npc.dialogue import _NPC_KEY

    stripped = raw.strip()
    if not stripped.isdigit():
        return raw

    if player_flags and player_flags.get(_NPC_KEY):
        return f"choice {stripped}"

    if app_state is None:
        return raw
    pending = app_state.pending_disambig.pop(player_id, None)
    if pending is None:
        return raw
    choices: list[str] = pending.get("choices", [])  # type: ignore[assignment]
    idx = int(stripped) - 1
    if 0 <= idx < len(choices):
        verb: str = pending.get("verb", "examine")  # type: ignore[assignment]
        return f"{verb} {choices[idx]}"
    return raw


def feed_items_html(messages: list[dict], current_player: Player) -> str:
    """Render bare feed items HTML."""
    return templates.get_template("partials/feed_items.html").render(
        feed_messages=messages,
        current_player=current_player,
    )
