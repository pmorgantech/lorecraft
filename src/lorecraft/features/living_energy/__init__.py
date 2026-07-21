"""Living-energy feature: the three energy channels (lumenroot/dreamveil/
emberthorn), the zone-imbalance policy over the Tier 1 zone-energy store
(roadmap_world.md gap #1), and the depletable `harvest` verb (gap #2).

Self-contained Tier 2 package: the channel identities live in ``channels.py``,
the imbalance read in ``policy.py``, and the harvest data/service/commands in
``harvest.py``/``commands.py``. It imports only ``engine.*`` and other features
(never a web host), per the tier boundary.

The manifest now carries a real ``register_fn`` (it was passive before gap #2):
it ensures the harvest table is loaded onto the feature's registry on the
feature-enable path — the authoritative, env-override-respecting load still lives
in ``main.py`` (mirroring ``_load_forage_definitions``), so ``_wire`` only fills
in when that explicit loader hasn't run (e.g. doc-gen / feature-load-only tests),
and never clobbers an already-loaded table. The harvest *verbs* are wired through
``register_all_commands`` like every other feature's, not here.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from lorecraft.features.living_energy.channels import CHANNELS
from lorecraft.features.living_energy.harvest import (
    DEFAULT_HARVEST_YAML_PATH,
    get_registry,
    load_harvest_yaml,
)
from lorecraft.features.living_energy.policy import imbalance
from lorecraft.features.manifest import FeatureManifest, register_feature

if TYPE_CHECKING:
    from lorecraft.state import AppState

__all__ = ["CHANNELS", "imbalance", "manifest"]


def _wire(_state: AppState) -> None:
    # Idempotent content fill: if main.py's explicit (env-path) loader already
    # populated the harvest table, leave it; otherwise load from the default
    # path so the feature-enable path (doc-gen, tests) still has data.
    registry = get_registry()
    if not registry.is_empty():
        return
    if not Path(DEFAULT_HARVEST_YAML_PATH).exists():
        return
    registry.load_document(load_harvest_yaml(DEFAULT_HARVEST_YAML_PATH))


manifest = FeatureManifest(key="living_energy", name="Living Energy", register_fn=_wire)

register_feature(manifest)
