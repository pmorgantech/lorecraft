"""Integration tests for admin REST API: issues/news/help topics CRUD (content ops)."""

from __future__ import annotations

from typing import Any

import anyio

from lorecraft.config import Settings
from lorecraft.main import create_app

from tests.integration._admin_api_support import (
    _SECRET,
    _access_token,
    _http,
    _lifespan,
    _make_engines,
    _seed_admin,
)

# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------


def test_create_and_list_issues(tmp_path) -> None:
    anyio.run(_test_create_and_list_issues, tmp_path)


async def _test_create_and_list_issues(tmp_path) -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        issues_yaml_path=str(tmp_path / "issues.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="moderator")
    async with _lifespan(app):
        _seed_admin(game_engine, role="moderator")
        status, created = await _http(
            app,
            "POST",
            "/admin/issues",
            body={
                "title": "Movement race condition",
                "type": "bug",
                "priority": "high",
            },
            token=token,
        )
        assert status == 200
        assert created["title"] == "Movement race condition"
        assert created["status"] == "open"
        assert created["created_by"] == "testadmin"

        status, listed = await _http(app, "GET", "/admin/issues", token=token)
        assert status == 200
        assert any(i["id"] == created["id"] for i in listed)

    # Admin mutation re-exports the YAML mirror to disk.
    assert (tmp_path / "issues.yaml").is_file()


def test_update_issue_status(tmp_path) -> None:
    anyio.run(_test_update_issue_status, tmp_path)


async def _test_update_issue_status(tmp_path) -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        issues_yaml_path=str(tmp_path / "issues.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="moderator")
    async with _lifespan(app):
        _seed_admin(game_engine, role="moderator")
        _, created = await _http(
            app, "POST", "/admin/issues", body={"title": "Fix it"}, token=token
        )
        status, updated = await _http(
            app,
            "PUT",
            f"/admin/issues/{created['id']}",
            body={"status": "resolved"},
            token=token,
        )
        assert status == 200
        assert updated["status"] == "resolved"

        status, missing = await _http(
            app,
            "PUT",
            "/admin/issues/does-not-exist",
            body={"status": "open"},
            token=token,
        )
        assert status == 404


def test_issue_components_endpoint(tmp_path) -> None:
    anyio.run(_test_issue_components_endpoint, tmp_path)


async def _test_issue_components_endpoint(tmp_path) -> None:
    from lorecraft.content.components import ISSUE_COMPONENTS

    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        issues_yaml_path=str(tmp_path / "issues.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="observer")
    async with _lifespan(app):
        _seed_admin(game_engine, role="observer")
        status, components = await _http(
            app, "GET", "/admin/issues/components", token=token
        )
        assert status == 200
        assert components == list(ISSUE_COMPONENTS)


def test_create_issue_rejects_unknown_component(tmp_path) -> None:
    anyio.run(_test_create_issue_rejects_unknown_component, tmp_path)


async def _test_create_issue_rejects_unknown_component(tmp_path) -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        issues_yaml_path=str(tmp_path / "issues.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="moderator")
    async with _lifespan(app):
        _seed_admin(game_engine, role="moderator")
        # A registered component is accepted.
        status, created = await _http(
            app,
            "POST",
            "/admin/issues",
            body={"title": "Parser bug", "component": "engine"},
            token=token,
        )
        assert status == 200
        assert created["component"] == "engine"

        # An unregistered component is rejected with 400.
        status, err = await _http(
            app,
            "POST",
            "/admin/issues",
            body={"title": "Bad", "component": "not-a-real-component"},
            token=token,
        )
        assert status == 400
        assert "not-a-real-component" in err["detail"]


def test_issue_mutation_broadcasts_content_changed(tmp_path) -> None:
    anyio.run(_test_issue_mutation_broadcasts_content_changed, tmp_path)


async def _test_issue_mutation_broadcasts_content_changed(tmp_path) -> None:
    import asyncio

    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        issues_yaml_path=str(tmp_path / "issues.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="moderator")
    async with _lifespan(app):
        _seed_admin(game_engine, role="moderator")
        # Subscribe a queue exactly as a live admin WebSocket would.
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=50)
        app.state.lorecraft.admin_broadcaster.add(q)

        status, _ = await _http(
            app, "POST", "/admin/issues", body={"title": "Fix"}, token=token
        )
        assert status == 200

        drained = []
        while not q.empty():
            drained.append(q.get_nowait())
        assert {"type": "content_changed", "resource": "issues"} in drained


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------


def test_create_list_and_delete_news(tmp_path) -> None:
    anyio.run(_test_create_list_and_delete_news, tmp_path)


async def _test_create_list_and_delete_news(tmp_path) -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        news_yaml_path=str(tmp_path / "news.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="moderator")
    async with _lifespan(app):
        _seed_admin(game_engine, role="moderator")
        status, created = await _http(
            app,
            "POST",
            "/admin/news",
            body={"title": "Welcome to Ashmoore", "type": "server", "body": "Hello!"},
            token=token,
        )
        assert status == 200
        assert created["title"] == "Welcome to Ashmoore"
        assert created["author"] == "testadmin"

        status, listed = await _http(app, "GET", "/admin/news", token=token)
        assert status == 200
        assert any(n["id"] == created["id"] for n in listed)

        status, feed = await _http(app, "GET", "/api/news")
        assert status == 200
        assert any(n["id"] == created["id"] for n in feed)

        status, _ = await _http(
            app, "DELETE", f"/admin/news/{created['id']}", token=token
        )
        assert status == 200

        status, listed_after = await _http(app, "GET", "/admin/news", token=token)
        assert status == 200
        assert not any(n["id"] == created["id"] for n in listed_after)

    assert (tmp_path / "news.yaml").is_file()


# ---------------------------------------------------------------------------
# Help topics
# ---------------------------------------------------------------------------


def test_create_update_and_delete_help_topic(tmp_path) -> None:
    anyio.run(_test_create_update_and_delete_help_topic, tmp_path)


async def _test_create_update_and_delete_help_topic(tmp_path) -> None:
    settings = Settings(
        database_path=":memory:",
        audit_database_path=":memory:",
        admin_jwt_secret=_SECRET,
        help_yaml_path=str(tmp_path / "help.yaml"),
    )
    game_engine, audit_engine = _make_engines()
    app = create_app(
        settings=settings, game_engine=game_engine, audit_engine=audit_engine
    )
    token = _access_token(role="moderator")
    async with _lifespan(app):
        _seed_admin(game_engine, role="moderator")

        # Create (id auto-assigned).
        status, created = await _http(
            app,
            "POST",
            "/admin/help",
            body={
                "name": "combat-basics",
                "title": "Combat Basics",
                "category": "World",
                "body": "swing your weapon",
                "keywords": ["fight", "attack"],
            },
            token=token,
        )
        assert status == 200
        assert created["name"] == "combat-basics"
        assert created["id"] >= 1
        topic_id = created["id"]

        # A duplicate name is rejected.
        status, _ = await _http(
            app,
            "POST",
            "/admin/help",
            body={"name": "combat-basics", "title": "Dup"},
            token=token,
        )
        assert status == 409

        # A bad slug is rejected.
        status, _ = await _http(
            app,
            "POST",
            "/admin/help",
            body={"name": "has spaces", "title": "Bad"},
            token=token,
        )
        assert status == 400

        # Update.
        status, updated = await _http(
            app,
            "PUT",
            f"/admin/help/{topic_id}",
            body={"title": "Fighting 101", "keywords": ["FIGHT"]},
            token=token,
        )
        assert status == 200
        assert updated["title"] == "Fighting 101"
        assert updated["keywords"] == ["fight"]  # lowercased

        status, listed = await _http(app, "GET", "/admin/help", token=token)
        assert status == 200
        assert any(t["id"] == topic_id for t in listed)

        # Delete.
        status, _ = await _http(app, "DELETE", f"/admin/help/{topic_id}", token=token)
        assert status == 200
        status, after = await _http(app, "GET", "/admin/help", token=token)
        assert not any(t["id"] == topic_id for t in after)

    # The YAML mirror was written on mutation.
    assert (tmp_path / "help.yaml").is_file()
