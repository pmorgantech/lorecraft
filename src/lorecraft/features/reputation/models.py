"""Reputation/standing table definition (Sprint 24.3)."""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class Reputation(SQLModel, table=True):
    """A player's standing with one NPC or faction.

    One row per (player_id, target_type, target_id); ReputationRepo owns
    get-or-create semantics, matching the CoinBalance/Meter "one row per
    named thing" shape.
    """

    id: int | None = Field(default=None, primary_key=True)
    player_id: str = Field(foreign_key="player.id", index=True)
    target_type: str = Field(index=True)  # "npc" | "faction"
    target_id: str = Field(index=True)
    standing: int = 0
