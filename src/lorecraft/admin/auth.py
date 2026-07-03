"""Admin JWT authentication and role enforcement."""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlmodel import Session, select

from lorecraft.models.admin import AdminUser

log = logging.getLogger(__name__)

ROLE_LEVELS: dict[str, int] = {
    "observer": 0,
    "moderator": 1,
    "world-builder": 2,
    "superadmin": 3,
}

_ALGORITHM = "HS256"
_bearer = HTTPBearer()


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256, no extra deps)
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
    return f"{salt}:{digest.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        salt, stored_hex = stored.split(":", 1)
        digest = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 260_000)
        return secrets.compare_digest(digest.hex(), stored_hex)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenPayload:
    username: str
    role: str
    token_type: str  # "access" | "refresh"


def create_token(
    username: str,
    role: str,
    secret: str,
    ttl_seconds: int,
    token_type: str,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": username,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + ttl_seconds,
        # Unique per call so two tokens issued within the same second (e.g.
        # back-to-back refresh-token rotations) never collide byte-for-byte.
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_token(token: str, secret: str) -> TokenPayload:
    """Raise jwt.InvalidTokenError (or subclass) on any failure."""
    payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    return TokenPayload(
        username=payload["sub"],
        role=payload["role"],
        token_type=payload["type"],
    )


def has_role(actual: str, required: str) -> bool:
    return ROLE_LEVELS.get(actual, -1) >= ROLE_LEVELS.get(required, 999)


# ---------------------------------------------------------------------------
# FastAPI dependency helpers
# ---------------------------------------------------------------------------


def _lorecraft_state(request: Request) -> Any:
    return request.app.state.lorecraft


async def get_current_admin(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
) -> TokenPayload:
    state = _lorecraft_state(request)
    try:
        token = decode_token(creds.credentials, state.settings.admin_jwt_secret)
    except jwt.InvalidTokenError as e:
        log.error("admin_token_decode_failed: %s", str(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token") from e
    if token.token_type != "access":
        raise HTTPException(status_code=401, detail="Expected access token")
    return token


async def _require_observer(
    admin: Annotated[TokenPayload, Depends(get_current_admin)],
) -> TokenPayload:
    return admin


async def _require_moderator(
    admin: Annotated[TokenPayload, Depends(get_current_admin)],
) -> TokenPayload:
    if not has_role(admin.role, "moderator"):
        raise HTTPException(status_code=403, detail="Requires moderator role")
    return admin


async def _require_world_builder(
    admin: Annotated[TokenPayload, Depends(get_current_admin)],
) -> TokenPayload:
    if not has_role(admin.role, "world-builder"):
        raise HTTPException(status_code=403, detail="Requires world-builder role")
    return admin


async def _require_superadmin(
    admin: Annotated[TokenPayload, Depends(get_current_admin)],
) -> TokenPayload:
    if not has_role(admin.role, "superadmin"):
        raise HTTPException(status_code=403, detail="Requires superadmin role")
    return admin


Observer = Annotated[TokenPayload, Depends(_require_observer)]
Moderator = Annotated[TokenPayload, Depends(_require_moderator)]
WorldBuilder = Annotated[TokenPayload, Depends(_require_world_builder)]
Superadmin = Annotated[TokenPayload, Depends(_require_superadmin)]


# ---------------------------------------------------------------------------
# Auth router: /admin/auth/token  and  /admin/auth/refresh
# ---------------------------------------------------------------------------


class _LoginBody(BaseModel):
    username: str
    password: str


class _RefreshBody(BaseModel):
    refresh_token: str


auth_router = APIRouter(prefix="/auth", tags=["admin-auth"])


@auth_router.post("/token")
async def login(body: _LoginBody, request: Request) -> dict[str, str | int]:
    state = _lorecraft_state(request)
    with Session(state.game_engine) as session:
        user = session.exec(
            select(AdminUser).where(AdminUser.username == body.username)
        ).first()
    if user is None or user.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    secret = state.settings.admin_jwt_secret
    access_ttl: int = state.settings.admin_jwt_access_ttl
    refresh_ttl: int = state.settings.admin_jwt_refresh_ttl
    return {
        "access_token": create_token(
            user.username, user.role, secret, access_ttl, "access"
        ),
        "refresh_token": create_token(
            user.username, user.role, secret, refresh_ttl, "refresh"
        ),
        "token_type": "bearer",
        "expires_in": access_ttl,
    }


@auth_router.post("/refresh")
async def refresh(body: _RefreshBody, request: Request) -> dict[str, str | int]:
    state = _lorecraft_state(request)
    secret = state.settings.admin_jwt_secret
    try:
        token = decode_token(body.refresh_token, secret)
    except jwt.InvalidTokenError as e:
        log.error("refresh_token_decode_failed: %s", str(e))
        raise HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        ) from e
    if token.token_type != "refresh":
        raise HTTPException(status_code=401, detail="Expected refresh token")
    access_ttl: int = state.settings.admin_jwt_access_ttl
    return {
        "access_token": create_token(
            token.username, token.role, secret, access_ttl, "access"
        ),
        "token_type": "bearer",
        "expires_in": access_ttl,
    }
