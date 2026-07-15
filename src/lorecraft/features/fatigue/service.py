"""Fatigue drain + rest/sleep/camp commands (Sprint 27.1-27.2, wishlist.md ->
Character condition). Meter mechanics + the skill-check penalty side of this
live in game/fatigue_source.py; this module owns drain (travel/encumbrance),
the player-facing rest/sleep/camp commands, and sleep's pause/recovery,
safe-vs-unsafe risk, warmth/exposure, and dream flavor.
"""

from __future__ import annotations

from lorecraft.features.weather.handlers import COLD_WEATHERS
from sqlmodel import Session, select

from lorecraft.engine.clock.world_clock import SECONDS_PER_HOUR
from lorecraft.features.encumbrance import rules as encumbrance
from lorecraft.engine.game.checks import skill_check
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.player_activity import (
    clear_expired_sleep,
    is_resting,
    is_sleeping,
    set_resting,
    set_sleeping_until,
)
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.meters import Meter
from lorecraft.engine.models.world import Room, WorldClock
from lorecraft.features.fatigue.source import FATIGUE_METER_KEY
from lorecraft.engine.game.modifiers import get_registry as get_modifier_registry
from lorecraft.features.warmth.rules import resolve_warmth
from lorecraft.features.disciplines.service import ProficiencyService

UNBURDENED_MOVE_DRAIN = 2.0
BURDENED_MOVE_DRAIN = 4.0
OVERLOADED_MOVE_DRAIN = 7.0
_MOVE_DRAIN_BY_BAND = {
    "unburdened": UNBURDENED_MOVE_DRAIN,
    "burdened": BURDENED_MOVE_DRAIN,
    "overloaded": OVERLOADED_MOVE_DRAIN,
}

REST_RECOVERY_PER_HOUR = 6.0
SLEEP_RECOVERY_PER_HOUR = 14.0
HP_RECOVERY_PER_HOUR = 2.0
HP_REST_RECOVERY_PER_HOUR = 8.0
HP_SLEEP_RECOVERY_PER_HOUR = 20.0
CAMP_RESTORE = 55.0
CAMP_HP_RESTORE = 20.0
INTERRUPTED_SLEEP_HOURS = 3.0
MAX_SLEEP_HOURS = 12.0

_TERRAIN_MOVE_COST = {
    "normal": 2.0,
    "road": 1.0,
    "forest": 3.0,
    "mountain": 5.0,
    "swamp": 5.0,
    "water": 6.0,
}
_WEATHER_MOVE_COST = {
    "light_rain": 1.0,
    "heavy_rain": 2.0,
    "fog": 1.0,
    "snow": 2.0,
    "blizzard": 4.0,
    "thunderstorm": 3.0,
    "hot": 1.0,
}
_ENCUMBRANCE_MOVE_COST = {"unburdened": 0.0, "burdened": 2.0, "overloaded": 5.0}
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
    def __init__(self, proficiency: ProficiencyService | None = None) -> None:
        self.proficiency = proficiency or ProficiencyService()

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.TIME_ADVANCED, self._on_time_advanced)

    def movement_cost(self, ctx: GameContext, target_room: Room) -> float:
        terrain_cost = _TERRAIN_MOVE_COST.get(
            target_room.terrain, _TERRAIN_MOVE_COST["normal"]
        )
        weather = ctx.clock.weather if ctx.clock is not None else "clear"
        weather_cost = (
            0.0 if target_room.indoor else _WEATHER_MOVE_COST.get(weather, 0.0)
        )
        return terrain_cost + weather_cost + self._encumbrance_move_cost(ctx)

    def consume_for_travel(self, ctx: GameContext, target_room: Room) -> bool:
        meter = ctx.meters.get(ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY)
        cost = self.movement_cost(ctx, target_room)
        if meter.current < cost:
            ctx.say(
                f"You need {cost:g} movement points to travel there, "
                f"but only have {meter.current:g}.",
                MessageType.WARNING,
            )
            return False
        ctx.meters.adjust(ctx.session, meter, -cost)
        return True

    def drain_for_travel(self, ctx: GameContext) -> None:
        meter = ctx.meters.get(ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY)
        ctx.meters.adjust(
            ctx.session, meter, -_MOVE_DRAIN_BY_BAND[self._encumbrance_band(ctx)]
        )

    def _encumbrance_move_cost(self, ctx: GameContext) -> float:
        return _ENCUMBRANCE_MOVE_COST[self._encumbrance_band(ctx)]

    def _encumbrance_band(self, ctx: GameContext) -> str:
        stats = ctx.player_repo.stats(ctx.player.id)
        strength = stats.strength if stats is not None else 10
        capacity = encumbrance.resolve_carry_capacity(
            ctx.session, ctx.player.id, strength
        )
        weight = encumbrance.total_carried_weight(ctx.session, ctx.player.id)
        return encumbrance.encumbrance_band(weight, capacity)

    def rest(self, ctx: GameContext) -> None:
        set_resting(ctx.player, True)
        ctx.say("You settle into a steady rest. Stand when you're ready to move again.")

    def stand(self, ctx: GameContext) -> None:
        if is_resting(ctx.player):
            set_resting(ctx.player, False)
            ctx.say("You stand up and ready yourself to move.")
            return
        ctx.say("You are already standing.")

    def camp(self, ctx: GameContext) -> None:
        self._restore(ctx, CAMP_RESTORE, "You make camp and rest for a while.")

    def _restore(self, ctx: GameContext, amount: float, message: str) -> None:
        meter = ctx.meters.get(ctx.session, "player", ctx.player.id, FATIGUE_METER_KEY)
        hp = ctx.meters.get(ctx.session, "player", ctx.player.id, "hp")
        if meter.current >= meter.maximum and hp.current >= hp.maximum:
            ctx.say("You are already well-rested.")
            return
        ctx.meters.adjust(ctx.session, meter, amount)
        if hp.current > 0:
            ctx.meters.adjust(ctx.session, hp, CAMP_HP_RESTORE)
        ctx.say(message)

    def sleep(self, ctx: GameContext, hours: float | None = None) -> None:
        """Sleep pauses the player until world time reaches the chosen wake time.

        Recovery happens from TIME_ADVANCED ticks. Safe rooms grant predictable
        sleep; exposed rooms still make the survival check and may shorten the
        planned sleep before the player becomes available again.
        """
        if ctx.clock is None:
            ctx.say("Time doesn't seem to be passing here.", MessageType.WARNING)
            return
        if hours is None:
            ctx.say("Sleep for how many hours? Try `sleep 8`.", MessageType.WARNING)
            return
        if hours <= 0 or hours > MAX_SLEEP_HOURS:
            ctx.say(
                f"Choose a sleep duration from 1 to {MAX_SLEEP_HOURS:g} hours.",
                MessageType.WARNING,
            )
            return
        planned_hours = hours
        if ctx.room.safe_rest:
            set_sleeping_until(
                ctx.player, ctx.clock.game_epoch + planned_hours * SECONDS_PER_HOUR
            )
            ctx.say(f"You settle in to sleep for {planned_hours:g} hours.")
            self._dream(ctx)
            return

        # Weathering an unsafe sleep is a Survival check (§7).
        base = self.proficiency.get_rank(ctx.session, ctx.player.id, "survival")
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
        # Materialize the PlayerStats row (get-or-create) before record_use,
        # which hard-raises on a missing row.
        ctx.player_repo.stats(ctx.player.id)
        self.proficiency.record_use(ctx.session, ctx.rng, ctx.player.id, "survival")

        if result.success:
            set_sleeping_until(
                ctx.player, ctx.clock.game_epoch + planned_hours * SECONDS_PER_HOUR
            )
            ctx.say(
                f"You bed down as best you can and sleep for {planned_hours:g} hours."
            )
            self._dream(ctx)
        else:
            interrupted_hours = min(planned_hours, INTERRUPTED_SLEEP_HOURS)
            set_sleeping_until(
                ctx.player, ctx.clock.game_epoch + interrupted_hours * SECONDS_PER_HOUR
            )
            ctx.say(
                "Your sleep out here is fitful and exposed; you expect to wake early."
            )

    def _on_time_advanced(self, event: Event, ctx: object) -> None:
        from lorecraft.engine.clock.world_clock import ClockEventContext

        if not isinstance(ctx, ClockEventContext):
            return
        previous = event.payload.get("previous_epoch")
        current = event.payload.get("current_epoch")
        if not isinstance(previous, int | float) or not isinstance(
            current, int | float
        ):
            return
        delta_hours = max(0.0, (float(current) - float(previous)) / SECONDS_PER_HOUR)
        if delta_hours <= 0:
            return
        with Session(ctx.game_engine) as session:
            clock = session.get(WorldClock, 1)
            players = session.exec(select(Player)).all()
            for player in players:
                sleeping = is_sleeping(player, clock)
                resting = is_resting(player)
                if not sleeping and not resting:
                    clear_expired_sleep(player, clock)
                    self._recover_hp(session, player.id, ctx.game_engine, delta_hours)
                    continue
                meter = self._meter_for(session, player.id, ctx.game_engine)
                rate = SLEEP_RECOVERY_PER_HOUR if sleeping else REST_RECOVERY_PER_HOUR
                self._adjust_meter(session, meter, rate * delta_hours)
                self._recover_hp(
                    session,
                    player.id,
                    ctx.game_engine,
                    delta_hours,
                    sleeping=sleeping,
                    resting=resting,
                )
                clear_expired_sleep(player, clock)
                session.add(player)
            session.commit()

    def _meter_for(
        self, session: Session, player_id: str, game_engine: object
    ) -> Meter:
        from sqlalchemy.engine import Engine

        from lorecraft.engine.game.rng import GameRng
        from lorecraft.engine.services.meters import MeterService

        assert isinstance(game_engine, Engine)
        return MeterService(game_engine, GameRng()).get(
            session, "player", player_id, FATIGUE_METER_KEY
        )

    def _hp_meter_for(
        self, session: Session, player_id: str, game_engine: object
    ) -> Meter:
        from sqlalchemy.engine import Engine

        from lorecraft.engine.game.rng import GameRng
        from lorecraft.engine.services.meters import MeterService

        assert isinstance(game_engine, Engine)
        return MeterService(game_engine, GameRng()).get(
            session, "player", player_id, "hp"
        )

    def _recover_hp(
        self,
        session: Session,
        player_id: str,
        game_engine: object,
        delta_hours: float,
        *,
        sleeping: bool = False,
        resting: bool = False,
    ) -> None:
        hp = self._hp_meter_for(session, player_id, game_engine)
        if hp.current <= 0 or hp.current >= hp.maximum:
            return
        if sleeping:
            rate = HP_SLEEP_RECOVERY_PER_HOUR
        elif resting:
            rate = HP_REST_RECOVERY_PER_HOUR
        else:
            rate = HP_RECOVERY_PER_HOUR
        self._adjust_meter(session, hp, rate * delta_hours)

    def _adjust_meter(self, session: Session, meter: Meter, amount: float) -> None:
        meter.current = max(0.0, min(meter.maximum, meter.current + amount))
        session.add(meter)

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
