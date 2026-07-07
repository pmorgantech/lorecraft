"""Sprint 53.3: mark boons (MarkBoonModifierSource) + the `marks` command."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.modifiers import resolve
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.models.player import Player
from lorecraft.features.marks.boons import MarkBoonModifierSource
from lorecraft.features.marks.commands import register_mark_commands
from lorecraft.features.marks.models import (
    MarkRegistry,
    earned_flag,
    validate_marks_document,
)
from lorecraft.features.marks.service import MarkService
from tests.unit.test_marks_service import _ctx, _seed

ROOM = "square"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        yield session


def _registry_with(*marks: dict[str, object]) -> MarkRegistry:
    registry = MarkRegistry()
    registry.load_document(validate_marks_document({"marks": list(marks)}))
    return registry


def _boon_mark(mark_id: str = "keen", **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": mark_id,
        "name": "Mark of the Keen Eye",
        "description": "Sharper senses in the wild.",
        "criteria": {"rooms_visited": [ROOM]},
        "boons": [{"key": "skill.perception", "kind": "add", "amount": 2}],
    }
    base.update(overrides)
    return base


class TestBoonSource:
    def test_earned_mark_contributes_boons(self, session: Session) -> None:
        player = _seed(session)
        source = MarkBoonModifierSource(_registry_with(_boon_mark()))
        player.flags = {earned_flag("keen"): True}
        session.add(player)
        session.commit()

        mods = list(source.modifiers_for(session, "player", "p1"))

        assert len(mods) == 1
        assert mods[0].key == "skill.perception"
        assert mods[0].source == "mark:keen"
        assert resolve("skill.perception", 10.0, mods) == 12.0

    def test_unearned_mark_contributes_nothing(self, session: Session) -> None:
        _seed(session)
        source = MarkBoonModifierSource(_registry_with(_boon_mark()))
        assert list(source.modifiers_for(session, "player", "p1")) == []

    def test_non_player_entities_ignored(self, session: Session) -> None:
        _seed(session)
        source = MarkBoonModifierSource(_registry_with(_boon_mark()))
        assert list(source.modifiers_for(session, "room", ROOM)) == []

    def test_unknown_player_ignored(self, session: Session) -> None:
        _seed(session)
        source = MarkBoonModifierSource(_registry_with(_boon_mark()))
        assert list(source.modifiers_for(session, "player", "ghost")) == []


class TestMarksCommand:
    def _run(
        self, session: Session, player: Player, registry: MarkRegistry
    ) -> list[str]:
        commands = CommandRegistry()
        register_mark_commands(commands, MarkService(registry))
        ctx = _ctx(session, player)
        command = commands.get("marks")
        assert command is not None
        command.handler(None, ctx)
        return ctx.messages

    def test_earned_and_teasers(self, session: Session) -> None:
        player = _seed(session)
        registry = _registry_with(
            _boon_mark("keen"),
            _boon_mark("wanderer", name="Mark of the Wanderer"),
        )
        player.flags = {earned_flag("keen"): True}

        messages = self._run(session, player, registry)

        assert messages[0] == "=== Marks ==="
        assert any("Mark of the Keen Eye — Sharper senses" in m for m in messages)
        assert sum(1 for m in messages if m == "??? — undiscovered") == 1

    def test_hidden_marks_omitted_until_earned(self, session: Session) -> None:
        player = _seed(session)
        registry = _registry_with(_boon_mark("secret", hidden=True))

        messages = self._run(session, player, registry)
        assert messages == ["No marks are known in this world."]

        player.flags = {earned_flag("secret"): True}
        messages = self._run(session, player, registry)
        assert any("Mark of the Keen Eye" in m for m in messages)

    def test_empty_registry_message(self, session: Session) -> None:
        player = _seed(session)
        messages = self._run(session, player, MarkRegistry())
        assert messages == ["No marks are known in this world."]
