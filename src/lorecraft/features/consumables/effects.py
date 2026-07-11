"""One-shot-on-consume item-effect dispatcher for eat/drink.

Distinct from `features/items/effects.py`, which compiles *continuous* equip-time
descriptors (stat_bonus/skill_bonus/...) into Modifiers. Consumable descriptors
fire *once* when the item is eaten/drunk and have no lasting item to hang a
modifier on, so they are dispatched here to Tier 1 services instead:

    {type: heal, meter: <key>, amount: <float>, message?: <str>}
        instant MeterService.adjust() on the actor's meter (generic `meter` key —
        works for `hp`, `fatigue`, or any registered meter).
    {type: apply_effect, effect_key: <str>, duration_ticks?: <float>,
     payload?: {...}, message?: <str>}
        a timed EffectService.apply() on the actor (buff potions — see buffs.py).

Reads `item.effects` generically; never branches on item ids. Unknown descriptor
types are a content-lint concern, not a runtime error — they are skipped here.
"""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.models.world import Item
from lorecraft.types import JsonObject


def apply_consumable_effects(item: Item, ctx: GameContext) -> None:
    """Apply every `heal`/`apply_effect` descriptor on `item` to the actor.

    Emits one player-facing `ctx.say(...)` per effect applied. A consumable with
    no (recognised) descriptors is silent here — the eat/drink verb still narrates
    the act itself.
    """
    clock_epoch = ctx.clock.game_epoch if ctx.clock is not None else 0.0
    for effect in item.effects:
        effect_type = effect.get("type")
        if effect_type == "heal":
            _apply_heal(effect, ctx)
        elif effect_type == "apply_effect":
            _apply_effect(effect, ctx, clock_epoch)


def _apply_heal(effect: JsonObject, ctx: GameContext) -> None:
    """Instantly adjust a meter by a positive amount (healing/restoration)."""
    meter_key = effect.get("meter")
    amount = effect.get("amount")
    if not isinstance(meter_key, str) or not isinstance(amount, (int, float)):
        return
    meter = ctx.meters.get(ctx.session, "player", ctx.player.id, meter_key)
    change = ctx.meters.adjust(ctx.session, meter, float(amount))
    restored = change.meter.current - change.previous
    message = effect.get("message")
    if isinstance(message, str) and message:
        ctx.say(message)
    elif restored > 0:
        ctx.say(f"You recover {restored:g} {meter_key}.")
    else:
        ctx.say("You feel no different.")


def _apply_effect(effect: JsonObject, ctx: GameContext, clock_epoch: float) -> None:
    """Apply a timed active effect (buff) to the actor for `duration_ticks`."""
    effect_key = effect.get("effect_key")
    if not isinstance(effect_key, str):
        return
    duration = effect.get("duration_ticks")
    duration_ticks = float(duration) if isinstance(duration, (int, float)) else None
    payload = effect.get("payload")
    ctx.effects.apply(
        ctx.session,
        "player",
        ctx.player.id,
        effect_key,
        duration_ticks=duration_ticks,
        payload=payload if isinstance(payload, dict) else None,
        clock_epoch=clock_epoch,
    )
    message = effect.get("message")
    ctx.say(
        message if isinstance(message, str) and message else "You feel it take hold."
    )
