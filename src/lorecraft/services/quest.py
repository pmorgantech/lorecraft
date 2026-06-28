"""Quest progression tracking."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from lorecraft.game.events import Event, GameEvent
from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext


class QuestService:
    def check_progression(self, event: Event, ctx: object) -> None:
        from lorecraft.game.context import GameContext as _GC

        if not isinstance(ctx, _GC) or ctx.quest_repo is None:
            return
        for progress in ctx.quest_repo.active_progress(ctx.player.id):
            quest = ctx.quest_repo.get(progress.quest_id)
            if quest is None:
                continue
            stage: JsonObject | None = next(
                (s for s in quest.stages if s["id"] == progress.current_stage_id),
                None,
            )
            if stage is None:
                continue
            if not self._conditions_met(stage.get("conditions", []), ctx):  # type: ignore[arg-type]
                continue
            completion_flags = stage.get("completion_flags") or {}
            for flag, value in (
                completion_flags.items() if isinstance(completion_flags, dict) else []
            ):  # type: ignore[union-attr]
                ctx.player.flags = {**ctx.player.flags, str(flag): value}
            idx = next(
                (
                    i
                    for i, s in enumerate(quest.stages)
                    if s["id"] == progress.current_stage_id
                ),
                -1,
            )
            if idx + 1 < len(quest.stages):
                next_stage = quest.stages[idx + 1]
                progress.current_stage_id = str(next_stage["id"])
                ctx.quest_repo.session.add(progress)
                ctx.say(
                    f"Quest updated: {quest.title} — {next_stage.get('description', '')}"
                )
                ctx.push_update(
                    "quest_update",
                    {
                        "quest_id": progress.quest_id,
                        "title": quest.title,
                        "stage_id": str(next_stage["id"]),
                        "stage_description": str(next_stage.get("description", "")),
                        "status": "active",
                    },
                )
                ctx.queue_event(
                    GameEvent.QUEST_UPDATED,
                    quest_id=progress.quest_id,
                    player_id=ctx.player.id,
                )
            else:
                progress.status = "completed"
                progress.completed_at = time.time()
                ctx.quest_repo.session.add(progress)
                self._award_rewards(stage.get("rewards") or {}, ctx)  # type: ignore[arg-type]
                ctx.say(f"Quest completed: {quest.title}!")
                ctx.push_update(
                    "quest_update",
                    {
                        "quest_id": progress.quest_id,
                        "title": quest.title,
                        "status": "completed",
                    },
                )
                ctx.queue_event(
                    GameEvent.QUEST_COMPLETED,
                    quest_id=progress.quest_id,
                    player_id=ctx.player.id,
                )

    def _conditions_met(self, conditions: list[JsonObject], ctx: GameContext) -> bool:
        for cond in conditions:
            ctype = str(cond.get("type", ""))
            if ctype == "flag_set" and not ctx.player.flags.get(str(cond["flag"])):
                return False
            if ctype == "flag_clear" and ctx.player.flags.get(str(cond["flag"])):
                return False
            if (
                ctype == "room_visited"
                and str(cond["room_id"]) not in ctx.player.visited_rooms
            ):
                return False
            if (
                ctype == "item_in_inventory"
                and str(cond["item_id"]) not in ctx.player.inventory
            ):
                return False
        return True

    def _award_rewards(self, rewards: JsonObject, ctx: GameContext) -> None:
        for item_id in rewards.get("items") or []:  # type: ignore[union-attr]
            item = ctx.item_repo.get(str(item_id))
            if item and str(item_id) not in ctx.player.inventory:
                ctx.player.inventory = [*ctx.player.inventory, str(item_id)]
                ctx.say(f"You receive {item.name}.")
        xp = rewards.get("xp")
        if xp:
            ctx.say(f"You gain {xp} experience.")
