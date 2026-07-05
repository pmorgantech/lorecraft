"""Save slots and disconnect safety services."""

from __future__ import annotations

from dataclasses import dataclass
import time
from uuid import uuid4

from sqlmodel import Session

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.transaction import TransactionSource
from lorecraft.models.audit import AuditEvent
from lorecraft.models.player import Player, PlayerStats, SaveSlot
from lorecraft.models.session import PlayerSession
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.types import JsonObject, JsonValue

VALID_SAVE_SLOTS = {"auto", "slot1", "slot2", "slot3"}


@dataclass(frozen=True)
class SessionStartResult:
    player_session: PlayerSession
    reconnected: bool


@dataclass(frozen=True)
class SessionEventContext:
    player_id: str
    session_id: str


class SaveSlotService:
    def save(self, slot_name: str | None, ctx: GameContext) -> None:
        slot = normalize_save_slot(slot_name)
        if slot is None:
            ctx.say("Use save auto, save slot1, save slot2, or save slot3.")
            return

        save_slot = ctx.player_repo.save_slot(ctx.player.id, slot)
        if save_slot is None:
            save_slot = SaveSlot(
                player_id=ctx.player.id,
                slot_name=slot,
                saved_at=time.time(),
                room_id=ctx.player.current_room_id,
            )
            ctx.player_repo.add_save_slot(save_slot)

        save_slot.saved_at = time.time()
        save_slot.room_id = ctx.player.current_room_id
        save_slot.inventory = _inventory_snapshot(ctx)
        save_slot.visited_rooms = list(ctx.player.visited_rooms)
        save_slot.met_npcs = list(ctx.player.met_npcs)
        save_slot.flags = dict(ctx.player.flags)
        save_slot.stats_snapshot = _stats_snapshot(
            ctx, ctx.player_repo.stats(ctx.player.id)
        )
        save_slot.quest_progress = {}

        ctx.say(f"Saved to {slot}.")
        ctx.push_update("save_slot", slot)

    def load(self, slot_name: str | None, ctx: GameContext) -> None:
        slot = normalize_save_slot(slot_name)
        if slot is None:
            ctx.say("Use load auto, load slot1, load slot2, or load slot3.")
            return

        save_slot = ctx.player_repo.save_slot(ctx.player.id, slot)
        if save_slot is None:
            ctx.say(f"No save found in {slot}.")
            return

        target_room = ctx.room_repo.active(save_slot.room_id)
        if target_room is None:
            ctx.say("That save points to a room that no longer exists.")
            return

        previous_room_id = ctx.room.id
        ctx.player.current_room_id = target_room.id
        _restore_inventory(ctx, save_slot.inventory)
        ctx.player.visited_rooms = list(save_slot.visited_rooms)
        if target_room.id not in ctx.player.visited_rooms:
            ctx.player.visited_rooms = [*ctx.player.visited_rooms, target_room.id]
        ctx.player.met_npcs = list(save_slot.met_npcs)
        ctx.player.flags = dict(save_slot.flags)
        _apply_stats_snapshot(ctx, save_slot.stats_snapshot)

        ctx.manager.move_player(ctx.player.id, previous_room_id, target_room.id)
        ctx.room = target_room

        ctx.say(f"Loaded {slot}.")
        ctx.push_update("room_id", target_room.id)
        ctx.push_update("save_slot", slot)
        ctx.queue_event(
            GameEvent.SAVE_LOADED,
            player_id=ctx.player.id,
            slot_name=slot,
            room_id=target_room.id,
        )


class SessionSafetyService:
    def __init__(
        self,
        *,
        game_session: Session,
        audit_session: Session,
        bus: EventBus,
        grace_seconds: float,
        now: float | None = None,
    ) -> None:
        self.game_session = game_session
        self.audit_session = audit_session
        self.player_repo = PlayerRepo(game_session)
        self.room_repo = RoomRepo(game_session)
        self.audit_repo = AuditRepo(audit_session)
        self.bus = bus
        self.grace_seconds = grace_seconds
        self.now = time.time() if now is None else now

    def start_or_resume_session(self, player: Player) -> SessionStartResult:
        self.expire_due_grace_periods(player_id=player.id)
        grace_session = self.player_repo.reconnectable_session(player.id, self.now)
        if grace_session is not None:
            grace_session.status = "active"
            grace_session.disconnected_at = None
            grace_session.grace_expires_at = None
            self._record_system_event(
                player,
                grace_session,
                GameEvent.PLAYER_RECONNECTED,
                summary="Player reconnected.",
            )
            self.bus.emit(
                Event(
                    GameEvent.PLAYER_RECONNECTED,
                    {"player_id": player.id, "session_id": grace_session.id},
                ),
                SessionEventContext(player_id=player.id, session_id=grace_session.id),
            )
            return SessionStartResult(grace_session, reconnected=True)

        player_session = PlayerSession(
            id=str(uuid4()),
            player_id=player.id,
            connected_at=self.now,
        )
        self.player_repo.add_session(player_session)
        return SessionStartResult(player_session, reconnected=False)

    def begin_grace_period(
        self, session_id: str, player: Player
    ) -> PlayerSession | None:
        player_session = self.player_repo.player_session(session_id)
        if player_session is None:
            return None

        player_session.status = "grace"
        player_session.disconnected_at = self.now
        player_session.grace_expires_at = self.now + self.grace_seconds
        self._record_system_event(
            player,
            player_session,
            GameEvent.PLAYER_DISCONNECTED,
            summary="Player disconnected; grace period started.",
            payload={"grace_expires_at": player_session.grace_expires_at},
        )
        self.bus.emit(
            Event(
                GameEvent.PLAYER_DISCONNECTED,
                {
                    "player_id": player.id,
                    "session_id": player_session.id,
                    "grace_expires_at": player_session.grace_expires_at,
                },
            ),
            SessionEventContext(player_id=player.id, session_id=player_session.id),
        )
        return player_session

    def expire_due_grace_periods(
        self, *, player_id: str | None = None
    ) -> list[PlayerSession]:
        expired_sessions = list(
            self.player_repo.expired_grace_sessions(self.now, player_id=player_id)
        )
        for player_session in expired_sessions:
            player = self.player_repo.get(player_session.player_id)
            if player is None:
                player_session.status = "expired"
                continue

            player_session.status = (
                "system_controlled"
                if player.active_combat_session_id is not None
                else "expired"
            )
            self._record_system_event(
                player,
                player_session,
                GameEvent.GRACE_PERIOD_EXPIRED,
                summary="Disconnect grace period expired.",
                payload={"status": player_session.status},
            )
            self.bus.emit(
                Event(
                    GameEvent.GRACE_PERIOD_EXPIRED,
                    {
                        "player_id": player.id,
                        "session_id": player_session.id,
                        "status": player_session.status,
                    },
                ),
                SessionEventContext(player_id=player.id, session_id=player_session.id),
            )
        return expired_sessions

    def _record_system_event(
        self,
        player: Player,
        player_session: PlayerSession,
        event_type: GameEvent,
        *,
        summary: str,
        payload: JsonObject | None = None,
    ) -> None:
        clock = self.room_repo.world_clock()
        self.audit_repo.record(
            AuditEvent(
                transaction_id=str(uuid4()),
                correlation_id=player_session.id,
                actor_id=player.id,
                event_type=event_type.value,
                source_type=TransactionSource.SYSTEM.value,
                room_id=player.current_room_id,
                game_time=clock.game_epoch if clock is not None else 0.0,
                real_time=self.now,
                summary=summary,
                payload_json=payload or {},
            )
        )


def normalize_save_slot(slot_name: str | None) -> str | None:
    slot = (slot_name or "auto").strip().lower()
    if slot in VALID_SAVE_SLOTS:
        return slot
    return None


def _inventory_snapshot(ctx: GameContext) -> list[JsonValue]:
    """Carried stacks as a save-slot snapshot (v2 shape: one dict per stack)."""
    return [
        {
            "item_id": stack.item_id,
            "quantity": stack.quantity,
            "instance_id": stack.instance_id,
        }
        for stack, _item in ctx.item_repo.stacks_carried_by(ctx.player.id)
    ]


def _restore_inventory(ctx: GameContext, snapshot: list[JsonValue]) -> None:
    """Replace the player's carried stacks with a save-slot snapshot.

    Accepts both the v2 shape (list of {item_id, quantity, instance_id} dicts)
    and the pre-Sprint-16 v1 shape (a flat list[str] of item ids, one entry
    per carried unit) — old saves must not break. v1 entries spawn one unit
    at a time, which merges into a single fungible stack via spawn()'s
    existing-stack lookup.
    """
    loc = Location("player", ctx.player.id)
    for stack in ctx.stack_repo.stacks_for_owner("player", ctx.player.id):
        assert stack.id is not None
        ctx.item_location.destroy(stack.id, stack.quantity)

    for entry in snapshot:
        if isinstance(entry, str):
            ctx.item_location.spawn(entry, loc, 1)
        elif isinstance(entry, dict):
            item_id = entry.get("item_id")
            quantity = entry.get("quantity", 1)
            if isinstance(item_id, str) and isinstance(quantity, int) and quantity > 0:
                ctx.item_location.spawn(item_id, loc, quantity)


def _stats_snapshot(ctx: GameContext, stats: PlayerStats | None) -> JsonObject:
    if stats is None:
        return {}
    hp_meter = ctx.meters.get(ctx.session, "player", ctx.player.id, "hp")
    return {
        "strength": stats.strength,
        "agility": stats.agility,
        "vitality": stats.vitality,
        "intellect": stats.intellect,
        "presence": stats.presence,
        "fortitude": stats.fortitude,
        "max_hp": stats.max_hp,
        "level": stats.level,
        "xp": stats.xp,
        "xp_to_next": stats.xp_to_next,
        "skills": dict(stats.skills),
        # v2 (Sprint 19): runtime hp lives in Meter("player", id, "hp"), not
        # PlayerStats.current_hp (deleted). See _apply_stats_snapshot for the
        # v1 (flat "current_hp" int) conversion-on-read.
        "meters": {"hp": hp_meter.current},
    }


def _apply_stats_snapshot(ctx: GameContext, snapshot: JsonObject) -> None:
    if not snapshot:
        return
    stats = ctx.player_repo.stats(ctx.player.id)
    if stats is None:
        stats = PlayerStats(player_id=ctx.player.id)
        ctx.player_repo.save_stats(stats)

    for field in (
        "strength",
        "agility",
        "vitality",
        "intellect",
        "presence",
        "fortitude",
        "max_hp",
        "level",
        "xp",
        "xp_to_next",
    ):
        value = snapshot.get(field)
        if isinstance(value, int):
            setattr(stats, field, value)
    skills = snapshot.get("skills")
    if isinstance(skills, dict):
        stats.skills = dict(skills)

    hp_value: object = None
    meters_snapshot = snapshot.get("meters")
    if isinstance(meters_snapshot, dict):
        hp_value = meters_snapshot.get("hp")
    elif "current_hp" in snapshot:
        hp_value = snapshot.get("current_hp")  # v1 shape compat
    if isinstance(hp_value, (int, float)):
        hp_meter = ctx.meters.get(ctx.session, "player", ctx.player.id, "hp")
        ctx.meters.set_current(ctx.session, hp_meter, float(hp_value))
