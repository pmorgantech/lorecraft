"""Zone energy repository — data access for ZoneEnergyState / ZoneEnergyChannelConfig."""

from __future__ import annotations

from sqlmodel import Session, select

from lorecraft.engine.models.zone_energy import (
    ZoneEnergyChannelConfig,
    ZoneEnergyState,
)


class ZoneEnergyRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find(self, zone: str, channel: str) -> ZoneEnergyState | None:
        statement = select(ZoneEnergyState).where(
            ZoneEnergyState.zone == zone,
            ZoneEnergyState.channel == channel,
        )
        return self.session.exec(statement).first()

    def all_states(self) -> list[ZoneEnergyState]:
        """Every existing state row, ordered by ``(zone, channel)`` (deterministic).

        Used by the drift sweep — only ``(zone, channel)`` pairs that have already
        been lazily created are ticked; there is no eager row for every possible
        zone/channel combination.
        """
        statement = select(ZoneEnergyState).order_by(
            ZoneEnergyState.zone,  # type: ignore[arg-type]
            ZoneEnergyState.channel,  # type: ignore[arg-type]
        )
        return list(self.session.exec(statement).all())

    def create(self, zone: str, channel: str, intensity: float) -> ZoneEnergyState:
        """Insert a new state row.

        Flushes so the composite-PK ``(zone, channel)`` uniqueness constraint is
        enforced immediately — a duplicate insert raises ``IntegrityError`` here
        rather than silently overwriting. The service layer only calls this after a
        ``find()`` miss, so a duplicate would signal a concurrent double-create.
        """
        state = ZoneEnergyState(zone=zone, channel=channel, intensity=intensity)
        self.session.add(state)
        self.session.flush()
        return state

    def save(self, state: ZoneEnergyState) -> None:
        self.session.add(state)

    def find_channel_config(self, channel: str) -> ZoneEnergyChannelConfig | None:
        return self.session.get(ZoneEnergyChannelConfig, channel)
