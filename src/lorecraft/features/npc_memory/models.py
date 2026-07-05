"""NPC memory table definition (Sprint 30.1).

Per-(player, npc) key/value memory, distinct from Player.flags (global) and
Reputation (a single numeric standing). Lets dialogue/quest authors write a
generic key like "helped" that means something different for each NPC,
without pre-naming one flag per NPC pair.
"""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonScalar


class NpcMemory(SQLModel, table=True):
    """One remembered fact a player and an NPC share.

    One row per (player_id, npc_id, key), matching the Reputation/CoinBalance
    "one row per named thing" shape; NpcMemoryRepo owns get-or-create.

    `value` is a scalar (not the fully recursive JsonValue): every real use
    is "remembers this happened" (True) or a simple flag/counter, and a bare
    recursive-union field type trips up pydantic/SQLModel's schema generation
    (unlike JsonObject/JsonValue nested *inside* a dict, which is fine).
    """

    id: int | None = Field(default=None, primary_key=True)
    player_id: str = Field(foreign_key="player.id", index=True)
    npc_id: str = Field(index=True)
    key: str = Field(index=True)
    value: JsonScalar = Field(default=True, sa_column=Column(JSON))
