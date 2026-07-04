"""Pending player-to-player trade data access (Sprint 28.4)."""

from __future__ import annotations

import time
from uuid import uuid4

from sqlmodel import Session, or_, select

from lorecraft.models.interaction import TradeOffer

TRADE_OFFER_TTL_SECONDS = 300.0


class TradeRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_open_for_player(self, player_id: str) -> TradeOffer | None:
        statement = select(TradeOffer).where(
            TradeOffer.status == "pending",
            or_(
                TradeOffer.initiator_id == player_id,
                TradeOffer.recipient_id == player_id,
            ),
        )
        return self.session.exec(statement).first()

    def find_open_between(
        self, player_a_id: str, player_b_id: str
    ) -> TradeOffer | None:
        statement = select(TradeOffer).where(
            TradeOffer.status == "pending",
            or_(
                (TradeOffer.initiator_id == player_a_id)
                & (TradeOffer.recipient_id == player_b_id),
                (TradeOffer.initiator_id == player_b_id)
                & (TradeOffer.recipient_id == player_a_id),
            ),
        )
        return self.session.exec(statement).first()

    def create(self, initiator_id: str, recipient_id: str) -> TradeOffer:
        now = time.time()
        offer = TradeOffer(
            id=str(uuid4()),
            initiator_id=initiator_id,
            recipient_id=recipient_id,
            created_at=now,
            expires_at=now + TRADE_OFFER_TTL_SECONDS,
        )
        self.session.add(offer)
        self.session.flush()
        return offer

    def save(self, offer: TradeOffer) -> None:
        self.session.add(offer)
