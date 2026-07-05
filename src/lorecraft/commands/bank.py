"""Banking commands: deposit, withdraw, balance (Sprint 28.3)."""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.registry import CommandCondition, CommandRegistry
from lorecraft.services.bank import BankService


def register_bank_commands(
    registry: CommandRegistry, bank: BankService | None = None
) -> None:
    service = bank or BankService()

    @registry.register(
        "deposit",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="deposit <amount> — deposit carried coins at a bank branch",
    )
    def deposit_command(noun: str | None, ctx: GameContext) -> None:
        service.deposit(noun, ctx)

    @registry.register(
        "withdraw",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="withdraw <amount> — withdraw banked coins at a bank branch",
    )
    def withdraw_command(noun: str | None, ctx: GameContext) -> None:
        service.withdraw(noun, ctx)

    @registry.register(
        "balance",
        conditions=[CommandCondition.NOT_IN_COMBAT],
        help="balance — show coins carried and banked",
    )
    def balance_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        service.balance(ctx)
