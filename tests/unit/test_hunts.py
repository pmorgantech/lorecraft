"""Scavenger-hunt feature (Sprint 48): lifecycle, find→reward, content-lint."""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.hunts.models import (
    HuntDef,
    HuntRegistry,
    HuntReward,
    HuntsDocument,
    lint_hunts,
    validate_hunts_document,
)
from lorecraft.features.hunts.service import HuntService
from lorecraft.features.inventory.service import InventoryService

ROOM = "square"


def _hunt() -> HuntDef:
    return HuntDef(
        id="h1",
        name="Test Hunt",
        clue_items=["gem", "coin"],
        spawn_rooms=[ROOM],
        reward=HuntReward(coins=30, lore="test_hunt"),
        duration_ticks=100,
    )


def _seed(session: Session) -> Player:
    session.add(Room(id=ROOM, name="Square", description="d", map_x=0, map_y=0))
    session.add(Item(id="gem", name="Green Gem", description="d", takeable=True))
    session.add(Item(id="coin", name="Copper Coin", description="d", takeable=True))
    player = Player(
        id="p1", username="Finder", current_room_id=ROOM, respawn_room_id=ROOM
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1"))
    session.commit()
    return player


def _ctx(session: Session, player: Player) -> GameContext:
    room = session.get(Room, player.current_room_id)
    assert room is not None
    return GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=GameRng(seed=1),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id="p1", correlation_id="s1"),
        session_id="s1",
    )


def _service(session: Session) -> tuple[HuntService, EventBus, Player]:
    player = _seed(session)
    registry = HuntRegistry()
    registry.register(_hunt())
    service = HuntService(registry=registry, ledger=LedgerService())
    bus = EventBus()
    service.register(bus)
    return service, bus, player


def test_open_spawns_clue_items_and_marks_open() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        service, _bus, _player = _service(session)
        service.open("h1", session, GameRng(seed=1))
        session.commit()

        assert service.is_open("h1")
        room_items = {
            stack.item_id for stack in StackRepo(session).stacks_for_owner("room", ROOM)
        }
        assert {"gem", "coin"} <= room_items


def test_finding_all_items_grants_reward_and_lore() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        service, bus, player = _service(session)
        service.open("h1", session, GameRng(seed=1))
        session.commit()

        ctx = _ctx(session, player)
        ctx.bus = bus
        inv = InventoryService()

        inv.take_item("gem", ctx)
        ctx.flush_events()
        assert player.flags.get("hunt:h1:found:gem") is True
        assert player.flags.get("hunt:h1:done") is None  # one still to find

        inv.take_item("coin", ctx)
        ctx.flush_events()
        assert player.flags.get("hunt:h1:done") is True
        assert player.flags.get("lore:test_hunt") is True
        assert LedgerService().balance_of(session, "player", "p1") == 30


def test_already_completed_hunt_does_not_re_reward() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        service, bus, player = _service(session)
        service.open("h1", session, GameRng(seed=1))
        session.commit()

        ctx = _ctx(session, player)
        ctx.bus = bus
        inv = InventoryService()
        inv.take_item("gem", ctx)
        inv.take_item("coin", ctx)
        ctx.flush_events()
        assert LedgerService().balance_of(session, "player", "p1") == 30

        # Re-fire a find for an already-done hunt: no extra coins.
        service._record_find(ctx, _hunt(), "gem")
        assert LedgerService().balance_of(session, "player", "p1") == 30


def test_close_despawns_remaining_items() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        service, _bus, _player = _service(session)
        service.open("h1", session, GameRng(seed=1))
        session.commit()

        service.close("h1", session)
        session.commit()

        assert not service.is_open("h1")
        remaining = {
            stack.item_id for stack in StackRepo(session).stacks_for_owner("room", ROOM)
        }
        assert "gem" not in remaining and "coin" not in remaining


def test_scheduled_job_opens_and_closes_a_hunt() -> None:
    """A `hunt_open`/`hunt_close` SCHEDULED_JOB_DUE event drives the lifecycle
    (the scheduler path) — the 'opens/closes on schedule' requirement."""
    from lorecraft.engine.game.events import Event, GameEvent
    from lorecraft.engine.services.scheduler import SchedulerEventContext

    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        service, bus, _player = _service(session)
        session.commit()

    sched_ctx = SchedulerEventContext(game_engine=engine, bus=bus, rng=GameRng(seed=1))

    bus.emit(
        Event(
            GameEvent.SCHEDULED_JOB_DUE,
            {"job_type": HuntService.JOB_OPEN, "payload": {"hunt_id": "h1"}},
        ),
        sched_ctx,
    )
    assert service.is_open("h1")

    bus.emit(
        Event(
            GameEvent.SCHEDULED_JOB_DUE,
            {"job_type": HuntService.JOB_CLOSE, "payload": {"hunt_id": "h1"}},
        ),
        sched_ctx,
    )
    assert not service.is_open("h1")


def test_lint_flags_unknown_item_and_room_references() -> None:
    doc = HuntsDocument(
        hunts=[
            HuntDef(
                id="bad",
                name="Bad",
                clue_items=["ghost_item"],
                spawn_rooms=["nowhere"],
            )
        ]
    )
    problems = lint_hunts(doc, known_item_ids=["real"], known_room_ids=["here"])
    assert any("ghost_item" in p for p in problems)
    assert any("nowhere" in p for p in problems)


def test_lint_passes_for_valid_references() -> None:
    doc = HuntsDocument(hunts=[_hunt()])
    problems = lint_hunts(doc, known_item_ids=["gem", "coin"], known_room_ids=[ROOM])
    assert problems == []


def test_document_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicate hunt ids"):
        validate_hunts_document(
            {
                "version": 1,
                "hunts": [
                    {"id": "x", "name": "A", "clue_items": ["i"], "spawn_rooms": ["r"]},
                    {"id": "x", "name": "B", "clue_items": ["i"], "spawn_rooms": ["r"]},
                ],
            }
        )


def test_reward_rejects_negative_coins() -> None:
    with pytest.raises(ValueError):
        HuntReward(coins=-1)


def test_shipped_ashmoore_hunts_lint_clean_against_world() -> None:
    """The checked-in world_content/hunts.yaml must reference only real items
    and rooms in world_content/world.yaml — the content-lint contract."""
    from pathlib import Path

    import yaml

    from lorecraft.features.hunts.models import load_hunts_yaml

    repo_root = Path(__file__).resolve().parents[2]
    world = yaml.safe_load((repo_root / "world_content" / "world.yaml").read_text())
    item_ids = [i["id"] for i in world.get("items", [])]
    room_ids = [r["id"] for r in world.get("rooms", [])]

    doc = load_hunts_yaml(repo_root / "world_content" / "hunts.yaml")
    assert doc.hunts, "expected at least one shipped hunt"
    assert lint_hunts(doc, known_item_ids=item_ids, known_room_ids=room_ids) == []
