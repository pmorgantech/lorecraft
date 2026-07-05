"""WebHost abstraction for composing engine + features into player web UI.

Provides a multi-directory Jinja template loader and a panel/slot registry
so features can contribute templates and UI panels via optional presentation.py.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from jinja2 import ChoiceLoader, Environment, FileSystemLoader


@dataclass
class Panel:
    """A UI panel a feature contributes to the web shell.

    Args:
        id: Unique panel identifier (convention: feature-key-name, e.g. "transit-minimap")
        slot: Named shell slot the panel lives in (e.g. "right-rail", "hud", "feed")
        partial: Template path relative to the feature's template dir (e.g. "partials/transit_minimap.html")
        context: Callable that builds the panel's template context (player, db) -> dict
    """

    id: str
    slot: str
    partial: str
    context: Callable[[Any, Any], dict]


@dataclass
class WebHost:
    """Multi-host template loader and panel/slot registry for the player web UI.

    Manages Jinja template search paths (base + feature-specific dirs) and
    auto-generates partial routes and shell slots for features that contribute UI.
    """

    base_template_dir: Path
    base_loaders: list[FileSystemLoader] = field(default_factory=list)
    panels: dict[str, Panel] = field(default_factory=dict)
    static_mounts: list[tuple[str, Path]] = field(default_factory=list)
    scripts: list[tuple[str, bool]] = field(default_factory=list)  # (url, module)

    def __post_init__(self) -> None:
        """Initialize with the base template directory."""
        self.base_loaders = [FileSystemLoader(self.base_template_dir)]

    def add_template_dir(self, path: Path) -> None:
        """Add a feature's template directory to the Jinja search path.

        Called by feature presentation.py during initialization. Templates in
        this dir are resolved after the base dir (ChoiceLoader tries in order).

        Args:
            path: Absolute path to the feature's template directory.
        """
        self.base_loaders.append(FileSystemLoader(path))

    def add_panel(self, panel: Panel) -> None:
        """Register a UI panel that a feature contributes.

        Auto-generates GET /partials/<panel.id> that renders the partial
        with context from panel.context(...). Records the panel for slot
        assignment in the shell template.

        Args:
            panel: Panel metadata and context builder.

        Raises:
            ValueError: if panel.id is already registered.
        """
        if panel.id in self.panels:
            raise ValueError(f"Panel {panel.id} already registered")
        self.panels[panel.id] = panel

    def add_static(self, mount: str, path: Path) -> None:
        """Mount a static directory for a feature (CSS, images, etc.).

        Called by feature presentation.py to make static assets available.

        Args:
            mount: Mount path (e.g. "/features/transit").
            path: Absolute path to the feature's static directory.
        """
        self.static_mounts.append((mount, path))

    def add_script(self, url: str, module: bool = False) -> None:
        """Register a JavaScript asset to inject into the shell <head>.

        Called by feature presentation.py to load interactive panel JS.

        Args:
            url: Script URL (relative or absolute).
            module: If True, inject as <script type="module">.
        """
        self.scripts.append((url, module))

    def build_jinja_environment(self) -> Environment:
        """Build a Jinja2 environment with all registered template dirs.

        Returns:
            Environment configured with ChoiceLoader over base + all feature
            template directories (searched in registration order).
        """
        loader = ChoiceLoader(self.base_loaders)
        return Environment(loader=loader)

    def get_panels_by_slot(self, slot: str) -> list[Panel]:
        """Get all panels registered for a named shell slot.

        Args:
            slot: Slot name (e.g. "right-rail").

        Returns:
            Ordered list of panels assigned to this slot (by feature load order).
        """
        return [p for p in self.panels.values() if p.slot == slot]
