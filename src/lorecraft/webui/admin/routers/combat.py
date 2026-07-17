"""Admin API router for live-tuning combat ruleset config."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from lorecraft.features.combat.definitions import get_action_registry
from lorecraft.features.combat.models import CombatRulesetConfig
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
