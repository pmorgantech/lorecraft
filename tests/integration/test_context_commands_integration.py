"""Sprint 55.4: context-attached commands over the real Ashmoore world.

Drives the shipped `read` (altar, Ruined Chapel) and `tip` (Mira, the inn)
context verbs against the imported `world_content/world.yaml`: they are hidden
from `help` and blocked out of context, work + fire their side effects in
context, and the shipped content lints clean.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.features.context_commands.models import (
    get_registry,
    lint_context_commands,
)
from lorecraft.features.npc.side_effects import get_registry as side_effect_registry
from lorecraft.world.bootstrap import ensure_world_bootstrapped
from tests.integration.test_marks_integration import _ctx

REPO_ROOT = Path(__file__).resolve().parents[2]


def _world():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    ensure_world_bootstrapped(
        engine,
        Settings(world_yaml_path=str(REPO_ROOT / "world_content" / "world.yaml")),
    )
    get_registry().clear()
    with Session(engine) as loader_session:
        get_registry().load_from_session(loader_session)
    registry = CommandRegistry()
    register_all_commands(registry)
    return engine, registry


def _player(session: Session, room: str) -> Player:
    player = Player(
        id="p1", username="Seeker", current_room_id=room, respawn_room_id=room
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1"))
    session.commit()
    return player


def _available(registry: CommandRegistry, verb: str, ctx: object) -> bool:
    command = registry.get(verb)
    assert command is not None
    return registry.evaluate_conditions(command, ctx).allowed


def test_read_altar_verb_gated_to_the_chapel() -> None:
    engine, registry = _world()
    assert registry.get("read") is not None, "the altar's read verb should register"

    with Session(engine) as session:
        # Elsewhere (village square): the altar isn't here → blocked.
        player = _player(session, "village_square")
        ctx = _ctx(session, player, EventBus())
        assert _available(registry, "read", ctx) is False

        # In the Ruined Chapel: available, and firing sets the lore flag.
        player.current_room_id = "ruined_chapel"
        session.add(player)
        session.commit()
        ctx = _ctx(session, player, EventBus())
        assert _available(registry, "read", ctx) is True

        registry.get("read").handler("altar", ctx)
        assert player.flags.get("lore:chapel_wheel") is True
        assert any("wheel-within-a-wheel" in m for m in ctx.messages)


def test_tip_verb_gated_to_mira() -> None:
    engine, registry = _world()
    with Session(engine) as session:
        player = _player(session, "village_square")
        ctx = _ctx(session, player, EventBus())
        assert _available(registry, "tip", ctx) is False

        player.current_room_id = "wandering_crow_inn"
        session.add(player)
        session.commit()
        ctx = _ctx(session, player, EventBus())
        assert _available(registry, "tip", ctx) is True
        registry.get("tip").handler(None, ctx)
        assert player.flags.get("tipped_mira") is True


def test_context_verbs_hidden_from_help_out_of_context() -> None:
    """The help/availability filter must not list `read`/`tip` where their
    object isn't present (the "appears only when relevant" contract)."""
    from lorecraft.commands.meta import _is_available

    engine, registry = _world()
    with Session(engine) as session:
        player = _player(session, "village_square")
        ctx = _ctx(session, player, EventBus())
        read = registry.get("read")
        tip = registry.get("tip")
        assert read is not None and tip is not None
        assert _is_available(registry, read, ctx, in_dialogue=False) is False
        assert _is_available(registry, tip, ctx, in_dialogue=False) is False


def test_shipped_context_commands_lint_clean() -> None:
    engine, _registry = _world()
    del engine
    problems = lint_context_commands(
        get_registry().all_bindings(), known_side_effects=side_effect_registry()
    )
    assert get_registry().all_bindings(), "expected shipped context commands"
    assert problems == []
