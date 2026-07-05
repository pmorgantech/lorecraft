"""Ledger repository — data access for CoinBalance rows."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.engine.models.ledger import CoinBalance


class LedgerRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find(self, holder_type: str, holder_id: str) -> CoinBalance | None:
        statement = select(CoinBalance).where(
            CoinBalance.holder_type == holder_type,
            CoinBalance.holder_id == holder_id,
        )
        return self.session.exec(statement).first()

    def create(self, holder_type: str, holder_id: str, balance: int) -> CoinBalance:
        row = CoinBalance(holder_type=holder_type, holder_id=holder_id, balance=balance)
        self.session.add(row)
        self.session.flush()
        return row

    def save(self, balance: CoinBalance) -> None:
        self.session.add(balance)
