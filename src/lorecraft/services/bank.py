"""Banking: deposit, withdraw, balance (Sprint 28.3, docs/trade_economy.md §9).

Banked money is a ledger holder (CoinBalance("bank_account", account.id)),
immune to death/robbery since that code only ever touches the
("player", id) holder. One logical account, many branches -- deposit in
one room's branch, withdraw in another's. Every transfer is one
LedgerService.execute_exchange leg (Sprint 20).
"""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.repos.bank_repo import BankRepo
from lorecraft.services.ledger import ExchangeLeg, LedgerService


class BankService:
    def __init__(self, ledger: LedgerService | None = None) -> None:
        self.ledger = ledger or LedgerService()

    def _branch_here(self, ctx: GameContext) -> bool:
        repo = BankRepo(ctx.session)
        return any(
            repo.bank_for_npc(npc.id) is not None
            for npc in ctx.npc_repo.in_room(ctx.room.id)
        )

    def _parse_amount(self, noun: str | None) -> int | None:
        if noun is None:
            return None
        try:
            amount = int(noun.strip())
        except ValueError:
            return None
        return amount if amount > 0 else None

    def deposit(self, noun: str | None, ctx: GameContext) -> None:
        if not self._branch_here(ctx):
            ctx.say("There's no bank here.")
            return
        amount = self._parse_amount(noun)
        if amount is None:
            ctx.say("Deposit how much?")
            return
        if self.ledger.balance_of(ctx.session, "player", ctx.player.id) < amount:
            ctx.say(f"You don't have {amount} coins to deposit.")
            return

        account = BankRepo(ctx.session).get_or_create_account(ctx.player.id)
        self.ledger.execute_exchange(
            ctx.session,
            [
                ExchangeLeg(
                    give_from=Location("player", ctx.player.id),
                    give_to=Location("bank_account", account.id),
                    coins=amount,
                )
            ],
        )
        ctx.say(f"You deposit {amount} coins.")
        ctx.queue_event(
            GameEvent.MONEY_DEPOSITED,
            player_id=ctx.player.id,
            account_id=account.id,
            amount=amount,
        )

    def withdraw(self, noun: str | None, ctx: GameContext) -> None:
        if not self._branch_here(ctx):
            ctx.say("There's no bank here.")
            return
        amount = self._parse_amount(noun)
        if amount is None:
            ctx.say("Withdraw how much?")
            return

        account = BankRepo(ctx.session).get_or_create_account(ctx.player.id)
        if self.ledger.balance_of(ctx.session, "bank_account", account.id) < amount:
            ctx.say(f"Your account doesn't have {amount} coins.")
            return

        self.ledger.execute_exchange(
            ctx.session,
            [
                ExchangeLeg(
                    give_from=Location("bank_account", account.id),
                    give_to=Location("player", ctx.player.id),
                    coins=amount,
                )
            ],
        )
        ctx.say(f"You withdraw {amount} coins.")
        ctx.queue_event(
            GameEvent.MONEY_WITHDRAWN,
            player_id=ctx.player.id,
            account_id=account.id,
            amount=amount,
        )

    def balance(self, ctx: GameContext) -> None:
        carried = self.ledger.balance_of(ctx.session, "player", ctx.player.id)
        account = BankRepo(ctx.session).account_for_player(ctx.player.id)
        banked = (
            self.ledger.balance_of(ctx.session, "bank_account", account.id)
            if account is not None
            else 0
        )
        ctx.say(f"You are carrying {carried} coins and have {banked} coins banked.")
