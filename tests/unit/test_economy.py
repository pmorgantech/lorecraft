"""Tests for Sprint 28.1: currency, item pricing, and NPC vendor shops
(buy/sell/list/appraise)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

import lorecraft.game.economy_holders  # noqa: F401 -- registration side effects
from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.game.context import GameContext
from lorecraft.game.engine import CommandEngine
from lorecraft.game.events import Event, EventBus, GameEvent
from lorecraft.game.holders import Location
from lorecraft.game.registry import CommandRegistry
from lorecraft.game.rng import GameRng
from lorecraft.game.rules import RuleEngine
from lorecraft.game.transaction import TransactionContext
from lorecraft.models.economy import RegionPricing, Shop, ShopStock
from lorecraft.repos.economy_repo import EconomyRepo
from lorecraft.models.world import Item, NPC, Room
from lorecraft.models.player import Player, PlayerStats
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo
from lorecraft.repos.stack_repo import StackRepo
from lorecraft.services.container import ServiceContainer
from lorecraft.services.economy import EconomyService
from lorecraft.services.effects import EffectService
from lorecraft.services.item_location import ItemLocationService
from lorecraft.services.ledger import LedgerService
from lorecraft.services.meters import MeterService
from lorecraft.services.restock import RestockService

ROOM_ID = "market"
SHOP_ID = "shop:shopkeep"
NPC_ID = "shopkeep"


def _seed(session: Session) -> None:
    session.add(
        Room(
            id=ROOM_ID,
            name="Market",
            description="d",
            map_x=0,
            map_y=0,
            area_id="market_district",
        )
    )
    session.add(
        NPC(
            id=NPC_ID,
            name="Shopkeep",
            description="d",
            current_room_id=ROOM_ID,
            home_room_id=ROOM_ID,
            dialogue_tree_id="",
        )
    )
    session.add(
        Item(
            id="salt_sack",
            name="sack of salt",
            description="d",
            value=20,
            quality="common",
            tradeable=True,
            category="trade_good",
        )
    )
    session.add(
        Item(
            id="gem",
            name="shiny gem",
            description="d",
            value=100,
            quality="rare",
            tradeable=True,
            category="trade_good",
        )
    )
    session.add(
        Item(
            id="cursed_ring",
            name="cursed ring",
            description="d",
            value=50,
            tradeable=True,
            bound=True,
            category="trade_good",
        )
    )
    session.add(
        Item(
            id="rock",
            name="plain rock",
            description="d",
            value=1,
            tradeable=True,
        )
    )
    session.add(
        Shop(
            id=SHOP_ID,
            npc_id=NPC_ID,
            name="Saltmarsh General Store",
            buys_categories=["trade_good"],
            sell_ratio=0.5,
            region_mult=1.0,
        )
    )
    session.add(ShopStock(shop_id=SHOP_ID, item_id="salt_sack", quantity=2))
    session.add(ShopStock(shop_id=SHOP_ID, item_id="gem", quantity=-1))
    session.commit()


def _build_engine_and_ctx() -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    _seed(session)
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id))
    session.commit()

    room = session.get(Room, ROOM_ID)
    assert room is not None
    bus = EventBus()
    registry = CommandRegistry()
    services_container = ServiceContainer.build()
    register_all_commands(registry, services_container)

    ctx = GameContext(
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
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=bus,
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
    return CommandEngine(registry, RuleEngine()), ctx, session


@pytest.fixture
def built() -> Iterator[tuple[CommandEngine, GameContext, Session]]:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    yield cmd_engine, ctx, session
    session.close()


class TestPricing:
    def test_buy_price_scales_with_quality(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        service = EconomyService()
        shop = session.get(Shop, SHOP_ID)
        salt = session.get(Item, "salt_sack")
        gem = session.get(Item, "gem")
        assert shop is not None and salt is not None and gem is not None

        assert service.buy_price(ctx, shop, NPC_ID, salt) == 20  # common: 1.0x
        assert service.buy_price(ctx, shop, NPC_ID, gem) == 250  # rare: 2.5x

    def test_sell_price_applies_sell_ratio(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, _ctx, session = built
        service = EconomyService()
        shop = session.get(Shop, SHOP_ID)
        assert shop is not None

        assert service.sell_price(shop, 20) == 10  # sell_ratio 0.5

    def test_bartering_skill_discounts_price(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        stats = session.get(PlayerStats, ctx.player.id)
        assert stats is not None
        stats.skills = {"bartering": 100}
        session.add(stats)
        session.commit()

        service = EconomyService()
        shop = session.get(Shop, SHOP_ID)
        salt = session.get(Item, "salt_sack")
        assert shop is not None and salt is not None

        # 100 * 0.0025 = 0.25, capped at BARTER_DISCOUNT_CAP = 0.25
        assert service.buy_price(ctx, shop, NPC_ID, salt) == 15


class TestListShop:
    def test_list_shows_stock_and_prices(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("list", ctx)

        joined = "\n".join(ctx.messages)
        assert "Saltmarsh General Store" in joined
        assert "sack of salt" in joined and "20 coins" in joined
        assert "shiny gem" in joined and "250 coins" in joined
        assert "unlimited" in joined

    def test_no_shop_in_room(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        other_room = Room(id="empty", name="Empty", description="d", map_x=5, map_y=5)
        session.add(other_room)
        session.commit()
        ctx.room = other_room

        cmd_engine.handle_command("list", ctx)

        assert ctx.messages == ["There's no shop here."]


class TestBuy:
    def test_buy_moves_coins_and_spawns_item(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ctx.ledger.credit(session, "player", ctx.player.id, 100)
        session.commit()

        cmd_engine.handle_command("buy salt sack", ctx)

        assert ctx.ledger.balance_of(session, "player", ctx.player.id) == 80
        assert ctx.ledger.balance_of(session, "shop", SHOP_ID) == 20
        assert (
            ctx.stack_repo.quantity_of(Location("player", ctx.player.id), "salt_sack")
            == 1
        )
        stock = EconomyRepo(session).find_stock(SHOP_ID, "salt_sack")
        assert stock is not None and stock.quantity == 1

    def test_buy_insufficient_funds(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built

        cmd_engine.handle_command("buy salt sack", ctx)

        assert any("afford" in m for m in ctx.messages)
        assert ctx.ledger.balance_of(session, "player", ctx.player.id) == 0

    def test_buy_out_of_stock(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ctx.ledger.credit(session, "player", ctx.player.id, 1000)
        session.commit()

        cmd_engine.handle_command("buy 3 salt sack", ctx)

        assert any("doesn't have 3" in m for m in ctx.messages)

    def test_buy_unlimited_stock_never_decrements(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ctx.ledger.credit(session, "player", ctx.player.id, 1000)
        session.commit()

        cmd_engine.handle_command("buy gem", ctx)

        stock = EconomyRepo(session).find_stock(SHOP_ID, "gem")
        assert stock is not None and stock.quantity == -1


class TestSell:
    def test_sell_destroys_stack_and_pays_player(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ctx.item_location.spawn("salt_sack", Location("player", ctx.player.id))
        ctx.ledger.credit(session, "shop", SHOP_ID, 100)
        session.commit()

        cmd_engine.handle_command("sell salt sack", ctx)

        assert ctx.ledger.balance_of(session, "player", ctx.player.id) == 10  # 20*0.5
        assert (
            ctx.stack_repo.quantity_of(Location("player", ctx.player.id), "salt_sack")
            == 0
        )

    def test_sell_rejects_bound_item(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ctx.item_location.spawn("cursed_ring", Location("player", ctx.player.id))
        session.commit()

        cmd_engine.handle_command("sell cursed ring", ctx)

        assert any("won't buy" in m for m in ctx.messages)

    def test_sell_rejects_uncategorized_item(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ctx.item_location.spawn("rock", Location("player", ctx.player.id))
        session.commit()

        cmd_engine.handle_command("sell rock", ctx)

        assert any("isn't interested" in m for m in ctx.messages)

    def test_sell_rejects_when_shop_lacks_cash(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ctx.item_location.spawn("gem", Location("player", ctx.player.id))
        session.commit()

        cmd_engine.handle_command("sell shiny gem", ctx)

        assert any("can't afford" in m for m in ctx.messages)
        assert ctx.stack_repo.quantity_of(Location("player", ctx.player.id), "gem") == 1


class TestAppraise:
    def test_appraise_shows_estimated_value(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        ctx.item_location.spawn("gem", Location("player", ctx.player.id))
        session.commit()

        cmd_engine.handle_command("appraise gem", ctx)

        assert any("250 coins" in m for m in ctx.messages)

    def test_appraise_unknown_item(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("appraise unicorn", ctx)

        assert any("don't see" in m for m in ctx.messages)


class TestRegionalPricing:
    def test_region_mult_scales_price(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        session.add(RegionPricing(area_id="market_district", region_mult=1.5))
        session.commit()

        service = EconomyService()
        shop = session.get(Shop, SHOP_ID)
        salt = session.get(Item, "salt_sack")
        assert shop is not None and salt is not None

        assert service.buy_price(ctx, shop, NPC_ID, salt) == 30  # 20 * 1.5

    def test_per_item_bias_scales_price(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        session.add(
            RegionPricing(
                area_id="market_district", region_mult=1.0, bias={"salt_sack": 0.5}
            )
        )
        session.commit()

        service = EconomyService()
        shop = session.get(Shop, SHOP_ID)
        salt = session.get(Item, "salt_sack")
        gem = session.get(Item, "gem")
        assert shop is not None and salt is not None and gem is not None

        assert service.buy_price(ctx, shop, NPC_ID, salt) == 10  # 20 * 0.5 bias
        assert service.buy_price(ctx, shop, NPC_ID, gem) == 250  # unbiased, unchanged

    def test_no_region_pricing_row_defaults_neutral(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        service = EconomyService()
        shop = session.get(Shop, SHOP_ID)
        salt = session.get(Item, "salt_sack")
        assert shop is not None and salt is not None

        assert service.buy_price(ctx, shop, NPC_ID, salt) == 20


class TestDemandPricing:
    def test_depleted_stock_costs_more(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        stock = EconomyRepo(session).find_stock(SHOP_ID, "salt_sack")
        assert stock is not None
        stock.restock_to = 10
        stock.quantity = 0  # fully depleted
        session.add(stock)
        session.commit()

        service = EconomyService()
        shop = session.get(Shop, SHOP_ID)
        salt = session.get(Item, "salt_sack")
        assert shop is not None and salt is not None

        # ratio 0 -> demand_mult = min(2.0, 1.5 cap) = 1.5
        assert service.buy_price(ctx, shop, NPC_ID, salt, stock=stock) == 30

    def test_flooded_stock_costs_less(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        stock = EconomyRepo(session).find_stock(SHOP_ID, "salt_sack")
        assert stock is not None
        stock.restock_to = 10
        stock.quantity = 20  # double the target -> flooded
        session.add(stock)
        session.commit()

        service = EconomyService()
        shop = session.get(Shop, SHOP_ID)
        salt = session.get(Item, "salt_sack")
        assert shop is not None and salt is not None

        # ratio 2.0 -> demand_mult = max(2.0 - 2.0, 0.5 floor) = 0.5
        assert service.buy_price(ctx, shop, NPC_ID, salt, stock=stock) == 10

    def test_unlimited_stock_has_no_demand_adjustment(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        stock = EconomyRepo(session).find_stock(SHOP_ID, "gem")
        assert stock is not None and stock.quantity == -1

        service = EconomyService()
        shop = session.get(Shop, SHOP_ID)
        gem = session.get(Item, "gem")
        assert shop is not None and gem is not None

        assert service.buy_price(ctx, shop, NPC_ID, gem, stock=stock) == 250


class TestRestock:
    def test_restock_triggers_after_configured_ticks(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        stock = EconomyRepo(session).find_stock(SHOP_ID, "salt_sack")
        assert stock is not None
        stock.quantity = 0
        stock.restock_to = 5
        stock.restock_every_ticks = 3
        session.add(stock)
        session.commit()

        service = RestockService(session.get_bind())
        bus = EventBus()
        service.register(bus)
        event = Event(GameEvent.TIME_ADVANCED, {"current_epoch": 0.0})

        bus.emit(event, ctx=None)
        bus.emit(event, ctx=None)
        # RestockService opens its own session per sweep; the long-lived
        # fixture session must expire its cached row to see those commits
        # (same pattern as test_meters.py's regen-sweep tests).
        session.expire_all()
        stock_mid = EconomyRepo(session).find_stock(SHOP_ID, "salt_sack")
        assert stock_mid is not None and stock_mid.quantity == 0  # not yet due

        bus.emit(event, ctx=None)
        session.expire_all()
        stock_after = EconomyRepo(session).find_stock(SHOP_ID, "salt_sack")
        assert stock_after is not None and stock_after.quantity == 5
        assert stock_after.ticks_since_restock == 0

    def test_stock_without_restock_schedule_is_untouched(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        stock = EconomyRepo(session).find_stock(SHOP_ID, "salt_sack")
        assert stock is not None
        assert stock.restock_every_ticks == 0

        service = RestockService(session.get_bind())
        bus = EventBus()
        service.register(bus)
        bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 0.0}), ctx=None)

        stock_after = EconomyRepo(session).find_stock(SHOP_ID, "salt_sack")
        assert stock_after is not None and stock_after.quantity == 2  # unchanged
