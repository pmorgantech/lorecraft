from types import SimpleNamespace

from lorecraft.game.context import GameContext
from lorecraft.game.events import EventBus, GameEvent
from lorecraft.game.transaction import TransactionContext


def test_context_collects_messages_updates_and_emits_events() -> None:
    bus = EventBus()
    observed = []
    bus.on(GameEvent.PLAYER_MOVED, lambda event, ctx: observed.append((event.payload, ctx.session_id)))
    ctx = GameContext(
        player=SimpleNamespace(id="player-1"),
        room=SimpleNamespace(id="tavern"),
        clock=SimpleNamespace(game_epoch=0),
        player_repo=None,
        room_repo=None,
        item_repo=None,
        npc_repo=None,
        manager=None,
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(actor_id="player-1", correlation_id="session-1"),
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
