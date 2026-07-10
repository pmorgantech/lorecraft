"""Declarative trigger binding — reactive ``on`` / ``when`` / ``do`` hooks on world entities.

`docs/scripting_engine_design.md` §3.3 and Appendix A. A builder attaches triggers to an NPC,
room, item, or exit; when a bound event fires, the trigger's ``when`` conditions are checked and,
if they pass, its ``do`` effects run. The headline synthetic event is **`encounter`** — an NPC
and a player becoming co-located, from either direction.

Tier 1. The condition/effect *vocabulary* lives in feature registries (which the engine may not
import), so this service takes them as injected :class:`WhenEvaluator` / :class:`DoApplier`
Protocols — satisfied structurally by the dialogue-condition and side-effect registries and wired
at the composition layer. The service owns only the engine-level parts: event routing, the
one-level ``any`` / ``all`` boolean logic, and fail-closed load-time validation against the
catalog. Effect/condition *names* are validated up front (fail-closed, §8.5); at runtime an
unknown name is ignored by the registry (fail-open), consistent with the rest of the engine.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from lorecraft.engine.game.context import GameContext, build_game_context
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.world_context import StandaloneWorldContext
from lorecraft.engine.scripting.validator import validate_conditions, validate_effects
from lorecraft.engine.scripting.vocabulary import Vocabulary
from lorecraft.types import JsonObject, JsonValue

log = logging.getLogger(__name__)

# Trigger-surface event names (`on:`). Kept distinct from `GameEvent` — these are what a
# builder writes; the service maps engine events onto them (e.g. PLAYER_MOVED → both
# `player_entered` for the room and `encounter` for NPCs now sharing it).
ON_ENCOUNTER = "encounter"
ON_PLAYER_ENTERED = "player_entered"
ON_PLAYER_LEFT = "player_left"

ENTITY_ROOM = "room"
ENTITY_NPC = "npc"
ENTITY_ITEM = "item"
ENTITY_EXIT = "exit"

_BOOL_GROUPS = ("any", "all")


class WhenEvaluator(Protocol):
    """Evaluates a map of conditions against a context (AND semantics).

    The dialogue-condition registry satisfies this structurally; injected so the Tier-1 service
    doesn't import features.
    """

    def evaluate(self, conditions: JsonObject, ctx: GameContext) -> bool: ...


class DoApplier(Protocol):
    """Applies a map of effects against a context. The side-effect registry satisfies this."""

    def apply(self, effects: JsonObject, ctx: GameContext) -> None: ...


class TriggerLoadError(Exception):
    """Raised when a trigger references an unknown condition/effect name (fail-closed load)."""


@dataclass(frozen=True)
class Trigger:
    """One parsed ``on`` / ``when`` / ``do`` hook, bound to an entity."""

    on: str
    entity_type: str
    entity_id: str
    when: JsonValue = None  # None = always
    do: JsonValue = None  # None = no-op


def parse_trigger(
    entity_type: str,
    entity_id: str,
    raw: JsonObject,
    *,
    vocab: Vocabulary,
) -> Trigger:
    """Build a :class:`Trigger` from raw YAML, validating its names against the catalog.

    Fail-closed: an unknown condition or effect name (or a bad param shape) raises
    :class:`TriggerLoadError` at load time, where the mistake was authored — rather than
    silently never firing at runtime.
    """
    on = raw.get("on")
    if not isinstance(on, str) or not on:
        raise TriggerLoadError(
            f"{entity_type}:{entity_id} trigger is missing a string 'on:' event"
        )
    when = raw.get("when")
    do = raw.get("do")
    location = f"{entity_type}:{entity_id} on={on}"
    issues = [
        *(
            validate_conditions(when, vocab, location=f"{location} when")
            if when
            else []
        ),
        *(validate_effects(do, vocab, location=f"{location} do") if do else []),
    ]
    if issues:
        raise TriggerLoadError("; ".join(str(issue) for issue in issues))
    return Trigger(
        on=on, entity_type=entity_type, entity_id=entity_id, when=when, do=do
    )


class TriggerService:
    """Binds triggers to engine events and fires their effects when conditions pass."""

    def __init__(self, when: WhenEvaluator, do: DoApplier) -> None:
        self._when = when
        self._do = do
        # Indexed by trigger-surface event name, then queried/filtered by entity per event.
        self._by_on: dict[str, list[Trigger]] = {}

    def load(self, triggers: Iterable[Trigger]) -> None:
        """Replace the loaded trigger set (call once at world load)."""
        self._by_on = {}
        for trigger in triggers:
            self._by_on.setdefault(trigger.on, []).append(trigger)

    def register(self, bus: EventBus) -> None:
        """Subscribe to the engine events that map onto trigger-surface events."""
        bus.on(GameEvent.PLAYER_MOVED, self._on_player_moved)
        bus.on(GameEvent.NPC_MOVED, self._on_npc_moved)

    # -- event mapping -------------------------------------------------------

    def _on_player_moved(self, event: Event, ctx: object) -> None:
        """A player entered a room: fire the room's `player_entered` and any co-located
        NPC's `encounter` triggers, with the mover as the actor (``ctx.player``)."""
        if not isinstance(ctx, GameContext):
            return  # only player-driven moves carry an actor context (A2 scope)
        to_room = event.payload.get("to_room_id")
        if not isinstance(to_room, str):
            return
        for trigger in self._by_on.get(ON_PLAYER_ENTERED, ()):
            if trigger.entity_type == ENTITY_ROOM and trigger.entity_id == to_room:
                self._fire(trigger, ctx)
        encounter_triggers = self._by_on.get(ON_ENCOUNTER, ())
        if encounter_triggers:
            npc_ids = {npc.id for npc in ctx.npc_repo.in_room(to_room)}
            for trigger in encounter_triggers:
                if trigger.entity_type == ENTITY_NPC and trigger.entity_id in npc_ids:
                    self._fire(trigger, ctx)

    def _on_npc_moved(self, event: Event, ctx: object) -> None:
        """An NPC entered a room autonomously (A3): fire *its* `encounter` triggers for each
        player already there — the mirror of the player-walks-in case. Runs against a fresh
        `GameContext` per co-located player (built from the autonomous tick's world context), so
        the same actor-bound conditions/effects apply."""
        if not isinstance(ctx, StandaloneWorldContext):
            return  # NPC_MOVED is emitted from the actor-less agency loop
        npc_id = event.payload.get("npc_id")
        to_room = event.payload.get("to_room_id")
        if not isinstance(npc_id, str) or not isinstance(to_room, str):
            return
        triggers = [
            trigger
            for trigger in self._by_on.get(ON_ENCOUNTER, ())
            if trigger.entity_type == ENTITY_NPC and trigger.entity_id == npc_id
        ]
        if not triggers:
            return
        room = ctx.room_repo.get(to_room)
        if room is None:
            return
        for player in ctx.player_repo.in_room(to_room):
            game_ctx = build_game_context(
                ctx.session,
                player,
                room,
                bus=ctx.bus,
                manager=ctx.manager,
                transaction=ctx.transaction,
                session_id=ctx.session_id,
                rng=ctx.rng,
                meters=ctx.meters,
                effects=ctx.effects,
                clock=ctx.clock,
            )
            for trigger in triggers:
                self._fire(trigger, game_ctx)

    # -- firing --------------------------------------------------------------

    def _fire(self, trigger: Trigger, ctx: GameContext) -> None:
        try:
            if self._when_passes(trigger.when, ctx):
                self._apply_do(trigger.do, ctx)
        except Exception:
            # A buggy trigger must never break the command that fired it — but leave a trace.
            log.exception(
                "trigger_failed on=%s entity=%s:%s",
                trigger.on,
                trigger.entity_type,
                trigger.entity_id,
            )

    def _when_passes(
        self, block: JsonValue, ctx: GameContext, *, depth: int = 0
    ) -> bool:
        """AND across keys; one level of ``any`` (OR) / ``all`` (AND) groups."""
        if not block:
            return True
        if not isinstance(block, dict):
            return False
        leaf: JsonObject = {}
        for key, value in block.items():
            if key in _BOOL_GROUPS:
                members = value if isinstance(value, list) else []
                results = [
                    self._when_passes(member, ctx, depth=depth + 1)
                    for member in members
                ]
                group_ok = any(results) if key == "any" else all(results)
                if not group_ok:
                    return False
            else:
                leaf[key] = value
        if leaf and not self._when.evaluate(leaf, ctx):
            return False
        return True

    def _apply_do(self, block: JsonValue, ctx: GameContext) -> None:
        """Run a ``do`` block: a map (unordered) or an ordered list of single-key maps."""
        if not block:
            return
        if isinstance(block, dict):
            self._do.apply(block, ctx)
            return
        if isinstance(block, list):
            for item in block:
                if isinstance(item, dict):
                    self._do.apply(item, ctx)
