"""Scheduled Intent combat service."""

from __future__ import annotations

import time
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.scheduler import ScheduledJob
from lorecraft.engine.models.world import NPC
from lorecraft.engine.repos.meter_repo import MeterRepo
from lorecraft.engine.repos.scheduler_repo import SchedulerRepo
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.scheduler import SchedulerEventContext
from lorecraft.features.combat.models import (
    CombatAction,
    CombatEncounter,
    CombatParticipant,
    CombatRelationship,
    CombatResolutionRecord,
)
from lorecraft.features.combat.repo import CombatRepo
from lorecraft.features.combat.damage import armor_profile_for, weapon_profile_for
from lorecraft.features.combat.resolution import (
    CombatResolution,
    CombatantSnapshot,
    npc_snapshot,
    player_snapshot,
    resolve_basic_attack,
)
from lorecraft.types import JsonObject

COMBAT_RESOLVE_JOB = "combat.resolve_action"

_ACTION_TIMING: dict[str, tuple[float, float]] = {
    "basic_attack": (0.25, 2.0),
    "defend": (0.0, 1.2),
    "flee": (0.35, 2.5),
}


class CombatService:
    """Owns combat policy and persistence for the Tier 2 combat feature."""

    def attack(self, noun: str | None, ctx: GameContext) -> None:
        target = self._resolve_npc_target(noun, ctx)
        if target is None:
            ctx.say("Attack whom?", MessageType.WARNING)
            return
        encounter, actor, target_participant = self._ensure_player_vs_npc_encounter(
            ctx, target
        )
        action = self._submit_action(
            repo=CombatRepo(ctx.session),
            session=ctx.session,
            encounter=encounter,
            actor=actor,
            action_key="basic_attack",
            now=self._now(ctx),
            target=target_participant,
        )
        ctx.player.active_combat_session_id = encounter.id
        ctx.player_repo.add(ctx.player)
        ctx.say(f"You commit to an attack on {target.name}.")
        ctx.tell_room(f"{ctx.player.username} moves to strike {target.name}.")
        ctx.queue_event(
            GameEvent.COMBAT_STARTED,
            encounter_id=encounter.id,
            actor_id=ctx.player.id,
            target_id=target.id,
            action_id=action.id,
        )
        self._push_combat_update(ctx, encounter.id)

    def defend(self, noun: str | None, ctx: GameContext) -> None:
        del noun
        encounter, actor = self._active_player_participation(ctx)
        if encounter is None or actor is None:
            ctx.say("You aren't in combat.", MessageType.WARNING)
            return
        self._submit_action(
            repo=CombatRepo(ctx.session),
            session=ctx.session,
            encounter=encounter,
            actor=actor,
            action_key="defend",
            now=self._now(ctx),
        )
        ctx.say("You shift into a guarded posture.")
        self._push_combat_update(ctx, encounter.id)

    def flee(self, noun: str | None, ctx: GameContext) -> None:
        del noun
        encounter, actor = self._active_player_participation(ctx)
        if encounter is None or actor is None:
            ctx.say("You aren't in combat.", MessageType.WARNING)
            return
        self._submit_action(
            repo=CombatRepo(ctx.session),
            session=ctx.session,
            encounter=encounter,
            actor=actor,
            action_key="flee",
            now=self._now(ctx),
        )
        ctx.say("You look for an opening to flee.")
        self._push_combat_update(ctx, encounter.id)

    def register(self, bus: EventBus) -> None:
        bus.on(GameEvent.SCHEDULED_JOB_DUE, self._on_scheduled_job_due)

    def resolve_action(
        self,
        session: Session,
        action_id: str,
        *,
        rng,
        current_epoch: float,
        bus: EventBus | None = None,
        meter_service: MeterService | None = None,
    ) -> CombatAction | None:
        repo = CombatRepo(session)
        action = repo.action(action_id)
        if action is None or action.state == "resolved":
            return action
        if action.state == "cancelled":
            return action
        encounter = repo.encounter(action.encounter_id)
        actor = repo.participant(action.actor_participant_id)
        if encounter is None or actor is None or encounter.state != "active":
            action.state = "cancelled"
            repo.add(action)
            return action
        if actor.status != "active":
            action.state = "cancelled"
            repo.add(action)
            return action

        meter_service = meter_service or MeterService(_session_engine(session), rng)
        resolution = self._calculate_resolution(session, repo, action, actor, rng=rng)
        self._apply_resolution(
            session,
            repo,
            encounter,
            action,
            actor,
            resolution,
            current_epoch=current_epoch,
            meter_service=meter_service,
        )
        if bus is not None:
            self._emit_resolution_events(bus, repo, encounter, resolution, action)
        if action.actor_type == "player" and action.action_key == "basic_attack":
            self._maybe_schedule_npc_response(
                session,
                repo,
                encounter,
                action,
                current_epoch=current_epoch,
            )
        self._maybe_end_encounter(session, repo, encounter, current_epoch)
        return action

    def _on_scheduled_job_due(self, event: Event, ctx: object) -> None:
        if event.payload.get("job_type") != COMBAT_RESOLVE_JOB:
            return
        if not isinstance(ctx, SchedulerEventContext):
            return
        payload = event.payload.get("payload")
        if not isinstance(payload, dict):
            return
        action_id = payload.get("action_id")
        if not isinstance(action_id, str):
            return
        current_epoch = _float_payload(event.payload, "current_epoch")
        with Session(ctx.game_engine) as session:
            self.resolve_action(
                session,
                action_id,
                rng=ctx.rng,
                current_epoch=current_epoch,
                bus=ctx.bus,
            )
            session.commit()

    def _resolve_npc_target(self, noun: str | None, ctx: GameContext) -> NPC | None:
        if noun:
            return ctx.npc_repo.find_in_room(ctx.room.id, noun)
        encounter, actor = self._active_player_participation(ctx)
        if encounter is None or actor is None:
            return None
        target = CombatRepo(ctx.session).hostile_target_for(encounter.id, actor.id)
        if target is None or target.actor_type != "npc":
            return None
        return ctx.npc_repo.get(target.actor_id)

    def _ensure_player_vs_npc_encounter(
        self, ctx: GameContext, npc: NPC
    ) -> tuple[CombatEncounter, CombatParticipant, CombatParticipant]:
        now = self._now(ctx)
        repo = CombatRepo(ctx.session)
        encounter = repo.active_encounter_for_actor("player", ctx.player.id)
        if encounter is None:
            encounter = CombatEncounter(
                id=str(uuid4()),
                location_id=ctx.room.id,
                started_at_game_time=now,
                started_at_real_time=time.time(),
                last_hostile_action_at=now,
            )
            repo.add(encounter)
        actor = repo.participant_for_actor(encounter.id, "player", ctx.player.id)
        if actor is None:
            actor = CombatParticipant(
                id=str(uuid4()),
                encounter_id=encounter.id,
                actor_type="player",
                actor_id=ctx.player.id,
                side_id=f"player:{ctx.player.id}",
                joined_at=now,
                primary_ready_at=now,
                reaction_ready_at=now,
            )
            repo.add(actor)
        target = repo.participant_for_actor(encounter.id, "npc", npc.id)
        if target is None:
            target = CombatParticipant(
                id=str(uuid4()),
                encounter_id=encounter.id,
                actor_type="npc",
                actor_id=npc.id,
                side_id=f"npc:{npc.id}",
                joined_at=now,
                primary_ready_at=now + 1.0,
                reaction_ready_at=now,
            )
            repo.add(target)
        self._ensure_hostile_edges(repo, encounter.id, actor.id, target.id)
        return encounter, actor, target

    def _ensure_hostile_edges(
        self, repo: CombatRepo, encounter_id: str, source_id: str, target_id: str
    ) -> None:
        for left, right in ((source_id, target_id), (target_id, source_id)):
            repo.add(
                CombatRelationship(
                    id=str(uuid4()),
                    encounter_id=encounter_id,
                    source_participant_id=left,
                    target_participant_id=right,
                )
            )

    def _active_player_participation(
        self, ctx: GameContext
    ) -> tuple[CombatEncounter | None, CombatParticipant | None]:
        if not ctx.player.active_combat_session_id:
            return None, None
        repo = CombatRepo(ctx.session)
        encounter = repo.encounter(ctx.player.active_combat_session_id)
        if encounter is None or encounter.state != "active":
            return None, None
        actor = repo.participant_for_actor(encounter.id, "player", ctx.player.id)
        return encounter, actor

    def _submit_action(
        self,
        *,
        repo: CombatRepo,
        session: Session,
        encounter: CombatEncounter,
        actor: CombatParticipant,
        action_key: str,
        now: float,
        target: CombatParticipant | None = None,
    ) -> CombatAction:
        windup, recovery = _ACTION_TIMING[action_key]
        starts_at = max(now, actor.primary_ready_at)
        existing = repo.pending_primary_action(actor.id)
        if existing is not None:
            existing.state = "cancelled"
            repo.add(existing)
        action = CombatAction(
            id=str(uuid4()),
            encounter_id=encounter.id,
            actor_participant_id=actor.id,
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            target_participant_id=target.id if target is not None else None,
            target_type=target.actor_type if target is not None else None,
            target_id=target.actor_id if target is not None else None,
            action_key=action_key,
            state="pending" if starts_at <= now else "queued",
            submitted_at=now,
            resolve_at=starts_at + windup,
            recovery_until=starts_at + windup + recovery,
        )
        repo.add(action)
        actor.primary_ready_at = action.recovery_until
        actor.queued_action_id = action.id if action.state == "queued" else None
        repo.add(actor)
        encounter.last_hostile_action_at = now
        repo.add(encounter)
        self._schedule_resolution(session, action)
        return action

    def _schedule_resolution(self, session: Session, action: CombatAction) -> None:
        SchedulerRepo(session).add(
            ScheduledJob(
                id=str(uuid4()),
                job_type=COMBAT_RESOLVE_JOB,
                due_at_epoch=action.resolve_at,
                payload={"action_id": action.id},
                created_at=time.time(),
            )
        )

    def _calculate_resolution(
        self,
        session: Session,
        repo: CombatRepo,
        action: CombatAction,
        actor: CombatParticipant,
        *,
        rng,
    ) -> CombatResolution:
        if action.action_key == "defend":
            snapshot = self._snapshot(session, actor)
            return CombatResolution(
                action_id=action.id,
                action_key="defend",
                actor=snapshot,
                target=None,
                outcome="defended",
                stamina_delta=-2.0,
                explanation=f"{snapshot.name} braces defensively.",
            )
        if action.action_key == "flee":
            snapshot = self._snapshot(session, actor)
            return CombatResolution(
                action_id=action.id,
                action_key="flee",
                actor=snapshot,
                target=None,
                outcome="escaped",
                stamina_delta=-8.0,
                target_status="escaped",
                explanation=f"{snapshot.name} breaks away from the fight.",
            )
        target = (
            repo.participant(action.target_participant_id)
            if action.target_participant_id is not None
            else None
        )
        if target is None or target.status != "active":
            snapshot = self._snapshot(session, actor)
            return CombatResolution(
                action_id=action.id,
                action_key=action.action_key,
                actor=snapshot,
                target=None,
                outcome="cancelled",
                explanation="The target is no longer available.",
            )
        defended = self._has_recent_defend(repo, target.id, action.submitted_at)
        return resolve_basic_attack(
            action_id=action.id,
            actor=self._snapshot(session, actor),
            target=self._snapshot(session, target),
            weapon=weapon_profile_for(session, actor.actor_type, actor.actor_id),
            armor=armor_profile_for(session, target.actor_type, target.actor_id),
            rng=rng,
            defended=defended,
        )

    def _record_resolution(
        self,
        repo: CombatRepo,
        encounter: CombatEncounter,
        action: CombatAction,
        resolution: CombatResolution,
        *,
        resolved_at: float,
    ) -> None:
        if repo.resolution_record_for_action(action.id) is not None:
            return
        target_type = (
            resolution.target.actor_type if resolution.target is not None else None
        )
        target_id = (
            resolution.target.actor_id if resolution.target is not None else None
        )
        repo.add(
            CombatResolutionRecord(
                id=str(uuid4()),
                encounter_id=encounter.id,
                action_id=action.id,
                actor_type=resolution.actor.actor_type,
                actor_id=resolution.actor.actor_id,
                target_type=target_type,
                target_id=target_id,
                action_key=resolution.action_key,
                outcome=resolution.outcome,
                damage=resolution.damage,
                resolved_at_game_time=resolved_at,
                ruleset_id=encounter.ruleset_id,
                random_trace=resolution.random_trace or {},
                damage_trace=resolution.damage_trace or {},
                payload=self._resolution_payload(resolution),
            )
        )

    def _apply_resolution(
        self,
        session: Session,
        repo: CombatRepo,
        encounter: CombatEncounter,
        action: CombatAction,
        actor: CombatParticipant,
        resolution: CombatResolution,
        *,
        current_epoch: float,
        meter_service: MeterService,
    ) -> None:
        action.state = "resolved"
        encounter.event_sequence += 1
        action.outcome = self._resolution_payload(resolution)
        action.random_trace = resolution.random_trace or {}
        self._record_resolution(
            repo,
            encounter,
            action,
            resolution,
            resolved_at=current_epoch,
        )
        if actor.queued_action_id == action.id:
            actor.queued_action_id = None
        if resolution.stamina_delta:
            stamina = meter_service.get(
                session, actor.actor_type, actor.actor_id, "stamina"
            )
            meter_service.adjust(session, stamina, resolution.stamina_delta)
        if resolution.action_key == "flee" and resolution.outcome == "escaped":
            actor.status = "escaped"
            if actor.actor_type == "player":
                player = session.get(Player, actor.actor_id)
                if player is not None:
                    player.active_combat_session_id = None
                    session.add(player)
        target = (
            repo.participant(action.target_participant_id)
            if action.target_participant_id is not None
            else None
        )
        if target is not None and resolution.damage > 0:
            hp = meter_service.get(session, target.actor_type, target.actor_id, "hp")
            change = meter_service.adjust(session, hp, -resolution.damage)
            self._add_contribution(actor, resolution.damage)
            if change.depleted:
                target.status = "defeated" if target.actor_type == "npc" else "downed"
                if target.actor_type == "player":
                    player = session.get(Player, target.actor_id)
                    if player is not None:
                        player.active_combat_session_id = None
                        session.add(player)
                repo.add(target)
        encounter.last_hostile_action_at = current_epoch
        repo.add(actor)
        repo.add(action)
        repo.add(encounter)

    def _maybe_schedule_npc_response(
        self,
        session: Session,
        repo: CombatRepo,
        encounter: CombatEncounter,
        action: CombatAction,
        *,
        current_epoch: float,
    ) -> None:
        target = (
            repo.participant(action.target_participant_id)
            if action.target_participant_id is not None
            else None
        )
        actor = repo.participant(action.actor_participant_id)
        if target is None or actor is None or target.actor_type != "npc":
            return
        if target.status != "active" or actor.status != "active":
            return
        if repo.pending_primary_action(target.id) is not None:
            return
        self._submit_action(
            repo=repo,
            session=session,
            encounter=encounter,
            actor=target,
            action_key="basic_attack",
            now=current_epoch,
            target=actor,
        )

    def _maybe_end_encounter(
        self,
        session: Session,
        repo: CombatRepo,
        encounter: CombatEncounter,
        current_epoch: float,
    ) -> None:
        active = list(repo.active_participants(encounter.id))
        active_sides = {participant.side_id for participant in active}
        if len(active_sides) > 1:
            return
        encounter.state = "ended"
        encounter.ended_at_game_time = current_epoch
        repo.add(encounter)
        for participant in active:
            if participant.actor_type == "player":
                player = session.get(Player, participant.actor_id)
                if player is not None:
                    player.active_combat_session_id = None
                    session.add(player)

    def _snapshot(
        self, session: Session, participant: CombatParticipant
    ) -> CombatantSnapshot:
        if participant.actor_type == "player":
            player = session.get(Player, participant.actor_id)
            stats = session.get(PlayerStats, participant.actor_id)
            return player_snapshot(
                participant.actor_id,
                player.username if player is not None else participant.actor_id,
                stats,
            )
        npc = session.get(NPC, participant.actor_id)
        if npc is None:
            return CombatantSnapshot(
                actor_type="npc",
                actor_id=participant.actor_id,
                name=participant.actor_id,
                strength=10,
                agility=8,
            )
        return npc_snapshot(npc)

    def _has_recent_defend(
        self, repo: CombatRepo, participant_id: str, since: float
    ) -> bool:
        action = repo.pending_primary_action(participant_id)
        return bool(
            action is not None
            and action.action_key == "defend"
            and action.submitted_at >= since - 3.0
        )

    def _add_contribution(self, actor: CombatParticipant, damage: float) -> None:
        contribution = dict(actor.contribution)
        contribution["damage"] = _float_mapping(contribution, "damage") + damage
        actor.contribution = contribution

    def _emit_resolution_events(
        self,
        bus: EventBus,
        repo: CombatRepo,
        encounter: CombatEncounter,
        resolution: CombatResolution,
        action: CombatAction,
    ) -> None:
        event_type = (
            GameEvent.PLAYER_ATTACKED
            if action.actor_type == "player"
            else GameEvent.NPC_ATTACKED
        )
        bus.emit(
            Event(
                event_type,
                {
                    "encounter_id": action.encounter_id,
                    "action_id": action.id,
                    "actor_type": action.actor_type,
                    "actor_id": action.actor_id,
                    "target_type": action.target_type,
                    "target_id": action.target_id,
                    "outcome": resolution.outcome,
                    "damage": resolution.damage,
                    "room_id": encounter.location_id,
                    "sequence": encounter.event_sequence,
                    "prose": resolution.explanation,
                    "message_type": MessageType.COMBAT.value,
                    "combat_update": self._combat_update(
                        repo, repo.session, encounter.id
                    ),
                },
            ),
            None,
        )

    def _combat_update(
        self, repo: CombatRepo, session: Session, encounter_id: str
    ) -> JsonObject:
        encounter = repo.encounter(encounter_id)
        participants = []
        meters = MeterRepo(session)
        for participant in repo.active_participants(encounter_id):
            hp = meters.find(participant.actor_type, participant.actor_id, "hp")
            stamina = meters.find(
                participant.actor_type, participant.actor_id, "stamina"
            )
            participants.append(
                {
                    "actor_type": participant.actor_type,
                    "actor_id": participant.actor_id,
                    "status": participant.status,
                    "position": participant.position,
                    "stance": participant.stance,
                    "primary_ready_at": participant.primary_ready_at,
                    "queued_action_id": participant.queued_action_id,
                    "hp": self._meter_state(hp),
                    "stamina": self._meter_state(stamina),
                }
            )
        return {
            "sequence": encounter.event_sequence if encounter is not None else 0,
            "encounter_id": encounter_id,
            "state": encounter.state if encounter is not None else "unknown",
            "participants": participants,
        }

    def _push_combat_update(self, ctx: GameContext, encounter_id: str) -> None:
        ctx.push_update(
            "combat",
            self._combat_update(CombatRepo(ctx.session), ctx.session, encounter_id),
        )

    def _meter_state(self, meter) -> JsonObject | None:
        if meter is None:
            return None
        ratio = meter.current / meter.maximum if meter.maximum else 0.0
        if ratio <= 0:
            label = "depleted"
        elif ratio < 0.35:
            label = "low"
        elif ratio < 0.75:
            label = "steady"
        else:
            label = "strong"
        return {"state": label, "current": meter.current, "maximum": meter.maximum}

    def _resolution_payload(self, resolution: CombatResolution) -> JsonObject:
        payload: JsonObject = {
            "action_key": resolution.action_key,
            "outcome": resolution.outcome,
            "damage": resolution.damage,
            "stamina_delta": resolution.stamina_delta,
            "explanation": resolution.explanation,
        }
        if resolution.damage_trace is not None:
            payload["damage_trace"] = resolution.damage_trace
        if resolution.target is not None:
            payload["target_id"] = resolution.target.actor_id
            payload["target_type"] = resolution.target.actor_type
        return payload

    def _now(self, ctx: GameContext) -> float:
        return ctx.clock.game_epoch if ctx.clock is not None else time.time()


def _session_engine(session: Session) -> Engine:
    bind = session.get_bind()
    if not isinstance(bind, Engine):
        raise TypeError("CombatService requires a Session bound to an Engine")
    return bind


def _float_payload(payload: JsonObject, key: str, default: float = 0.0) -> float:
    value = payload.get(key, default)
    return float(value) if isinstance(value, (int, float, str)) else default


def _float_mapping(payload: JsonObject, key: str, default: float = 0.0) -> float:
    value = payload.get(key, default)
    return float(value) if isinstance(value, (int, float, str)) else default
