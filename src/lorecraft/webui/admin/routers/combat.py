"""Admin API router for live-tuning combat ruleset config."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, col, select

from lorecraft.features.combat.definitions import get_action_registry
from lorecraft.features.combat.models import CombatRulesetConfig, CombatWound
from lorecraft.features.combat.rulesets import get_or_create_combat_ruleset_config
from lorecraft.webui.admin.auth import Observer, Superadmin

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


def _serialize(config: CombatRulesetConfig) -> dict[str, float | str]:
    return {
        "id": config.id,
        "damage_multiplier": config.damage_multiplier,
        "stamina_cost_multiplier": config.stamina_cost_multiplier,
    }


def _serialize_wound(wound: CombatWound) -> dict[str, Any]:
    return {
        "id": wound.id,
        "encounter_id": wound.encounter_id,
        "action_id": wound.action_id,
        "target_type": wound.target_type,
        "target_id": wound.target_id,
        "body_location": wound.body_location,
        "severity": wound.severity,
        "damage": wound.damage,
        "status": wound.status,
        "created_at_game_time": wound.created_at_game_time,
        "healed_at_game_time": wound.healed_at_game_time,
        "payload": wound.payload,
    }


def _known_ruleset_ids() -> list[str]:
    ids = {action.ruleset_id for action in get_action_registry().all()}
    return sorted(ids)


@router.get("/combat/rulesets")
async def get_combat_rulesets(
    request: Request, _: Observer
) -> list[dict[str, float | str]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        configs = [
            get_or_create_combat_ruleset_config(session, ruleset_id)
            for ruleset_id in _known_ruleset_ids()
        ]
        session.commit()
        return [_serialize(config) for config in configs]


@router.get("/combat/wounds")
async def get_combat_wounds(
    request: Request,
    _: Observer,
    target_type: str | None = None,
    target_id: str | None = None,
    status: str | None = "active",
    limit: int = 100,
) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        stmt = select(CombatWound).order_by(
            col(CombatWound.created_at_game_time).desc()
        )
        if target_type:
            stmt = stmt.where(CombatWound.target_type == target_type)
        if target_id:
            stmt = stmt.where(CombatWound.target_id == target_id)
        if status:
            stmt = stmt.where(CombatWound.status == status)
        wounds = session.exec(stmt.limit(min(limit, 500))).all()
        return [_serialize_wound(wound) for wound in wounds]


class _CombatRulesetBody(BaseModel):
    damage_multiplier: float | None = None
    stamina_cost_multiplier: float | None = None


@router.post("/combat/rulesets/{ruleset_id}")
async def set_combat_ruleset(
    ruleset_id: str, body: _CombatRulesetBody, request: Request, _: Superadmin
) -> dict[str, float | str]:
    if body.damage_multiplier is not None and body.damage_multiplier <= 0:
        raise HTTPException(
            status_code=422, detail="damage_multiplier must be positive"
        )
    if body.stamina_cost_multiplier is not None and body.stamina_cost_multiplier <= 0:
        raise HTTPException(
            status_code=422, detail="stamina_cost_multiplier must be positive"
        )
    if ruleset_id not in _known_ruleset_ids():
        raise HTTPException(status_code=404, detail=f"Unknown ruleset: {ruleset_id}")

    state = _state(request)
    with Session(state.game_engine) as session:
        config = get_or_create_combat_ruleset_config(session, ruleset_id)
        if body.damage_multiplier is not None:
            config.damage_multiplier = body.damage_multiplier
        if body.stamina_cost_multiplier is not None:
            config.stamina_cost_multiplier = body.stamina_cost_multiplier
        session.add(config)
        session.commit()
        session.refresh(config)
        return _serialize(config)
