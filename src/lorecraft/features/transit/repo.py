"""Transit line/stop data access (Sprint 29.2)."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.features.transit.models import TransitLine, TransitStop


class TransitRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def all_lines(self) -> list[TransitLine]:
        return list(self.session.exec(select(TransitLine)).all())

    def get_line(self, line_id: str) -> TransitLine | None:
        return self.session.get(TransitLine, line_id)

    def stops_for_line(self, line_id: str) -> list[TransitStop]:
        statement = (
            select(TransitStop)
            .where(TransitStop.line_id == line_id)
            .order_by(TransitStop.sequence)  # type: ignore[arg-type]
        )
        return list(self.session.exec(statement).all())

    def lines_at_station(self, room_id: str) -> list[TransitLine]:
        stops = self.session.exec(
            select(TransitStop).where(TransitStop.room_id == room_id)
        ).all()
        line_ids = {stop.line_id for stop in stops}
        return [line for line in self.all_lines() if line.id in line_ids]

    def line_for_vehicle_room(self, room_id: str) -> TransitLine | None:
        statement = select(TransitLine).where(TransitLine.vehicle_room_id == room_id)
        return self.session.exec(statement).first()
