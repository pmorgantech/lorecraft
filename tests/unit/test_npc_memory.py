"""Tests for NPC memory (Sprint 30.1): the `remember` dialogue side effect,
the `npc_remembers` dialogue condition, and the `npc_remembers` quest
condition type -- all scoped per-(player, npc)."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.features.npc_memory.conditions import register as _register_npc_memory
from lorecraft.db import create_tables
from lorecraft.game import quest_conditions
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.models.dialogue import DialogueTree
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import NPC, Room
from lorecraft.npc.dialogue import DialogueService, current_npc_id
from lorecraft.repos.dialogue_repo import DialogueRepo
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.features.npc_memory.repo import NpcMemoryRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.repos.quest_repo import QuestRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.services.meters import MeterService

# NPC-memory conditions/side effect used to register as an import side effect;
# they now register via the npc_memory feature's register(). Call it once here.
_register_npc_memory()

_THOR_TREE = {
    "root_node": "greeting",
    "nodes": {
        "greeting": {
            "text": "Need something forged?",
            "side_effects": {},
            "choices": [
                {
                    "label": "I fixed your bellows.",
                    "next_node": "thanked",
                    "required_flags": [],
                    "forbidden_flags": [],
                    "side_effects": {"remember": ["helped"]},
                },
                {
                    "label": "Remember when I helped you?",
                    "next_node": "recalled",
                    "npc_remembers": ["helped"],
                    "side_effects": {},
                },
                {
                    "label": "Goodbye.",
                    "next_node": None,
                    "side_effects": {},
                },
            ],
        },
        "thanked": {"text": "Much obliged.", "side_effects": {}, "choices": []},
        "recalled": {"text": "Aye, I remember.", "side_effects": {}, "choices": []},
    },
}

_MIRA_TREE = {
    "root_node": "greeting",
    "nodes": {
        "greeting": {
            "text": "Welcome to the inn.",
            "side_effects": {},
            "choices": [
                {
                    "label": "Remember when I helped you?",
                    "next_node": "recalled",
                    "npc_remembers": ["helped"],
                    "side_effects": {},
                },
                {"label": "Goodbye.", "next_node": None, "side_effects": {}},
            ],
        },
        "recalled": {"text": "Aye, I remember.", "side_effects": {}, "choices": []},
    },
}


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def _seed(session: Session) -> Player:
    session.add(
        Room(id="forge", name="Forge", description="A hot room.", map_x=0, map_y=0)
    )
    session.add(
        NPC(
            id="thor",
            name="Thor",
            description="A blacksmith.",
            current_room_id="forge",
            home_room_id="forge",
            dialogue_tree_id="thor_tree",
        )
    )
    session.add(
        NPC(
            id="mira",
            name="Mira",
            description="An innkeeper.",
            current_room_id="forge",
            home_room_id="forge",
            dialogue_tree_id="mira_tree",
        )
    )
    session.add(DialogueTree(id="thor_tree", tree_data=_THOR_TREE))
    session.add(DialogueTree(id="mira_tree", tree_data=_MIRA_TREE))
    player = Player(
        id="p1", username="hero", current_room_id="forge", respawn_room_id="forge"
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
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=GameRng(),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        quest_repo=QuestRepo(session),
        dialogue_repo=DialogueRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s"),
        session_id="s",
    )


class TestRememberSideEffect:
    def test_remember_sets_memory_scoped_to_current_npc(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed(session)
            session.commit()
            ctx = _ctx(session, player)

            DialogueService().start("thor", ctx)
            DialogueService().choose(1, ctx)  # "I fixed your bellows." -> remember
            session.commit()

            assert NpcMemoryRepo(session).remembers("p1", "thor", "helped")

    def test_remember_is_noop_outside_dialogue(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed(session)
            session.commit()
            ctx = _ctx(session, player)
            assert current_npc_id(ctx) is None

            from lorecraft.npc.side_effects import get_registry

            get_registry().apply({"remember": ["helped"]}, ctx)
            session.commit()

            assert not NpcMemoryRepo(session).remembers("p1", "thor", "helped")


class TestNpcRemembersCondition:
    def test_choice_hidden_until_remembered(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed(session)
            session.commit()
            ctx = _ctx(session, player)

            DialogueService().start("thor", ctx)
            panel = ctx.updates["dialogue"]
            assert panel is not None
            labels = [c["label"] for c in panel["choices"]]
            assert "Remember when I helped you?" not in labels

    def test_choice_visible_after_remembered(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed(session)
            session.commit()
            ctx = _ctx(session, player)
            NpcMemoryRepo(session).set("p1", "thor", "helped", True)
            session.commit()

            DialogueService().start("thor", ctx)
            panel = ctx.updates["dialogue"]
            assert panel is not None
            labels = [c["label"] for c in panel["choices"]]
            assert "Remember when I helped you?" in labels

    def test_memory_is_scoped_per_npc_not_global(self) -> None:
        """Remembering "helped" for Thor must not leak into Mira's dialogue --
        the whole point of NPC memory over a global Player.flags entry."""
        e = _engine()
        with Session(e) as session:
            player = _seed(session)
            session.commit()
            ctx = _ctx(session, player)
            NpcMemoryRepo(session).set("p1", "thor", "helped", True)
            session.commit()

            DialogueService().start("mira", ctx)
            panel = ctx.updates["dialogue"]
            assert panel is not None
            labels = [c["label"] for c in panel["choices"]]
            assert "Remember when I helped you?" not in labels


class TestQuestNpcRemembersCondition:
    def test_quest_condition_checks_memory_for_named_npc(self) -> None:
        e = _engine()
        with Session(e) as session:
            player = _seed(session)
            session.commit()
            ctx = _ctx(session, player)

            cond = {"type": "npc_remembers", "npc_id": "thor", "flag": "helped"}
            assert quest_conditions.get_registry().evaluate_all([cond], ctx) is False

            NpcMemoryRepo(session).set("p1", "thor", "helped", True)
            session.commit()
            assert quest_conditions.get_registry().evaluate_all([cond], ctx) is True
