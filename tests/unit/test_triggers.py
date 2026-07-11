"""A2 — TriggerService: on/when/do binding, encounter synthesis, any/all, fail-closed load.

Wires the real dialogue-condition and side-effect registries into the Tier-1 service and fires
triggers through the event bus with a real GameContext, so the mechanism is exercised end to end
(not against fakes). See `docs/scripting_engine_design.md` §3.3 + Appendix A.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import NPC, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.scripting.triggers import (
    Trigger,
    TriggerLoadError,
    TriggerService,
    parse_trigger,
)
from lorecraft.engine.scripting.vocabulary import global_vocabulary
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService

# Importing these registers the built-in vocabulary (actor_has_flag / set_flags / …) that the
# triggers below reference and the loader validates against.
from lorecraft.features.npc import dialogue_conditions, side_effects

ROOM = "plaza"
NPC_ID = "sentinel"


@pytest.fixture
def session() -> Session:  # type: ignore[misc]
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as session:
        session.add(Room(id=ROOM, name="Plaza", description="d", map_x=0, map_y=0))
        session.add(
            NPC(
                id=NPC_ID,
                name="Sentinel",
                description="brass",
                current_room_id=ROOM,
                home_room_id=ROOM,
                dialogue_tree_id="none",
            )
        )
        player = Player(
            id="p1", username="Walker", current_room_id=ROOM, respawn_room_id=ROOM
        )
        session.add(player)
        session.add(PlayerStats(player_id="p1"))
        session.commit()
        yield session


def _ctx(session: Session, bus: EventBus) -> GameContext:
    player = session.get(Player, "p1")
    room = session.get(Room, ROOM)
    assert player is not None and room is not None
    bind = session.get_bind()
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
        meters=MeterService(bind, GameRng()),
        effects=EffectService(bind, GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(actor_id="p1", correlation_id="s1"),
        session_id="s1",
    )


def _service(bus: EventBus) -> TriggerService:
    service = TriggerService(
        when=dialogue_conditions.get_registry(), do=side_effects.get_registry()
    )
    service.register(bus)
    return service


def _move(bus: EventBus, ctx: GameContext) -> None:
    bus.emit(
        Event(
            GameEvent.PLAYER_MOVED,
            {"player_id": "p1", "from_room_id": "elsewhere", "to_room_id": ROOM},
        ),
        ctx,
    )


def test_encounter_trigger_fires_and_runs_effect(session: Session) -> None:
    bus = EventBus()
    service = _service(bus)
    ctx = _ctx(session, bus)
    service.load(
        [
            Trigger(
                on="encounter",
                entity_type="npc",
                entity_id=NPC_ID,
                do={"set_flags": ["greeted"]},
            )
        ]
    )
    _move(bus, ctx)
    assert ctx.player.flags.get("greeted") is True


def test_encounter_when_gates_the_effect(session: Session) -> None:
    bus = EventBus()
    service = _service(bus)
    ctx = _ctx(session, bus)
    service.load(
        [
            Trigger(
                on="encounter",
                entity_type="npc",
                entity_id=NPC_ID,
                when={"actor_has_flag": ["vip"]},
                do={"set_flags": ["greeted"]},
            )
        ]
    )
    _move(bus, ctx)
    assert "greeted" not in ctx.player.flags  # when failed (no vip flag)

    ctx.player.flags = {**ctx.player.flags, "vip": True}
    _move(bus, ctx)
    assert ctx.player.flags.get("greeted") is True  # when passed


def test_encounter_only_fires_for_npc_in_the_room(session: Session) -> None:
    bus = EventBus()
    service = _service(bus)
    ctx = _ctx(session, bus)
    service.load(
        [
            Trigger(
                on="encounter",
                entity_type="npc",
                entity_id="absent_npc",
                do={"set_flags": ["greeted"]},
            )
        ]
    )
    _move(bus, ctx)
    assert "greeted" not in ctx.player.flags


def test_player_entered_room_trigger_fires(session: Session) -> None:
    bus = EventBus()
    service = _service(bus)
    ctx = _ctx(session, bus)
    service.load(
        [
            Trigger(
                on="player_entered",
                entity_type="room",
                entity_id=ROOM,
                do={"set_flags": ["saw_plaza"]},
            )
        ]
    )
    _move(bus, ctx)
    assert ctx.player.flags.get("saw_plaza") is True


def test_any_group_one_true_member_passes(session: Session) -> None:
    bus = EventBus()
    service = _service(bus)
    ctx = _ctx(session, bus)
    ctx.player.flags = {**ctx.player.flags, "b": True}
    service.load(
        [
            Trigger(
                on="encounter",
                entity_type="npc",
                entity_id=NPC_ID,
                when={"any": [{"actor_has_flag": ["a"]}, {"actor_has_flag": ["b"]}]},
                do={"set_flags": ["hit"]},
            )
        ]
    )
    _move(bus, ctx)
    assert ctx.player.flags.get("hit") is True


def test_all_group_requires_every_member(session: Session) -> None:
    bus = EventBus()
    service = _service(bus)
    ctx = _ctx(session, bus)
    ctx.player.flags = {**ctx.player.flags, "a": True}  # missing "b"
    service.load(
        [
            Trigger(
                on="encounter",
                entity_type="npc",
                entity_id=NPC_ID,
                when={"all": [{"actor_has_flag": ["a"]}, {"actor_has_flag": ["b"]}]},
                do={"set_flags": ["hit"]},
            )
        ]
    )
    _move(bus, ctx)
    assert "hit" not in ctx.player.flags


def test_parse_trigger_rejects_unknown_effect() -> None:
    with pytest.raises(TriggerLoadError, match="unknown effect 'teleport_home'"):
        parse_trigger(
            "npc",
            NPC_ID,
            {"on": "encounter", "do": [{"teleport_home": True}]},
            vocab=global_vocabulary(),
        )


def test_parse_trigger_rejects_unknown_condition() -> None:
    with pytest.raises(TriggerLoadError, match="unknown condition 'is_raining'"):
        parse_trigger(
            "npc",
            NPC_ID,
            {
                "on": "encounter",
                "when": {"is_raining": True},
                "do": {"set_flags": ["x"]},
            },
            vocab=global_vocabulary(),
        )


def test_parse_trigger_accepts_known_names() -> None:
    trigger = parse_trigger(
        "npc",
        NPC_ID,
        {
            "on": "encounter",
            "when": {"actor_has_flag": ["vip"]},
            "do": {"set_flags": ["ok"]},
        },
        vocab=global_vocabulary(),
    )
    assert trigger.on == "encounter" and trigger.entity_id == NPC_ID


def test_parse_trigger_requires_on() -> None:
    with pytest.raises(TriggerLoadError, match="missing a string 'on:'"):
        parse_trigger(
            "npc", NPC_ID, {"do": {"set_flags": ["x"]}}, vocab=global_vocabulary()
        )
