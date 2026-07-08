"""Scavenger-hunt lifecycle: open, hunt (find), reward, close (Sprint 48).

Pure content on existing primitives (docs/scavenger_hunt.md): item spawns for
placement, the `ITEM_TAKEN` event for finds, player flags for progress, the
ledger for coin rewards, and news items for announcements. No new Tier 1
mechanism. The only global state is the in-memory set of currently-open hunts.
"""

from __future__ import annotations

import time
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.services.scheduler import SchedulerEventContext
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.features.hunts.models import HuntDef, HuntRegistry, get_registry
from lorecraft.models.news import NewsItem


def _found_flag(hunt_id: str, item_id: str) -> str:
    return f"hunt:{hunt_id}:found:{item_id}"


def _done_flag(hunt_id: str) -> str:
    return f"hunt:{hunt_id}:done"


class HuntService:
    def __init__(
        self,
        registry: HuntRegistry | None = None,
        ledger: LedgerService | None = None,
    ) -> None:
        self._registry = registry or get_registry()
        self._ledger = ledger or LedgerService()
        self._open: set[str] = set()

    JOB_OPEN = "hunt_open"
    JOB_CLOSE = "hunt_close"

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.ITEM_TAKEN, self._on_item_taken)
        bus.on(GameEvent.SCHEDULED_JOB_DUE, self._on_scheduled_job_due)

    def is_open(self, hunt_id: str) -> bool:
        return hunt_id in self._open

    def open_hunts(self) -> list[HuntDef]:
        return [h for h in self._registry.all() if h.id in self._open]

    # ---- lifecycle -----------------------------------------------------

    def open(self, hunt_id: str, session: Session, rng: GameRng) -> HuntDef:
        """Place the clue items across the pool rooms and announce (news).

        Deterministic given `rng`: each clue item is spawned into a room the
        rng picks from `spawn_rooms`. Never commits (the caller owns the txn)."""
        hunt = self._require(hunt_id)
        location = ItemLocationService(session)
        for item_id in hunt.clue_items:
            room_id = rng.choice(hunt.spawn_rooms)
            location.spawn(item_id, Location("room", room_id))
        self._open.add(hunt_id)
        self._announce(
            session,
            title=f"A hunt begins: {hunt.name}",
            body=hunt.description or f"{hunt.name} has begun. Seek the hidden items!",
        )
        return hunt

    def close(self, hunt_id: str, session: Session) -> HuntDef:
        """Despawn any un-taken clue items still in the pool rooms and announce."""
        hunt = self._require(hunt_id)
        stack_repo = StackRepo(session)
        location = ItemLocationService(session)
        clue_ids = set(hunt.clue_items)
        for room_id in set(hunt.spawn_rooms):
            for stack in stack_repo.stacks_for_owner("room", room_id):
                if stack.item_id in clue_ids and stack.id is not None:
                    location.destroy(stack.id, stack.quantity)
        self._open.discard(hunt_id)
        self._announce(
            session,
            title=f"A hunt ends: {hunt.name}",
            body=f"{hunt.name} has ended.",
        )
        return hunt

    def _on_scheduled_job_due(self, event: Event, ctx: object) -> None:
        """Open/close a hunt when its scheduled job fires. The scheduler hands
        us a `SchedulerEventContext` (game engine + rng), not a GameContext, so
        we run in our own committed transaction."""
        if not isinstance(ctx, SchedulerEventContext):
            return
        job_type = str(event.payload.get("job_type", ""))
        payload = event.payload.get("payload", {})
        hunt_id = str(payload.get("hunt_id", "")) if isinstance(payload, dict) else ""
        if not hunt_id or self._registry.get(hunt_id) is None:
            return
        if job_type == self.JOB_OPEN:
            open_hunt_with_engine(self, hunt_id, ctx.game_engine, ctx.rng)
        elif job_type == self.JOB_CLOSE:
            close_hunt_with_engine(self, hunt_id, ctx.game_engine)

    # ---- find + reward -------------------------------------------------

    def _on_item_taken(self, event: Event, ctx: object) -> None:
        if not isinstance(ctx, GameContext):
            return
        item_id = str(event.payload.get("item_id", ""))
        if not item_id:
            return
        for hunt in self.open_hunts():
            if item_id in hunt.clue_items:
                self._record_find(ctx, hunt, item_id)

    def _record_find(self, ctx: GameContext, hunt: HuntDef, item_id: str) -> None:
        if ctx.player.flags.get(_done_flag(hunt.id)):
            return
        flags = dict(ctx.player.flags)
        flags[_found_flag(hunt.id, item_id)] = True

        remaining = [
            i for i in hunt.clue_items if not flags.get(_found_flag(hunt.id, i))
        ]
        if remaining:
            ctx.player.flags = flags
            item = ItemRepo(ctx.session).get(item_id)
            label = item.name if item is not None else item_id
            ctx.say(
                f"You found a hunt item ({label})! "
                f"{len(remaining)} still to find for {hunt.name}.",
                MessageType.QUEST,
            )
            return

        # Completed the hunt this take.
        flags[_done_flag(hunt.id)] = True
        if hunt.reward.lore:
            flags[f"lore:{hunt.reward.lore}"] = True
        ctx.player.flags = flags
        if hunt.reward.coins > 0:
            self._ledger.credit(ctx.session, "player", ctx.player.id, hunt.reward.coins)
        ctx.say(
            (
                f"You've completed {hunt.name}! Reward: {hunt.reward.coins} coins."
                if hunt.reward.coins > 0
                else f"You've completed {hunt.name}!"
            ),
            MessageType.QUEST,
        )

    # ---- helpers -------------------------------------------------------

    def _announce(self, session: Session, *, title: str, body: str) -> None:
        session.add(
            NewsItem(
                id=f"hunt-{uuid4().hex[:12]}",
                type="event",
                title=title,
                body=body,
                author="Ashmoore",
                published_at=time.time(),
                priority="normal",
                tags=["hunt"],
            )
        )

    def _require(self, hunt_id: str) -> HuntDef:
        hunt = self._registry.get(hunt_id)
        if hunt is None:
            raise KeyError(f"unknown hunt: {hunt_id!r}")
        return hunt


def open_hunt_with_engine(
    service: HuntService, hunt_id: str, game_engine: Engine, rng: GameRng
) -> None:
    """Open a hunt in its own committed transaction — the entry point for an
    admin trigger or a scheduled `hunt_open` job (which only has the engine)."""
    with Session(game_engine) as session:
        service.open(hunt_id, session, rng)
        session.commit()


def close_hunt_with_engine(
    service: HuntService, hunt_id: str, game_engine: Engine
) -> None:
    with Session(game_engine) as session:
        service.close(hunt_id, session)
        session.commit()
