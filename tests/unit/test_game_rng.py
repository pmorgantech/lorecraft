"""Unit tests for GameRng — the sanctioned randomness source (engine_core.md §3.6)."""

from __future__ import annotations

from lorecraft.engine.game.rng import GameRng


def test_same_seed_produces_identical_sequences() -> None:
    a = GameRng(42)
    b = GameRng(42)

    draws_a = [a.randint(1, 100) for _ in range(20)]
    draws_b = [b.randint(1, 100) for _ in range(20)]

    assert draws_a == draws_b


def test_different_seeds_produce_different_sequences() -> None:
    a = GameRng(1)
    b = GameRng(2)

    draws_a = [a.randint(1, 1_000_000) for _ in range(20)]
    draws_b = [b.randint(1, 1_000_000) for _ in range(20)]

    assert draws_a != draws_b


def test_unseeded_instances_are_independent() -> None:
    a = GameRng()
    b = GameRng()

    # Not a determinism guarantee (OS entropy) — just confirms independent
    # underlying random.Random instances, not a shared global state.
    assert a is not b
    assert a._random is not b._random  # noqa: SLF001


def test_randint_respects_bounds() -> None:
    rng = GameRng(7)
    for _ in range(100):
        value = rng.randint(5, 10)
        assert 5 <= value <= 10


def test_uniform_respects_bounds() -> None:
    rng = GameRng(7)
    for _ in range(100):
        value = rng.uniform(0.0, 1.0)
        assert 0.0 <= value <= 1.0


def test_choice_returns_a_member_of_the_sequence() -> None:
    rng = GameRng(7)
    options = ("clear", "rain", "snow")
    for _ in range(20):
        assert rng.choice(options) in options


def test_chance_always_true_at_probability_one() -> None:
    rng = GameRng(7)
    assert all(rng.chance(1.0) for _ in range(50))


def test_chance_always_false_at_probability_zero() -> None:
    rng = GameRng(7)
    assert not any(rng.chance(0.0) for _ in range(50))


def test_chance_seeded_determinism() -> None:
    a = GameRng(99)
    b = GameRng(99)

    draws_a = [a.chance(0.5) for _ in range(30)]
    draws_b = [b.chance(0.5) for _ in range(30)]

    assert draws_a == draws_b
