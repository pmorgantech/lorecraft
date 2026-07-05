"""Admin API router for admin account management (list, create, revoke)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from lorecraft.webui.admin.auth import Superadmin, hash_password
from lorecraft.models.admin import AdminUser

router = APIRouter(tags=["admin"])


def _state(request: Request) -> Any:
    return request.app.state.lorecraft


class _CreateAdminBody(BaseModel):
    username: str
    password: str
    role: str = "observer"


@router.get("/accounts")
async def list_admin_accounts(request: Request, _: Superadmin) -> list[dict[str, Any]]:
    state = _state(request)
    with Session(state.game_engine) as session:
        users = session.exec(select(AdminUser)).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "created_at": u.created_at,
            "revoked_at": u.revoked_at,
            "active": u.revoked_at is None,
        }
        for u in users
    ]


@router.post("/accounts")
async def create_admin_account(
    body: _CreateAdminBody, request: Request, _: Superadmin
) -> dict[str, str]:
    if body.role not in ("observer", "moderator", "world-builder", "superadmin"):
        raise HTTPException(status_code=422, detail=f"Unknown role: {body.role}")
    state = _state(request)
    with Session(state.game_engine) as session:
        existing = session.exec(
            select(AdminUser).where(AdminUser.username == body.username)
        ).first()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Username already exists")
        user = AdminUser(
            id=str(uuid.uuid4()),
            username=body.username,
            password_hash=hash_password(body.password),
            role=body.role,
            created_at=time.time(),
        )
        session.add(user)
        session.commit()
    return {
        "id": user.id,
        "username": body.username,
        "role": body.role,
        "status": "created",
    }


@router.delete("/accounts/{username}")
async def revoke_admin_account(
    username: str, request: Request, token: Superadmin
) -> dict[str, str]:
    if username == token.username:
        raise HTTPException(status_code=422, detail="Cannot revoke your own account")
    state = _state(request)
    with Session(state.game_engine) as session:
        user = session.exec(
            select(AdminUser).where(AdminUser.username == username)
        ).first()
        if user is None:
            raise HTTPException(status_code=404, detail="Admin user not found")
        user.revoked_at = time.time()
        session.add(user)
        session.commit()
    return {"username": username, "status": "revoked"}
