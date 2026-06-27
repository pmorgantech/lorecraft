"""Command dispatch loop scaffold."""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.game.context import GameContext
from lorecraft.game.parser import ParsedCommand, parse
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rules import RuleEngine


@dataclass
class CommandEngine:
    registry: CommandRegistry
    rules: RuleEngine

    def handle_command(self, raw: str, ctx: GameContext) -> ParsedCommand:
        parsed = parse(raw)
        if not parsed.verb:
            ctx.say("Enter a command.")
            return parsed

        command = self.registry.get(parsed.verb)
        if command is None:
            ctx.say("I don't understand that command.")
            return parsed

        condition = self.registry.evaluate_conditions(command, ctx)
        if not condition.allowed:
            ctx.say(condition.reason or "You can't do that.")
            return parsed

        rule_result = self.rules.check(parsed.verb, ctx, {"noun": parsed.noun, "raw": parsed.raw})
        if not rule_result.allowed:
            ctx.say(rule_result.reason or "You can't do that.")
            return parsed

        command.handler(parsed.noun, ctx)
        return parsed
