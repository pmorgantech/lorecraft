"""Progression config table — the Tier 2, admin-tunable leveling *policy*.

A DB singleton mirroring the `WorldClock` pattern (`engine/models/world.py`): a
single row holding both the XP-curve params fed to the Tier 1 `LevelCurve`
mechanism and the per-level reward policy (coins/skill-points). Seeded from
`world.yaml`'s `progression:` section and live-editable via the admin endpoint
(Sprint 73.4). The actual balance numbers live in YAML/DB, never as Python
constants — the fields below carry no numeric defaults on purpose.
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class ProgressionConfig(SQLModel, table=True):
    """Singleton row: XP-curve params + per-level reward policy.

    Curve params (`base`, `step`) map directly onto `engine.game.leveling`'s
    `LevelCurve` formula. Reward params say what crossing one level grants; Tier 2
    multiplies them by `levels_gained` when a level-up fires (Sprint 73.7).
    """

    id: int | None = Field(default=None, primary_key=True)
    base: int
    step: int
    coins_per_level: int
    skill_points_per_level: int
