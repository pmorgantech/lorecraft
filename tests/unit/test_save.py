from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus, GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.game.meters import MeterDef
from lorecraft.engine.game.meters import get_registry as get_meter_registry
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.player import Player, PlayerStats, SaveSlot
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.meter_repo import MeterRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.save import SaveSlotService, SessionSafetyService


def _hp_base_maximum(entity_type: str, entity_id: str, session: Session) -> float:
    if entity_type == "player":
        stats = session.get(PlayerStats, entity_id)
        return float(stats.max_hp) if stats is not None else 100.0
    return 50.0


get_meter_registry().register(MeterDef(key="hp", base_maximum=_hp_base_maximum))


def test_save_slot_service_preserves_and_loads_player_owned_state() -> None:
    game_engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=game_engine, audit_engine=audit_engine)
    manager = ConnectionManager()

    with Session(game_engine) as game_session, Session(audit_engine) as audit_session:
        player = _seed_save_world(game_session)
        game_session.commit()
        ctx = _build_context(game_session, audit_session, player, manager)

        SaveSlotService().save("slot1", ctx)
        game_session.commit()

        player.current_room_id = "square"
        for stack in StackRepo(game_session).stacks_for_owner("player", player.id):
            assert stack.id is not None
            ItemLocationService(game_session).destroy(stack.id, stack.quantity)
        player.visited_rooms = ["square"]
        player.flags = {"door_open": False}
        game_session.commit()

        SaveSlotService().load("slot1", ctx)
        game_session.commit()
        ctx.flush_events()

        persisted = game_session.get(Player, "player-1")
        stats = game_session.get(PlayerStats, "player-1")
        save_slot = game_session.exec(select(SaveSlot)).first()
        persisted_carried = [
            stack.item_id
            for stack in StackRepo(game_session).stacks_for_owner("player", "player-1")
        ]
        hp_meter = MeterRepo(game_session).find("player", "player-1", "hp")

    assert save_slot is not None
    assert save_slot.room_id == "tavern"
    assert save_slot.inventory == [
        {"item_id": "old_sword", "quantity": 1, "instance_id": None}
    ]
    assert save_slot.visited_rooms == ["tavern"]
    assert persisted is not None
    assert persisted.current_room_id == "tavern"
    assert persisted_carried == ["old_sword"]
    assert persisted.visited_rooms == ["tavern"]
    assert persisted.flags == {"door_open": True}
    assert stats is not None
    assert hp_meter is not None
    assert hp_meter.current == 75
    assert ctx.messages == ["Saved to slot1.", "Loaded slot1."]
    assert ctx.updates["room_id"] == "tavern"
    assert manager.players_in_room("tavern") == ["player-1"]


def test_session_safety_grace_reconnect_and_expiry_are_audited() -> None:
    game_engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=game_engine, audit_engine=audit_engine)
    observed: list[GameEvent] = []
    bus = EventBus()
    for event_type in (
        GameEvent.PLAYER_DISCONNECTED,
        GameEvent.PLAYER_RECONNECTED,
        GameEvent.GRACE_PERIOD_EXPIRED,
    ):
        bus.on(event_type, lambda event, ctx: observed.append(event.type))

    with Session(game_engine) as game_session, Session(audit_engine) as audit_session:
        player = _seed_save_world(game_session)
        game_session.commit()
        service = SessionSafetyService(
            game_session=game_session,
            audit_session=audit_session,
            bus=bus,
            grace_seconds=60.0,
            now=100.0,
        )

        started = service.start_or_resume_session(player)
        service.begin_grace_period(started.player_session.id, player)
        game_session.commit()
        audit_session.commit()

        reconnected = SessionSafetyService(
            game_session=game_session,
            audit_session=audit_session,
            bus=bus,
            grace_seconds=60.0,
            now=120.0,
        ).start_or_resume_session(player)
        game_session.commit()
        audit_session.commit()

        service.begin_grace_period(reconnected.player_session.id, player)
        player.active_combat_session_id = "combat-1"
        expired = SessionSafetyService(
            game_session=game_session,
            audit_session=audit_session,
            bus=bus,
            grace_seconds=60.0,
            now=181.0,
        ).expire_due_grace_periods(player_id=player.id)
        game_session.commit()
        audit_session.commit()

        audit_events = audit_session.exec(select(AuditEvent)).all()
        started_reconnected = started.reconnected
        reconnected_reconnected = reconnected.reconnected
        started_session_id = started.player_session.id
        reconnected_session_id = reconnected.player_session.id
        expired_status = expired[0].status

    assert not started_reconnected
    assert reconnected_reconnected
    assert reconnected_session_id == started_session_id
    assert expired_status == "system_controlled"
    assert observed == [
        GameEvent.PLAYER_DISCONNECTED,
        GameEvent.PLAYER_RECONNECTED,
        GameEvent.PLAYER_DISCONNECTED,
        GameEvent.GRACE_PERIOD_EXPIRED,
    ]
    assert [event.event_type for event in audit_events] == [
        "player_disconnected",
        "player_reconnected",
        "player_disconnected",
        "grace_period_expired",
    ]
    assert {event.source_type for event in audit_events} == {"SYSTEM"}


def _seed_save_world(session: Session) -> Player:
    session.add(
        Room(
            id="tavern",
            name="Tavern",
            description="A warm room.",
            map_x=0,
            map_y=0,
        )
    )
    session.add(
        Room(
            id="square",
            name="Square",
            description="A busy square.",
            map_x=1,
            map_y=0,
        )
    )
    session.add(
        Item(id="old_sword", name="Old Sword", description="Nicked but serviceable.")
    )
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="tavern",
        visited_rooms=["tavern"],
        flags={"door_open": True},
        respawn_room_id="tavern",
    )
    session.add(player)
    session.add(PlayerStats(player_id="player-1"))
    session.commit()
    ItemLocationService(session).spawn("old_sword", Location("player", player.id))
    hp_meter = MeterService(session.get_bind(), GameRng()).get(
        session, "player", "player-1", "hp"
    )
    MeterService(session.get_bind(), GameRng()).set_current(session, hp_meter, 75.0)
    session.commit()
    return player


def _build_context(
    game_session: Session,
    audit_session: Session,
    player: Player,
    manager: ConnectionManager,
) -> GameContext:
    room = game_session.get(Room, player.current_room_id)
    assert room is not None
    manager.move_player(player.id, None, room.id)
    return GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(game_session),
        room_repo=RoomRepo(game_session),
        item_repo=ItemRepo(game_session),
        stack_repo=StackRepo(game_session),
        item_location=ItemLocationService(game_session),
        ledger=LedgerService(),
        rng=GameRng(),
        session=game_session,
        meters=MeterService(game_session.get_bind(), GameRng()),
        effects=EffectService(game_session.get_bind(), GameRng()),
        npc_repo=NpcRepo(game_session),
        manager=manager,
        bus=EventBus(),
        audit=AuditRepo(audit_session),
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
        commit_state=game_session.commit,
        commit_audit=audit_session.commit,
    )
