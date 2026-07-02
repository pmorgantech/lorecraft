"""Unit tests for Here Now presence helpers."""

from __future__ import annotations

from lorecraft.web.session import format_idle_duration, presence_for_player


class _FakeManager:
    def __init__(self, connected: set[str]) -> None:
        self._connected = connected

    def is_connected(self, player_id: str) -> bool:
        return player_id in self._connected


class _FakeSession:
    def __init__(
        self,
        *,
        status: str = "active",
        disconnected_at: float | None = None,
    ) -> None:
        self.status = status
        self.disconnected_at = disconnected_at


class _FakePlayerRepo:
    def __init__(self, session: _FakeSession | None) -> None:
        self._session = session

    def latest_session(self, player_id: str) -> _FakeSession | None:
        del player_id
        return self._session


def test_format_idle_duration_compact() -> None:
    assert format_idle_duration(30) == "Away"
    assert format_idle_duration(125) == "Idle 2m"
    assert format_idle_duration(7440) == "Idle 2h4m"
    assert format_idle_duration(7200) == "Idle 2h"


def test_presence_online_when_ws_connected() -> None:
    presence = presence_for_player(
        "player-1",
        manager=_FakeManager({"player-1"}),
        player_repo=_FakePlayerRepo(None),
    )
    assert presence["presence"] == "online"
    assert presence["is_online"] is True


def test_presence_grace_when_session_in_grace() -> None:
    presence = presence_for_player(
        "player-1",
        manager=_FakeManager(set()),
        player_repo=_FakePlayerRepo(_FakeSession(status="grace")),
    )
    assert presence["presence"] == "grace"
    assert presence["status_label"] == "Reconnecting…"


def test_presence_idle_after_disconnect() -> None:
    presence = presence_for_player(
        "player-1",
        manager=_FakeManager(set()),
        player_repo=_FakePlayerRepo(
            _FakeSession(status="expired", disconnected_at=1_000.0)
        ),
        now=1_000.0 + 7440,
    )
    assert presence["presence"] == "away"
    assert presence["status_label"] == "Idle 2h4m"
