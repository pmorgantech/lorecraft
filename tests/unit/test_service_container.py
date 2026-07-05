"""ServiceContainer builds feature-gated services conditionally (tier split,
step 6): economy/bank/fatigue exist only when their feature is enabled, and
command registration skips a gated feature whose service is absent."""

from __future__ import annotations

from lorecraft.commands import register_all_commands
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.services.container import ServiceContainer


def test_default_build_has_all_services() -> None:
    # enabled=None means "all on" — behaviour-preserving default.
    services = ServiceContainer.build()
    assert services.economy is not None
    assert services.bank is not None
    assert services.fatigue is not None
    # Always-on services are present too.
    assert services.movement is not None
    assert services.trade is not None


def test_disabled_feature_service_is_none() -> None:
    services = ServiceContainer.build(enabled={"fatigue"})
    assert services.fatigue is not None
    assert services.economy is None
    assert services.bank is None


def test_empty_enabled_disables_all_gated_services() -> None:
    services = ServiceContainer.build(enabled=set())
    assert services.economy is None
    assert services.bank is None
    assert services.fatigue is None
    # But always-on services remain.
    assert services.inventory is not None


def test_register_all_commands_skips_absent_gated_services() -> None:
    # With economy/bank/fatigue disabled, registration must not crash and must
    # not register their verbs.
    registry = CommandRegistry()
    services = ServiceContainer.build(enabled=set())
    register_all_commands(registry, services)
    for verb in ("buy", "sell", "deposit", "withdraw"):
        assert registry.get(verb) is None, f"{verb!r} should be absent when disabled"


def test_register_all_commands_registers_present_gated_services() -> None:
    registry = CommandRegistry()
    services = ServiceContainer.build()  # all on
    register_all_commands(registry, services)
    for verb in ("buy", "sell", "deposit", "withdraw"):
        assert registry.get(verb) is not None, (
            f"{verb!r} should be present when enabled"
        )
