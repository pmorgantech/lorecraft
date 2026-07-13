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
from dataclasses import replace
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
from lorecraft.engine.models.session import PlayerSession
from lorecraft.protocol.gateway import (
    ApplyOutcome,
    BuildSnapshot,
    ExecutionRejected,
    OutcomeApplied,
    RoomTarget,
    SnapshotReady,
)
from lorecraft.state import AppState
from lorecraft.types import JsonObject
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


def _drain_admin_audit_pushes(
    queue: "asyncio.Queue[JsonObject]",
) -> list[JsonObject]:
    """Collect the `audit_appended` admin-feed pushes buffered on `queue`."""
    pushes: list[JsonObject] = []
    while not queue.empty():
        message = queue.get_nowait()
        if message.get("type") == "audit_appended":
            pushes.append(message)
    return pushes


def test_apply_outcome_fires_admin_audit_appended_broadcast(state: AppState) -> None:
    """PARITY (the gap the 4a harness missed): persisting a Rust-executed `look`
    emits `COMMAND_EXECUTED` on the bus, so `main.py`'s `_push_command_executed`
    observer pushes an `audit_appended` admin-feed broadcast — identical to what
    the pure-Python command path (`handle_ws_command` -> `CommandEngine`) produces.

    Pre-fix behavior: `apply_outcome` recorded the audit ROW but never emitted the
    bus event, so no observer fired and an admin watching the live audit tab missed
    every Rust-executed command. The baseline compare below is the exact side
    effect that was silently absent.
    """
    _warm_up_look(state)

    # Baseline: the pure-Python path's admin audit-feed push for the same `look`.
    baseline_queue: asyncio.Queue[JsonObject] = asyncio.Queue()
    state.admin_broadcaster.add(baseline_queue)
    asyncio.run(
        handle_ws_command(
            state, DirectiveConnectionManager(), PLAYER_ID, "admin-base", "look"
        )
    )
    state.admin_broadcaster.remove(baseline_queue)
    baseline = _drain_admin_audit_pushes(baseline_queue)

    # Rust path: apply_outcome must fire the identical admin push.
    rust_queue: asyncio.Queue[JsonObject] = asyncio.Queue()
    state.admin_broadcaster.add(rust_queue)
    outcome = _look_outcome(state, "c-admin")
    asyncio.run(apply_outcome(state, _envelope("admin-rust", "c-admin"), outcome))
    state.admin_broadcaster.remove(rust_queue)
    rust = _drain_admin_audit_pushes(rust_queue)

    # Exactly one audit-feed push, carrying the right actor/summary/room, and
    # byte-identical to the Python path's (the payload has no session-scoped field).
    assert len(baseline) == 1
    assert len(rust) == 1
    push = rust[0]
    assert push["actor_id"] == PLAYER_ID
    assert push["room_id"] == state.settings.seed_player_start_room
    assert push["summary"]
    assert rust == baseline


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


# --- 4b hardening: short-circuit (frozen guard + handler-failure error) -------


def _freeze_session(state: AppState, session_id: str) -> None:
    """Insert a `frozen` player session so the frozen-guard path can be exercised.

    Mirrors what an admin freeze produces: a `PlayerSession` row for the seeded
    player whose `status` is `frozen` — the exact state `handle_ws_command`'s guard
    (`player_session(session_id).status == "frozen"`) rejects on.
    """
    with Session(state.game_engine) as game_session:
        game_session.add(
            PlayerSession(
                id=session_id,
                player_id=PLAYER_ID,
                connected_at=0.0,
                status="frozen",
            )
        )
        game_session.commit()


def _count_command_audit_rows(state: AppState) -> int:
    with Session(state.audit_engine) as audit:
        return sum(
            1
            for e in audit.exec(select(AuditEvent)).all()
            if e.event_type == "command_executed"
        )


def test_build_snapshot_rejects_frozen_session_without_executing(
    state: AppState, adapter: GatewayAdapter
) -> None:
    """FINDING #2: a frozen player's `look` is short-circuited at `BuildSnapshot`
    with the exact frozen `system` message — NO snapshot is built, NOTHING is
    pended for an `ApplyOutcome`, and NO audit row is written (parity with
    `handle_ws_command`'s pre-execution frozen guard).

    Pre-fix behavior (confirmed by reading the replaced `_on_build_snapshot`,
    which returned a `SnapshotReady` unconditionally): a frozen session's
    `BuildSnapshot` produced a `SnapshotReady`, so Rust would have gone on to
    execute/apply/audit/broadcast the look — this assertion (`ExecutionRejected`)
    would have failed against that code.
    """
    _warm_up_look(state)
    audit_before = _count_command_audit_rows(state)
    _freeze_session(state, "frozen-sess")

    envelope = _envelope("frozen-sess", "cmd-frozen")
    (frame,) = asyncio.run(adapter.handle_inbound(BuildSnapshot(envelope=envelope)))

    assert isinstance(frame, ExecutionRejected)
    assert frame.command_id == "cmd-frozen"
    assert frame.direct_reply == {
        "type": "system",
        "text": "Your session is frozen. Contact an administrator.",
    }
    # No execution context was created for this command...
    assert "cmd-frozen" not in adapter._pending  # pyright: ignore[reportPrivateUsage]
    # ...and nothing was audited (no execute/apply happened).
    assert _count_command_audit_rows(state) == audit_before


def test_build_snapshot_handler_failure_returns_error_not_raises(
    state: AppState, adapter: GatewayAdapter
) -> None:
    """FINDING #1: a `build_look_request` failure (here, a vanished player) is
    caught and degraded to a client-facing in-game `error` reply carried on an
    `ExecutionRejected` frame — NOT allowed to escape the handler (which pre-fix
    would drop the reply at the dispatch catch-all and hang the Rust driver).

    Pre-fix behavior (confirmed by reading the replaced `_on_build_snapshot`,
    which called `build_look_request` with no guard): the `ValidationError` for an
    unknown player propagated out of `handle_inbound` — under the real
    `_handle_client` loop it was logged and `continue`d with no reply frame, the
    exact indefinite-hang source. Post-fix it is a bounded `ExecutionRejected`.
    """
    envelope = _envelope("missing-sess", "cmd-missing")
    # An unknown player id makes `build_look_request` raise ValidationError.
    envelope = replace(envelope, player_id="does-not-exist", actor_id="does-not-exist")

    (frame,) = asyncio.run(adapter.handle_inbound(BuildSnapshot(envelope=envelope)))

    assert isinstance(frame, ExecutionRejected)
    assert frame.command_id == "cmd-missing"
    assert isinstance(frame.direct_reply, dict)
    assert frame.direct_reply["type"] == "error"
    # Nothing pended: no ApplyOutcome will follow a rejected build.
    assert "cmd-missing" not in adapter._pending  # pyright: ignore[reportPrivateUsage]


def test_apply_outcome_unknown_command_returns_error_not_raises(
    state: AppState, adapter: GatewayAdapter
) -> None:
    """FINDING #1: an `ApplyOutcome` for a `command_id` with no pending envelope is
    caught and degraded to an `ExecutionRejected` error reply — never raised (which
    pre-fix escaped to the dispatch catch-all and dropped the reply, hanging Rust
    awaiting `OutcomeApplied`).

    Pre-fix behavior (confirmed by reading the replaced `_on_apply_outcome`, which
    raised `ValidationError` for an unknown `command_id`): the exception propagated
    out of `handle_inbound`; under `_handle_client` it was logged and `continue`d
    with no reply, the hang source. Post-fix it is a bounded `ExecutionRejected`.
    """
    outcome = _look_outcome(state, "never-pended")

    (frame,) = asyncio.run(
        adapter.handle_inbound(ApplyOutcome(command_id="never-pended", outcome=outcome))
    )

    assert isinstance(frame, ExecutionRejected)
    assert frame.command_id == "never-pended"
    assert isinstance(frame.direct_reply, dict)
    assert frame.direct_reply["type"] == "error"
