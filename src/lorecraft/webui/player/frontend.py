"""
Lorecraft Web UI Router (HTMX + Alpine + Jinja2)

Server-driven UI:
- /lobby : simple player selector / entry
- /game : main SSR game screen
- POST /command : process command, return feed + OOB updates
- GET /partials/* : individual panels
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session as DBSession

from lorecraft.engine.game.broadcast import broadcast_command_effects
from lorecraft.engine.game.context import build_game_context
from lorecraft.engine.services.crash_reports import record_crash
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.features.npc.dialogue import _NPC_KEY, dialogue_panel_state
from lorecraft.observability import bind_transaction_context
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.features.npc.repo import DialogueRepo
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.features.quests.repo import QuestRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.save import SessionSafetyService
from lorecraft.webui.player.auth import (
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidUsernameError,
    PlayerAlreadyLoggedInError,
    PlayerNotFoundError,
    StartRoomNotConfiguredError,
    login_or_register,
)
from lorecraft.webui.player.password_policy import PasswordPolicy
from lorecraft.webui.player.preferences import (
    DISPLAY_DENSITIES,
    FEED_PAGE_LENGTHS,
    FEED_VERBOSITIES,
    FONT_SCALES,
    LAYOUTS,
    MINIMAP_STYLES,
    MODE_DEFAULT_THEME,
    THEMES,
    TIMESTAMP_FORMATS,
    TOGGLEABLE_PANELS,
    apply_updates,
    resolve_preferences,
)
from lorecraft.webui.player.rendering import (
    audit_to_feed,
    build_map_data,
    create_dev_player,
    feed_items_html,
    mark_oob_swap,
    resolve_command_text,
    room_card_message,
)
from lorecraft.webui.player.session import (
    CommandResult,
    MUD_CHRONICLE_LAYOUTS,
    expire_grace_periods,
    get_app_state,
    get_broadcast_manager,
    get_bus,
    get_command_engine,
    get_effects,
    get_engines,
    get_manager,
    get_meters,
    get_real_manager,
    get_rng,
    encumbrance_snapshot_for,
    inventory_snapshot,
    players_here,
    room_panel_context,
    set_player_session_cookie,
    clear_player_session_cookie,
    active_quests_snapshot,
    stats_snapshot,
    vitals_snapshot,
    world_time_snapshot,
)

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="src/lorecraft/webui/player/templates")
# Single source of truth for the layout -> default-scheme mapping (Sprint 67):
# injected into base.html as `window.LC_MODE_DEFAULT_THEME` so the top-bar
# picker's and settings page's client-side "auto" preview read the same data
# `resolve_preferences()` uses server-side, instead of hand-copied JS literals
# that could drift from it.
templates.env.globals["MODE_DEFAULT_THEME_JSON"] = json.dumps(MODE_DEFAULT_THEME)

# Feature flag (Sprint 58): show the quick Theme/Layout pickers in the top nav
# bar. Experimental — flip to False (or delete the flag, the
# `partials/topbar_appearance.html` include, and the `/settings/appearance`
# route) to peel the feature back. The settings page keeps its own pickers
# regardless of this flag.
APPEARANCE_TOPBAR = True


def _carried_snapshot(item_repo: ItemRepo, player_id: str) -> list[tuple[str, int]]:
    """Comparable (item_id, quantity) snapshot of a player's carried stacks."""
    return [
        (stack.item_id, stack.quantity)
        for stack, _item in item_repo.stacks_carried_by(player_id)
    ]


async def get_current_player(request: Request) -> Player:
    """Resolve the current player.

    Prefers the signed `lorecraft_session` cookie minted by `/lobby/enter` and
    `/lobby/create` (see `lorecraft.webui.player.player_auth`) — this is the only path
    that can't be forged by a client. Falls back to the legacy dev/test path
    (`?player_id=`/`&pid=` or an unsigned `player_id` cookie) when no valid
    signed session is present, gated by `Settings.allow_query_player_id`.
    """
    from lorecraft.webui.player.player_auth import (
        PLAYER_SESSION_COOKIE,
        decode_player_id,
    )
    from lorecraft.webui.player.session import player_session_secret

    app_state = get_app_state(request)
    game_engine, _ = get_engines(request)

    session_token = request.cookies.get(PLAYER_SESSION_COOKIE)
    if session_token:
        signed_player_id = decode_player_id(
            session_token, player_session_secret(app_state)
        )
        if signed_player_id:
            with DBSession(game_engine) as db:
                signed_player = PlayerRepo(db).get(signed_player_id)
            if signed_player is not None:
                return signed_player

    allow_legacy = (
        app_state.settings.allow_query_player_id if app_state is not None else False
    )
    if not allow_legacy:
        raise HTTPException(status_code=401, detail="No active session")

    explicit_id = request.query_params.get("player_id") or request.query_params.get(
        "pid"
    )
    cookie_id = request.cookies.get("player_id")
    player_id = explicit_id or cookie_id

    with DBSession(game_engine) as db:
        repo = PlayerRepo(db)
        room_repo = RoomRepo(db)
        if player_id:
            p = repo.get(player_id)
            if p:
                return p
            p = repo.by_username(player_id)
            if p:
                return p
            if explicit_id:
                p = create_dev_player(db, room_repo, explicit_id)
                if p is not None:
                    return p

        players = list(repo.list_all(limit=1))
        if players:
            return players[0]

        try:
            existing = repo.get("player-1") or repo.by_username("player-1")
            if existing:
                return existing
            from lorecraft.engine.models.world import Room

            dev = Player(
                id="player-1",
                username="player-1",
                current_room_id="village_square",
                respawn_room_id="village_square",
                visited_rooms=["village_square"],
            )
            db.add(dev)
            if room_repo.get("village_square") is None:
                db.add(
                    Room(
                        id="village_square",
                        name="Village Square",
                        description="A small square.",
                        map_x=0,
                        map_y=0,
                    )
                )
            db.commit()
            db.refresh(dev)
            return dev
        except Exception as ex:
            log.error("dev_player_creation_failed: %s", str(ex))
            try:
                any_p = list(repo.list_all(limit=1))
                if any_p:
                    return any_p[0]
            except Exception as list_ex:
                log.error("fallback_player_list_failed: %s", str(list_ex))
            raise HTTPException(
                status_code=404, detail=f"No player and could not create fallback: {ex}"
            ) from ex


async def get_current_player_optional(request: Request) -> Player | None:
    """Like `get_current_player`, but returns None instead of raising 401.

    Only for `GET /lobby`: that page must be reachable with *no* session at
    all (it's where a session is created), unlike every other route in this
    router, which should correctly 401 without one.
    """
    try:
        return await get_current_player(request)
    except HTTPException:
        return None


# =============================================================================
# LOBBY (password-protected login/create — see web/auth.py)
# =============================================================================


def _lobby_context(
    request: Request,
    app_state: object | None,
    *,
    player: Player | None = None,
    error: str | None = None,
    active_tab: str = "join",
    form_username: str = "",
) -> dict[str, object]:
    """Shared lobby template context, including the (configurable) password
    requirement list so the create form can show and validate against it."""
    settings = getattr(app_state, "settings", None)
    policy = (
        PasswordPolicy.from_settings(settings)  # type: ignore[arg-type]
        if settings is not None
        else PasswordPolicy()
    )
    return {
        "request": request,
        "player": player,
        "error": error,
        "active_tab": active_tab,
        "form_username": form_username,
        "username_pattern": "[A-Za-z0-9_-]{3,30}",
        "password_min_length": policy.min_length,
        "password_max_length": policy.max_length,
        "password_require_mixed_case": policy.require_mixed_case,
        "password_require_number": policy.require_number,
        "password_require_symbol": policy.require_symbol,
        "password_requirements": policy.requirements(),
    }


@router.get("/lobby", response_class=HTMLResponse)
async def lobby(
    request: Request, player: Player | None = Depends(get_current_player_optional)
):
    """Lobby: log in to an existing character or create a new one, both password-protected."""
    context = _lobby_context(request, get_app_state(request), player=player)
    return templates.TemplateResponse(request, "lobby.html", context)


@router.post("/lobby/enter", response_class=RedirectResponse)
async def enter_world(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    """Log in to an existing character. Unlike /lobby/create, does not
    silently create an account for an unknown username (allow_create=False)
    — a typo'd name should 404, not spawn an empty new character."""
    app_state = get_app_state(request)
    start_room = (
        app_state.settings.seed_player_start_room if app_state else "village_square"
    )
    game_engine, _ = get_engines(request)

    with DBSession(game_engine) as db:
        room_repo = RoomRepo(db)
        try:
            result = login_or_register(
                db,
                room_repo,
                username,
                password,
                start_room=start_room,
                allow_create=False,
            )
        except PlayerAlreadyLoggedInError as e:
            return templates.TemplateResponse(
                request,
                "lobby.html",
                _lobby_context(
                    request,
                    app_state,
                    error=str(e),
                    active_tab="join",
                    form_username=username,
                ),
                status_code=400,
            )
        except (
            InvalidUsernameError,
            PlayerNotFoundError,
            InvalidCredentialsError,
        ) as e:
            return templates.TemplateResponse(
                request,
                "lobby.html",
                _lobby_context(
                    request,
                    app_state,
                    error=str(e),
                    active_tab="join",
                    form_username=username,
                ),
                status_code=400,
            )
        except StartRoomNotConfiguredError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        db.commit()
        player_id = result.player.id

    resp = RedirectResponse(url="/game", status_code=303)
    set_player_session_cookie(resp, player_id, app_state)
    return resp


@router.post("/lobby/create", response_class=RedirectResponse)
async def create_character(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(""),
):
    """Create a new player character (or claim a passwordless one) and log in.

    Shares `login_or_register()` with `/lobby/enter` and `POST /auth/login` —
    the only difference is which lobby tab a browser user came from. Enforces
    the configured password complexity policy and that the two password fields
    match; on any validation failure the lobby is re-rendered with an inline
    error on the Create tab (not a raw error page). If the username already has
    a password set, this behaves like a login (and will 401 on a wrong
    password) rather than a hard "name taken" error.
    """
    app_state = get_app_state(request)
    start_room = (
        app_state.settings.seed_player_start_room if app_state else "village_square"
    )

    def _create_error(message: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "lobby.html",
            _lobby_context(
                request,
                app_state,
                error=message,
                active_tab="create",
                form_username=username,
            ),
            status_code=400,
        )

    if password != password_confirm:
        return _create_error("Passwords do not match.")

    policy = (
        PasswordPolicy.from_settings(app_state.settings)
        if app_state is not None
        else PasswordPolicy()
    )
    game_engine, _ = get_engines(request)

    with DBSession(game_engine) as db:
        room_repo = RoomRepo(db)
        try:
            result = login_or_register(
                db,
                room_repo,
                username,
                password,
                start_room=start_room,
                password_policy=policy,
            )
        except PlayerAlreadyLoggedInError as e:
            return _create_error(str(e))
        except (
            InvalidUsernameError,
            InvalidPasswordError,
            InvalidCredentialsError,
        ) as e:
            return _create_error(str(e))
        except StartRoomNotConfiguredError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        db.commit()
        player_id = result.player.id

    resp = RedirectResponse(url="/game", status_code=303)
    set_player_session_cookie(resp, player_id, app_state)
    return resp


# =============================================================================
# GAME SCREEN
# =============================================================================


@router.get("/game", response_class=HTMLResponse)
async def game_screen(
    request: Request,
    player: Player = Depends(get_current_player),
):
    """Main game UI - SSR initial panels."""
    game_engine, audit_engine = get_engines(request)

    with DBSession(game_engine) as game_db, DBSession(audit_engine) as audit_db:
        player_repo = PlayerRepo(game_db)
        room_repo = RoomRepo(game_db)
        item_repo = ItemRepo(game_db)
        audit_repo = AuditRepo(audit_db)

        player = player_repo.get(player.id) or player

        current_room = None
        if player.current_room_id:
            current_room = room_repo.get(player.current_room_id)

        inv = inventory_snapshot(player, item_repo)
        room_panel = room_panel_context(
            current_room,
            room_repo,
            item_repo,
            player,
            npc_repo=NpcRepo(game_db),
        )
        map_data = build_map_data(
            room_repo,
            player,
            current_room,
            level=current_room.map_z if current_room else None,
        )

        # Feed length is a per-account preference (Sprint 33.2 quick-win).
        prefs = resolve_preferences(player.preferences)
        feed_limit = prefs.feed_page_length

        feed_events = []
        if current_room:
            feed_events = list(
                audit_repo.recent_for_room(current_room.id, limit=feed_limit)
            )
        if not feed_events:
            feed_events = list(audit_repo.recent_for_actor(player.id, limit=feed_limit))

        feed_events = [
            e for e in feed_events if "COMMAND" not in (e.event_type or "").upper()
        ]

        feed_messages = [audit_to_feed(e, player) for e in reversed(feed_events)]

        if (
            not feed_messages
            and current_room
            and prefs.layout not in MUD_CHRONICLE_LAYOUTS
        ):
            feed_messages = [
                {
                    "id": "welcome",
                    "timestamp": time.strftime("%H:%M", time.localtime()),
                    "actor": None,
                    "text": f"You arrive in {current_room.name}.",
                    "type": "narrative",
                }
            ]

        quest_repo = QuestRepo(game_db)
        dialogue_repo = DialogueRepo(game_db)
        active_quests = active_quests_snapshot(player, quest_repo)
        dialogue = dialogue_panel_state(player.flags, NpcRepo(game_db), dialogue_repo)
        world_time = world_time_snapshot(room_repo)
        players_in_room = players_here(
            player,
            current_room.id if current_room else None,
            get_real_manager(request),
            player_repo,
        )

        # The chronicle-only layouts (immersive, classic) drop the dedicated
        # room/players panels, so they narrate the room in the chronicle
        # instead — as a styled room card (mirrors the Current Location panel;
        # see room_card_message / feed_room_card.html) appended last (closest
        # to the prompt), like a MUD showing you the room right after you
        # connect (Sprint 58/59, styled in Sprint 60).
        if prefs.layout in MUD_CHRONICLE_LAYOUTS and current_room:
            feed_messages = [
                *feed_messages,
                room_card_message(
                    current_room,
                    room_panel,
                    players_in_room,
                    msg_id="room-card",
                    timestamp=time.strftime("%H:%M", time.localtime()),
                ),
            ]

        # The classic layout's prompt shows a vitals line (real meters, not MUD
        # stats — see vitals_snapshot). Only computed for that layout.
        vitals = (
            vitals_snapshot(game_db, get_meters(request), player.id)
            if prefs.layout == "classic"
            else None
        )
        # The Stats pane (Sprint 62, from the export's "Score" readout) —
        # Standard shows it as a tab, Dock as a window-shade section.
        player_stats = (
            stats_snapshot(
                game_db,
                player_repo,
                get_meters(request),
                get_effects(request),
                player.id,
            )
            if prefs.layout in ("standard", "dock")
            else None
        )

        context = {
            "request": request,
            "current_player": player,
            "current_room": current_room,
            "inventory": inv,
            "encumbrance": encumbrance_snapshot_for(game_db, player_repo, player.id),
            "feed_messages": feed_messages,
            "players_here": players_in_room,
            "active_quests": active_quests,
            "dialogue": dialogue,
            "world_time": world_time,
            "vitals": vitals,
            "player_stats": player_stats,
            # Top-bar quick Theme/Layout pickers (Sprint 58, feature-flagged).
            "appearance_picker": APPEARANCE_TOPBAR,
            "theme_options": THEMES,
            "layout_options": LAYOUTS,
            **room_panel,
            **map_data,
            # Per-account presentation preferences (Sprint 32.2) — resolved in
            # exactly one place (above) and injected as `prefs` for the base
            # shell + panels.
            **prefs.to_context(),
        }
    return templates.TemplateResponse(request, "game.html", context)


# =============================================================================
# ACCOUNT SETTINGS (Sprint 32.2)
# =============================================================================


def _muteable_topic_channels() -> list:
    """The subscribable chat channels (Sprint 52.8) — muteable P2ALL topics
    from the engine's channel registry."""
    from lorecraft.engine.game.channels import get_registry as get_channel_registry

    return [c for c in get_channel_registry().topic_channels() if c.muteable]


def _settings_context(request: Request, player: Player) -> dict:
    """Build the settings-form context from the account's resolved preferences."""
    prefs = resolve_preferences(player.preferences)
    return {
        "request": request,
        "current_player": player,
        "appearance_picker": APPEARANCE_TOPBAR,
        "theme_options": THEMES,
        "layout_options": LAYOUTS,
        "minimap_style_options": MINIMAP_STYLES,
        "density_options": DISPLAY_DENSITIES,
        "verbosity_options": FEED_VERBOSITIES,
        "timestamp_options": TIMESTAMP_FORMATS,
        "font_scale_options": FONT_SCALES,
        "feed_page_length_options": FEED_PAGE_LENGTHS,
        "toggleable_panels": TOGGLEABLE_PANELS,
        # Chat channel subscriptions (Sprint 52.8): one toggle per muteable
        # topic channel; absent from the stored map = the channel default.
        "topic_channels": [
            {
                "id": channel.id,
                "tag": channel.tag,
                "subscribed": prefs.channel_subscriptions.get(
                    channel.id, channel.default_subscribed
                ),
            }
            for channel in _muteable_topic_channels()
        ],
        **prefs.to_context(),
    }


@router.get("/settings", response_class=HTMLResponse)
async def settings_screen(
    request: Request, player: Player = Depends(get_current_player)
):
    """Account preferences page (display density, feed verbosity, motion, panels)."""
    game_engine, _ = get_engines(request)
    with DBSession(game_engine) as db:
        player = PlayerRepo(db).get(player.id) or player
        context = _settings_context(request, player)
    return templates.TemplateResponse(request, "settings.html", context)


@router.post("/settings", response_class=HTMLResponse)
async def update_settings(
    request: Request, player: Player = Depends(get_current_player)
):
    """Persist a preferences update, then redirect back to the game screen.

    Every field is re-validated through ``apply_updates`` (invalid values fall
    back to their default), so the stored blob can never hold an invalid value.
    Uses Post/Redirect/Get so Save returns to ``/game`` (where the new theme /
    layout takes effect) without the player needing a second click.
    """
    form = await request.form()
    updates: dict[str, object] = {
        "theme": form.get("theme"),
        "layout": form.get("layout"),
        "minimap_style": form.get("minimap_style"),
        "display_density": form.get("display_density"),
        "feed_verbosity": form.get("feed_verbosity"),
        "timestamp_format": form.get("timestamp_format"),
        "font_scale": form.get("font_scale"),
        "feed_page_length": form.get("feed_page_length"),
        # An unchecked checkbox is simply absent from the form.
        "reduced_motion": "reduced_motion" in form,
        "high_contrast": "high_contrast" in form,
        "separate_chat": "separate_chat" in form,
        # One checkbox per muteable topic channel (unchecked = absent = off).
        "channel_subscriptions": {
            channel.id: f"channel_sub_{channel.id}" in form
            for channel in _muteable_topic_channels()
        },
        "hidden_panels": [
            v for v in form.getlist("hidden_panels") if isinstance(v, str)
        ],
    }

    game_engine, _ = get_engines(request)
    with DBSession(game_engine) as db:
        repo = PlayerRepo(db)
        player = repo.get(player.id) or player
        current = resolve_preferences(player.preferences)
        # Reassign (not mutate) so SQLModel flags the JSON column dirty.
        player.preferences = apply_updates(current, updates).to_stored()
        repo.add(player)
        db.commit()
    return RedirectResponse(url="/game", status_code=303)


@router.post("/settings/appearance")
async def update_appearance(
    request: Request,
    theme: str | None = Form(default=None),
    layout: str | None = Form(default=None),
    minimap_style: str | None = Form(default=None),
    player: Player = Depends(get_current_player),
):
    """Quick scheme/layout/minimap-style change from the top-bar pickers
    (Sprint 58, gated by ``APPEARANCE_TOPBAR``) and the map-pane toggle
    (Sprint 62). Updates ONLY the field(s) supplied, merged over the account's
    current preferences, so it never disturbs any other setting. Returns 204 —
    the caller updates the page client-side (instant class swap) or via a
    reload (layout), so there is nothing to render here.
    """
    updates: dict[str, object] = {}
    if theme is not None:
        updates["theme"] = theme
    if layout is not None:
        updates["layout"] = layout
    if minimap_style is not None:
        updates["minimap_style"] = minimap_style
    if updates:
        game_engine, _ = get_engines(request)
        with DBSession(game_engine) as db:
            repo = PlayerRepo(db)
            player = repo.get(player.id) or player
            current = resolve_preferences(player.preferences)
            # Reassign (not mutate) so SQLModel flags the JSON column dirty.
            player.preferences = apply_updates(current, updates).to_stored()
            repo.add(player)
            db.commit()
    return Response(status_code=204)


# =============================================================================
# COMMAND HANDLER (HTMX + OOB)
# =============================================================================


@router.post("/command", response_class=HTMLResponse)
async def handle_command(
    request: Request,
    command: str = Form(...),
    player: Player = Depends(get_current_player),
):
    """Execute command using CommandEngine + GameContext."""
    game_engine, audit_engine = get_engines(request)

    raw = (command or "").strip()
    if not raw:
        return HTMLResponse(feed_items_html([], player), status_code=200)

    with (
        DBSession(game_engine) as game_db,
        DBSession(audit_engine) as audit_db,
    ):
        pre_room_id = player.current_room_id

        player_repo = PlayerRepo(game_db)
        room_repo = RoomRepo(game_db)
        item_repo = ItemRepo(game_db)
        player = player_repo.get(player.id) or player
        pre_inv = _carried_snapshot(item_repo, player.id)

        room = room_repo.get(player.current_room_id)
        if room is None:
            return HTMLResponse('<div class="msg system">You are nowhere.</div>')

        app_state = get_app_state(request)
        grace_seconds = (
            app_state.settings.disconnect_grace_seconds if app_state else 60.0
        )
        expire_grace_periods(
            game_db, audit_db, get_bus(request), grace_seconds=grace_seconds
        )

        session_id = f"web-{int(time.time() * 1000)}"
        transaction = TransactionContext.create(
            actor_id=player.id, correlation_id=session_id
        )
        # The command's OWN cross-player effects (movement `move_player`, P2P/follow
        # `send_to_player`, `is_connected` checks, deferred deliveries) run against
        # `ctx.manager`, and its post-command room fan-out runs against the same
        # manager below. In gateway mode both must route through the push manager so
        # they reach Rust-connected clients and keep the adapter mirror consistent
        # (mirroring the WS path, which uses the adapter's DirectiveConnectionManager
        # for both). Flag off: the real ConnectionManager, exactly as before.
        broadcast_manager = get_broadcast_manager(request)
        try:
            ctx = build_game_context(
                game_db,
                player,
                room,
                bus=get_bus(request),
                manager=broadcast_manager or get_manager(),
                transaction=transaction,
                session_id=session_id,
                rng=get_rng(request),
                meters=get_meters(request),
                effects=get_effects(request),
                clock=room_repo.world_clock(),
                audit_session=audit_db,
                commit_state=game_db.commit,
                commit_audit=audit_db.commit,
                rollback_state=game_db.rollback,
            )

            command_text = resolve_command_text(raw, player.id, app_state, player.flags)
            with bind_transaction_context(
                transaction.transaction_id, transaction.correlation_id
            ):
                get_command_engine(request).handle_command(command_text, ctx)

            disambig = ctx.updates.pop("disambig_pending", None)
            if (
                disambig is not None
                and isinstance(disambig, dict)
                and app_state is not None
            ):
                app_state.pending_disambig[player.id] = disambig

            quest_changed = "quest_update" in ctx.updates
            # Sprint 73.9: a level-up (via features/progression/feedback.py's
            # narrate_level_up) pushes "stats_update" the same way a quest
            # change pushes "quest_update" above -- re-render the Stats pane
            # this turn so a live client sees the new level/xp/skill_points
            # without a manual refresh.
            stats_changed = "stats_update" in ctx.updates

            after_player = player_repo.get(player.id) or player
            npc_repo = NpcRepo(game_db)
            dialogue_repo = DialogueRepo(game_db)
            dialogue_snapshot = dialogue_panel_state(
                after_player.flags, npc_repo, dialogue_repo
            )
            had_dialogue = bool(player.flags.get(_NPC_KEY))
            has_dialogue = dialogue_snapshot is not None
            dialogue_changed = "dialogue" in ctx.updates or had_dialogue or has_dialogue
            after_room = room_repo.get(after_player.current_room_id) or ctx.room
            after_inv = _carried_snapshot(item_repo, after_player.id)

            room_changed = after_player.current_room_id != pre_room_id
            inv_changed = after_inv != pre_inv or "inventory" in ctx.updates
            # Refresh room pane if items were taken/dropped/used (room_messages) or if the player moved
            room_state_changed = bool(ctx.room_messages) or room_changed

            room_panel = room_panel_context(
                after_room,
                room_repo,
                item_repo,
                after_player,
                npc_repo=npc_repo,
            )
            map_data = build_map_data(
                room_repo,
                after_player,
                after_room,
                level=after_room.map_z if after_room else None,
            )
            players_in_room = players_here(
                after_player,
                after_player.current_room_id,
                get_real_manager(request),
                player_repo,
            )

            # Resolved once here (Sprint 58): drives both the chronicle-only
            # room card below and which pane a chat echo lands in.
            prefs = resolve_preferences(after_player.preferences)
            _cmd_parts = command_text.strip().split(None, 1)
            command_verb = _cmd_parts[0].lower() if _cmd_parts else ""
            command_arg = _cmd_parts[1].strip() if len(_cmd_parts) > 1 else ""

            # Chronicle-only layouts (immersive, classic) drop the Current
            # Location panel, so they narrate the room in the feed as a styled
            # card (Sprint 60). It shows on arrival (movement doesn't otherwise
            # narrate the new room) and on a successful *bare* `look` — for
            # which the engine's own flat room narration is suppressed below so
            # the card doesn't duplicate it. A blocked look (e.g. darkness)
            # pushes no `room_id`, so its warning still shows and no card fires.
            mud_layout = prefs.layout in MUD_CHRONICLE_LAYOUTS
            is_bare_look = command_verb in {"look", "l"} and not command_arg
            # Suppression only applies where the card replaces the narration —
            # a chronicle-only layout. Elsewhere (standard/dock/e-reader) the
            # engine's look output must reach the feed untouched.
            look_narrated = mud_layout and is_bare_look and "room_id" in ctx.updates
            show_room_card = after_room is not None and (
                (mud_layout and room_changed) or look_narrated
            )

            # Only emit what this command produced this turn.
            # No manual raw-echo + no re-pulling old audits here (prevents duplicate
            # "player-1 : xxx" and history leaking into the current feed append).
            feed_msgs: list[dict] = []
            ts = time.strftime("%H:%M", time.localtime())

            for m in ctx.messages:
                # On a narrated bare `look` in a chronicle-only layout the
                # engine's flat room text is replaced by the styled card below,
                # so drop it here to avoid showing the room twice (Sprint 60).
                if look_narrated:
                    continue
                feed_msgs.append(
                    {
                        "id": f"msg-{session_id}-{len(feed_msgs)}",
                        "timestamp": ts,
                        "actor": None,
                        "text": m,
                        "type": "narrative",
                        # Sprint 56: the semantic type from ctx.say(), kept as a
                        # separate field from `type` above (which drives the
                        # pre-existing player_action/system/dialogue/narrative
                        # styling) so existing rendering is unchanged; templates
                        # add an additional msg-<msg_type> class opt-in.
                        "msg_type": m.type.value,
                    }
                )

            # The chronicle-only layouts (immersive, classic) narrate the room
            # as a styled card in place of the Current Location panel — on
            # arrival (movement never narrated the new room; that was the
            # panel's job) and on a bare `look` (whose engine narration was
            # suppressed above). Built from the same room_panel data the panel
            # renders, so the card can't drift from it (Sprint 60).
            if show_room_card:
                feed_msgs.append(
                    room_card_message(
                        after_room,
                        room_panel,
                        players_in_room,
                        msg_id=f"msg-{session_id}-room",
                        timestamp=ts,
                    )
                )

            # Chat channel (Sprint 45 split, Sprint 52 channels): the actor's own
            # chat echo, tagged so the client can route it to the chat pane when
            # separate_chat is on and style it per channel. With the preference
            # off it renders in the single feed like before. When a chat pane
            # exists (separate_chat, or the immersive layout's left-column pane),
            # the render below routes this item there via an HTMX OOB append
            # instead of leaving it in the main feed (Sprint 58).
            for echo in ctx.chat_echoes:
                feed_msgs.append(
                    {
                        "id": f"msg-{session_id}-{len(feed_msgs)}",
                        "timestamp": ts,
                        "actor": None,
                        "text": echo.text,
                        "type": "chat",
                        "channel": echo.channel,
                    }
                )

            disconnect_requested = bool(getattr(ctx, "updates", {}).get("disconnect"))

            new_inv = inventory_snapshot(after_player, item_repo)

            result = CommandResult(
                new_feed_messages=feed_msgs,
                room_changed=room_state_changed,
                new_room=after_room,
                inventory_changed=inv_changed,
                new_inventory=new_inv,
                minimap_changed=room_changed,
                exits=room_panel["exits"],
                player_id=after_player.id,
                dialogue=dialogue_snapshot,
                dialogue_changed=dialogue_changed,
                quest_changed=quest_changed,
                stats_changed=stats_changed,
            )

            # A chat pane exists when separate_chat is on, or in the classic
            # layout's display-only channel (Sprint 58/59) — route the actor's
            # own chat echo there via HTMX OOB instead of the main feed (see
            # feed_items.html). Immersive folds chat INTO the full-bleed
            # chronicle (Sprint 59.8), so it keeps the default in-feed render.
            route_chat_oob = prefs.separate_chat or prefs.layout == "classic"
            feed_html = templates.get_template("partials/feed_items.html").render(
                feed_messages=result.new_feed_messages,
                current_player=after_player,
                route_chat_oob=route_chat_oob,
            )

            response_html = feed_html

            # Classic layout shows a vitals line in its prompt (Sprint 59) —
            # OOB-refresh it each turn (stamina/coins change on rest, travel,
            # buying, etc.), like the design's "vitals update in the same trip".
            if prefs.layout == "classic":
                vitals_html = templates.get_template("partials/vitals.html").render(
                    vitals=vitals_snapshot(
                        game_db, get_meters(request), after_player.id
                    ),
                )
                response_html += (
                    f'<div id="vitals" hx-swap-oob="true" '
                    f'class="mb-1.5 text-xs">{vitals_html}</div>'
                )

            if room_state_changed and result.new_room:
                room_html = templates.get_template(
                    "partials/room_description.html"
                ).render(
                    current_room=result.new_room,
                    current_player=after_player,
                    **room_panel_context(
                        result.new_room,
                        room_repo,
                        item_repo,
                        after_player,
                        npc_repo=NpcRepo(game_db),
                    ),
                )
                response_html += mark_oob_swap(room_html, "room-description")

            if result.inventory_changed:
                inv_html = templates.get_template("partials/inventory.html").render(
                    inventory=result.new_inventory,
                    current_player=after_player,
                    encumbrance=encumbrance_snapshot_for(
                        game_db, player_repo, after_player.id
                    ),
                )
                response_html += mark_oob_swap(inv_html, "inventory")

            if result.minimap_changed:
                map_html = templates.get_template("partials/minimap.html").render(
                    current_room=after_room,
                    current_player=after_player,
                    **room_panel,
                    **map_data,
                )
                # Mark the partial's OWN sized root (w-full h-full) for the OOB
                # swap — NOT a bare <div id="minimap"> wrapper. Wrapping nested a
                # sized #minimap inside an unsized one, so the compass lost its
                # box on room change and ballooned (Sprint 59 fix).
                response_html += mark_oob_swap(map_html, "minimap")

            if result.dialogue_changed:
                dialogue_html = templates.get_template("partials/dialogue.html").render(
                    dialogue=result.dialogue,
                    request=request,
                )
                response_html += mark_oob_swap(dialogue_html, "dialogue-overlay")

            if result.quest_changed:
                quest_repo = QuestRepo(game_db)
                quest_html = templates.get_template(
                    "partials/quest_tracker.html"
                ).render(
                    active_quests=active_quests_snapshot(after_player, quest_repo),
                )
                response_html += mark_oob_swap(quest_html, "quest-tracker")

            if result.stats_changed:
                # Only the standard/dock layouts render #stats-panel (see
                # game.html / game_dock.html); the OOB swap is a harmless
                # no-op client-side for layouts without that element, same
                # as the quest-tracker swap above.
                stats_html = templates.get_template("partials/stats_panel.html").render(
                    player_stats=stats_snapshot(
                        game_db,
                        player_repo,
                        get_meters(request),
                        get_effects(request),
                        after_player.id,
                    ),
                )
                response_html += mark_oob_swap(stats_html, "stats-panel")

            try:
                players_html = templates.get_template(
                    "partials/players_online.html"
                ).render(
                    players_here=players_in_room,
                    current_player=after_player,
                )
                response_html += mark_oob_swap(players_html, "players-online")
            except Exception as e:
                log.debug("players_template_render_failed: %s", str(e))

            if broadcast_manager:
                await broadcast_command_effects(
                    broadcast_manager, ctx, pre_room_id=pre_room_id
                )

            final_resp = HTMLResponse(content=response_html)
            if disconnect_requested:
                # TODO(3b-followup / decision 8): gateway-mode graceful quit must
                # instruct Rust to close the socket and route the leave broadcasts
                # through the push manager. Deferred here — it needs a new
                # Python->Rust close instruction (protocol + Rust handler), which is
                # out of scope for this Python-only fix, and none of the exit-blocking
                # e2e tests is a graceful quit. Flag off this is byte-identical; flag
                # on the leave narration currently reaches nobody until 3b wires it.
                mgr = get_real_manager(request)
                active_session = player_repo.active_session(after_player.id)
                if active_session is not None:
                    SessionSafetyService(
                        game_session=game_db,
                        audit_session=audit_db,
                        bus=get_bus(request),
                        grace_seconds=grace_seconds,
                    ).begin_grace_period(active_session.id, after_player)
                    game_db.commit()
                    audit_db.commit()

                if mgr and after_player.current_room_id:
                    room_id = after_player.current_room_id
                    # The "leaves the game." narration was already broadcast to the
                    # room by broadcast_command_effects() above (it drains
                    # ctx.room_messages) — don't re-broadcast it here or the room
                    # sees it twice.
                    try:
                        await mgr.broadcast_to_room(
                            room_id,
                            {
                                "type": "player_left",
                                "player_id": after_player.id,
                                "username": after_player.username,
                                "presence": "grace",
                            },
                            exclude=after_player.id,
                        )
                        await mgr.broadcast_to_room(
                            room_id,
                            {
                                "type": "state_change",
                                "affected_panels": ["players-online"],
                                "actor_id": after_player.id,
                            },
                            exclude=after_player.id,
                        )
                    except Exception as e:
                        log.debug("disconnect_broadcast_failed: %s", str(e))
                    # Terminate any follow involving the leaver and tell the still-
                    # connected other side (mirrors the involuntary-drop path in
                    # main.py's WS handler).
                    follow_service = (
                        app_state.services.follow if app_state is not None else None
                    )
                    if follow_service is not None:
                        try:
                            await follow_service.break_on_disconnect(
                                mgr, player_repo, after_player.id
                            )
                        except Exception as e:
                            log.debug("disconnect_follow_break_failed: %s", str(e))
                    try:
                        await mgr.disconnect(after_player.id)
                    except Exception as e:
                        log.debug("manager_disconnect_failed: %s", str(e))

                clear_player_session_cookie(final_resp)
                final_resp.headers["HX-Redirect"] = "/lobby"
            return final_resp
        except Exception as exc:
            # Sprint 57.3: anything that escapes the command pipeline
            # (as opposed to a handler exception, already caught and
            # reported gracefully inside CommandEngine) previously
            # produced a raw 500. Capture it and degrade to a friendly
            # in-game error instead.
            log.exception("unhandled_command_pipeline_exception")
            game_db.rollback()
            record_crash(
                audit_db,
                transaction_id=transaction.transaction_id,
                correlation_id=transaction.correlation_id,
                player_id=player.id,
                command_text=raw,
                exc=exc,
            )
            return HTMLResponse(
                '<div class="msg system">Something went wrong processing that '
                "command. It has been logged for review.</div>"
            )


# =============================================================================
# PARTIAL ENDPOINTS
# =============================================================================


@router.get("/partials/feed", response_class=HTMLResponse)
async def partial_feed(
    request: Request,
    since: str | None = None,
    player: Player = Depends(get_current_player),
):
    """Feed partial. For append use ?since=lastId."""
    game_engine, audit_engine = get_engines(request)

    with DBSession(game_engine) as game_db, DBSession(audit_engine) as audit_db:
        player = PlayerRepo(game_db).get(player.id) or player
        room_id = player.current_room_id
        audit_repo = AuditRepo(audit_db)

        events: list = []
        if room_id:
            events = list(audit_repo.recent_for_room(room_id, limit=30))
        if not events:
            events = list(audit_repo.recent_for_actor(player.id, limit=20))

        events = [e for e in events if "COMMAND" not in (e.event_type or "").upper()]

        if since:
            try:
                since_int = int(since)
                events = [e for e in events if (e.id or 0) > since_int]
            except ValueError:
                log.debug("feed_since_parse_failed: %s", since)

        messages = [audit_to_feed(e, player) for e in reversed(events)]
        template_name = "partials/feed_items.html" if since else "partials/feed.html"

        return templates.TemplateResponse(
            request,
            template_name,
            {"request": request, "feed_messages": messages, "current_player": player},
        )


@router.get("/partials/room-description", response_class=HTMLResponse)
async def partial_room(request: Request, player: Player = Depends(get_current_player)):
    game_engine, _ = get_engines(request)
    with DBSession(game_engine) as db:
        player = PlayerRepo(db).get(player.id) or player
        room_repo = RoomRepo(db)
        room = room_repo.get(player.current_room_id) if player.current_room_id else None
        rpanel = room_panel_context(
            room,
            room_repo,
            ItemRepo(db),
            player,
            npc_repo=NpcRepo(db),
        )
    return templates.TemplateResponse(
        request,
        "partials/room_description.html",
        {
            "request": request,
            "current_room": room,
            "current_player": player,
            **rpanel,
        },
    )


@router.get("/partials/inventory", response_class=HTMLResponse)
async def partial_inventory(
    request: Request, player: Player = Depends(get_current_player)
):
    game_engine, _ = get_engines(request)
    with DBSession(game_engine) as db:
        repo = PlayerRepo(db)
        player = repo.get(player.id) or player
        inv = inventory_snapshot(player, ItemRepo(db))
        encumbrance = encumbrance_snapshot_for(db, repo, player.id)
    return templates.TemplateResponse(
        request,
        "partials/inventory.html",
        {
            "request": request,
            "inventory": inv,
            "current_player": player,
            "encumbrance": encumbrance,
        },
    )


@router.get("/partials/quest-tracker", response_class=HTMLResponse)
async def partial_quest_tracker(
    request: Request, player: Player = Depends(get_current_player)
):
    """Sprint 30.2: lets a scheduler-driven quest event (QuestTimerService,
    which has no in-flight HTTP request to OOB-swap a response into) target
    this one player's quest-tracker panel via a `state_change` WS push,
    the same generic `affected_panels` -> GET this route pattern every other
    live-refreshed panel uses."""
    game_engine, _ = get_engines(request)
    with DBSession(game_engine) as db:
        player = PlayerRepo(db).get(player.id) or player
        quest_repo = QuestRepo(db)
        active_quests = active_quests_snapshot(player, quest_repo)
    return templates.TemplateResponse(
        request,
        "partials/quest_tracker.html",
        {"request": request, "active_quests": active_quests},
    )


@router.get("/partials/minimap", response_class=HTMLResponse)
async def partial_minimap(
    request: Request, player: Player = Depends(get_current_player)
):
    game_engine, _ = get_engines(request)
    with DBSession(game_engine) as db:
        player = PlayerRepo(db).get(player.id) or player
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
    return templates.TemplateResponse(
        request,
        "partials/minimap.html",
        {
            "request": request,
            "current_room": room,
            "current_player": player,
            **rpanel,
            **map_data,
        },
    )


@router.get("/partials/map-full", response_class=HTMLResponse)
async def partial_map_full(
    request: Request, player: Player = Depends(get_current_player)
):
    """Full-screen map modal content (Sprint 26.1): more rooms than the
    sidebar minimap, plus a cartography-gated reveal of known-but-unvisited
    rooms one non-hidden exit away from anywhere the player has been."""
    game_engine, _ = get_engines(request)
    with DBSession(game_engine) as db:
        player = PlayerRepo(db).get(player.id) or player
        room_repo = RoomRepo(db)
        room = room_repo.get(player.current_room_id) if player.current_room_id else None
        cartography_level = _cartography_level(db, player.id)
        map_data = build_map_data(
            room_repo,
            player,
            room,
            full=True,
            cartography_level=cartography_level,
            level=room.map_z if room else None,
        )
    return templates.TemplateResponse(
        request,
        "partials/map_modal.html",
        {
            "request": request,
            "current_room": room,
            "current_player": player,
            **map_data,
        },
    )


def _cartography_level(db: DBSession, player_id: str) -> int:
    from lorecraft.engine.game.modifiers import resolve_for
    from lorecraft.features.skills.service import SkillService

    skills = SkillService()
    base = skills.get_level(db, player_id, "cartography")
    return round(resolve_for(db, "player", player_id, "skill.cartography", base=base))


@router.get("/partials/players-online", response_class=HTMLResponse)
async def partial_players(
    request: Request, player: Player = Depends(get_current_player)
):
    game_engine, audit_engine = get_engines(request)
    app_state = get_app_state(request)
    grace_seconds = app_state.settings.disconnect_grace_seconds if app_state else 60.0
    with DBSession(game_engine) as game_db, DBSession(audit_engine) as audit_db:
        expire_grace_periods(
            game_db,
            audit_db,
            get_bus(request),
            grace_seconds=grace_seconds,
        )
        p = PlayerRepo(game_db).get(player.id) or player
        players_in_room = players_here(
            p,
            p.current_room_id,
            get_real_manager(request),
            PlayerRepo(game_db),
        )
    return templates.TemplateResponse(
        request,
        "partials/players_online.html",
        {"request": request, "players_here": players_in_room, "current_player": p},
    )
