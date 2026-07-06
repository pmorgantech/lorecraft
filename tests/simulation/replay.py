"""Scenario playback against a live simulation server (Sprint 43, Phases 1–2).

Replays a `lorecraft.tools.session_replay.Scenario` through the existing
`VirtualPlayer` WebSocket harness — either once for a golden audit diff
(`replay_scenario`, Phase 1) or fanned out across N concurrent players with
the load-test percentile report (`fan_out_scenario`, Phase 2). Lives with the
tests (not `src/`) because it drives the live-server fixtures; the scenario
format, normaliser, and report shape it consumes are production code in
`lorecraft.tools.session_replay`.

Timing is `fast` (each command sent as soon as the previous reply arrives;
recorded `t` deltas are ignored) with an optional per-command jitter for
fan-out. Honouring `t` (`realtime`) and mixed scenarios are Phase 3
(`docs/session_replay.md`).
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid

from lorecraft.tools.session_replay import (
    NormalizedEvent,
    Scenario,
    latency_report,
    normalize_events,
)
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


def fan_out_scenario(
    server: SimulationServer,
    scenario: Scenario,
    *,
    players: int,
    jitter_ms: int = 0,
) -> dict[str, float | int]:
    """Replay one scenario's command stream across N concurrent players.

    Each logical actor's recording is mapped onto `players` freshly created
    players who all drive the same stream concurrently (the load-test shape:
    contention over shared world state is the point, so commands like `take`
    may succeed for one player and fail for the rest — every command still
    returns a `command_result` and is measured). Returns the shared
    p50/p95/p99/max latency report.

    With `jitter_ms > 0`, each player sleeps a random 0..jitter before each
    command, approximating real think-time instead of a lockstep herd.
    """
    if len(scenario.actors) != 1:
        raise NotImplementedError(
            f"fan-out replays a single-actor scenario; this one has "
            f"{len(scenario.actors)} actors (mixed scenarios are Sprint 43.3)"
        )
    script = [command.raw for command in scenario.commands_for(scenario.actors[0])]
    # Character creation is setup, not part of the measured load — do it
    # synchronously up front so the async phase is purely connect + drive.
    credentials = [
        (server.create_player(name), name)
        for name in (f"replay_{i}_{uuid.uuid4().hex[:6]}" for i in range(players))
    ]
    latencies_ms = asyncio.run(_run_fan_out(server, script, credentials, jitter_ms))
    return latency_report(
        latencies_ms,
        players=players,
        commands_per_player=len(script),
        jitter_ms=jitter_ms,
    )


async def _run_fan_out(
    server: SimulationServer,
    script: list[str],
    credentials: list[tuple[str, str]],
    jitter_ms: int,
) -> list[float]:
    # Connect sequentially (setup, not measured): concurrent connects to the
    # same starting room race each socket's `connected` handshake against the
    # `player_joined` broadcasts from other joins. The measured load is the
    # concurrent command drive below.
    players: list[VirtualPlayer] = []
    for player_id, username in credentials:
        players.append(await VirtualPlayer.connect(server.ws_url, player_id, username))
    try:
        per_player = await asyncio.gather(
            *(_drive_script(player, script, jitter_ms) for player in players)
        )
    finally:
        await asyncio.gather(
            *(player.close() for player in players), return_exceptions=True
        )
    return [ms for player_latencies in per_player for ms in player_latencies]


async def _drive_script(
    player: VirtualPlayer, script: list[str], jitter_ms: int
) -> list[float]:
    """Run the script once, returning per-command round-trip latency in ms."""
    latencies: list[float] = []
    for command in script:
        if jitter_ms:
            await asyncio.sleep(random.uniform(0, jitter_ms) / 1000.0)
        start = time.perf_counter()
        await player.send_command(command)
        latencies.append((time.perf_counter() - start) * 1000.0)
    return latencies
