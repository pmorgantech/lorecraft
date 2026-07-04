"""Shop and shop-stock data access (Sprint 28.1)."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.models.economy import Shop, ShopStock


class EconomyRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def shop_for_npc(self, npc_id: str) -> Shop | None:
        statement = select(Shop).where(Shop.npc_id == npc_id)
        return self.session.exec(statement).first()

    def stock_for_shop(self, shop_id: str) -> list[ShopStock]:
        statement = (
            select(ShopStock).where(ShopStock.shop_id == shop_id).order_by(ShopStock.id)  # type: ignore[arg-type]
        )
        return list(self.session.exec(statement).all())

    def find_stock(self, shop_id: str, item_id: str) -> ShopStock | None:
        statement = select(ShopStock).where(
            ShopStock.shop_id == shop_id, ShopStock.item_id == item_id
        )
        return self.session.exec(statement).first()

    def save(self, stock: ShopStock) -> None:
        self.session.add(stock)
