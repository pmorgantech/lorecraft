"""Service container: one place to construct and hold gameplay services."""

from __future__ import annotations

from dataclasses import dataclass, field

from lorecraft.npc.dialogue import DialogueService
from lorecraft.services.character_info import CharacterInfoService
from lorecraft.services.inventory import InventoryService
from lorecraft.services.movement import MovementService
from lorecraft.services.quest import QuestService
from lorecraft.services.save import SaveSlotService


@dataclass
class ServiceContainer:
    """Stateless gameplay services, constructed once and shared everywhere.

    Command modules and event wiring take services from this container
    instead of instantiating their own, so there is exactly one place
    that decides how a service is built.
    """

    movement: MovementService = field(default_factory=MovementService)
    inventory: InventoryService = field(default_factory=InventoryService)
    save: SaveSlotService = field(default_factory=SaveSlotService)
    dialogue: DialogueService = field(default_factory=DialogueService)
    quest: QuestService = field(default_factory=QuestService)
    character_info: CharacterInfoService = field(default_factory=CharacterInfoService)

    @classmethod
    def build(cls) -> ServiceContainer:
        """Construct the default set of gameplay services."""
        return cls()
