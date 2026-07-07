"""Sprint 54.3: celestial content over the real Ashmoore world.

Tide causeway: the shipped `celestial.yaml` gate drives the authoritative
`creek_crossing → tidal_islet` Exit as the tide turns — movement itself is
never special-cased (§3.9 one-owner). Moon lore: the shipped innkeeper
dialogue choice is visible only under a full moon via the `moon_phase_is`
dialogue condition.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from lorecraft.config import Settings
from lorecraft.db import create_tables
from lorecraft.engine.clock.celestial import DAYS_PER_MOON_PHASE
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import WorldClock
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.features.celestial.conditions import register as register_conditions
from lorecraft.features.celestial.content import (
    CelestialContentRegistry,
    load_celestial_yaml,
    register_tide_gate_handlers,
    sync_tide_gates,
)
from lorecraft.features.movement.service import MovementService
from lorecraft.features.npc.dialogue import _visible_choices
from lorecraft.features.npc.models import DialogueTree
from lorecraft.world.bootstrap import ensure_world_bootstrapped
from tests.integration.test_marks_integration import _ctx

REPO_ROOT = Path(__file__).resolve().parents[2]

FULL_MOON_DAY = 4 * DAYS_PER_MOON_PHASE + 1
LOW_TIDE_HOUR = 0
HIGH_TIDE_HOUR = 8  # START_HOUR — the state the world wakes to


def _engine():
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
    return engine


def _shipped_gates() -> CelestialContentRegistry:
    registry = CelestialContentRegistry()
    registry.load_document(
        load_celestial_yaml(REPO_ROOT / "world_content" / "celestial.yaml")
    )
    return registry


def _seed_player(session: Session, room: str) -> Player:
    player = Player(
        id="p1", username="Wader", current_room_id=room, respawn_room_id=room
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1"))
    session.commit()
    return player


def test_tide_causeway_opens_and_drowns_with_the_tide() -> None:
    engine = _engine()
    gates = _shipped_gates()
    assert gates.tide_gates(), "expected the shipped causeway gate"
    bus = EventBus()
    register_tide_gate_handlers(bus, engine, gates)
    movement = MovementService()

    with Session(engine) as session:
        # Authored state matches the wake-up tide (high → locked).
        exit_ = RoomRepo(session).exit("creek_crossing", "south")
        assert exit_ is not None and exit_.locked is True

        # Low tide reveals the causeway; the real move command crosses it.
        assert sync_tide_gates(session, LOW_TIDE_HOUR, gates) == 1
        session.commit()
        player = _seed_player(session, "creek_crossing")
        ctx = _ctx(session, player, bus)
        movement.move("south", ctx)
        assert player.current_room_id == "tidal_islet"
        session.commit()  # the engine commits per command; mirror that

    # The tide turns (handler path, own session/commit): causeway drowns.
    bus.emit(Event(GameEvent.TIDE_CHANGED, {"tide": "high", "hour": 6}), object())

    with Session(engine) as session:
        exit_ = RoomRepo(session).exit("creek_crossing", "south")
        assert exit_ is not None and exit_.locked is True

        # Wading back is always possible — the return exit is never gated.
        player = session.get(Player, "p1")
        assert player is not None
        ctx = _ctx(session, player, EventBus())
        movement.move("north", ctx)
        assert player.current_room_id == "creek_crossing"

        # And the drowned causeway blocks the way south again.
        ctx = _ctx(session, player, EventBus())
        movement.move("south", ctx)
        assert player.current_room_id == "creek_crossing"
        assert any("locked" in m.lower() for m in ctx.messages)


def test_moon_gated_dialogue_choice_only_at_full_moon() -> None:
    engine = _engine()
    register_conditions()
    moon_label_fragment = "moon is full tonight"

    with Session(engine) as session:
        tree = session.get(DialogueTree, "innkeeper_dialogue")
        assert tree is not None
        nodes = tree.tree_data.get("nodes")
        assert isinstance(nodes, dict)
        greeting = nodes["greeting"]
        assert isinstance(greeting, dict)
        player = _seed_player(session, "wandering_crow_inn")
        ctx = _ctx(session, player, EventBus())

        ctx.clock = WorldClock(
            game_epoch=0.0, real_epoch=0.0, current_day=FULL_MOON_DAY
        )
        labels = [str(c.get("label", "")) for c in _visible_choices(greeting, ctx)]
        assert any(moon_label_fragment in label.lower() for label in labels)

        ctx.clock.current_day = 1  # new moon
        labels = [str(c.get("label", "")) for c in _visible_choices(greeting, ctx)]
        assert not any(moon_label_fragment in label.lower() for label in labels)


def test_shipped_celestial_content_lints_clean_against_world() -> None:
    import yaml as yaml_module

    from lorecraft.features.celestial.content import lint_celestial

    world = yaml_module.safe_load(
        (REPO_ROOT / "world_content" / "world.yaml").read_text()
    )
    known_exits = [
        (room["id"], exit_["direction"])
        for room in world.get("rooms", [])
        for exit_ in room.get("exits", [])
    ]
    doc = load_celestial_yaml(REPO_ROOT / "world_content" / "celestial.yaml")
    assert doc.tide_gates, "expected at least one shipped tide gate"
    assert lint_celestial(doc, known_exits=known_exits) == []
