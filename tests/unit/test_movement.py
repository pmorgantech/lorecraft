from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus, GameEvent
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Exit, Item, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.features.fatigue.service import FatigueService
from lorecraft.features.fatigue.source import (
    FATIGUE_METER_KEY,
    register as register_fatigue,
)
from lorecraft.features.exploration.rules import mark_exit_discovered
from lorecraft.features.movement.commands import register_movement_commands
from lorecraft.features.movement.service import MovementService

register_fatigue()


def test_movement_service_moves_player_and_queues_event() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    manager = ConnectionManager()
    observed = []

    with Session(engine) as session:
        _seed_rooms(session)
        player = _seed_player(session)
        session.commit()
        bus = EventBus()
        bus.on(
            GameEvent.PLAYER_MOVED, lambda event, ctx: observed.append(event.payload)
        )
        ctx = _build_context(session, player, manager, bus)
        manager.move_player("player-1", None, "tavern")

        MovementService().move("east", ctx)
        session.commit()
        ctx.flush_events()

        persisted = session.get(Player, "player-1")

    assert ctx.messages == ["You go east."]
    assert ctx.room_messages == ["petem leaves east."]
    assert ctx.arrival_messages == ["petem arrives from the west."]
    assert ctx.updates == {"room_id": "square"}
    assert manager.players_in_room("square") == ["player-1"]
    assert persisted.current_room_id == "square"
    assert persisted.visited_rooms == ["square"]
    assert observed == [
        {
            "player_id": "player-1",
            "from_room_id": "tavern",
            "to_room_id": "square",
            "direction": "east",
        }
    ]


def test_unlock_requires_the_right_key() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Exit(
                room_id="tavern",
                direction="north",
                target_room_id="square",
                locked=True,
                key_item_id="brass_key",
            )
        )
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().unlock("north", ctx)

    assert ctx.messages == ["You don't have the right key."]


def test_unlock_persists_and_allows_future_keyless_movement() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Exit(
                room_id="tavern",
                direction="north",
                target_room_id="square",
                locked=True,
                key_item_id="brass_key",
            )
        )
        session.add(Item(id="brass_key", name="Brass Key", description="A key."))
        player = _seed_player(session)
        session.commit()
        item_location = ItemLocationService(session)
        loc = Location("player", player.id)
        stack = item_location.spawn("brass_key", loc)[0]
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().unlock("north", ctx)
        session.commit()

        assert ctx.messages == ["You unlock the way north. It is now unlocked."]

        ctx.messages.clear()
        assert stack.id is not None
        item_location.destroy(stack.id, 1)
        session.commit()
        MovementService().move("north", ctx)

    assert ctx.messages == ["You go north."]


def test_lock_sets_exit_locked_when_key_carried() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Exit(
                room_id="tavern",
                direction="north",
                target_room_id="square",
                locked=False,
                key_item_id="brass_key",
            )
        )
        session.add(Item(id="brass_key", name="Brass Key", description="A key."))
        player = _seed_player(session)
        session.commit()
        ItemLocationService(session).spawn("brass_key", Location("player", player.id))
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().lock("north", ctx)

    assert ctx.messages == ["You lock the way north. It is now locked."]


def test_unlock_without_direction_prompts() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().unlock(None, ctx)

    assert ctx.messages == ["Unlock which way?"]


def test_movement_service_blocks_missing_exit() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().move("north", ctx)

    assert ctx.messages == ["You can't go that way."]
    assert ctx.player.current_room_id == "tavern"


def test_where_reports_shortest_known_path_to_room() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Room(
                id="south_gate",
                name="South Gate",
                description="A guarded gate.",
                map_x=1,
                map_y=1,
            )
        )
        session.add(
            Exit(room_id="square", direction="south", target_room_id="south_gate")
        )
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().where("south gate", ctx)

    assert ctx.messages == ["Path to South Gate: e, s"]
    assert ctx.player.current_room_id == "tavern"


def test_where_command_accepts_multi_word_room_reference() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    registry = CommandRegistry()
    register_movement_commands(registry)
    cmd_engine = CommandEngine(registry, RuleEngine())

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Room(
                id="south_gate",
                name="South Gate",
                description="A guarded gate.",
                map_x=1,
                map_y=1,
            )
        )
        session.add(
            Exit(room_id="square", direction="south", target_room_id="south_gate")
        )
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        cmd_engine.handle_command("where south gate", ctx)

    assert ctx.messages == ["Path to South Gate: e, s"]


def test_where_uses_discovered_hidden_exits_but_does_not_reveal_unknown_ones() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Room(
                id="south_gate",
                name="South Gate",
                description="A guarded gate.",
                map_x=1,
                map_y=1,
            )
        )
        session.add(
            Exit(room_id="square", direction="south", target_room_id="south_gate")
        )
        session.add(
            Exit(
                room_id="tavern",
                direction="south",
                target_room_id="south_gate",
                hidden=True,
            )
        )
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().where("south gate", ctx)
        mark_exit_discovered(ctx, "tavern", "south")
        MovementService().where("south gate", ctx)

    assert ctx.messages == [
        "Path to South Gate: e, s",
        "Path to South Gate: s",
    ]


def test_where_reports_unreachable_room() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Room(
                id="island",
                name="Island",
                description="A lonely island.",
                map_x=10,
                map_y=10,
            )
        )
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        MovementService().where("island", ctx)

    assert ctx.messages == ["I can't find a known path to Island from here."]


def test_pick_records_skill_use_for_a_player_without_a_stats_row() -> None:
    """Regression: `pick` must not raise NotFoundError for a brand-new character
    whose PlayerStats row has never been materialized. MovementService.pick calls
    PlayerRepo.stats() for its get-or-create side effect before skills.record_use
    (which hard-raises on a missing row); removing that call silently regressed a
    fresh character's first lockpick attempt."""
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        session.add(
            Exit(
                room_id="tavern",
                direction="north",
                target_room_id="square",
                locked=True,
                key_item_id="brass_key",
            )
        )
        player = _seed_player(session)
        session.commit()
        # Sanity: the fresh player genuinely has no PlayerStats row yet.
        assert session.get(PlayerStats, player.id) is None
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        # Must not raise NotFoundError from record_use.
        MovementService().pick("north", ctx)
        session.commit()

        assert session.get(PlayerStats, player.id) is not None


def test_movement_blocks_when_movement_points_are_insufficient() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    manager = ConnectionManager()

    with Session(engine) as session:
        _seed_rooms(session)
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, manager, EventBus())
        meter = ctx.meters.get(session, "player", player.id, FATIGUE_METER_KEY)
        ctx.meters.set_current(session, meter, 0.0)

        MovementService(FatigueService()).move("east", ctx)

    assert "movement points" in ctx.messages[0]
    assert ctx.player.current_room_id == "tavern"


def test_movement_cost_depends_on_target_terrain_and_weather() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        _seed_rooms(session)
        square = session.get(Room, "square")
        assert square is not None
        square.terrain = "forest"
        player = _seed_player(session)
        session.commit()
        ctx = _build_context(session, player, ConnectionManager(), EventBus())

        cost = FatigueService().movement_cost(ctx, square)

    assert cost == 3.0


def _seed_rooms(session: Session) -> None:
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
    session.add(Exit(room_id="tavern", direction="east", target_room_id="square"))


def _seed_player(session: Session) -> Player:
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="tavern",
        respawn_room_id="tavern",
    )
    session.add(player)
    return player


def _build_context(
    session: Session,
    player: Player,
    manager: ConnectionManager,
    bus: EventBus,
) -> GameContext:
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
        rng=GameRng(),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=manager,
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
