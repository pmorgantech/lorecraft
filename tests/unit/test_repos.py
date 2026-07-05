from sqlmodel import Session, create_engine

from lorecraft.db import create_tables, database_url, sqlite_url
from lorecraft.engine.game.holders import Location
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.player import Player, PlayerStats, SaveSlot
from lorecraft.engine.models.session import PlayerSession
from lorecraft.engine.models.world import Exit, Item, NPC, Room
from lorecraft.engine.repos import AuditRepo, ItemRepo, NpcRepo, PlayerRepo, RoomRepo
from lorecraft.engine.services.item_location import ItemLocationService


def test_database_url_preserves_sqlalchemy_urls() -> None:
    postgres_url = "postgresql+psycopg://user:pass@localhost/lorecraft"

    assert database_url(postgres_url) == postgres_url
    assert sqlite_url(":memory:") == "sqlite://"
    assert sqlite_url("game.db") == "sqlite:///game.db"


def test_repos_round_trip_core_game_models() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        players = PlayerRepo(session)
        rooms = RoomRepo(session)
        items = ItemRepo(session)
        npcs = NpcRepo(session)

        rooms.add(
            Room(
                id="tavern",
                name="Tavern",
                description="A warm room.",
                map_x=0,
                map_y=0,
            )
        )
        rooms.add(
            Room(
                id="square",
                name="Square",
                description="A busy square.",
                map_x=1,
                map_y=0,
            )
        )
        session.add(Exit(room_id="tavern", direction="east", target_room_id="square"))
        players.add(
            Player(
                id="player-1",
                username="petem",
                current_room_id="tavern",
                respawn_room_id="tavern",
            )
        )
        players.save_stats(PlayerStats(player_id="player-1", max_hp=75))
        session.add(
            PlayerSession(
                id="session-1",
                player_id="player-1",
                connected_at=10.0,
            )
        )
        session.add(
            SaveSlot(
                player_id="player-1",
                slot_name="auto",
                saved_at=20.0,
                room_id="tavern",
            )
        )
        items.add(Item(id="gem", name="Gem", description="A bright gem."))
        session.commit()
        ItemLocationService(session).spawn("gem", Location("room", "tavern"))
        npcs.add(
            NPC(
                id="keeper",
                name="Keeper",
                description="The tavern keeper.",
                current_room_id="tavern",
                home_room_id="tavern",
                dialogue_tree_id="keeper_intro",
            )
        )
        session.commit()

        assert players.by_username("petem").id == "player-1"
        assert players.stats("player-1").max_hp == 75
        assert players.active_session("player-1").id == "session-1"
        assert [slot.slot_name for slot in players.save_slots("player-1")] == ["auto"]
        assert rooms.active("tavern").name == "Tavern"
        assert rooms.exit("tavern", "east").target_room_id == "square"
        assert [stack.item_id for stack, _ in items.items_in_room("tavern")] == ["gem"]
        assert [npc.id for npc in npcs.in_room("tavern")] == ["keeper"]


def test_item_repo_matches_plural_queries_against_plural_item_names() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        items = ItemRepo(session)
        rooms = RoomRepo(session)
        rooms.add(
            Room(
                id="market", name="Market", description="Busy stalls.", map_x=0, map_y=0
            )
        )
        items.add(
            Item(
                id="dried_herbs",
                name="Bundle of Dried Herbs",
                description="Fragrant.",
                takeable=True,
            )
        )
        items.add(
            Item(
                id="copper_coin",
                name="Worn Copper Coin",
                description="Tarnished.",
                takeable=True,
            )
        )
        session.commit()
        item_location = ItemLocationService(session)
        item_location.spawn("dried_herbs", Location("room", "market"), 3)
        item_location.spawn("copper_coin", Location("room", "market"), 2)
        session.commit()

        herb_matches = items.search_in_room("market", "herbs")
        coin_matches = items.search_in_room("market", "coins")

    assert len(herb_matches) == 1
    assert herb_matches[0][1].id == "dried_herbs"
    assert len(coin_matches) == 1
    assert coin_matches[0][1].id == "copper_coin"


def test_item_repo_get_many_batch_loads_deduplicates_and_skips_missing() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        items = ItemRepo(session)
        items.add(Item(id="gem", name="Gem", description="Bright."))
        items.add(Item(id="coin", name="Coin", description="Round."))
        session.commit()

        # Duplicate ids collapse; a missing id is simply absent from the result.
        loaded = items.get_many(["gem", "coin", "gem", "ghost"])

        assert set(loaded) == {"gem", "coin"}
        assert loaded["gem"].name == "Gem"
        assert loaded["coin"].name == "Coin"
        # Empty input short-circuits to an empty dict.
        assert items.get_many([]) == {}


def test_item_repo_name_index_projects_name_and_aliases() -> None:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))

    with Session(engine) as session:
        items = ItemRepo(session)
        items.add(Item(id="gem", name="Gem", description="Bright.", aliases=["stone"]))
        items.add(Item(id="coin", name="Coin", description="Round."))
        session.commit()

        # Duplicate ids collapse; a missing id is absent; aliases come through.
        index = items.name_index(["gem", "coin", "gem", "ghost"])

        assert set(index) == {"gem", "coin"}
        assert index["gem"] == ("Gem", ["stone"])
        assert index["coin"] == ("Coin", [])
        # Empty input short-circuits to an empty dict.
        assert items.name_index([]) == {}

        # Returned alias lists are copies — mutating one must not corrupt the row.
        index["gem"][1].append("mutated")
        assert items.name_index(["gem"])["gem"] == ("Gem", ["stone"])


def test_audit_repo_uses_separate_audit_session() -> None:
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=create_engine("sqlite://"), audit_engine=audit_engine)

    with Session(audit_engine) as session:
        audit = AuditRepo(session)
        audit.record(
            AuditEvent(
                transaction_id="txn-1",
                correlation_id="session-1",
                actor_id="player-1",
                event_type="player_moved",
                source_type="PLAYER_COMMAND",
                room_id="tavern",
                game_time=1.0,
                real_time=2.0,
                summary="Player moved.",
            )
        )
        session.commit()

        assert [event.summary for event in audit.for_transaction("txn-1")] == [
            "Player moved."
        ]
        assert [event.transaction_id for event in audit.for_actor("player-1")] == [
            "txn-1"
        ]
