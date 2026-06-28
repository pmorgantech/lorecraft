"""Lorecraft admin TUI — Textual application with F1-F5 screen routing."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import Screen
    from textual.widgets import (
        Button,
        DataTable,
        Footer,
        Header,
        Input,
        Label,
        RichLog,
        Static,
    )
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Admin TUI requires the 'admin-tui' extras: pip install 'lorecraft[admin-tui]'"
    ) from exc

_CRED_PATH = Path.home() / ".config" / "lorecraft-admin" / "credentials.json"


# ---------------------------------------------------------------------------
# Credential helpers
# ---------------------------------------------------------------------------


def _load_creds() -> dict[str, str]:
    if _CRED_PATH.exists():
        return json.loads(_CRED_PATH.read_text())
    return {}


def _save_creds(data: dict[str, str]) -> None:
    _CRED_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CRED_PATH.write_text(json.dumps(data))
    _CRED_PATH.chmod(0o600)


# ---------------------------------------------------------------------------
# HTTP helper (stdlib, no extra deps)
# ---------------------------------------------------------------------------


class _Api:
    def __init__(self, base_url: str, access_token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token

    def _request(
        self,
        method: str,
        path: str,
        body: Any = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return {"error": exc.reason, "status": exc.code}
        except Exception as exc:
            return {"error": str(exc)}

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self._request("POST", path, body)

    def login(self, username: str, password: str) -> str | None:
        resp = self.post(
            "/admin/auth/token", {"username": username, "password": password}
        )
        token = resp.get("access_token")
        if token:
            self.access_token = token
        return token


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------


class LoginScreen(Screen[None]):
    TITLE = "Login"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="login-box"):
            yield Label("Lorecraft Admin — Login", id="login-title")
            yield Input(placeholder="Base URL (e.g. http://localhost:8000)", id="url")
            yield Input(placeholder="Username", id="username")
            yield Input(placeholder="Password", password=True, id="password")
            yield Button("Login", variant="primary", id="login-btn")
            yield Label("", id="login-error")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "login-btn":
            self._do_login()

    def _do_login(self) -> None:
        url = self.query_one("#url", Input).value.strip()
        username = self.query_one("#username", Input).value.strip()
        password = self.query_one("#password", Input).value
        if not url or not username or not password:
            self.query_one("#login-error", Label).update("All fields required.")
            return
        api = _Api(url)
        token = api.login(username, password)
        if not token:
            self.query_one("#login-error", Label).update("Login failed.")
            return
        _save_creds({"base_url": url, "access_token": token, "username": username})
        self.app.api = api  # type: ignore[attr-defined]
        self.app.push_screen("players")


class PlayersScreen(Screen[None]):
    TITLE = "Players (F1)"
    BINDINGS = [
        Binding("t", "teleport", "Teleport"),
        Binding("f", "freeze", "Freeze"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="players-table")
        yield Static("t=teleport  f=freeze  r=refresh", id="players-hint")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("ID", "Username", "Room", "Online", "Inv")
        self.action_refresh()

    def action_refresh(self) -> None:
        self.run_worker(self._load_players, exclusive=True, thread=True)

    def _load_players(self) -> None:
        api: _Api = self.app.api  # type: ignore[attr-defined]
        players = api.get("/admin/players")
        if not isinstance(players, list):
            return
        table = self.query_one(DataTable)
        table.clear()
        for p in players:
            table.add_row(
                p.get("id", "")[:8],
                p.get("username", ""),
                p.get("current_room_id", ""),
                "✓" if p.get("online") else "✗",
                str(p.get("inventory_count", 0)),
                key=p.get("id", ""),
            )

    def action_freeze(self) -> None:
        table = self.query_one(DataTable)
        if table.cursor_row < 0:
            return
        row_key = table.get_row_at(table.cursor_row)
        player_id = str(row_key[0])  # first column is truncated ID
        # For a real freeze we'd need the full ID; this is a UX placeholder
        self.notify(f"Freeze not yet wired for row — select by ID: {player_id}")

    def action_teleport(self) -> None:
        self.notify(
            "Teleport: use the web panel for now (requires full player ID + room ID)"
        )


class AuditScreen(Screen[None]):
    TITLE = "Audit (F2)"
    BINDINGS = [Binding("r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="audit-filters"):
            yield Input(placeholder="actor", id="filter-actor")
            yield Input(placeholder="room", id="filter-room")
            yield Input(placeholder="event_type", id="filter-type")
            yield Button("Search", id="audit-search")
        yield RichLog(id="audit-log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()

    def action_refresh(self) -> None:
        self.run_worker(self._load_audit, exclusive=True, thread=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "audit-search":
            self.action_refresh()

    def _load_audit(self) -> None:
        api: _Api = self.app.api  # type: ignore[attr-defined]
        actor = self.query_one("#filter-actor", Input).value.strip() or None
        room = self.query_one("#filter-room", Input).value.strip() or None
        etype = self.query_one("#filter-type", Input).value.strip() or None
        params: list[str] = []
        if actor:
            params.append(f"actor={urllib.parse.quote(actor)}")
        if room:
            params.append(f"room={urllib.parse.quote(room)}")
        if etype:
            params.append(f"event_type={urllib.parse.quote(etype)}")
        qs = "?" + "&".join(params) if params else ""
        events = api.get(f"/admin/audit{qs}")
        log_widget = self.query_one(RichLog)
        log_widget.clear()
        if not isinstance(events, list):
            log_widget.write(f"[red]Error: {events}[/red]")
            return
        for e in events[:200]:
            ts = time.strftime("%H:%M:%S", time.localtime(e.get("real_time", 0)))
            color = (
                "red"
                if e.get("severity") == "ERROR"
                else "yellow"
                if e.get("severity") == "WARNING"
                else "green"
            )
            log_widget.write(
                f"[dim]{ts}[/dim] [{color}]{e.get('event_type', '')}[/{color}] "
                f"[cyan]{e.get('actor_id', '')}[/cyan] "
                f"[white]{e.get('summary', '')}[/white]"
            )


class WorldScreen(Screen[None]):
    TITLE = "World (F3)"
    BINDINGS = [Binding("r", "refresh", "Refresh")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield DataTable(id="rooms-table")
            with Vertical(id="room-editor"):
                yield Label("Select a room to edit", id="room-editor-title")
                yield Input(placeholder="Name", id="edit-name")
                yield Input(placeholder="Description", id="edit-desc")
                yield Input(placeholder="Light level (0-1)", id="edit-light")
                yield Button("Save (Ctrl+S)", id="save-room", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("ID", "Name", "Active", "x", "y")
        self.action_refresh()

    def action_refresh(self) -> None:
        self.run_worker(self._load_rooms, exclusive=True, thread=True)

    def _load_rooms(self) -> None:
        api: _Api = self.app.api  # type: ignore[attr-defined]
        rooms = api.get("/admin/world/rooms")
        if not isinstance(rooms, list):
            return
        table = self.query_one(DataTable)
        table.clear()
        for r in rooms:
            table.add_row(
                r.get("id", ""),
                r.get("name", ""),
                "✓" if r.get("is_active") else "✗",
                str(r.get("map_x", 0)),
                str(r.get("map_y", 0)),
                key=r.get("id", ""),
            )
        self.app._rooms_cache = rooms  # type: ignore[attr-defined]

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        rooms = getattr(self.app, "_rooms_cache", [])
        room = next((r for r in rooms if r.get("id") == event.row_key.value), None)
        if room is None:
            return
        self.query_one("#room-editor-title", Label).update(f"Editing: {room['id']}")
        self.query_one("#edit-name", Input).value = room.get("name", "")
        self.query_one("#edit-desc", Input).value = room.get("description", "")
        self.query_one("#edit-light", Input).value = str(room.get("light_level", 1))
        self.query_one("#save-room", Button).disabled = False
        self.app._editing_room = room  # type: ignore[attr-defined]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-room":
            self.run_worker(self._save_room, exclusive=True, thread=True)

    def _save_room(self) -> None:
        room = getattr(self.app, "_editing_room", None)
        if room is None:
            return
        api: _Api = self.app.api  # type: ignore[attr-defined]
        body = {
            "name": self.query_one("#edit-name", Input).value,
            "description": self.query_one("#edit-desc", Input).value,
            "light_level": int(self.query_one("#edit-light", Input).value or "1"),
            "version": room.get("version", 1),
        }
        result = api._request("PUT", f"/admin/world/rooms/{room['id']}", body)
        if "error" in result:
            self.notify(f"Save failed: {result['error']}", severity="error")
        else:
            self.notify(f"Saved {room['id']}")
            self.action_refresh()


class ChangesetsScreen(Screen[None]):
    TITLE = "Changesets (F4)"
    BINDINGS = [
        Binding("n", "new_changeset", "New"),
        Binding("s", "scan", "Scan"),
        Binding("p", "promote", "Promote"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="cs-table")
        yield RichLog(id="cs-log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("ID", "Name", "Status", "Created by", "Version")
        self.action_refresh()

    def action_refresh(self) -> None:
        self.run_worker(self._load_changesets, exclusive=True, thread=True)

    def _load_changesets(self) -> None:
        api: _Api = self.app.api  # type: ignore[attr-defined]
        cs_list = api.get("/admin/changesets")
        if not isinstance(cs_list, list):
            return
        table = self.query_one(DataTable)
        table.clear()
        for cs in cs_list:
            table.add_row(
                cs.get("id", "")[:8],
                cs.get("name", ""),
                cs.get("status", ""),
                cs.get("created_by", ""),
                cs.get("world_version") or "-",
                key=cs.get("id", ""),
            )
        self.app._cs_cache = cs_list  # type: ignore[attr-defined]

    def _selected_cs_id(self) -> str | None:
        table = self.query_one(DataTable)
        if table.cursor_row < 0:
            return None
        cs_list = getattr(self.app, "_cs_cache", [])
        if table.cursor_row >= len(cs_list):
            return None
        return cs_list[table.cursor_row].get("id")

    def action_scan(self) -> None:
        cs_id = self._selected_cs_id()
        if cs_id:
            self.run_worker(lambda: self._scan(cs_id), exclusive=True, thread=True)

    def _scan(self, cs_id: str) -> None:
        api: _Api = self.app.api  # type: ignore[attr-defined]
        result = api.post(f"/admin/changesets/{cs_id}/scan")
        log_widget = self.query_one(RichLog)
        log_widget.clear()
        log_widget.write(f"[bold]Scan result for {cs_id}:[/bold]")
        log_widget.write(
            f"Status: {result.get('status')}  Conflicts: {result.get('conflict_count')}  Errors: {result.get('error_count')}"
        )
        self.action_refresh()

    def action_promote(self) -> None:
        cs_id = self._selected_cs_id()
        if cs_id:
            self.run_worker(lambda: self._promote(cs_id), exclusive=True, thread=True)

    def _promote(self, cs_id: str) -> None:
        api: _Api = self.app.api  # type: ignore[attr-defined]
        result = api.post(f"/admin/changesets/{cs_id}/promote")
        log_widget = self.query_one(RichLog)
        log_widget.clear()
        if "error" in result:
            log_widget.write(f"[red]Promote failed: {result}[/red]")
        else:
            log_widget.write(f"[green]Promoted: {result}[/green]")
        self.action_refresh()

    def action_new_changeset(self) -> None:
        self.notify("Enter name in console — not yet wired to a dialog in this build")


class ClockScreen(Screen[None]):
    TITLE = "Clock (F5)"
    BINDINGS = [
        Binding("p", "toggle_pause", "Pause/Resume"),
        Binding("r", "refresh", "Refresh"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="clock-panel"):
            yield Label("", id="clock-display")
            yield Label("", id="clock-status")
            with Horizontal():
                yield Button("Pause", id="pause-btn")
                yield Button("Resume", id="resume-btn")
            yield Input(placeholder="Time ratio (e.g. 60)", id="ratio-input")
            yield Button("Set ratio", id="ratio-btn")
            yield Input(placeholder="Weather (clear, fog, snow...)", id="weather-input")
            yield Button("Set weather", id="weather-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.action_refresh()
        self.set_interval(5, self.action_refresh)

    def action_refresh(self) -> None:
        self.run_worker(self._load_clock, exclusive=True, thread=True)

    def _load_clock(self) -> None:
        api: _Api = self.app.api  # type: ignore[attr-defined]
        clock = api.get("/admin/clock")
        if "error" in clock:
            self.query_one("#clock-display", Label).update(f"[red]{clock}[/red]")
            return
        self.query_one("#clock-display", Label).update(
            f"Day {clock.get('current_day')}  "
            f"{clock.get('current_hour'):02d}:{clock.get('current_minute'):02d}  "
            f"{clock.get('current_season').capitalize()}  "
            f"{clock.get('weather').replace('_', ' ').capitalize()}"
        )
        self.query_one("#clock-status", Label).update(
            f"Paused: {clock.get('paused')}  Ratio: {clock.get('time_ratio')}×"
        )

    def action_toggle_pause(self) -> None:
        self.run_worker(self._toggle_pause, exclusive=True, thread=True)

    def _toggle_pause(self) -> None:
        api: _Api = self.app.api  # type: ignore[attr-defined]
        clock = api.get("/admin/clock")
        path = "/admin/clock/resume" if clock.get("paused") else "/admin/clock/pause"
        api.post(path)
        self._load_clock()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        api: _Api = self.app.api  # type: ignore[attr-defined]
        if event.button.id == "pause-btn":
            self.run_worker(
                lambda: api.post("/admin/clock/pause"), exclusive=True, thread=True
            )
        elif event.button.id == "resume-btn":
            self.run_worker(
                lambda: api.post("/admin/clock/resume"), exclusive=True, thread=True
            )
        elif event.button.id == "ratio-btn":
            ratio_str = self.query_one("#ratio-input", Input).value.strip()
            try:
                ratio = float(ratio_str)
                self.run_worker(
                    lambda: api.post("/admin/clock/time-ratio", {"ratio": ratio}),
                    exclusive=True,
                    thread=True,
                )
            except ValueError:
                self.notify("Invalid ratio", severity="error")
        elif event.button.id == "weather-btn":
            weather = self.query_one("#weather-input", Input).value.strip()
            self.run_worker(
                lambda: api.post("/admin/clock/weather", {"weather": weather}),
                exclusive=True,
                thread=True,
            )


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------


class LoreCraftAdminApp(App[None]):
    """Lorecraft admin TUI."""

    TITLE = "Lorecraft Admin"
    CSS = """
    Screen { background: #0a0a0f; }
    Header { background: #11111a; color: #a8ff78; }
    Footer { background: #11111a; }
    DataTable { height: 1fr; }
    LoginScreen { align: center middle; }
    #login-box { width: 60; height: auto; padding: 2; border: solid #4a4a6a; }
    #login-title { text-align: center; color: #a8ff78; margin-bottom: 1; }
    #login-error { color: #ff4444; }
    #audit-filters { height: 3; }
    #room-editor { width: 40; padding: 1; border: solid #4a4a6a; }
    #clock-panel { padding: 2; }
    #clock-display { color: #a8ff78; text-style: bold; }
    """

    BINDINGS = [
        Binding("f1", "switch_screen('players')", "Players", priority=True),
        Binding("f2", "switch_screen('audit')", "Audit", priority=True),
        Binding("f3", "switch_screen('world')", "World", priority=True),
        Binding("f4", "switch_screen('changesets')", "Changesets", priority=True),
        Binding("f5", "switch_screen('clock')", "Clock", priority=True),
        Binding("q", "quit", "Quit"),
    ]

    SCREENS = {
        "players": PlayersScreen,
        "audit": AuditScreen,
        "world": WorldScreen,
        "changesets": ChangesetsScreen,
        "clock": ClockScreen,
    }

    def __init__(self) -> None:
        super().__init__()
        creds = _load_creds()
        base_url = creds.get(
            "base_url", os.getenv("LORECRAFT_ADMIN_URL", "http://localhost:8000")
        )
        token = creds.get("access_token", "")
        self.api = _Api(base_url, token)

    def on_mount(self) -> None:
        if self.api.access_token:
            self.push_screen("players")
        else:
            self.push_screen(LoginScreen())


def main() -> None:  # pragma: no cover
    LoreCraftAdminApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
