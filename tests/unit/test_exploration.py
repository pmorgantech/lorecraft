"""Tests for Sprint 25: search/hidden-exit discovery, condition-flag gated
exits, terrain skill gating, and the journal command."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.models.world import Exit, Room
from lorecraft.models.player import Player, PlayerStats
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService

START_ROOM_ID = "start"
DEST_ROOM_ID = "dest"


def _seed(session: Session) -> None:
    session.add(
        Room(id=START_ROOM_ID, name="Start Room", description="d", map_x=0, map_y=0)
    )
    session.add(
        Room(id=DEST_ROOM_ID, name="Dest Room", description="d", map_x=1, map_y=0)
    )
    session.add(
        Exit(
            room_id=START_ROOM_ID,
            direction="north",
            target_room_id=DEST_ROOM_ID,
            hidden=True,
        )
    )
    session.add(
        Exit(
            room_id=START_ROOM_ID,
            direction="east",
            target_room_id=DEST_ROOM_ID,
            condition_flags=["has_key"],
        )
    )
    session.commit()


def _build_engine_and_ctx(
    *, rng_seed: int | None = 1
) -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    _seed(session)
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=START_ROOM_ID,
        respawn_room_id=START_ROOM_ID,
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id))
    session.commit()

    room = session.get(Room, START_ROOM_ID)
    assert room is not None
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
        rng=GameRng(seed=rng_seed),
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


@pytest.fixture
def built() -> Iterator[tuple[CommandEngine, GameContext, Session]]:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    yield cmd_engine, ctx, session
    session.close()


class TestHiddenExitMovement:
    def test_hidden_exit_is_directly_usable(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("go north", ctx)

        assert ctx.player.current_room_id == DEST_ROOM_ID

    def test_hidden_exit_not_listed_until_discovered(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("look", ctx)

        exits_line = next(m for m in ctx.messages if m.startswith("Exits:"))
        assert "north" not in exits_line


class TestConditionFlagGatedExits:
    def test_exit_blocked_without_flag(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("go east", ctx)

        assert ctx.player.current_room_id == START_ROOM_ID
        assert ctx.messages == ["Something prevents you from going that way."]

    def test_exit_allowed_with_flag(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.player.flags = {**ctx.player.flags, "has_key": True}

        cmd_engine.handle_command("go east", ctx)

        assert ctx.player.current_room_id == DEST_ROOM_ID


class TestSearch:
    def test_search_with_favorable_roll_reveals_hidden_exit(self) -> None:
        # Try a range of seeds to find one where the search succeeds;
        # skill_check's floor is 5% so this always terminates quickly.
        for seed in range(50):
            cmd_engine, ctx, _session = _build_engine_and_ctx(rng_seed=seed)
            cmd_engine.handle_command("search", ctx)
            if any("hidden passage" in m for m in ctx.messages):
                break
        else:
            pytest.fail("no seed produced a successful search in 50 tries")

        cmd_engine.handle_command("look", ctx)
        exits_line = next(m for m in ctx.messages if m.startswith("Exits:"))
        assert "north" in exits_line

    def test_search_awards_xp_on_discovery(self) -> None:
        for seed in range(50):
            cmd_engine, ctx, session = _build_engine_and_ctx(rng_seed=seed)
            stats_before = session.get(PlayerStats, ctx.player.id)
            assert stats_before is not None
            xp_before = stats_before.xp
            cmd_engine.handle_command("search", ctx)
            if any("hidden passage" in m for m in ctx.messages):
                stats_after = session.get(PlayerStats, ctx.player.id)
                assert stats_after is not None
                assert stats_after.xp > xp_before
                return
        pytest.fail("no seed produced a successful search in 50 tries")


class TestTerrainGating:
    def test_movement_blocked_below_required_skill(self) -> None:
        cmd_engine, ctx, session = _build_engine_and_ctx()
        dest = session.get(Room, DEST_ROOM_ID)
        assert dest is not None
        dest.terrain = "mountain"
        session.add(dest)
        session.commit()
        ctx.player.flags = {**ctx.player.flags, "has_key": True}

        cmd_engine.handle_command("go east", ctx)

        assert ctx.player.current_room_id == START_ROOM_ID
        assert any("skilled enough" in m for m in ctx.messages)

    def test_movement_allowed_above_required_skill(self) -> None:
        cmd_engine, ctx, session = _build_engine_and_ctx()
        dest = session.get(Room, DEST_ROOM_ID)
        assert dest is not None
        dest.terrain = "mountain"
        session.add(dest)
        stats = session.get(PlayerStats, ctx.player.id)
        assert stats is not None
        stats.skills = {"survival": 50}
        session.add(stats)
        session.commit()
        ctx.player.flags = {**ctx.player.flags, "has_key": True}

        cmd_engine.handle_command("go east", ctx)

        assert ctx.player.current_room_id == DEST_ROOM_ID

    def test_look_shows_terrain_description(self) -> None:
        cmd_engine, ctx, session = _build_engine_and_ctx()
        room = session.get(Room, START_ROOM_ID)
        assert room is not None
        room.terrain = "forest"
        session.add(room)
        session.commit()
        ctx.room = room

        cmd_engine.handle_command("look", ctx)

        assert any("undergrowth" in m for m in ctx.messages)


class TestJournal:
    def test_journal_shows_visited_places_and_met_npcs(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.player.visited_rooms = [START_ROOM_ID, DEST_ROOM_ID]
        ctx.player.met_npcs = []

        cmd_engine.handle_command("journal", ctx)

        assert any("Start Room" in m and "Dest Room" in m for m in ctx.messages)

    def test_journal_shows_lore_flags(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.player.flags = {**ctx.player.flags, "lore:ancient_ruins": True}

        cmd_engine.handle_command("journal", ctx)

        assert any("ancient_ruins" in m for m in ctx.messages)

    def test_journal_empty_state(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("journal", ctx)

        assert any("none yet" in m for m in ctx.messages)
