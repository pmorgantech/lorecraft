"""Meter repository — data access for Meter rows."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.models.meters import Meter


class MeterRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find(self, entity_type: str, entity_id: str, key: str) -> Meter | None:
        statement = select(Meter).where(
            Meter.entity_type == entity_type,
            Meter.entity_id == entity_id,
            Meter.key == key,
        )
        return self.session.exec(statement).first()

    def all_for_key(self, key: str) -> list[Meter]:
        """Every existing meter row for a given key, ordered by ID (deterministic).

        Used by the regen sweep — only meters that have already been lazily
        created are ticked; there is no eager row for every possible entity.
        """
        statement = (
            select(Meter).where(Meter.key == key).order_by(Meter.id)  # type: ignore[arg-type]
        )
        return list(self.session.exec(statement).all())

    def create(
        self, entity_type: str, entity_id: str, key: str, current: float, maximum: float
    ) -> Meter:
        meter = Meter(
            entity_type=entity_type,
            entity_id=entity_id,
            key=key,
            current=current,
            maximum=maximum,
        )
        self.session.add(meter)
        self.session.flush()
        return meter

    def save(self, meter: Meter) -> None:
        self.session.add(meter)
