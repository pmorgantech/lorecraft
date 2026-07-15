"""Combat aggregate data access."""

from __future__ import annotations

from collections.abc import Sequence

from sqlmodel import Session, col, select

from lorecraft.features.combat.models import (
    CombatAction,
    CombatEncounter,
    CombatParticipant,
    CombatRelationship,
    CombatResolutionRecord,
)


class CombatRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def encounter(self, encounter_id: str) -> CombatEncounter | None:
        return self.session.get(CombatEncounter, encounter_id)

    def action(self, action_id: str) -> CombatAction | None:
        return self.session.get(CombatAction, action_id)

    def resolution_record_for_action(
        self, action_id: str
    ) -> CombatResolutionRecord | None:
        statement = select(CombatResolutionRecord).where(
            CombatResolutionRecord.action_id == action_id
        )
        return self.session.exec(statement).first()

    def participant(self, participant_id: str) -> CombatParticipant | None:
        return self.session.get(CombatParticipant, participant_id)

    def participants(self, encounter_id: str) -> Sequence[CombatParticipant]:
        statement = (
            select(CombatParticipant)
            .where(CombatParticipant.encounter_id == encounter_id)
            .order_by(col(CombatParticipant.joined_at), col(CombatParticipant.id))
        )
        return self.session.exec(statement).all()

    def active_encounter_for_actor(
        self, actor_type: str, actor_id: str
    ) -> CombatEncounter | None:
        statement = (
            select(CombatEncounter)
            .join(
                CombatParticipant,
                col(CombatParticipant.encounter_id) == col(CombatEncounter.id),
            )
            .where(CombatEncounter.state == "active")
            .where(CombatParticipant.actor_type == actor_type)
            .where(CombatParticipant.actor_id == actor_id)
            .where(CombatParticipant.status == "active")
            .order_by(col(CombatEncounter.started_at_game_time).desc())
        )
        return self.session.exec(statement).first()

    def participant_for_actor(
        self, encounter_id: str, actor_type: str, actor_id: str
    ) -> CombatParticipant | None:
        statement = (
            select(CombatParticipant)
            .where(CombatParticipant.encounter_id == encounter_id)
            .where(CombatParticipant.actor_type == actor_type)
            .where(CombatParticipant.actor_id == actor_id)
        )
        return self.session.exec(statement).first()

    def active_participants(self, encounter_id: str) -> Sequence[CombatParticipant]:
        statement = (
            select(CombatParticipant)
            .where(CombatParticipant.encounter_id == encounter_id)
            .where(CombatParticipant.status == "active")
            .order_by(col(CombatParticipant.joined_at), col(CombatParticipant.id))
        )
        return self.session.exec(statement).all()

    def hostile_target_for(
        self, encounter_id: str, source_participant_id: str
    ) -> CombatParticipant | None:
        statement = (
            select(CombatParticipant)
            .join(
                CombatRelationship,
                col(CombatRelationship.target_participant_id)
                == col(CombatParticipant.id),
            )
            .where(CombatRelationship.encounter_id == encounter_id)
            .where(CombatRelationship.source_participant_id == source_participant_id)
            .where(CombatRelationship.hostility == "hostile")
            .where(CombatParticipant.status == "active")
            .order_by(col(CombatParticipant.joined_at), col(CombatParticipant.id))
        )
        return self.session.exec(statement).first()

    def relationship_between(
        self, encounter_id: str, source_participant_id: str, target_participant_id: str
    ) -> CombatRelationship | None:
        statement = (
            select(CombatRelationship)
            .where(CombatRelationship.encounter_id == encounter_id)
            .where(CombatRelationship.source_participant_id == source_participant_id)
            .where(CombatRelationship.target_participant_id == target_participant_id)
        )
        return self.session.exec(statement).first()

    def relationships_for_encounter(
        self, encounter_id: str
    ) -> Sequence[CombatRelationship]:
        statement = (
            select(CombatRelationship)
            .where(CombatRelationship.encounter_id == encounter_id)
            .order_by(
                col(CombatRelationship.source_participant_id),
                col(CombatRelationship.target_participant_id),
            )
        )
        return self.session.exec(statement).all()

    def pending_primary_action(self, participant_id: str) -> CombatAction | None:
        statement = (
            select(CombatAction)
            .where(CombatAction.actor_participant_id == participant_id)
            .where(CombatAction.channel == "primary")
            .where(CombatAction.state.in_(["pending", "queued"]))  # type: ignore[attr-defined]
            .order_by(col(CombatAction.submitted_at).desc())
        )
        return self.session.exec(statement).first()

    def pending_primary_actions(self, participant_id: str) -> Sequence[CombatAction]:
        statement = (
            select(CombatAction)
            .where(CombatAction.actor_participant_id == participant_id)
            .where(CombatAction.channel == "primary")
            .where(CombatAction.state.in_(["pending", "queued"]))  # type: ignore[attr-defined]
            .order_by(col(CombatAction.submitted_at), col(CombatAction.id))
        )
        return self.session.exec(statement).all()

    def add(self, row: object) -> None:
        self.session.add(row)
