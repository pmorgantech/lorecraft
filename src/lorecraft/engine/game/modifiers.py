"""Runtime modifier resolution — one resolver for bonuses from many sources.

See docs/engine/engine_core.md §3.5. Generalizes the equipment/traits/terrain/condition/
pricing "stack bonuses with a defined order" problem into a single pure function
plus a pluggable collection registry. Tier 1 registers no sources — the
active-effect and trait sources (§3.4, Sprint 19) register here once they exist;
equipment/terrain sources are Tier 2 (Sprint 23+).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlmodel import Session

ModifierKind = Literal["add", "mult", "clamp_min", "clamp_max"]


@dataclass(frozen=True)
class Modifier:
    """One bonus/penalty contribution to a resolved value.

    Args:
        key: Namespaced target, e.g. "stat.strength", "skill.perception",
            "meter.hp.max", "carry_capacity", "price.buy".
        kind: How this amount combines with others at the same key.
        amount: The magnitude. Percentages are `mult` amounts (0.75 = 25% off),
            never `add` of a fraction.
        source: Provenance for debugging/UI, e.g. "item:miners_helm",
            "trait:weakened", "effect:<uuid>".
    """

    key: str
    kind: ModifierKind
    amount: float
    source: str


def resolve(key: str, base: float, modifiers: Iterable[Modifier]) -> float:
    """Resolve `base` against every modifier matching `key`.

    Filters to `key`, then applies in FIXED bucket order (order within a
    bucket never matters — every op in it is commutative):

        1. add:   value = base + sum(amounts)
        2. mult:  value = value * product(amounts)
        3. clamp: value = min(value, min(clamp_max amounts));
                  value = max(value, max(clamp_min amounts))

    Never stored, never cached — recompute per use. Returns a float; the
    caller rounds/ints at its own edge (prices round(), stats int(), meters
    stay float).
    """
    relevant = [m for m in modifiers if m.key == key]

    value = base + sum(m.amount for m in relevant if m.kind == "add")

    mult_amounts = [m.amount for m in relevant if m.kind == "mult"]
    for amount in mult_amounts:
        value *= amount

    clamp_maxes = [m.amount for m in relevant if m.kind == "clamp_max"]
    if clamp_maxes:
        value = min(value, min(clamp_maxes))

    clamp_mins = [m.amount for m in relevant if m.kind == "clamp_min"]
    if clamp_mins:
        value = max(value, max(clamp_mins))

    return value


class ModifierSource(Protocol):
    """A pluggable contributor of modifiers for a given entity."""

    def modifiers_for(
        self, session: Session, entity_type: str, entity_id: str
    ) -> Iterable[Modifier]: ...


class ModifierRegistry:
    """Registry of ModifierSources, collected in registration order.

    Unlike the name-keyed registries elsewhere in game/ (ComponentRegistry,
    HolderRegistry), sources aren't named in the spec, so this can't dedupe
    by key — a source registered more than once (e.g. app lifespan running
    twice in the same process, as tests do) will double-count. Register a
    module-level singleton once at import time where possible; if a Tier 2
    feature must register at app lifespan, it owns making that idempotent.
    """

    def __init__(self) -> None:
        self._sources: list[ModifierSource] = []

    def register(self, source: ModifierSource) -> None:
        self._sources.append(source)

    def collect(
        self, session: Session, entity_type: str, entity_id: str
    ) -> list[Modifier]:
        """All modifiers from every registered source for this entity."""
        modifiers: list[Modifier] = []
        for source in self._sources:
            modifiers.extend(source.modifiers_for(session, entity_type, entity_id))
        return modifiers


_registry = ModifierRegistry()


def get_registry() -> ModifierRegistry:
    """Get the global modifier registry."""
    return _registry


def resolve_for(
    session: Session, entity_type: str, entity_id: str, key: str, base: float
) -> float:
    """Convenience: collect from every registered source, then resolve()."""
    modifiers = get_registry().collect(session, entity_type, entity_id)
    return resolve(key, base, modifiers)
