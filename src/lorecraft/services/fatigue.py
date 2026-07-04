"""Fatigue drain + rest/sleep/camp commands (Sprint 27.1, wishlist.md ->
Character condition). Meter mechanics + the skill-check penalty side of this
live in game/fatigue_source.py; this module owns drain (travel/encumbrance)
and the player-facing rest/sleep/camp commands.
"""

from __future__ import annotations

from lorecraft.game import encumbrance
from lorecraft.game.context import GameContext
from lorecraft.game.events import Event, EventBus, GameEvent
from lorecraft.game.fatigue_source import FATIGUE_METER_KEY

UNBURDENED_MOVE_DRAIN = 2.0
BURDENED_MOVE_DRAIN = 4.0
OVERLOADED_MOVE_DRAIN = 7.0
_MOVE_DRAIN_BY_BAND = {
    "unburdened": UNBURDENED_MOVE_DRAIN,
    "burdened": BURDENED_MOVE_DRAIN,
    "overloaded": OVERLOADED_MOVE_DRAIN,
}

REST_RESTORE = 20.0
CAMP_RESTORE = 55.0
# Sleep restores to full outright; MeterService.adjust() clamps at maximum
# regardless of delta size. Sprint 27.2 layers clock-advance/risk/dream
# flavor on top of this same command.
SLEEP_RESTORE = 10_000.0


class FatigueService:
    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.PLAYER_MOVED, self._on_player_moved)

    def _on_player_moved(self, event: Event, ctx: object) -> None:
        from lorecraft.game.context import GameContext as _GC

        if isinstance(ctx, _GC):
            self.drain_for_travel(ctx)

    def drain_for_travel(self, ctx: GameContext) -> None:
        stats = ctx.player_repo.stats(ctx.player.id)
        strength = stats.strength if stats is not None else 10
        capacity = encumbrance.resolve_carry_capacity(
            ctx.session, ctx.player.id, strength
        )
        weight = encumbrance.total_carried_weight(ctx.session, ctx.player.id)
        band = encumbrance.encumbrance_band(weight, capacity)
        meter = ctx.meters.get(ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY)
        ctx.meters.adjust(ctx.session, meter, -_MOVE_DRAIN_BY_BAND[band])

    def rest(self, ctx: GameContext) -> None:
        self._restore(
            ctx, REST_RESTORE, "You catch your breath and feel a little less tired."
        )

    def camp(self, ctx: GameContext) -> None:
        self._restore(ctx, CAMP_RESTORE, "You make camp and rest for a while.")

    def sleep(self, ctx: GameContext) -> None:
        self._restore(
            ctx,
            SLEEP_RESTORE,
            "You fall into a deep sleep and wake feeling refreshed.",
        )

    def _restore(self, ctx: GameContext, amount: float, message: str) -> None:
        meter = ctx.meters.get(ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY)
        if meter.current >= meter.maximum:
            ctx.say("You are already well-rested.")
            return
        ctx.meters.adjust(ctx.session, meter, amount)
        ctx.say(message)
