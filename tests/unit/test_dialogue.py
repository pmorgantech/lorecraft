"""Unit tests for the dialogue tree walker."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.events import EventBus
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.dialogue import DialogueTree
from lorecraft.models.player import Player
from lorecraft.models.world import NPC, Room
from lorecraft.npc.dialogue import DialogueService, _NPC_KEY, _NODE_KEY
from lorecraft.repos.dialogue_repo import DialogueRepo
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.quest_repo import QuestRepo
from lorecraft.repos.room_repo import RoomRepo

_TREE_DATA = {
    "root_node": "greeting",
    "nodes": {
        "greeting": {
            "text": "Hello, traveler.",
            "side_effects": {},
            "choices": [
                {
                    "label": "Tell me the news.",
                    "next_node": "news",
                    "required_flags": [],
                    "forbidden_flags": [],
                    "side_effects": {"set_flags": ["asked_news"]},
                },
                {
                    "label": "Goodbye.",
                    "next_node": None,
                    "required_flags": [],
                    "forbidden_flags": [],
                    "side_effects": {"end_dialogue": True},
                },
            ],
        },
        "news": {
            "text": "Strange things afoot.",
            "side_effects": {},
            "choices": [],
        },
    },
}


def _seed(session: Session) -> Player:
    session.add(
        Room(id="tavern", name="Tavern", description="A warm room.", map_x=0, map_y=0)
    )
    session.add(
        NPC(
            id="keeper",
            name="Keeper",
            description="A guard.",
            current_room_id="tavern",
            home_room_id="tavern",
            dialogue_tree_id="test_tree",
        )
    )
    session.add(DialogueTree(id="test_tree", tree_data=_TREE_DATA))
    player = Player(
        id="p1",
        username="hero",
        current_room_id="tavern",
        respawn_room_id="tavern",
    )
    session.add(player)
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
        npc_repo=NpcRepo(session),
        quest_repo=QuestRepo(session),
        dialogue_repo=DialogueRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s"),
        session_id="s",
    )


def _engine() -> object:
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def test_start_shows_root_node_and_choices() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)

        DialogueService().start("keeper", ctx)

    assert "Keeper: Hello, traveler." in ctx.messages
    dialogue = ctx.updates.get("dialogue")
    assert isinstance(dialogue, dict)
    assert dialogue["npc_name"] == "Keeper"
    assert len(dialogue["choices"]) == 2


def test_start_unknown_npc_gives_error() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)

        DialogueService().start("nobody", ctx)

    assert any("isn't here" in m for m in ctx.messages)
    assert "dialogue" not in ctx.updates


def test_choose_advances_to_next_node_and_applies_side_effects() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)
        service = DialogueService()

        service.start("keeper", ctx)
        ctx.messages.clear()
        ctx.updates.clear()

        service.choose(1, ctx)

        assert player.flags.get("asked_news") is True
        # news node has no choices → terminal → dialogue ends
        assert ctx.updates.get("dialogue") is None
        assert "Keeper: Strange things afoot." in ctx.messages


def test_choose_goodbye_ends_dialogue() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)
        service = DialogueService()

        service.start("keeper", ctx)
        ctx.updates.clear()

        service.choose(2, ctx)  # "Goodbye." has end_dialogue side effect

    assert player.flags.get(_NPC_KEY) is None
    assert ctx.updates.get("dialogue") is None


def test_choose_out_of_range_says_error() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)
        service = DialogueService()

        service.start("keeper", ctx)
        ctx.messages.clear()

        service.choose(99, ctx)

    assert any("Choose between" in m for m in ctx.messages)


def test_choose_without_active_dialogue() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)

        DialogueService().choose(1, ctx)

    assert any("not in a conversation" in m for m in ctx.messages)


def test_end_clears_flags_and_update() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.commit()
        ctx = _ctx(session, player)
        service = DialogueService()

        service.start("keeper", ctx)
        assert player.flags.get(_NPC_KEY) is not None

        service.end(ctx)

    assert player.flags.get(_NPC_KEY) is None
    assert player.flags.get(_NODE_KEY) is None
    assert ctx.updates.get("dialogue") is None


def test_required_flags_hide_gated_choice() -> None:
    e = _engine()
    with Session(e) as session:
        player = _seed(session)
        session.merge(
            DialogueTree(
                id="gated_tree",
                tree_data={
                    "root_node": "start",
                    "nodes": {
                        "start": {
                            "text": "What do you want?",
                            "side_effects": {},
                            "choices": [
                                {
                                    "label": "Secret option",
                                    "next_node": None,
                                    "required_flags": ["has_secret"],
                                    "forbidden_flags": [],
                                    "side_effects": {},
                                },
                                {
                                    "label": "Plain option",
                                    "next_node": None,
                                    "required_flags": [],
                                    "forbidden_flags": [],
                                    "side_effects": {},
                                },
                            ],
                        }
                    },
                },
            )
        )
        session.merge(
            NPC(
                id="gatekeeper",
                name="Gatekeeper",
                description="A mysterious figure.",
                current_room_id="tavern",
                home_room_id="tavern",
                dialogue_tree_id="gated_tree",
            )
        )
        session.commit()
        ctx = _ctx(session, player)

        DialogueService().start("gatekeeper", ctx)

    dialogue = ctx.updates["dialogue"]
    assert isinstance(dialogue, dict)
    assert len(dialogue["choices"]) == 1
    assert dialogue["choices"][0]["label"] == "Plain option"
