"""Mark award lifecycle: evaluate criteria, award once, announce (Sprint 53).

Pure content on existing primitives: criteria read the journal state already
on `Player` (`visited_rooms`, `met_npcs`, `discovered_items`, `flags`); earned
state is the `mark:<id>` player flag; evaluation rides the same queued
pre-commit events quest progression does (`PLAYER_MOVED` / `ITEM_TAKEN` /
`QUEST_COMPLETED` — flushed before the command's one commit, so award writes
land in the command's transaction). No new Tier 1 mechanism, no new table.

Dialogue-only criteria (`npcs_met`, dialogue-set `flags_set`) award on the
player's next qualifying event — in practice their next step away from the
NPC, which reads naturally in play.
"""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.models.player import Player
from lorecraft.features.marks.models import (
    MarkCriteria,
    MarkDef,
    MarkRegistry,
    earned_flag,
    get_registry,
)


class MarkService:
    def __init__(self, registry: MarkRegistry | None = None) -> None:
        self._registry = registry or get_registry()

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.PLAYER_MOVED, self._on_event)
        bus.on(GameEvent.ITEM_TAKEN, self._on_event)
        bus.on(GameEvent.QUEST_COMPLETED, self._on_event)

    def _on_event(self, event: Event, ctx: object) -> None:
        del event
        if not isinstance(ctx, GameContext):
            return
        self.evaluate(ctx)

    # ---- evaluation ------------------------------------------------------

    def evaluate(self, ctx: GameContext) -> list[MarkDef]:
        """Award every unearned mark whose criteria the player now meets.

        Runs to a fixpoint so a mark whose criteria include another mark's
        `mark:<id>` flag can be earned in the same evaluation. Idempotent —
        the earned flag guards re-awards.
        """
        awarded: list[MarkDef] = []
        progressed = True
        while progressed:
            progressed = False
            for mark in self._registry.all():
                if ctx.player.flags.get(earned_flag(mark.id)):
                    continue
                if self._met(mark.criteria, ctx.player):
                    self._award(ctx, mark)
                    awarded.append(mark)
                    progressed = True
        return awarded

    def earned(self, player: Player) -> list[MarkDef]:
        """Every registered mark this player has earned, in registry order."""
        return [
            mark
            for mark in self._registry.all()
            if player.flags.get(earned_flag(mark.id))
        ]

    def unearned_visible(self, player: Player) -> list[MarkDef]:
        """Unearned marks that may tease as "???" — hidden marks excluded."""
        return [
            mark
            for mark in self._registry.all()
            if not mark.hidden and not player.flags.get(earned_flag(mark.id))
        ]

    @staticmethod
    def _met(criteria: MarkCriteria, player: Player) -> bool:
        if criteria.rooms_visited and not set(criteria.rooms_visited) <= set(
            player.visited_rooms
        ):
            return False
        if (
            criteria.rooms_visited_count
            and len(player.visited_rooms) < criteria.rooms_visited_count
        ):
            return False
        if criteria.npcs_met and not set(criteria.npcs_met) <= set(player.met_npcs):
            return False
        if criteria.items_discovered and not set(criteria.items_discovered) <= set(
            player.discovered_items
        ):
            return False
        if criteria.flags_set and not all(
            player.flags.get(flag) for flag in criteria.flags_set
        ):
            return False
        return True

    @staticmethod
    def _award(ctx: GameContext, mark: MarkDef) -> None:
        # Reassign (not mutate) so SQLModel flags the JSON column dirty.
        flags = dict(ctx.player.flags)
        flags[earned_flag(mark.id)] = True
        ctx.player.flags = flags
        ctx.say(f"You have earned {mark.name}!", MessageType.QUEST)
        if mark.description:
            ctx.say(mark.description, MessageType.QUEST)
