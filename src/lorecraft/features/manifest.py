"""Feature manifest: the declarative descriptor for a Tier 2 feature.

A `FeatureManifest` is what a Tier 2 feature exports so the engine can load
it *by configuration* instead of via the brittle side-effect imports that
`main.py` used to carry (e.g. `import lorecraft.game.fatigue_source  # noqa`).
Each feature package's ``__init__`` builds one manifest and calls
:func:`register_feature`; the loader (see ``lorecraft.features.loader``) then
selects which registered features to actually wire based on the enabled set.

See ``docs/tier_split_refactor.md`` for the full design. This module is the
first, additive step: it introduces the descriptor and the registry without
moving any existing code, so nothing else changes behaviour yet.

Deliberately minimal for now: fields that later steps depend on (conditional
service construction, model lists) are added when the step that consumes them
lands, rather than shipping unused seams — see the progress tracker.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lorecraft.state import AppState

# A feature's wiring hook: called once at app startup with the assembled
# AppState, it registers the feature's commands, conditions, side effects,
# modifiers, rules, and event handlers on the shared Tier 1 registries.
RegisterFn = Callable[["AppState"], None]


@dataclass(frozen=True)
class FeatureManifest:
    """Declarative description of a Tier 2 feature.

    Attributes:
        key: Stable identifier used in the enabled-features config and in
            dependency references (e.g. ``"equipment"``). Unique across features.
        name: Human-readable name for logs and admin tooling.
        dependencies: Keys of other features that must also be enabled for this
            one to work. The loader raises if a dependency is missing.
        register_fn: Optional hook that wires the feature onto the shared
            registries at startup. ``None`` for features that only contribute
            passive definitions registered elsewhere.
        presentation: Optional dotted import path to a module exposing
            ``register(web_host)``. Imported *only* by a web host, never by the
            engine, so a headless run never loads UI code (see §1c).
    """

    key: str
    name: str
    dependencies: tuple[str, ...] = ()
    register_fn: RegisterFn | None = None
    presentation: str | None = None


# Populated at import time as feature packages call register_feature(). The
# loader consumes this catalogue; being registered here does NOT mean a feature
# is enabled — enablement is a separate, config-driven decision.
FEATURE_REGISTRY: dict[str, FeatureManifest] = {}


def register_feature(manifest: FeatureManifest) -> None:
    """Add a feature manifest to the global catalogue.

    Raises:
        ValueError: if a feature with the same key is already registered
            (a duplicate key is almost always a copy-paste bug).
    """
    if manifest.key in FEATURE_REGISTRY:
        raise ValueError(f"Feature {manifest.key!r} is already registered")
    FEATURE_REGISTRY[manifest.key] = manifest


def get_feature(key: str) -> FeatureManifest | None:
    """Return the registered manifest for ``key``, or ``None`` if unknown."""
    return FEATURE_REGISTRY.get(key)


def clear_registry() -> None:
    """Drop all registered features. Test-only: lets a test start from empty."""
    FEATURE_REGISTRY.clear()
