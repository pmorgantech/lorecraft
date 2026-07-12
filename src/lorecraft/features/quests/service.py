"""Quest progression tracking.

Sprint 30.1 adds stage `branches`: an ordered list of `{conditions,
next_stage, side_effects}` dicts, evaluated (in order) once a stage's own
base `conditions` pass. The first branch whose own conditions also pass wins
-- its `side_effects` (any handler on the shared npc/side_effects.py
registry: set_flags, give_item, adjust_reputation, remember, ...) are the
"consequence" of that branch, and `next_stage` becomes the new current
stage (or, if null, completes the quest). A stage with no `branches` keeps
the original linear behavior (advance to the next stage in `stages` order)
for full backward compatibility with quests authored before this sprint.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from lorecraft.features.progression.feedback import narrate_level_up
from lorecraft.features.progression.rewards import apply_rewards
from lorecraft.features.quests import conditions as quest_conditions
from lorecraft.features.quests.repo import QuestRepo
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.message_types import MessageType
from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext
    from lorecraft.features.quests.models import PlayerQuestProgress, Quest


def _current_epoch(ctx: "GameContext") -> float:
    return ctx.clock.game_epoch if ctx.clock is not None else 0.0


def _stage_by_id(quest: "Quest", stage_id: str) -> JsonObject | None:
    return next((s for s in quest.stages if s["id"] == stage_id), None)


class QuestService:
    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.ITEM_TAKEN, self.check_progression)
        bus.on(GameEvent.PLAYER_MOVED, self.check_progression)
        bus.on(GameEvent.ITEM_DROPPED, self.check_progression)

    def check_progression(self, event: Event, ctx: object) -> None:
        del event
        from lorecraft.engine.game.context import GameContext as _GC

        if not isinstance(ctx, _GC):
            return
        quest_repo = QuestRepo(ctx.session)
        for progress in quest_repo.active_progress(ctx.player.id):
            quest = quest_repo.get(progress.quest_id)
            if quest is None:
                continue
            stage = _stage_by_id(quest, progress.current_stage_id)
            if stage is None:
                continue
            if not self._conditions_met(stage.get("conditions", []), ctx):  # type: ignore[arg-type]
                continue

            branches = stage.get("branches") or []
            if branches:
                self._advance_via_branch(quest, stage, progress, branches, ctx)  # type: ignore[arg-type]
            else:
                self._advance_linear(quest, stage, progress, ctx)

    def _advance_via_branch(
        self,
        quest: "Quest",
        stage: JsonObject,
        progress: "PlayerQuestProgress",
        branches: list[JsonObject],
        ctx: "GameContext",
    ) -> None:
        branch = next(
            (
                b
                for b in branches
                if self._conditions_met(b.get("conditions", []), ctx)  # type: ignore[arg-type]
            ),
            None,
        )
        if branch is None:
            return  # no branch's extra conditions satisfied yet -- stall here

        self._apply_completion_flags(stage, ctx)
        self._apply_side_effects(branch.get("side_effects", {}), ctx)  # type: ignore[arg-type]
        next_stage_id = branch.get("next_stage")
        if next_stage_id:
            self._enter_stage(quest, progress, str(next_stage_id), ctx)
        else:
            self._complete_quest(quest, stage, progress, ctx)

    def _advance_linear(
        self,
        quest: "Quest",
        stage: JsonObject,
        progress: "PlayerQuestProgress",
        ctx: "GameContext",
    ) -> None:
        self._apply_completion_flags(stage, ctx)
        idx = next(
            (i for i, s in enumerate(quest.stages) if s["id"] == stage["id"]), -1
        )
        if not stage.get("terminal") and idx + 1 < len(quest.stages):
            next_stage = quest.stages[idx + 1]
            self._enter_stage(quest, progress, str(next_stage["id"]), ctx)
        else:
            self._complete_quest(quest, stage, progress, ctx)

    def _enter_stage(
        self,
        quest: "Quest",
        progress: "PlayerQuestProgress",
        next_stage_id: str,
        ctx: "GameContext",
    ) -> None:
        next_stage = _stage_by_id(quest, next_stage_id)
        if next_stage is None:
            # Authoring bug safety net (a branch/next_stage referencing an
            # unknown stage id): treat as quest completion rather than
            # silently stalling forever or raising mid-command.
            self._complete_quest(quest, None, progress, ctx)
            return
        progress.current_stage_id = next_stage_id
        progress.stage_started_epoch = _current_epoch(ctx)
        ctx.session.add(progress)
        ctx.say(
            f"Quest updated: {quest.title} — {next_stage.get('description', '')}",
            MessageType.QUEST,
        )
        ctx.push_update(
            "quest_update",
            {
                "quest_id": progress.quest_id,
                "title": quest.title,
                "stage_id": next_stage_id,
                "stage_description": str(next_stage.get("description", "")),
                "status": "active",
            },
        )
        ctx.queue_event(
            GameEvent.QUEST_UPDATED,
            quest_id=progress.quest_id,
            player_id=ctx.player.id,
        )

    def _complete_quest(
        self,
        quest: "Quest",
        stage: JsonObject | None,
        progress: "PlayerQuestProgress",
        ctx: "GameContext",
    ) -> None:
        progress.status = "completed"
        progress.completed_at = time.time()
        ctx.session.add(progress)
        if stage is not None:
            self._award_rewards(stage.get("rewards") or {}, ctx)  # type: ignore[arg-type]
        ctx.say(f"Quest completed: {quest.title}!", MessageType.QUEST)
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

    def _apply_completion_flags(self, stage: JsonObject, ctx: "GameContext") -> None:
        completion_flags = stage.get("completion_flags") or {}
        for flag, value in (
            completion_flags.items() if isinstance(completion_flags, dict) else []
        ):  # type: ignore[union-attr]
            ctx.player.flags = {**ctx.player.flags, str(flag): value}

    def _apply_side_effects(self, effects: JsonObject, ctx: "GameContext") -> None:
        from lorecraft.features.npc.side_effects import get_registry

        get_registry().apply(effects, ctx)

    def _conditions_met(self, conditions: list[JsonObject], ctx: "GameContext") -> bool:
        return quest_conditions.get_registry().evaluate_all(conditions, ctx)

    def _award_rewards(self, rewards: JsonObject, ctx: "GameContext") -> None:
        """Grant a stage's rewards via the Tier 2 interpreter, then narrate.

        The interpreter owns the reward vocabulary and all balance numbers
        (items/xp/coins/skill_points, config-driven level-up payouts); this only
        turns the returned `RewardOutcome` into feed lines. Because
        `_complete_quest` calls this per completed stage, multi-stage quests
        award incrementally for free — no special-casing here.
        """
        outcome = apply_rewards(ctx, rewards)
        for item_id in outcome.items_spawned:
            item = ctx.item_repo.get(item_id)
            if item is not None:
                ctx.say(f"You receive {item.name}.")
        if outcome.coins_granted:
            ctx.say(f"You receive {outcome.coins_granted} coins.")
        if outcome.xp_granted:
            ctx.say(f"You gain {outcome.xp_granted} experience.")
        # Dedicated LEVEL feed line + PLAYER_LEVELED_UP event + Stats-pane push
        # (Sprint 73.9), shared with the discovery path so a level-up narrates
        # consistently no matter what granted the XP.
        narrate_level_up(ctx, outcome)
