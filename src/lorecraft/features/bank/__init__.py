"""Bank feature: bank accounts — registers the "bank_account" holder type.

Self-contained Tier 2 package (tier split, step 8): the "bank_account" holder
(`holders.py`), service (`service.py`), model (`models.py`), and repo
(`repo.py`) live here; the manifest registers the holder. (The banking command
module dissolves into the package in step 9.)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.bank.holders import register as _register_bank

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_bank()


manifest = FeatureManifest(key="bank", name="Banking", register_fn=_wire)

register_feature(manifest)
