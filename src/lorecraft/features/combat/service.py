"""Scheduled Intent combat service."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import cast
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlmodel import Session, col, select

from lorecraft.errors import NotFoundError
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.transaction import TransactionSource
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.items import ItemInstance, ItemStack
from lorecraft.engine.models.meters import ActiveEffect
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.scheduler import ScheduledJob
from lorecraft.engine.models.world import Item, NPC, Room
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.engine.repos.meter_repo import MeterRepo
from lorecraft.engine.repos.scheduler_repo import SchedulerRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import ExchangeLeg, LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.scheduler import SchedulerEventContext
from lorecraft.features.combat.models import (
    CombatAction,
    CombatEncounter,
    CombatParticipant,
    CombatRelationship,
    CombatResolutionRecord,
    CombatWound,
)
from lorecraft.features.combat.boss_phases import (
    BossPhaseContext,
    BossPhaseDecision,
    get_boss_phase_registry,
)
from lorecraft.features.combat.damage import armor_profile_for, weapon_profile_for
from lorecraft.features.combat.definitions import (
    RESOLVER_DEFEND,
    RESOLVER_FLEE,
    RESOLVER_OPPOSED_ATTACK,
    CombatActionCombo,
    CombatActionDef,
    get_action_registry,
)
from lorecraft.features.combat.effects import (
    COMBAT_OFF_BALANCE,
    WEAKENED,
    register_combat_effects,
)
from lorecraft.features.combat.environment import environmental_defense_for
from lorecraft.features.combat.effect_hooks import (
    ActionAdmissionContext,
    DamageReceivedContext,
    MovementContext,
    run_action_admission_hooks,
    run_damage_received_hooks,
    run_movement_hooks,
)
from lorecraft.features.combat.policy import (
    ACTION_BASIC_ATTACK,
    ACTION_DEFEND,
    ACTION_FLEE,
    ACTION_RANGE_ENGAGED,
    ACTION_RANGED_ATTACK,
    ENGAGEMENT_ENGAGED,
    ENGAGEMENT_GUARDING,
    ENGAGEMENT_UNENGAGED,
    OFF_BALANCE_DEFENSE_PENALTY,
    OFF_BALANCE_DURATION,
    REACTION_NEVER,
    STATUS_ACTIVE,
    STATUS_ESCAPED,
    THREAT_DAMAGE_WEIGHT,
    THREAT_DECAY_PER_TICK,
    THREAT_FOCUSED_THRESHOLD,
    THREAT_MAX,
    THREAT_WATCHING_THRESHOLD,
    VALID_REACTION_POLICIES,
    VALID_STANCES,
    defeat_decision_for,
    normalize_reaction_policy,
    normalize_stance,
    stance_policy_for,
)
from lorecraft.features.combat.repo import CombatRepo
from lorecraft.features.combat.resolution import (
    CombatResolution,
    CombatantSnapshot,
    npc_snapshot,
    player_snapshot,
    resolve_basic_attack,
)
from lorecraft.features.combat.rulesets import combat_ruleset_config_for
from lorecraft.features.combat.wounds import derive_wound
from lorecraft.features.reputation.service import ReputationService
from lorecraft.types import JsonObject, JsonValue

COMBAT_RESOLVE_JOB = "combat.resolve_action"

_REACTION_RECOVERY = 1.5
RESPAWN_HP_FRACTION = 0.25


class CombatService:
    """Owns combat policy and persistence for the Tier 2 combat feature."""

    def attack(self, noun: str | None, ctx: GameContext) -> None:
        self._attack_with_action_key(
            noun,
            ctx,
            action_key=ACTION_BASIC_ATTACK,
            commit_message="You commit to an attack on {target}.",
            room_message="{actor} moves to strike {target}.",
        )

    def shoot(self, noun: str | None, ctx: GameContext) -> None:
        self._attack_with_action_key(
            noun,
            ctx,
            action_key=ACTION_RANGED_ATTACK,
            commit_message="You line up a shot at {target}.",
            room_message="{actor} draws a bead on {target}.",
        )

    def consider(self, noun: str | None, ctx: GameContext) -> None:
        target = self._resolve_npc_target(noun, ctx)
        if target is None:
            ctx.say("Consider whom?", MessageType.WARNING)
            return

        repo = CombatRepo(ctx.session)
        encounter = repo.active_encounter_for_actor("player", ctx.player.id)
        now = self._now(ctx)
        actor_participant = (
            repo.participant_for_actor(encounter.id, "player", ctx.player.id)
            if encounter is not None
            else None
        ) or CombatParticipant(
            id="consider-player",
            encounter_id="consider",
            actor_type="player",
            actor_id=ctx.player.id,
            side_id=f"player:{ctx.player.id}",
            joined_at=now,
        )
        target_participant = (
            repo.participant_for_actor(encounter.id, "npc", target.id)
            if encounter is not None
            else None
        ) or CombatParticipant(
            id="consider-target",
            encounter_id="consider",
            actor_type="npc",
            actor_id=target.id,
            side_id=f"npc:{target.id}",
            joined_at=now,
        )

        actor = self._snapshot(ctx.session, actor_participant)
        opponent = self._snapshot(ctx.session, target_participant)
        hp = ctx.meters.get(ctx.session, "npc", target.id, "hp")
        weapon = weapon_profile_for(ctx.session, actor.actor_type, actor.actor_id)
        armor = armor_profile_for(ctx.session, opponent.actor_type, opponent.actor_id)
        attack_score = actor.strength + weapon.accuracy_bonus + actor.attack_bonus
        defense_score = opponent.agility + armor.block + opponent.defense_bonus
        margin = attack_score - defense_score
        if margin >= 15:
            odds = "You should have a clear advantage."
        elif margin >= 5:
            odds = "You seem favored."
        elif margin >= -4:
            odds = "This looks like an even fight."
        elif margin >= -14:
            odds = "This looks risky."
        else:
            odds = "You are badly outmatched."
        health = self._meter_state(hp)
        health_text = (
            str(health["state"]) if health is not None else "unknown condition"
        )
        ctx.say(f"{target.name} looks {health_text}. {odds}", MessageType.HINT)

    def _attack_with_action_key(
        self,
        noun: str | None,
        ctx: GameContext,
        *,
        action_key: str,
        commit_message: str,
        room_message: str,
    ) -> None:
        target = self._resolve_npc_target(noun, ctx)
        if target is None:
            ctx.say("Target whom?", MessageType.WARNING)
            return
        encounter, actor, target_participant = self._ensure_player_vs_npc_encounter(
            ctx, target
        )
        action = self._submit_action(
            repo=CombatRepo(ctx.session),
            session=ctx.session,
            encounter=encounter,
            actor=actor,
            action_key=action_key,
            now=self._now(ctx),
            target=target_participant,
        )
        ctx.player.active_combat_session_id = encounter.id
        ctx.player_repo.add(ctx.player)
        ctx.say(commit_message.format(target=target.name))
        ctx.tell_room(
            room_message.format(actor=ctx.player.username, target=target.name)
        )
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
            action_key=ACTION_DEFEND,
            now=self._now(ctx),
        )
        ctx.say("You shift into a guarded posture.")
        self._push_combat_update(ctx, encounter.id)

    def guard(self, noun: str | None, ctx: GameContext) -> None:
        encounter, actor = self._active_player_participation(ctx)
        if encounter is None or actor is None:
            ctx.say("You aren't in combat.", MessageType.WARNING)
            return
        repo = CombatRepo(ctx.session)
        target = self._resolve_guard_target(
            ctx.session, repo, encounter.id, actor, noun
        )
        if target is None:
            ctx.say("Guard whom?", MessageType.WARNING)
            return
        self._set_guarding_edge(repo, encounter.id, actor.id, target.id)
        self._submit_action(
            repo=repo,
            session=ctx.session,
            encounter=encounter,
            actor=actor,
            action_key=ACTION_DEFEND,
            now=self._now(ctx),
        )
        target_name = self._participant_name(ctx.session, target)
        ctx.say(f"You move to guard {target_name}.")
        self._push_combat_update(ctx, encounter.id)

    def assist(self, noun: str | None, ctx: GameContext) -> None:
        target_player = self._resolve_assist_target(noun, ctx)
        if target_player is None:
            ctx.say("Assist whom?", MessageType.WARNING)
            return
        if target_player.id == ctx.player.id:
            ctx.say("You are already covering yourself.", MessageType.WARNING)
            return
        repo = CombatRepo(ctx.session)
        encounter = repo.active_encounter_for_actor("player", target_player.id)
        if encounter is None:
            ctx.say(f"{target_player.username} is not in combat.", MessageType.WARNING)
            return
        sponsor = repo.participant_for_actor(encounter.id, "player", target_player.id)
        if sponsor is None or sponsor.status != STATUS_ACTIVE:
            ctx.say(
                f"{target_player.username} is not active in combat.",
                MessageType.WARNING,
            )
            return
        now = self._now(ctx)
        actor = repo.participant_for_actor(encounter.id, "player", ctx.player.id)
        if actor is None:
            actor = CombatParticipant(
                id=str(uuid4()),
                encounter_id=encounter.id,
                actor_type="player",
                actor_id=ctx.player.id,
                side_id=sponsor.side_id,
                joined_at=now,
                primary_ready_at=now,
                reaction_ready_at=now,
            )
        actor.status = STATUS_ACTIVE
        actor.side_id = sponsor.side_id
        self._mark_assistance(actor, sponsor, now)
        repo.add(actor)
        self._ensure_assist_edges(repo, encounter.id, actor, sponsor)
        ctx.player.active_combat_session_id = encounter.id
        ctx.player_repo.add(ctx.player)
        ctx.say(f"You join {target_player.username}'s side.")
        ctx.tell_room(f"{ctx.player.username} joins {target_player.username}'s side.")
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
            action_key=ACTION_FLEE,
            now=self._now(ctx),
        )
        ctx.say("You look for an opening to flee.")
        self._push_combat_update(ctx, encounter.id)

    def stance(self, noun: str | None, ctx: GameContext) -> None:
        encounter, actor = self._active_player_participation(ctx)
        if encounter is None or actor is None:
            ctx.say("You aren't in combat.", MessageType.WARNING)
            return
        stance = normalize_stance(noun)
        if stance is None:
            ctx.say(
                "Choose a stance: " + ", ".join(VALID_STANCES) + ".",
                MessageType.WARNING,
            )
            return
        actor.stance = stance
        CombatRepo(ctx.session).add(actor)
        ctx.say(f"You shift to a {stance} stance.")
        self._push_combat_update(ctx, encounter.id)

    def reaction(self, noun: str | None, ctx: GameContext) -> None:
        encounter, actor = self._active_player_participation(ctx)
        if encounter is None or actor is None:
            ctx.say("You aren't in combat.", MessageType.WARNING)
            return
        policy = normalize_reaction_policy(noun)
        if policy is None:
            ctx.say(
                "Choose a reaction policy: " + ", ".join(VALID_REACTION_POLICIES) + ".",
                MessageType.WARNING,
            )
            return
        actor.reaction_policy = policy
        CombatRepo(ctx.session).add(actor)
        ctx.say(f"Your reaction policy is now {policy}.")
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
        audit_repo: AuditRepo | None = None,
        effect_service: EffectService | None = None,
    ) -> CombatAction | None:
        repo = CombatRepo(session)
        action = repo.action(action_id)
        if action is None or action.state in {"resolved", "interrupted"}:
            return action
        if action.state == "cancelled":
            return action
        encounter = repo.encounter(action.encounter_id)
        actor = repo.participant(action.actor_participant_id)
        if encounter is None or actor is None or encounter.state != "active":
            action.state = "cancelled"
            repo.add(action)
            return action
        if actor.status != STATUS_ACTIVE:
            resolution = self._interrupted_resolution(
                session,
                repo,
                action,
                actor,
                reason=f"actor_status:{actor.status}",
            )
            record = self._apply_interruption(
                repo,
                encounter,
                action,
                actor,
                resolution,
                current_epoch=current_epoch,
            )
            self._record_audit_resolution(
                audit_repo,
                encounter,
                action,
                resolution,
                record,
                current_epoch=current_epoch,
            )
            if bus is not None:
                self._emit_resolution_events(
                    bus, repo, encounter, resolution, action, record
                )
            return action

        meter_service = meter_service or MeterService(_session_engine(session), rng)
        effect_service = effect_service or EffectService(_session_engine(session), rng)
        resolution = self._calculate_resolution(session, repo, action, actor, rng=rng)
        record = self._apply_resolution(
            session,
            repo,
            encounter,
            action,
            actor,
            resolution,
            current_epoch=current_epoch,
            meter_service=meter_service,
            effect_service=effect_service,
        )
        self._maybe_end_encounter(session, repo, encounter, current_epoch)
        self._maybe_auto_continue_attacks(
            session,
            repo,
            encounter,
            action,
            current_epoch=current_epoch,
        )
        self._record_audit_resolution(
            audit_repo,
            encounter,
            action,
            resolution,
            record,
            current_epoch=current_epoch,
        )
        if bus is not None:
            self._emit_resolution_events(
                bus, repo, encounter, resolution, action, record
            )
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
        audit_session = (
            Session(ctx.audit_engine) if ctx.audit_engine is not None else None
        )
        try:
            with Session(ctx.game_engine) as session:
                self.resolve_action(
                    session,
                    action_id,
                    rng=ctx.rng,
                    current_epoch=current_epoch,
                    bus=ctx.bus,
                    audit_repo=AuditRepo(audit_session)
                    if audit_session is not None
                    else None,
                    effect_service=EffectService(ctx.game_engine, ctx.rng),
                )
                session.commit()
                if audit_session is not None:
                    audit_session.commit()
        finally:
            if audit_session is not None:
                audit_session.close()

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
            relationship = repo.relationship_between(encounter_id, left, right)
            if relationship is None:
                relationship = CombatRelationship(
                    id=str(uuid4()),
                    encounter_id=encounter_id,
                    source_participant_id=left,
                    target_participant_id=right,
                    engagement=ENGAGEMENT_ENGAGED,
                )
            else:
                relationship.engagement = ENGAGEMENT_ENGAGED
            repo.add(relationship)

    def _set_guarding_edge(
        self,
        repo: CombatRepo,
        encounter_id: str,
        guardian_id: str,
        target_id: str,
    ) -> None:
        for relationship in repo.relationships_for_encounter(encounter_id):
            if (
                relationship.source_participant_id == guardian_id
                and relationship.engagement == ENGAGEMENT_GUARDING
            ):
                relationship.engagement = ENGAGEMENT_UNENGAGED
                repo.add(relationship)
        relationship = repo.relationship_between(encounter_id, guardian_id, target_id)
        if relationship is None:
            relationship = CombatRelationship(
                id=str(uuid4()),
                encounter_id=encounter_id,
                source_participant_id=guardian_id,
                target_participant_id=target_id,
                hostility="supportive",
                engagement=ENGAGEMENT_GUARDING,
            )
        else:
            relationship.hostility = "supportive"
            relationship.engagement = ENGAGEMENT_GUARDING
        repo.add(relationship)

    def _resolve_guard_target(
        self,
        session: Session,
        repo: CombatRepo,
        encounter_id: str,
        actor: CombatParticipant,
        noun: str | None,
    ) -> CombatParticipant | None:
        if noun is None or noun.strip().lower() in {"", "me", "self"}:
            return actor
        needle = noun.strip().lower()
        for participant in repo.participants(encounter_id):
            if (
                participant.status != STATUS_ACTIVE
                or participant.side_id != actor.side_id
            ):
                continue
            if participant.actor_id.lower() == needle:
                return participant
            if self._participant_name(session, participant).lower() == needle:
                return participant
        return None

    def _resolve_assist_target(
        self, noun: str | None, ctx: GameContext
    ) -> Player | None:
        if noun is None or not noun.strip():
            return None
        needle = noun.strip().lower()
        for player in ctx.player_repo.in_room(ctx.room.id):
            if player.id == ctx.player.id:
                continue
            if player.id.lower() == needle or player.username.lower() == needle:
                return player
        return None

    def _ensure_assist_edges(
        self,
        repo: CombatRepo,
        encounter_id: str,
        actor: CombatParticipant,
        sponsor: CombatParticipant,
    ) -> None:
        support = repo.relationship_between(encounter_id, actor.id, sponsor.id)
        if support is None:
            support = CombatRelationship(
                id=str(uuid4()),
                encounter_id=encounter_id,
                source_participant_id=actor.id,
                target_participant_id=sponsor.id,
            )
        support.hostility = "supportive"
        support.engagement = ENGAGEMENT_UNENGAGED
        repo.add(support)

        hostile_targets = [
            relationship.target_participant_id
            for relationship in repo.relationships_for_encounter(encounter_id)
            if relationship.source_participant_id == sponsor.id
            and relationship.hostility == "hostile"
        ]
        for target_id in hostile_targets:
            self._ensure_hostile_edges(repo, encounter_id, actor.id, target_id)

    def _mark_assistance(
        self,
        actor: CombatParticipant,
        sponsor: CombatParticipant,
        current_epoch: float,
    ) -> None:
        contribution = dict(actor.contribution)
        contribution["participation"] = "assistance"
        contribution["counts_as_participation"] = True
        contribution["assisted_participant_id"] = sponsor.id
        contribution["assisted_actor_type"] = sponsor.actor_type
        contribution["assisted_actor_id"] = sponsor.actor_id
        contribution["joined_as_assist_at"] = current_epoch
        contribution["combat_contract"] = {
            "kind": "party_assist",
            "scope": "encounter",
            "counts_as_participation": True,
            "sponsor_participant_id": sponsor.id,
        }
        actor.contribution = contribution

    def _guard_interceptor(
        self, repo: CombatRepo, encounter_id: str, target: CombatParticipant
    ) -> CombatParticipant | None:
        relationship = repo.guarding_relationship_for_target(encounter_id, target.id)
        if relationship is None or relationship.source_participant_id == target.id:
            return None
        guardian = repo.participant(relationship.source_participant_id)
        if guardian is None:
            return None
        if guardian.status != STATUS_ACTIVE or guardian.side_id != target.side_id:
            return None
        return guardian

    def _auto_reaction_for_attack(
        self, action: CombatAction, target: CombatParticipant
    ) -> JsonObject:
        used = (
            action.channel == "primary"
            and action.action_key == ACTION_BASIC_ATTACK
            and target.reaction_policy != REACTION_NEVER
            and target.last_reaction_action_id != action.id
            and target.reaction_ready_at <= action.resolve_at
        )
        return {
            "auto_reaction_policy": target.reaction_policy,
            "auto_reaction_used": used,
            "auto_reaction_kind": "brace" if used else None,
            "auto_reaction_participant_id": target.id if used else None,
            "auto_reaction_actor_id": target.actor_id if used else None,
        }

    def _consume_reaction_if_used(
        self,
        repo: CombatRepo,
        encounter_id: str,
        resolution: CombatResolution,
        action: CombatAction,
        *,
        current_epoch: float,
    ) -> None:
        if not resolution.random_trace or not bool(
            resolution.random_trace.get("auto_reaction_used", False)
        ):
            return
        if resolution.target is None:
            return
        participant = repo.participant_for_actor(
            encounter_id, resolution.target.actor_type, resolution.target.actor_id
        )
        if participant is None:
            return
        participant.reaction_ready_at = max(
            participant.reaction_ready_at,
            current_epoch + _REACTION_RECOVERY,
        )
        participant.last_reaction_action_id = action.id
        repo.add(participant)

    def _resolution_target_participant(
        self,
        repo: CombatRepo,
        encounter_id: str,
        action: CombatAction,
        resolution: CombatResolution,
    ) -> CombatParticipant | None:
        if resolution.target is not None:
            return repo.participant_for_actor(
                encounter_id,
                resolution.target.actor_type,
                resolution.target.actor_id,
            )
        if action.target_participant_id is None:
            return None
        return repo.participant(action.target_participant_id)

    def _participant_name(
        self, session: Session, participant: CombatParticipant
    ) -> str:
        if participant.actor_type == "player":
            player = session.get(Player, participant.actor_id)
            return player.username if player is not None else participant.actor_id
        npc = session.get(NPC, participant.actor_id)
        return npc.name if npc is not None else participant.actor_id

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
        action_def = self._action_def_for(action_key)
        windup = action_def.timing.windup
        recovery = action_def.timing.recovery
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
        admission_hooks = self._run_action_admission_hooks(
            session,
            actor,
            action_key=action_key,
            target_participant_id=target.id if target is not None else None,
            current_epoch=now,
        )
        if admission_hooks:
            action.random_trace = {
                "action_admission_hooks": cast(JsonValue, admission_hooks)
            }
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
        action_def = self._action_def_for(action.action_key)
        ruleset_config = combat_ruleset_config_for(session, action_def.ruleset_id)
        ruleset_trace: JsonObject = {
            "ruleset_damage_multiplier": ruleset_config.damage_multiplier,
            "ruleset_stamina_cost_multiplier": ruleset_config.stamina_cost_multiplier,
        }
        if action_def.resolver == RESOLVER_DEFEND:
            snapshot = self._snapshot(session, actor)
            return self._with_action_admission_trace(
                CombatResolution(
                    action_id=action.id,
                    action_key=action.action_key,
                    actor=snapshot,
                    target=None,
                    outcome="defended",
                    ruleset_id=action_def.ruleset_id,
                    resolver_version=action_def.resolver_version,
                    action_range=action_def.action_range,
                    stamina_delta=self._scaled_stamina_delta(
                        action_def.stamina_delta or 0.0,
                        ruleset_config.stamina_cost_multiplier,
                    ),
                    explanation=f"{snapshot.name} braces defensively.",
                    random_trace={"actor_stance": snapshot.stance, **ruleset_trace},
                ),
                action,
            )
        if action_def.resolver == RESOLVER_FLEE:
            snapshot = self._snapshot(session, actor)
            stance = stance_policy_for(actor.stance)
            return self._with_action_admission_trace(
                CombatResolution(
                    action_id=action.id,
                    action_key=action.action_key,
                    actor=snapshot,
                    target=None,
                    outcome="escaped",
                    ruleset_id=action_def.ruleset_id,
                    resolver_version=action_def.resolver_version,
                    action_range=action_def.action_range,
                    stamina_delta=self._scaled_stamina_delta(
                        stance.flee_stamina_delta,
                        ruleset_config.stamina_cost_multiplier,
                    ),
                    target_status="escaped",
                    explanation=f"{snapshot.name} breaks away from the fight.",
                    random_trace={
                        "actor_stance": snapshot.stance,
                        "stance_flee_stamina_delta": stance.flee_stamina_delta,
                        **ruleset_trace,
                    },
                ),
                action,
            )
        target = (
            repo.participant(action.target_participant_id)
            if action.target_participant_id is not None
            else None
        )
        if target is None or target.status != STATUS_ACTIVE:
            snapshot = self._snapshot(session, actor)
            return self._with_action_admission_trace(
                CombatResolution(
                    action_id=action.id,
                    action_key=action.action_key,
                    actor=snapshot,
                    target=None,
                    outcome="cancelled",
                    ruleset_id=action_def.ruleset_id,
                    resolver_version=action_def.resolver_version,
                    action_range=action_def.action_range,
                    explanation="The target is no longer available.",
                    random_trace=ruleset_trace,
                ),
                action,
            )
        original_target = target
        if action_def.resolver != RESOLVER_OPPOSED_ATTACK:
            snapshot = self._snapshot(session, actor)
            return self._with_action_admission_trace(
                CombatResolution(
                    action_id=action.id,
                    action_key=action.action_key,
                    actor=snapshot,
                    target=None,
                    outcome="cancelled",
                    ruleset_id=action_def.ruleset_id,
                    resolver_version=action_def.resolver_version,
                    action_range=action_def.action_range,
                    explanation=f"Unsupported combat resolver: {action_def.resolver}.",
                    random_trace={
                        "unsupported_resolver": action_def.resolver,
                        **ruleset_trace,
                    },
                ),
                action,
            )
        action_range = action_def.action_range
        intercept_eligible = action_range == ACTION_RANGE_ENGAGED
        interceptor = (
            self._guard_interceptor(repo, action.encounter_id, target)
            if intercept_eligible
            else None
        )
        if interceptor is not None:
            target = interceptor
        explicit_defend = self._has_recent_defend(repo, target.id, action.submitted_at)
        auto_reaction = self._auto_reaction_for_attack(action, target)
        auto_reaction_used = bool(auto_reaction["auto_reaction_used"])
        defended = explicit_defend or interceptor is not None or auto_reaction_used
        original_target_snapshot = self._snapshot(session, original_target)
        target_snapshot = self._snapshot(session, target)
        encounter = repo.encounter(action.encounter_id)
        environment = environmental_defense_for(
            session.get(Room, encounter.location_id) if encounter is not None else None
        )
        if environment.bonus:
            target_snapshot = replace(
                target_snapshot,
                defense_bonus=target_snapshot.defense_bonus + environment.bonus,
            )
        actor_snapshot = self._snapshot(session, actor)
        actor_snapshot, combo_trace, consumed_combo = self._apply_combo_attack_bonus(
            actor_snapshot,
            actor,
            action_def.combo,
        )
        actor_snapshot = replace(
            actor_snapshot,
            damage_multiplier=(
                actor_snapshot.damage_multiplier * ruleset_config.damage_multiplier
            ),
        )
        resolution = resolve_basic_attack(
            action_id=action.id,
            action_key=action.action_key,
            action_range=action_range,
            actor=actor_snapshot,
            target=target_snapshot,
            weapon=weapon_profile_for(session, actor.actor_type, actor.actor_id),
            armor=armor_profile_for(session, target.actor_type, target.actor_id),
            rng=rng,
            defended=defended,
            stamina_delta=self._scaled_stamina_delta(
                action_def.stamina_delta or 0.0,
                ruleset_config.stamina_cost_multiplier,
            ),
        )
        resolution = replace(
            resolution,
            ruleset_id=action_def.ruleset_id,
            resolver_version=action_def.resolver_version,
            random_trace={
                **(resolution.random_trace or {}),
                "ruleset_id": action_def.ruleset_id,
                "resolver_version": action_def.resolver_version,
                **combo_trace,
                **environment.trace,
                **ruleset_trace,
            },
        )
        granted_combo = self._apply_combo_result(
            actor,
            action_def.combo,
            outcome=resolution.outcome,
            consumed_combo=consumed_combo,
        )
        if granted_combo is not None:
            resolution = replace(
                resolution,
                random_trace={
                    **(resolution.random_trace or {}),
                    "combo_granted": granted_combo,
                    "combo_ready_after": granted_combo,
                },
            )
        elif consumed_combo is not None:
            resolution = replace(
                resolution,
                random_trace={
                    **(resolution.random_trace or {}),
                    "combo_ready_after": None,
                },
            )
        if consumed_combo is not None or granted_combo is not None:
            repo.add(actor)
        if auto_reaction:
            resolution = replace(
                resolution,
                random_trace={
                    **(resolution.random_trace or {}),
                    **auto_reaction,
                    "intercept_eligible": intercept_eligible,
                },
            )
        resolution = self._with_action_admission_trace(resolution, action)
        if interceptor is None:
            return resolution
        random_trace = {
            **(resolution.random_trace or {}),
            "intercepted": True,
            "original_target_participant_id": original_target.id,
            "original_target_id": original_target.actor_id,
            "interceptor_participant_id": interceptor.id,
            "interceptor_id": interceptor.actor_id,
        }
        damage_trace = {
            **(resolution.damage_trace or {}),
            "intercepted": True,
            "original_target_id": original_target.actor_id,
            "interceptor_id": interceptor.actor_id,
        }
        return replace(
            resolution,
            explanation=(
                f"{target_snapshot.name} intercepts for "
                f"{original_target_snapshot.name}. {resolution.explanation}"
            ),
            random_trace=random_trace,
            damage_trace=damage_trace,
        )

    def _apply_combo_attack_bonus(
        self,
        actor_snapshot: CombatantSnapshot,
        actor: CombatParticipant,
        combo: CombatActionCombo | None,
    ) -> tuple[CombatantSnapshot, JsonObject, str | None]:
        current_combo = actor.contribution.get("combo_ready")
        combo_ready = current_combo if isinstance(current_combo, str) else None
        trace: JsonObject = {
            "combo_ready_before": combo_ready,
            "combo_consumed": None,
            "combo_granted": None,
            "combo_accuracy_bonus": 0.0,
            "combo_damage_multiplier": 1.0,
        }
        if combo is None or combo.consumes is None or combo_ready != combo.consumes:
            return actor_snapshot, trace, None
        trace["combo_consumed"] = combo.consumes
        trace["combo_accuracy_bonus"] = combo.accuracy_bonus
        trace["combo_damage_multiplier"] = combo.damage_multiplier
        return (
            replace(
                actor_snapshot,
                attack_bonus=actor_snapshot.attack_bonus + combo.accuracy_bonus,
                damage_multiplier=actor_snapshot.damage_multiplier
                * combo.damage_multiplier,
            ),
            trace,
            combo.consumes,
        )

    def _apply_combo_result(
        self,
        actor: CombatParticipant,
        combo: CombatActionCombo | None,
        *,
        outcome: str,
        consumed_combo: str | None,
    ) -> str | None:
        if combo is None:
            return None
        contribution = dict(actor.contribution)
        if consumed_combo is not None:
            contribution.pop("combo_ready", None)
        granted_combo: str | None = None
        if combo.grants is not None and outcome in combo.grant_outcomes:
            contribution["combo_ready"] = combo.grants
            granted_combo = combo.grants
        if consumed_combo is not None or granted_combo is not None:
            actor.contribution = contribution
        return granted_combo

    def _record_resolution(
        self,
        repo: CombatRepo,
        encounter: CombatEncounter,
        action: CombatAction,
        resolution: CombatResolution,
        *,
        resolved_at: float,
        payload: JsonObject,
    ) -> CombatResolutionRecord:
        existing = repo.resolution_record_for_action(action.id)
        if existing is not None:
            return existing
        target_type = (
            resolution.target.actor_type if resolution.target is not None else None
        )
        target_id = (
            resolution.target.actor_id if resolution.target is not None else None
        )
        record = CombatResolutionRecord(
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
            ruleset_id=resolution.ruleset_id,
            resolver_version=resolution.resolver_version,
            random_trace=resolution.random_trace or {},
            damage_trace=resolution.damage_trace or {},
            payload=payload,
        )
        repo.add(record)
        return record

    def _interrupted_resolution(
        self,
        session: Session,
        repo: CombatRepo,
        action: CombatAction,
        actor: CombatParticipant,
        *,
        reason: str,
    ) -> CombatResolution:
        target = (
            repo.participant(action.target_participant_id)
            if action.target_participant_id is not None
            else None
        )
        action_def = self._action_def_for(action.action_key)
        return CombatResolution(
            action_id=action.id,
            action_key=action.action_key,
            actor=self._snapshot(session, actor),
            target=self._snapshot(session, target) if target is not None else None,
            outcome="interrupted",
            ruleset_id=action_def.ruleset_id,
            resolver_version=action_def.resolver_version,
            action_range=action_def.action_range,
            explanation="The action is interrupted before it resolves.",
            random_trace={
                "interrupt_reason": reason,
                "ruleset_id": action_def.ruleset_id,
                "resolver_version": action_def.resolver_version,
            },
        )

    def _apply_interruption(
        self,
        repo: CombatRepo,
        encounter: CombatEncounter,
        action: CombatAction,
        actor: CombatParticipant,
        resolution: CombatResolution,
        *,
        current_epoch: float,
    ) -> CombatResolutionRecord:
        action.state = "interrupted"
        encounter.event_sequence += 1
        action.random_trace = resolution.random_trace or {}
        if actor.queued_action_id == action.id:
            actor.queued_action_id = None
        action.outcome = self._resolution_payload(
            resolution,
            record_id=None,
            state_changes=[],
            position_changes=[],
            effect_changes=[],
            threat_changes=[],
            consequence_changes=[],
            wound_changes=[],
        )
        record = self._record_resolution(
            repo,
            encounter,
            action,
            resolution,
            resolved_at=current_epoch,
            payload=action.outcome,
        )
        action.outcome = self._resolution_payload(
            resolution,
            record_id=record.id,
            state_changes=[],
            position_changes=[],
            effect_changes=[],
            threat_changes=[],
            consequence_changes=[],
            wound_changes=[],
        )
        record.payload = action.outcome
        repo.add(record)
        repo.add(actor)
        repo.add(action)
        repo.add(encounter)
        return record

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
        effect_service: EffectService,
    ) -> CombatResolutionRecord:
        action.state = "resolved"
        encounter.event_sequence += 1
        action.random_trace = resolution.random_trace or {}
        state_changes: list[JsonValue] = []
        position_changes: list[JsonValue] = []
        threat_changes: list[JsonValue] = []
        consequence_changes: list[JsonValue] = []
        wound_changes: list[JsonValue] = []
        if actor.queued_action_id == action.id:
            actor.queued_action_id = None
        if resolution.stamina_delta:
            stamina = meter_service.get(
                session, actor.actor_type, actor.actor_id, "stamina"
            )
            meter_service.adjust(session, stamina, resolution.stamina_delta)
        if resolution.action_key == ACTION_FLEE and resolution.outcome == "escaped":
            state_changes.append(
                self._transition_participant(
                    repo,
                    actor,
                    STATUS_ESCAPED,
                    reason=ACTION_FLEE,
                    current_epoch=current_epoch,
                )
            )
            if actor.actor_type == "player":
                player = session.get(Player, actor.actor_id)
                if player is not None:
                    player.active_combat_session_id = None
                    session.add(player)
        self._consume_reaction_if_used(
            repo,
            encounter.id,
            resolution,
            action,
            current_epoch=current_epoch,
        )
        target = self._resolution_target_participant(
            repo, encounter.id, action, resolution
        )
        effect_changes: list[JsonValue] = []
        if target is not None and resolution.damage > 0:
            hp = meter_service.get(session, target.actor_type, target.actor_id, "hp")
            change = meter_service.adjust(session, hp, -resolution.damage)
            wound_changes.append(
                self._record_wound(
                    repo,
                    encounter,
                    action,
                    target,
                    resolution,
                    hp_before=change.previous,
                    hp_after=change.meter.current,
                    current_epoch=current_epoch,
                )
            )
            effect_changes.extend(
                self._run_damage_received_hooks(
                    session,
                    target,
                    action,
                    resolution,
                    current_epoch=current_epoch,
                )
            )
            self._add_contribution(actor, resolution.damage)
            threat_changes.append(
                self._add_threat(
                    session,
                    target,
                    actor,
                    amount=resolution.damage,
                    current_epoch=current_epoch,
                )
            )
            consequence_changes.extend(
                self._apply_combat_consequences(
                    session,
                    source=actor,
                    target=target,
                    trigger="on_damage_received",
                    current_epoch=current_epoch,
                )
            )
            if change.depleted:
                decision = defeat_decision_for(target.actor_type)
                state_changes.append(
                    self._transition_participant(
                        repo,
                        target,
                        decision.status,
                        reason="hp_depleted",
                        current_epoch=current_epoch,
                    )
                )
                if decision.clears_player_combat:
                    player = session.get(Player, target.actor_id)
                    if player is not None:
                        player.active_combat_session_id = None
                        session.add(player)
                if target.actor_type == "player":
                    consequence_changes.append(
                        self._apply_player_death_respawn(
                            session,
                            meter_service,
                            effect_service,
                            target,
                            current_epoch=current_epoch,
                        )
                    )
                consequence_changes.extend(
                    self._apply_combat_rewards(
                        session,
                        source=actor,
                        target=target,
                        trigger="on_defeat",
                        current_epoch=current_epoch,
                    )
                )
            elif resolution.outcome == "strong_hit":
                effect_changes.append(
                    self._apply_off_balance_effect(
                        session,
                        effect_service,
                        target,
                        action,
                        current_epoch=current_epoch,
                    )
                )
        refreshed_positions, movement_effects = self._refresh_positions(
            repo,
            session,
            encounter.id,
            current_epoch=current_epoch,
        )
        position_changes.extend(refreshed_positions)
        effect_changes.extend(movement_effects)
        encounter.last_hostile_action_at = current_epoch
        payload = self._resolution_payload(
            resolution,
            record_id=None,
            state_changes=state_changes,
            position_changes=position_changes,
            effect_changes=effect_changes,
            threat_changes=threat_changes,
            consequence_changes=consequence_changes,
            wound_changes=wound_changes,
        )
        action.outcome = payload
        record = self._record_resolution(
            repo,
            encounter,
            action,
            resolution,
            resolved_at=current_epoch,
            payload=payload,
        )
        action.outcome = self._resolution_payload(
            resolution,
            record_id=record.id,
            state_changes=state_changes,
            position_changes=position_changes,
            effect_changes=effect_changes,
            threat_changes=threat_changes,
            consequence_changes=consequence_changes,
            wound_changes=wound_changes,
        )
        record.payload = action.outcome
        repo.add(record)
        repo.add(actor)
        repo.add(action)
        repo.add(encounter)
        return record

    def _record_wound(
        self,
        repo: CombatRepo,
        encounter: CombatEncounter,
        action: CombatAction,
        target: CombatParticipant,
        resolution: CombatResolution,
        *,
        hp_before: float,
        hp_after: float,
        current_epoch: float,
    ) -> JsonObject:
        descriptor = derive_wound(
            action_id=action.id,
            target_id=target.actor_id,
            damage=resolution.damage,
        )
        payload: JsonObject = {
            "outcome": resolution.outcome,
            "action_key": resolution.action_key,
            "hp_before": hp_before,
            "hp_after": hp_after,
        }
        wound = CombatWound(
            id=str(uuid4()),
            encounter_id=encounter.id,
            action_id=action.id,
            target_type=target.actor_type,
            target_id=target.actor_id,
            body_location=descriptor.body_location,
            severity=descriptor.severity,
            damage=resolution.damage,
            created_at_game_time=current_epoch,
            payload=payload,
        )
        repo.add(wound)
        return {
            "wound_id": wound.id,
            "target_type": target.actor_type,
            "target_id": target.actor_id,
            "body_location": wound.body_location,
            "severity": wound.severity,
            "damage": wound.damage,
            "status": wound.status,
            "hp_before": hp_before,
            "hp_after": hp_after,
        }

    def _maybe_auto_continue_attacks(
        self,
        session: Session,
        repo: CombatRepo,
        encounter: CombatEncounter,
        action: CombatAction,
        *,
        current_epoch: float,
    ) -> None:
        if encounter.state != "active" or not self._is_attack_action(action.action_key):
            return
        for participant in repo.active_participants(encounter.id):
            if repo.pending_primary_action(participant.id) is not None:
                continue
            target = repo.hostile_target_for(encounter.id, participant.id)
            if target is None:
                continue
            action_key = ACTION_BASIC_ATTACK
            trace: JsonObject | None = None
            if participant.actor_type == "npc":
                target = self._preferred_target_for_npc(
                    repo, participant, fallback=target
                )
                phase_decision = self._boss_phase_decision(
                    session,
                    repo,
                    encounter,
                    participant,
                    action,
                    fallback_target=target,
                    current_epoch=current_epoch,
                )
                if phase_decision is not None:
                    phase_target = (
                        repo.participant(phase_decision.target_participant_id)
                        if phase_decision.target_participant_id is not None
                        else None
                    )
                    if (
                        phase_target is not None
                        and phase_target.status == STATUS_ACTIVE
                        and phase_target.side_id != participant.side_id
                    ):
                        target = phase_target
                    action_key = phase_decision.action_key
                    trace = {"boss_phase": phase_decision.trace()}
            next_action = self._submit_action(
                repo=repo,
                session=session,
                encounter=encounter,
                actor=participant,
                action_key=action_key,
                now=current_epoch,
                target=target,
            )
            if trace is not None:
                next_action.random_trace = {**next_action.random_trace, **trace}
                repo.add(next_action)

    def _boss_phase_decision(
        self,
        session: Session,
        repo: CombatRepo,
        encounter: CombatEncounter,
        participant: CombatParticipant,
        triggering_action: CombatAction,
        *,
        fallback_target: CombatParticipant,
        current_epoch: float,
    ) -> BossPhaseDecision | None:
        npc = session.get(NPC, participant.actor_id)
        if npc is None:
            return None
        resolver_key = npc.ai.get("combat_phase_resolver")
        if not isinstance(resolver_key, str) or not resolver_key.strip():
            return None
        resolver = get_boss_phase_registry().get(resolver_key.strip())
        if resolver is None:
            return None
        return resolver(
            BossPhaseContext(
                session=session,
                repo=repo,
                encounter=encounter,
                npc=npc,
                participant=participant,
                triggering_action=triggering_action,
                fallback_target=fallback_target,
                current_epoch=current_epoch,
            )
        )

    def _preferred_target_for_npc(
        self,
        repo: CombatRepo,
        npc_participant: CombatParticipant,
        *,
        fallback: CombatParticipant,
    ) -> CombatParticipant:
        attention = npc_participant.threat.get("attention")
        if not isinstance(attention, dict):
            return fallback
        best: tuple[float, CombatParticipant] | None = None
        for participant_id, raw_entry in attention.items():
            if not isinstance(participant_id, str) or not isinstance(raw_entry, dict):
                continue
            candidate = repo.participant(participant_id)
            if (
                candidate is None
                or candidate.status != STATUS_ACTIVE
                or candidate.side_id == npc_participant.side_id
            ):
                continue
            score = _float_mapping(raw_entry, "score")
            if best is None or score > best[0]:
                best = (score, candidate)
        return best[1] if best is not None and best[0] > 0 else fallback

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

    def _transition_participant(
        self,
        repo: CombatRepo,
        participant: CombatParticipant,
        status: str,
        *,
        reason: str,
        current_epoch: float,
    ) -> JsonObject:
        previous_status = participant.status
        participant.status = status
        participant.queued_action_id = None
        cancelled_actions = []
        for pending in repo.pending_primary_actions(participant.id):
            pending.state = "cancelled"
            repo.add(pending)
            cancelled_actions.append(pending.id)
        for relationship in repo.relationships_for_encounter(participant.encounter_id):
            if participant.id in {
                relationship.source_participant_id,
                relationship.target_participant_id,
            }:
                relationship.engagement = ENGAGEMENT_UNENGAGED
                repo.add(relationship)
        participant.position = ENGAGEMENT_UNENGAGED
        repo.add(participant)
        return {
            "participant_id": participant.id,
            "actor_type": participant.actor_type,
            "actor_id": participant.actor_id,
            "from_status": previous_status,
            "to_status": status,
            "reason": reason,
            "at": current_epoch,
            "cancelled_action_ids": cancelled_actions,
        }

    def _refresh_positions(
        self,
        repo: CombatRepo,
        session: Session,
        encounter_id: str,
        *,
        current_epoch: float,
    ) -> tuple[list[JsonValue], list[JsonValue]]:
        participants = list(repo.participants(encounter_id))
        active_ids = {
            participant.id
            for participant in participants
            if participant.status == STATUS_ACTIVE
        }
        engaged_ids: set[str] = set()
        for relationship in repo.relationships_for_encounter(encounter_id):
            if relationship.engagement != ENGAGEMENT_ENGAGED:
                continue
            if (
                relationship.source_participant_id not in active_ids
                or relationship.target_participant_id not in active_ids
            ):
                relationship.engagement = ENGAGEMENT_UNENGAGED
                repo.add(relationship)
                continue
            engaged_ids.add(relationship.source_participant_id)
            engaged_ids.add(relationship.target_participant_id)

        changes: list[JsonValue] = []
        effect_changes: list[JsonValue] = []
        for participant in participants:
            previous_position = participant.position
            next_position = (
                ENGAGEMENT_ENGAGED
                if participant.id in engaged_ids
                else ENGAGEMENT_UNENGAGED
            )
            if previous_position == next_position:
                continue
            effect_changes.extend(
                self._run_movement_hooks(
                    session,
                    participant,
                    previous_position,
                    next_position,
                    current_epoch=current_epoch,
                )
            )
            participant.position = next_position
            repo.add(participant)
            changes.append(
                {
                    "participant_id": participant.id,
                    "actor_type": participant.actor_type,
                    "actor_id": participant.actor_id,
                    "from_position": previous_position,
                    "to_position": next_position,
                }
            )
        return changes, effect_changes

    def _active_combat_effects(
        self, session: Session, participant: CombatParticipant
    ) -> list[ActiveEffect]:
        statement = (
            select(ActiveEffect)
            .where(ActiveEffect.entity_type == participant.actor_type)
            .where(ActiveEffect.entity_id == participant.actor_id)
            .where(col(ActiveEffect.effect_key).like("combat.%"))
            .order_by(col(ActiveEffect.applied_at_epoch))
        )
        return list(session.exec(statement).all())

    def _effect_defense_bonus(self, effect: ActiveEffect) -> int:
        if effect.effect_key != COMBAT_OFF_BALANCE:
            return 0
        potency = effect.payload.get("potency", OFF_BALANCE_DEFENSE_PENALTY)
        return int(potency) if isinstance(potency, int | float | str) else 0

    def _apply_off_balance_effect(
        self,
        session: Session,
        effect_service: EffectService,
        target: CombatParticipant,
        action: CombatAction,
        *,
        current_epoch: float,
    ) -> JsonObject:
        register_combat_effects()
        existing = next(
            (
                effect
                for effect in self._active_combat_effects(session, target)
                if effect.effect_key == COMBAT_OFF_BALANCE
            ),
            None,
        )
        if existing is not None:
            return {
                "effect_id": existing.id,
                "effect_key": existing.effect_key,
                "actor_type": target.actor_type,
                "actor_id": target.actor_id,
                "applied_at": existing.applied_at_epoch,
                "expires_at": existing.expires_at_epoch,
                "source_action_id": action.id,
                "already_active": True,
            }
        effect = effect_service.apply(
            session,
            target.actor_type,
            target.actor_id,
            COMBAT_OFF_BALANCE,
            duration_ticks=OFF_BALANCE_DURATION,
            payload={
                "source_actor_type": action.actor_type,
                "source_actor_id": action.actor_id,
                "source_action_id": action.id,
                "tags": ["combat", "control"],
                "potency": OFF_BALANCE_DEFENSE_PENALTY,
                "state": "active",
            },
            clock_epoch=current_epoch,
        )
        return {
            "effect_id": effect.id,
            "effect_key": effect.effect_key,
            "actor_type": target.actor_type,
            "actor_id": target.actor_id,
            "applied_at": effect.applied_at_epoch,
            "expires_at": effect.expires_at_epoch,
            "source_action_id": action.id,
        }

    def _snapshot(
        self, session: Session, participant: CombatParticipant
    ) -> CombatantSnapshot:
        stance = stance_policy_for(participant.stance)
        active_effects = self._active_combat_effects(session, participant)
        effect_defense_bonus = sum(
            self._effect_defense_bonus(effect) for effect in active_effects
        )
        active_effect_keys = tuple(effect.effect_key for effect in active_effects)
        if participant.actor_type == "player":
            player = session.get(Player, participant.actor_id)
            stats = session.get(PlayerStats, participant.actor_id)
            return player_snapshot(
                participant.actor_id,
                player.username if player is not None else participant.actor_id,
                stats,
                stance=participant.stance,
                attack_bonus=stance.attack_bonus,
                defense_bonus=stance.defense_bonus + effect_defense_bonus,
                damage_multiplier=stance.damage_multiplier,
                active_effects=active_effect_keys,
            )
        npc = session.get(NPC, participant.actor_id)
        if npc is None:
            return CombatantSnapshot(
                actor_type="npc",
                actor_id=participant.actor_id,
                name=participant.actor_id,
                strength=10,
                agility=8,
                stance=participant.stance,
                attack_bonus=stance.attack_bonus,
                defense_bonus=stance.defense_bonus + effect_defense_bonus,
                damage_multiplier=stance.damage_multiplier,
                active_effects=active_effect_keys,
            )
        return npc_snapshot(
            npc,
            stance=participant.stance,
            attack_bonus=stance.attack_bonus,
            defense_bonus=stance.defense_bonus + effect_defense_bonus,
            damage_multiplier=stance.damage_multiplier,
            active_effects=active_effect_keys,
        )

    def _has_recent_defend(
        self, repo: CombatRepo, participant_id: str, since: float
    ) -> bool:
        action = repo.pending_primary_action(participant_id)
        return bool(
            action is not None
            and action.action_key == ACTION_DEFEND
            and action.submitted_at >= since - 3.0
        )

    def _action_def_for(self, action_key: str) -> CombatActionDef:
        action_def = get_action_registry().get(action_key)
        if action_def is None:
            raise ValueError(f"unknown combat action: {action_key!r}")
        return action_def

    def _scaled_stamina_delta(self, delta: float, cost_multiplier: float) -> float:
        if delta >= 0:
            return delta
        return round(delta * cost_multiplier, 3)

    def _is_attack_action(self, action_key: str) -> bool:
        action_def = get_action_registry().get(action_key)
        return bool(
            action_def is not None and action_def.resolver == RESOLVER_OPPOSED_ATTACK
        )

    def _with_action_admission_trace(
        self, resolution: CombatResolution, action: CombatAction
    ) -> CombatResolution:
        admission_hooks = action.random_trace.get("action_admission_hooks")
        if not isinstance(admission_hooks, list) or not admission_hooks:
            return resolution
        return replace(
            resolution,
            random_trace={
                **(resolution.random_trace or {}),
                "action_admission_hooks": admission_hooks,
            },
        )

    def _run_action_admission_hooks(
        self,
        session: Session,
        participant: CombatParticipant,
        *,
        action_key: str,
        target_participant_id: str | None,
        current_epoch: float,
    ) -> list[JsonObject]:
        return run_action_admission_hooks(
            self._active_combat_effects(session, participant),
            ActionAdmissionContext(
                session=session,
                participant=participant,
                action_key=action_key,
                target_participant_id=target_participant_id,
                current_epoch=current_epoch,
            ),
        )

    def _run_damage_received_hooks(
        self,
        session: Session,
        participant: CombatParticipant,
        action: CombatAction,
        resolution: CombatResolution,
        *,
        current_epoch: float,
    ) -> list[JsonObject]:
        return run_damage_received_hooks(
            self._active_combat_effects(session, participant),
            DamageReceivedContext(
                session=session,
                participant=participant,
                action=action,
                resolution=resolution,
                damage=resolution.damage,
                current_epoch=current_epoch,
            ),
        )

    def _run_movement_hooks(
        self,
        session: Session,
        participant: CombatParticipant,
        from_position: str,
        to_position: str,
        *,
        current_epoch: float,
    ) -> list[JsonObject]:
        return run_movement_hooks(
            self._active_combat_effects(session, participant),
            MovementContext(
                session=session,
                participant=participant,
                from_position=from_position,
                to_position=to_position,
                current_epoch=current_epoch,
            ),
        )

    def _add_contribution(self, actor: CombatParticipant, damage: float) -> None:
        contribution = dict(actor.contribution)
        contribution["damage"] = _float_mapping(contribution, "damage") + damage
        actor.contribution = contribution

    def _add_threat(
        self,
        session: Session,
        target: CombatParticipant,
        source: CombatParticipant,
        *,
        amount: float,
        current_epoch: float,
    ) -> JsonObject:
        threat = dict(target.threat)
        attention_map = self._attention_map(threat.get("attention"))
        decayed_attention = self._decayed_attention(attention_map, current_epoch)
        previous = decayed_attention.get(source.id, {})
        previous_score = _float_mapping(previous, "score")
        score = min(THREAT_MAX, previous_score + amount * THREAT_DAMAGE_WEIGHT)
        entry: JsonObject = {
            "participant_id": source.id,
            "actor_type": source.actor_type,
            "actor_id": source.actor_id,
            "score": round(score, 2),
            "cue": self._threat_cue(score),
            "last_updated_at": current_epoch,
        }
        decayed_attention[source.id] = entry
        threat["attention"] = cast(JsonValue, decayed_attention)
        threat["combat_role"] = self._combat_role(session, target)
        target.threat = threat
        return {
            "participant_id": target.id,
            "actor_type": target.actor_type,
            "actor_id": target.actor_id,
            "combat_role": threat["combat_role"],
            "source_participant_id": source.id,
            "source_actor_type": source.actor_type,
            "source_actor_id": source.actor_id,
            "score": entry["score"],
            "cue": entry["cue"],
            "at": current_epoch,
        }

    def _apply_combat_consequences(
        self,
        session: Session,
        *,
        source: CombatParticipant,
        target: CombatParticipant,
        trigger: str,
        current_epoch: float,
    ) -> list[JsonObject]:
        if source.actor_type != "player" or target.actor_type != "npc":
            return []
        npc = session.get(NPC, target.actor_id)
        if npc is None:
            return []
        raw_config = npc.ai.get("combat_consequences")
        if not isinstance(raw_config, dict):
            return []
        raw_obligations = raw_config.get(trigger, [])
        if not isinstance(raw_obligations, list):
            return []

        changes: list[JsonObject] = []
        reputation = ReputationService()
        for raw_obligation in raw_obligations:
            if not isinstance(raw_obligation, dict):
                continue
            if raw_obligation.get("type") != "adjust_reputation":
                continue
            target_type = raw_obligation.get("target_type")
            target_id = raw_obligation.get("target_id")
            delta = raw_obligation.get("delta")
            if (
                not isinstance(target_type, str)
                or not isinstance(target_id, str)
                or not isinstance(delta, int)
            ):
                continue
            standing = reputation.adjust(
                session,
                source.actor_id,
                target_type,
                target_id,
                delta,
            )
            changes.append(
                {
                    "type": "adjust_reputation",
                    "trigger": trigger,
                    "player_id": source.actor_id,
                    "target_actor_type": target.actor_type,
                    "target_actor_id": target.actor_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "delta": delta,
                    "standing": standing,
                    "reason": raw_obligation.get("reason"),
                    "at": current_epoch,
                }
            )
        return changes

    def _apply_combat_rewards(
        self,
        session: Session,
        *,
        source: CombatParticipant,
        target: CombatParticipant,
        trigger: str,
        current_epoch: float,
    ) -> list[JsonObject]:
        if source.actor_type != "player" or target.actor_type != "npc":
            return []
        npc = session.get(NPC, target.actor_id)
        if npc is None:
            return []
        raw_config = npc.ai.get("combat_rewards")
        if not isinstance(raw_config, dict):
            return []
        raw_rewards = raw_config.get(trigger, [])
        if not isinstance(raw_rewards, list):
            return []

        changes: list[JsonObject] = []
        ledger = LedgerService()
        for raw_reward in raw_rewards:
            if not isinstance(raw_reward, dict):
                continue
            if raw_reward.get("type") != "coins":
                continue
            amount = raw_reward.get("amount")
            if not isinstance(amount, int) or amount <= 0:
                continue
            ledger.credit(session, "player", source.actor_id, amount)
            changes.append(
                {
                    "type": "coins",
                    "trigger": trigger,
                    "player_id": source.actor_id,
                    "target_actor_type": target.actor_type,
                    "target_actor_id": target.actor_id,
                    "amount": amount,
                    "message": raw_reward.get("message"),
                    "at": current_epoch,
                }
            )
        return changes

    def _apply_player_death_respawn(
        self,
        session: Session,
        meter_service: MeterService,
        effect_service: EffectService,
        participant: CombatParticipant,
        *,
        current_epoch: float,
    ) -> JsonObject:
        player = session.get(Player, participant.actor_id)
        if player is None:
            return {
                "type": "player_respawn_missing_player",
                "player_id": participant.actor_id,
                "at": current_epoch,
            }
        death_room_id = player.current_room_id
        respawn_room_id = player.respawn_room_id

        ledger = LedgerService()
        item_location = ItemLocationService(session)
        stack_repo = StackRepo(session)
        corpse_stack_id: int | None = None
        corpse_instance_id: str | None = None
        coin_loss = int(ledger.balance_of(session, "player", player.id) * 0.20)
        dropped_stacks: list[JsonObject] = []
        corpse_error: str | None = None
        try:
            corpse_stack = item_location.spawn(
                "corpse", Location("room", death_room_id)
            )[0]
            corpse_stack_id = corpse_stack.id
            corpse_instance_id = corpse_stack.instance_id
            if corpse_instance_id is None:
                corpse_error = "corpse_item_not_instanced"
            else:
                corpse_instance = session.get(ItemInstance, corpse_instance_id)
                if corpse_instance is not None:
                    openable = corpse_instance.state.get("openable")
                    if isinstance(openable, dict):
                        state = dict(corpse_instance.state)
                        state["openable"] = {**openable, "open": True}
                        corpse_instance.state = state
                        session.add(corpse_instance)
                        session.flush()
                drop_candidates = self._death_drop_stacks(
                    session, stack_repo, player.id
                )
                legs: list[ExchangeLeg] = []
                stacks = tuple(
                    (stack.id, stack.quantity)
                    for stack in drop_candidates
                    if stack.id is not None
                )
                if coin_loss > 0 or stacks:
                    legs.append(
                        ExchangeLeg(
                            give_from=Location("player", player.id),
                            give_to=Location("container", corpse_instance_id),
                            coins=coin_loss,
                            stacks=stacks,
                        )
                    )
                if legs:
                    ledger.execute_exchange(session, legs)
                dropped_stacks = [
                    {
                        "stack_id": stack.id,
                        "item_id": stack.item_id,
                        "quantity": stack.quantity,
                    }
                    for stack in drop_candidates
                ]
        except NotFoundError as exc:
            corpse_error = exc.code

        player.current_room_id = respawn_room_id
        player.active_combat_session_id = None
        player.ghost_state = False
        session.add(player)

        hp = meter_service.get(session, "player", player.id, "hp")
        restored_hp = max(1.0, hp.maximum * RESPAWN_HP_FRACTION)
        meter_service.set_current(session, hp, restored_hp)
        weakened = effect_service.apply(
            session,
            "player",
            player.id,
            WEAKENED,
            duration_ticks=180.0,
            payload={"reason": "death"},
            clock_epoch=current_epoch,
        )
        return {
            "type": "player_respawned",
            "player_id": player.id,
            "death_room_id": death_room_id,
            "respawn_room_id": respawn_room_id,
            "respawn_hp": hp.current,
            "respawn_hp_fraction": RESPAWN_HP_FRACTION,
            "corpse_stack_id": corpse_stack_id,
            "corpse_instance_id": corpse_instance_id,
            "corpse_error": corpse_error,
            "coin_loss": coin_loss if corpse_instance_id is not None else 0,
            "dropped_stacks": cast(JsonValue, dropped_stacks),
            "weakened_effect_id": weakened.id,
            "at": current_epoch,
        }

    def _death_drop_stacks(
        self, session: Session, stack_repo: StackRepo, player_id: str
    ) -> list[ItemStack]:
        stacks: list[ItemStack] = []
        for stack in stack_repo.stacks_for_owner("player", player_id):
            if stack.slot is not None:
                continue
            item = session.get(Item, stack.item_id)
            if item is not None and item.bound:
                continue
            stacks.append(stack)
        return stacks

    def _decayed_attention(
        self, attention: dict[str, JsonObject], current_epoch: float
    ) -> dict[str, JsonObject]:
        decayed: dict[str, JsonObject] = {}
        for participant_id, entry in attention.items():
            score = _float_mapping(entry, "score")
            last_updated = _float_mapping(entry, "last_updated_at", current_epoch)
            elapsed = max(0.0, current_epoch - last_updated)
            next_score = max(0.0, score - elapsed * THREAT_DECAY_PER_TICK)
            if next_score <= 0:
                continue
            decayed[participant_id] = {
                **entry,
                "score": round(next_score, 2),
                "cue": self._threat_cue(next_score),
                "last_updated_at": current_epoch,
            }
        return decayed

    def _attention_map(self, raw_attention: object) -> dict[str, JsonObject]:
        if not isinstance(raw_attention, dict):
            return {}
        attention: dict[str, JsonObject] = {}
        for participant_id, entry in raw_attention.items():
            if isinstance(participant_id, str) and isinstance(entry, dict):
                attention[participant_id] = cast(JsonObject, dict(entry))
        return attention

    def _threat_cue(self, score: float) -> str:
        if score >= THREAT_FOCUSED_THRESHOLD:
            return "focused"
        if score >= THREAT_WATCHING_THRESHOLD:
            return "watching"
        return "aware"

    def _combat_role(self, session: Session, participant: CombatParticipant) -> str:
        if participant.actor_type != "npc":
            return "player"
        npc = session.get(NPC, participant.actor_id)
        if npc is None:
            return "defensive"
        configured = npc.ai.get("combat_role")
        if isinstance(configured, str) and configured.strip():
            return configured.strip().lower()
        return npc.behavior.strip().lower() if npc.behavior.strip() else "defensive"

    def _threat_summary(
        self,
        session: Session,
        participant: CombatParticipant,
        *,
        current_epoch: float,
    ) -> JsonObject:
        attention_map = self._attention_map(participant.threat.get("attention"))
        decayed = self._decayed_attention(attention_map, current_epoch)
        return {
            "combat_role": self._combat_role(session, participant),
            "attention": list(decayed.values()),
        }

    def _record_audit_resolution(
        self,
        audit_repo: AuditRepo | None,
        encounter: CombatEncounter,
        action: CombatAction,
        resolution: CombatResolution,
        record: CombatResolutionRecord,
        *,
        current_epoch: float,
    ) -> None:
        if audit_repo is None:
            return
        event_type = (
            GameEvent.PLAYER_ATTACKED
            if action.actor_type == "player"
            else GameEvent.NPC_ATTACKED
        )
        target_id = (
            resolution.target.actor_id
            if resolution.target is not None
            else action.target_id
        )
        target_type = (
            resolution.target.actor_type
            if resolution.target is not None
            else action.target_type
        )
        audit_repo.record(
            AuditEvent(
                transaction_id=f"combat-action:{action.id}:resolve",
                correlation_id=encounter.id,
                parent_transaction_ids=[],
                actor_id=action.actor_id,
                event_type=event_type.value,
                source_type=TransactionSource.SCHEDULER.value,
                target_id=target_id,
                room_id=encounter.location_id,
                game_time=current_epoch,
                real_time=time.time(),
                severity="INFO",
                summary=(
                    f"Combat action resolved: {action.action_key} {resolution.outcome}"
                ),
                payload_json={
                    "encounter_id": encounter.id,
                    "action_id": action.id,
                    "resolution_record_id": record.id,
                    "actor_type": action.actor_type,
                    "actor_id": action.actor_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "action_key": action.action_key,
                    "outcome": resolution.outcome,
                    "damage": resolution.damage,
                    "ruleset_id": record.ruleset_id,
                    "resolver_version": record.resolver_version,
                    "resolution": action.outcome,
                },
            )
        )

    def _emit_resolution_events(
        self,
        bus: EventBus,
        repo: CombatRepo,
        encounter: CombatEncounter,
        resolution: CombatResolution,
        action: CombatAction,
        record: CombatResolutionRecord,
    ) -> None:
        event_type = (
            GameEvent.PLAYER_ATTACKED
            if action.actor_type == "player"
            else GameEvent.NPC_ATTACKED
        )
        target_id = (
            resolution.target.actor_id
            if resolution.target is not None
            else action.target_id
        )
        target_type = (
            resolution.target.actor_type
            if resolution.target is not None
            else action.target_type
        )
        prose = self._resolution_prose(repo.session, resolution, action.outcome)
        bus.emit(
            Event(
                event_type,
                {
                    "encounter_id": action.encounter_id,
                    "action_id": action.id,
                    "actor_type": action.actor_type,
                    "actor_id": action.actor_id,
                    "target_type": target_type,
                    "target_id": target_id,
                    "outcome": resolution.outcome,
                    "damage": resolution.damage,
                    "resolution_record_id": record.id,
                    "payload": action.outcome,
                    "room_id": encounter.location_id,
                    "sequence": encounter.event_sequence,
                    "prose": prose,
                    "message_type": MessageType.COMBAT.value,
                    "combat_update": self._combat_update(
                        repo, repo.session, encounter.id
                    ),
                },
            ),
            None,
        )
        self._emit_death_events(bus, encounter, action.outcome)

    def _emit_death_events(
        self, bus: EventBus, encounter: CombatEncounter, payload: JsonObject
    ) -> None:
        consequence_changes = payload.get("consequence_changes")
        if not isinstance(consequence_changes, list):
            return
        for raw_change in consequence_changes:
            if not isinstance(raw_change, dict):
                continue
            if raw_change.get("type") != "player_respawned":
                continue
            player_id = raw_change.get("player_id")
            if not isinstance(player_id, str):
                continue
            common = {
                "player_id": player_id,
                "encounter_id": encounter.id,
                "death_room_id": raw_change.get("death_room_id"),
                "respawn_room_id": raw_change.get("respawn_room_id"),
                "corpse_stack_id": raw_change.get("corpse_stack_id"),
                "corpse_instance_id": raw_change.get("corpse_instance_id"),
                "coin_loss": raw_change.get("coin_loss"),
                "dropped_stacks": raw_change.get("dropped_stacks"),
            }
            bus.emit(Event(GameEvent.PLAYER_DIED, common), None)
            bus.emit(
                Event(
                    GameEvent.PLAYER_RESPAWNED,
                    {
                        **common,
                        "respawn_hp": raw_change.get("respawn_hp"),
                        "weakened_effect_id": raw_change.get("weakened_effect_id"),
                    },
                ),
                None,
            )

    def _resolution_prose(
        self, session: Session, resolution: CombatResolution, payload: JsonObject
    ) -> str:
        lines = [resolution.explanation] if resolution.explanation else []
        state_changes = payload.get("state_changes")
        if isinstance(state_changes, list):
            for raw_change in state_changes:
                if not isinstance(raw_change, dict):
                    continue
                to_status = raw_change.get("to_status")
                actor_type = raw_change.get("actor_type")
                actor_id = raw_change.get("actor_id")
                if not isinstance(to_status, str) or not isinstance(actor_id, str):
                    continue
                name = self._actor_name(session, str(actor_type), actor_id)
                if to_status == "defeated":
                    lines.append(f"{name} is defeated.")
                elif to_status == "dead":
                    lines.append(f"{name} dies.")
                elif to_status == "downed":
                    lines.append(f"{name} is downed.")
                elif to_status == "escaped":
                    lines.append(f"{name} escapes.")
        consequence_changes = payload.get("consequence_changes")
        if isinstance(consequence_changes, list):
            for raw_change in consequence_changes:
                if not isinstance(raw_change, dict):
                    continue
                if raw_change.get("type") != "coins":
                    if raw_change.get("type") == "player_respawned":
                        respawn_room_id = raw_change.get("respawn_room_id")
                        if isinstance(respawn_room_id, str):
                            lines.append(
                                f"You wake at {respawn_room_id}, battered but alive."
                            )
                    continue
                message = raw_change.get("message")
                amount = raw_change.get("amount")
                if isinstance(message, str) and message.strip():
                    lines.append(message.strip())
                elif isinstance(amount, int):
                    lines.append(f"You receive {amount} coins.")
        return " ".join(lines)

    def _actor_name(self, session: Session, actor_type: str, actor_id: str) -> str:
        if actor_type == "player":
            player = session.get(Player, actor_id)
            return player.username if player is not None else actor_id
        if actor_type == "npc":
            npc = session.get(NPC, actor_id)
            return npc.name if npc is not None else actor_id
        return actor_id

    def _combat_update(
        self, repo: CombatRepo, session: Session, encounter_id: str
    ) -> JsonObject:
        encounter = repo.encounter(encounter_id)
        participants = []
        meters = MeterRepo(session)
        for participant in repo.participants(encounter_id):
            hp = meters.find(participant.actor_type, participant.actor_id, "hp")
            stamina = meters.find(
                participant.actor_type, participant.actor_id, "stamina"
            )
            participants.append(
                {
                    "actor_type": participant.actor_type,
                    "actor_id": participant.actor_id,
                    "name": self._participant_name(session, participant),
                    "status": participant.status,
                    "position": participant.position,
                    "stance": participant.stance,
                    "combat_role": self._combat_role(session, participant),
                    "threat": self._threat_summary(
                        session,
                        participant,
                        current_epoch=encounter.last_hostile_action_at
                        if encounter is not None
                        else 0.0,
                    ),
                    "reaction_policy": participant.reaction_policy,
                    "reaction_ready_at": participant.reaction_ready_at,
                    "primary_ready_at": participant.primary_ready_at,
                    "queued_action_id": participant.queued_action_id,
                    "active_effects": [
                        {
                            "id": effect.id,
                            "effect_key": effect.effect_key,
                            "expires_at": effect.expires_at_epoch,
                            "payload": effect.payload,
                        }
                        for effect in self._active_combat_effects(session, participant)
                    ],
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

    def _resolution_payload(
        self,
        resolution: CombatResolution,
        *,
        record_id: str | None,
        state_changes: list[JsonValue],
        position_changes: list[JsonValue],
        effect_changes: list[JsonValue],
        threat_changes: list[JsonValue],
        consequence_changes: list[JsonValue],
        wound_changes: list[JsonValue],
    ) -> JsonObject:
        payload: JsonObject = {
            "action_key": resolution.action_key,
            "ruleset_id": resolution.ruleset_id,
            "resolver_version": resolution.resolver_version,
            "action_range": resolution.action_range,
            "outcome": resolution.outcome,
            "damage": resolution.damage,
            "stamina_delta": resolution.stamina_delta,
            "explanation": resolution.explanation,
            "actor_stance": resolution.actor.stance,
            "state_changes": state_changes,
            "position_changes": position_changes,
            "effect_changes": effect_changes,
            "threat_changes": threat_changes,
            "consequence_changes": consequence_changes,
            "wound_changes": wound_changes,
        }
        if record_id is not None:
            payload["resolution_record_id"] = record_id
        if resolution.damage_trace is not None:
            payload["damage_trace"] = resolution.damage_trace
        if resolution.random_trace is not None:
            payload["random_trace"] = resolution.random_trace
        if resolution.target is not None:
            payload["target_id"] = resolution.target.actor_id
            payload["target_type"] = resolution.target.actor_type
            payload["target_stance"] = resolution.target.stance
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
