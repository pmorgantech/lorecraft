"""Reputation-gated command/dialogue conditions (Sprint 24.3).

Registers the canonical `actor_reputation_at_least` predicate on both the command and dialogue
condition registries (same capability, two authoring surfaces) plus an `adjust_reputation` side
effect — no core edits.

Scripting-engine A0.5 (`docs/scripting_engine_design.md` §8.6) collapsed the historical
`reputation_at_least` (command) / `min_reputation` (dialogue) synonym pair to the one §8.4
name `actor_reputation_at_least`. The two registries keep their own param encodings for now
(command: colon-string `<target_type>:<target_id>:<min>`; dialogue: a `{target_type, target_id,
min}` map) — the colon-string→map normalization rides along with A2's load-path validator.

Sprint 30.1 adds the flip side: an `adjust_reputation` side effect on the
shared npc/side_effects.py registry, so dialogue choices and quest
branches can make standing changes a *consequence* ("world-state/standing
changes" per docs/roadmap.md Sprint 30.1), not just a gate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.engine.game import command_conditions
from lorecraft.engine.game.command_conditions import ConditionResult
from lorecraft.engine.scripting.vocabulary import (
    CapabilitySig,
    ParamSpec,
    Subject,
    VocabEntry,
    VocabKind,
)
from lorecraft.features.npc import dialogue_conditions, side_effects
from lorecraft.features.reputation.service import ReputationService
from lorecraft.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext

_reputation = ReputationService()

# Shared params describing the target both authoring surfaces address: the command
# surface encodes them as a `<target_type>:<target_id>:<min>` colon-string, the
# dialogue surface as a `{target_type, target_id, min}` map.
_TARGET_PARAMS = (
    ParamSpec(
        "target_type",
        "str",
        doc="Kind of entity whose standing is checked, e.g. 'npc' or 'faction' "
        "(command: colon-string field 1; dialogue: map key).",
    ),
    ParamSpec(
        "target_id",
        "str",
        doc="Id of the target within that type "
        "(command: colon-string field 2; dialogue: map key).",
    ),
)

# One canonical descriptor for the standing gate, registered on BOTH the command and
# dialogue condition surfaces (same capability, two authoring surfaces — the catalog's
# idempotent same-capability registration keeps a single entry, mirroring
# `actor_has_flag`/`actor_lacks_flag`). The descriptor must be identical on both sides so
# the generated `docs/scripting_api.md` is independent of import order.
_REPUTATION_AT_LEAST_SPEC = VocabEntry(
    name="actor_reputation_at_least",
    kind=VocabKind.CONDITION,
    subject=Subject.ACTOR,
    category="reputation",
    doc="The actor's standing with a target is at least the given minimum.",
    capability=CapabilitySig(Subject.ACTOR, "reputation", "standing", "at_least"),
    params=(
        *_TARGET_PARAMS,
        ParamSpec(
            "min",
            "int",
            doc="Minimum standing required "
            "(command: colon-string field 3; dialogue: 'min' map key).",
        ),
    ),
)

_ADJUST_REPUTATION_SPEC = VocabEntry(
    name="adjust_reputation",
    kind=VocabKind.EFFECT,
    subject=Subject.ACTOR,
    category="reputation",
    doc="Change the actor's standing with a target by a signed amount.",
    capability=CapabilitySig(Subject.ACTOR, "reputation", "standing", "adjust"),
    params=(
        *_TARGET_PARAMS,
        ParamSpec(
            "delta", "int", doc="Signed standing change to apply ('delta' map key)."
        ),
    ),
)


def _reputation_at_least(parameter: str, ctx: "GameContext") -> ConditionResult:
    parts = parameter.split(":", 2)
    if len(parts) != 3:
        return ConditionResult(True)
    target_type, target_id, min_standing_raw = parts
    try:
        min_standing = int(min_standing_raw)
    except ValueError:
        return ConditionResult(True)

    standing = _reputation.standing_of(
        ctx.session, ctx.player.id, target_type, target_id
    )
    if standing < min_standing:
        return ConditionResult(False, "They don't trust you enough for that yet.")
    return ConditionResult(True)


def _reputation_at_least_dialogue(data: JsonObject, ctx: "GameContext") -> bool:
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    min_standing = data.get("min")
    if not isinstance(target_type, str) or not isinstance(target_id, str):
        return True
    if not isinstance(min_standing, (int, float)):
        return True
    standing = _reputation.standing_of(
        ctx.session, ctx.player.id, target_type, target_id
    )
    return standing >= min_standing


def _handle_adjust_reputation(data: JsonValue, ctx: "GameContext") -> None:
    """`adjust_reputation: {target_type: npc, target_id: thor, delta: 10}`."""
    if not isinstance(data, dict):
        return
    target_type = data.get("target_type")
    target_id = data.get("target_id")
    delta = data.get("delta")
    if not isinstance(target_type, str) or not isinstance(target_id, str):
        return
    if not isinstance(delta, (int, float)) or isinstance(delta, bool):
        return
    _reputation.adjust(ctx.session, ctx.player.id, target_type, target_id, int(delta))


def register() -> None:
    """Register the reputation conditions + `adjust_reputation` side effect on
    the shared Tier 1 registries.

    Called by the `reputation` feature's manifest (`lorecraft/features/
    reputation`) when the feature is enabled — no longer a module-level import
    side effect, so disabling the feature actually leaves these unregistered.
    Idempotent: re-registering the same name+capability is a harmless no-op in
    the shared catalog (see `Vocabulary.register`).

    Uses `register_spec` (not the bare `register`) so both `actor_reputation_at_least`
    and `adjust_reputation` publish a self-describing `VocabEntry` into the shared
    scripting catalog — this is what makes them appear in the generated
    `docs/scripting_api.md` (§8). The command and dialogue registries both register the
    one canonical name `actor_reputation_at_least` (§8.6) with an identical descriptor;
    they're separate registries, so the shared name is not a collision — it's the same
    predicate on two authoring surfaces.
    """
    command_conditions.get_registry().register_spec(
        _REPUTATION_AT_LEAST_SPEC, _reputation_at_least
    )
    dialogue_conditions.get_registry().register_spec(
        _REPUTATION_AT_LEAST_SPEC, _reputation_at_least_dialogue
    )
    side_effects.get_registry().register_spec(
        _ADJUST_REPUTATION_SPEC, _handle_adjust_reputation
    )
