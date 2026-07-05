"""Player-facing bug/feedback report command.

Wires directly into the existing repo-tracked issue tracker
(`content/issues.py`, Sprint 10.5.1) via the same `create_issue()` both this
command and the admin `POST /admin/issues` endpoint call — one construction
path, so reports show up immediately in the admin issues list/TUI panel
without a parallel system to keep in sync.
"""

from __future__ import annotations

from lorecraft.content.issues import create_issue
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandRegistry, CommandScope

_MAX_REPORT_LENGTH = 1000
_MAX_TITLE_LENGTH = 80


def _build_title(text: str) -> str:
    if len(text) <= _MAX_TITLE_LENGTH:
        return text
    return f"{text[: _MAX_TITLE_LENGTH - 3]}..."


def register_report_commands(registry: CommandRegistry) -> None:
    @registry.register(
        "report",
        "/report",
        scope=CommandScope.GLOBAL,
        help="report <description> (also /report) — report a bug or issue to the developers",
    )
    def report_command(noun: str | None, ctx: GameContext) -> None:
        text = (noun or "").strip()
        if not text:
            ctx.say("Report what? Usage: report <description of the bug or issue>.")
            return

        truncated = len(text) > _MAX_REPORT_LENGTH
        if truncated:
            text = text[:_MAX_REPORT_LENGTH]

        issue = create_issue(
            ctx.session,
            title=_build_title(text),
            description=text,
            type="bug",
            component="player-report",
            created_by=ctx.player.username,
            tags=["player-report"],
        )
        note = " (truncated to 1000 characters)" if truncated else ""
        ctx.say(f"Thanks — logged as {issue.id}{note}. The team will take a look.")
