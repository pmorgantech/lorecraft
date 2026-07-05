"""Unit tests for the guided /report flow (Sprint 33.1)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine, select

from lorecraft.commands import register_all_commands
from lorecraft.commands.report import REPORT_WIZARD_FLAG
from lorecraft.models.issue import Issue
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
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


def _build() -> tuple[CommandRegistry, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    room = Room(id="tavern", name="Tavern", description="d", map_x=0, map_y=0)
    session.add(room)
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="tavern",
        respawn_room_id="tavern",
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
            actor_id="player-1", correlation_id="s-1"
        ),
        session_id="s-1",
    )
    registry = CommandRegistry()
    register_all_commands(registry)
    return registry, ctx, session


@pytest.fixture
def built() -> Iterator[tuple[CommandRegistry, GameContext, Session]]:
    registry, ctx, session = _build()
    yield registry, ctx, session
    session.close()


def _report(registry: CommandRegistry, ctx: GameContext, noun: str | None) -> None:
    registry.get("report").handler(noun, ctx)


def _issues(session: Session) -> list[Issue]:
    session.commit()
    return list(session.exec(select(Issue)))


def test_one_liner_still_works(
    built: tuple[CommandRegistry, GameContext, Session],
) -> None:
    registry, ctx, session = built
    _report(registry, ctx, "the door is stuck")
    issues = _issues(session)
    assert len(issues) == 1
    assert issues[0].description == "the door is stuck"
    assert issues[0].type == "bug"
    # No wizard state left behind.
    assert REPORT_WIZARD_FLAG not in ctx.player.flags


def test_bare_report_starts_wizard(
    built: tuple[CommandRegistry, GameContext, Session],
) -> None:
    registry, ctx, session = built
    _report(registry, ctx, None)
    assert ctx.player.flags.get(REPORT_WIZARD_FLAG) == "category"
    assert "what kind" in ctx.messages[-1].lower()
    # Nothing filed yet.
    assert _issues(session) == []


def test_full_guided_flow_files_report(
    built: tuple[CommandRegistry, GameContext, Session],
) -> None:
    registry, ctx, session = built
    _report(registry, ctx, None)  # start
    _report(registry, ctx, "feedback")  # category
    assert ctx.player.flags.get(REPORT_WIZARD_FLAG) == "title"
    _report(registry, ctx, "Nicer map colours")  # title
    assert ctx.player.flags.get(REPORT_WIZARD_FLAG) == "detail"
    _report(registry, ctx, "The exits are hard to read on the minimap.")  # detail

    issues = _issues(session)
    assert len(issues) == 1
    issue = issues[0]
    assert issue.title == "Nicer map colours"
    assert issue.description == "The exits are hard to read on the minimap."
    assert issue.type == "feedback"  # mapped from category
    assert "feedback" in issue.tags
    # Wizard state cleared after filing.
    assert REPORT_WIZARD_FLAG not in ctx.player.flags


def test_detail_skip_files_with_empty_description(
    built: tuple[CommandRegistry, GameContext, Session],
) -> None:
    registry, ctx, session = built
    _report(registry, ctx, None)
    _report(registry, ctx, "bug")
    _report(registry, ctx, "Crash on save")
    _report(registry, ctx, "skip")

    issues = _issues(session)
    assert len(issues) == 1
    assert issues[0].description == ""
    assert issues[0].type == "bug"


def test_invalid_category_reprompts_without_advancing(
    built: tuple[CommandRegistry, GameContext, Session],
) -> None:
    registry, ctx, session = built
    _report(registry, ctx, None)
    _report(registry, ctx, "banana")  # not a category
    assert ctx.player.flags.get(REPORT_WIZARD_FLAG) == "category"  # still here
    assert _issues(session) == []


def test_cancel_aborts_wizard(
    built: tuple[CommandRegistry, GameContext, Session],
) -> None:
    registry, ctx, session = built
    _report(registry, ctx, None)
    _report(registry, ctx, "bug")
    _report(registry, ctx, "cancel")
    assert REPORT_WIZARD_FLAG not in ctx.player.flags
    assert "cancel" in ctx.messages[-1].lower()
    assert _issues(session) == []


def test_web_input_routes_to_report_while_wizard_active() -> None:
    # The web layer sends free-text input to `report` while the wizard is open.
    from lorecraft.webui.player.rendering import resolve_command_text

    active = {REPORT_WIZARD_FLAG: "title"}
    # A multi-word title, a lone word, and even a number all route to report.
    assert (
        resolve_command_text("the map is broken", "p1", None, active)
        == "report the map is broken"
    )
    assert resolve_command_text("bug", "p1", None, active) == "report bug"
    assert resolve_command_text("42", "p1", None, active) == "report 42"


def test_web_input_unaffected_when_no_wizard() -> None:
    from lorecraft.webui.player.rendering import resolve_command_text

    # No wizard flag: normal input passes through untouched.
    assert resolve_command_text("go north", "p1", None, {}) == "go north"
