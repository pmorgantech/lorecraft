"""The one sanctioned source of randomness in src/lorecraft.

See docs/engine/engine_core.md §3.6: any randomness reaching an event payload, audit
record, or WS message must be deterministic when seeded, so the simulation
harness's audit-regression diff (tests/simulation/test_audit_regression.py)
stays meaningful. `random` is banned everywhere else in src/ via
pyproject.toml's ruff banned-api rule; this module is the sole exception.
"""

from __future__ import annotations

import random  # noqa: TID251 -- GameRng is the sanctioned wrapper
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class GameRng:
    """Deterministic when seeded. The ONLY sanctioned randomness source in src/lorecraft."""

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def randint(self, a: int, b: int) -> int:
        return self._random.randint(a, b)

    def uniform(self, a: float, b: float) -> float:
        return self._random.uniform(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        return self._random.choice(seq)

    def chance(self, p: float) -> bool:
        """True with probability p (0.0-1.0)."""
        return self._random.uniform(0, 1) < p
