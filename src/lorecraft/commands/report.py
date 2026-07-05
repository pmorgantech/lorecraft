"""Player-facing bug/feedback report command.

Two ways to file a report, both landing in the same repo-tracked issue tracker
(`content/issues.py`, Sprint 10.5.1) via the single `create_issue()` path the
admin `POST /admin/issues` endpoint also uses:

* **One-liner (fast path):** ``report <description>`` logs immediately, exactly
  as before — unchanged for muscle memory and scripts.
* **Guided flow (Sprint 33.1):** bare ``report`` starts a short modal wizard
  (category → title → detail) whose state lives in ``player.flags`` (like the
  dialogue system), so the next few inputs are captured as answers. ``cancel``
  aborts at any step. The web layer routes free-text input to this command while
  the wizard is active (see ``resolve_command_text``).
"""

from __future__ import annotations

from typing import cast

from lorecraft.content.issues import create_issue
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.registry import CommandRegistry, CommandScope
from lorecraft.types import JsonObject

_MAX_REPORT_LENGTH = 1000
_MAX_TITLE_LENGTH = 80

# player.flags keys holding the in-progress wizard state. Presence of
# REPORT_WIZARD_FLAG is what the web layer checks to route input here.
REPORT_WIZARD_FLAG = "_report_step"
_REPORT_DRAFT = "_report_draft"

# Category -> issue `type`. Categories are what the player picks; they map onto
# the tracker's existing type field so reports slot into the same admin views.
_CATEGORIES: dict[str, str] = {
    "bug": "bug",
    "feedback": "feedback",
    "idea": "todo",
}
_CANCEL_WORDS = frozenset({"cancel", "abort", "stop", "quit"})


def _build_title(text: str) -> str:
    if len(text) <= _MAX_TITLE_LENGTH:
        return text
    return f"{text[: _MAX_TITLE_LENGTH - 3]}..."


def _clear_wizard(ctx: GameContext) -> None:
    flags = dict(ctx.player.flags)
    flags.pop(REPORT_WIZARD_FLAG, None)
    flags.pop(_REPORT_DRAFT, None)
    ctx.player.flags = flags


def _set_wizard(ctx: GameContext, step: str, draft: JsonObject) -> None:
    ctx.player.flags = {
        **ctx.player.flags,
        REPORT_WIZARD_FLAG: step,
        _REPORT_DRAFT: draft,
    }


def _file_report(
    ctx: GameContext, *, category: str, title: str, description: str
) -> None:
    issue = create_issue(
        ctx.session,
        title=_build_title(title),
        description=description,
        type=_CATEGORIES.get(category, "bug"),
        component="player-report",
        created_by=ctx.player.username,
        tags=["player-report", category],
    )
    ctx.emit(GameEvent.ISSUE_FILED, issue_id=issue.id)
    ctx.say(f"Thanks — logged as {issue.id} ({category}). The team will take a look.")


def _log_one_liner(ctx: GameContext, text: str) -> None:
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
    ctx.emit(GameEvent.ISSUE_FILED, issue_id=issue.id)
    note = " (truncated to 1000 characters)" if truncated else ""
    ctx.say(f"Thanks — logged as {issue.id}{note}. The team will take a look.")


def _advance_wizard(ctx: GameContext, answer: str) -> None:
    """Consume one wizard answer and move to the next step (or finish)."""
    step = cast(str, ctx.player.flags.get(REPORT_WIZARD_FLAG, ""))
    draft: JsonObject = dict(cast(JsonObject, ctx.player.flags.get(_REPORT_DRAFT, {})))

    if answer.lower() in _CANCEL_WORDS:
        _clear_wizard(ctx)
        ctx.say("Report cancelled — nothing was filed.")
        return

    if step == "category":
        category = answer.lower()
        if category not in _CATEGORIES:
            ctx.say(
                "Please choose a category: bug, feedback, or idea "
                "(or 'cancel' to stop)."
            )
            return
        draft["category"] = category
        _set_wizard(ctx, "title", draft)
        ctx.say("Got it. Give your report a short title (one line).")
        return

    if step == "title":
        if not answer.strip():
            ctx.say("A title can't be empty. Enter a short title (or 'cancel').")
            return
        draft["title"] = answer.strip()
        _set_wizard(ctx, "detail", draft)
        ctx.say(
            "Now describe it in as much detail as you like "
            "(or type 'skip' for no extra detail)."
        )
        return

    if step == "detail":
        detail = "" if answer.strip().lower() == "skip" else answer.strip()
        category = cast(str, draft.get("category", "bug"))
        title = cast(str, draft.get("title", ""))
        _clear_wizard(ctx)
        _file_report(ctx, category=category, title=title, description=detail)
        return

    # Unknown/stale step — reset defensively.
    _clear_wizard(ctx)
    ctx.say("Sorry, your report session expired. Type 'report' to start again.")


def register_report_commands(registry: CommandRegistry) -> None:
    @registry.register(
        "report",
        "/report",
        scope=CommandScope.GLOBAL,
        help="report [description] (also /report) — file a bug/feedback report; bare 'report' starts a guided flow",
    )
    def report_command(noun: str | None, ctx: GameContext) -> None:
        text = (noun or "").strip()

        # If a guided flow is in progress, treat this input as the next answer.
        if ctx.player.flags.get(REPORT_WIZARD_FLAG):
            _advance_wizard(ctx, text)
            return

        # `report <description>` — immediate one-liner (unchanged fast path).
        if text:
            _log_one_liner(ctx, text)
            return

        # Bare `report` — start the guided flow.
        _set_wizard(ctx, "category", {})
        ctx.say(
            "Let's file a report. What kind is it? "
            "Reply: bug, feedback, or idea (or 'cancel' to stop)."
        )
