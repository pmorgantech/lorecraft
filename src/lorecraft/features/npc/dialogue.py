"""Dialogue tree walker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.npc.repo import DialogueRepo
from lorecraft.types import JsonObject

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext
    from lorecraft.engine.repos.npc_repo import NpcRepo

_NPC_KEY = "_dialogue_npc_id"
_NODE_KEY = "_dialogue_node_id"


def current_npc_id(ctx: GameContext) -> str | None:
    """The NPC the player is currently talking to, or None outside dialogue.

    Exposed for other npc/ modules (npc_memory_conditions.py) that need to
    scope a side effect or condition to "whichever NPC this conversation is
    with" without reaching into the private dialogue flag keys themselves.
    """
    npc_id = ctx.player.flags.get(_NPC_KEY)
    return str(npc_id) if npc_id else None


class DialogueService:
    def start(self, npc_id: str, ctx: GameContext) -> None:
        npc = ctx.npc_repo.get(npc_id)
        if npc is None:
            ctx.say("That person isn't here.")
            return
        if npc_id not in ctx.player.met_npcs:
            ctx.player.met_npcs = [*ctx.player.met_npcs, npc_id]
        if not npc.dialogue_tree_id:
            ctx.say(f"{npc.name} has nothing to say.")
            return
        tree_record = DialogueRepo(ctx.session).get(npc.dialogue_tree_id)
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
        if npc is None:
            self._end(ctx)
            return
        tree_record = DialogueRepo(ctx.session).get(npc.dialogue_tree_id)
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

    def _push_dialogue_panel(
        self,
        ctx: GameContext,
        *,
        npc_name: str,
        node_text: str,
        choices: list[JsonObject],
        terminal: bool = False,
    ) -> None:
        ctx.push_update(
            "dialogue",
            {
                "npc_name": npc_name,
                "node_text": node_text,
                "choices": [
                    {"index": i + 1, "label": str(choice.get("label", ""))}
                    for i, choice in enumerate(choices)
                ],
                "terminal": terminal,
            },
        )

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
        visible = _visible_choices(node, ctx)
        terminal = not visible

        node_effects: JsonObject = node.get("side_effects", {}) or {}  # type: ignore[assignment]
        if terminal and node_effects.get("end_dialogue"):
            node_effects = {
                key: value
                for key, value in node_effects.items()
                if key != "end_dialogue"
            }
        _apply_side_effects(node_effects, ctx)

        self._push_dialogue_panel(
            ctx,
            npc_name=npc_name,
            node_text=text,
            choices=visible,
            terminal=terminal,
        )


def dialogue_panel_state(
    player_flags: JsonObject,
    npc_repo: NpcRepo,
    dialogue_repo: DialogueRepo,
) -> JsonObject | None:
    """Build dialogue overlay payload from persisted player dialogue flags."""
    npc_id = player_flags.get(_NPC_KEY)
    node_id = player_flags.get(_NODE_KEY)
    if not npc_id or not node_id:
        return None

    npc = npc_repo.get(str(npc_id))
    if npc is None or not npc.dialogue_tree_id:
        return None
    tree_record = dialogue_repo.get(npc.dialogue_tree_id)
    if tree_record is None:
        return None

    tree = tree_record.tree_data
    nodes: JsonObject = tree.get("nodes", {})  # type: ignore[assignment]
    node: JsonObject = nodes.get(str(node_id), {})  # type: ignore[assignment]
    if not node:
        return None

    visible = _visible_choices_for_flags(node, player_flags)
    terminal = not visible

    return {
        "npc_name": npc.name,
        "node_text": str(node.get("text", "")),
        "choices": [
            {"index": i + 1, "label": str(choice.get("label", ""))}
            for i, choice in enumerate(visible)
        ],
        "terminal": terminal,
    }


def _visible_choices_for_flags(
    node: JsonObject, player_flags: JsonObject
) -> list[JsonObject]:
    """Check choices using the condition registry (flag-based only, no ctx)."""
    choices = node.get("choices", [])
    visible: list[JsonObject] = []
    for choice in choices:  # type: ignore[union-attr]
        required = choice.get("required_flags", [])
        forbidden = choice.get("forbidden_flags", [])
        if all(player_flags.get(str(flag)) for flag in required):
            if not any(player_flags.get(str(flag)) for flag in forbidden):
                visible.append(choice)  # type: ignore[arg-type]
    return visible


def _choice_visible(choice: JsonObject, ctx: GameContext) -> bool:
    """Evaluate all conditions on a choice using the registry; all must pass."""
    from lorecraft.features.npc.dialogue_conditions import get_registry

    registry = get_registry()
    conditions: JsonObject = {}
    # Extract all condition fields (anything that's a registry predicate)
    for key, value in choice.items():  # type: ignore[union-attr]
        if key in registry:
            conditions[key] = value
    return registry.evaluate(conditions, ctx)


def _visible_choices(node: JsonObject, ctx: GameContext) -> list[JsonObject]:
    """Return choices visible given conditions; uses registry for extensibility."""
    choices = node.get("choices", [])
    visible: list[JsonObject] = []
    for choice in choices:  # type: ignore[union-attr]
        if _choice_visible(choice, ctx):
            visible.append(choice)  # type: ignore[arg-type]
    return visible


def _apply_side_effects(effects: JsonObject, ctx: GameContext) -> None:
    """Apply dialogue side effects using the registered handlers."""
    from lorecraft.features.npc.side_effects import get_registry

    registry = get_registry()
    registry.apply(effects, ctx)


def _start_quest(quest_id: str, ctx: GameContext) -> None:
    """Start a quest for the player. Kept for backward compatibility with tests."""
    from lorecraft.features.npc.side_effects import _handle_start_quest

    _handle_start_quest(quest_id, ctx)
