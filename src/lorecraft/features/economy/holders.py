"""Registers the "shop" item/coin holder type (Sprint 28.1, docs/trade_economy.md §2).

A shop's cash is `CoinBalance("shop", shop.id)`; its purchased-out stock
becomes `ItemStack`s owned by `("shop", shop.id)` transiently during
`execute_exchange` legs. Self-registers at import time, imported for side
effects from main.py, mirroring game/holders.py's built-in registrations.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.engine.game.holders import HolderTypeDef, get_registry
from lorecraft.features.economy.models import Shop


def _shop_exists(session: Session, holder_id: str) -> bool:
    return session.get(Shop, holder_id) is not None


def register() -> None:
    """Register the "shop" holder type. Called by the `economy` feature manifest
    when enabled (no longer a module-level import side effect). Idempotent."""
    get_registry().register(HolderTypeDef("shop", _shop_exists))
