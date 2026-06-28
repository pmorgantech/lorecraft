"""Dialogue tree walker."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from lorecraft.game.events import GameEvent
from lorecraft.models.quest import PlayerQuestProgress
from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext

_NPC_KEY = "_dialogue_npc_id"
_NODE_KEY = "_dialogue_node_id"


class DialogueService:
    def start(self, npc_id: str, ctx: GameContext) -> None:
        npc = ctx.npc_repo.get(npc_id)
        if npc is None:
            ctx.say("That person isn't here.")
            return
        if not npc.dialogue_tree_id or ctx.dialogue_repo is None:
            ctx.say(f"{npc.name} has nothing to say.")
            return
        tree_record = ctx.dialogue_repo.get(npc.dialogue_tree_id)
        if tree_record is None:
            ctx.say(f"{npc.name} has nothing to say.")
            return
        tree = tree_record.tree_data
        root = str(tree.get("root_node", "root"))
        ctx.player.flags = {**ctx.player.flags, _NPC_KEY: npc_id, _NODE_KEY: root}
        self._show_node(tree, root, npc.name, ctx)

    def choose(self, index: int, ctx: GameContext) -> None:
        npc_id = ctx.player.flags.get(_NPC_KEY)
        node_id = ctx.player.flags.get(_NODE_KEY)
        if not npc_id or not node_id:
            ctx.say("You are not in a conversation.")
            return
        npc = ctx.npc_repo.get(str(npc_id))
        if npc is None or ctx.dialogue_repo is None:
            self._end(ctx)
            return
        tree_record = ctx.dialogue_repo.get(npc.dialogue_tree_id)
        if tree_record is None:
            self._end(ctx)
            return
        tree = tree_record.tree_data
        nodes: JsonObject = tree.get("nodes", {})  # type: ignore[assignment]
        node: JsonObject = nodes.get(str(node_id), {})  # type: ignore[assignment]
        visible = _visible_choices(node, ctx)
        if index < 1 or index > len(visible):
            ctx.say(f"Choose between 1 and {len(visible)}.")
            return
        choice = visible[index - 1]
        _apply_side_effects(choice.get("side_effects", {}), ctx)  # type: ignore[arg-type]
        next_node = choice.get("next_node")
        if next_node:
            ctx.player.flags = {**ctx.player.flags, _NODE_KEY: str(next_node)}
            self._show_node(tree, str(next_node), npc.name, ctx)
        else:
            self._end(ctx)

    def end(self, ctx: GameContext) -> None:
        self._end(ctx)

    def _end(self, ctx: GameContext) -> None:
        flags = {**ctx.player.flags}
        flags.pop(_NPC_KEY, None)
        flags.pop(_NODE_KEY, None)
        ctx.player.flags = flags
        ctx.push_update("dialogue", None)

    def _show_node(
        self, tree: JsonObject, node_id: str, npc_name: str, ctx: GameContext
    ) -> None:
        nodes: JsonObject = tree.get("nodes", {})  # type: ignore[assignment]
        node: JsonObject = nodes.get(node_id, {})  # type: ignore[assignment]
        if not node:
            self._end(ctx)
            return
        text = str(node.get("text", ""))
        ctx.say(f"{npc_name}: {text}")
        _apply_side_effects(node.get("side_effects", {}), ctx)  # type: ignore[arg-type]
        visible = _visible_choices(node, ctx)
        if not visible:
            self._end(ctx)
            return
        ctx.push_update(
            "dialogue",
            {
                "npc_name": npc_name,
                "node_text": text,
                "choices": [
                    {"index": i + 1, "label": str(c.get("label", ""))}
                    for i, c in enumerate(visible)
                ],
            },
        )


def _visible_choices(node: JsonObject, ctx: GameContext) -> list[JsonObject]:
    choices = node.get("choices", [])
    visible: list[JsonObject] = []
    for choice in choices:  # type: ignore[union-attr]
        required = choice.get("required_flags", [])
        forbidden = choice.get("forbidden_flags", [])
        if all(ctx.player.flags.get(str(f)) for f in required):
            if not any(ctx.player.flags.get(str(f)) for f in forbidden):
                visible.append(choice)  # type: ignore[arg-type]
    return visible


def _apply_side_effects(effects: JsonObject, ctx: GameContext) -> None:
    if not effects:
        return
    for flag in effects.get("set_flags", []):  # type: ignore[union-attr]
        ctx.player.flags = {**ctx.player.flags, str(flag): True}
    for flag in effects.get("clear_flags", []):  # type: ignore[union-attr]
        flags = {**ctx.player.flags}
        flags.pop(str(flag), None)
        ctx.player.flags = flags
    give_item = effects.get("give_item")
    if give_item:
        item_id = str(give_item)
        item = ctx.item_repo.get(item_id)
        if item and item_id not in ctx.player.inventory:
            ctx.player.inventory = [*ctx.player.inventory, item_id]
            ctx.say(f"You receive {item.name}.")
            ctx.push_update("inventory", list(ctx.player.inventory))
    start_quest = effects.get("start_quest")
    if start_quest and ctx.quest_repo is not None:
        _start_quest(str(start_quest), ctx)
    if effects.get("end_dialogue"):
        flags = {**ctx.player.flags}
        flags.pop(_NPC_KEY, None)
        flags.pop(_NODE_KEY, None)
        ctx.player.flags = flags
        ctx.push_update("dialogue", None)


def _start_quest(quest_id: str, ctx: GameContext) -> None:
    if ctx.quest_repo is None:
        return
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
