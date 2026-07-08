"""Both pluggable predicate registries must degrade *and* log on failure.

A buggy predicate should never crash command dispatch or dialogue rendering,
but the old behaviour swallowed the exception with no trace: the command
silently became unavailable / the dialogue option silently vanished, with
nothing in the logs to explain why. These tests pin the fix — the failure is
still absorbed (graceful degradation) but is now logged with a traceback.
"""

from __future__ import annotations

import logging
from typing import cast

import pytest

from lorecraft.engine.game.command_conditions import (
    CommandConditionRegistry,
    ConditionResult,
)
from lorecraft.engine.game.context import GameContext
from lorecraft.features.npc.dialogue_conditions import ConditionRegistry
from lorecraft.types import JsonObject

# The registries invoke the predicate before it touches ctx, so a throwaway
# sentinel is enough — the predicate under test raises immediately.
_CTX = cast(GameContext, object())


def _boom(*_args: object) -> ConditionResult:
    raise RuntimeError("predicate is broken")


class TestCommandConditionErrorHandling:
    def test_failed_predicate_degrades_to_disallowed(self) -> None:
        registry = CommandConditionRegistry()
        registry.register("boom", _boom)

        result = registry.evaluate("boom", _CTX)

        assert result.allowed is False
        assert result.reason == "Condition evaluation error."

    def test_failed_predicate_is_logged_with_traceback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        registry = CommandConditionRegistry()
        registry.register("boom", _boom)

        with caplog.at_level(
            logging.ERROR, logger="lorecraft.engine.game.command_conditions"
        ):
            registry.evaluate("boom", _CTX)

        assert any(
            "command_condition_failed" in r.message and r.exc_info
            for r in caplog.records
        ), "expected a logged record with exception info"

    def test_unknown_condition_still_allows(self) -> None:
        # Regression guard: the logging change must not touch the
        # forward-compatible "unknown condition => allowed" fast path.
        registry = CommandConditionRegistry()
        assert registry.evaluate("never_registered", _CTX).allowed is True


class TestDialogueConditionErrorHandling:
    @staticmethod
    def _boom_predicate(_data: JsonObject, _ctx: GameContext) -> bool:
        raise RuntimeError("predicate is broken")

    def test_failed_predicate_degrades_to_hidden(self) -> None:
        registry = ConditionRegistry()
        registry.register("boom", self._boom_predicate)

        assert registry.evaluate(cast(JsonObject, {"boom": {}}), _CTX) is False

    def test_failed_predicate_is_logged_with_traceback(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        registry = ConditionRegistry()
        registry.register("boom", self._boom_predicate)

        with caplog.at_level(
            logging.ERROR, logger="lorecraft.features.npc.dialogue_conditions"
        ):
            registry.evaluate(cast(JsonObject, {"boom": {}}), _CTX)

        assert any(
            "dialogue_condition_failed" in r.message and r.exc_info
            for r in caplog.records
        ), "expected a logged record with exception info"

    def test_unknown_condition_ignored(self) -> None:
        # Regression guard: unknown condition types stay ignored (all-pass).
        registry = ConditionRegistry()
        assert (
            registry.evaluate(cast(JsonObject, {"never_registered": {}}), _CTX) is True
        )
