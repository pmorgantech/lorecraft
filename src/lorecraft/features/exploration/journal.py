"""Journal: discovered places, met NPCs, learned lore, active quests (Sprint 25.3).

Lore is a data-driven convention, not a new subsystem: dialogue side effects
already set arbitrary player flags (Sprint 10.1's set_flags); world authors
mark a flag as a lore entry by prefixing its name with "lore:" — this
service just surfaces every such flag the player has set, with no new
authoring mechanism to learn.
"""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.features.quests.repo import QuestRepo

LORE_FLAG_PREFIX = "lore:"


class JournalService:
    def show(self, ctx: GameContext) -> None:
        ctx.say("=== Journal ===")

        self._show_places(ctx)
        self._show_npcs(ctx)
        self._show_items(ctx)
        self._show_lore(ctx)
        self._show_quests(ctx)

    def _show_places(self, ctx: GameContext) -> None:
        room_ids = ctx.player.visited_rooms
        if not room_ids:
            ctx.say("Places visited: none yet.")
            return
        names = sorted(
            room.name
            for room_id in room_ids
            if (room := ctx.room_repo.active(room_id)) is not None
        )
        ctx.say(f"Places visited: {', '.join(names)}.")

    def _show_npcs(self, ctx: GameContext) -> None:
        npc_ids = ctx.player.met_npcs
        if not npc_ids:
            ctx.say("People met: none yet.")
            return
        names = sorted(
            npc.name
            for npc_id in npc_ids
            if (npc := ctx.npc_repo.get(npc_id)) is not None
        )
        ctx.say(f"People met: {', '.join(names)}.")

    def _show_items(self, ctx: GameContext) -> None:
        item_ids = ctx.player.discovered_items
        if not item_ids:
            ctx.say("Items discovered: none yet.")
            return
        names = sorted(
            item.name
            for item_id in item_ids
            if (item := ctx.item_repo.get(item_id)) is not None
        )
        ctx.say(f"Items discovered: {', '.join(names)}.")

    def _show_lore(self, ctx: GameContext) -> None:
        lore_topics = sorted(
            flag[len(LORE_FLAG_PREFIX) :]
            for flag, value in ctx.player.flags.items()
            if flag.startswith(LORE_FLAG_PREFIX) and value
        )
        if not lore_topics:
            ctx.say("Lore learned: none yet.")
            return
        ctx.say(f"Lore learned: {', '.join(lore_topics)}.")

    def _show_quests(self, ctx: GameContext) -> None:
        quest_repo = QuestRepo(ctx.session)
        active = quest_repo.active_progress(ctx.player.id)
        if not active:
            ctx.say("Active clues: none.")
            return
        titles = []
        for progress in active:
            quest = quest_repo.get(progress.quest_id)
            titles.append(quest.title if quest is not None else progress.quest_id)
        ctx.say(f"Active clues: {', '.join(sorted(titles))}.")
