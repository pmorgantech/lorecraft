"""Python side of the cross-language `look` ScriptResult parity check (Rust-port
Phase 2).

This captures the deterministic input/output of the `look` pure-rule contract
boundary (`InventoryService._build_look_request` ->
`look_pure.look_effects(ScriptRequest) -> ScriptResult`) into two checked-in
fixtures under ``rust/fixtures/look_only/``:

- ``request.json`` — the serialized ``ScriptRequest`` the Rust
  ``lorecraft-feature-look`` crate reads as input.
- ``expected_result_hash.txt`` — the sha256 of the canonical-JSON
  ``ScriptResult``. The Rust crate reproduces the same `look` policy, hashes its
  own output with the ``lorecraft-replay`` port of ``replay_hash.canonical_json``,
  and asserts equality against this hex digest. That is the Phase 2 exit
  criterion (Rust reproduces the `look_only` ScriptResult hash in shadow mode).

This is deliberately **distinct** from ``tests/simulation/scenarios/
look_only.audit.json``, which is a DB audit-trail projection of the full command
pipeline (parser/dispatch/audit-writer/commit) and is the reserved *Phase 4*
target — reproducing it needs Rust to own the pipeline. This test neither
replaces nor touches that file; it hashes only the pure `look` ScriptResult.

Regenerate the fixtures (after an intentional `look` output change) with::

    LORECRAFT_UPDATE_RUST_FIXTURES=1 make test-simulation

mirroring the ``LORECRAFT_UPDATE_GOLDENS`` flag used by the audit-regression
goldens. The env flag only *rewrites* the fixtures; the hash-equality assertion
runs unconditionally and is the actual regression guard.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine

from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import build_game_context
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.inventory.look_pure import look_effects
from lorecraft.features.inventory.service import InventoryService
from lorecraft.protocol import ScriptRequest
from lorecraft.tools.replay_hash import canonical_json
from tests.simulation.conftest import SimulationServer

pytestmark = pytest.mark.simulation

# The scenario seed pinned by tests/simulation/scenarios/look_only.json, so the
# seeded world (and therefore the captured request/hash) is deterministic.
_RNG_SEED = 1

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "rust" / "fixtures" / "look_only"
_REQUEST_PATH = _FIXTURE_DIR / "request.json"
_HASH_PATH = _FIXTURE_DIR / "expected_result_hash.txt"

_ACTOR_ID = "player-1"


def _build_look_request(server: SimulationServer) -> ScriptRequest:
    """Materialize the `look` ScriptRequest for `player-1` in its starting room.

    Reuses the disposable simulation server (a fresh ``world_content/world.yaml``
    world seeded with ``rng_seed=1``, per-test sqlite files) rather than a second
    bootstrap path. A throwaway character is created through the normal
    player-creation route purely to *derive* the configured starting room id from
    world config — no room id is hardcoded here.
    """
    probe_id = server.create_player("look-parity-probe")
    engine = create_engine(f"sqlite:///{server.game_db_path}")
    with Session(engine) as session:
        room_repo = RoomRepo(session)
        probe = session.get(Player, probe_id)
        assert probe is not None, "probe character was not created"
        start_room_id = probe.current_room_id  # derived from world config
        room = room_repo.get(start_room_id)
        assert room is not None, f"starting room {start_room_id!r} not seeded"

        # A stable, non-persisted actor so the captured request.json is
        # deterministic across regenerations. `_build_look_request` reads only
        # `player.id`/`player.flags` off this object — a fresh player has no
        # discovery flags, so hidden exits stay hidden deterministically.
        player = Player(
            id=_ACTOR_ID,
            username=_ACTOR_ID,
            current_room_id=start_room_id,
            respawn_room_id=start_room_id,
        )
        ctx = build_game_context(
            session,
            player,
            room,
            bus=EventBus(),
            manager=ConnectionManager(),
            transaction=TransactionContext.create(
                actor_id=_ACTOR_ID, correlation_id="look-parity"
            ),
            session_id="look-parity",
            rng=GameRng(_RNG_SEED),
            meters=MeterService(session.get_bind(), GameRng(_RNG_SEED)),
            effects=EffectService(session.get_bind(), GameRng(_RNG_SEED)),
            clock=room_repo.world_clock(),
        )
        return InventoryService()._build_look_request(ctx)


def _result_hash(request: ScriptRequest) -> str:
    """sha256 hex of the canonical-JSON `look` ScriptResult for `request`.

    Reuses ``replay_hash.canonical_json`` (sorted keys, no whitespace, UTF-8,
    float-rejecting) so the byte-canonicalisation matches the Rust
    ``lorecraft-replay`` port exactly; `replay_hash` exposes no bytes-hashing
    helper, so the sha256 is applied here directly.
    """
    return hashlib.sha256(canonical_json(look_effects(request).to_json())).hexdigest()


def test_look_scriptresult_hash_matches_checked_in_fixture(
    simulation_server_factory: Callable[..., SimulationServer],
) -> None:
    server = simulation_server_factory(rng_seed=_RNG_SEED)
    request = _build_look_request(server)
    live_hash = _result_hash(request)

    if os.getenv("LORECRAFT_UPDATE_RUST_FIXTURES") == "1":
        _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        _REQUEST_PATH.write_text(
            json.dumps(request.to_json(), indent=2, ensure_ascii=False) + "\n"
        )
        _HASH_PATH.write_text(live_hash + "\n")

    assert _HASH_PATH.exists(), (
        "no checked-in look_only result hash — regenerate with "
        "LORECRAFT_UPDATE_RUST_FIXTURES=1 make test-simulation"
    )
    # The unconditional regression guard: the live ScriptResult hash must equal
    # the checked-in digest the Rust parity test also asserts against.
    assert live_hash == _HASH_PATH.read_text().strip()
