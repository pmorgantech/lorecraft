"""Living-energy policy reads over the Tier 1 zone-energy store (gap #1, Tier 2).

Pure Tier 2 policy: it defines what "imbalance" *means* for a zone (a numeric
spread across the three living-energy channels) on top of the unopinionated Tier 1
``ZoneEnergyState``/``ZoneEnergyChannelConfig`` store, which knows nothing of
imbalance. Nothing consumes ``imbalance()`` yet — it is the read that gaps #6/#7
(cross-energy volatility, machine fuel-typing) will build on — so this stays a
correct, tested read with no side effects.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.engine.repos.zone_energy_repo import ZoneEnergyRepo
from lorecraft.errors import NotFoundError
from lorecraft.features.living_energy.channels import CHANNELS


def imbalance(session: Session, zone: str) -> float:
    """Return the max-min intensity spread across a zone's three channels.

    A perfectly balanced zone (all channels at the same intensity) returns
    ``0.0``; a larger value means the channels have drifted further apart. This is
    a pure read — a channel with no ``ZoneEnergyState`` row yet contributes its
    configured baseline (the effective intensity of an untouched zone) *without*
    creating a row, unlike ``ZoneEnergyService.get()`` which lazily materialises
    one. A channel with no ``ZoneEnergyChannelConfig`` at all is a setup error
    (``NotFoundError``), mirroring the Tier 1 service's rejection of an
    unregistered channel rather than silently inventing a default.
    """
    repo = ZoneEnergyRepo(session)
    intensities: list[float] = []
    for channel in CHANNELS:
        state = repo.find(zone, channel)
        if state is not None:
            intensities.append(state.intensity)
            continue
        config = repo.find_channel_config(channel)
        if config is None:
            raise NotFoundError(
                f"No ZoneEnergyChannelConfig registered for channel {channel!r}",
                "not_found_zone_energy_channel",
            )
        intensities.append(config.baseline)
    return max(intensities) - min(intensities)
