"""Sprint 70: social emotes (wave/point) + the player `quests` inspection command."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.models.world import Room
from lorecraft.features.quests.models import PlayerQuestProgress, Quest
from tests.unit.test_chat_broadcast import _ctx, _player


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        yield session


@pytest.fixture
def registry() -> CommandRegistry:
    registry = CommandRegistry()
    register_all_commands(registry)
    return registry


def _seed_room(session: Session) -> None:
    session.add(Room(id="square", name="Square", description="d", map_x=0, map_y=0))


def _run(registry: CommandRegistry, verb: str, noun: str | None, ctx: object) -> None:
    registry.get(verb).handler(noun, ctx)  # type: ignore[arg-type]


class TestEmotes:
    def test_wave_no_target(self, session: Session, registry: CommandRegistry) -> None:
        _seed_room(session)
        player = _player(session, "wanda", "square")
        session.commit()
        ctx = _ctx(session, player, ConnectionManager())

        _run(registry, "wave", None, ctx)

        assert ctx.messages == ["You wave."]
        assert ctx.room_messages == ["Wanda waves."]

    def test_wave_at_present_player(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        _seed_room(session)
        player = _player(session, "wanda", "square")
        _player(session, "bob", "square")  # co-located, username "Bob"
        session.commit()
        ctx = _ctx(session, player, ConnectionManager())

        _run(registry, "wave", "at Bob", ctx)

        assert ctx.messages == ["You wave at Bob."]
        assert ctx.room_messages == ["Wanda waves at Bob."]

    def test_point_at_raw_noun(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        _seed_room(session)
        player = _player(session, "wanda", "square")
        session.commit()
        ctx = _ctx(session, player, ConnectionManager())

        _run(registry, "point", "at sign", ctx)

        assert ctx.messages == ["You point at sign."]
        assert ctx.room_messages == ["Wanda points at sign."]

    def test_point_with_no_target_warns(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        _seed_room(session)
        player = _player(session, "wanda", "square")
        session.commit()
        ctx = _ctx(session, player, ConnectionManager())

        _run(registry, "point", None, ctx)

        assert ctx.messages == ["Point at what?"]
        assert ctx.room_messages == []

    def test_emote_poses_free_text_action(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        _seed_room(session)
        player = _player(session, "wanda", "square")
        session.commit()
        ctx = _ctx(session, player, ConnectionManager())

        _run(registry, "emote", "leans on the old sign", ctx)

        assert ctx.messages == ["You emote: Wanda leans on the old sign."]
        assert ctx.room_messages == ["Wanda leans on the old sign."]

    def test_smile_laugh_and_nod(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        _seed_room(session)
        player = _player(session, "wanda", "square")
        _player(session, "bob", "square")
        session.commit()
        ctx = _ctx(session, player, ConnectionManager())

        _run(registry, "smile", "at Bob", ctx)
        _run(registry, "laugh", None, ctx)
        _run(registry, "nod", "at Bob", ctx)

        assert ctx.messages == [
            "You smile at Bob.",
            "You laugh.",
            "You nod at Bob.",
        ]
        assert ctx.room_messages == [
            "Wanda smiles at Bob.",
            "Wanda laughs.",
            "Wanda nods at Bob.",
        ]


class TestQuestsCommand:
    def _seed_quest(self, session: Session, status: str, stage_id: str) -> None:
        session.add(
            Quest(
                id="amulet",
                title="Find the Amulet",
                description="d",
                stages=[
                    {"id": "s1", "description": "Search the crypt."},
                    {"id": "s2", "description": "Return it to Mira."},
                ],
            )
        )
        session.add(
            PlayerQuestProgress(
                player_id="wanda",
                quest_id="amulet",
                current_stage_id=stage_id,
                status=status,
                started_at=0.0,
            )
        )

    def test_no_quests(self, session: Session, registry: CommandRegistry) -> None:
        _seed_room(session)
        player = _player(session, "wanda", "square")
        session.commit()
        ctx = _ctx(session, player, ConnectionManager())

        _run(registry, "quests", None, ctx)

        assert ctx.messages == ["You have no quests yet."]

    def test_active_multistage_shows_stage_and_objective(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        _seed_room(session)
        player = _player(session, "wanda", "square")
        self._seed_quest(session, status="active", stage_id="s1")
        session.commit()
        ctx = _ctx(session, player, ConnectionManager())

        _run(registry, "quests", None, ctx)

        lines = [str(m) for m in ctx.messages]
        assert lines[0] == "Your quests:"
        assert "  • Find the Amulet — stage 1/2: Search the crypt." in lines

    def test_completed_quest_marked_done(
        self, session: Session, registry: CommandRegistry
    ) -> None:
        _seed_room(session)
        player = _player(session, "wanda", "square")
        self._seed_quest(session, status="completed", stage_id="s2")
        session.commit()
        ctx = _ctx(session, player, ConnectionManager())

        _run(registry, "quests", None, ctx)

        lines = [str(m) for m in ctx.messages]
        assert "  ✓ Find the Amulet — completed" in lines
