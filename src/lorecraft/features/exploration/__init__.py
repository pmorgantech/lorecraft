"""Exploration feature: exit-discovery helpers, the exploration service, the
exploration journal, and timed room-state effects.

Self-contained Tier 2 package (tier split, step 8): exit-discovery helpers in
`rules.py`, the exploration service in `service.py`, and the journal in
`journal.py`, wired through the `ServiceContainer`. Its `register_fn` registers
the Sprint 39 `passage_open` room effect + `open_timed_passage` mechanism side
effect (see `room_effects.py`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.exploration.room_effects import (
    register as _register_room_effects,
)

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(_state: AppState) -> None:
    _register_room_effects()


manifest = FeatureManifest(
    key="exploration", name="Exploration & Journal", register_fn=_wire
)

register_feature(manifest)
