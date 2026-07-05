"""Player-to-player trade: offer, accept, decline (Sprint 28.4,
docs/trade_economy.md §8).

A safe two-party handshake built directly on LedgerService.execute_exchange
(Sprint 20): `offer` only ever records intent (a TradeOffer row) and moves
nothing; `accept` composes exactly one execute_exchange call with both
sides' pledges as legs. That call's own leg validation *is* the escrow
revalidation -- if either side no longer holds what they pledged, the whole
exchange raises and nothing moves. Policy gates (tradeable, not bound, same
room, not expired) are re-checked at accept time, not just at offer time.
"""

from __future__ import annotations

import time

from lorecraft.errors import ConflictError, NotFoundError
from lorecraft.engine.game.command_patterns import (
    ROLE_OBJECT,
    ROLE_QUANTITY,
    ROLE_RECIPIENT,
    role_int,
    role_str,
)
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.features.trading.repo import TradeRepo
from lorecraft.engine.services.ledger import ExchangeLeg, LedgerService


class TradeService:
    def __init__(self, ledger: LedgerService | None = None) -> None:
        self.ledger = ledger or LedgerService()

    def _find_recipient(self, ctx: GameContext, name: str):
        query = name.strip().lower()
        for player in ctx.player_repo.in_room(ctx.room.id):
            if player.id != ctx.player.id and player.username.lower() == query:
                return player
        return None

    def offer(self, noun: str | None, ctx: GameContext) -> None:
        del noun
        parsed = ctx.parsed_command
        object_phrase = role_str(parsed, ROLE_OBJECT) if parsed else None
        recipient_phrase = role_str(parsed, ROLE_RECIPIENT) if parsed else None
        if not object_phrase or not recipient_phrase:
            ctx.say("Offer what to whom? (e.g. offer sword to Bob)")
            return

        recipient = self._find_recipient(ctx, recipient_phrase)
        if recipient is None:
            ctx.say(f"There is no {recipient_phrase} here.")
            return

        repo = TradeRepo(ctx.session)
        existing = repo.find_open_for_player(ctx.player.id)
        if (
            existing is not None
            and existing.recipient_id != recipient.id
            and existing.initiator_id != recipient.id
        ):
            ctx.say(
                "You already have a pending trade with someone else. Decline it first."
            )
            return
        offer_row = (
            existing
            or repo.find_open_between(ctx.player.id, recipient.id)
            or repo.create(ctx.player.id, recipient.id)
        )

        # The parser strips a leading quantity out of the object phrase (e.g.
        # "40 coins" -> quantity=40, object="coins"), so a coin pledge is
        # detected from the bare noun plus the separately-parsed quantity.
        if object_phrase.strip().lower() in {"coin", "coins"}:
            amount = role_int(parsed, ROLE_QUANTITY) if parsed else None
            if not amount or amount <= 0:
                ctx.say("Offer how many coins?")
                return
            if ctx.player.id == offer_row.initiator_id:
                offer_row.initiator_coins = amount
            else:
                offer_row.recipient_coins = amount
            repo.save(offer_row)
            ctx.say(f"You offer {amount} coins to {recipient.username}.")
            return

        stacks = ctx.item_repo.player_stacks_matching(ctx.player.id, object_phrase)
        if not stacks:
            ctx.say("You don't have that.")
            return
        stack, item = stacks[0]
        if not item.tradeable or item.bound:
            ctx.say(f"You can't trade {item.name}.")
            return
        requested_quantity = role_int(parsed, ROLE_QUANTITY) if parsed else None
        quantity = min(requested_quantity or 1, stack.quantity)
        assert stack.id is not None

        side = (
            offer_row.initiator_stacks
            if ctx.player.id == offer_row.initiator_id
            else offer_row.recipient_stacks
        )
        side = [pair for pair in side if pair[0] != stack.id]
        side.append([stack.id, quantity])
        if ctx.player.id == offer_row.initiator_id:
            offer_row.initiator_stacks = side
        else:
            offer_row.recipient_stacks = side
        repo.save(offer_row)

        label = item.name if quantity == 1 else f"{quantity} {item.name}"
        ctx.say(f"You offer {label} to {recipient.username}.")

    def accept(self, noun: str | None, ctx: GameContext) -> None:
        del noun
        offer_row = TradeRepo(ctx.session).find_open_for_player(ctx.player.id)
        if offer_row is None:
            ctx.say("You have no pending trade offer.")
            return
        if time.time() > offer_row.expires_at:
            offer_row.status = "expired"
            TradeRepo(ctx.session).save(offer_row)
            ctx.say("That trade offer has expired.")
            return

        other_id = (
            offer_row.recipient_id
            if ctx.player.id == offer_row.initiator_id
            else offer_row.initiator_id
        )
        other = ctx.player_repo.get(other_id)
        if other is None or other.current_room_id != ctx.player.current_room_id:
            ctx.say(
                f"{'They' if other is None else other.username} are no longer here."
            )
            return

        legs: list[ExchangeLeg] = []
        for stack_id, quantity in offer_row.initiator_stacks:
            item = self._item_for_stack(ctx, stack_id)
            if item is None or not item.tradeable or item.bound:
                ctx.say(
                    "The trade fell through — one side's item is no longer tradeable."
                )
                return
            legs.append(
                ExchangeLeg(
                    give_from=Location("player", offer_row.initiator_id),
                    give_to=Location("player", offer_row.recipient_id),
                    stacks=((stack_id, quantity),),
                )
            )
        for stack_id, quantity in offer_row.recipient_stacks:
            item = self._item_for_stack(ctx, stack_id)
            if item is None or not item.tradeable or item.bound:
                ctx.say(
                    "The trade fell through — one side's item is no longer tradeable."
                )
                return
            legs.append(
                ExchangeLeg(
                    give_from=Location("player", offer_row.recipient_id),
                    give_to=Location("player", offer_row.initiator_id),
                    stacks=((stack_id, quantity),),
                )
            )
        if offer_row.initiator_coins > 0:
            legs.append(
                ExchangeLeg(
                    give_from=Location("player", offer_row.initiator_id),
                    give_to=Location("player", offer_row.recipient_id),
                    coins=offer_row.initiator_coins,
                )
            )
        if offer_row.recipient_coins > 0:
            legs.append(
                ExchangeLeg(
                    give_from=Location("player", offer_row.recipient_id),
                    give_to=Location("player", offer_row.initiator_id),
                    coins=offer_row.recipient_coins,
                )
            )

        if not legs:
            ctx.say("There's nothing pledged to that trade yet.")
            return

        try:
            self.ledger.execute_exchange(ctx.session, legs)
        except (ConflictError, NotFoundError):
            offer_row.status = "declined"
            TradeRepo(ctx.session).save(offer_row)
            ctx.say("The trade fell through — one side no longer has what was pledged.")
            return

        offer_row.status = "accepted"
        TradeRepo(ctx.session).save(offer_row)
        ctx.say(f"Trade complete with {other.username}!")
        ctx.tell_room(f"{ctx.player.username} and {other.username} strike a deal.")
        ctx.queue_event(
            GameEvent.TRADE_COMPLETED,
            initiator_id=offer_row.initiator_id,
            recipient_id=offer_row.recipient_id,
            offer_id=offer_row.id,
        )

    def decline(self, noun: str | None, ctx: GameContext) -> None:
        del noun
        offer_row = TradeRepo(ctx.session).find_open_for_player(ctx.player.id)
        if offer_row is None:
            ctx.say("You have no pending trade offer.")
            return
        offer_row.status = "declined"
        TradeRepo(ctx.session).save(offer_row)
        ctx.say("You call off the trade.")

    def _item_for_stack(self, ctx: GameContext, stack_id: int):
        stack = ctx.stack_repo.find_stack(stack_id)
        if stack is None:
            return None
        return ctx.item_repo.get(stack.item_id)
