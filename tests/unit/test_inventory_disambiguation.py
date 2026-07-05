"""Tests for shortened item names, ambiguity prompts, and the key gallery fixture."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.parser import parse_command
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.services.inventory import InventoryService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.meters import MeterService
from tests.fixtures.disambig_fixtures import (
    DISAMBIG_ROOM_ID,
    SIMILAR_ITEM_SPECS,
    seed_disambig_gallery,
    similar_item_entities,
)


def _seed_gallery_player(session: Session) -> Player:
    seed_disambig_gallery(session, link=None)
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=DISAMBIG_ROOM_ID,
        respawn_room_id=DISAMBIG_ROOM_ID,
    )
    session.add(player)
    return player


def _build_context(session: Session, player: Player) -> GameContext:
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
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )


class TestItemRepoShortNames:
    def test_shortened_queries_match_word_subsets(self) -> None:
        engine = create_engine("sqlite://")
        create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

        with Session(engine) as session:
            seed_disambig_gallery(session, link=None)
            session.commit()
            items = ItemRepo(session)

            key_matches = items.search_in_room(DISAMBIG_ROOM_ID, "key")
            key_ids = {item.id for _, item in key_matches}
            assert key_ids == {
                "red_key",
                "iron_key",
                "rusty_iron_key",
                "steel_key",
                "cage_key",
            }

            assert len(items.search_in_room(DISAMBIG_ROOM_ID, "steel")) == 1
            assert items.search_in_room(DISAMBIG_ROOM_ID, "steel")[0][1].id == (
                "steel_key"
            )

            red_matches = items.search_in_room(DISAMBIG_ROOM_ID, "red")
            assert {item.id for _, item in red_matches} == {"red_key", "red_rose"}

            iron_matches = items.search_in_room(DISAMBIG_ROOM_ID, "iron")
            assert {item.id for _, item in iron_matches} == {
                "iron_key",
                "rusty_iron_key",
                "rusty_iron_sword",
            }

            assert len(items.search_in_room(DISAMBIG_ROOM_ID, "rusty iron key")) == 1
            assert (
                items.search_in_room(DISAMBIG_ROOM_ID, "rusty iron key")[0][1].id
                == "rusty_iron_key"
            )

    def test_alias_matches_item_not_named_by_alias(self) -> None:
        engine = create_engine("sqlite://")
        create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

        with Session(engine) as session:
            seed_disambig_gallery(session, link=None)
            session.commit()
            items = ItemRepo(session)

            blade_matches = items.search_in_room(DISAMBIG_ROOM_ID, "blade")
            assert {item.id for _, item in blade_matches} == {"rusty_iron_sword"}

            shortsword_matches = items.search_in_room(DISAMBIG_ROOM_ID, "shortsword")
            assert {item.id for _, item in shortsword_matches} == {"rusty_iron_sword"}


class TestInventoryAmbiguityPrompts:
    def test_take_key_prompts_numbered_choices(self) -> None:
        engine = create_engine("sqlite://")
        create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

        with Session(engine) as session:
            player = _seed_gallery_player(session)
            session.commit()
            ctx = _build_context(session, player)

            InventoryService().take_item("key", ctx)

        assert ctx.messages[0].startswith("Which do you mean?")
        assert "(1) Red Key" in ctx.messages[0]
        assert ctx.updates["disambig_pending"]["verb"] == "take"
        assert len(ctx.updates["disambig_pending"]["choices"]) == 5

    def test_take_rusty_iron_prompts_two_choices(self) -> None:
        engine = create_engine("sqlite://")
        create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

        with Session(engine) as session:
            player = _seed_gallery_player(session)
            session.commit()
            ctx = _build_context(session, player)

            InventoryService().take_item("rusty iron", ctx)

        assert "Rusty Iron Key" in ctx.messages[0]
        assert "Rusty Iron Sword" in ctx.messages[0]
        assert len(ctx.updates["disambig_pending"]["choices"]) == 2

    def test_take_specific_name_succeeds(self) -> None:
        engine = create_engine("sqlite://")
        create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

        with Session(engine) as session:
            player = _seed_gallery_player(session)
            session.commit()
            ctx = _build_context(session, player)

            InventoryService().take_item("steel key", ctx)
            session.commit()
            carried = StackRepo(session).stacks_for_owner("player", player.id)
            remaining = StackRepo(session).stacks_at(Location("room", DISAMBIG_ROOM_ID))

        assert ctx.messages == ["You take Steel Key."]
        assert [stack.item_id for stack in carried] == ["steel_key"]
        assert len(remaining) == len(SIMILAR_ITEM_SPECS) - 1


class TestParserAndInventoryIntegration:
    def test_parser_defers_take_ambiguity_to_inventory(self) -> None:
        class MockContext:
            get_visible_entities = staticmethod(lambda: similar_item_entities())
            get_inventory = staticmethod(lambda: [])

        result = parse_command("take key", context=MockContext())
        assert not result.error_message
        assert result.commands[0].roles.get("object") == "key"
        assert "object" not in result.commands[0].resolved_ids

    def test_command_engine_take_key_reaches_inventory_disambig(self) -> None:
        engine = create_engine("sqlite://")
        create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

        with Session(engine) as session:
            player = _seed_gallery_player(session)
            session.commit()
            ctx = _build_context(session, player)
            registry = CommandRegistry()
            from lorecraft.commands.inventory import register_inventory_commands

            register_inventory_commands(registry)
            cmd_engine = CommandEngine(registry, RuleEngine())

            cmd_engine.handle_command("take key", ctx)

        assert ctx.messages[0].startswith("Which do you mean?")
        assert ctx.updates["disambig_pending"]["verb"] == "take"

    def test_command_engine_examine_key_reaches_inventory_disambig(self) -> None:
        engine = create_engine("sqlite://")
        create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

        with Session(engine) as session:
            player = _seed_gallery_player(session)
            session.commit()
            ctx = _build_context(session, player)
            registry = CommandRegistry()
            from lorecraft.commands.inventory import register_inventory_commands

            register_inventory_commands(registry)
            cmd_engine = CommandEngine(registry, RuleEngine())

            cmd_engine.handle_command("examine key", ctx)

        assert ctx.messages[0].startswith("Which do you mean?")
        assert ctx.updates["disambig_pending"]["verb"] == "examine"
