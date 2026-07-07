"""Marks commands: the read-only `marks` verb (Sprint 53.3)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.features.marks.service import MarkService


def register_mark_commands(
    registry: CommandRegistry, mark_service: MarkService | None = None
) -> None:
    service = mark_service or MarkService()

    @registry.register(
        "marks",
        help="marks — list the marks you have earned by discovery",
    )
    def marks_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        earned = service.earned(ctx.player)
        undiscovered = service.unearned_visible(ctx.player)
        if not earned and not undiscovered:
            ctx.say("No marks are known in this world.")
            return
        ctx.say("=== Marks ===")
        for mark in earned:
            line = f"✦ {mark.name}"
            if mark.description:
                line += f" — {mark.description}"
            ctx.say(line)
        # Unearned, non-hidden marks tease as "???" — a nudge to explore.
        # Hidden marks are omitted entirely until earned.
        for _ in undiscovered:
            ctx.say("??? — undiscovered")
