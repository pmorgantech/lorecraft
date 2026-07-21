"""Zone energy service (roadmap_world.md gap #1, Tier 1 mechanism).

Borrows the *shape* of ``MeterService`` — lazy ``get()``, clamped ``adjust()``
returning a small change record, and a ``TIME_ADVANCED`` sweep with its own
short-lived session + direct commit — but implements a distinct dynamic: zone
energy drifts *bidirectionally* toward a per-channel baseline (deplete down,
recover up), where a meter only regens monotonically toward its maximum.

This is the Tier 1 hook gap #2's harvest verbs build on: read
``get(session, zone, channel).intensity`` and draw down via
``adjust(session, state, -yield_amount)`` (clamped; the returned change lets the
verb detect "you exhausted this node" without Tier 1 knowing what harvesting is).
The drift sweep regenerates it over time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.models.zone_energy import (
    ZoneEnergyChannelConfig,
    ZoneEnergyState,
)
from lorecraft.engine.repos.zone_energy_repo import ZoneEnergyRepo
from lorecraft.errors import NotFoundError


@dataclass(frozen=True)
class ZoneEnergyChange:
    """Result of an ``adjust()`` call.

    ``clamped_low``/``clamped_high`` report whether the requested delta was clipped
    at a bound (the caller decides what that means — e.g. gap #2's harvest verb
    reads ``clamped_low`` to detect "you exhausted this node"). Mirrors the
    primitives-emit-nothing convention of ``MeterChange``.
    """

    state: ZoneEnergyState
    previous: float
    new: float
    delta: float
    clamped_low: bool  # requested delta would have crossed below 0
    clamped_high: bool  # requested delta would have crossed above max_intensity


class ZoneEnergyService:
    def __init__(self, game_engine: Engine) -> None:
        self._game_engine = game_engine

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.TIME_ADVANCED, self._on_time_advanced)

    def get(self, session: Session, zone: str, channel: str) -> ZoneEnergyState:
        """Fetch a zone-energy state, creating it lazily at the channel's baseline.

        Tier 1 does not invent a default baseline for an unregistered channel: if no
        ``ZoneEnergyChannelConfig`` row exists for ``channel``, that is a caller
        error (raises ``NotFoundError``), mirroring ``MeterService.get()`` rejecting
        a key with no registered ``MeterDef``.
        """
        repo = ZoneEnergyRepo(session)
        existing = repo.find(zone, channel)
        if existing is not None:
            return existing

        config = repo.find_channel_config(channel)
        if config is None:
            raise NotFoundError(
                f"No ZoneEnergyChannelConfig registered for channel {channel!r}",
                "not_found_zone_energy_channel",
            )
        return repo.create(zone, channel, config.baseline)

    def adjust(
        self, session: Session, state: ZoneEnergyState, delta: float
    ) -> ZoneEnergyChange:
        """Apply ``delta`` to ``state.intensity``, clamped to ``[0, max_intensity]``.

        The upper bound comes from the channel's current config; if the config row
        has been removed the existing intensity is treated as the ceiling (no
        silent invention of a new maximum). Never commits — the caller owns the
        session, exactly like ``MeterService.adjust()``.
        """
        repo = ZoneEnergyRepo(session)
        config = repo.find_channel_config(state.channel)
        max_intensity = config.max_intensity if config is not None else state.intensity

        previous = state.intensity
        raw = previous + delta
        new = max(0.0, min(max_intensity, raw))
        state.intensity = new
        repo.save(state)
        return ZoneEnergyChange(
            state=state,
            previous=previous,
            new=new,
            delta=delta,
            clamped_low=raw < 0.0,
            clamped_high=raw > max_intensity,
        )

    def _on_time_advanced(self, event: Event, ctx: object) -> None:
        del ctx
        current_epoch = event.payload.get("current_epoch")

        with Session(self._game_engine) as session:
            repo = ZoneEnergyRepo(session)
            # Cache channel configs so the sweep does one lookup per channel, not
            # one per row.
            config_cache: dict[str, ZoneEnergyChannelConfig | None] = {}
            for state in repo.all_states():
                channel = state.channel
                if channel not in config_cache:
                    config_cache[channel] = repo.find_channel_config(channel)
                config = config_cache[channel]
                # A row whose channel config was removed (e.g. admin deletion) is
                # left untouched rather than drifting toward an invented baseline.
                if config is None:
                    continue

                previous = state.intensity
                gap = config.baseline - previous
                if gap == 0:
                    continue
                step = math.copysign(min(config.regen_per_tick, abs(gap)), gap)
                new = max(0.0, min(config.max_intensity, previous + step))
                if new == previous:
                    continue
                state.intensity = new
                if isinstance(current_epoch, (int, float)):
                    state.updated_epoch = float(current_epoch)
                repo.save(state)
            session.commit()
