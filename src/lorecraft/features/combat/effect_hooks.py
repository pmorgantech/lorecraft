"""Combat-local active-effect hook registry.

The generic engine effect system owns timed effect lifecycle. Combat owns these
policy hook points because they are combat-specific events and payloads.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlmodel import Session

from lorecraft.engine.models.meters import ActiveEffect
from lorecraft.features.combat.models import CombatAction, CombatParticipant
from lorecraft.features.combat.resolution import CombatResolution
from lorecraft.types import JsonObject


@dataclass(frozen=True)
class DamageReceivedContext:
    session: Session
    participant: CombatParticipant
    action: CombatAction
    resolution: CombatResolution
    damage: float
    current_epoch: float


@dataclass(frozen=True)
class ActionAdmissionContext:
    session: Session
    participant: CombatParticipant
    action_key: str
    target_participant_id: str | None
    current_epoch: float


@dataclass(frozen=True)
class MovementContext:
    session: Session
    participant: CombatParticipant
    from_position: str
    to_position: str
    current_epoch: float


DamageReceivedHook = Callable[[ActiveEffect, DamageReceivedContext], JsonObject | None]
ActionAdmissionHook = Callable[
    [ActiveEffect, ActionAdmissionContext], JsonObject | None
]
MovementHook = Callable[[ActiveEffect, MovementContext], JsonObject | None]


@dataclass(frozen=True)
class CombatEffectHooks:
    on_damage_received: DamageReceivedHook | None = None
    on_action_admission: ActionAdmissionHook | None = None
    on_movement: MovementHook | None = None


class CombatEffectHookRegistry:
    def __init__(self) -> None:
        self._hooks: dict[str, CombatEffectHooks] = {}

    def register(self, effect_key: str, hooks: CombatEffectHooks) -> None:
        self._hooks[effect_key] = hooks

    def get(self, effect_key: str) -> CombatEffectHooks | None:
        return self._hooks.get(effect_key)

    def clear(self) -> None:
        self._hooks.clear()


_registry = CombatEffectHookRegistry()


def get_combat_effect_hook_registry() -> CombatEffectHookRegistry:
    return _registry


def run_damage_received_hooks(
    effects: list[ActiveEffect], context: DamageReceivedContext
) -> list[JsonObject]:
    results: list[JsonObject] = []
    registry = get_combat_effect_hook_registry()
    for effect in effects:
        hooks = registry.get(effect.effect_key)
        if hooks is None or hooks.on_damage_received is None:
            continue
        payload = hooks.on_damage_received(effect, context)
        if payload is not None:
            results.append(_hook_result(effect, "on_damage_received", payload))
    return results


def run_action_admission_hooks(
    effects: list[ActiveEffect], context: ActionAdmissionContext
) -> list[JsonObject]:
    results: list[JsonObject] = []
    registry = get_combat_effect_hook_registry()
    for effect in effects:
        hooks = registry.get(effect.effect_key)
        if hooks is None or hooks.on_action_admission is None:
            continue
        payload = hooks.on_action_admission(effect, context)
        if payload is not None:
            results.append(_hook_result(effect, "on_action_admission", payload))
    return results


def run_movement_hooks(
    effects: list[ActiveEffect], context: MovementContext
) -> list[JsonObject]:
    results: list[JsonObject] = []
    registry = get_combat_effect_hook_registry()
    for effect in effects:
        hooks = registry.get(effect.effect_key)
        if hooks is None or hooks.on_movement is None:
            continue
        payload = hooks.on_movement(effect, context)
        if payload is not None:
            results.append(_hook_result(effect, "on_movement", payload))
    return results


def _hook_result(effect: ActiveEffect, event: str, payload: JsonObject) -> JsonObject:
    return {
        "event": event,
        "effect_id": effect.id,
        "effect_key": effect.effect_key,
        "actor_type": effect.entity_type,
        "actor_id": effect.entity_id,
        "payload": payload,
    }
