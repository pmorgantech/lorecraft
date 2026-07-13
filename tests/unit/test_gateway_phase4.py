"""Phase 4 execution round-trip (Option A): the Python persistence handlers.

Rust owns execution; Python owns persistence. These tests anchor the two Python
halves of the round-trip for the read-only `look` slice:

- `build_look_request` (the `BuildSnapshot` half) produces the same `ScriptRequest`
  the live look path builds — asserted against the canonical Phase 2 fixture.
- `apply_outcome` (the `ApplyOutcome` half) persists a look outcome and returns a
  `direct_reply` byte-identical to `handle_ws_command`'s `command_result`, writes
  a `command_executed` audit row matching `look_only.audit.json`'s shape, and
  returns the single room `state_change` delivery.

Reuses the `state`/adapter fixtures + seeded world from `test_gateway_adapter.py`
(`create_app` + `TestClient` lifespan) — no invented world content.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from lorecraft.config import Settings
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.features.inventory.look_pure import look_effects
from lorecraft.gateway.adapter import GatewayAdapter
from lorecraft.gateway.connection_manager import DirectiveConnectionManager
from lorecraft.gateway.effect_apply import apply_outcome
from lorecraft.gateway.snapshots import build_look_request
from lorecraft.main import create_app
from lorecraft.protocol import PROTOCOL_VERSION
from lorecraft.protocol.envelope import CommandEnvelope, CommandOutcome, OutcomeStatus
from lorecraft.protocol.gateway import (
    ApplyOutcome,
    BuildSnapshot,
    OutcomeApplied,
    RoomTarget,
    SnapshotReady,
)
from lorecraft.state import AppState
from lorecraft.webui.player.ws_command import handle_ws_command

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "rust" / "fixtures" / "look_only"
AUDIT_FIXTURE = (
    REPO_ROOT / "tests" / "simulation" / "scenarios" / "look_only.audit.json"
)
PLAYER_ID = "player-1"


def _base_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=str(tmp_path / "game.db"),
        audit_database_path=str(tmp_path / "audit.db"),
        world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
        issues_yaml_path=str(tmp_path / "issues.yaml"),
        news_yaml_path=str(tmp_path / "news.yaml"),
        help_yaml_path=str(tmp_path / "help_topics.yaml"),
        admin_jwt_secret="test-admin-secret-at-least-32-bytes!!",
        seed_player_id=PLAYER_ID,
        seed_player_username=PLAYER_ID,
        # Freeze the clock so the `time` snapshot in `updates` is deterministic
        # between the baseline and apply_outcome runs (ratio 0 => no advance).
        world_time_ratio=0.0,
        gateway_socket_path=str(tmp_path / "lifespan-gateway.sock"),
    )


@pytest.fixture
def state(tmp_path: Path) -> Iterator[AppState]:
    app = create_app(settings=_base_settings(tmp_path))
    with TestClient(app):
        yield app.state.lorecraft


@pytest.fixture
def adapter(state: AppState, tmp_path: Path) -> GatewayAdapter:
    return GatewayAdapter(state, socket_path=str(tmp_path / "gateway.sock"))


def _envelope(session_id: str, command_id: str, raw: str = "look") -> CommandEnvelope:
    return CommandEnvelope(
        protocol_version=PROTOCOL_VERSION,
        world_id="world",
        actor_id=PLAYER_ID,
        player_id=PLAYER_ID,
        session_id=session_id,
        command_id=command_id,
        receive_sequence=1,
        deadline_ms=1000,
        raw=raw,
    )


def _look_outcome(state: AppState, command_id: str) -> CommandOutcome:
    """A synthetic look outcome: the pure `look_effects` messages Rust ports,
    with no effects (look is read-only)."""
    request = build_look_request(state, _envelope("snap", command_id))
    result = look_effects(request)
    return CommandOutcome(
        command_id=command_id,
        status=OutcomeStatus.EXECUTED,
        messages=list(result.messages),
        applied_effects=[],
    )


def _warm_up_look(state: AppState) -> None:
    """Settle first-look state mutations (visited/discovered/met) so subsequent
    looks are idempotent — the parity compare is then deterministic."""
    asyncio.run(
        handle_ws_command(
            state, DirectiveConnectionManager(), PLAYER_ID, "warmup", "look"
        )
    )


# --- BuildSnapshot half ------------------------------------------------------


def test_build_look_request_matches_canonical_fixture(state: AppState) -> None:
    """The snapshot built for the seed player equals the Phase 2 canonical
    `request.json` — proof the reused `_build_look_request` didn't drift."""
    request = build_look_request(state, _envelope("s", "c"))
    expected = json.loads((FIXTURE_DIR / "request.json").read_text())
    assert request.to_json() == expected


def test_on_build_snapshot_returns_snapshot_ready(
    state: AppState, adapter: GatewayAdapter
) -> None:
    envelope = _envelope("s", "c-build")
    (frame,) = asyncio.run(adapter.handle_inbound(BuildSnapshot(envelope=envelope)))
    assert isinstance(frame, SnapshotReady)
    assert frame.command_id == "c-build"
    # The envelope is now pending, awaiting the correlated ApplyOutcome.
    assert adapter._pending[envelope.command_id] is envelope  # pyright: ignore[reportPrivateUsage]


# --- ApplyOutcome half (the parity anchor) -----------------------------------


def test_apply_outcome_direct_reply_matches_handle_ws_command(state: AppState) -> None:
    _warm_up_look(state)
    expected = asyncio.run(
        handle_ws_command(state, DirectiveConnectionManager(), PLAYER_ID, "s1", "look")
    )
    outcome = _look_outcome(state, "c1")
    direct_reply, _deliveries = asyncio.run(
        apply_outcome(state, _envelope("s1", "c1"), outcome)
    )
    assert direct_reply["type"] == "command_result"
    assert direct_reply == expected


def test_apply_outcome_returns_single_state_change_delivery(state: AppState) -> None:
    _warm_up_look(state)
    outcome = _look_outcome(state, "c2")
    _direct_reply, deliveries = asyncio.run(
        apply_outcome(state, _envelope("s2", "c2"), outcome)
    )
    (directive,) = deliveries
    assert isinstance(directive.target, RoomTarget)
    assert directive.target.id == state.settings.seed_player_start_room
    assert directive.exclude == PLAYER_ID
    assert isinstance(directive.payload, dict)
    assert directive.payload["type"] == "state_change"
    panels = directive.payload["affected_panels"]
    assert isinstance(panels, list)
    assert "players-online" in panels
    # Idempotent panel-refresh directives are coalesce-keyed (Tier 2 policy).
    assert directive.coalesce_key is not None


def test_apply_outcome_writes_command_executed_audit(state: AppState) -> None:
    _warm_up_look(state)
    outcome = _look_outcome(state, "c3")
    asyncio.run(apply_outcome(state, _envelope("audit-sess", "c3"), outcome))

    with Session(state.audit_engine) as audit:
        rows = [
            e
            for e in audit.exec(select(AuditEvent)).all()
            if e.correlation_id == "audit-sess"
        ]
    (row,) = rows
    projected = {
        "event_type": row.event_type,
        "summary": row.summary,
        "target_id": row.target_id,
        "room_id": row.room_id,
        "severity": row.severity,
    }
    expected = json.loads(AUDIT_FIXTURE.read_text())[0]
    assert projected == expected


# --- full round-trip through the adapter -------------------------------------


def test_build_then_apply_round_trip_through_adapter(
    state: AppState, adapter: GatewayAdapter
) -> None:
    """BuildSnapshot -> SnapshotReady -> (Rust executes) -> ApplyOutcome ->
    OutcomeApplied, with the pending envelope recovered by command_id."""
    _warm_up_look(state)
    envelope = _envelope("rt-sess", "rt")
    (ready,) = asyncio.run(adapter.handle_inbound(BuildSnapshot(envelope=envelope)))
    assert isinstance(ready, SnapshotReady)

    # Rust would execute `ready.request`; we stand in with the pure look output.
    result = look_effects(ready.request)
    outcome = CommandOutcome(
        command_id="rt",
        status=OutcomeStatus.EXECUTED,
        messages=list(result.messages),
        applied_effects=[],
    )
    (applied,) = asyncio.run(
        adapter.handle_inbound(ApplyOutcome(command_id="rt", outcome=outcome))
    )
    assert isinstance(applied, OutcomeApplied)
    assert applied.command_id == "rt"
    assert isinstance(applied.direct_reply, dict)
    assert applied.direct_reply["type"] == "command_result"
    assert len(applied.deliveries) == 1
    # The pending entry is cleaned up on ApplyOutcome.
    assert "rt" not in adapter._pending  # pyright: ignore[reportPrivateUsage]
