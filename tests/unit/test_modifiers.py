"""Unit tests for the modifier resolver (engine_core.md §3.5)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.modifiers import (
    Modifier,
    ModifierRegistry,
    resolve,
    resolve_for,
)


def test_resolve_with_no_modifiers_returns_base() -> None:
    assert resolve("stat.strength", 10.0, []) == 10.0


def test_resolve_ignores_modifiers_for_other_keys() -> None:
    modifiers = [Modifier("skill.perception", "add", 5.0, "item:x")]
    assert resolve("stat.strength", 10.0, modifiers) == 10.0


def test_resolve_add_bucket_sums() -> None:
    modifiers = [
        Modifier("stat.strength", "add", 2.0, "item:a"),
        Modifier("stat.strength", "add", 3.0, "item:b"),
    ]
    assert resolve("stat.strength", 10.0, modifiers) == 15.0


def test_resolve_mult_bucket_multiplies() -> None:
    modifiers = [
        Modifier("stat.strength", "mult", 1.5, "trait:strong"),
        Modifier("stat.strength", "mult", 2.0, "effect:buff"),
    ]
    assert resolve("stat.strength", 10.0, modifiers) == 30.0


def test_resolve_applies_add_before_mult() -> None:
    modifiers = [
        Modifier("stat.strength", "add", 5.0, "item:a"),
        Modifier("stat.strength", "mult", 2.0, "trait:strong"),
    ]
    # (10 + 5) * 2 = 30, NOT 10 + (5*2) = 20 or 10*2 + 5 = 25.
    assert resolve("stat.strength", 10.0, modifiers) == 30.0


def test_resolve_clamp_max_caps_value() -> None:
    modifiers = [
        Modifier("skill.perception", "add", 50.0, "item:a"),
        Modifier("skill.perception", "clamp_max", 95.0, "engine:ceiling"),
    ]
    assert resolve("skill.perception", 60.0, modifiers) == 95.0


def test_resolve_clamp_min_floors_value() -> None:
    modifiers = [
        Modifier("meter.hp.max", "add", -200.0, "effect:curse"),
        Modifier("meter.hp.max", "clamp_min", 1.0, "engine:floor"),
    ]
    assert resolve("meter.hp.max", 100.0, modifiers) == 1.0


def test_resolve_multiple_clamp_max_uses_the_tightest() -> None:
    modifiers = [
        Modifier("price.buy", "clamp_max", 95.0, "a"),
        Modifier("price.buy", "clamp_max", 50.0, "b"),
    ]
    assert resolve("price.buy", 200.0, modifiers) == 50.0


def test_resolve_worked_example_from_spec() -> None:
    """engine_core.md §3.5's worked example: base perception 30; helm +5 add;
    trait sure-eyed x1.1 mult; effect weakened x0.8 mult; clamp_max 95 ->
    (30+5) x 1.1 x 0.8 = 30.8 -> consumer ints to 30."""
    modifiers = [
        Modifier("skill.perception", "add", 5.0, "item:miners_helm"),
        Modifier("skill.perception", "mult", 1.1, "trait:sure-eyed"),
        Modifier("skill.perception", "mult", 0.8, "effect:weakened"),
        Modifier("skill.perception", "clamp_max", 95.0, "engine:ceiling"),
    ]
    result = resolve("skill.perception", 30.0, modifiers)
    assert result == 30.8
    assert int(result) == 30


def test_resolve_order_within_a_bucket_does_not_matter() -> None:
    a = [
        Modifier("x", "add", 1.0, "a"),
        Modifier("x", "add", 2.0, "b"),
        Modifier("x", "mult", 3.0, "c"),
    ]
    b = list(reversed(a))
    assert resolve("x", 10.0, a) == resolve("x", 10.0, b)


class _StubSource:
    def __init__(self, modifiers: Iterable[Modifier]) -> None:
        self._modifiers = list(modifiers)

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> Iterable[Modifier]:
        return self._modifiers


def test_modifier_registry_collects_from_all_registered_sources() -> None:
    registry = ModifierRegistry()
    registry.register(_StubSource([Modifier("stat.strength", "add", 2.0, "a")]))
    registry.register(_StubSource([Modifier("stat.strength", "add", 3.0, "b")]))

    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        collected = registry.collect(session, "player", "player-1")

    assert len(collected) == 2
    assert sum(m.amount for m in collected) == 5.0


def test_resolve_for_uses_the_global_registry() -> None:
    from lorecraft.engine.game import modifiers as modifiers_module

    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    registry = ModifierRegistry()
    registry.register(_StubSource([Modifier("stat.strength", "add", 4.0, "a")]))

    original_registry = modifiers_module._registry
    modifiers_module._registry = registry
    try:
        with Session(engine) as session:
            result = resolve_for(session, "player", "player-1", "stat.strength", 10.0)
    finally:
        modifiers_module._registry = original_registry

    assert result == 14.0
