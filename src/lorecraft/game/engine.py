"""Command dispatch loop scaffold."""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.game.context import GameContext
from lorecraft.game.events import GameEvent
from lorecraft.game.parser import ParsedCommand, parse_command, registry_verb
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rules import RuleEngine
from lorecraft.services.audit import AuditService
from lorecraft.types import JsonObject, JsonValue


def _command_audit_payload(parsed: ParsedCommand, **extra: str) -> JsonObject:
    payload: JsonObject = {
        "verb": parsed.verb,
        "raw": parsed.raw,
        **extra,
    }
    if parsed.noun is not None:
        payload["noun"] = parsed.noun
    if parsed.roles:
        payload["roles"] = dict(parsed.roles)
    if parsed.resolved_ids:
        resolved: dict[str, JsonValue] = {
            key: value for key, value in parsed.resolved_ids.items()
        }
        payload["resolved_ids"] = resolved
    return payload


@dataclass
class CommandEngine:
    registry: CommandRegistry
    rules: RuleEngine

    def handle_command(self, raw: str, ctx: GameContext) -> ParsedCommand:
        result = parse_command(raw, context=ctx)
        if result.error_message:
            ctx.say(result.error_message)
            if result.suggestions:
                ctx.say("Perhaps you meant: " + ", ".join(result.suggestions))
            blocked = ParsedCommand(verb="", raw=raw)
            self._record_blocked(
                ctx,
                blocked,
                "parse_error",
                result.error_message,
            )
            return blocked

        if not result.commands:
            ctx.say("Enter a command.")
            blocked = ParsedCommand(verb="", raw=raw)
            self._record_blocked(ctx, blocked, "empty_command", "No command entered.")
            return blocked

        last_parsed = result.commands[-1]
        for parsed in result.commands:
            executed = self._execute_parsed(parsed, ctx)
            if executed is not None:
                last_parsed = executed
        return last_parsed

    def _execute_parsed(
        self, parsed: ParsedCommand, ctx: GameContext
    ) -> ParsedCommand | None:
        lookup_verb = registry_verb(parsed.verb)
        if not lookup_verb:
            ctx.say("Enter a command.")
            self._record_blocked(ctx, parsed, "empty_command", "No command entered.")
            return None

        command = self.registry.get(lookup_verb)
        if command is None:
            ctx.say("I don't understand that command.")
            self._record_blocked(ctx, parsed, "unknown_command", "Unknown command.")
            return None

        condition = self.registry.evaluate_conditions(command, ctx)
        if not condition.allowed:
            reason = condition.reason or "You can't do that."
            ctx.say(reason)
            self._record_blocked(ctx, parsed, "condition_blocked", reason)
            return None

        rule_payload = _command_audit_payload(parsed)
        rule_result = self.rules.check(parsed.verb, ctx, rule_payload)
        if not rule_result.allowed:
            reason = rule_result.reason or "You can't do that."
            ctx.say(reason)
            self._record_blocked(ctx, parsed, "rule_blocked", reason)
            return None

        ctx.parsed_command = parsed
        command.handler(parsed.noun, ctx)
        ctx.commit_state_changes()
        self._record_success(ctx, parsed)
        ctx.flush_events()
        return parsed

    def _record_blocked(
        self, ctx: GameContext, parsed: ParsedCommand, reason_type: str, reason: str
    ) -> None:
        payload = _command_audit_payload(
            parsed,
            reason_type=reason_type,
            reason=reason,
        )
        AuditService.from_context(ctx).record(
            ctx,
            GameEvent.COMMAND_BLOCKED,
            severity="WARNING",
            summary=f"Command blocked: {reason}",
            payload=payload,
        )
        ctx.commit_audit_events()

    def _record_success(self, ctx: GameContext, parsed: ParsedCommand) -> None:
        payload = _command_audit_payload(parsed)
        AuditService.from_context(ctx).record(
            ctx,
            GameEvent.COMMAND_EXECUTED,
            severity="INFO",
            summary=f"Command executed: {parsed.verb}",
            payload=payload,
        )
        ctx.commit_audit_events()
