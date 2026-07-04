"""Bank feature: bank accounts — registers the "bank_account" holder type.

Migrated to the manifest system (tier split, step 5). The holder registration
still lives in `lorecraft.game.bank_holders`; the manifest wraps it so it loads
via config instead of a side-effect import. The bank service/commands join this
manifest in a later step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.game.bank_holders import register as _register_bank

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_bank()


manifest = FeatureManifest(key="bank", name="Banking", register_fn=_wire)

register_feature(manifest)
