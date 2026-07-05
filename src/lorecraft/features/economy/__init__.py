"""Economy feature: shops (buy/sell) — registers the "shop" holder type.

Self-contained Tier 2 package (tier split, step 8): the "shop" holder
(`holders.py`), service (`service.py`), model (`models.py`), and repo
(`repo.py`) live here; the manifest registers the holder. (The `buy`/`sell`
command module dissolves into the package in step 9.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.economy.holders import register as _register_economy

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_economy()


manifest = FeatureManifest(key="economy", name="Economy & Shops", register_fn=_wire)

register_feature(manifest)
