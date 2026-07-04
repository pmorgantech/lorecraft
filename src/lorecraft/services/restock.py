"""Shop stock restocking sweep (Sprint 28.2, docs/trade_economy.md §6).

Engine-holding schedulable, same shape as LightFuelService: on every
TIME_ADVANCED tick, every ShopStock row with a restock schedule
(`restock_every_ticks > 0`) counts one tick closer; once it reaches the
threshold, quantity jumps straight to `restock_to` (the doc's own "keep it
simple: a per-shop-per-item running adjustment, not a full market
simulation") and the counter resets. Opens its own short-lived session and
commits it directly -- no GameContext exists in this scheduler-driven sweep.
"""

from __future__ import annotations

from sqlalchemy import Engine
from sqlmodel import Session

from lorecraft.game.events import Event, EventBus, GameEvent
from lorecraft.repos.economy_repo import EconomyRepo


class RestockService:
    def __init__(self, game_engine: Engine) -> None:
        self.game_engine = game_engine

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.TIME_ADVANCED, self._on_time_advanced)

    def _on_time_advanced(self, event: Event, ctx: object) -> None:
        del event, ctx
        with Session(self.game_engine) as session:
            repo = EconomyRepo(session)
            for stock in repo.all_restockable_stock():
                if stock.quantity == stock.restock_to:
                    stock.ticks_since_restock = 0
                    repo.save(stock)
                    continue
                stock.ticks_since_restock += 1
                if stock.ticks_since_restock >= stock.restock_every_ticks:
                    stock.quantity = stock.restock_to
                    stock.ticks_since_restock = 0
                repo.save(stock)
            session.commit()
