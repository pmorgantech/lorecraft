"""Unit tests for WebHost (panel/slot registry and template loader abstraction)."""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from lorecraft.webui.player.host import Panel, WebHost


@pytest.fixture
def temp_templates() -> tuple[Path, Path]:
    """Create temporary template directories for base and feature."""
    with TemporaryDirectory() as base_dir, TemporaryDirectory() as feature_dir:
        base_path = Path(base_dir)
        feature_path = Path(feature_dir)

        # Create a base template
        (base_path / "base.html").write_text(
            "<html><body>{% block content %}{% endblock %}</body></html>"
        )

        # Create a feature template
        (feature_path / "transit_minimap.html").write_text("<div>Minimap</div>")

        yield base_path, feature_path


class TestWebHost:
    """Tests for WebHost abstraction."""

    def test_init_with_base_template_dir(
        self, temp_templates: tuple[Path, Path]
    ) -> None:
        """WebHost initializes with base template directory."""
        base_path, _ = temp_templates
        host = WebHost(base_template_dir=base_path)

        assert host.base_template_dir == base_path
        assert len(host.base_loaders) == 1

    def test_add_template_dir(self, temp_templates: tuple[Path, Path]) -> None:
        """add_template_dir adds a feature template directory to search path."""
        base_path, feature_path = temp_templates
        host = WebHost(base_template_dir=base_path)

        host.add_template_dir(feature_path)

        assert len(host.base_loaders) == 2

    def test_add_panel(self, temp_templates: tuple[Path, Path]) -> None:
        """add_panel registers a panel."""
        base_path, _ = temp_templates
        host = WebHost(base_template_dir=base_path)

        panel = Panel(
            id="test-panel",
            slot="right-rail",
            partial="partials/test.html",
            context=lambda p, db: {"test": True},
        )
        host.add_panel(panel)

        assert "test-panel" in host.panels
        assert host.panels["test-panel"] == panel

    def test_add_panel_duplicate_raises(
        self, temp_templates: tuple[Path, Path]
    ) -> None:
        """add_panel raises if panel id is already registered."""
        base_path, _ = temp_templates
        host = WebHost(base_template_dir=base_path)

        panel = Panel(
            id="duplicate",
            slot="right-rail",
            partial="partials/test.html",
            context=lambda p, db: {},
        )
        host.add_panel(panel)

        with pytest.raises(ValueError, match="already registered"):
            host.add_panel(panel)

    def test_add_static(self, temp_templates: tuple[Path, Path]) -> None:
        """add_static registers a static mount."""
        base_path, feature_path = temp_templates
        host = WebHost(base_template_dir=base_path)

        host.add_static("/features/test", feature_path)

        assert ("/features/test", feature_path) in host.static_mounts

    def test_add_script(self, temp_templates: tuple[Path, Path]) -> None:
        """add_script registers a JS script."""
        base_path, _ = temp_templates
        host = WebHost(base_template_dir=base_path)

        host.add_script("/features/test/script.js", module=True)

        assert ("/features/test/script.js", True) in host.scripts

    def test_build_jinja_environment(self, temp_templates: tuple[Path, Path]) -> None:
        """build_jinja_environment creates a Jinja2 Environment with ChoiceLoader."""
        base_path, feature_path = temp_templates
        host = WebHost(base_template_dir=base_path)
        host.add_template_dir(feature_path)

        env = host.build_jinja_environment()

        assert env is not None
        # Verify that both base and feature templates are accessible
        assert env.get_template("base.html") is not None
        assert env.get_template("transit_minimap.html") is not None

    def test_get_panels_by_slot(self, temp_templates: tuple[Path, Path]) -> None:
        """get_panels_by_slot returns panels for a named slot."""
        base_path, _ = temp_templates
        host = WebHost(base_template_dir=base_path)

        panel1 = Panel(
            id="panel-1",
            slot="right-rail",
            partial="p1.html",
            context=lambda p, db: {},
        )
        panel2 = Panel(
            id="panel-2",
            slot="right-rail",
            partial="p2.html",
            context=lambda p, db: {},
        )
        panel3 = Panel(
            id="panel-3",
            slot="left-rail",
            partial="p3.html",
            context=lambda p, db: {},
        )

        host.add_panel(panel1)
        host.add_panel(panel2)
        host.add_panel(panel3)

        right_rail = host.get_panels_by_slot("right-rail")
        left_rail = host.get_panels_by_slot("left-rail")

        assert len(right_rail) == 2
        assert panel1 in right_rail
        assert panel2 in right_rail
        assert len(left_rail) == 1
        assert panel3 in left_rail

    def test_get_panels_by_slot_unknown_returns_empty(
        self, temp_templates: tuple[Path, Path]
    ) -> None:
        """get_panels_by_slot returns empty list for unknown slot."""
        base_path, _ = temp_templates
        host = WebHost(base_template_dir=base_path)

        panels = host.get_panels_by_slot("nonexistent")

        assert panels == []
