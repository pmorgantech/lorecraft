"""Economy feature: shops (buy/sell) — registers the "shop" holder type.

Migrated to the manifest system (tier split, step 5). The holder registration
still lives in `lorecraft.game.economy_holders`; the manifest wraps it so it
loads via config instead of a side-effect import. The economy service/commands
join this manifest in a later step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.game.economy_holders import register as _register_economy

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_economy()


manifest = FeatureManifest(key="economy", name="Economy & Shops", register_fn=_wire)

register_feature(manifest)
