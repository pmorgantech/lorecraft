"""Fixtures for the simulation harness (Sprint 12).

Complements `tests/e2e/` (a real browser against a real server) and the
ASGI-transport integration tests (no socket, no HTML/JS) with a third
transport: real WebSocket clients (`tests/simulation/virtual_player.py`)
against a real, live `uvicorn` server. This is the layer that can run N
players concurrently to exercise room broadcast fan-out and contention over
shared world state.

Uses the real `world_content/world.yaml` (no synthetic test-only world
content, per AGENTS.md) with a disposable per-test sqlite DB, same as
`tests/e2e/conftest.py`.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from sqlmodel import Session, col, create_engine, select

from lorecraft.config import Settings
from lorecraft.main import create_app
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.player import Player
from lorecraft.engine.repos.stack_repo import StackRepo

REPO_ROOT = Path(__file__).resolve().parents[2]
_STARTUP_TIMEOUT_SECONDS = 10.0


class _LiveServer:
    """Runs the real FastAPI app under uvicorn on a background thread."""

    def __init__(self, app: Any) -> None:
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("live simulation server did not start in time")
            time.sleep(0.01)

    @property
    def base_url(self) -> str:
        port = self._server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)


@dataclass
class SimulationServer:
    """A live server plus direct DB access for setup/assertions.

    The game and audit DBs are disposable sqlite *files* (not `:memory:`), so
    the test process can open its own read-only-in-practice `Session` against
    them to create characters without going through the browser lobby UI, and
    to inspect final state (inventory, audit trail) once a scenario finishes.
    """

    base_url: str
    game_db_path: Path
    audit_db_path: Path

    @property
    def ws_url(self) -> str:
        return "ws://" + self.base_url.removeprefix("http://")

    def create_player(self, username: str) -> str:
        """Create a character via the real `/lobby/create` route; return its id."""
        # /lobby/create requires a matching `password_confirm` and enforces the
        # default PasswordPolicy (mixed case + a digit), so send both fields with
        # a policy-compliant password — otherwise it 400s. (Throwaway per-test
        # sqlite credential, not a real secret.)
        password = "Simulation-Test-1"  # gitleaks:allow
        response = httpx.post(
            f"{self.base_url}/lobby/create",
            data={
                "username": username,
                "password": password,
                "password_confirm": password,
            },
            follow_redirects=False,
        )
        if response.status_code != 303:
            response.raise_for_status()
        engine = create_engine(f"sqlite:///{self.game_db_path}")
        with Session(engine) as session:
            player = session.exec(
                select(Player).where(Player.username == username)
            ).one()
            return player.id

    def audit_trail_for(self, actor_id: str) -> list[AuditEvent]:
        """Chronological audit events recorded for one actor."""
        engine = create_engine(f"sqlite:///{self.audit_db_path}")
        with Session(engine) as session:
            events = session.exec(
                select(AuditEvent)
                .where(AuditEvent.actor_id == actor_id)
                .order_by(col(AuditEvent.real_time))
            ).all()
            return list(events)

    def player_inventory(self, player_id: str) -> list[str]:
        """Flat, quantity-expanded list of carried item ids (stack creation order)."""
        engine = create_engine(f"sqlite:///{self.game_db_path}")
        with Session(engine) as session:
            player = session.get(Player, player_id)
            assert player is not None
            ids: list[str] = []
            for stack in StackRepo(session).stacks_for_owner("player", player_id):
                ids.extend([stack.item_id] * stack.quantity)
            return ids


@pytest.fixture
def simulation_server_factory(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[Callable[[], SimulationServer]]:
    """Boot fresh, disposable, real live servers on demand.

    Yields a factory instead of a single server so tests that need more than
    one independent server (e.g. audit-log regression: same script, two
    separate fresh worlds) don't have to duplicate the boot sequence. Every
    server created by a call is stopped at teardown.
    """
    live_servers: list[_LiveServer] = []

    def _make() -> SimulationServer:
        db_dir = tmp_path_factory.mktemp("sim")
        game_db_path = db_dir / "sim-game.db"
        audit_db_path = db_dir / "sim-audit.db"
        settings = Settings(
            database_path=str(game_db_path),
            audit_database_path=str(audit_db_path),
            world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
            seed_player_id="",
            seed_player_username="",
            # VirtualPlayer connects directly with ?player_id= to exercise
            # the raw wire protocol (see virtual_player.py's docstring) —
            # not the login UI, so it needs the legacy fallback explicitly
            # (off by default since Sprint 4; see docs/roadmap.md 4.6).
            allow_query_player_id=True,
        )
        app = create_app(settings=settings)
        live_server = _LiveServer(app)
        live_server.start()
        live_servers.append(live_server)
        return SimulationServer(
            base_url=live_server.base_url,
            game_db_path=game_db_path,
            audit_db_path=audit_db_path,
        )

    try:
        yield _make
    finally:
        for live_server in live_servers:
            live_server.stop()


@pytest.fixture
def simulation_server(
    simulation_server_factory: Callable[[], SimulationServer],
) -> SimulationServer:
    """A single fresh, disposable, real live server — the common case."""
    return simulation_server_factory()
