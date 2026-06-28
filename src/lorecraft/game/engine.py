"""Command dispatch loop scaffold."""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.game.context import GameContext
from lorecraft.game.events import GameEvent
from lorecraft.game.parser import ParsedCommand, parse
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rules import RuleEngine
from lorecraft.services.audit import AuditService
from lorecraft.types import JsonObject


@dataclass
class CommandEngine:
    registry: CommandRegistry
    rules: RuleEngine

    def handle_command(self, raw: str, ctx: GameContext) -> ParsedCommand:
        parsed = parse(raw)
        if not parsed.verb:
            ctx.say("Enter a command.")
            self._record_blocked(ctx, parsed, "empty_command", "No command entered.")
            return parsed

        command = self.registry.get(parsed.verb)
        if command is None:
            ctx.say("I don't understand that command.")
            self._record_blocked(ctx, parsed, "unknown_command", "Unknown command.")
            return parsed

        condition = self.registry.evaluate_conditions(command, ctx)
        if not condition.allowed:
            reason = condition.reason or "You can't do that."
            ctx.say(reason)
            self._record_blocked(ctx, parsed, "condition_blocked", reason)
            return parsed

        rule_result = self.rules.check(
            parsed.verb, ctx, {"noun": parsed.noun, "raw": parsed.raw}
        )
        if not rule_result.allowed:
            reason = rule_result.reason or "You can't do that."
            ctx.say(reason)
            self._record_blocked(ctx, parsed, "rule_blocked", reason)
            return parsed

        command.handler(parsed.noun, ctx)
        ctx.commit_state_changes()
        self._record_success(ctx, parsed)
        ctx.flush_events()
        return parsed

    def _record_blocked(
        self, ctx: GameContext, parsed: ParsedCommand, reason_type: str, reason: str
    ) -> None:
        payload: JsonObject = {
            "verb": parsed.verb,
            "noun": parsed.noun,
            "raw": parsed.raw,
            "reason_type": reason_type,
            "reason": reason,
        }
        AuditService.from_context(ctx).record(
            ctx,
            GameEvent.COMMAND_BLOCKED,
            severity="WARNING",
            summary=f"Command blocked: {reason}",
            payload=payload,
        )
        ctx.commit_audit_events()

    def _record_success(self, ctx: GameContext, parsed: ParsedCommand) -> None:
        payload: JsonObject = {
            "verb": parsed.verb,
            "noun": parsed.noun,
            "raw": parsed.raw,
        }
        AuditService.from_context(ctx).record(
            ctx,
            GameEvent.COMMAND_EXECUTED,
            severity="INFO",
            summary=f"Command executed: {parsed.verb}",
            payload=payload,
        )
        ctx.commit_audit_events()
