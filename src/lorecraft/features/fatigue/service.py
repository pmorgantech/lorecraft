"""Fatigue drain + rest/sleep/camp commands (Sprint 27.1-27.2, wishlist.md ->
Character condition). Meter mechanics + the skill-check penalty side of this
live in game/fatigue_source.py; this module owns drain (travel/encumbrance),
the player-facing rest/sleep/camp commands, and sleep's clock-advance,
safe-vs-unsafe risk, warmth/exposure, and dream flavor.
"""

from __future__ import annotations

from lorecraft.features.weather.handlers import COLD_WEATHERS, apply_daily_weather
from lorecraft.engine.clock.world_clock import SECONDS_PER_HOUR, apply_clock_fields
from lorecraft.features.encumbrance import rules as encumbrance
from lorecraft.engine.game.checks import skill_check
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.features.fatigue.source import FATIGUE_METER_KEY
from lorecraft.engine.game.modifiers import get_registry as get_modifier_registry
from lorecraft.features.warmth.rules import resolve_warmth
from lorecraft.features.skills.service import SkillService

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
# MeterService.adjust() clamps at maximum regardless of delta size.
SLEEP_RESTORE = 10_000.0

SAFE_SLEEP_HOURS = 8.0
INTERRUPTED_SLEEP_HOURS = 3.0
# Unsafe (wilderness) sleep is a survival skill_check; cold weather without
# enough warmth (game/warmth.py, worn clothing) makes it harder.
UNSAFE_SLEEP_BASE_DIFFICULTY = 10
COLD_EXPOSURE_PENALTY = 20.0

DREAM_MESSAGES = [
    "You dream of a road not yet walked.",
    "You dream of distant bells and a voice you almost remember.",
    "You dream of standing at the edge of a great, dark water.",
    "You dream of a door that wasn't there yesterday.",
]


class FatigueService:
    def __init__(self, skills: SkillService | None = None) -> None:
        self.skills = skills or SkillService()

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.PLAYER_MOVED, self._on_player_moved)

    def _on_player_moved(self, event: Event, ctx: object) -> None:
        from lorecraft.engine.game.context import GameContext as _GC

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

    def _restore(self, ctx: GameContext, amount: float, message: str) -> None:
        meter = ctx.meters.get(ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY)
        if meter.current >= meter.maximum:
            ctx.say("You are already well-rested.")
            return
        ctx.meters.adjust(ctx.session, meter, amount)
        ctx.say(message)

    def sleep(self, ctx: GameContext) -> None:
        """Sleep is reliable in a `Room.safe_rest` room (inn/camp): full
        restore, advances the clock, dream flavor. Anywhere else it's a
        survival skill_check gamble -- cold weather without enough warmth
        (equipped clothing) makes it harder; failure interrupts the sleep
        for a partial, dreamless rest."""
        if ctx.room.safe_rest:
            ctx.say("You settle in and drift off to sleep.")
            self._advance_clock(ctx, SAFE_SLEEP_HOURS)
            self._grant_full_rest(ctx)
            self._dream(ctx)
            return

        base = self.skills.get_level(ctx.session, ctx.player.id, "survival")
        modifiers = get_modifier_registry().collect(
            ctx.session, "player", ctx.player.id
        )
        warmth = resolve_warmth(ctx.session, ctx.player.id)
        is_cold = ctx.clock is not None and ctx.clock.weather in COLD_WEATHERS
        cold_penalty = max(0.0, COLD_EXPOSURE_PENALTY - warmth) if is_cold else 0.0
        difficulty = round(UNSAFE_SLEEP_BASE_DIFFICULTY + cold_penalty)
        result = skill_check(
            ctx.rng,
            base=base,
            difficulty=difficulty,
            modifiers=modifiers,
            key="skill.survival",
        )
        if ctx.player_repo.stats(ctx.player.id) is not None:
            self.skills.record_use(ctx.session, ctx.rng, ctx.player.id, "survival")

        if result.success:
            ctx.say("You bed down as best you can and manage a full night's rest.")
            self._advance_clock(ctx, SAFE_SLEEP_HOURS)
            self._grant_full_rest(ctx)
            self._dream(ctx)
        else:
            ctx.say(
                "Your sleep out here is fitful and interrupted; you wake still tired."
            )
            self._advance_clock(ctx, INTERRUPTED_SLEEP_HOURS)
            meter = ctx.meters.get(
                ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY
            )
            ctx.meters.adjust(ctx.session, meter, REST_RESTORE)

    def _grant_full_rest(self, ctx: GameContext) -> None:
        meter = ctx.meters.get(ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY)
        if meter.current < meter.maximum:
            ctx.meters.adjust(ctx.session, meter, SLEEP_RESTORE)

    def _advance_clock(self, ctx: GameContext, hours: float) -> None:
        clock = ctx.clock
        if clock is None:
            return
        previous_day = clock.current_day
        clock.game_epoch += hours * SECONDS_PER_HOUR
        apply_clock_fields(clock)
        ctx.session.add(clock)
        if clock.current_day != previous_day:
            apply_daily_weather(clock, ctx.rng.choice)

    def _dream(self, ctx: GameContext) -> None:
        lore_flags = sorted(
            flag
            for flag, value in ctx.player.flags.items()
            if flag.startswith("lore:") and value
        )
        if lore_flags:
            topic = ctx.rng.choice(lore_flags).removeprefix("lore:").replace("_", " ")
            ctx.say(f"You dream of half-remembered fragments about {topic}.")
            return
        ctx.say(ctx.rng.choice(DREAM_MESSAGES))
