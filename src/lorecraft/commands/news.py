"""News/announcements command."""

from __future__ import annotations

import time

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandRegistry, CommandScope


def _format_news_lines(ctx: GameContext) -> list[str]:
    if ctx.news_repo is None:
        return ["No news available."]
    items = ctx.news_repo.list_active(now=time.time())
    if not items:
        return ["No news right now."]
    lines = ["=== News ==="]
    for item in items:
        lines.append(f"[{item.type}] {item.title}")
        if item.body:
            lines.append(f"  {item.body.strip()}")
    return lines


def register_news_commands(registry: CommandRegistry) -> None:
    @registry.register(
        "news",
        "/news",
        scope=CommandScope.GLOBAL,
        help="news (also /news) — show current announcements",
    )
    def news_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        ctx.say("\n".join(_format_news_lines(ctx)))
