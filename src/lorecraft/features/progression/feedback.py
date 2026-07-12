"""Tier 2 level-up feedback — turn a reward's level-up into player-facing signal.

When a reward grant (a quest turn-in, a discovery, ...) awards XP that crosses a
level threshold, the Tier 1 leveling mechanism (`engine.game.leveling`) returns a
``LevelUpResult`` but stays IO-free — it emits no message, event, or UI push, on
purpose. This module owns that presentation policy: given the ``RewardOutcome``
its caller already has in hand, it narrates the "You reach level N!" feed line
(``MessageType.LEVEL``), queues a ``PLAYER_LEVELED_UP`` event, and pushes the
fresh Score/Stats numbers so a live client's Stats pane reflects the change.

Every reward path that can level a player up (quests, exploration/discovery)
routes its outcome through here, so the three effects stay consistent and no path
silently levels a player without narrating it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.message_types import MessageType
from lorecraft.features.progression.rewards import RewardOutcome

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext

# The key a live command response reads to refresh the Score/Stats pane. Mirrors
# the "quest_update" push convention: a marker payload the frontend picks up to
# re-render the pane. The Stats-pane template rendering itself is a Frontend task.
STATS_UPDATE_KEY = "stats_update"


def narrate_level_up(ctx: GameContext, outcome: RewardOutcome) -> None:
    """Emit the feed line, event, and Stats-pane push for a leveled-up outcome.

    A no-op when the grant didn't cross a level, so every reward path can call it
    unconditionally with whatever ``RewardOutcome`` it produced.
    """
    level_up = outcome.level_up
    if level_up is None or not level_up.leveled_up:
        return

    ctx.say(f"You reach level {level_up.new_level}!", MessageType.LEVEL)
    ctx.queue_event(
        GameEvent.PLAYER_LEVELED_UP,
        player_id=ctx.player.id,
        old_level=level_up.old_level,
        new_level=level_up.new_level,
        levels_gained=level_up.levels_gained,
    )

    # Push the fresh Score numbers so a connected client's Stats pane reflects
    # the new level/xp and any skill points the level-up payout granted. Read
    # from the persisted stats row so the values already include the payout.
    stats = ctx.player_repo.stats(ctx.player.id)
    if stats is not None:
        ctx.push_update(
            STATS_UPDATE_KEY,
            {
                "level": stats.level,
                "xp": stats.xp,
                "xp_to_next": stats.xp_to_next,
                "skill_points": stats.skill_points,
            },
        )
