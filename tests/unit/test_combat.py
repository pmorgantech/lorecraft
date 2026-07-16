"""Scheduled Intent combat foundation tests."""

from __future__ import annotations

from collections.abc import Iterator

import asyncio
import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine, select

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.meters import MeterDef
from lorecraft.engine.game.meters import get_registry as get_meter_registry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine, RuleResult
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.items import ItemStack
from lorecraft.engine.models.audit import AuditEvent
from lorecraft.engine.models.meters import ActiveEffect
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.scheduler import ScheduledJob
from lorecraft.engine.models.world import Item, NPC, Room, WorldClock
from lorecraft.engine.repos.audit_repo import AuditRepo
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.scheduler import SchedulerService
from lorecraft.features.combat.models import (
    CombatAction,
    CombatEncounter,
    CombatParticipant,
    CombatRelationship,
    CombatResolutionRecord,
    CombatRulesetConfig,
    CombatWound,
)
from lorecraft.features.combat.broadcast import broadcast_combat_resolution
from lorecraft.features.combat.boss_phases import (
    BossPhaseDecision,
    get_boss_phase_registry,
)
from lorecraft.features.combat.damage import (
    ArmorProfile,
    apply_damage_stack,
    armor_profile_for,
    weapon_profile_for,
)
from lorecraft.features.combat.definitions import (
    CALCULATOR_OPPOSED_ATTACK,
    RESOLVER_OPPOSED_ATTACK,
    CombatActionCombo,
    CombatActionDef,
    CombatActionTiming,
    CombatActionsDocument,
    get_action_registry,
    register_builtin_combat_actions,
)
from lorecraft.features.combat.effect_hooks import (
    CombatEffectHooks,
    get_combat_effect_hook_registry,
)
from lorecraft.features.combat.effects import register_combat_effects
from lorecraft.features.combat.repo import CombatRepo
from lorecraft.features.combat.service import COMBAT_RESOLVE_JOB, CombatService
from lorecraft.features.fatigue.source import FATIGUE_METER_KEY
from lorecraft.features.item_components.components import (
    register as register_components,
)
from lorecraft.features.reputation.models import Reputation


@pytest.fixture(autouse=True)
def combat_meters() -> Iterator[None]:
    register_components()
    register_combat_effects()
    registry = get_meter_registry()
    hook_registry = get_combat_effect_hook_registry()
    boss_phase_registry = get_boss_phase_registry()
    hook_registry.clear()
    boss_phase_registry.clear()
    registry.register(
        MeterDef(
            key="hp",
            base_maximum=lambda entity_type, entity_id, session: _hp_base(
                entity_type, entity_id, session
            ),
        )
    )
    registry.register(
        MeterDef(
            key=FATIGUE_METER_KEY,
            base_maximum=lambda entity_type, entity_id, session: 100.0,
        )
    )
    yield
    registry._defs.pop("hp", None)  # type: ignore[attr-defined]
    registry._defs.pop(FATIGUE_METER_KEY, None)  # type: ignore[attr-defined]
    hook_registry.clear()
    boss_phase_registry.clear()


def test_attack_submits_intent_and_schedules_resolution() -> None:
    engine = _engine()
    bus = EventBus()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session, bus=bus)
        service.attack("goblin", ctx)
        session.commit()

        encounter = session.exec(select(CombatEncounter)).one()
        actions = session.exec(select(CombatAction)).all()
        participants = session.exec(select(CombatParticipant)).all()
        jobs = session.exec(select(ScheduledJob)).all()

        assert ctx.player.active_combat_session_id == encounter.id
        assert encounter.state == "active"
        assert {p.actor_type for p in participants} == {"player", "npc"}
        assert len(actions) == 1
        assert actions[0].action_key == "basic_attack"
        assert actions[0].state == "pending"
        assert jobs[0].job_type == COMBAT_RESOLVE_JOB
        assert jobs[0].payload == {"action_id": actions[0].id}
        assert "combat" in ctx.updates


def test_combat_admission_rule_blocks_action_submission() -> None:
    engine = _engine()
    rules = RuleEngine()
    observed_payloads: list[dict] = []

    def block_admission(ctx: object, payload: dict) -> RuleResult:
        observed_payloads.append(payload)
        return RuleResult.block("The arena wards flare.")

    rules.register_rule("combat.action.admit", block_admission)
    service = CombatService(rules)

    with Session(engine) as session:
        ctx = _context(session, rules=rules)
        service.attack("goblin", ctx)
        session.commit()

        assert session.exec(select(CombatAction)).all() == []
        assert session.exec(select(ScheduledJob)).all() == []
        assert "The arena wards flare." in ctx.messages
        assert observed_payloads[0]["action_key"] == "basic_attack"
        assert observed_payloads[0]["target_id"] == "goblin"


def test_combat_resolution_rule_cancels_scheduled_action() -> None:
    engine = _engine()
    rules = RuleEngine()

    def block_resolution(ctx: object, payload: dict) -> RuleResult:
        assert payload["action_key"] == "basic_attack"
        return RuleResult.block("The target steps behind sanctuary law.")

    rules.register_rule("combat.action.resolve", block_resolution)
    service = CombatService(rules)

    with Session(engine) as session:
        ctx = _context(session, rules=rules)
        service.attack("goblin", ctx)
        action = session.exec(select(CombatAction)).one()
        action_id = action.id

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        action = session.get(CombatAction, action_id)
        record = session.exec(select(CombatResolutionRecord)).one()
        assert action is not None
        assert action.state == "resolved"
        assert action.outcome["outcome"] == "cancelled"
        assert record.outcome == "cancelled"
        assert record.random_trace["rule_blocked"] == "combat.action.resolve"
        assert record.random_trace["rule_reason"] == (
            "The target steps behind sanctuary law."
        )


def test_shoot_submits_ranged_intent_and_records_range_trace() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.shoot("goblin", ctx)
        action = session.exec(select(CombatAction)).one()
        action_id = action.id

        assert action.action_key == "ranged_attack"

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        action = session.get(CombatAction, action_id)
        record = session.exec(select(CombatResolutionRecord)).one()

        assert action is not None
        assert action.outcome["action_key"] == "ranged_attack"
        assert action.outcome["action_range"] == "ranged"
        assert action.random_trace["action_range"] == "ranged"
        assert action.random_trace["intercept_eligible"] is False
        assert record.action_key == "ranged_attack"
        assert record.random_trace["action_range"] == "ranged"


def test_consider_appraises_nearby_npc() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.consider("goblin", ctx)

        assert ctx.messages
        assert "Goblin looks strong." in str(ctx.messages[0])
        assert "clear advantage" in str(ctx.messages[0])


def test_combat_service_uses_data_authored_action_timing() -> None:
    registry = get_action_registry()
    registry.clear()
    registry.load_document(
        CombatActionsDocument(
            actions=[
                CombatActionDef(
                    id="ranged_attack",
                    action_range="ranged",
                    calculator=CALCULATOR_OPPOSED_ATTACK,
                    resolver=RESOLVER_OPPOSED_ATTACK,
                    timing=CombatActionTiming(windup=1.5, recovery=4.0),
                    stamina_delta=-3.0,
                )
            ]
        )
    )
    try:
        engine = _engine()
        service = CombatService()

        with Session(engine) as session:
            ctx = _context(session)
            service.shoot("goblin", ctx)
            action = session.exec(select(CombatAction)).one()

            assert action.resolve_at == 1.5
            assert action.recovery_until == 5.5
    finally:
        register_builtin_combat_actions(registry)


def test_combat_resolution_persists_action_ruleset_and_resolver_version() -> None:
    registry = get_action_registry()
    registry.clear()
    registry.load_document(
        CombatActionsDocument(
            actions=[
                CombatActionDef(
                    id="basic_attack",
                    ruleset_id="test-ruleset",
                    action_range="engaged",
                    calculator=CALCULATOR_OPPOSED_ATTACK,
                    resolver=RESOLVER_OPPOSED_ATTACK,
                    resolver_version="opposed-test-v7",
                    timing=CombatActionTiming(windup=0.25, recovery=2.0),
                    stamina_delta=-6.0,
                )
            ]
        )
    )
    try:
        engine = _engine()
        service = CombatService()

        with Session(engine) as session:
            ctx = _context(session)
            service.attack("goblin", ctx)
            action = session.exec(select(CombatAction)).one()
            action_id = action.id

            service.resolve_action(
                session,
                action_id,
                rng=GameRng(seed=1),
                current_epoch=10.0,
                meter_service=ctx.meters,
            )
            session.commit()

        with Session(engine) as session:
            action = session.get(CombatAction, action_id)
            record = session.exec(select(CombatResolutionRecord)).one()

            assert action is not None
            assert record.ruleset_id == "test-ruleset"
            assert record.resolver_version == "opposed-test-v7"
            assert record.random_trace["ruleset_id"] == "test-ruleset"
            assert record.random_trace["resolver_version"] == "opposed-test-v7"
            assert record.payload["ruleset_id"] == "test-ruleset"
            assert record.payload["resolver_version"] == "opposed-test-v7"
            assert action.outcome["ruleset_id"] == "test-ruleset"
            assert action.outcome["resolver_version"] == "opposed-test-v7"
    finally:
        register_builtin_combat_actions(registry)


def test_combat_resolution_uses_live_ruleset_config() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        session.add(
            CombatRulesetConfig(
                id="core",
                damage_multiplier=2.0,
                stamina_cost_multiplier=2.0,
            )
        )
        ctx = _context(session)
        service.attack("goblin", ctx)
        action = session.exec(select(CombatAction)).one()
        action_id = action.id

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        record = session.exec(select(CombatResolutionRecord)).one()
        stamina = ctx_meters(engine).get(
            session, "player", "player-1", FATIGUE_METER_KEY
        )

        assert record.payload["stamina_delta"] == -12.0
        assert record.random_trace["ruleset_damage_multiplier"] == 2.0
        assert record.random_trace["ruleset_stamina_cost_multiplier"] == 2.0
        assert record.damage_trace["actor_stance_damage_multiplier"] == 2.0
        assert stamina.current == 88.0


def test_combat_action_combo_grants_followup_state() -> None:
    registry = get_action_registry()
    registry.clear()
    registry.load_document(
        CombatActionsDocument(
            actions=[
                CombatActionDef(
                    id="basic_attack",
                    action_range="engaged",
                    calculator=CALCULATOR_OPPOSED_ATTACK,
                    resolver=RESOLVER_OPPOSED_ATTACK,
                    timing=CombatActionTiming(windup=0.25, recovery=2.0),
                    stamina_delta=-6.0,
                    combo=CombatActionCombo(
                        grants="opening",
                        grant_outcomes=["miss", "glancing", "hit", "strong_hit"],
                    ),
                )
            ]
        )
    )
    try:
        engine = _engine()
        service = CombatService()

        with Session(engine) as session:
            ctx = _context(session)
            service.attack("goblin", ctx)
            action = session.exec(select(CombatAction)).one()
            action_id = action.id

            service.resolve_action(
                session,
                action_id,
                rng=GameRng(seed=1),
                current_epoch=10.0,
                meter_service=ctx.meters,
            )
            session.commit()

        with Session(engine) as session:
            player = session.exec(
                select(CombatParticipant).where(
                    CombatParticipant.actor_type == "player"
                )
            ).one()
            record = session.exec(select(CombatResolutionRecord)).one()

            assert player.contribution["combo_ready"] == "opening"
            assert record.random_trace["combo_ready_before"] is None
            assert record.random_trace["combo_consumed"] is None
            assert record.random_trace["combo_granted"] == "opening"
            assert record.random_trace["combo_ready_after"] == "opening"
    finally:
        register_builtin_combat_actions(registry)


def test_combat_action_combo_consumes_followup_for_attack_bonus() -> None:
    registry = get_action_registry()
    registry.clear()
    registry.load_document(
        CombatActionsDocument(
            actions=[
                CombatActionDef(
                    id="basic_attack",
                    action_range="engaged",
                    calculator=CALCULATOR_OPPOSED_ATTACK,
                    resolver=RESOLVER_OPPOSED_ATTACK,
                    timing=CombatActionTiming(windup=0.25, recovery=2.0),
                    stamina_delta=-6.0,
                    combo=CombatActionCombo(
                        consumes="opening",
                        accuracy_bonus=5.0,
                        damage_multiplier=1.5,
                    ),
                )
            ]
        )
    )
    try:
        engine = _engine()
        service = CombatService()

        with Session(engine) as session:
            ctx = _context(session)
            service.attack("goblin", ctx)
            action = session.exec(select(CombatAction)).one()
            action_id = action.id
            player = session.exec(
                select(CombatParticipant).where(
                    CombatParticipant.actor_type == "player"
                )
            ).one()
            player.contribution = {"combo_ready": "opening"}
            session.add(player)

            service.resolve_action(
                session,
                action_id,
                rng=GameRng(seed=1),
                current_epoch=10.0,
                meter_service=ctx.meters,
            )
            session.commit()

        with Session(engine) as session:
            player = session.exec(
                select(CombatParticipant).where(
                    CombatParticipant.actor_type == "player"
                )
            ).one()
            record = session.exec(select(CombatResolutionRecord)).one()

            assert "combo_ready" not in player.contribution
            assert record.random_trace["combo_ready_before"] == "opening"
            assert record.random_trace["combo_consumed"] == "opening"
            assert record.random_trace["combo_granted"] is None
            assert record.random_trace["combo_accuracy_bonus"] == 5.0
            assert record.random_trace["combo_damage_multiplier"] == 1.5
            assert record.random_trace["combo_ready_after"] is None
            assert record.random_trace["actor_stance_attack_bonus"] == 5.0
            assert record.damage_trace["actor_stance_damage_multiplier"] == 1.5
    finally:
        register_builtin_combat_actions(registry)


def test_combat_resolution_applies_room_terrain_and_cover_defense() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        ctx.room.terrain = "forest"
        ctx.room.flags = {"combat_cover": "partial"}
        session.add(ctx.room)
        service.attack("goblin", ctx)
        action = session.exec(select(CombatAction)).one()
        action_id = action.id

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        record = session.exec(select(CombatResolutionRecord)).one()

        assert record.random_trace["terrain"] == "forest"
        assert record.random_trace["terrain_defense_bonus"] == 2
        assert record.random_trace["cover"] == "partial"
        assert record.random_trace["cover_defense_bonus"] == 2
        assert record.random_trace["environment_defense_bonus"] == 4
        assert record.random_trace["target_stance_defense_bonus"] == 4


def test_scheduled_resolution_applies_damage_and_npc_counter_intent() -> None:
    engine, audit_engine = _engine_pair()
    rng = GameRng(seed=7)
    bus = EventBus()
    scheduler = SchedulerService(engine, rng, audit_engine)
    service = CombatService()
    scheduler.register(bus)
    service.register(bus)
    observed: list[dict] = []
    bus.on(GameEvent.PLAYER_ATTACKED, lambda event, ctx: observed.append(event.payload))

    with Session(engine) as session:
        ctx = _context(session, bus=bus, rng=rng)
        service.attack("goblin", ctx)
        session.commit()

    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 10.0}), ctx=None)

    with Session(engine) as session:
        actions = session.exec(
            select(CombatAction).order_by(CombatAction.submitted_at)
        ).all()
        record = session.exec(select(CombatResolutionRecord)).one()
        wound = session.exec(select(CombatWound)).one()
        record_id = record.id
        goblin_hp = ctx_meters(engine).get(session, "npc", "goblin", "hp")

        assert actions[0].state == "resolved"
        assert actions[0].outcome["action_key"] == "basic_attack"
        assert "damage_trace" in actions[0].outcome
        assert actions[0].random_trace
        assert record.action_id == actions[0].id
        assert actions[0].outcome["resolution_record_id"] == record_id
        assert record.random_trace == actions[0].random_trace
        assert record.damage_trace["final_damage"] == actions[0].outcome["damage"]
        assert record.payload["random_trace"] == record.random_trace
        assert wound.action_id == actions[0].id
        assert wound.target_type == "npc"
        assert wound.target_id == "goblin"
        assert wound.status == "active"
        assert wound.body_location in {
            "head",
            "torso",
            "left_arm",
            "right_arm",
            "left_leg",
            "right_leg",
        }
        assert wound.severity in {"bruise", "minor", "major", "critical"}
        assert record.payload["wound_changes"][0]["wound_id"] == wound.id
        assert actions[0].outcome["wound_changes"][0]["body_location"] == (
            wound.body_location
        )
        assert goblin_hp.current < goblin_hp.maximum
        assert any(
            action.actor_type == "npc" and action.state == "pending"
            for action in actions
        )
        assert any(
            action.actor_type == "player" and action.state == "pending"
            for action in actions[1:]
        )
        assert observed
        assert observed[0]["sequence"] == 1
        assert observed[0]["room_id"] == "arena"
        assert observed[0]["message_type"] == "combat"
        assert observed[0]["prose"]
        assert observed[0]["combat_update"]["sequence"] == 1
        assert observed[0]["combat_update"]["participants"]
        assert observed[0]["resolution_record_id"] == record_id

    with Session(audit_engine) as audit_session:
        audit_event = audit_session.exec(select(AuditEvent)).one()
        assert audit_event.event_type == GameEvent.PLAYER_ATTACKED.value
        assert audit_event.source_type == "SCHEDULER"
        assert audit_event.payload_json["resolution_record_id"] == record_id
        assert audit_event.payload_json["resolution"]["damage_trace"]
        assert audit_event.payload_json["resolution"]["wound_changes"][0]["wound_id"]


def test_simultaneous_planning_mode_queues_npc_response_with_shared_resolution() -> (
    None
):
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        goblin = session.get(NPC, "goblin")
        assert goblin is not None
        goblin.ai = {"combat_mode": "simultaneous_planning"}
        goblin.max_hp = 500
        session.add(goblin)

        service.attack("goblin", ctx)
        session.commit()

    with Session(engine) as session:
        encounter = session.exec(select(CombatEncounter)).one()
        actions = session.exec(
            select(CombatAction).order_by(CombatAction.actor_type)
        ).all()
        npc_action = next(action for action in actions if action.actor_type == "npc")
        player_action = next(
            action for action in actions if action.actor_type == "player"
        )

        assert encounter.combat_mode == "simultaneous_planning"
        assert npc_action.state == "pending"
        assert npc_action.resolve_at == player_action.resolve_at
        assert npc_action.random_trace["simultaneous_planning"] == {
            "trigger_action_id": player_action.id,
            "shared_resolve_at": player_action.resolve_at,
        }

        service.resolve_action(
            session,
            player_action.id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx_meters(engine),
        )
        session.commit()

    with Session(engine) as session:
        actions = session.exec(select(CombatAction)).all()

        assert len(actions) == 2


def test_damage_updates_threat_attention_and_combat_state_cues() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        stats = session.get(PlayerStats, "player-1")
        assert stats is not None
        stats.strength = 120
        session.add(stats)
        goblin_model = session.get(NPC, "goblin")
        assert goblin_model is not None
        goblin_model.max_hp = 500
        session.add(goblin_model)
        service.attack("goblin", ctx)
        action = session.exec(
            select(CombatAction).where(CombatAction.actor_type == "player")
        ).one()
        action_id = action.id

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        combat_update = service._combat_update(
            CombatRepo(session), session, ctx.player.active_combat_session_id or ""
        )
        session.commit()

    with Session(engine) as session:
        goblin = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "npc")
        ).one()
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == action_id
            )
        ).one()
        attention = goblin.threat["attention"]
        goblin_state = next(
            participant
            for participant in combat_update["participants"]
            if participant["actor_type"] == "npc"
        )

        assert list(attention.values())[0]["actor_id"] == "player-1"
        assert list(attention.values())[0]["cue"] == "focused"
        assert record.payload["threat_changes"][0]["actor_id"] == "goblin"
        assert record.payload["threat_changes"][0]["source_actor_id"] == "player-1"
        assert record.payload["threat_changes"][0]["cue"] == "focused"
        assert goblin_state["name"] == "Goblin"
        assert goblin_state["combat_role"] == "defensive"
        assert goblin_state["threat"]["attention"][0]["actor_id"] == "player-1"


def test_combat_damage_applies_configured_reputation_consequence() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        goblin_model = session.get(NPC, "goblin")
        assert goblin_model is not None
        goblin_model.ai = {
            "combat_consequences": {
                "on_damage_received": [
                    {
                        "type": "adjust_reputation",
                        "target_type": "faction",
                        "target_id": "city_watch",
                        "delta": -5,
                        "reason": "assault",
                    }
                ]
            }
        }
        session.add(goblin_model)
        service.attack("goblin", ctx)
        action = session.exec(
            select(CombatAction).where(CombatAction.actor_type == "player")
        ).one()
        action_id = action.id

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        reputation = session.exec(select(Reputation)).one()
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == action_id
            )
        ).one()
        consequence = record.payload["consequence_changes"][0]

        assert reputation.player_id == "player-1"
        assert reputation.target_type == "faction"
        assert reputation.target_id == "city_watch"
        assert reputation.standing == -5
        assert consequence["type"] == "adjust_reputation"
        assert consequence["trigger"] == "on_damage_received"
        assert consequence["player_id"] == "player-1"
        assert consequence["target_actor_id"] == "goblin"
        assert consequence["target_type"] == "faction"
        assert consequence["target_id"] == "city_watch"
        assert consequence["delta"] == -5
        assert consequence["standing"] == -5
        assert consequence["reason"] == "assault"


def test_npc_counter_intent_prefers_highest_threat_target() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        encounter = session.exec(select(CombatEncounter)).one()
        player = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        goblin = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "npc")
        ).one()
        ally = _add_ally_participant(session, encounter, player.side_id)
        goblin.threat = {
            "attention": {
                ally.id: {
                    "participant_id": ally.id,
                    "actor_type": "player",
                    "actor_id": "ally",
                    "score": 80.0,
                    "cue": "focused",
                    "last_updated_at": 0.0,
                }
            }
        }
        session.add(goblin)
        action = session.exec(
            select(CombatAction).where(CombatAction.actor_type == "player")
        ).one()

        service.resolve_action(
            session,
            action.id,
            rng=GameRng(seed=1),
            current_epoch=1.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        npc_action = session.exec(
            select(CombatAction)
            .where(CombatAction.actor_type == "npc")
            .where(CombatAction.state == "pending")
        ).one()

        assert npc_action.target_id == "ally"


def test_registered_boss_phase_resolver_overrides_npc_counter_intent() -> None:
    engine = _engine()
    service = CombatService()

    def phase_resolver(context) -> BossPhaseDecision:
        return BossPhaseDecision(
            action_key="ranged_attack",
            target_participant_id=context.fallback_target.id,
            phase="bloodied",
            payload={"source_action_id": context.triggering_action.id},
        )

    get_boss_phase_registry().register("test.bloodied", phase_resolver)

    with Session(engine) as session:
        ctx = _context(session)
        goblin_model = session.get(NPC, "goblin")
        assert goblin_model is not None
        goblin_model.ai = {"combat_phase_resolver": "test.bloodied"}
        session.add(goblin_model)
        service.attack("goblin", ctx)
        action = session.exec(
            select(CombatAction).where(CombatAction.actor_type == "player")
        ).one()
        action_id = action.id

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=1.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        npc_action = session.exec(
            select(CombatAction)
            .where(CombatAction.actor_type == "npc")
            .where(CombatAction.state == "pending")
        ).one()

        assert npc_action.action_key == "ranged_attack"
        assert npc_action.target_id == "player-1"
        assert npc_action.random_trace["boss_phase"]["phase"] == "bloodied"
        assert npc_action.random_trace["boss_phase"]["payload"] == {
            "source_action_id": action_id
        }


def test_flee_resolution_ends_player_participation() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        service.flee(None, ctx)
        flee_action = session.exec(
            select(CombatAction).where(CombatAction.action_key == "flee")
        ).one()

        service.resolve_action(
            session,
            flee_action.id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        player = session.get(Player, "player-1")
        participant = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()

        assert player is not None and player.active_combat_session_id is None
        assert participant.status == "escaped"
        assert participant.position == "unengaged"


def test_stance_command_persists_participant_policy_and_updates_state() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        service.stance("aggressive", ctx)
        session.commit()

    with Session(engine) as session:
        participant = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()

        assert participant.stance == "aggressive"
        player_state = next(
            participant
            for participant in ctx.updates["combat"]["participants"]
            if participant["actor_type"] == "player"
        )
        assert player_state["stance"] == "aggressive"


def test_aggressive_stance_feeds_attack_resolution_trace() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        service.stance("aggressive", ctx)
        action = session.exec(
            select(CombatAction).where(CombatAction.actor_type == "player")
        ).one()
        action_id = action.id

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        action = session.get(CombatAction, action_id)
        assert action is not None
        record = session.exec(select(CombatResolutionRecord)).one()

        assert action.outcome["actor_stance"] == "aggressive"
        assert action.random_trace["actor_stance"] == "aggressive"
        assert action.random_trace["actor_stance_attack_bonus"] == 3.0
        assert record.damage_trace["actor_stance"] == "aggressive"
        assert record.damage_trace["actor_stance_damage_multiplier"] == 1.1


def test_mobile_stance_reduces_flee_stamina_cost() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        service.stance("mobile", ctx)
        service.flee(None, ctx)
        flee_action = session.exec(
            select(CombatAction).where(CombatAction.action_key == "flee")
        ).one()

        service.resolve_action(
            session,
            flee_action.id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        flee_action = session.exec(
            select(CombatAction).where(CombatAction.action_key == "flee")
        ).one()
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == flee_action.id
            )
        ).one()

        assert flee_action.outcome["actor_stance"] == "mobile"
        assert flee_action.outcome["stamina_delta"] == -4.0
        assert record.random_trace["stance_flee_stamina_delta"] == -4.0


def test_guarding_ally_creates_intercept_edge_and_redirects_attack() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        stats = session.get(PlayerStats, "player-1")
        assert stats is not None
        stats.agility = -100
        session.add(stats)
        service.attack("goblin", ctx)
        encounter = session.exec(select(CombatEncounter)).one()
        guardian = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        goblin = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "npc")
        ).one()
        ally = _add_ally_participant(session, encounter, guardian.side_id)

        service.guard("ally", ctx)
        guard_edge = session.exec(
            select(CombatRelationship)
            .where(CombatRelationship.source_participant_id == guardian.id)
            .where(CombatRelationship.target_participant_id == ally.id)
        ).one()
        guard_edge_id = guard_edge.id
        npc_attack = service._submit_action(
            repo=CombatRepo(session),
            session=session,
            encounter=encounter,
            actor=goblin,
            action_key="basic_attack",
            now=0.0,
            target=ally,
        )
        npc_attack_id = npc_attack.id

        service.resolve_action(
            session,
            npc_attack_id,
            rng=GameRng(seed=2),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        npc_attack = session.get(CombatAction, npc_attack_id)
        guard_edge = session.get(CombatRelationship, guard_edge_id)
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == npc_attack_id
            )
        ).one()

        assert guard_edge is not None
        assert guard_edge.engagement == "guarding"
        assert npc_attack is not None
        assert npc_attack.outcome["target_id"] == "player-1"
        assert record.target_id == "player-1"
        assert record.random_trace["intercepted"] is True
        assert record.random_trace["original_target_id"] == "ally"
        assert record.random_trace["interceptor_id"] == "player-1"
        guardian_hp = ctx_meters(engine).get(session, "player", "player-1", "hp")
        ally_hp = ctx_meters(engine).get(session, "player", "ally", "hp")
        assert guardian_hp.current < guardian_hp.maximum
        assert ally_hp.current == ally_hp.maximum


def test_ranged_attack_does_not_redirect_to_guarding_ally() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        stats = session.get(PlayerStats, "ally")
        assert stats is None
        service.attack("goblin", ctx)
        encounter = session.exec(select(CombatEncounter)).one()
        guardian = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        goblin = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "npc")
        ).one()
        ally = _add_ally_participant(session, encounter, guardian.side_id)
        ally_stats = session.get(PlayerStats, ally.actor_id)
        assert ally_stats is not None
        ally_stats.agility = -100
        session.add(ally_stats)
        service.guard("ally", ctx)

        npc_attack = service._submit_action(
            repo=CombatRepo(session),
            session=session,
            encounter=encounter,
            actor=goblin,
            action_key="ranged_attack",
            now=0.0,
            target=ally,
        )
        npc_attack_id = npc_attack.id

        service.resolve_action(
            session,
            npc_attack_id,
            rng=GameRng(seed=2),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == npc_attack_id
            )
        ).one()

        assert record.target_id == "ally"
        assert record.random_trace["action_range"] == "ranged"
        assert record.random_trace["intercept_eligible"] is False
        assert "intercepted" not in record.random_trace
        guardian_hp = ctx_meters(engine).get(session, "player", "player-1", "hp")
        ally_hp = ctx_meters(engine).get(session, "player", "ally", "hp")
        assert guardian_hp.current == guardian_hp.maximum
        assert ally_hp.current < ally_hp.maximum


def test_assist_joins_ally_encounter_and_counts_as_participation() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        session.add(
            Player(
                id="ally",
                username="ally",
                current_room_id="arena",
                respawn_room_id="arena",
            )
        )
        session.add(PlayerStats(player_id="ally", strength=10, agility=10, max_hp=100))
        session.flush()

        service.attack("goblin", ctx)
        ally_ctx = _context_for_existing_player(session, "ally")
        service.assist("petem", ally_ctx)
        session.commit()

    with Session(engine) as session:
        encounter = session.exec(select(CombatEncounter)).one()
        player = session.exec(
            select(CombatParticipant)
            .where(CombatParticipant.actor_type == "player")
            .where(CombatParticipant.actor_id == "player-1")
        ).one()
        ally = session.exec(
            select(CombatParticipant)
            .where(CombatParticipant.actor_type == "player")
            .where(CombatParticipant.actor_id == "ally")
        ).one()
        goblin = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "npc")
        ).one()
        ally_player = session.get(Player, "ally")
        support = session.exec(
            select(CombatRelationship)
            .where(CombatRelationship.source_participant_id == ally.id)
            .where(CombatRelationship.target_participant_id == player.id)
        ).one()
        hostile = session.exec(
            select(CombatRelationship)
            .where(CombatRelationship.source_participant_id == ally.id)
            .where(CombatRelationship.target_participant_id == goblin.id)
        ).one()

        assert ally_player is not None
        assert ally_player.active_combat_session_id == encounter.id
        assert ally.side_id == player.side_id
        assert ally.contribution["participation"] == "assistance"
        assert ally.contribution["counts_as_participation"] is True
        assert ally.contribution["combat_contract"]["kind"] == "party_assist"
        assert support.hostility == "supportive"
        assert hostile.hostility == "hostile"


def test_reaction_policy_updates_state_and_auto_reaction_is_bounded() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        encounter = session.exec(select(CombatEncounter)).one()
        player = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        goblin = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "npc")
        ).one()
        npc_attack = service._submit_action(
            repo=CombatRepo(session),
            session=session,
            encounter=encounter,
            actor=goblin,
            action_key="basic_attack",
            now=0.0,
            target=player,
        )
        npc_attack_id = npc_attack.id

        service.resolve_action(
            session,
            npc_attack_id,
            rng=GameRng(seed=2),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        player = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == npc_attack_id
            )
        ).one()

        assert record.random_trace["auto_reaction_policy"] == "defensive"
        assert record.random_trace["auto_reaction_used"] is True
        assert record.random_trace["auto_reaction_kind"] == "brace"
        assert player.last_reaction_action_id == npc_attack_id
        assert player.reaction_ready_at == 11.5


def test_reaction_never_policy_disables_auto_reaction() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        service.reaction("never", ctx)
        encounter = session.exec(select(CombatEncounter)).one()
        player = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        goblin = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "npc")
        ).one()
        npc_attack = service._submit_action(
            repo=CombatRepo(session),
            session=session,
            encounter=encounter,
            actor=goblin,
            action_key="basic_attack",
            now=0.0,
            target=player,
        )
        npc_attack_id = npc_attack.id

        service.resolve_action(
            session,
            npc_attack_id,
            rng=GameRng(seed=2),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        player = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == npc_attack_id
            )
        ).one()

        assert player.reaction_policy == "never"
        assert player.last_reaction_action_id is None
        assert record.random_trace["auto_reaction_policy"] == "never"
        assert record.random_trace["auto_reaction_used"] is False


def test_inactive_actor_interrupts_pending_windup_with_record() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        action = session.exec(
            select(CombatAction).where(CombatAction.actor_type == "player")
        ).one()
        actor = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        actor.status = "downed"
        session.add(actor)

        service.resolve_action(
            session,
            action.id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        action = session.exec(select(CombatAction)).one()
        record = session.exec(select(CombatResolutionRecord)).one()

        assert action.state == "interrupted"
        assert action.outcome["outcome"] == "interrupted"
        assert action.outcome["resolution_record_id"] == record.id
        assert record.outcome == "interrupted"
        assert record.random_trace["interrupt_reason"] == "actor_status:downed"


def test_strong_hit_applies_off_balance_effect_and_expiry_hook_removes_it() -> None:
    engine = _engine()
    bus = EventBus()
    effect_service = EffectService(engine, GameRng(seed=1))
    effect_service.register(bus)
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session, bus=bus)
        stats = session.get(PlayerStats, "player-1")
        assert stats is not None
        stats.strength = 120
        session.add(stats)
        goblin = session.get(NPC, "goblin")
        assert goblin is not None
        goblin.max_hp = 500
        session.add(goblin)
        service.attack("goblin", ctx)
        action = session.exec(
            select(CombatAction).where(CombatAction.actor_type == "player")
        ).one()
        action_id = action.id

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
            effect_service=effect_service,
        )
        session.commit()

    with Session(engine) as session:
        effect = session.exec(select(ActiveEffect)).one()
        record = session.exec(select(CombatResolutionRecord)).one()

        assert effect.effect_key == "combat.off_balance"
        assert effect.entity_type == "npc"
        assert effect.entity_id == "goblin"
        assert effect.applied_at_epoch == 10.0
        assert effect.expires_at_epoch == 16.0
        assert effect.payload["source_action_id"] == action_id
        assert record.payload["effect_changes"][0]["effect_id"] == effect.id
        assert record.random_trace["target_active_effects"] == []

    with Session(engine) as session:
        encounter = session.exec(select(CombatEncounter)).one()
        player = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        goblin = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "npc")
        ).one()
        action = service._submit_action(
            repo=CombatRepo(session),
            session=session,
            encounter=encounter,
            actor=player,
            action_key="basic_attack",
            now=12.0,
            target=goblin,
        )
        second_action_id = action.id
        service.resolve_action(
            session,
            second_action_id,
            rng=GameRng(seed=1),
            current_epoch=12.0,
            meter_service=ctx_meters(engine),
            effect_service=effect_service,
        )
        session.commit()

    with Session(engine) as session:
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == second_action_id
            )
        ).one()
        assert record.random_trace["target_active_effects"] == ["combat.off_balance"]
        assert record.random_trace["target_stance_defense_bonus"] == -3

    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": 17.0}), ctx=None)

    with Session(engine) as session:
        assert session.exec(select(ActiveEffect)).all() == []


def test_combat_effect_hooks_record_admission_and_damage_payloads() -> None:
    engine = _engine()
    service = CombatService()
    hook_registry = get_combat_effect_hook_registry()
    hook_registry.register(
        "combat.test_admission",
        CombatEffectHooks(
            on_action_admission=lambda effect, context: {
                "action_key": context.action_key,
                "target_participant_id": context.target_participant_id,
            }
        ),
    )
    hook_registry.register(
        "combat.test_damage",
        CombatEffectHooks(
            on_damage_received=lambda effect, context: {
                "damage": context.damage,
                "action_key": context.action.action_key,
            }
        ),
    )

    with Session(engine) as session:
        ctx = _context(session)
        session.add(
            ActiveEffect(
                id="effect-admission",
                entity_type="player",
                entity_id="player-1",
                effect_key="combat.test_admission",
                payload={},
                applied_at_epoch=0.0,
            )
        )
        session.add(
            ActiveEffect(
                id="effect-damage",
                entity_type="npc",
                entity_id="goblin",
                effect_key="combat.test_damage",
                payload={},
                applied_at_epoch=0.0,
            )
        )
        service.attack("goblin", ctx)
        action = session.exec(select(CombatAction)).one()
        action_id = action.id

        assert action.random_trace["action_admission_hooks"][0]["effect_key"] == (
            "combat.test_admission"
        )

        service.resolve_action(
            session,
            action_id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        action = session.get(CombatAction, action_id)
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == action_id
            )
        ).one()

        assert action is not None
        assert action.random_trace["action_admission_hooks"][0]["event"] == (
            "on_action_admission"
        )
        hook_changes = [
            change
            for change in record.payload["effect_changes"]
            if change.get("event") == "on_damage_received"
        ]
        assert hook_changes
        assert hook_changes[0]["effect_key"] == "combat.test_damage"
        assert hook_changes[0]["payload"]["action_key"] == "basic_attack"


def test_combat_effect_movement_hooks_record_position_changes() -> None:
    engine = _engine()
    service = CombatService()
    get_combat_effect_hook_registry().register(
        "combat.test_movement",
        CombatEffectHooks(
            on_movement=lambda effect, context: {
                "from_position": context.from_position,
                "to_position": context.to_position,
            }
        ),
    )

    with Session(engine) as session:
        ctx = _context(session)
        service.attack("goblin", ctx)
        encounter = session.exec(select(CombatEncounter)).one()
        goblin = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "npc")
        ).one()
        goblin.position = "unengaged"
        session.add(goblin)
        session.add(
            ActiveEffect(
                id="effect-movement",
                entity_type="npc",
                entity_id="goblin",
                effect_key="combat.test_movement",
                payload={},
                applied_at_epoch=0.0,
            )
        )

        position_changes, effect_changes = service._refresh_positions(
            CombatRepo(session),
            session,
            encounter.id,
            current_epoch=3.0,
        )

        assert position_changes[0]["actor_id"] == "goblin"
        assert effect_changes[0]["event"] == "on_movement"
        assert effect_changes[0]["payload"] == {
            "from_position": "unengaged",
            "to_position": "engaged",
        }


def test_npc_hp_depletion_marks_defeated_and_unengages_participants() -> None:
    engine = _engine()
    service = CombatService()

    with Session(engine) as session:
        ctx = _context(session)
        goblin = session.get(NPC, "goblin")
        assert goblin is not None
        goblin.max_hp = 1
        session.add(goblin)
        service.attack("goblin", ctx)
        action = session.exec(select(CombatAction)).one()

        service.resolve_action(
            session,
            action.id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
        )
        session.commit()

    with Session(engine) as session:
        encounter = session.exec(select(CombatEncounter)).one()
        participants = session.exec(select(CombatParticipant)).all()
        by_type = {participant.actor_type: participant for participant in participants}
        record = session.exec(select(CombatResolutionRecord)).one()

        assert encounter.state == "ended"
        assert by_type["npc"].status == "defeated"
        assert by_type["npc"].position == "unengaged"
        assert by_type["player"].position == "unengaged"
        assert record.payload["state_changes"][0]["to_status"] == "defeated"
        assert record.payload["position_changes"]


def test_npc_defeat_applies_configured_coin_reward_and_final_prose() -> None:
    engine = _engine()
    service = CombatService()
    bus = EventBus()
    observed: list[dict] = []
    bus.on(GameEvent.PLAYER_ATTACKED, lambda event, ctx: observed.append(event.payload))

    with Session(engine) as session:
        ctx = _context(session, bus=bus)
        goblin = session.get(NPC, "goblin")
        assert goblin is not None
        goblin.max_hp = 1
        goblin.ai = {
            "combat_rewards": {
                "on_defeat": [
                    {
                        "type": "coins",
                        "amount": 25,
                        "message": "You earn 25 coins for the clean spar.",
                    }
                ]
            }
        }
        session.add(goblin)
        service.attack("goblin", ctx)
        action = session.exec(select(CombatAction)).one()

        service.resolve_action(
            session,
            action.id,
            rng=GameRng(seed=1),
            current_epoch=10.0,
            meter_service=ctx.meters,
            bus=bus,
        )
        session.commit()

        assert LedgerService().balance_of(session, "player", "player-1") == 25
        record = session.exec(select(CombatResolutionRecord)).one()
        assert record.payload["consequence_changes"][0]["type"] == "coins"
        assert record.payload["consequence_changes"][0]["amount"] == 25

    assert observed
    assert "Goblin is defeated." in observed[0]["prose"]
    assert "You earn 25 coins for the clean spar." in observed[0]["prose"]


def test_player_hp_depletion_kills_respawns_and_cancels_queued_action() -> None:
    engine = _engine()
    service = CombatService()
    bus = EventBus()
    observed: list[dict] = []
    death_events: list[dict] = []
    respawn_events: list[dict] = []
    bus.on(GameEvent.NPC_ATTACKED, lambda event, ctx: observed.append(event.payload))
    bus.on(GameEvent.PLAYER_DIED, lambda event, ctx: death_events.append(event.payload))
    bus.on(
        GameEvent.PLAYER_RESPAWNED,
        lambda event, ctx: respawn_events.append(event.payload),
    )

    with Session(engine) as session:
        ctx = _context(session, bus=bus)
        session.add(
            Room(
                id="temple",
                name="Temple",
                description="A respawn point.",
                map_x=1,
                map_y=1,
            )
        )
        session.add(
            Item(
                id="corpse",
                name="Corpse",
                description="Death container.",
                takeable=False,
                capacity=200.0,
            )
        )
        session.add(Item(id="trinket", name="Trinket", description="Loose loot."))
        session.add(
            Item(
                id="bound_charm",
                name="Bound Charm",
                description="Kept.",
                bound=True,
            )
        )
        session.add(
            Item(
                id="worn_vest",
                name="Worn Vest",
                description="Equipped.",
                slot="torso",
                wearable=True,
            )
        )
        session.flush()
        ctx.player.respawn_room_id = "temple"
        session.add(ctx.player)
        ctx.ledger.credit(session, "player", ctx.player.id, 100)
        ctx.item_location.spawn("trinket", Location("player", ctx.player.id))
        ctx.item_location.spawn("bound_charm", Location("player", ctx.player.id))
        ctx.item_location.spawn(
            "worn_vest", Location("player", ctx.player.id, slot="torso")
        )
        stats = session.get(PlayerStats, "player-1")
        assert stats is not None
        stats.max_hp = 5
        stats.agility = -100
        session.add(stats)

        service.attack("goblin", ctx)
        player_action = session.exec(
            select(CombatAction).where(CombatAction.actor_type == "player")
        ).one()
        service.resolve_action(
            session,
            player_action.id,
            rng=GameRng(seed=1),
            current_epoch=1.0,
            meter_service=ctx.meters,
        )
        service.defend(None, ctx)
        queued_defend = session.exec(
            select(CombatAction).where(CombatAction.action_key == "defend")
        ).one()
        queued_defend_id = queued_defend.id
        npc_action = session.exec(
            select(CombatAction)
            .where(CombatAction.actor_type == "npc")
            .where(CombatAction.state == "pending")
        ).one()
        npc_action_id = npc_action.id

        service.resolve_action(
            session,
            npc_action_id,
            rng=GameRng(seed=2),
            current_epoch=2.0,
            meter_service=ctx.meters,
            bus=bus,
        )
        session.commit()

    with Session(engine) as session:
        player = session.get(Player, "player-1")
        participant = session.exec(
            select(CombatParticipant).where(CombatParticipant.actor_type == "player")
        ).one()
        queued = session.get(CombatAction, queued_defend_id)
        record = session.exec(
            select(CombatResolutionRecord).where(
                CombatResolutionRecord.action_id == npc_action_id
            )
        ).one()
        hp = ctx_meters(engine).get(session, "player", "player-1", "hp")
        death_change = record.payload["consequence_changes"][0]
        corpse_instance_id = death_change["corpse_instance_id"]
        corpse_stack_id = death_change["corpse_stack_id"]
        weakened_effects = session.exec(
            select(ActiveEffect).where(ActiveEffect.effect_key == "weakened")
        ).all()
        corpse_stack = session.get(ItemStack, corpse_stack_id)
        corpse_contents = StackRepo(session).stacks_for_owner(
            "container", corpse_instance_id
        )

        assert player is not None and player.active_combat_session_id is None
        assert player.current_room_id == "temple"
        assert LedgerService().balance_of(session, "player", "player-1") == 80
        assert (
            LedgerService().balance_of(session, "container", corpse_instance_id) == 20
        )
        assert participant.status == "dead"
        assert participant.position == "unengaged"
        assert participant.queued_action_id is None
        assert hp.current == 1.25
        assert queued is not None and queued.state == "cancelled"
        assert record.payload["state_changes"][0]["to_status"] == "dead"
        assert death_change["type"] == "player_respawned"
        assert death_change["coin_loss"] == 20
        assert death_change["dropped_stacks"][0]["item_id"] == "trinket"
        assert corpse_stack is not None and corpse_stack.owner_id == "arena"
        assert {stack.item_id for stack in corpse_contents} == {"trinket"}
        assert (
            StackRepo(session).quantity_of(
                Location("player", "player-1"), "bound_charm"
            )
            == 1
        )
        assert (
            StackRepo(session).quantity_of(
                Location("player", "player-1", slot="torso"), "worn_vest"
            )
            == 1
        )
        assert len(weakened_effects) == 1
        assert (
            queued_defend_id
            in record.payload["state_changes"][0]["cancelled_action_ids"]
        )
    assert observed
    assert "petem dies." in observed[0]["prose"]
    assert "You wake at temple" in observed[0]["prose"]
    assert death_events and death_events[0]["coin_loss"] == 20
    assert death_events[0]["dropped_stacks"][0]["item_id"] == "trinket"
    assert respawn_events and respawn_events[0]["respawn_hp"] == 1.25
    assert respawn_events[0]["weakened_effect_id"] == weakened_effects[0].id


def test_damage_profiles_use_equipped_weapon_and_armor_descriptors() -> None:
    engine = _engine()
    with Session(engine) as session:
        _context(session)
        session.add(
            Item(
                id="fine_sword",
                name="Fine Sword",
                description="Sharp.",
                slot="main_hand",
                weight=4.0,
                category="weapon",
                quality="fine",
            )
        )
        session.add(
            Item(
                id="chainmail",
                name="Chainmail",
                description="Heavy rings.",
                slot="torso",
                wearable=True,
                weight=12.0,
                category="armor",
                quality="common",
            )
        )
        session.add(
            ItemStack(
                item_id="fine_sword",
                owner_type="player",
                owner_id="player-1",
                slot="main_hand",
            )
        )
        session.add(
            ItemStack(
                item_id="chainmail",
                owner_type="player",
                owner_id="player-1",
                slot="torso",
            )
        )
        session.flush()

        weapon = weapon_profile_for(session, "player", "player-1")
        armor = armor_profile_for(session, "player", "player-1")
        mitigated = apply_damage_stack(
            base_damage=12.0,
            outcome_multiplier=1.0,
            armor=armor,
            penetration=weapon.penetration,
        )
        unarmored = apply_damage_stack(
            base_damage=12.0,
            outcome_multiplier=1.0,
            armor=ArmorProfile(block=0.0, resistance_factor=0.0, sources=()),
            penetration=0.0,
        )

        assert weapon.base_damage > 4.0
        assert weapon.accuracy_bonus > 0.0
        assert "item:fine_sword" in weapon.sources
        assert armor.block > 0.0
        assert armor.resistance_factor > 0.0
        assert "item:chainmail" in armor.sources
        assert mitigated.amount < unarmored.amount
        assert mitigated.trace["armor_sources"] == ["item:chainmail"]


def test_combat_damage_profiles_prefer_item_effect_descriptors() -> None:
    engine = _engine()
    with Session(engine) as session:
        _context(session)
        session.add(
            Item(
                id="dueling_pistol",
                name="Dueling Pistol",
                description="Loud.",
                slot="main_hand",
                weight=1.0,
                category="tool",
                effects=[
                    {
                        "type": "weapon_profile",
                        "base_damage": 11.0,
                        "accuracy_bonus": 2.0,
                        "penetration": 3.0,
                        "tags": ["ranged", "piercing"],
                    }
                ],
            )
        )
        session.add(
            Item(
                id="duelist_coat",
                name="Duelist Coat",
                description="Reinforced.",
                slot="torso",
                wearable=True,
                weight=1.0,
                category="clothing",
                effects=[
                    {
                        "type": "armor_profile",
                        "block": 2.5,
                        "resistance_factor": 0.12,
                        "tags": ["padded"],
                    }
                ],
            )
        )
        session.add(
            ItemStack(
                item_id="dueling_pistol",
                owner_type="player",
                owner_id="player-1",
                slot="main_hand",
            )
        )
        session.add(
            ItemStack(
                item_id="duelist_coat",
                owner_type="player",
                owner_id="player-1",
                slot="torso",
            )
        )
        session.flush()

        weapon = weapon_profile_for(session, "player", "player-1")
        armor = armor_profile_for(session, "player", "player-1")
        damage = apply_damage_stack(
            base_damage=weapon.base_damage,
            outcome_multiplier=1.0,
            armor=armor,
            penetration=weapon.penetration,
        )

        assert weapon.base_damage == 11.0
        assert weapon.accuracy_bonus == 2.0
        assert weapon.penetration == 3.0
        assert weapon.sources == ("item:dueling_pistol:weapon_profile",)
        assert weapon.tags == ("piercing", "ranged")
        assert armor.block == 2.5
        assert armor.resistance_factor == 0.12
        assert armor.sources == ("item:duelist_coat:armor_profile",)
        assert armor.tags == ("padded",)
        assert damage.trace["armor_tags"] == ["padded"]


def test_combat_broadcast_sends_prose_and_structured_update() -> None:
    class RecordingManager:
        def __init__(self) -> None:
            self.messages: list[tuple[str, dict]] = []

        async def broadcast_to_room(self, room_id: str, message: dict) -> None:
            self.messages.append((room_id, message))

    manager = RecordingManager()
    event = Event(
        GameEvent.PLAYER_ATTACKED,
        {
            "room_id": "arena",
            "sequence": 3,
            "prose": "petem attacks Goblin: hit.",
            "combat_update": {
                "sequence": 3,
                "encounter_id": "encounter-1",
                "participants": [],
            },
        },
    )

    asyncio.run(broadcast_combat_resolution(manager, event))  # type: ignore[arg-type]

    assert manager.messages == [
        (
            "arena",
            {
                "type": "feed_append",
                "content": "petem attacks Goblin: hit.",
                "message_type": "combat",
                "sequence": 3,
            },
        ),
        (
            "arena",
            {
                "type": "combat_update",
                "sequence": 3,
                "encounter_id": "encounter-1",
                "participants": [],
            },
        ),
    ]


def _add_ally_participant(
    session: Session, encounter: CombatEncounter, side_id: str
) -> CombatParticipant:
    player = Player(
        id="ally",
        username="ally",
        current_room_id="arena",
        respawn_room_id="arena",
    )
    session.add(player)
    session.add(
        PlayerStats(
            player_id=player.id,
            strength=10,
            agility=10,
            max_hp=100,
        )
    )
    participant = CombatParticipant(
        id="ally-participant",
        encounter_id=encounter.id,
        actor_type="player",
        actor_id=player.id,
        side_id=side_id,
        joined_at=0.0,
        primary_ready_at=0.0,
        reaction_ready_at=0.0,
    )
    session.add(participant)
    session.flush()
    return participant


def _engine():
    engine, _ = _engine_pair()
    return engine


def _engine_pair():
    engine = create_engine("sqlite://")
    audit_engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=audit_engine)
    return engine, audit_engine


def _context(
    session: Session,
    *,
    bus: EventBus | None = None,
    rng: GameRng | None = None,
    rules: RuleEngine | None = None,
) -> GameContext:
    room = Room(
        id="arena",
        name="Arena",
        description="A test arena.",
        map_x=0,
        map_y=0,
    )
    player = Player(
        id="player-1",
        username="petem",
        current_room_id="arena",
        respawn_room_id="arena",
    )
    npc = NPC(
        id="goblin",
        name="Goblin",
        description="A hostile goblin.",
        current_room_id="arena",
        home_room_id="arena",
        dialogue_tree_id="goblin",
        max_hp=40,
    )
    session.add(room)
    session.add(player)
    session.add(
        PlayerStats(
            player_id=player.id,
            strength=30,
            agility=12,
            max_hp=100,
        )
    )
    session.add(npc)
    session.flush()
    rng = rng or GameRng(seed=1)
    engine = session.get_bind()
    assert isinstance(engine, Engine)
    return GameContext(
        player=player,
        room=room,
        clock=WorldClock(game_epoch=0.0, real_epoch=0.0),
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=rng,
        session=session,
        meters=MeterService(engine, rng),
        effects=EffectService(engine, rng),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=bus or EventBus(),
        audit=AuditRepo(session),
        transaction=TransactionContext.create(
            actor_id="player-1", correlation_id="session-1"
        ),
        session_id="session-1",
        rules=rules,
    )


def _context_for_existing_player(
    session: Session,
    player_id: str,
    *,
    bus: EventBus | None = None,
    rng: GameRng | None = None,
) -> GameContext:
    player = session.get(Player, player_id)
    assert player is not None
    room = session.get(Room, player.current_room_id)
    assert room is not None
    rng = rng or GameRng(seed=1)
    engine = session.get_bind()
    assert isinstance(engine, Engine)
    return GameContext(
        player=player,
        room=room,
        clock=WorldClock(game_epoch=0.0, real_epoch=0.0),
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=rng,
        session=session,
        meters=MeterService(engine, rng),
        effects=EffectService(engine, rng),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=bus or EventBus(),
        audit=AuditRepo(session),
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id=f"session-{player.id}"
        ),
        session_id=f"session-{player.id}",
    )


def _hp_base(entity_type: str, entity_id: str, session: Session) -> float:
    if entity_type == "player":
        stats = session.get(PlayerStats, entity_id)
        return float(stats.max_hp if stats is not None else 100)
    npc = session.get(NPC, entity_id)
    return float(npc.max_hp if npc is not None else 50)


def ctx_meters(engine) -> MeterService:
    return MeterService(engine, GameRng(seed=1))
