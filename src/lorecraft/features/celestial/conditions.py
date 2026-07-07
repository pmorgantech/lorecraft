"""Celestial condition gates: `moon_phase_is` / `tide_is` (Sprint 54).

Registered with both pluggable condition registries so world content can gate
**commands** (``conditions: ["moon_phase_is:full"]``) and **dialogue
choices/exits** (``conditions: {moon_phase_is: full}``) on the derived
celestial state — no engine change, the feature-registration pattern.
Worlds without a seeded clock fail closed (the gate stays shut).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.engine.clock.celestial import (
    MOON_PHASES,
    TIDES,
    moon_phase_for_day,
    tide_for_hour,
)
from lorecraft.engine.game.command_conditions import (
    ConditionResult,
    get_registry as get_command_registry,
)
from lorecraft.features.npc.dialogue_conditions import (
    get_registry as get_dialogue_registry,
)

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext


def _label(state: str) -> str:
    return state.replace("_", " ")


def _moon_phase_is(parameter: str, ctx: GameContext) -> ConditionResult:
    wanted = parameter.strip()
    if wanted not in MOON_PHASES:
        return ConditionResult(False, "The heavens give no sign.")
    if ctx.clock is None:
        return ConditionResult(False, "The heavens give no sign.")
    phase = moon_phase_for_day(ctx.clock.current_day)
    if phase == wanted:
        return ConditionResult(True)
    return ConditionResult(False, f"That waits for the {_label(wanted)} moon.")


def _tide_is(parameter: str, ctx: GameContext) -> ConditionResult:
    wanted = parameter.strip()
    if wanted not in TIDES:
        return ConditionResult(False, "The tide gives no sign.")
    if ctx.clock is None:
        return ConditionResult(False, "The tide gives no sign.")
    tide = tide_for_hour(ctx.clock.current_hour)
    if tide == wanted:
        return ConditionResult(True)
    return ConditionResult(False, f"That waits for {_label(wanted)} tide.")


def _dialogue_moon_phase_is(condition_data: object, ctx: GameContext) -> bool:
    return _moon_phase_is(str(condition_data), ctx).allowed


def _dialogue_tide_is(condition_data: object, ctx: GameContext) -> bool:
    return _tide_is(str(condition_data), ctx).allowed


def register() -> None:
    """Register the celestial gates with both condition registries. Idempotent —
    both registries are name-keyed dicts, so re-registration just overwrites."""
    get_command_registry().register("moon_phase_is", _moon_phase_is)
    get_command_registry().register("tide_is", _tide_is)
    get_dialogue_registry().register("moon_phase_is", _dialogue_moon_phase_is)
    get_dialogue_registry().register("tide_is", _dialogue_tide_is)
