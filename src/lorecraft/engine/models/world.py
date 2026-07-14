"""World state table definitions."""

from __future__ import annotations

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

from lorecraft.types import JsonObject


class Room(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    map_x: int
    map_y: int
    map_z: int = 0  # floor/level; minimap filters to current_room.map_z (Sprint 66)
    # Sprint 71.2: the old conflated `area_id` split into two orthogonal fields.
    # `zone` — geographic/thematic, user-facing; 4 values (ashmoore, cogsworth,
    # whisperwood, port_veridian). Powers zone-qualified teleport addressing,
    # rooms_in_area, admin World grouping, npc_ai wander bounds, weather fronts,
    # and economy region pricing.
    zone: str | None = None
    # `room_type` — universal room-kind taxonomy (cave|wilderness|town, growing);
    # what kind of room it is, applied across all zones (not per-zone).
    room_type: str | None = None
    is_active: bool = True
    fallback_room_id: str | None = None
    flags: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    disabled_commands: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    light_level: int = 1
    version: int = 1
    terrain: str = (
        "normal"  # affects travel gating; see game/terrain.py's TerrainRegistry
    )
    safe_rest: bool = False  # inns/camps: `sleep` here is reliable, never interrupted
    indoor: bool = (
        False  # interiors (vaults, cellars): weather narration is suppressed here
    )
    loot_table: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    ambient_events: list[JsonObject] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    # Declarative on/when/do trigger hooks (scripting engine A2): each is a raw
    # {on, when?, do} dict, parsed+validated by scripting.triggers.parse_trigger at load
    # and bound to the live event bus by scripting_wiring.build_trigger_service.
    triggers: list[JsonObject] = Field(default_factory=list, sa_column=Column(JSON))


class Exit(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    room_id: str = Field(foreign_key="room.id", index=True)
    direction: str
    target_room_id: str
    locked: bool = False
    key_item_id: str | None = None
    hidden: bool = False
    condition_flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class Item(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    takeable: bool = True
    tradeable: bool = True
    bound: bool = False  # Sprint 16: soulbound items can't be dropped/sold/traded (enforced by Tier 2 rules)
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    usable_with: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    loot_table: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    slot: str | None = (
        None  # equipment slot key (head, hands, main_hand, etc.); None = not equippable
    )
    wearable: bool = False  # worn (armor/clothing) vs. wielded (weapon/tool/light)
    weight: float = 0.0  # item weight; drives encumbrance
    quality: str = (
        "common"  # common|fine|superior|rare|legendary — affects value & trade
    )
    max_durability: int | None = (
        None  # None = indestructible; else tracked per-instance via component
    )
    light: int = 0  # light radius/level this item emits when equipped & lit
    capacity: float | None = (
        None  # if set, item is a container holding up to capacity weight
    )
    effects: list[JsonObject] = Field(
        default_factory=list, sa_column=Column(JSON)
    )  # effect descriptors (registry-driven)
    value: int = (
        0  # base coin value; shop prices derive from value * quality (Sprint 28)
    )
    category: str | None = (
        None  # trade category (food, supplies, trade_good, ...); gates Shop.buys_categories
    )
    # Sprint 30.2: mechanism puzzles (levers, dials). Non-empty states = item
    # gets the "mechanism" component; `activate`/`turn`/`pull` cycles through
    # them in order. See game/standard_mechanisms.py.
    mechanism_states: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # Side effects (any handler on npc/side_effects.py's registry) applied
    # once when the mechanism transitions INTO the named state -- e.g.
    # {"3": {"set_flags": ["vault_unlocked"]}} for a dial solved at "3".
    mechanism_side_effects: JsonObject = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    # Side effects applied on a successful `use <this> with <other>` (Sprint
    # 30.2 item-combination puzzles), keyed by the other item's id. Checked
    # in both directions -- see services/inventory.py's use_item().
    combination_side_effects: JsonObject = Field(
        default_factory=dict, sa_column=Column(JSON)
    )
    # Context-attached verbs (Sprint 55): verb -> {aliases, help, say,
    # side_effects, requires?}. Each becomes a command available only when this
    # item is present/held (gated object_present:<id>); see features/context_commands.
    context_commands: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))


class WorldMeta(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    schema_version: int = 1
    engine_version: str = "0.1.0"


class WorldClock(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_epoch: float
    real_epoch: float
    time_ratio: float = 60.0
    paused: bool = False
    current_hour: int = 8
    current_minute: int = 0
    current_day: int = 1
    current_season: str = "spring"
    weather: str = "clear"


class NPC(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    current_room_id: str
    home_room_id: str
    dialogue_tree_id: str
    behavior: str = "defensive"
    # Definitional base (Sprint 19); runtime hp is Meter("npc", id, "hp") — current_hp
    # is deleted, not deprecated.
    max_hp: int = 50
    loot_table: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    respawn_seconds: int | None = 300
    schedule: list[JsonObject] = Field(default_factory=list, sa_column=Column(JSON))
    # Context-attached verbs (Sprint 55): verb -> {aliases, help, say,
    # side_effects, requires?}, available only when this NPC is in the room
    # (gated npc_present:<id>); see features/context_commands.
    context_commands: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    # Declarative on/when/do trigger hooks (scripting engine A2): raw {on, when?, do}
    # dicts, parsed by scripting.triggers.parse_trigger and bound to the bus at load.
    triggers: list[JsonObject] = Field(default_factory=list, sa_column=Column(JSON))
    # Autonomous agency config (scripting engine A3): {mode: wander|patrol, move_every,
    # area?, route?}. Empty = passive (the default). Driven by features/npc_ai.
    ai: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    # Escort quests (Sprint 68): the player this NPC is currently following, if
    # any. Set/cleared by the "start_escort"/"end_escort" side effects
    # (features/follow/conditions.py); driven by PLAYER_MOVED the same way
    # player-follow is, but DB-backed (not FollowService's in-memory dict) so
    # the "npc_following" quest condition can read it without needing a
    # shared service reference. See features/follow/service.py.
    following_player_id: str | None = None
