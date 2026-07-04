"""Warmth resolution (Sprint 27.2, docs/wishlist.md -> Character condition).

Composes the Tier 1 modifier resolver with equipped items' `warmth_bonus`
effects (game/item_effects.py) -- gives worn clothing a non-combat purpose:
a cloak matters when sleeping out in a blizzard (services/fatigue.py).
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.game.modifiers import resolve_for

WARMTH_KEY = "warmth"
BASE_WARMTH = 0.0


def resolve_warmth(session: Session, player_id: str) -> float:
    return resolve_for(session, "player", player_id, WARMTH_KEY, base=BASE_WARMTH)
