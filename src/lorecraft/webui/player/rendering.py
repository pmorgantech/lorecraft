"""
Lorecraft Web Rendering

Template rendering, feed formatting, and HTML output generation.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi.templating import Jinja2Templates
from sqlmodel import Session as DBSession

from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.room_repo import RoomRepo

templates = Jinja2Templates(directory="src/lorecraft/webui/player/templates")


CARTOGRAPHY_REVEAL_THRESHOLD = 20


def build_map_data(
    room_repo: RoomRepo,
    player: Player,
    current_room: Room | None,
    *,
    full: bool = False,
    cartography_level: int = 0,
) -> dict:
    """Build data for the graphical mini-map of nearby discovered rooms + connections.

    `full=True` (the full-screen map modal, Sprint 26.1) lifts the 7-room cap
    to 60 and, once the player's cartography skill reaches
    CARTOGRAPHY_REVEAL_THRESHOLD, also plots rooms one non-hidden exit away
    from anywhere visited — "known but unvisited" (dimmer, name withheld).
    Hidden exits stay off the map entirely; that's `search`'s reveal, not
    cartography's (Sprint 25.1).
    """
    if not current_room:
        return {"nearby_rooms": [], "map_lines": []}
    visited = set(getattr(player, "visited_rooms", []) or [])
    if current_room.id:
        visited.add(current_room.id)

    known_ids = set(visited)
    if full and cartography_level >= CARTOGRAPHY_REVEAL_THRESHOLD:
        for rid in list(visited):
            for ex in room_repo.exits(rid):
                if not ex.hidden:
                    known_ids.add(ex.target_room_id)

    cx = getattr(current_room, "map_x", 0) or 0
    cy = getattr(current_room, "map_y", 0) or 0
    cands = []
    for rid in known_ids:
        r = room_repo.get(rid)
        if (
            r
            and getattr(r, "map_x", None) is not None
            and getattr(r, "map_y", None) is not None
        ):
            d = abs((r.map_x or 0) - cx) + abs((r.map_y or 0) - cy)
            cands.append((d, r, rid in visited))
    cands.sort(key=lambda item: item[0])
    limit = 60 if full else 7
    nearby = []
    for _, r, is_visited in cands[:limit]:
        nearby.append(
            {
                "id": r.id,
                "name": r.name if is_visited else "Unexplored",
                "x": r.map_x or 0,
                "y": r.map_y or 0,
                "current": r.id == current_room.id,
                "visited": is_visited,
            }
        )
    # Connections among shown rooms
    nids = {n["id"] for n in nearby}
    conns = []
    for rid in nids:
        for ex in room_repo.exits(rid):
            if ex.hidden:
                continue
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


def mud_room_block(room: Any, room_panel: dict[str, Any]) -> list[str]:
    """Old-school-MUD-style plain-text room description (Sprint 58): name,
    description, NPCs present, visible items, and non-hidden exits — the text
    equivalent of the room + minimap panels, for layouts (immersive) that drop
    them in favour of a dominant chronicle. Built from the same `room_panel`
    data those panels render, so it can't drift from what they'd show.
    """
    lines = [room.name, room.description]

    npcs = room_panel.get("npcs") or []
    if npcs:
        lines.append(f"Present: {', '.join(npcs)}.")

    items = room_panel.get("items_visible") or []
    if items:
        lines.append(f"You see: {', '.join(items)}.")

    exits = [e["direction"] for e in room_panel.get("exits", []) if not e.get("hidden")]
    lines.append(
        f"Exits: {', '.join(sorted(exits))}."
        if exits
        else "There are no obvious exits."
    )
    return lines


def mud_players_here_line(players_in_room: list[dict[str, Any]]) -> str | None:
    """'X, Y are here.' line — the text equivalent of the Here Now panel, for
    layouts (immersive) that drop it. None if no one else is present."""
    others = [p["name"] for p in players_in_room if not p.get("is_self")]
    if not others:
        return None
    verb = "is" if len(others) == 1 else "are"
    return f"{', '.join(others)} {verb} here."


def mark_oob_swap(html: str, element_id: str) -> str:
    """Mark a rendered partial for HTMX out-of-band swap by element id."""
    needle = f'id="{element_id}"'
    if needle not in html:
        return html
    return html.replace(needle, f'{needle} hx-swap-oob="true"', 1)


def create_dev_player(db: DBSession, room_repo: RoomRepo, player_id: str) -> Any | None:
    """Create a dev/test player at village_square when explicitly requested."""
    from lorecraft.engine.models.player import Player

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
    from lorecraft.commands.report import REPORT_WIZARD_FLAG
    from lorecraft.features.npc.dialogue import _NPC_KEY

    stripped = raw.strip()

    # Guided report wizard (Sprint 33.1): while active, any input is the answer
    # to the current step — route it to the `report` command, which advances the
    # flag-driven state machine. Checked before the numeric/dialogue branches so
    # a one-word answer (e.g. "bug") or a number in a title is captured verbatim.
    if player_flags and player_flags.get(REPORT_WIZARD_FLAG):
        return f"report {stripped}" if stripped else "report"

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
