"""Data access for the progression config singleton."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.features.progression.models import ProgressionConfig


class ProgressionRepo:
    """Reads/writes the single `ProgressionConfig` row (mirrors RoomRepo.world_clock)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def config(self) -> ProgressionConfig | None:
        """The progression config singleton, or None if the world seeded none."""
        return self.session.exec(select(ProgressionConfig)).first()
