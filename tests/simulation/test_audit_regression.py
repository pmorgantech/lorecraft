"""Audit log regression testing (Sprint 12 / architecture.md §25).

Runs the same scripted command sequence for one virtual player against two
independent, freshly-bootstrapped servers and asserts the *shape* of the
resulting audit trail is identical: same event types, summaries, targets,
rooms, and severities, in the same order. Real IDs (transaction/correlation
IDs, timestamps, the player's own generated UUID) legitimately differ between
runs and are excluded from the comparison.

This is the harness described for "audit log regression testing: run a known
script, capture the audit log, run it again after code changes, diff the
logs" — used here as a determinism check today, and as the scaffold future
sprints can point a second (pre-change) capture at.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from lorecraft.models.audit import AuditEvent
from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer

pytestmark = pytest.mark.simulation

_USERNAME = "regression_bot"
_SCRIPT = [
    "look",
    "go east",
    "take coin",
    "go west",
    "talk mira",
    "choice 1",
    "bye",
]

NormalizedEvent = tuple[str, str, str | None, str, str]


def _normalize(events: list[AuditEvent]) -> list[NormalizedEvent]:
    return [
        (
            event.event_type,
            event.summary,
            event.target_id,
            event.room_id,
            event.severity,
        )
        for event in events
    ]


async def _run_script(server: SimulationServer) -> list[NormalizedEvent]:
    player_id = server.create_player(_USERNAME)
    player = await VirtualPlayer.connect(server.ws_url, player_id, _USERNAME)
    try:
        await player.run_script(_SCRIPT)
    finally:
        await player.close()
    return _normalize(server.audit_trail_for(player_id))


def test_same_script_produces_the_same_normalized_audit_trail(
    simulation_server_factory: Callable[[], SimulationServer],
) -> None:
    """Regression guard: replaying the golden-path script twice, against two
    independent fresh servers, should record the same sequence of audit
    events (modulo run-specific IDs/timestamps). A divergence here means a
    code change made command handling non-deterministic for an identical
    script — worth investigating before merging."""
    first_run = asyncio.run(_run_script(simulation_server_factory()))
    second_run = asyncio.run(_run_script(simulation_server_factory()))

    assert first_run == second_run
    assert len(first_run) > 0
