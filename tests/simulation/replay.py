"""Scenario playback against a live simulation server (Sprint 43, Phase 1).

Replays a `lorecraft.tools.session_replay.Scenario` through the existing
`VirtualPlayer` WebSocket harness and returns the resulting normalised audit
trail, so callers can diff it against a golden or a second run. Lives with the
tests (not `src/`) because it drives the live-server fixtures; the scenario
format and normaliser it consumes are production code in
`lorecraft.tools.session_replay`.

Phase 1 scope: single actor, `fast` timing (each command sent as soon as the
previous reply arrives; recorded `t` deltas are ignored). N-player fan-out and
timing modes are Phase 2/3 (`docs/session_replay.md`).
"""

from __future__ import annotations

import uuid

from lorecraft.tools.session_replay import NormalizedEvent, Scenario, normalize_events
from tests.simulation.conftest import SimulationServer
from tests.simulation.virtual_player import VirtualPlayer


async def replay_scenario(
    server: SimulationServer, scenario: Scenario
) -> list[NormalizedEvent]:
    """Replay a single-actor scenario; return the actor's normalised trail.

    The scenario's actor is *logical*: a fresh player is created on the
    server and the recorded command stream is driven through it, so replays
    never depend on the recorded player existing in the target world.
    """
    if len(scenario.actors) != 1:
        raise NotImplementedError(
            f"Phase 1 replay is single-actor; scenario has {len(scenario.actors)} "
            "actors (N-player fan-out is Sprint 43.2)"
        )
    actor = scenario.actors[0]
    username = f"replay_{uuid.uuid4().hex[:8]}"
    player_id = server.create_player(username)
    player = await VirtualPlayer.connect(server.ws_url, player_id, username)
    try:
        for command in scenario.commands_for(actor):
            await player.send_command(command.raw)
    finally:
        await player.close()
    return normalize_events(server.audit_trail_for(player_id))
