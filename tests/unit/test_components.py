"""Unit tests for the registered issue-component set."""

from __future__ import annotations

from lorecraft.content.components import ISSUE_COMPONENTS, is_valid_component


def test_registered_components_are_valid() -> None:
    assert ISSUE_COMPONENTS  # non-empty
    for component in ISSUE_COMPONENTS:
        assert is_valid_component(component)


def test_empty_component_is_allowed() -> None:
    # "" means "unassigned" — the default for in-game player reports.
    assert is_valid_component("")


def test_unregistered_component_is_rejected() -> None:
    assert not is_valid_component("engine/parser")  # too granular; not registered
    assert not is_valid_component("nonsense")
