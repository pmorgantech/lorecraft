"""Player credential binding table definition."""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class PlayerAuth(SQLModel, table=True):
    """Provider-agnostic credential binding for a `Player`.

    `provider`/`provider_subject` generalize beyond local username+password
    (e.g. `provider="google"`, `provider_subject=<google_sub>`) so OAuth can
    be added later without changing this shape. `credential_hash` is only
    used by the `local` provider.
    """

    id: int | None = Field(default=None, primary_key=True)
    player_id: str = Field(foreign_key="player.id", unique=True, index=True)
    provider: str = "local"
    provider_subject: str = Field(index=True)
    credential_hash: str | None = None
    created_at: float
    last_login_at: float
