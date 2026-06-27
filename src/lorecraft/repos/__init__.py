"""Thin SQLModel repository wrappers."""

from lorecraft.repos.audit_repo import AuditRepo
from lorecraft.repos.item_repo import ItemRepo
from lorecraft.repos.npc_repo import NpcRepo
from lorecraft.repos.player_repo import PlayerRepo
from lorecraft.repos.room_repo import RoomRepo

__all__ = [
    "AuditRepo",
    "ItemRepo",
    "NpcRepo",
    "PlayerRepo",
    "RoomRepo",
]
