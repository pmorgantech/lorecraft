"""Sprint 55.2: context_commands schema, registry load, and content-lint."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.models.world import NPC, Item
from lorecraft.features.context_commands.models import (
    ContextCommandRegistry,
    lint_context_commands,
)
from lorecraft.world.validator import ContextCommandData


class TestSchema:
    def test_valid_command(self) -> None:
        spec = ContextCommandData.model_validate(
            {
                "aliases": ["yank"],
                "help": "pull the lever",
                "say": "The lever clunks.",
                "side_effects": {"set_flags": ["lever_pulled"]},
            }
        )
        assert spec.aliases == ["yank"]
        assert spec.side_effects == {"set_flags": ["lever_pulled"]}

    def test_command_that_does_nothing_rejected(self) -> None:
        with pytest.raises(ValidationError, match="say.*and/or.*side_effects"):
            ContextCommandData.model_validate({"help": "does nothing"})

    def test_say_only_is_valid(self) -> None:
        spec = ContextCommandData.model_validate({"say": "You admire the mural."})
        assert spec.side_effects == {}

    def test_unknown_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContextCommandData.model_validate({"say": "hi", "bogus": 1})


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        yield session


class TestRegistryLoad:
    def test_scans_items_and_npcs(self, session: Session) -> None:
        session.add(
            Item(
                id="lever",
                name="Lever",
                description="d",
                context_commands={
                    "pull": {"say": "clunk", "side_effects": {"set_flags": ["p"]}}
                },
            )
        )
        session.add(
            NPC(
                id="dog",
                name="Dog",
                description="d",
                current_room_id="sq",
                home_room_id="sq",
                dialogue_tree_id="",
                context_commands={"pet": {"say": "The dog wags its tail."}},
            )
        )
        session.commit()

        registry = ContextCommandRegistry()
        registry.load_from_session(session)

        assert set(registry.verbs()) == {"pull", "pet"}
        pull = registry.bindings_for("pull")[0]
        assert pull.owner_type == "item" and pull.owner_id == "lever"
        assert pull.gate == "object_present:lever"
        pet = registry.bindings_for("pet")[0]
        assert pet.gate == "npc_present:dog"

    def test_shared_verb_collects_multiple_bindings(self, session: Session) -> None:
        for lever_id in ("lever_a", "lever_b"):
            session.add(
                Item(
                    id=lever_id,
                    name=lever_id,
                    description="d",
                    context_commands={"pull": {"say": "clunk"}},
                )
            )
        session.commit()
        registry = ContextCommandRegistry()
        registry.load_from_session(session)
        assert {b.owner_id for b in registry.bindings_for("pull")} == {
            "lever_a",
            "lever_b",
        }


class TestLint:
    def test_unknown_side_effect_reported(self, session: Session) -> None:
        session.add(
            Item(
                id="lever",
                name="Lever",
                description="d",
                context_commands={"pull": {"side_effects": {"explode": {}}}},
            )
        )
        session.commit()
        registry = ContextCommandRegistry()
        registry.load_from_session(session)

        problems = lint_context_commands(
            registry.all_bindings(), known_side_effects={"set_flags", "start_quest"}
        )
        assert len(problems) == 1
        assert "'explode'" in problems[0]

    def test_known_side_effects_lint_clean(self, session: Session) -> None:
        session.add(
            Item(
                id="lever",
                name="Lever",
                description="d",
                context_commands={"pull": {"side_effects": {"set_flags": ["x"]}}},
            )
        )
        session.commit()
        registry = ContextCommandRegistry()
        registry.load_from_session(session)
        assert (
            lint_context_commands(
                registry.all_bindings(), known_side_effects={"set_flags"}
            )
            == []
        )
