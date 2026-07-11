"""Player-facing quest inspection: the `quests` command.

Lists the player's quests with per-quest status and, for a multi-stage quest, which stage it's
on (`stage N/M`) plus that stage's objective. Read-only — quest *progression* is driven by the
event bus (`QuestService.check_progression`), never by this command.
"""

from __future__ import annotations

from sqlmodel import select

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.features.quests.models import PlayerQuestProgress, Quest

_STATUS_ORDER = {"active": 0, "completed": 1, "failed": 2}


def _format_quest_line(quest: Quest | None, progress: PlayerQuestProgress) -> str:
    title = quest.title if quest is not None else progress.quest_id
    if progress.status == "completed":
        return f"  ✓ {title} — completed"
    if progress.status == "failed":
        return f"  ✗ {title} — failed"

    stages = quest.stages if quest is not None else []
    total = len(stages)
    idx = next(
        (i for i, s in enumerate(stages) if s.get("id") == progress.current_stage_id),
        None,
    )
    if idx is None or total == 0:
        return f"  • {title} — active"
    objective = str(stages[idx].get("description", "")).strip()
    position = f"stage {idx + 1}/{total}" if total > 1 else "in progress"
    return (
        f"  • {title} — {position}: {objective}"
        if objective
        else f"  • {title} — {position}"
    )


def register_quest_commands(registry: CommandRegistry) -> None:
    @registry.register(
        "quests",
        "quest",
        help="quests — list your quests and their progress",
    )
    def quests_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        rows = ctx.session.exec(
            select(PlayerQuestProgress).where(
                PlayerQuestProgress.player_id == ctx.player.id
            )
        ).all()
        if not rows:
            ctx.say("You have no quests yet.", MessageType.QUEST)
            return
        ctx.say("Your quests:", MessageType.QUEST)
        for progress in sorted(rows, key=lambda p: _STATUS_ORDER.get(p.status, 3)):
            quest = ctx.session.get(Quest, progress.quest_id)
            ctx.say(_format_quest_line(quest, progress), MessageType.QUEST)
