"""Rule evaluation layer."""

from __future__ import annotations

from collections.abc import Callable
from collections import defaultdict
from dataclasses import dataclass

from lorecraft.types import JsonObject


@dataclass(frozen=True)
class RuleResult:
    allowed: bool
    reason: str | None = None
    modified_payload: JsonObject | None = None

    @classmethod
    def allow(cls, modified_payload: JsonObject | None = None) -> "RuleResult":
        return cls(allowed=True, modified_payload=modified_payload)

    @classmethod
    def block(cls, reason: str) -> "RuleResult":
        return cls(allowed=False, reason=reason)


RuleFn = Callable[[object, JsonObject], RuleResult]


class RuleEngine:
    def __init__(self) -> None:
        self._rules: dict[str, list[RuleFn]] = defaultdict(list)

    def register_rule(self, event_type: str, rule_fn: RuleFn) -> None:
        self._rules[event_type].append(rule_fn)

    def check(
        self, event_type: str, ctx: object, payload: JsonObject | None = None
    ) -> RuleResult:
        current_payload = dict(payload or {})
        for rule in self._rules.get(event_type, []):
            result = rule(ctx, current_payload)
            if not result.allowed:
                return result
            if result.modified_payload:
                current_payload.update(result.modified_payload)
        return RuleResult.allow(current_payload)
