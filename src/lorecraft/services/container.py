"""Service container: one place to construct and hold gameplay services."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field

from lorecraft.features.npc.dialogue import DialogueService
from lorecraft.features.bank.service import BankService
from lorecraft.features.character.service import CharacterInfoService
from lorecraft.features.economy.service import EconomyService
from lorecraft.features.exploration.service import ExplorationService
from lorecraft.features.fatigue.service import FatigueService
from lorecraft.features.inventory.service import InventoryService
from lorecraft.features.exploration.journal import JournalService
from lorecraft.features.movement.service import MovementService
from lorecraft.features.quests.service import QuestService
from lorecraft.engine.services.save import SaveSlotService
from lorecraft.features.trading.service import TradeService

# Container fields that belong to a migrated Tier 2 feature, keyed by feature.
# `build()` instantiates these only when the feature is enabled; everything
# else is (for now) always-on because its feature has not been migrated to the
# manifest system yet. The mapping grows as more features are migrated, and the
# whole container becomes feature-driven once features own their services
# (docs/tier_split_refactor.md, step 8).
_FEATURE_GATED_SERVICES: dict[str, type] = {
    "fatigue": FatigueService,
    "economy": EconomyService,
    "bank": BankService,
}


@dataclass
class ServiceContainer:
    """Stateless gameplay services, constructed once and shared everywhere.

    Command modules and event wiring take services from this container
    instead of instantiating their own, so there is exactly one place
    that decides how a service is built.

    Feature-gated services (``fatigue``, ``economy``, ``bank``) are ``None``
    when their Tier 2 feature is disabled; consumers must check before use.
    """

    movement: MovementService = field(default_factory=MovementService)
    inventory: InventoryService = field(default_factory=InventoryService)
    save: SaveSlotService = field(default_factory=SaveSlotService)
    dialogue: DialogueService = field(default_factory=DialogueService)
    quest: QuestService = field(default_factory=QuestService)
    character_info: CharacterInfoService = field(default_factory=CharacterInfoService)
    exploration: ExplorationService = field(default_factory=ExplorationService)
    journal: JournalService = field(default_factory=JournalService)
    # Feature-gated (see _FEATURE_GATED_SERVICES). Default factories keep a bare
    # ServiceContainer() fully populated; build() overrides with None when the
    # owning feature is disabled.
    fatigue: FatigueService | None = field(default_factory=FatigueService)
    economy: EconomyService | None = field(default_factory=EconomyService)
    bank: BankService | None = field(default_factory=BankService)
    trade: TradeService = field(default_factory=TradeService)

    @classmethod
    def build(cls, enabled: Collection[str] | None = None) -> ServiceContainer:
        """Construct the gameplay services.

        Args:
            enabled: Feature keys that are active. Feature-gated services whose
                key is absent are set to ``None``. ``enabled=None`` means "all
                features on" — the behaviour-preserving default used by tests
                and by a default server boot.
        """
        gated: dict[str, object | None] = {}
        for key, service_cls in _FEATURE_GATED_SERVICES.items():
            gated[key] = service_cls() if (enabled is None or key in enabled) else None
        return cls(
            fatigue=gated["fatigue"],  # type: ignore[arg-type]
            economy=gated["economy"],  # type: ignore[arg-type]
            bank=gated["bank"],  # type: ignore[arg-type]
        )
