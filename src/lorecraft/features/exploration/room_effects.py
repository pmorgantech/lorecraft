"""Timed room effects content — the `passage_open` gate (engine_core.md §3.9).

The first content example of the Sprint 39 timed-room-effect primitive: a room
`EffectDef` whose `on_apply` opens an exit (writing the authoritative `Exit`
state and stashing the prior state in its payload) and whose `on_expire`
restores it. Because the engine's expiry sweep drives `on_expire`, a gate
"opened for N ticks" re-closes itself with no extra scheduler and no movement
changes — movement keeps reading the one `Exit` state.

A `mechanism_side_effects` handler (`open_timed_passage`) lets a Sprint 30
plate/lever trigger it purely from world YAML, e.g.::

    mechanism_side_effects:
      activated: {open_timed_passage: {direction: north, ticks: 30}}
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.engine.game.effects import EffectDef
from lorecraft.engine.game.effects import get_registry as get_effect_registry
from lorecraft.engine.models.meters import ActiveEffect
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.features.npc.side_effects import get_registry as get_side_effect_registry
from lorecraft.types import JsonValue

if TYPE_CHECKING:
    from sqlmodel import Session

    from lorecraft.engine.game.context import GameContext

PASSAGE_OPEN_KEY = "passage_open"


def _on_apply(session: Session, effect: ActiveEffect) -> None:
    """Open the exit named in `payload["direction"]`, stashing its prior locked
    state so `on_expire` restores exactly that (a normally-open exit is left
    open; a normally-locked one is re-locked)."""
    direction = str(effect.payload.get("direction", ""))
    exit_ = RoomRepo(session).exit(effect.entity_id, direction)
    if exit_ is None:
        return
    effect.payload = {**effect.payload, "prior_locked": exit_.locked}
    exit_.locked = False
    session.add(exit_)
    session.add(effect)


def _on_expire(session: Session, effect: ActiveEffect) -> None:
    """Restore the exit's locked state to what it was before this effect."""
    direction = str(effect.payload.get("direction", ""))
    exit_ = RoomRepo(session).exit(effect.entity_id, direction)
    if exit_ is None:
        return
    exit_.locked = bool(effect.payload.get("prior_locked", True))
    session.add(exit_)


def _handle_open_timed_passage(data: JsonValue, ctx: GameContext) -> None:  # type: ignore[misc]
    """`mechanism_side_effects` handler: apply a `passage_open` room effect to
    the actor's current room. `data` is `{"direction": <dir>, "ticks": <n>}`."""
    if not isinstance(data, dict):
        return
    direction = str(data.get("direction", ""))
    ticks = float(data.get("ticks", 0) or 0)  # type: ignore[arg-type]
    if not direction or ticks <= 0:
        return
    clock_epoch = ctx.clock.game_epoch if ctx.clock is not None else 0.0
    ctx.effects.apply(
        ctx.session,
        "room",
        ctx.room.id,
        PASSAGE_OPEN_KEY,
        duration_ticks=ticks,
        payload={"direction": direction},
        clock_epoch=clock_epoch,
    )
    ctx.say(f"A mechanism grinds — the way {direction} opens.")


def register() -> None:
    """Register the `passage_open` EffectDef and its mechanism side effect.

    Idempotent: the feature's `register_fn` can run more than once (app
    lifespan re-entry in tests), so re-registration is skipped.
    """
    effect_registry = get_effect_registry()
    if PASSAGE_OPEN_KEY not in effect_registry:
        effect_registry.register(
            EffectDef(
                key=PASSAGE_OPEN_KEY,
                modifiers=lambda effect: [],
                on_apply=_on_apply,
                on_expire=_on_expire,
            )
        )
    side_effects = get_side_effect_registry()
    if "open_timed_passage" not in side_effects:
        side_effects.register("open_timed_passage", _handle_open_timed_passage)
