"""Meter definitions and registry (engine_core.md §3.3).

Tier 1 ships the mechanism; the "hp" MeterDef is registered as bootstrap proof
in main.py's lifespan (base_maximum reads PlayerStats.max_hp / NPC.max_hp).
Other resources (fatigue, hunger, mana, ...) are Tier 2/3 registrations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlmodel import Session


@dataclass(frozen=True)
class MeterDef:
    """Definition of a registerable meter type.

    Args:
        key: Unique meter identifier (e.g., "hp", "fatigue").
        base_maximum: (entity_type, entity_id, session) -> the un-modified max.
            §3.5's resolve() is applied on top via MeterService.recompute_maximum().
        regen_per_tick: Applied on TIME_ADVANCED; 0 = no automatic regen.
        start_full: Whether a lazily-created meter starts at its maximum
            (True) or at 0 (False).
    """

    key: str
    base_maximum: Callable[[str, str, Session], float]
    regen_per_tick: float = 0.0
    start_full: bool = True


class MeterRegistry:
    """Registry of meter definitions, keyed by name (overwrites on re-register)."""

    def __init__(self) -> None:
        self._defs: dict[str, MeterDef] = {}

    def register(self, meter_def: MeterDef) -> None:
        self._defs[meter_def.key] = meter_def

    def get(self, key: str) -> MeterDef | None:
        return self._defs.get(key)

    def __contains__(self, key: str) -> bool:
        return key in self._defs

    def all_keys(self) -> list[str]:
        """Registered meter keys, for the regen sweep to iterate deterministically."""
        return sorted(self._defs.keys())


_registry = MeterRegistry()


def get_registry() -> MeterRegistry:
    """Get the global meter registry."""
    return _registry
