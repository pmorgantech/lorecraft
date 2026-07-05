"""Player web UI host — composes engine + features into an HTMX web interface.

The WebHost abstraction (tier_split_refactor.md §1b/§1c) lets features contribute
UI panels via optional presentation.py modules. This module handles:
- WebHost initialization with base template dir
- Auto-discovery and loading of feature presentation modules
- Panel registry setup

See tier_split_refactor.md for the full framework design and how
builder/admins extend the UI via feature presentation.py.
"""

from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lorecraft.features.manifest import FeatureManifest
    from lorecraft.webui.player.host import WebHost

log = logging.getLogger(__name__)


def create_web_host() -> WebHost:
    """Create a WebHost with the base player template directory.

    Returns:
        Initialized WebHost ready for feature presentation modules to register
        UI panels, static mounts, and scripts.
    """
    from lorecraft.webui.player.host import WebHost

    base_template_dir = Path(__file__).parent / "templates"
    return WebHost(base_template_dir=base_template_dir)


def load_feature_presentations(
    web_host: WebHost,
    enabled_features: dict[str, FeatureManifest],
) -> None:
    """Load feature presentation modules and register their UI contributions.

    Called once at app startup for each enabled feature with a presentation
    module. The presentation module may register panels, static mounts, and
    scripts on the web host.

    Degradation: if a feature's presentation.py fails to load or its register()
    raises, the failure is logged but the app continues (UI degrades, features
    still functional headless).

    Args:
        web_host: WebHost to register panels onto.
        enabled_features: Mapping of feature key -> manifest for all enabled
            features. Only features with a non-None presentation field are
            attempted to load.
    """
    loaded = 0
    for key, manifest in enabled_features.items():
        if not manifest.presentation:
            continue

        try:
            module = import_module(manifest.presentation)
            if not hasattr(module, "register"):
                log.warning(
                    "feature presentation %s has no register() function",
                    manifest.presentation,
                )
                continue

            module.register(web_host)
            loaded += 1
            log.debug("loaded presentation for feature: %s", key)
        except Exception:
            log.exception(
                "failed to load presentation for feature %s (%s)",
                key,
                manifest.presentation,
            )

    if loaded:
        log.info("Loaded %d feature presentation(s)", loaded)
