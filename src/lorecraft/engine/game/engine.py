"""Command dispatch loop scaffold."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from lorecraft.engine.game.command_patterns import (
    ROLE_OBJECT,
    ROLE_RECIPIENT,
    ROLE_TARGET,
)
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.parser import ParsedCommand, parse_command, registry_verb
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.services.audit import AuditService
from lorecraft.observability import time_operation
from lorecraft.types import JsonObject, JsonValue

log = logging.getLogger(__name__)


def _command_summary_text(parsed: ParsedCommand) -> str:
    """Full command text for an audit summary — the verb plus its arguments as
    the player typed them (e.g. "move south", "get all"), so the audit log reads
    at a glance instead of showing the bare verb. Falls back to the verb when no
    raw text is available, and caps length to keep summaries tidy."""
    text = (parsed.raw or "").strip()
    if not text:
        return parsed.verb
    return text if len(text) <= 120 else text[:117] + "..."


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


def _npc_target_id(parsed: ParsedCommand, ctx: GameContext) -> str | None:
    """The NPC id a command targeted, if any.

    Checked against `ctx.npc_repo` (not just "any resolved id") so item or
    player targets (e.g. `take sword`, `give coin to bob`) don't get counted
    as NPC interactions — only an id that actually names an NPC does. Feeds
    `AuditEvent.target_id`, which `analytics.npc_interaction_counts` reads
    (Sprint 51 — previously always `None`, so that query was always empty).
    """
    if ctx.npc_repo is None:
        return None
    for role in (ROLE_TARGET, ROLE_OBJECT, ROLE_RECIPIENT):
        candidate = parsed.resolved_ids.get(role)
        if candidate and ctx.npc_repo.get(candidate) is not None:
            return candidate
    return None


@dataclass
class CommandEngine:
    registry: CommandRegistry
    rules: RuleEngine

    def handle_command(self, raw: str, ctx: GameContext) -> ParsedCommand:
        with time_operation("command_parse") as parse_timing:
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
            executed = self._execute_parsed(
                parsed, ctx, parse_ms=parse_timing.duration_ms
            )
            if executed is not None:
                last_parsed = executed
        return last_parsed

    def _execute_parsed(
        self, parsed: ParsedCommand, ctx: GameContext, *, parse_ms: float = 0.0
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

        with time_operation("condition_evaluate") as condition_timing:
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
        start = time.perf_counter()
        try:
            command.handler(parsed.noun, ctx)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            log.exception("command_handler_crashed verb=%s", parsed.verb)
            self._rollback(ctx, parsed, exc, duration_ms)
            return None
        duration_ms = (time.perf_counter() - start) * 1000
        # flush_events() runs handlers (e.g. QuestService.check_progression) that
        # mutate ctx.session further — it must run before the one commit, or those
        # mutations are silently discarded when the request's session closes
        # (EventBus.emit() isolates handler exceptions into HandlerResult.error
        # rather than raising, so this can't turn a failed handler into a rollback
        # of the command's own already-applied changes).
        ctx.flush_events()
        with time_operation("db_commit") as commit_timing:
            ctx.commit_state_changes()
        perf: JsonObject = {
            "command_parse": round(parse_ms, 3),
            "condition_evaluate": round(condition_timing.duration_ms, 3),
            "db_commit": round(commit_timing.duration_ms, 3),
        }
        self._record_success(ctx, parsed, duration_ms, perf=perf)
        log.info("command_executed verb=%s duration_ms=%.2f", parsed.verb, duration_ms)
        # Announce the executed command on the bus so composition-layer
        # observers (e.g. the admin console's live audit feed) can react
        # without the engine knowing about them. The audit row is already
        # recorded and committed above, so a listener that re-reads the audit
        # log will see this command. Handler exceptions are isolated by the bus.
        ctx.emit(
            GameEvent.COMMAND_EXECUTED,
            actor_id=ctx.player.id,
            verb=parsed.verb,
            summary=_command_summary_text(parsed),
            room_id=ctx.room.id,
        )
        return parsed

    def _rollback(
        self,
        ctx: GameContext,
        parsed: ParsedCommand,
        exc: Exception,
        duration_ms: float,
    ) -> None:
        """Undo an in-flight command after its handler raised.

        Golden rule (architecture.md §26): never tell clients something
        happened until the database says it happened. A handler that raises
        may have left `ctx` with partial narration/updates and the game DB
        session with uncommitted, half-applied state — neither has been
        committed yet at this point, so discard both and roll the session
        back before reporting a generic failure.
        """
        ctx.rollback_state_changes()
        ctx.messages.clear()
        ctx.room_messages.clear()
        ctx.updates.clear()
        ctx.pending_events.clear()
        ctx.say("Something went wrong processing that command.")
        payload = _command_audit_payload(
            parsed,
            reason_type="handler_exception",
            reason=str(exc),
            error_type=type(exc).__name__,
        )
        payload["duration_ms"] = round(duration_ms, 3)
        AuditService.from_context(ctx).record(
            ctx,
            GameEvent.COMMAND_FAILED,
            target_id=_npc_target_id(parsed, ctx),
            severity="ERROR",
            summary=f"Command handler crashed: {_command_summary_text(parsed)}",
            payload=payload,
        )
        ctx.commit_audit_events()

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
            target_id=_npc_target_id(parsed, ctx),
            severity="WARNING",
            summary=f"Command blocked: {reason}",
            payload=payload,
        )
        ctx.commit_audit_events()

    def _record_success(
        self,
        ctx: GameContext,
        parsed: ParsedCommand,
        duration_ms: float,
        *,
        perf: JsonObject | None = None,
    ) -> None:
        payload = _command_audit_payload(parsed)
        payload["duration_ms"] = round(duration_ms, 3)
        if perf:
            # Per-operation breakdown (command_parse/condition_evaluate/db_commit)
            # feeding analytics.operation_latency_percentiles (Sprint 35.3).
            payload["perf"] = perf
        AuditService.from_context(ctx).record(
            ctx,
            GameEvent.COMMAND_EXECUTED,
            target_id=_npc_target_id(parsed, ctx),
            severity="INFO",
            summary=f"Command executed: {_command_summary_text(parsed)}",
            payload=payload,
        )
        ctx.commit_audit_events()
