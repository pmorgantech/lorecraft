"""AbilityModifierSource: unlocked passive abilities feed the modifier resolver
(Sprint 78.9, replaces the pre-78 progression skill-tree modifier-source test)."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.modifiers import resolve
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.features.disciplines.abilities import (
    AbilityRegistry,
    validate_ability_document,
)
from lorecraft.features.disciplines.modifier_source import AbilityModifierSource


def _registry() -> AbilityRegistry:
    registry = AbilityRegistry()
    registry.load_document(
        validate_ability_document(
            {
                "abilities": [
                    {
                        "id": "mule",
                        "name": "Mule",
                        "discipline": "fortitude",
                        "cost": 1,
                        "unlock": {
                            "modifier": {
                                "key": "carry_capacity",
                                "kind": "add",
                                "amount": 20,
                            }
                        },
                    },
                    {
                        "id": "forage",
                        "name": "Forage",
                        "discipline": "survival",
                        "cost": 1,
                        "unlock": {"enables_verb": "forage"},
                    },
                ]
            }
        )
    )
    return registry


def _session_with_unlocked(*unlocked: str) -> tuple[Session, str]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    player = Player(id="p1", username="u", current_room_id="r", respawn_room_id="r")
    session.add(player)
    session.add(PlayerStats(player_id="p1", unlocked_nodes=list(unlocked)))
    session.commit()
    return session, "p1"


def test_unlocked_passive_contributes_its_modifier() -> None:
    session, pid = _session_with_unlocked("mule")
    source = AbilityModifierSource(_registry())
    modifiers = list(source.modifiers_for(session, "player", pid))
    assert len(modifiers) == 1
    assert modifiers[0].key == "carry_capacity"
    # +20 applied over a base carry capacity.
    assert resolve("carry_capacity", 100.0, modifiers) == 120.0
    session.close()


def test_non_modifier_ability_contributes_nothing() -> None:
    session, pid = _session_with_unlocked("forage")
    source = AbilityModifierSource(_registry())
    assert list(source.modifiers_for(session, "player", pid)) == []
    session.close()


def test_unowned_ability_contributes_nothing() -> None:
    session, pid = _session_with_unlocked()  # nothing unlocked
    source = AbilityModifierSource(_registry())
    assert list(source.modifiers_for(session, "player", pid)) == []
    session.close()
