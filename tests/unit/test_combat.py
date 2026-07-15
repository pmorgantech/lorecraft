"""Scheduled Intent combat foundation tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.meters import MeterDef
from lorecraft.engine.game.meters import get_registry as get_meter_registry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.scheduler import ScheduledJob
from lorecraft.engine.models.world import Item, NPC, Room, WorldClock
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.scheduler import SchedulerService
from lorecraft.features.combat.models import (
    CombatAction,
    CombatEncounter,
    CombatParticipant,
    CombatResolutionRecord,
)
from lorecraft.features.combat.damage import (
    ArmorProfile,
    apply_damage_stack,
    armor_profile_for,
    weapon_profile_for,
)
from lorecraft.features.combat.service import COMBAT_RESOLVE_JOB, CombatService


@pytest.fixture(autouse=True)
def combat_meters() -> Iterator[None]:
    registry = get_meter_registry()
    registry.register(
        MeterDef(
            key="hp",
            base_maximum=lambda entity_type, entity_id, session: _hp_base(
                entity_type, entity_id, session
            ),
        )
    )
    registry.register(
        MeterDef(
            key="stamina",
            base_maximum=lambda entity_type, entity_id, session: 100.0,
        )
    )
    yield
    registry._defs.pop("hp", None)  # type: ignore[attr-defined]
    registry._defs.pop("stamina", None)  # type: ignore[attr-defined]


def test_attack_submits_intent_and_schedules_resolution() -> None:
    engine = _engine()
    bus = EventBus()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session, bus=bus)
        service.attack("goblin", ctx)
        session.commit()

        encounter = session.exec(select(CombatEncounter)).one()
        actions = session.exec(select(CombatAction)).all()
        participants = session.exec(select(CombatParticipant)).all()
        jobs = session.exec(select(ScheduledJob)).all()

        assert ctx.player.active_combat_session_id == encounter.id
        assert encounter.state == "active"
        assert {p.actor_type for p in participants} == {"player", "npc"}
        assert len(actions) == 1
        assert actions[0].action_key == "basic_attack"
        assert actions[0].state == "pending"
        assert jobs[0].job_type == COMBAT_RESOLVE_JOB
        assert jobs[0].payload == {"action_id": actions[0].id}
        assert "combat" in ctx.updates


def test_scheduled_resolution_applies_damage_and_npc_counter_intent() -> None:
    engine = _engine()
    rng = GameRng(seed=7)
    bus = EventBus()
    scheduler = SchedulerService(engine, rng)
    service = CombatService()
    scheduler.register(bus)
    service.register(bus)

    with Session(engine) as session:
        ctx = _context(session, bus=bus, rng=rng)
        service.attack("goblin", ctx)
        session.commit()

    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 10.0}), ctx=None)

    with Session(engine) as session:
        actions = session.exec(
            select(CombatAction).order_by(CombatAction.submitted_at)
        ).all()
        record = session.exec(select(CombatResolutionRecord)).one()
        goblin_hp = ctx_meters(engine).get(session, "npc", "goblin", "hp")

        assert actions[0].state == "resolved"
        assert actions[0].outcome["action_key"] == "basic_attack"
        assert "damage_trace" in actions[0].outcome
        assert actions[0].random_trace
        assert record.action_id == actions[0].id
        assert record.random_trace == actions[0].random_trace
        assert record.damage_trace["final_damage"] == actions[0].outcome["damage"]
        assert goblin_hp.current < goblin_hp.maximum
        assert any(
            action.actor_type == "npc" and action.state == "pending"
            for action in actions
        )


def test_flee_resolution_ends_player_participation() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        service.flee(None, ctx)
        flee_action = session.exec(
            select(CombatAction).where(CombatAction.action_key == "flee")
        ).one()

        service.resolve_action(
            session,
            flee_action.id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        player = session.get(Player, "player-1")
        participant = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()

        assert player is not None and player.active_combat_session_id is None
        assert participant.status == "escaped"


def test_damage_profiles_use_equipped_weapon_and_armor_descriptors() -> None:
    engine = _engine()
    with Session(engine) as session:
        _context(session)
        session.add(
            Item(
                id="fine_sword",
                name="Fine Sword",
                description="Sharp.",
                slot="main_hand",
                weight=4.0,
                category="weapon",
                quality="fine",
            )
        )
        session.add(
            Item(
                id="chainmail",
                name="Chainmail",
                description="Heavy rings.",
                slot="torso",
                wearable=True,
                weight=12.0,
                category="armor",
                quality="common",
            )
        )
        session.add(
            ItemStack(
                item_id="fine_sword",
                owner_type="player",
                owner_id="player-1",
                slot="main_hand",
            )
        )
        session.add(
            ItemStack(
                item_id="chainmail",
                owner_type="player",
                owner_id="player-1",
                slot="torso",
            )
        )
        session.flush()

        weapon = weapon_profile_for(session, "player", "player-1")
        armor = armor_profile_for(session, "player", "player-1")
        mitigated = apply_damage_stack(
            base_damage=12.0,
            outcome_multiplier=1.0,
            armor=armor,
            penetration=weapon.penetration,
        )
        unarmored = apply_damage_stack(
            base_damage=12.0,
            outcome_multiplier=1.0,
            armor=ArmorProfile(block=0.0, resistance_factor=0.0, sources=()),
            penetration=0.0,
        )

        assert weapon.base_damage > 4.0
        assert weapon.accuracy_bonus > 0.0
        assert "item:fine_sword" in weapon.sources
        assert armor.block > 0.0
        assert armor.resistance_factor > 0.0
        assert "item:chainmail" in armor.sources
        assert mitigated.amount < unarmored.amount
        assert mitigated.trace["armor_sources"] == ["item:chainmail"]


def _engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def _context(
    session: Session,
    *,
    bus: EventBus | None = None,
    rng: GameRng | None = None,
) -> GameContext:
    room = Room(
        id="arena",
        name="Arena",
        description="A test arena.",
        map_x=0,
        map_y=0,
    )
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="arena",
        respawn_room_id="arena",
    )
    npc = NPC(
        id="goblin",
        name="Goblin",
        description="A hostile goblin.",
        current_room_id="arena",
        home_room_id="arena",
        dialogue_tree_id="goblin",
        max_hp=40,
    )
    session.add(room)
    session.add(player)
    session.add(
        PlayerStats(
            player_id=player.id,
            strength=30,
            agility=12,
            max_hp=100,
        )
    )
    session.add(npc)
    session.flush()
    rng = rng or GameRng(seed=1)
    engine = session.get_bind()
    assert isinstance(engine, Engine)
    return GameContext(
        player=player,
        room=room,
        clock=WorldClock(game_epoch=0.0, real_epoch=0.0),
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=rng,
        session=session,
        meters=MeterService(engine, rng),
        effects=EffectService(engine, rng),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=bus or EventBus(),
        audit=AuditRepo(session),
        transaction=TransactionContext.create(
            actor_id="player-1", correlation_id="session-1"
        ),
        session_id="session-1",
    )


def _hp_base(entity_type: str, entity_id: str, session: Session) -> float:
    if entity_type == "player":
        stats = session.get(PlayerStats, entity_id)
        return float(stats.max_hp if stats is not None else 100)
    npc = session.get(NPC, entity_id)
    return float(npc.max_hp if npc is not None else 50)


def ctx_meters(engine) -> MeterService:
    return MeterService(engine, GameRng(seed=1))
