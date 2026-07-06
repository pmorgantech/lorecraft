"""Scavenger-hunt commands: the read-only `hunts` verb (Sprint 48)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.features.hunts.models import HuntDef
from lorecraft.features.hunts.service import HuntService


def register_hunt_commands(
    registry: CommandRegistry, hunt_service: HuntService | None = None
) -> None:
    service = hunt_service or HuntService()

    @registry.register(
        "hunts",
        help="hunts — list active scavenger hunts and your progress",
    )
    def hunts_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        active = service.open_hunts()
        if not active:
            ctx.say("There are no scavenger hunts running right now.")
            return
        ctx.say("=== Active hunts ===")
        for hunt in active:
            ctx.say(_progress_line(hunt, ctx))

    def _progress_line(hunt: HuntDef, ctx: GameContext) -> str:
        if ctx.player.flags.get(f"hunt:{hunt.id}:done"):
            return f"{hunt.name}: completed ✓"
        found = sum(
            1
            for item_id in hunt.clue_items
            if ctx.player.flags.get(f"hunt:{hunt.id}:found:{item_id}")
        )
        return f"{hunt.name}: {found}/{len(hunt.clue_items)} found"
