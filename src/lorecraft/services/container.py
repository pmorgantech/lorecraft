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
from lorecraft.features.follow.service import FollowService
from lorecraft.features.hunts.service import HuntService
from lorecraft.features.inventory.service import InventoryService
from lorecraft.features.exploration.journal import JournalService
from lorecraft.features.marks.service import MarkService
from lorecraft.features.movement.service import MovementService
from lorecraft.features.quests.service import QuestService
from lorecraft.engine.services.save import SaveSlotService
from lorecraft.features.trading.service import TradeService

# Every Tier 2 feature service the container holds, mapped
# ``container_field -> (feature_key, service_cls)``. ``build()`` instantiates a
# field only when its owning feature is enabled; otherwise the field is ``None``
# and consumers must guard before use (command registration and event wiring
# already do — see ``register_all_commands`` and ``main.py``).
#
# Note two field names differ from their feature key: ``dialogue`` is owned by
# the ``npc`` feature, and ``journal`` shares the ``exploration`` feature with
# ``exploration``. Only Tier 1 ``save`` (``engine/services/save``) is not gated —
# it is engine infrastructure, always present (docs/tier_split_refactor.md step 12b).
_FEATURE_GATED_SERVICES: dict[str, tuple[str, type]] = {
    "movement": ("movement", MovementService),
    "inventory": ("inventory", InventoryService),
    "dialogue": ("npc", DialogueService),
    "quest": ("quests", QuestService),
    "character_info": ("character", CharacterInfoService),
    "exploration": ("exploration", ExplorationService),
    "journal": ("exploration", JournalService),
    "trade": ("trading", TradeService),
    "fatigue": ("fatigue", FatigueService),
    "economy": ("economy", EconomyService),
    "bank": ("bank", BankService),
    "follow": ("follow", FollowService),
    "hunts": ("hunts", HuntService),
    "marks": ("marks", MarkService),
}


@dataclass
class ServiceContainer:
    """Stateless gameplay services, constructed once and shared everywhere.

    Command modules and event wiring take services from this container
    instead of instantiating their own, so there is exactly one place
    that decides how a service is built.

    Every Tier 2 feature service (see ``_FEATURE_GATED_SERVICES``) is ``None``
    when its owning feature is disabled; consumers must check before use. Only
    the Tier 1 ``save`` service is unconditionally present.
    """

    save: SaveSlotService = field(default_factory=SaveSlotService)
    # Feature-gated (see _FEATURE_GATED_SERVICES). Default factories keep a bare
    # ServiceContainer() fully populated; build() overrides with None when the
    # owning feature is disabled.
    movement: MovementService | None = field(default_factory=MovementService)
    inventory: InventoryService | None = field(default_factory=InventoryService)
    dialogue: DialogueService | None = field(default_factory=DialogueService)
    quest: QuestService | None = field(default_factory=QuestService)
    character_info: CharacterInfoService | None = field(
        default_factory=CharacterInfoService
    )
    exploration: ExplorationService | None = field(default_factory=ExplorationService)
    journal: JournalService | None = field(default_factory=JournalService)
    fatigue: FatigueService | None = field(default_factory=FatigueService)
    economy: EconomyService | None = field(default_factory=EconomyService)
    bank: BankService | None = field(default_factory=BankService)
    trade: TradeService | None = field(default_factory=TradeService)
    follow: FollowService | None = field(default_factory=FollowService)
    hunts: HuntService | None = field(default_factory=HuntService)
    marks: MarkService | None = field(default_factory=MarkService)

    @classmethod
    def build(cls, enabled: Collection[str] | None = None) -> ServiceContainer:
        """Construct the gameplay services.

        Args:
            enabled: Feature keys that are active. Feature-gated services whose
                owning feature is absent are set to ``None``. ``enabled=None``
                means "all features on" — the behaviour-preserving default used
                by tests and by a default server boot.
        """
        kwargs: dict[str, object | None] = {}
        for container_field, (
            feature_key,
            service_cls,
        ) in _FEATURE_GATED_SERVICES.items():
            active = enabled is None or feature_key in enabled
            kwargs[container_field] = service_cls() if active else None
        return cls(**kwargs)  # type: ignore[arg-type]
