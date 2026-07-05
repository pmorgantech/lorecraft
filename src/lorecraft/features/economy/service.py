"""Vendor shop economy: pricing, buy/sell/list/appraise (Sprint 28.1-28.2).

See docs/trade_economy.md. Prices are derived at runtime, never stored,
matching the engine's derived-stat convention (engine_core.md §3.5). Every
coin/item movement goes through LedgerService.execute_exchange -- this
service never mutates a CoinBalance or ItemStack directly.

Regional pricing (§5): a room's area has an optional `RegionPricing` (world
YAML `economy.regions`) contributing an area-wide `region_mult` and a
per-item `bias` multiplier; `Shop.region_mult` is a further per-shop
adjustment on top (not a full override). Demand (§6): `_demand_mult` reads
current stock against `restock_to` -- depleted stock costs more, flooded
stock costs less, bounded to [DEMAND_MULT_MIN, DEMAND_MULT_MAX]. Restocking
itself is services/restock.py's scheduler-driven sweep.

`appraise` is not skill-gated in this cut (the doc's own §13 leaves this an
open question); it shows the item's derived base value outright, without
region/demand/discount adjustments (a rough, shop-independent estimate).
"""

from __future__ import annotations

from lorecraft.errors import ConflictError
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.grammar import score_match
from lorecraft.engine.game.holders import Location
from lorecraft.features.economy.models import Shop, ShopStock
from lorecraft.engine.models.world import Item, NPC
from lorecraft.features.economy.repo import EconomyRepo
from lorecraft.features.inventory.service import parse_item_target
from lorecraft.engine.services.ledger import ExchangeLeg, LedgerService
from lorecraft.features.reputation.service import ReputationService
from lorecraft.features.skills.service import SkillService

QUALITY_MULTIPLIERS = {
    "common": 1.0,
    "fine": 1.3,
    "superior": 1.7,
    "rare": 2.5,
    "legendary": 4.0,
}

BARTER_DISCOUNT_CAP = 0.25
BARTER_DISCOUNT_PER_LEVEL = 0.0025
REP_DISCOUNT_CAP = 0.25
REP_DISCOUNT_PER_STANDING = 0.0025
MATCH_THRESHOLD = 0.5

DEMAND_MULT_MIN = 0.5
DEMAND_MULT_MAX = 1.5


class EconomyService:
    def __init__(
        self,
        ledger: LedgerService | None = None,
        skills: SkillService | None = None,
        reputation: ReputationService | None = None,
    ) -> None:
        self.ledger = ledger or LedgerService()
        self.skills = skills or SkillService()
        self.reputation = reputation or ReputationService()

    # -- shop/item lookup --------------------------------------------

    def _shop_here(self, ctx: GameContext) -> tuple[Shop, NPC] | None:
        repo = EconomyRepo(ctx.session)
        for npc in ctx.npc_repo.in_room(ctx.room.id):
            shop = repo.shop_for_npc(npc.id)
            if shop is not None:
                return shop, npc
        return None

    def _best_match(self, query: str, candidates: list[Item]) -> Item | None:
        scored = [
            (score_match(query, item.name, item.aliases), item) for item in candidates
        ]
        scored = [pair for pair in scored if pair[0] >= MATCH_THRESHOLD]
        if not scored:
            return None
        return max(scored, key=lambda pair: pair[0])[1]

    # -- pricing --------------------------------------------------

    def _barter_discount(self, ctx: GameContext) -> float:
        level = self.skills.get_level(ctx.session, ctx.player.id, "bartering")
        return min(BARTER_DISCOUNT_CAP, level * BARTER_DISCOUNT_PER_LEVEL)

    def _rep_discount(self, ctx: GameContext, npc_id: str) -> float:
        standing = self.reputation.standing_of(
            ctx.session, ctx.player.id, "npc", npc_id
        )
        return min(REP_DISCOUNT_CAP, max(0, standing) * REP_DISCOUNT_PER_STANDING)

    def _region_mult_and_bias(
        self, ctx: GameContext, item_id: str
    ) -> tuple[float, float]:
        region = EconomyRepo(ctx.session).region_for_area(ctx.room.area_id)
        if region is None:
            return 1.0, 1.0
        bias = region.bias.get(item_id, 1.0)
        bias_mult = bias if isinstance(bias, (int, float)) else 1.0
        return region.region_mult, float(bias_mult)

    def _demand_mult(self, stock: ShopStock | None) -> float:
        """Depleted stock costs more, flooded stock costs less (§6); a shop
        with no restock target (restock_to <= 0) or unlimited stock (-1)
        tracks no scarcity."""
        if stock is None or stock.quantity < 0 or stock.restock_to <= 0:
            return 1.0
        ratio = stock.quantity / stock.restock_to
        return max(DEMAND_MULT_MIN, min(DEMAND_MULT_MAX, 2.0 - ratio))

    def buy_price(
        self,
        ctx: GameContext,
        shop: Shop,
        npc_id: str,
        item: Item,
        *,
        stock: ShopStock | None = None,
    ) -> int:
        quality_mult = QUALITY_MULTIPLIERS.get(item.quality, 1.0)
        region_mult, bias_mult = self._region_mult_and_bias(ctx, item.id)
        demand_mult = self._demand_mult(stock)
        discount = (1 - self._barter_discount(ctx)) * (
            1 - self._rep_discount(ctx, npc_id)
        )
        return max(
            0,
            round(
                item.value
                * quality_mult
                * region_mult
                * shop.region_mult
                * bias_mult
                * demand_mult
                * discount
            ),
        )

    def sell_price(self, shop: Shop, buy_price_value: int) -> int:
        return max(0, round(buy_price_value * shop.sell_ratio))

    # -- commands --------------------------------------------------

    def list_shop(self, ctx: GameContext) -> None:
        found = self._shop_here(ctx)
        if found is None:
            ctx.say("There's no shop here.")
            return
        shop, npc = found
        stock_rows = [
            stock
            for stock in EconomyRepo(ctx.session).stock_for_shop(shop.id)
            if stock.quantity != 0
        ]
        if not stock_rows:
            ctx.say(f"{shop.name} has nothing for sale right now.")
            return
        lines = [f"{shop.name}:"]
        for stock in stock_rows:
            item = ctx.item_repo.get(stock.item_id)
            if item is None:
                continue
            price = self.buy_price(ctx, shop, npc.id, item, stock=stock)
            qty_label = "unlimited" if stock.quantity < 0 else str(stock.quantity)
            lines.append(f"  {item.name} -- {price} coins ({qty_label} in stock)")
        ctx.say("\n".join(lines))

    def buy(self, noun: str | None, ctx: GameContext) -> None:
        if not noun:
            ctx.say("Buy what?")
            return
        found = self._shop_here(ctx)
        if found is None:
            ctx.say("There's no shop here.")
            return
        shop, npc = found
        target = parse_item_target(noun)

        repo = EconomyRepo(ctx.session)
        candidates: dict[str, Item] = {}
        for stock in repo.stock_for_shop(shop.id):
            if stock.quantity == 0:
                continue
            item = ctx.item_repo.get(stock.item_id)
            if item is not None:
                candidates[item.id] = item
        item = self._best_match(target.query, list(candidates.values()))
        if item is None:
            ctx.say(f"{shop.name} doesn't have that.")
            return
        stock = repo.find_stock(shop.id, item.id)
        assert stock is not None

        quantity = target.quantity
        if stock.quantity >= 0 and stock.quantity < quantity:
            ctx.say(f"{shop.name} doesn't have {quantity} of that.")
            return

        price_each = self.buy_price(ctx, shop, npc.id, item, stock=stock)
        total_price = price_each * quantity
        if self.ledger.balance_of(ctx.session, "player", ctx.player.id) < total_price:
            ctx.say(f"You can't afford that ({total_price} coins).")
            return

        try:
            self.ledger.execute_exchange(
                ctx.session,
                [
                    ExchangeLeg(
                        give_from=Location("player", ctx.player.id),
                        give_to=Location("shop", shop.id),
                        coins=total_price,
                    )
                ],
            )
        except ConflictError:
            ctx.say(f"You can't afford that ({total_price} coins).")
            return

        ctx.item_location.spawn(item.id, Location("player", ctx.player.id), quantity)
        if stock.quantity >= 0:
            stock.quantity -= quantity
            ctx.session.add(stock)

        label = item.name if quantity == 1 else f"{quantity} {item.name}"
        ctx.say(f"You buy {label} for {total_price} coins.")
        ctx.queue_event(
            GameEvent.ITEM_PURCHASED,
            player_id=ctx.player.id,
            shop_id=shop.id,
            item_id=item.id,
            quantity=quantity,
            price=total_price,
        )

    def sell(self, noun: str | None, ctx: GameContext) -> None:
        if not noun:
            ctx.say("Sell what?")
            return
        found = self._shop_here(ctx)
        if found is None:
            ctx.say("There's no shop here.")
            return
        shop, npc = found
        target = parse_item_target(noun)

        owned: dict[str, Item] = {}
        for stack in ctx.stack_repo.stacks_for_owner("player", ctx.player.id):
            item = ctx.item_repo.get(stack.item_id)
            if item is not None:
                owned[item.id] = item
        item = self._best_match(target.query, list(owned.values()))
        if item is None:
            ctx.say("You don't have that.")
            return

        if not item.tradeable or item.bound:
            ctx.say(f"{shop.name} won't buy that.")
            return
        if not shop.buys_categories or item.category not in shop.buys_categories:
            ctx.say(f"{shop.name} isn't interested in that.")
            return

        stack = next(
            s
            for s in ctx.stack_repo.stacks_for_owner("player", ctx.player.id)
            if s.item_id == item.id
        )
        quantity = min(target.quantity, stack.quantity)
        existing_stock = EconomyRepo(ctx.session).find_stock(shop.id, item.id)
        price_each = self.sell_price(
            shop, self.buy_price(ctx, shop, npc.id, item, stock=existing_stock)
        )
        total_price = price_each * quantity

        if self.ledger.balance_of(ctx.session, "shop", shop.id) < total_price:
            ctx.say(f"{shop.name} can't afford to buy that right now.")
            return

        assert stack.id is not None
        # Sold items are destroyed, not held by the shop as real stock (trade_economy.md
        # §4): ShopStock.quantity is an abstract counter, materialized as an ItemStack only
        # when bought. Only the coin leg goes through execute_exchange.
        self.ledger.execute_exchange(
            ctx.session,
            [
                ExchangeLeg(
                    give_from=Location("shop", shop.id),
                    give_to=Location("player", ctx.player.id),
                    coins=total_price,
                ),
            ],
        )
        ctx.item_location.destroy(stack.id, quantity)

        if existing_stock is not None and existing_stock.quantity >= 0:
            existing_stock.quantity += quantity
            ctx.session.add(existing_stock)

        label = item.name if quantity == 1 else f"{quantity} {item.name}"
        ctx.say(f"You sell {label} for {total_price} coins.")
        ctx.queue_event(
            GameEvent.ITEM_SOLD,
            player_id=ctx.player.id,
            shop_id=shop.id,
            item_id=item.id,
            quantity=quantity,
            price=total_price,
        )

    def appraise(self, noun: str | None, ctx: GameContext) -> None:
        if not noun:
            ctx.say("Appraise what?")
            return
        candidates: dict[str, Item] = {}
        for stack in ctx.stack_repo.stacks_for_owner("player", ctx.player.id):
            item = ctx.item_repo.get(stack.item_id)
            if item is not None:
                candidates[item.id] = item
        for _stack, item in ctx.item_repo.items_in_room(ctx.room.id):
            candidates[item.id] = item
        item = self._best_match(noun, list(candidates.values()))
        if item is None:
            ctx.say("You don't see that.")
            return
        quality_mult = QUALITY_MULTIPLIERS.get(item.quality, 1.0)
        estimated = round(item.value * quality_mult)
        ctx.say(
            f"{item.name} ({item.quality}) looks to be worth around {estimated} coins."
        )
