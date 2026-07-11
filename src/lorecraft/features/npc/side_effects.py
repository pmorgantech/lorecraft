"""Dialogue side effect registry: pluggable handlers for quest/item/flag effects.

See docs/feature-registration.md for the complete feature registration pattern,
which shows how to plug new side effects (combat.start_combat, etc.) without
modifying dialogue.py.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.scripting.vocabulary import (
    CapabilitySig,
    ParamSpec,
    Subject,
    VocabEntry,
    VocabKind,
    global_vocabulary,
)
from lorecraft.features.quests.models import PlayerQuestProgress
from lorecraft.features.quests.repo import QuestRepo
from lorecraft.types import JsonObject, JsonValue

if TYPE_CHECKING:
    from lorecraft.engine.game.context import GameContext

SideEffectHandler = Callable[[JsonValue, "GameContext"], None]


class SideEffectRegistry:
    """Registry of dialogue side effect handlers.

    Built-in handlers (set_flags, clear_flags, give_item, start_quest,
    end_dialogue) are registered at module load. New effects can be
    registered by calling register() without touching dialogue.py.

    Handlers registered via :meth:`register_spec` also publish a self-describing
    :class:`VocabEntry` descriptor into the shared scripting catalog
    (``global_vocabulary()``) — the path new effects should use so they show up in the
    generated builder-guide and are checked for duplication (see
    ``docs/scripting_engine_design.md`` §8). The bare :meth:`register` remains for
    un-migrated callers.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, SideEffectHandler] = {}

    def register(self, effect_name: str, handler: SideEffectHandler) -> None:
        """Register a side effect handler by name (no catalog descriptor)."""
        self._handlers[effect_name] = handler

    def register_spec(self, spec: VocabEntry, handler: SideEffectHandler) -> None:
        """Register a handler *and* its descriptor in the shared catalog.

        The descriptor's ``name`` is the handler's key, so the two can't drift. An
        exact-name collision in the shared catalog raises ``VocabularyError`` (loud, not a
        silent overwrite).
        """
        global_vocabulary().register(spec)
        self._handlers[spec.name] = handler

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
    from lorecraft.features.inventory.service import inventory_update_entries

    item_id = str(data)
    item = ctx.item_repo.get(item_id)
    loc = Location("player", ctx.player.id)
    if item and ctx.stack_repo.quantity_of(loc, item_id) <= 0:
        ctx.item_location.spawn(item_id, loc)
        ctx.say(f"You receive {item.name}.")
        ctx.push_update(
            "inventory",
            inventory_update_entries(ctx.item_repo.stacks_carried_by(ctx.player.id)),
        )


def _handle_start_quest(data: JsonValue, ctx: "GameContext") -> None:  # type: ignore[misc]
    quest_repo = QuestRepo(ctx.session)
    quest_id = str(data)
    quest = quest_repo.get(quest_id)
    if quest is None or not quest.stages:
        return
    if quest_repo.player_progress(ctx.player.id, quest_id) is not None:
        return
    first_stage = quest.stages[0]
    quest_repo.add_progress(
        PlayerQuestProgress(
            player_id=ctx.player.id,
            quest_id=quest_id,
            current_stage_id=str(first_stage["id"]),
            status="active",
            started_at=time.time(),
            stage_started_epoch=ctx.clock.game_epoch if ctx.clock is not None else 0.0,
        )
    )
    ctx.say(f"Quest started: {quest.title}.", MessageType.QUEST)
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
    from lorecraft.features.npc.dialogue import _NPC_KEY, _NODE_KEY

    flags = {**ctx.player.flags}
    flags.pop(_NPC_KEY, None)
    flags.pop(_NODE_KEY, None)
    ctx.player.flags = flags
    ctx.push_update("dialogue", None)


def _handle_narrate_room(data: JsonValue, ctx: "GameContext") -> None:  # type: ignore[misc]
    """World-safe narration to a room's occupants (the first *visible* trigger effect).

    ``{narrate_room: "text"}`` narrates to the actor's current room; the map form
    ``{narrate_room: {room: <id>, text: "..."}}`` targets an explicit room. Broadcasts
    immediately (autonomous-style, actor included) so the line shows up in the room feed.
    """
    from lorecraft.engine.game.world_context import broadcast_room_async

    if isinstance(data, str):
        text, room_id = data, ctx.room.id
    elif isinstance(data, dict):
        text = str(data.get("text", ""))
        raw_room = data.get("room")
        room_id = raw_room if isinstance(raw_room, str) else ctx.room.id
    else:
        return
    if text:
        broadcast_room_async(ctx.manager, room_id, text)


def _handle_narrate_zone(data: JsonValue, ctx: "GameContext") -> None:  # type: ignore[misc]
    """Broadcast a line to every room in a zone (scripting engine A5).

    ``{narrate_zone: "text"}`` uses the actor's current zone; ``{narrate_zone: {area, text}}``
    targets an explicit ``zone``.
    """
    from lorecraft.engine.game.world_context import broadcast_room_async

    if isinstance(data, str):
        text: str = data
        area = ctx.room.zone
    elif isinstance(data, dict):
        text = str(data.get("text", ""))
        raw_area = data.get("area")
        area = raw_area if isinstance(raw_area, str) else ctx.room.zone
    else:
        return
    if not text or not area:
        return
    for room in ctx.room_repo.rooms_in_area(area):
        broadcast_room_async(ctx.manager, room.id, text)


def _handle_apply_effect(data: JsonValue, ctx: "GameContext") -> None:  # type: ignore[misc]
    """Apply a timed :class:`ActiveEffect` to a target (scripting engine A4/A5).

    ``apply_effect: {effect: <key>, target: actor|room|stored_item, ticks?: N}``. ``stored_item``
    resolves to the item id in ``ctx.event_payload`` (the item a container trigger just handled).
    ``ticks`` omitted = permanent. The ``effect`` key must be a registered effect definition.
    """
    if not isinstance(data, dict):
        return
    effect_key = str(data.get("effect", ""))
    if not effect_key:
        return
    target = str(data.get("target", "actor"))
    raw_ticks = data.get("ticks")
    duration = (
        float(raw_ticks)
        if isinstance(raw_ticks, (int, float)) and not isinstance(raw_ticks, bool)
        else None
    )
    entity_type, entity_id = _effect_target(target, ctx)
    if entity_id is None:
        return
    epoch = ctx.clock.game_epoch if ctx.clock is not None else 0.0
    ctx.effects.apply(
        ctx.session,
        entity_type=entity_type,
        entity_id=entity_id,
        effect_key=effect_key,
        duration_ticks=duration,
        clock_epoch=epoch,
    )


def _effect_target(target: str, ctx: "GameContext") -> tuple[str, str | None]:
    if target == "room":
        return "room", ctx.room.id
    if target == "stored_item":
        item_id = ctx.event_payload.get("item_id")
        return "item", item_id if isinstance(item_id, str) else None
    return "player", ctx.player.id  # default: the actor


def _effect(
    name: str,
    *,
    category: str,
    domain: str,
    attribute: str,
    op: str,
    doc: str,
    params: tuple[ParamSpec, ...] = (),
    subject: Subject = Subject.ACTOR,
) -> VocabEntry:
    return VocabEntry(
        name=name,
        kind=VocabKind.EFFECT,
        subject=subject,
        category=category,
        doc=doc,
        capability=CapabilitySig(subject, domain, attribute, op),
        params=params,
    )


_registry.register_spec(
    _effect(
        "set_flags",
        category="flags",
        domain="flags",
        attribute="<flag>",
        op="set",
        doc="Set one or more boolean flags on the actor.",
        params=(ParamSpec("flags", "list[str]", doc="Flag names to set true."),),
    ),
    _handle_set_flags,
)
_registry.register_spec(
    _effect(
        "clear_flags",
        category="flags",
        domain="flags",
        attribute="<flag>",
        op="clear",
        doc="Remove one or more boolean flags from the actor.",
        params=(ParamSpec("flags", "list[str]", doc="Flag names to clear."),),
    ),
    _handle_clear_flags,
)
_registry.register_spec(
    _effect(
        "give_item",
        category="inventory",
        domain="inventory",
        attribute="item",
        op="give",
        doc="Give the actor one of an item (no-op if already carried).",
        params=(ParamSpec("item_id", "item_id", doc="Item to grant."),),
    ),
    _handle_give_item,
)
_registry.register_spec(
    _effect(
        "start_quest",
        category="quests",
        domain="quests",
        attribute="quest",
        op="start",
        doc="Start a quest for the actor at its first stage (no-op if already started).",
        params=(ParamSpec("quest_id", "quest_id", doc="Quest to start."),),
    ),
    _handle_start_quest,
)
_registry.register_spec(
    _effect(
        "end_dialogue",
        category="dialogue",
        domain="dialogue",
        attribute="session",
        op="clear",
        doc="Close the actor's current dialogue session.",
    ),
    _handle_end_dialogue,
)
_registry.register_spec(
    _effect(
        "narrate_room",
        subject=Subject.WORLD,
        category="narration",
        domain="narration",
        attribute="room",
        op="broadcast",
        doc=(
            'Broadcast a line to a room\'s occupants. Scalar form `narrate_room: "text"` '
            "targets the actor's room; map form `{text, room?}` can target another room."
        ),
        params=(
            ParamSpec(
                "text", "str", doc="The line to narrate (or a {text, room?} map)."
            ),
        ),
    ),
    _handle_narrate_room,
)
_registry.register_spec(
    _effect(
        "narrate_zone",
        subject=Subject.WORLD,
        category="narration",
        domain="narration",
        attribute="zone",
        op="broadcast",
        doc="Broadcast a line to every room in a zone (defaults to the actor's area).",
        params=(ParamSpec("text", "str", doc="The line (or a {text, area?} map)."),),
    ),
    _handle_narrate_zone,
)
_registry.register_spec(
    _effect(
        "apply_effect",
        subject=Subject.TARGET,
        category="effects",
        domain="effects",
        attribute="active",
        op="apply",
        doc="Apply a timed ActiveEffect to a target (actor | room | stored_item).",
        params=(
            ParamSpec("effect", "effect_key", doc="Registered effect definition key."),
            ParamSpec(
                "target",
                "subject",
                required=False,
                doc="actor (default) | room | stored_item.",
            ),
            ParamSpec(
                "ticks", "int", required=False, doc="Duration; omitted = permanent."
            ),
        ),
    ),
    _handle_apply_effect,
)


def get_registry() -> SideEffectRegistry:
    """Get the global side effect registry."""
    return _registry
