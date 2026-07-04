"""SQLModel table definitions for Lorecraft persistence."""

from lorecraft.models.audit import AuditEvent
from lorecraft.models.changeset import (
    Changeset,
    ChangesetItem,
    ConflictScanResult,
    WorldMigration,
)
from lorecraft.models.combat import CombatSession
from lorecraft.models.interaction import PvpConsent, TradeOffer
from lorecraft.models.items import ItemInstance, ItemStack
from lorecraft.models.player import Player, PlayerStats, SaveSlot
from lorecraft.models.player_auth import PlayerAuth
from lorecraft.models.quest import PlayerQuestProgress, Quest
from lorecraft.models.session import PlayerSession
from lorecraft.models.world import (
    Exit,
    Item,
    NPC,
    Room,
    WorldClock,
    WorldMeta,
)

__all__ = [
    "AuditEvent",
    "Changeset",
    "ChangesetItem",
    "CombatSession",
    "ConflictScanResult",
    "Exit",
    "Item",
    "ItemInstance",
    "ItemStack",
    "NPC",
    "Player",
    "PlayerAuth",
    "PlayerQuestProgress",
    "PlayerSession",
    "PlayerStats",
    "PvpConsent",
    "Quest",
    "Room",
    "SaveSlot",
    "TradeOffer",
    "WorldClock",
    "WorldMeta",
    "WorldMigration",
]
