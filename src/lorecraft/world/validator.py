"""Validation for authored world YAML documents."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from lorecraft.features.weather.handlers import WEATHER_TABLE

KNOWN_WEATHER = frozenset(w for states in WEATHER_TABLE.values() for w in states)


class WorldValidationError(ValueError):
    """Raised when authored world data is structurally invalid."""


class ExitData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: str
    target_room_id: str
    locked: bool = False
    key_item_id: str | None = None
    hidden: bool = False
    condition_flags: list[str] = Field(default_factory=list)


class RoomData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    map_x: int
    map_y: int
    map_z: int = 0
    zone: str | None = None
    room_type: str | None = None
    is_active: bool = True
    fallback_room_id: str | None = None
    flags: dict[str, object] = Field(default_factory=dict)
    disabled_commands: list[str] = Field(default_factory=list)
    light_level: int = 1
    version: int = 1
    terrain: str = "normal"
    safe_rest: bool = False
    indoor: bool = False
    exits: list[ExitData] = Field(default_factory=list)
    # Declarative on/when/do trigger hooks (scripting engine A2). Raw dicts here; validated
    # against the vocabulary catalog by `parse_trigger` at world load (fail-closed).
    triggers: list[dict[str, object]] = Field(default_factory=list)


class ContextCommandData(BaseModel):
    """One object-scoped verb (Sprint 55). Declared on an item or NPC; becomes
    a command available only when that object is present, firing `side_effects`
    through the shared side-effect registry."""

    model_config = ConfigDict(extra="forbid")

    aliases: list[str] = Field(default_factory=list)
    help: str = ""
    say: str = ""  # message shown to the actor when the verb fires
    side_effects: dict[str, object] = Field(default_factory=dict)
    requires: str | None = (
        None  # optional extra condition string, e.g. "actor_has_flag:x"
    )

    @model_validator(mode="after")
    def _does_something(self) -> "ContextCommandData":
        if not self.side_effects and not self.say:
            raise ValueError("a context command must set `say` and/or `side_effects`")
        return self


class ItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    takeable: bool = True
    tradeable: bool = True
    bound: bool = False
    aliases: list[str] = Field(default_factory=list)
    usable_with: list[str] = Field(default_factory=list)
    loot_table: dict[str, object] = Field(default_factory=dict)
    slot: str | None = None
    wearable: bool = False
    weight: float = 0.0
    quality: str = "common"
    max_durability: int | None = None
    light: int = 0
    capacity: float | None = None
    effects: list[dict[str, object]] = Field(default_factory=list)
    value: int = 0
    category: str | None = None
    mechanism_states: list[str] = Field(default_factory=list)
    mechanism_side_effects: dict[str, dict[str, object]] = Field(default_factory=dict)
    combination_side_effects: dict[str, dict[str, object]] = Field(default_factory=dict)
    context_commands: dict[str, ContextCommandData] = Field(default_factory=dict)


class RoomItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str
    item_id: str
    quantity: int = 1


class NpcScheduleEntryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_hour: int
    target_room_id: str


class ShopStockData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    quantity: int = 0  # -1 = unlimited
    restock_to: int = 0
    restock_every_ticks: int = 0


class ShopData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    buys_categories: list[str] = Field(default_factory=list)
    sell_ratio: float = 0.5
    region_mult: float = 1.0
    starting_coins: int = 500
    stock: list[ShopStockData] = Field(default_factory=list)


class BankBranchData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str


class NpcData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    home_room_id: str
    current_room_id: str | None = None
    dialogue_tree_id: str = ""
    behavior: str = "defensive"
    max_hp: int = 50
    schedule: list[NpcScheduleEntryData] = Field(default_factory=list)
    loot_table: dict[str, object] = Field(default_factory=dict)
    shop: ShopData | None = None
    bank: BankBranchData | None = None
    context_commands: dict[str, ContextCommandData] = Field(default_factory=dict)
    # Declarative on/when/do trigger hooks (scripting engine A2); validated by `parse_trigger`.
    triggers: list[dict[str, object]] = Field(default_factory=list)
    # Autonomous agency config (scripting engine A3): {mode: wander|patrol, move_every, ...}.
    ai: dict[str, object] = Field(default_factory=dict)


class DialogueChoiceData(BaseModel):
    # extra="allow", unlike the rest of the world schema: the dialogue engine's
    # choice-visibility contract is *open-keyed* — any extra key naming a
    # registered dialogue-condition predicate (features/npc/dialogue_conditions,
    # e.g. Sprint 54's `moon_phase_is`/`tide_is`) gates the choice, and unknown
    # keys are ignored at runtime. Forbidding extras here would reject exactly
    # the content the feature-registration pattern invites.
    model_config = ConfigDict(extra="allow")

    label: str
    next_node: str | None = None
    actor_has_flag: list[str] = Field(default_factory=list)
    actor_lacks_flag: list[str] = Field(default_factory=list)
    side_effects: dict[str, object] = Field(default_factory=dict)


class DialogueNodeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    side_effects: dict[str, object] = Field(default_factory=dict)
    choices: list[DialogueChoiceData] = Field(default_factory=list)


class DialogueTreeData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    root_node: str
    nodes: dict[str, DialogueNodeData]


class QuestConditionData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    flag: str | None = None  # also doubles as the memory key for npc_remembers
    room_id: str | None = None
    item_id: str | None = None
    npc_id: str | None = None  # required for type: npc_remembers


class QuestBranchData(BaseModel):
    """One outcome of a branching stage (Sprint 30.1): evaluated in list
    order, first branch whose `conditions` all pass wins. `side_effects` are
    that branch's consequence (any npc/side_effects.py handler -- set_flags,
    give_item, adjust_reputation, remember, ...); `next_stage` is the stage
    id to move to, or null to complete the quest."""

    model_config = ConfigDict(extra="forbid")

    conditions: list[QuestConditionData] = Field(default_factory=list)
    next_stage: str | None = None
    side_effects: dict[str, object] = Field(default_factory=dict)


class QuestTimeoutData(BaseModel):
    """Sprint 30.2: what happens if a stage's `timeout_ticks` elapses before
    the player progresses it (QuestTimerService). `next_stage: null` fails
    the quest (status becomes "failed", not "completed")."""

    model_config = ConfigDict(extra="forbid")

    next_stage: str | None = None
    message: str = ""
    set_flags: dict[str, bool] = Field(default_factory=dict)


class QuestStageData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str = ""
    conditions: list[QuestConditionData] = Field(default_factory=list)
    completion_flags: dict[str, object] = Field(default_factory=dict)
    rewards: dict[str, object] = Field(default_factory=dict)
    branches: list[QuestBranchData] = Field(default_factory=list)
    # A stage reached via a branch jump may sit at any array index, not
    # necessarily last -- `terminal: true` completes the quest as soon as
    # this stage's own `conditions` pass, instead of falling through to
    # `stages[idx+1]` (the legacy, array-order-only completion rule, still
    # the default for stages that were never a branch target).
    terminal: bool = False
    timeout_ticks: float | None = None
    on_timeout: QuestTimeoutData | None = None


class QuestData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str = ""
    stages: list[QuestStageData] = Field(default_factory=list)


class RegionPricingData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone: str
    region_mult: float = 1.0
    bias: dict[str, float] = Field(default_factory=dict)  # item_id -> price multiplier


class EconomyConfigData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = "coins"
    regions: list[RegionPricingData] = Field(default_factory=list)


class ProgressionConfigData(BaseModel):
    """`world.yaml` `progression:` section — XP-curve params + per-level rewards.

    All four are required: the game-balance numbers live here (authored, data-
    driven), never as Python defaults in the engine.
    """

    model_config = ConfigDict(extra="forbid")

    base: int
    step: int
    coins_per_level: int
    skill_points_per_level: int


class TransitStopData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str
    sequence: int
    dwell_ticks: int = 5
    travel_ticks: int = 20
    boarding: bool = True


class TransitLineData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    mode: str
    service_type: str = "local"
    vehicle_room_id: str | None = None
    ticket_item_id: str | None = None
    ticket_consumed: bool = True
    reverses: bool = True
    loop: bool = False
    animate_minimap: bool = True
    weather_sensitive: bool = False
    blocking_weather: list[str] = Field(default_factory=list)
    stops: list[TransitStopData] = Field(default_factory=list)


class TransitConfigData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[TransitLineData] = Field(default_factory=list)


class WorldDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rooms: list[RoomData] = Field(default_factory=list)
    items: list[ItemData] = Field(default_factory=list)
    room_items: list[RoomItemData] = Field(default_factory=list)
    npcs: list[NpcData] = Field(default_factory=list)
    dialogue_trees: list[DialogueTreeData] = Field(default_factory=list)
    quests: list[QuestData] = Field(default_factory=list)
    economy: EconomyConfigData | None = None
    progression: ProgressionConfigData | None = None
    transit: TransitConfigData | None = None


def _validate_quest_condition(
    quest_id: str,
    stage_id: str,
    cond: QuestConditionData,
    room_ids: set[str],
    item_ids: set[str],
    npc_ids: set[str],
    errors: list[str],
) -> None:
    if cond.room_id is not None and cond.room_id not in room_ids:
        errors.append(
            f"quest {quest_id} stage {stage_id} condition references missing "
            f"room {cond.room_id}"
        )
    if cond.item_id is not None and cond.item_id not in item_ids:
        errors.append(
            f"quest {quest_id} stage {stage_id} condition references missing "
            f"item {cond.item_id}"
        )
    if cond.type == "npc_remembers":
        if cond.npc_id is None or cond.npc_id not in npc_ids:
            errors.append(
                f"quest {quest_id} stage {stage_id} npc_remembers condition "
                f"references missing npc {cond.npc_id!r}"
            )
        if cond.flag is None:
            errors.append(
                f"quest {quest_id} stage {stage_id} npc_remembers condition "
                "needs a 'flag' (the memory key)"
            )


def _validate_open_timed_passage(
    item_id: str, state_name: str, data: object
) -> list[str]:
    """Shape-check an `open_timed_passage` mechanism side effect (Sprint 39.3).

    Catches authoring errors in a plate/lever that opens a timed gate; the
    handler needs a non-empty `direction` and a positive `ticks`. (Whether the
    direction resolves to a real exit is a runtime concern — the item's room is
    not known statically.)
    """
    where = f"item {item_id} mechanism_side_effects[{state_name!r}] open_timed_passage"
    if not isinstance(data, dict):
        return [f"{where} must be a mapping with 'direction' and 'ticks'"]
    errors: list[str] = []
    direction = data.get("direction")
    if not isinstance(direction, str) or not direction.strip():
        errors.append(f"{where} needs a non-empty 'direction'")
    ticks = data.get("ticks")
    if isinstance(ticks, bool) or not isinstance(ticks, (int, float)) or ticks <= 0:
        errors.append(f"{where} needs a positive numeric 'ticks'")
    return errors


def validate_world_document(data: object) -> WorldDocument:
    try:
        document = WorldDocument.model_validate(data)
    except ValidationError as exc:
        raise WorldValidationError(str(exc)) from exc

    errors: list[str] = []
    room_ids = {room.id for room in document.rooms}
    item_ids = {item.id for item in document.items}
    dialogue_tree_ids = {dt.id for dt in document.dialogue_trees}
    npc_ids = {npc.id for npc in document.npcs}

    for room in document.rooms:
        if room.fallback_room_id is not None and room.fallback_room_id not in room_ids:
            errors.append(
                f"room {room.id} references missing fallback room {room.fallback_room_id}"
            )
        for exit_ in room.exits:
            if exit_.target_room_id not in room_ids:
                errors.append(
                    f"room {room.id} exit {exit_.direction} references missing room "
                    f"{exit_.target_room_id}"
                )
            if exit_.key_item_id is not None and exit_.key_item_id not in item_ids:
                errors.append(
                    f"room {room.id} exit {exit_.direction} references missing key item "
                    f"{exit_.key_item_id}"
                )

    for room_item in document.room_items:
        if room_item.room_id not in room_ids:
            errors.append(f"room item references missing room {room_item.room_id}")
        if room_item.item_id not in item_ids:
            errors.append(f"room item references missing item {room_item.item_id}")
        if room_item.quantity < 1:
            errors.append(
                f"room item {room_item.item_id} in {room_item.room_id} must have quantity >= 1"
            )

    for npc in document.npcs:
        if npc.home_room_id not in room_ids:
            errors.append(
                f"npc {npc.id} references missing home_room_id {npc.home_room_id}"
            )
        if npc.current_room_id and npc.current_room_id not in room_ids:
            errors.append(
                f"npc {npc.id} references missing current_room_id {npc.current_room_id}"
            )
        if npc.dialogue_tree_id and npc.dialogue_tree_id not in dialogue_tree_ids:
            errors.append(
                f"npc {npc.id} references missing dialogue_tree_id {npc.dialogue_tree_id}"
            )
        for entry in npc.schedule:
            if entry.target_room_id not in room_ids:
                errors.append(
                    f"npc {npc.id} schedule references missing room {entry.target_room_id}"
                )
        if npc.shop is not None:
            for stock in npc.shop.stock:
                if stock.item_id not in item_ids:
                    errors.append(
                        f"npc {npc.id} shop stock references missing item {stock.item_id}"
                    )

    for item in document.items:
        if item.mechanism_states and len(item.mechanism_states) < 2:
            errors.append(
                f"item {item.id} mechanism_states must have at least 2 states"
            )
        for state_name, side_effects in item.mechanism_side_effects.items():
            if state_name not in item.mechanism_states:
                errors.append(
                    f"item {item.id} mechanism_side_effects references unknown "
                    f"state {state_name!r} (not in mechanism_states)"
                )
            open_passage = (
                side_effects.get("open_timed_passage")
                if isinstance(side_effects, dict)
                else None
            )
            if open_passage is not None:
                errors.extend(
                    _validate_open_timed_passage(item.id, state_name, open_passage)
                )
        for other_item_id in item.combination_side_effects:
            if other_item_id not in item_ids:
                errors.append(
                    f"item {item.id} combination_side_effects references missing "
                    f"item {other_item_id}"
                )

    for quest in document.quests:
        stage_ids = {stage.id for stage in quest.stages}
        if len(stage_ids) != len(quest.stages):
            errors.append(f"quest {quest.id} has duplicate stage ids")
        for stage in quest.stages:
            for cond in stage.conditions:
                _validate_quest_condition(
                    quest.id, stage.id, cond, room_ids, item_ids, npc_ids, errors
                )
            for branch in stage.branches:
                if branch.next_stage is not None and branch.next_stage not in stage_ids:
                    errors.append(
                        f"quest {quest.id} stage {stage.id} branch references "
                        f"unknown next_stage {branch.next_stage!r}"
                    )
                for cond in branch.conditions:
                    _validate_quest_condition(
                        quest.id, stage.id, cond, room_ids, item_ids, npc_ids, errors
                    )
            if stage.on_timeout is not None:
                if stage.timeout_ticks is None:
                    errors.append(
                        f"quest {quest.id} stage {stage.id} has on_timeout but no "
                        "timeout_ticks"
                    )
                if (
                    stage.on_timeout.next_stage is not None
                    and stage.on_timeout.next_stage not in stage_ids
                ):
                    errors.append(
                        f"quest {quest.id} stage {stage.id} on_timeout references "
                        f"unknown next_stage {stage.on_timeout.next_stage!r}"
                    )

    if document.economy is not None:
        zones = {room.zone for room in document.rooms if room.zone is not None}
        for region in document.economy.regions:
            if region.zone not in zones:
                errors.append(f"economy region references missing zone {region.zone}")
            for biased_item_id in region.bias:
                if biased_item_id not in item_ids:
                    errors.append(
                        f"economy region {region.zone} bias references missing item {biased_item_id}"
                    )

    if document.transit is not None:
        rooms_by_id = {room.id: room for room in document.rooms}
        for line in document.transit.lines:
            if line.vehicle_room_id is not None:
                vehicle_room = rooms_by_id.get(line.vehicle_room_id)
                if vehicle_room is None:
                    errors.append(
                        f"transit line {line.id!r} references missing vehicle_room_id {line.vehicle_room_id!r}"
                    )
                elif vehicle_room.exits:
                    errors.append(
                        f"transit line {line.id!r} vehicle_room {line.vehicle_room_id!r} "
                        "must have no static exits (board/disembark only)"
                    )
            if line.ticket_item_id is not None and line.ticket_item_id not in item_ids:
                errors.append(
                    f"transit line {line.id!r} references missing ticket_item_id {line.ticket_item_id!r}"
                )
            for weather in line.blocking_weather:
                if weather not in KNOWN_WEATHER:
                    errors.append(
                        f"transit line {line.id!r} blocking_weather has unknown state {weather!r}"
                    )

            sequences = sorted(stop.sequence for stop in line.stops)
            if sequences != list(range(len(sequences))):
                errors.append(
                    f"transit line {line.id!r} stop sequences must be contiguous from 0 "
                    f"(got {sequences})"
                )
            for stop in line.stops:
                if stop.room_id not in room_ids:
                    errors.append(
                        f"transit line {line.id!r} stop references missing room {stop.room_id!r}"
                    )
            if line.service_type == "express":
                boarding_stops = sum(1 for stop in line.stops if stop.boarding)
                if boarding_stops < 2:
                    errors.append(
                        f"transit line {line.id!r} is express but has fewer than 2 boarding stops"
                    )

    if errors:
        raise WorldValidationError("; ".join(errors))

    return document
