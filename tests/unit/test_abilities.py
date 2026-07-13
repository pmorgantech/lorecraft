"""Unit tests for the Tier 1 generic ability mechanism (engine/game/abilities.py).

All `AbilityDef`s here are SYNTHETIC — constructed in-test, never referencing a
real discipline or ability id (that content arrives in Sprint 78). These tests
cover only the opinion-free mechanism: acquisition gating, usage gating,
proficiency growth, and the cooldown/resource primitives.
"""

from __future__ import annotations

import pytest

from lorecraft.engine.game.abilities import (
    PROFICIENCY_IMPROVE_KEY,
    AbilityDef,
    ActorState,
    ResourceCost,
    UsageRequirements,
    WorldState,
    can_afford_resource,
    check_acquisition,
    check_usage,
    cooldown_expiry,
    is_off_cooldown,
    resolve_proficiency,
)
from lorecraft.engine.game.checks import CHECK_CEIL, CHECK_FLOOR
from lorecraft.engine.game.modifiers import Modifier
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import PlayerStats
from lorecraft.errors import ValidationError


def _ability(**overrides: object) -> AbilityDef:
    """A synthetic AbilityDef with sensible defaults, overridable per test."""
    base: dict[str, object] = {
        "id": "synthetic_a",
        "discipline_id": "synthetic_discipline",
        "tier": 1,
        "ability_type": "active",
        "activation_type": "instant",
    }
    base.update(overrides)
    return AbilityDef(**base)  # type: ignore[arg-type]


def _stats(**overrides: object) -> PlayerStats:
    stats = PlayerStats(player_id="p1")
    for key, value in overrides.items():
        setattr(stats, key, value)
    return stats


# --- AbilityDef ---------------------------------------------------------------


def test_ability_def_defaults() -> None:
    ability = _ability()
    assert ability.prerequisites == ()
    assert ability.cost == 0
    assert ability.required_discipline_rank == 0
    assert ability.required_level is None
    assert ability.usage == UsageRequirements()


def test_ability_type_is_open_string_not_validated() -> None:
    # §5.5: the field is a plain string; a value the engine has never heard of
    # (e.g. a future combat type) constructs fine — adding types is content work.
    ability = _ability(ability_type="stance", activation_type="channeled")
    assert ability.ability_type == "stance"
    assert ability.activation_type == "channeled"


# --- check_acquisition --------------------------------------------------------


def test_acquisition_all_conditions_met() -> None:
    ability = _ability(cost=2, required_discipline_rank=1, required_level=3)
    stats = _stats(skill_points=5, level=3)
    result = check_acquisition(stats, ability, discipline_rank=1)
    assert result.allowed
    assert result.affordable
    assert result.prerequisites_met
    assert result.rank_met
    assert result.level_met
    assert result.missing_prerequisites == ()


def test_acquisition_blocked_by_cost() -> None:
    ability = _ability(cost=10)
    stats = _stats(skill_points=3)
    result = check_acquisition(stats, ability, discipline_rank=0)
    assert not result.allowed
    assert not result.affordable


def test_acquisition_exact_cost_is_affordable() -> None:
    ability = _ability(cost=4)
    stats = _stats(skill_points=4)
    assert check_acquisition(stats, ability, discipline_rank=0).affordable


def test_acquisition_missing_prerequisites_listed() -> None:
    ability = _ability(prerequisites=("prior_a", "prior_b"))
    stats = _stats(skill_points=0, unlocked_nodes=["prior_a"])
    result = check_acquisition(stats, ability, discipline_rank=0)
    assert not result.allowed
    assert not result.prerequisites_met
    assert result.missing_prerequisites == ("prior_b",)


def test_acquisition_all_prerequisites_held() -> None:
    ability = _ability(prerequisites=("prior_a",))
    stats = _stats(unlocked_nodes=["prior_a", "unrelated"])
    result = check_acquisition(stats, ability, discipline_rank=0)
    assert result.prerequisites_met
    assert result.missing_prerequisites == ()


def test_acquisition_blocked_by_discipline_rank() -> None:
    ability = _ability(required_discipline_rank=5)
    stats = _stats()
    result = check_acquisition(stats, ability, discipline_rank=4)
    assert not result.rank_met
    assert not result.allowed


def test_acquisition_blocked_by_level() -> None:
    ability = _ability(required_level=10)
    stats = _stats(level=9)
    result = check_acquisition(stats, ability, discipline_rank=0)
    assert not result.level_met
    assert not result.allowed


def test_acquisition_no_level_gate_passes() -> None:
    ability = _ability(required_level=None)
    stats = _stats(level=1)
    assert check_acquisition(stats, ability, discipline_rank=0).level_met


def test_acquisition_reports_every_failed_condition() -> None:
    ability = _ability(
        cost=99,
        prerequisites=("missing",),
        required_discipline_rank=9,
        required_level=9,
    )
    stats = _stats(skill_points=0, level=1, unlocked_nodes=[])
    result = check_acquisition(stats, ability, discipline_rank=0)
    assert not result.affordable
    assert not result.prerequisites_met
    assert not result.rank_met
    assert not result.level_met
    assert not result.allowed


# --- check_usage --------------------------------------------------------------


def test_usage_no_requirements_is_usable() -> None:
    result = check_usage(ActorState(), _ability(), None, WorldState())
    assert result.usable


def test_usage_character_state_via_flag() -> None:
    ability = _ability(usage=UsageRequirements(character_states=("hidden",)))
    actor = ActorState(flags=frozenset({"state.hidden"}))
    result = check_usage(actor, ability, None, WorldState())
    assert result.character_states_met
    assert result.usable


def test_usage_character_state_via_active_effect() -> None:
    ability = _ability(usage=UsageRequirements(character_states=("burning",)))
    actor = ActorState(active_effects=frozenset({"burning"}))
    assert check_usage(actor, ability, None, WorldState()).character_states_met


def test_usage_missing_character_state_reported() -> None:
    ability = _ability(usage=UsageRequirements(character_states=("hidden", "calm")))
    actor = ActorState(flags=frozenset({"state.hidden"}))
    result = check_usage(actor, ability, None, WorldState())
    assert not result.usable
    assert result.missing_character_states == ("calm",)


def test_usage_target_states_require_a_target() -> None:
    ability = _ability(usage=UsageRequirements(target_states=("marked",)))
    result = check_usage(ActorState(), ability, None, WorldState())
    assert not result.target_states_met
    assert result.missing_target_states == ("marked",)
    assert not result.usable


def test_usage_target_states_met() -> None:
    ability = _ability(usage=UsageRequirements(target_states=("marked",)))
    target = ActorState(flags=frozenset({"state.marked"}))
    result = check_usage(ActorState(), ability, target, WorldState())
    assert result.target_states_met
    assert result.usable


def test_usage_terrain_match() -> None:
    ability = _ability(usage=UsageRequirements(terrain=("outdoor",)))
    world = WorldState(terrain=frozenset({"outdoor", "forest"}))
    assert check_usage(ActorState(), ability, None, world).terrain_met


def test_usage_terrain_mismatch() -> None:
    ability = _ability(usage=UsageRequirements(terrain=("outdoor",)))
    world = WorldState(terrain=frozenset({"indoor"}))
    result = check_usage(ActorState(), ability, None, world)
    assert not result.terrain_met
    assert not result.usable


def test_usage_empty_terrain_requirement_matches_anywhere() -> None:
    ability = _ability(usage=UsageRequirements(terrain=()))
    world = WorldState(terrain=frozenset({"indoor"}))
    assert check_usage(ActorState(), ability, None, world).terrain_met


def test_usage_resource_affordable() -> None:
    ability = _ability(
        usage=UsageRequirements(resource=ResourceCost(type="stamina", cost=10))
    )
    actor = ActorState(resources={"stamina": 10.0})
    assert check_usage(actor, ability, None, WorldState()).resource_met


def test_usage_resource_insufficient() -> None:
    ability = _ability(
        usage=UsageRequirements(resource=ResourceCost(type="stamina", cost=10))
    )
    actor = ActorState(resources={"stamina": 3.0})
    result = check_usage(actor, ability, None, WorldState())
    assert not result.resource_met
    assert not result.usable


def test_usage_zero_cost_resource_ignored() -> None:
    ability = _ability(
        usage=UsageRequirements(resource=ResourceCost(type="stamina", cost=0))
    )
    # No stamina meter at all, but a 0-cost declaration must not block.
    assert check_usage(ActorState(), ability, None, WorldState()).resource_met


def test_usage_cooldown_not_ready() -> None:
    ability = _ability(usage=UsageRequirements(cooldown_seconds=30))
    actor = ActorState(cooldowns={"synthetic_a": 100.0})
    world = WorldState(now_epoch=90.0)
    result = check_usage(actor, ability, None, world)
    assert not result.cooldown_ready
    assert not result.usable


def test_usage_cooldown_elapsed() -> None:
    ability = _ability(usage=UsageRequirements(cooldown_seconds=30))
    actor = ActorState(cooldowns={"synthetic_a": 100.0})
    world = WorldState(now_epoch=100.0)
    assert check_usage(actor, ability, None, world).cooldown_ready


def test_usage_no_cooldown_entry_is_ready() -> None:
    ability = _ability()
    assert check_usage(ActorState(), ability, None, WorldState()).cooldown_ready


# --- cooldown / resource primitives -------------------------------------------


def test_can_afford_resource() -> None:
    assert can_afford_resource(10.0, 5.0)
    assert can_afford_resource(5.0, 5.0)
    assert not can_afford_resource(4.0, 5.0)


def test_can_afford_resource_rejects_negative_cost() -> None:
    with pytest.raises(ValidationError):
        can_afford_resource(10.0, -1.0)


def test_cooldown_expiry() -> None:
    assert cooldown_expiry(100.0, 30.0) == 130.0


def test_cooldown_expiry_rejects_negative_seconds() -> None:
    with pytest.raises(ValidationError):
        cooldown_expiry(100.0, -5.0)


def test_is_off_cooldown() -> None:
    assert is_off_cooldown(100.0, None)
    assert is_off_cooldown(100.0, 100.0)
    assert is_off_cooldown(101.0, 100.0)
    assert not is_off_cooldown(99.0, 100.0)


# --- resolve_proficiency ------------------------------------------------------


def _first_roll(seed: int) -> int:
    """The d100 a fresh GameRng(seed) yields — the roll resolve_proficiency uses."""
    return GameRng(seed).randint(1, 100)


def test_proficiency_capped_returns_max_without_rolling() -> None:
    # At/above the cap: no growth, returns the cap, does not consume the rng.
    rng = GameRng(1)
    assert resolve_proficiency(rng, 100, [], improve_chance=1.0, max_rank=100) == 100.0
    assert resolve_proficiency(rng, 105, [], improve_chance=1.0, max_rank=100) == 100.0


def test_proficiency_grows_by_at_most_one() -> None:
    for seed in range(50):
        result = resolve_proficiency(
            GameRng(seed), 10, [], improve_chance=0.5, max_rank=100
        )
        assert result in (10.0, 11.0)


def test_proficiency_deterministic_success() -> None:
    # improve_chance 1.0 -> target clamped to CHECK_CEIL; success iff roll <= ceil.
    seed = 7
    target = CHECK_CEIL
    expected = 1.0 if _first_roll(seed) <= target else 0.0
    result = resolve_proficiency(GameRng(seed), 0, [], improve_chance=1.0, max_rank=100)
    assert result == 0.0 + expected


def test_proficiency_deterministic_floor() -> None:
    # improve_chance 0.0 -> target clamped to CHECK_FLOOR (never impossible).
    seed = 3
    expected_grew = _first_roll(seed) <= CHECK_FLOOR
    result = resolve_proficiency(GameRng(seed), 0, [], improve_chance=0.0, max_rank=100)
    assert result == (1.0 if expected_grew else 0.0)


def test_proficiency_modifier_raises_learn_target() -> None:
    # A large additive bonus to the improve key pushes the target to the ceiling,
    # so a roll that would fail at the floor now succeeds.
    seed = 3
    roll = _first_roll(seed)
    assert CHECK_FLOOR < roll <= CHECK_CEIL  # guard: seed sits between the bounds
    boost = [
        Modifier(key=PROFICIENCY_IMPROVE_KEY, kind="add", amount=100.0, source="t")
    ]
    result = resolve_proficiency(
        GameRng(seed), 0, boost, improve_chance=0.0, max_rank=100
    )
    assert result == 1.0


def test_proficiency_rejects_out_of_range_chance() -> None:
    with pytest.raises(ValidationError):
        resolve_proficiency(GameRng(1), 0, [], improve_chance=1.5, max_rank=100)
    with pytest.raises(ValidationError):
        resolve_proficiency(GameRng(1), 0, [], improve_chance=-0.1, max_rank=100)


def test_proficiency_rejects_negative_max_rank() -> None:
    with pytest.raises(ValidationError):
        resolve_proficiency(GameRng(1), 0, [], improve_chance=0.5, max_rank=-1)
