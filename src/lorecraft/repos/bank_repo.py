"""Bank and bank-account data access (Sprint 28.3)."""

from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from lorecraft.models.bank import Bank, BankAccount


class BankRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def bank_for_npc(self, npc_id: str) -> Bank | None:
        statement = select(Bank).where(Bank.npc_id == npc_id)
        return self.session.exec(statement).first()

    def account_for_player(self, player_id: str) -> BankAccount | None:
        statement = select(BankAccount).where(BankAccount.player_id == player_id)
        return self.session.exec(statement).first()

    def get_or_create_account(self, player_id: str) -> BankAccount:
        existing = self.account_for_player(player_id)
        if existing is not None:
            return existing
        account = BankAccount(id=str(uuid4()), player_id=player_id)
        self.session.add(account)
        self.session.flush()
        return account
