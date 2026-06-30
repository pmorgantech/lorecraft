"""Shared fixtures for parser integration tests."""

from __future__ import annotations

import pytest

from tests.fixtures.disambig_fixtures import similar_item_entities


@pytest.fixture
def mock_context():
    """Room + inventory entities for fuzzy resolution and disambiguation tests."""

    class MockContext:
        def get_visible_entities(self):
            return [
                *similar_item_entities(),
                ("id_gabriel", "Gabriel", ["gabriel"]),
                ("id_mira", "Mira", ["mira", "innkeeper"]),
                ("id_chest", "wooden chest", ["chest"]),
                ("id_backpack", "leather backpack", ["backpack"]),
                ("id_goblin", "goblin", []),
                ("id_lantern", "lantern", []),
                ("id_purse", "leather purse", ["purse"]),
            ]

        def get_inventory(self):
            return [
                ("id_lantern_inv", "lantern", []),
                ("id_apple_inv", "apple", []),
            ]

    return MockContext()
