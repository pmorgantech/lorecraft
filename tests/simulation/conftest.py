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
from dataclasses import dataclass, field
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
from tests._rust_gateway import (
    RustGateway,
    ensure_gateway_binary,
    through_rust_enabled,
    unique_socket_path,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_STARTUP_TIMEOUT_SECONDS = 10.0


class _LiveServer:
    """Runs the real FastAPI app under uvicorn on a background thread."""

    def __init__(self, app: Any) -> None:
        # ws="websockets-sansio": avoid uvicorn's default legacy-websockets impl,
        # which websockets>=14 deprecates (see tests/e2e/conftest.py).
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            ws="websockets-sansio",
        )
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
    # True when `base_url` is the Rust gateway front door (ticket-only `/ws`);
    # False when it is the Python uvicorn origin directly (legacy `?player_id=`).
    through_rust: bool = False
    # The live FastAPI app instance (`_LiveServer` runs it on a background thread
    # in *this* process, not a subprocess), so a test can reach `app.state.lorecraft`
    # to drive the shared command pipeline (`handle_ws_command`) in-process against
    # the exact same game/audit DBs the wire path just wrote to — e.g. the Phase 4
    # look-parity harness's Python-direct oracle. `None` only if never wired (never
    # the case for `simulation_server_factory`-built servers).
    app: Any = None
    # Session cookies captured from each character's `/lobby/create` 303, keyed
    # by player id, so a later `POST /auth/ws-ticket` can authenticate as them.
    _session_cookies: dict[str, httpx.Cookies] = field(default_factory=dict)

    @property
    def ws_url(self) -> str:
        return "ws://" + self.base_url.removeprefix("http://")

    def create_player(self, username: str) -> str:
        """Create a character via the real `/lobby/create` route; return its id.

        Captures the `lorecraft_session` cookie set on the 303 redirect (relayed
        untouched through the Rust proxy in Rust-fronted mode) so `mint_ticket`
        can authenticate the follow-up `POST /auth/ws-ticket` as this character.
        """
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
            self._session_cookies[player.id] = response.cookies
            return player.id

    def mint_ticket(self, player_id: str) -> str:
        """Mint a single-use WS ticket via the proxied `POST /auth/ws-ticket`.

        Uses the session cookie captured by `create_player`, so the whole
        cookie -> ticket round-trip goes through the Rust front door — proving
        the ticket flow survives the reverse proxy before it is redeemed on the
        Rust `/ws` upgrade.
        """
        cookies = self._session_cookies.get(player_id)
        if cookies is None:
            raise RuntimeError(f"no session cookie captured for player {player_id}")
        response = httpx.post(f"{self.base_url}/auth/ws-ticket", cookies=cookies)
        response.raise_for_status()
        return response.json()["ws_ticket"]

    def prepare_login(self, username: str) -> tuple[str, str | None]:
        """Create a character and return `(player_id, ticket)` for a WS connect.

        In Rust-fronted mode the ticket is a real single-use ws-ticket (the Rust
        `/ws` accepts only `?ticket=`); in Python-direct mode it is `None` and
        the caller connects with the legacy `?player_id=` path. Callers pass the
        ticket straight to `VirtualPlayer.connect(..., ticket=ticket)`, which
        selects the transport accordingly — one call site for both modes.
        """
        player_id = self.create_player(username)
        ticket = self.mint_ticket(player_id) if self.through_rust else None
        return player_id, ticket

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
) -> Iterator[Callable[..., SimulationServer]]:
    """Boot fresh, disposable, real live servers on demand.

    Yields a factory instead of a single server so tests that need more than
    one independent server (e.g. audit-log regression: same script, two
    separate fresh worlds) don't have to duplicate the boot sequence. Every
    server created by a call is stopped at teardown.

    Each server is either Python-direct (uvicorn only) or Rust-fronted (a
    `lorecraft-gateway` subprocess in front of the Python app). The default is
    taken from `LORECRAFT_THROUGH_RUST`, overridable per call with the
    `through_rust=` keyword (the dedicated Rust-only tests force it True).
    """
    live_servers: list[_LiveServer] = []
    gateways: list[RustGateway] = []
    socket_paths: list[str] = []

    def _make(
        rng_seed: int | None = None,
        *,
        through_rust: bool | None = None,
        extra_env: dict[str, str] | None = None,
        world_time_ratio: float | None = None,
    ) -> SimulationServer:
        """Boot one fresh server.

        `extra_env` is forwarded verbatim to the `RustGateway` subprocess (no
        effect in Python-direct mode) — e.g. `{"LORECRAFT_RUST_VERBS": "look"}`
        to opt a single test into routing a migrated verb through Rust's
        execution path without touching the default (empty allow-list) fixture.
        `world_time_ratio` overrides `Settings`' default real-time clock advance
        (60.0) — pass `0.0` to freeze the world clock for a byte-identity compare
        that must not race an in-test tick (e.g. the Phase 4 parity harness);
        left `None`, most simulation tests want the clock actually advancing.
        """
        if through_rust is None:
            through_rust = through_rust_enabled()
        db_dir = tmp_path_factory.mktemp("sim")
        game_db_path = db_dir / "sim-game.db"
        audit_db_path = db_dir / "sim-audit.db"
        socket_path = unique_socket_path() if through_rust else None
        settings = Settings(
            database_path=str(game_db_path),
            audit_database_path=str(audit_db_path),
            world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml"),
            # Scenario replay (Sprint 43) pins this to the scenario's recorded
            # seed so golden audit diffs stay deterministic.
            rng_seed=rng_seed,
            seed_player_id="",
            seed_player_username="",
            # Python-direct: VirtualPlayer connects with ?player_id= to exercise
            # the raw wire protocol (see virtual_player.py's docstring), so the
            # legacy fallback is enabled. Rust-fronted: the gateway `/ws` is
            # ticket-only, so keep the fallback OFF and exercise the real ticket
            # path (create -> cookie -> /auth/ws-ticket -> ?ticket=).
            allow_query_player_id=not through_rust,
            gateway_enabled=through_rust,
            gateway_socket_path=socket_path or "var/gateway.sock",
            **(
                {"world_time_ratio": world_time_ratio}
                if world_time_ratio is not None
                else {}
            ),
        )
        app = create_app(settings=settings)
        live_server = _LiveServer(app)
        live_server.start()
        live_servers.append(live_server)

        base_url = live_server.base_url
        if through_rust:
            assert socket_path is not None  # set whenever through_rust
            ensure_gateway_binary()
            gateway = RustGateway(
                backend_url=live_server.base_url,
                socket_path=socket_path,
                extra_env=extra_env,
            )
            gateway.start()
            gateways.append(gateway)
            socket_paths.append(socket_path)
            base_url = gateway.base_url

        return SimulationServer(
            base_url=base_url,
            game_db_path=game_db_path,
            audit_db_path=audit_db_path,
            through_rust=through_rust,
            app=app,
        )

    try:
        yield _make
    finally:
        for gateway in gateways:
            gateway.stop()
        for live_server in live_servers:
            live_server.stop()
        for socket_path in socket_paths:
            Path(socket_path).unlink(missing_ok=True)


@pytest.fixture
def simulation_server(
    simulation_server_factory: Callable[..., SimulationServer],
) -> SimulationServer:
    """A single fresh, disposable, real live server — the common case.

    Python-direct by default; Rust-fronted when `LORECRAFT_THROUGH_RUST` is set
    (the three named exit tests consume this fixture unchanged, so the same test
    bodies run against either front door).
    """
    return simulation_server_factory()


@pytest.fixture
def rust_gateway_server(
    simulation_server_factory: Callable[..., SimulationServer],
) -> SimulationServer:
    """A Rust-fronted live server, forced on regardless of the env flag.

    For tests that specifically exercise the Rust gateway itself (e.g. the
    bad-ticket -> 1008 auth rejection), so they run the Rust path even in an
    otherwise Python-direct suite. Requires a buildable `lorecraft-gateway`.
    """
    return simulation_server_factory(through_rust=True)
