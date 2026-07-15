"""Registered boss phase resolvers for combat NPC counter-intents."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlmodel import Session

from lorecraft.engine.models.world import NPC
from lorecraft.features.combat.models import (
    CombatAction,
    CombatEncounter,
    CombatParticipant,
)
from lorecraft.features.combat.repo import CombatRepo
from lorecraft.types import JsonObject


@dataclass(frozen=True)
class BossPhaseContext:
    session: Session
    repo: CombatRepo
    encounter: CombatEncounter
    npc: NPC
    participant: CombatParticipant
    triggering_action: CombatAction
    fallback_target: CombatParticipant
    current_epoch: float


@dataclass(frozen=True)
class BossPhaseDecision:
    action_key: str
    target_participant_id: str | None = None
    phase: str | None = None
    payload: JsonObject = field(default_factory=dict)

    def trace(self) -> JsonObject:
        return {
            "phase": self.phase,
            "action_key": self.action_key,
            "target_participant_id": self.target_participant_id,
            "payload": self.payload,
        }


BossPhaseResolver = Callable[[BossPhaseContext], BossPhaseDecision | None]


class BossPhaseRegistry:
    def __init__(self) -> None:
        self._resolvers: dict[str, BossPhaseResolver] = {}

    def register(self, key: str, resolver: BossPhaseResolver) -> None:
        self._resolvers[key] = resolver

    def get(self, key: str) -> BossPhaseResolver | None:
        return self._resolvers.get(key)

    def clear(self) -> None:
        self._resolvers.clear()


_registry = BossPhaseRegistry()


def get_boss_phase_registry() -> BossPhaseRegistry:
    return _registry
