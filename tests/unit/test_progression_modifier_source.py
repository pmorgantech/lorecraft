"""Passive skill-tree abilities feed the modifier resolver (Sprint 74.4)."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.modifiers import resolve
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.features.encumbrance.rules import carry_base, resolve_carry_capacity
from lorecraft.features.progression.modifier_source import SkillTreeModifierSource
from lorecraft.features.progression.skill_tree import (
    SkillTreeRegistry,
    validate_skill_tree_document,
)


def _registry() -> SkillTreeRegistry:
    doc = validate_skill_tree_document(
        {
            "nodes": [
                {
                    "id": "mule",
                    "name": "Mule",
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
                    "id": "haggler",
                    "name": "Haggler",
                    "cost": 2,
                    "unlock": {
                        "modifier": {
                            "key": "price.buy",
                            "kind": "mult",
                            "amount": 0.95,
                        }
                    },
                },
                {
                    "id": "silver_tongue",
                    "name": "Silver Tongue",
                    "cost": 1,
                    "unlock": {},
                },
            ]
        }
    )
    registry = SkillTreeRegistry()
    registry.load_document(doc)
    return registry


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def _seed(session: Session, *, unlocked: list[str], strength: int = 10) -> None:
    session.add(
        Player(id="p1", username="hero", current_room_id="r", respawn_room_id="r")
    )
    session.add(PlayerStats(player_id="p1", strength=strength, unlocked_nodes=unlocked))
    session.commit()


def test_unlocking_mule_raises_carry_capacity() -> None:
    source = SkillTreeModifierSource(_registry())
    with Session(_engine()) as session:
        _seed(session, unlocked=[])
        base = carry_base(10)

        # Nothing unlocked -> no contribution.
        no_bonus = resolve(
            "carry_capacity", base, source.modifiers_for(session, "player", "p1")
        )
        assert no_bonus == base

        stats = session.get(PlayerStats, "p1")
        assert stats is not None
        stats.unlocked_nodes = ["mule"]
        session.add(stats)
        session.commit()

        with_bonus = resolve(
            "carry_capacity", base, source.modifiers_for(session, "player", "p1")
        )
        assert with_bonus == base + 20


def test_registered_source_flows_through_resolve_for() -> None:
    from lorecraft.features.progression.modifier_source import register

    register()  # idempotent global registration
    with Session(_engine()) as session:
        _seed(session, unlocked=["mule"])
        # The registered source uses the *global* skill-tree registry; load our
        # test node into it so resolve_for sees the contribution end-to-end.
        from lorecraft.features.progression.skill_tree import get_registry

        get_registry().clear()
        get_registry().load_document(
            validate_skill_tree_document(
                {
                    "nodes": [
                        {
                            "id": "mule",
                            "name": "Mule",
                            "cost": 1,
                            "unlock": {
                                "modifier": {
                                    "key": "carry_capacity",
                                    "kind": "add",
                                    "amount": 20,
                                }
                            },
                        }
                    ]
                }
            )
        )
        capacity = resolve_carry_capacity(session, "p1", 10)
        get_registry().clear()
    assert capacity == carry_base(10) + 20


def test_price_multiplier_stacks_multiplicatively() -> None:
    source = SkillTreeModifierSource(_registry())
    with Session(_engine()) as session:
        _seed(session, unlocked=["haggler"])
        price = resolve(
            "price.buy", 100.0, source.modifiers_for(session, "player", "p1")
        )
    assert price == 95.0


def test_interaction_node_contributes_no_modifier() -> None:
    source = SkillTreeModifierSource(_registry())
    with Session(_engine()) as session:
        _seed(session, unlocked=["silver_tongue"])
        mods = list(source.modifiers_for(session, "player", "p1"))
    assert mods == []


def test_non_player_entity_gets_no_modifiers() -> None:
    source = SkillTreeModifierSource(_registry())
    with Session(_engine()) as session:
        mods = list(source.modifiers_for(session, "npc", "goblin"))
    assert mods == []
