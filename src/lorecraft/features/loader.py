"""Feature discovery and loading.

Two responsibilities, both config-driven and free of per-feature special cases:

* :func:`discover_features` imports every feature subpackage so its manifest
  self-registers into ``FEATURE_REGISTRY`` — this is the catalogue of what
  *exists*, replacing the hand-maintained side-effect import list in
  ``main.py``.
* :func:`load_features` takes the *enabled* set (from config) and returns the
  manifests to actually wire, validated and ordered so each feature's
  dependencies come before it. It raises on an unknown feature, a dependency
  that isn't enabled, or a dependency cycle.

See ``docs/tier_split_refactor.md`` (step 2). Still additive: nothing calls
these yet — that wiring is a later step.
"""

from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING

import lorecraft.features
from lorecraft.features.manifest import FEATURE_REGISTRY, FeatureManifest

if TYPE_CHECKING:
    from lorecraft.state import AppState

log = logging.getLogger(__name__)

# Env var holding a comma-separated list of enabled feature keys. Unset means
# "all discovered features" (behaviour-preserving default).
FEATURES_ENV_VAR = "LORECRAFT_FEATURES"


def discover_features() -> dict[str, FeatureManifest]:
    """Import every feature subpackage, triggering its manifest registration.

    Walks the immediate subpackages of ``lorecraft.features`` and imports each,
    running its ``register_feature(...)`` side effect. Only *subpackages* are
    treated as features; plain modules here (``manifest``, ``loader``) are
    skipped. Idempotent — importing an already-imported package is a no-op.

    Returns a snapshot copy of the resulting registry.
    """
    for module_info in pkgutil.iter_modules(
        lorecraft.features.__path__, prefix="lorecraft.features."
    ):
        if module_info.ispkg:
            importlib.import_module(module_info.name)
    return dict(FEATURE_REGISTRY)


def load_features(
    enabled: Sequence[str],
    registry: Mapping[str, FeatureManifest] | None = None,
) -> dict[str, FeatureManifest]:
    """Validate the enabled feature set and return it in dependency order.

    Args:
        enabled: Feature keys that should be active (order is respected as a
            tie-breaker so loading is deterministic).
        registry: Catalogue to resolve keys against; defaults to the global
            ``FEATURE_REGISTRY``. Passing an explicit mapping keeps tests
            hermetic.

    Returns:
        An insertion-ordered mapping ``key -> manifest`` where every feature
        appears after all of its (transitive) dependencies.

    Raises:
        ValueError: if an enabled key is not registered, if an enabled feature
            depends on one that is not enabled, or if the dependencies form a
            cycle.
    """
    catalogue = FEATURE_REGISTRY if registry is None else registry
    enabled_set = set(enabled)

    for key in enabled:
        if key not in catalogue:
            raise ValueError(f"Feature {key!r} is not registered")

    for key in enabled:
        for dependency in catalogue[key].dependencies:
            if dependency not in enabled_set:
                raise ValueError(
                    f"Feature {key!r} requires {dependency!r}, which is not enabled"
                )

    ordered: dict[str, FeatureManifest] = {}
    visiting: set[str] = set()

    def visit(key: str, chain: tuple[str, ...]) -> None:
        if key in ordered:
            return
        if key in visiting:
            cycle = " -> ".join((*chain, key))
            raise ValueError(f"Feature dependency cycle: {cycle}")
        visiting.add(key)
        for dependency in catalogue[key].dependencies:
            visit(dependency, (*chain, key))
        visiting.discard(key)
        ordered[key] = catalogue[key]

    for key in enabled:
        visit(key, ())

    return ordered


def resolve_enabled_features(
    explicit: Sequence[str] | None,
    available: Iterable[str],
) -> list[str]:
    """Decide which feature keys are enabled.

    Precedence, highest first:

    1. ``explicit`` — an argument passed by the caller (e.g. a test or an
       alternate entrypoint). ``None`` means "not specified", which falls
       through; an empty list means "explicitly none".
    2. The ``LORECRAFT_FEATURES`` env var — a comma-separated list of keys.
    3. Default: every ``available`` (discovered) feature — this preserves
       today's behaviour where every shipped feature is active.
    """
    if explicit is not None:
        return list(explicit)
    raw = os.getenv(FEATURES_ENV_VAR)
    if raw is not None and raw.strip():
        return [key.strip() for key in raw.split(",") if key.strip()]
    return list(available)


def wire_features(state: AppState, features: Mapping[str, FeatureManifest]) -> None:
    """Call each loaded feature's ``register_fn`` to wire it onto ``state``.

    ``features`` must already be in dependency order (as returned by
    :func:`load_features`), so a feature is wired only after everything it
    depends on. Features without a ``register_fn`` (passive definition-only
    features) are skipped.
    """
    for manifest in features.values():
        if manifest.register_fn is not None:
            manifest.register_fn(state)
