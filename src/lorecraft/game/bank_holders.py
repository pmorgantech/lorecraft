"""Registers the "bank_account" item/coin holder type (Sprint 28.3).

Banked money is `CoinBalance("bank_account", account.id)` -- immune to
death/robbery simply because that code only ever touches the
`("player", id)` holder. Self-registers at import time, imported for side
effects from main.py, mirroring game/economy_holders.py.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.game.holders import HolderTypeDef, get_registry
from lorecraft.models.bank import BankAccount


def _bank_account_exists(session: Session, holder_id: str) -> bool:
    return session.get(BankAccount, holder_id) is not None


get_registry().register(HolderTypeDef("bank_account", _bank_account_exists))
