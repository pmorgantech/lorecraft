"""Dialogue side effect registry: pluggable handlers for quest/item/flag effects.

See docs/feature-registration.md for the complete feature registration pattern,
which shows how to plug new side effects (combat.start_combat, etc.) without
modifying dialogue.py.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from lorecraft.game.events import GameEvent
from lorecraft.models.quest import PlayerQuestProgress
from lorecraft.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext

SideEffectHandler = Callable[[JsonValue, "GameContext"], None]


class SideEffectRegistry:
    """Registry of dialogue side effect handlers.

    Built-in handlers (set_flags, clear_flags, give_item, start_quest,
    end_dialogue) are registered at module load. New effects can be
    registered by calling register() without touching dialogue.py.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, SideEffectHandler] = {}

    def register(self, effect_name: str, handler: SideEffectHandler) -> None:
        """Register a side effect handler by name."""
        self._handlers[effect_name] = handler

    def apply(self, effects: JsonObject, ctx: GameContext) -> None:
        """Apply all side effects from the given dict using registered handlers."""
        if not effects:
            return
        for effect_name, effect_data in effects.items():
            if effect_name in self._handlers:
                handler = self._handlers[effect_name]
                handler(effect_data, ctx)  # type: ignore[arg-type]

    def __contains__(self, effect_name: str) -> bool:
        return effect_name in self._handlers


_registry = SideEffectRegistry()


def _handle_set_flags(data: JsonValue, ctx: "GameContext") -> None:  # type: ignore[misc]
    for flag in data:  # type: ignore[union-attr]
        ctx.player.flags = {**ctx.player.flags, str(flag): True}


def _handle_clear_flags(data: JsonValue, ctx: "GameContext") -> None:  # type: ignore[misc]
    for flag in data:  # type: ignore[union-attr]
        flags = {**ctx.player.flags}
        flags.pop(str(flag), None)
        ctx.player.flags = flags


def _handle_give_item(data: JsonValue, ctx: "GameContext") -> None:  # type: ignore[misc]
    item_id = str(data)
    item = ctx.item_repo.get(item_id)
    if item and item_id not in ctx.player.inventory:
        ctx.player.inventory = [*ctx.player.inventory, item_id]
        ctx.say(f"You receive {item.name}.")
        ctx.push_update("inventory", list(ctx.player.inventory))


def _handle_start_quest(data: JsonValue, ctx: "GameContext") -> None:  # type: ignore[misc]
    if ctx.quest_repo is None:
        return
    quest_id = str(data)
    quest = ctx.quest_repo.get(quest_id)
    if quest is None or not quest.stages:
        return
    if ctx.quest_repo.player_progress(ctx.player.id, quest_id) is not None:
        return
    first_stage = quest.stages[0]
    ctx.quest_repo.add_progress(
        PlayerQuestProgress(
            player_id=ctx.player.id,
            quest_id=quest_id,
            current_stage_id=str(first_stage["id"]),
            status="active",
            started_at=time.time(),
        )
    )
    ctx.say(f"Quest started: {quest.title}.")
    ctx.push_update(
        "quest_update",
        {
            "quest_id": quest_id,
            "title": quest.title,
            "stage_id": str(first_stage["id"]),
            "stage_description": str(first_stage.get("description", "")),
            "status": "active",
        },
    )
    ctx.queue_event(GameEvent.QUEST_UPDATED, quest_id=quest_id, player_id=ctx.player.id)


def _handle_end_dialogue(data: JsonValue, ctx: "GameContext") -> None:  # type: ignore[misc]
    del data
    from lorecraft.npc.dialogue import _NPC_KEY, _NODE_KEY

    flags = {**ctx.player.flags}
    flags.pop(_NPC_KEY, None)
    flags.pop(_NODE_KEY, None)
    ctx.player.flags = flags
    ctx.push_update("dialogue", None)


_registry.register("set_flags", _handle_set_flags)
_registry.register("clear_flags", _handle_clear_flags)
_registry.register("give_item", _handle_give_item)
_registry.register("start_quest", _handle_start_quest)
_registry.register("end_dialogue", _handle_end_dialogue)


def get_registry() -> SideEffectRegistry:
    """Get the global side effect registry."""
    return _registry
