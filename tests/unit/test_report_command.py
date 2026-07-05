"""Tests for the `report` command (player-facing bug/feedback -> issue tracker)."""

from __future__ import annotations

from sqlmodel import Session, create_engine, select

from lorecraft.commands import register_all_commands
from lorecraft.commands.report import _MAX_REPORT_LENGTH
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.models.issue import Issue
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService


def _build_engine_and_ctx() -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    room = Room(
        id="square", name="Square", description="A busy square.", map_x=0, map_y=0
    )
    session.add(room)
    player = Player(
        id="player-1",
        username="grumpiest_fellow",
        current_room_id="square",
        respawn_room_id="square",
    )
    session.add(player)
    session.commit()
    ctx = GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=GameRng(),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
    registry = CommandRegistry()
    register_all_commands(registry)
    return CommandEngine(registry, RuleEngine()), ctx, session


def test_report_with_no_text_starts_guided_flow() -> None:
    # Sprint 33.1: bare `report` now opens the guided wizard instead of erroring.
    from lorecraft.commands.report import REPORT_WIZARD_FLAG

    cmd_engine, ctx, session = _build_engine_and_ctx()

    cmd_engine.handle_command("report", ctx)

    assert ctx.player.flags.get(REPORT_WIZARD_FLAG) == "category"
    assert "what kind" in ctx.messages[-1].lower()
    # Nothing filed until the flow completes.
    assert session.exec(select(Issue)).first() is None


def test_report_creates_an_issue_visible_to_the_admin_tracker() -> None:
    cmd_engine, ctx, session = _build_engine_and_ctx()

    cmd_engine.handle_command(
        "report the keys stay in the room pane after get all", ctx
    )

    issues = session.exec(select(Issue)).all()
    assert len(issues) == 1
    issue = issues[0]
    assert issue.id.startswith("issue-")
    assert issue.type == "bug"
    assert issue.status == "open"
    assert issue.component == "player-report"
    assert issue.created_by == "grumpiest_fellow"
    assert "player-report" in issue.tags
    assert "keys stay in the room pane" in issue.description

    assert len(ctx.messages) == 1
    assert issue.id in ctx.messages[0]
    assert "logged" in ctx.messages[0].lower()


def test_report_emits_issue_filed_event() -> None:
    # The admin console live-refreshes its Issues tab off this event (main.py
    # forwards ISSUE_FILED to the admin broadcaster as a content_changed push).
    from lorecraft.engine.game.events import Event, GameEvent

    cmd_engine, ctx, session = _build_engine_and_ctx()
    seen: list[Event] = []
    ctx.bus.on(GameEvent.ISSUE_FILED, lambda event, _ctx: seen.append(event))

    cmd_engine.handle_command("report the torch flickers oddly", ctx)

    issue = session.exec(select(Issue)).first()
    assert issue is not None
    assert len(seen) == 1
    assert seen[0].payload.get("issue_id") == issue.id


def test_report_wizard_completion_emits_issue_filed_event() -> None:
    # The guided flow routes free text to the handler directly (the web layer,
    # not the parser), so drive the handler rather than parsing each answer.
    from lorecraft.commands.report import REPORT_WIZARD_FLAG
    from lorecraft.engine.game.events import Event, GameEvent

    _, ctx, session = _build_engine_and_ctx()
    registry = CommandRegistry()
    register_all_commands(registry)
    report = registry.get("report").handler

    seen: list[Event] = []
    ctx.bus.on(GameEvent.ISSUE_FILED, lambda event, _ctx: seen.append(event))

    report(None, ctx)  # start wizard
    report("bug", ctx)  # category
    report("Torch bug", ctx)  # title
    report("skip", ctx)  # detail -> files the report

    assert ctx.player.flags.get(REPORT_WIZARD_FLAG) is None
    assert len(seen) == 1
    issue = session.exec(select(Issue)).first()
    assert issue is not None
    assert seen[0].payload.get("issue_id") == issue.id


def test_report_truncates_overly_long_text() -> None:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    long_text = "x" * (_MAX_REPORT_LENGTH + 500)

    cmd_engine.handle_command(f"report {long_text}", ctx)

    issue = session.exec(select(Issue)).first()
    assert issue is not None
    assert len(issue.description) == _MAX_REPORT_LENGTH
    assert "truncated" in ctx.messages[0].lower()


def test_report_title_is_shortened_for_long_descriptions() -> None:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    long_text = "a" * 200

    cmd_engine.handle_command(f"report {long_text}", ctx)

    issue = session.exec(select(Issue)).first()
    assert issue is not None
    assert len(issue.title) <= 80
    assert issue.title.endswith("...")
    assert issue.description == long_text


def test_slash_report_alias_behaves_identically() -> None:
    cmd_engine, ctx, session = _build_engine_and_ctx()

    cmd_engine.handle_command(
        "/report the keys stay in the room pane after get all", ctx
    )

    issue = session.exec(select(Issue)).first()
    assert issue is not None
    assert issue.created_by == "grumpiest_fellow"
    # The free-text fix must apply to the /report alias too -- the message
    # must not fragment on the preposition "in" the way it would for a
    # normal object/destination phrase.
    assert "keys stay in the room pane" in issue.description
