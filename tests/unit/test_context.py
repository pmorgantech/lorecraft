from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.events import EventBus, GameEvent
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.player import Player
from lorecraft.models.world import Room
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo


def test_context_collects_messages_updates_and_emits_events() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    bus = EventBus()
    observed = []
    bus.on(
        GameEvent.PLAYER_MOVED,
        lambda event, ctx: observed.append((event.payload, ctx.session_id)),
    )
    manager = ConnectionManager()

    with Session(engine) as session:
        player_repo = PlayerRepo(session)
        room_repo = RoomRepo(session)
        player = Player(
            id="player-1",
            username="petem",
            current_room_id="tavern",
            respawn_room_id="tavern",
        )
        room = Room(
            id="tavern",
            name="Tavern",
            description="A warm room.",
            map_x=0,
            map_y=0,
        )
        ctx = GameContext(
            player=player,
            room=room,
            clock=None,
            player_repo=player_repo,
            room_repo=room_repo,
            item_repo=ItemRepo(session),
            npc_repo=NpcRepo(session),
            manager=manager,
            bus=bus,
            audit=None,
            transaction=TransactionContext.create(
                actor_id="player-1", correlation_id="session-1"
            ),
            session_id="session-1",
        )

        ctx.say("You move north.")
        ctx.tell_room("Player leaves north.")
        ctx.push_update("room", "square")
        ctx.emit(GameEvent.PLAYER_MOVED, room_id="square")

        assert ctx.messages == ["You move north."]
        assert ctx.room_messages == ["Player leaves north."]
        assert ctx.updates == {"room": "square"}
        assert observed == [({"room_id": "square"}, "session-1")]
