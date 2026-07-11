# Multiplayer Text Adventure Engine — Comprehensive Implementation Guide

> **Purpose:** This document is a complete, authoritative implementation reference synthesized from all design sessions. It is intended as the primary handoff artifact for Claude Code / Codex to begin building the engine. Read it fully before writing any code.
>
> **Implementation status:** See [`roadmap.md`](roadmap.md) — the single source of truth for
> what's done and what's next, with per-sprint task tables and current status.

---

## Table of Contents

1. [Project Identity & Philosophy](#1-project-identity--philosophy)
2. [Technology Stack](#2-technology-stack)
3. [Architectural Theme (Core Principle)](#3-architectural-theme-core-principle)
4. [Project Structure](#4-project-structure)
5. [Core Patterns](#5-core-patterns)
6. [Database Schema](#6-database-schema)
7. [Subsystem: World Clock & Scheduler](#7-subsystem-world-clock--scheduler)
8. [Subsystem: Event Bus](#8-subsystem-event-bus)
9. [Subsystem: Command System](#9-subsystem-command-system)
10. [Subsystem: Rule Engine](#10-subsystem-rule-engine)
11. [Subsystem: Service Layer](#11-subsystem-service-layer)
12. [Subsystem: Audit Log](#12-subsystem-audit-log)
13. [Subsystem: NPC System](#13-subsystem-npc-system)
14. [Subsystem: Quest Engine](#14-subsystem-quest-engine)
15. [Subsystem: Combat System](#15-subsystem-combat-system)
16. [Subsystem: Weather & Seasons](#16-subsystem-weather--seasons)
17. [Subsystem: Save Slots & Death/Respawn](#17-subsystem-save-slots--deathrespawn)
18. [Subsystem: Disconnect Handling](#18-subsystem-disconnect-handling)
19. [Subsystem: World Versioning & Changesets](#19-subsystem-world-versioning--changesets)
20. [Subsystem: Player Interaction (Trading & PvP)](#20-subsystem-player-interaction-trading--pvp)
21. [Subsystem: Admin & Authoring Tools](#21-subsystem-admin--authoring-tools)
22. [Frontend UI](#22-frontend-ui)
23. [WebSocket Protocol](#23-websocket-protocol)
24. [World Authoring (YAML)](#24-world-authoring-yaml)
25. [Testing Infrastructure](#25-testing-infrastructure)
26. [Transaction & Event Lifecycle](#26-transaction--event-lifecycle)
27. [Intentionally Deferred](#27-intentionally-deferred)
28. [Build Order Recommendation](#28-build-order-recommendation)

---

## 1. Project Identity & Philosophy

A persistent, multiplayer browser-based text adventure engine. Players connect via WebSocket to a shared, living world. They issue text commands and see results in a multi-panel browser UI. The world runs on real time whether players are connected or not.

**Core tenets:**
- Single authoritative process: one game server, one event bus, one scheduler, one world clock, one SQLite DB. No premature horizontal scaling.
- Never tell clients something happened until the database says it happened.
- World state is shared. Player state is per-player. These are never conflated.
- The audit log is the canonical history of the world. Everything else is derived from it or consistent with it.
- Complexity is deferred until it's proven necessary. The architecture should be easy to extend, not pre-extended.

**Must-haves before building gameplay:**
- Disconnect handling
- Transaction model
- Rule engine
- Scheduler design
- Event bus with separate notification and work events
- Service layer boundaries
- Audit log schema

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.11+ |
| Web framework | FastAPI |
| Real-time | WebSockets (FastAPI native) |
| Database ORM | SQLModel (Pydantic + SQLAlchemy) |
| Database | SQLite (single file, single process) |
| World authoring | YAML files seeded into SQLite |
| Frontend | Vanilla JS + Tailwind CSS (CDN, no build step) |
| Admin TUI | Textual (Python terminal UI library) |
| Testing | pytest + in-memory SQLite |

---

## 3. Architectural Theme (Core Principle)

Every operation in the engine maps to exactly one of these five layers. When in doubt about where code belongs, consult this table.

| Layer | Responsibility | Examples |
|---|---|---|
| **Services** | Perform the work | `MovementService.move()`, `InventoryService.take_item()` |
| **Rules** | Decide whether and how work may proceed | `RuleEngine.check("take_item", ctx)` |
| **Transactions** | Explain why work happened; tie together all resulting effects | `TransactionContext` with `transaction_id`, `correlation_id` |
| **Events** | Notify the rest of the engine about what occurred | `bus.emit(GameEvent.ITEM_TAKEN, ...)` |
| **Scheduler** | Decide when future work should occur | `scheduler.schedule("npc_move", at=next_tick)` |

---

## 4. Project Structure

The codebase is organized on **three axes** (the tier split, CHANGELOG 0.15.0–0.32.0; design in [`tier_split_refactor.md`](tier_split_refactor.md), boundary in [`architecture_tiers.md`](architecture_tiers.md)):

- **Tier 1 — `engine/`**: content-agnostic primitives. Runs headless; imports only `engine.*` and `lorecraft.types` — never `features/` or `webui/` (enforced by `tests/unit/test_tier_boundaries.py`).
- **Tier 2 — `features/`**: 24 optional, self-contained feature packages, each owning its own `models`/`service`/`repo`/`commands`/`conditions`/…, declared by a `FeatureManifest`. Discovered via `discover_features()` and gated by the enabled set.
- **Web — `webui/`**: the delivery hosts (`player/` HTMX UI + `admin/` console) that compose an engine + features. A feature may optionally ship a `presentation.py` picked up by the web host.
- **Composition root** (`main.py`, `commands/`, `services/container.py`, `state.py`) may import features and web; the engine may not import any of them.

```
.
├── src/
│   └── lorecraft/
│       ├── main.py                    # FastAPI app + startup lifespan (composition root)
│       ├── state.py                   # AppState (services, registries, web_host)
│       ├── config.py  db.py  errors.py  types.py  observability.py  analytics.py
│       │
│       ├── engine/                    # ── Tier 1: content-agnostic primitives (headless)
│       │   ├── game/                  # context, engine, parser, registry, events, rules,
│       │   │                          #   rng, checks, modifiers, meters, effects, traits,
│       │   │                          #   components, holders, broadcast, connection_manager
│       │   ├── models/                # player, world, items, meters, ledger, mobile,
│       │   │                          #   audit, session, scheduler, player_auth
│       │   ├── services/              # item_location, meters, effects, ledger, scheduler,
│       │   │                          #   mobile_route, item_components, audit, save
│       │   ├── repos/                 # player/room/item/npc/audit/stack/ledger/meter/…_repo
│       │   └── clock/world_clock.py   # WorldClock + real-time loop
│       │
│       ├── features/                  # ── Tier 2: optional feature packages (one dir each)
│       │   ├── manifest.py            # FeatureManifest + registry
│       │   ├── loader.py              # discover_features / load_features / resolve_enabled
│       │   ├── economy/               # e.g. models, service, repo, commands, holders, restock
│       │   │   └── …                  #   (+ optional presentation.py for feature UI)
│       │   ├── transit/               # …, presentation.py (registers the minimap panel)
│       │   └── …                      # inventory, movement, npc, quests, trading, bank,
│       │                              #   equipment, traits, skills, exploration, fatigue,
│       │                              #   warmth, terrain, weather, light, reputation,
│       │                              #   containers, item_components, items, character,
│       │                              #   npc_memory, encumbrance
│       │
│       ├── webui/                     # ── Web: delivery hosts (compose engine + features)
│       │   ├── player/                # HTMX/Alpine/Jinja player UI
│       │   │   ├── __init__.py        #   create_web_host / load_feature_presentations
│       │   │   ├── host.py            #   WebHost: multi-dir Jinja loader + panel/slot registry
│       │   │   ├── frontend.py  session.py  rendering.py  auth.py  player_auth.py
│       │   │   └── templates/  static/
│       │   └── admin/                 # Admin REST API + push WS + Textual TUI
│       │       ├── api.py  websocket.py  auth.py  broadcaster.py
│       │       └── routers/           # players, world, clock, audit, accounts, issues, news, …
│       │
│       ├── commands/                  # Shell/OOC verbs + register_all_commands (composition)
│       │   ├── meta.py  social.py  news.py  report.py
│       │   └── __init__.py            #   wires engine shell verbs + every feature's verbs
│       │
│       ├── services/container.py      # ServiceContainer — builds Tier 2 services per enabled set
│       ├── content/                   # issues.py, news.py (YAML↔DB), paths.py
│       ├── world/                     # loader, validator, versioning, bootstrap (YAML → DB)
│       └── tools/                     # world_cli.py, validators.py
│
├── tests/
│   ├── unit/                         # Pure function tests (+ test_tier_boundaries.py)
│   ├── integration/                  # In-memory SQLite tests (+ test_feature_toggling.py)
│   ├── e2e/                          # Playwright browser tests
│   └── simulation/                   # N scripted virtual players over real WebSockets
│
└── world_content/                    # world.yaml (rooms/items/npcs/quests/dialogue/…)
```

> **Note.** Combat/PvP subsystems (`features/combat`, `npc/combat_ai`, `models/combat`) are **not yet built** — deferred to roadmap Sprints 61–65. The stat/skill/equipment primitives they will consume already exist in `engine/` and the relevant `features/`.

---

## 5. Core Patterns

### GameContext

The single object passed to every command handler. Constructed fresh per request. Never stored globally.

```python
@dataclass
class GameContext:
    player: Player
    room: Room
    clock: WorldClock               # read-only time reference
    player_repo: PlayerRepo
    room_repo: RoomRepo
    item_repo: ItemRepo
    npc_repo: NpcRepo
    manager: ConnectionManager      # room-based WebSocket broadcasts
    bus: EventBus
    audit: AuditService
    transaction: TransactionContext
    session_id: str

    messages: list[str] = field(default_factory=list)       # to commanding player
    room_messages: list[str] = field(default_factory=list)  # broadcast to room
    updates: dict = field(default_factory=dict)             # structured UI updates

    def say(self, text: str):
        self.messages.append(text)

    def tell_room(self, text: str):
        self.room_messages.append(text)

    def push_update(self, key: str, value):
        self.updates[key] = value

    def emit(self, event: GameEvent, **payload):
        self.bus.emit(Event(event, payload), self)
```

### TransactionContext

Every command, scheduler job, and admin action creates a `TransactionContext`. All audit events produced within that context share the same `transaction_id`.

```python
@dataclass
class TransactionContext:
    transaction_id: str             # UUID per command
    correlation_id: str             # UUID per player session (chains related txns)
    parent_transaction_ids: list[str]  # causal chain (e.g., quest trigger → scheduler job)
    source_type: str                # PLAYER_COMMAND | SCHEDULER | ADMIN | SYSTEM
    actor_id: str
```

### ConnectionManager

Manages all active WebSocket connections. Supports room-based broadcast.

```python
class ConnectionManager:
    # player_id → WebSocket
    # room_id → set[player_id]

    async def connect(self, player_id: str, ws: WebSocket) -> None
    async def disconnect(self, player_id: str) -> None
    async def send_to_player(self, player_id: str, message: dict) -> None
    async def broadcast_to_room(self, room_id: str, message: dict, exclude: str = None) -> None
    def move_player(self, player_id: str, from_room: str, to_room: str) -> None
    def players_in_room(self, room_id: str) -> list[str]
```

---

## 6. Database Schema

All tables use SQLModel. SQLite is the backing store. Use a single `game.db` file and a separate `audit.db` file (the audit log is isolated for independent archival and querying).

### Core World Tables

```python
class Room(SQLModel, table=True):
    id: str = Field(primary_key=True)      # slug, e.g. "tavern_main"
    name: str
    description: str
    map_x: int
    map_y: int
    map_z: int = 0                          # floor/level; minimap filters to current_room.map_z
    area_id: Optional[str]                  # logical grouping
    is_active: bool = True                  # False = not reachable; part of changeset system
    fallback_room_id: Optional[str]         # where to displace players if deactivated
    flags: dict = Field(default_factory=dict, sa_column=Column(JSON))
    disabled_commands: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    light_level: int = 1                    # 0 = dark
    version: int = 1                        # optimistic locking

class Exit(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    room_id: str = Field(foreign_key="room.id", index=True)
    direction: str
    target_room_id: str
    locked: bool = False
    key_item_id: Optional[str] = None
    hidden: bool = False
    condition_flags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

class Item(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    takeable: bool = True
    tradeable: bool = True                  # False = quest-critical; never changes hands
    usable_with: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    loot_table: dict = Field(default_factory=dict, sa_column=Column(JSON))

class RoomItem(SQLModel, table=True):
    """Junction: which items are in which rooms right now."""
    id: int = Field(default=None, primary_key=True)
    room_id: str
    item_id: str
    quantity: int = 1

class WorldMeta(SQLModel, table=True):
    """Singleton. Always exactly one row."""
    id: int = Field(default=None, primary_key=True)
    schema_version: int = 1
    engine_version: str = "0.1.0"
```

### Player Tables

```python
class Player(SQLModel, table=True):
    id: str = Field(primary_key=True)      # UUID
    username: str = Field(unique=True, index=True)
    current_room_id: str
    inventory: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    visited_rooms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    flags: dict = Field(default_factory=dict, sa_column=Column(JSON))
    respawn_room_id: str                    # bound waypoint
    pvp_consent: bool = False               # explicit opt-in
    world_schema_version: int = 1           # for lazy migration
    active_combat_session_id: Optional[str] = None
    ghost_state: bool = False               # True between death and respawn

class PlayerStats(SQLModel, table=True):
    player_id: str = Field(primary_key=True, foreign_key="player.id")
    strength: int = 10
    agility: int = 10
    vitality: int = 10
    intellect: int = 10
    presence: int = 10
    fortitude: int = 10
    max_hp: int = 100
    current_hp: int = 100
    level: int = 1
    xp: int = 0
    xp_to_next: int = 100
    skills: dict = Field(default_factory=dict, sa_column=Column(JSON))  # skill_name → 0-100

class PlayerSession(SQLModel, table=True):
    """Tracks connection state; disconnect ≠ logout."""
    id: str = Field(primary_key=True)      # session UUID
    player_id: str = Field(index=True)
    connected_at: float
    disconnected_at: Optional[float] = None
    grace_expires_at: Optional[float] = None   # grace period for reconnect
    status: str = "active"                 # active | grace | expired | system_controlled

class SaveSlot(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    player_id: str = Field(index=True)
    slot_name: str                          # "slot1", "slot2", "slot3", or "auto"
    saved_at: float
    room_id: str
    inventory: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    flags: dict = Field(default_factory=dict, sa_column=Column(JSON))
    stats_snapshot: dict = Field(default_factory=dict, sa_column=Column(JSON))
    quest_progress: dict = Field(default_factory=dict, sa_column=Column(JSON))
    timeline_branch_id: Optional[str] = None   # set when loaded past a death event
```

### World Clock

```python
class WorldClock(SQLModel, table=True):
    """Singleton. Always exactly one row."""
    id: int = Field(default=None, primary_key=True)
    game_epoch: float          # accumulated game-time seconds
    real_epoch: float          # wall time when last persisted
    time_ratio: float = 60.0  # 1 real second = 60 game seconds (= 1 game minute per real second)
    paused: bool = False
    current_hour: int = 8
    current_minute: int = 0
    current_day: int = 1
    current_season: str = "spring"  # spring | summer | autumn | winter
    weather: str = "clear"
```

### NPC Tables

```python
class NPC(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    description: str
    current_room_id: str
    home_room_id: str
    dialogue_tree_id: str
    behavior: str = "defensive"             # aggressive|defensive|cowardly|territorial|guard
    max_hp: int = 50
    current_hp: int = 50
    loot_table: dict = Field(default_factory=dict, sa_column=Column(JSON))
    respawn_seconds: Optional[int] = 300    # None = never respawns
    schedule: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    # schedule entry: {"game_hour": 8, "target_room_id": "market_square", "move_type": "walk"}
```

### Quest Tables

```python
class Quest(SQLModel, table=True):
    id: str = Field(primary_key=True)
    title: str
    description: str
    stages: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    # stage: {"id": "s1", "description": "...", "conditions": [...], "completion_flags": {...}}

class PlayerQuestProgress(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    player_id: str = Field(index=True)
    quest_id: str
    current_stage_id: str
    status: str = "active"                  # active | complete | failed
    started_at: float
    completed_at: Optional[float] = None
```

### Combat Tables

```python
class CombatSession(SQLModel, table=True):
    id: str = Field(primary_key=True)       # UUID
    room_id: str
    started_at: float
    status: str = "active"                  # active | resolved
    combatants: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    # combatant: {"entity_id": ..., "entity_type": "player|npc", "next_action_tick": ..., "speed": ..., "threat": {...}}
```

### World Versioning Tables

```python
class Changeset(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    status: str = "draft"                   # draft|scanning|conflicts|ready|live|rolled_back
    created_by: str
    created_at: float
    promoted_at: Optional[float] = None
    world_version: Optional[str] = None     # e.g. "1.2.0" — set on promotion

class ChangesetItem(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    changeset_id: str = Field(index=True)
    entity_type: str                        # room|item|npc|flag|exit
    entity_id: str
    operation: str                          # create|update|delete|activate|deactivate
    before_state: dict = Field(default_factory=dict, sa_column=Column(JSON))
    after_state: dict = Field(default_factory=dict, sa_column=Column(JSON))

class WorldMigration(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    from_version: int
    to_version: int
    migration_type: str                     # rename_flag|rename_room|restructure
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    applied_at: float

class ConflictScanResult(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    changeset_id: str = Field(index=True)
    entity_type: str
    entity_id: str
    severity: str                           # ERROR|WARNING|INFO
    auto_resolvable: bool
    acknowledged: bool = False
    description: str
```

### Player Interaction Tables

```python
class TradeOffer(SQLModel, table=True):
    id: str = Field(primary_key=True)
    initiator_id: str
    recipient_id: str
    initiator_items: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    recipient_items: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = "pending"                 # pending|accepted|declined|cancelled|expired
    created_at: float
    expires_at: float                       # TTL to auto-cancel stale offers

class PvpConsent(SQLModel, table=True):
    """Explicit opt-in per player pair."""
    id: int = Field(default=None, primary_key=True)
    player_a_id: str
    player_b_id: str
    consented_at: float
    revoked_at: Optional[float] = None
```

### Audit Table (in `audit.db`)

```python
class AuditEvent(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    transaction_id: str = Field(index=True)
    correlation_id: str = Field(index=True)
    parent_transaction_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    actor_id: str = Field(index=True)       # player_id, npc_id, "system", "admin:X"
    event_type: str = Field(index=True)     # GameEvent enum value
    source_type: str                        # PLAYER_COMMAND|SCHEDULER|ADMIN|SYSTEM
    target_id: Optional[str] = None        # item/npc/room/player affected
    room_id: str = Field(index=True)
    game_time: float                        # world clock timestamp
    real_time: float = Field(index=True)   # wall clock timestamp
    severity: str = "INFO"                  # INFO|WARNING|ERROR
    summary: str                            # human-readable one-liner
    payload_json: dict = Field(default_factory=dict, sa_column=Column(JSON))
```

---

## 7. Subsystem: World Clock & Scheduler

### World Clock

The clock runs as an independent `asyncio` background task, completely separate from command handling.

**Behavior:**
- `game_epoch` advances at `time_ratio` × real seconds.
- On startup: load `WorldClock` from DB. If `paused=False`, compute how much real time elapsed since `real_epoch` and fast-forward `game_epoch` accordingly.
- Emit `TIME_ADVANCED` every real-time tick (e.g., every 1 second). The event carries previous and current game time so listeners can detect hour/day/season crossings.
- Emit `HOUR_CHANGED`, `DAY_CHANGED`, `SEASON_CHANGED` as appropriate when those boundaries are crossed.
- Persist `game_epoch` and `real_epoch` to DB every minute and on clean shutdown.
- If `paused=True`, the clock loop sleeps without advancing.
- The admin API can set `time_ratio`, toggle `paused`, and override weather without touching the clock loop code.

**Key invariant:** `WorldClock` is a singleton table. It is **never** per-player.

### Scheduler

A persistent, DB-backed service that knows *when* work is due and emits work events. It knows **nothing** about game rules — owning subsystems perform the actual work.

```python
# Conceptual interface
class SchedulerService:
    def schedule(self, job_type: str, at_game_epoch: float, payload: dict) -> str
    def cancel(self, job_id: str) -> None
    def tick(self, current_epoch: float) -> None  # called on every TIME_ADVANCED
```

On every `TIME_ADVANCED` event, the scheduler queries for due jobs and emits work events for each. The NPC movement system, combat tick, and delayed world effects all use the scheduler.

---

## 8. Subsystem: Event Bus

Two distinct event kinds — do not mix them.

### Notification Events
Announce facts. Handlers observe and react. Handlers do **not** report back.
- Examples: `ITEM_TAKEN`, `PLAYER_MOVED`, `QUEST_UPDATED`, `TIME_ADVANCED`, `WEATHER_CHANGED`, `PLAYER_DIED`

### Work Events
Request subsystem action. Handlers return a result: `success | retry | permanent_failure`.
- Examples: `COMBAT_TICK_DUE`, `NPC_MOVE_DUE`, `SCHEDULED_JOB_DUE`

### Implementation Notes

```python
class GameEvent(str, Enum):
    # Notification events
    ITEM_TAKEN = "item_taken"
    ITEM_DROPPED = "item_dropped"
    ITEM_USED = "item_used"
    PLAYER_MOVED = "player_moved"
    PLAYER_DIED = "player_died"
    PLAYER_RESPAWNED = "player_respawned"
    NPC_MOVED = "npc_moved"
    NPC_DIED = "npc_died"
    NPC_FLED = "npc_fled"
    COMBAT_STARTED = "combat_started"
    COMBAT_ENDED = "combat_ended"
    PLAYER_ATTACKED = "player_attacked"
    NPC_ATTACKED = "npc_attacked"
    SKILL_IMPROVED = "skill_improved"
    QUEST_UPDATED = "quest_updated"
    QUEST_COMPLETED = "quest_completed"
    TIME_ADVANCED = "time_advanced"
    HOUR_CHANGED = "hour_changed"
    DAY_CHANGED = "day_changed"
    SEASON_CHANGED = "season_changed"
    WEATHER_CHANGED = "weather_changed"
    TRADE_COMPLETED = "trade_completed"
    PLAYER_DISCONNECTED = "player_disconnected"
    PLAYER_RECONNECTED = "player_reconnected"
    WORLD_CHANGESET_PROMOTED = "world_changeset_promoted"
    SAVE_LOADED = "save_loaded"

    # Work events
    COMBAT_TICK_DUE = "combat_tick_due"
    NPC_MOVE_DUE = "npc_move_due"
    SCHEDULED_JOB_DUE = "scheduled_job_due"
    GRACE_PERIOD_EXPIRED = "grace_period_expired"
```

The bus is synchronous and in-process. It supports:
- Handler priority ordering
- Per-event exception isolation (one bad handler doesn't kill the bus)
- Result collection for work events

---

## 9. Subsystem: Command System

### Parser

Converts raw text input to structured commands with semantic **roles** (object, recipient,
direction, message, …). Supports prepositions, quantities, compounds (`;`), and optional
`GameContext` entity resolution.

See **[command_parser.md](command_parser.md)** for role keys, command patterns (movement,
speech, transfer, containers, gestures, …), handler integration guidance, and test
conventions.

```python
@dataclass
class ParsedCommand:
    verb: str
    raw: str
    roles: dict[str, JsonValue]       # e.g. {"object": "sword", "recipient": "Gabriel"}
    resolved_ids: dict[str, str]      # after fuzzy match against room/inventory
    # .noun — legacy convenience property for single-phrase handlers

result = parse_command("give lead pipe to Gabriel", context=ctx)
# → commands[0].verb == "give"
# → roles == {"object": "lead pipe", "recipient": "Gabriel"}
```

Pattern helpers: `src/lorecraft/game/command_patterns.py`

### Command Registry

Commands declare their scope and conditions. No hardcoded if/else dispatch.

```python
class CommandScope(str, Enum):
    GLOBAL = "global"   # always available (help, quit, save)
    SOCIAL = "social"   # requires another player present
    WORLD = "world"     # normal world interaction

class CommandCondition(str, Enum):
    REQUIRES_LIGHT = "requires_light"
    NOT_IN_COMBAT = "not_in_combat"
    IN_COMBAT = "in_combat"
    HAS_COMBAT_TARGET = "has_combat_target"
    ACTOR_HAS_FLAG = "actor_has_flag"   # parameterized: ACTOR_HAS_FLAG:cave_open
    ACTOR_LACKS_FLAG = "actor_lacks_flag"
    ITEM_IN_INVENTORY = "item_in_inventory"
    NPC_PRESENT = "npc_present"

def register(verb: str, *aliases: str, scope=CommandScope.WORLD, conditions: list[CommandCondition] = None):
    """Decorator for command handler functions."""
    ...
```

Example handler registration:

```python
@register("take", "get", "pick", scope=CommandScope.WORLD, conditions=[CommandCondition.REQUIRES_LIGHT])
def do_take(noun: str | None, ctx: GameContext) -> None:
    item = ctx.item_repo.find_in_room(noun, ctx.room.id)
    if not item:
        ctx.say("You don't see that here.")
        return
    ctx.inventory_service.take_item(item, ctx)
```

### Room-Level Overrides

Rooms can disable specific commands regardless of conditions:

```yaml
# In YAML
rooms:
  - id: cursed_vault
    disabled_commands: ["save", "trade", "emote"]
```

### Condition Evaluation

The registry evaluates all declared conditions **before** calling the handler. If any condition fails, a contextual error message is returned and the handler is never invoked. Blocked commands are still written to the audit log with `result="blocked"`.

---

## 10. Subsystem: Rule Engine

A dedicated layer between commands/services and execution. Systems and future content hooks register rules without coupling to core service code.

```python
class RuleResult:
    allowed: bool
    reason: Optional[str] = None    # shown to player if blocked
    modified_payload: Optional[dict] = None  # rules can modify what's about to happen

class RuleEngine:
    def register_rule(self, event_type: str, rule_fn: Callable) -> None
    def check(self, event_type: str, ctx: GameContext, payload: dict) -> RuleResult
```

Example rule registration:

```python
# A world content hook can add a rule without touching core services
rule_engine.register_rule("take_item", lambda ctx, payload:
    RuleResult(allowed=False, reason="The artifact is bound to this altar.")
    if payload["item_id"] == "sacred_gem" and not ctx.player.flags.get("priest_blessed")
    else RuleResult(allowed=True)
)
```

Services call `rule_engine.check(...)` before performing any state change. This is how quests, world state, and future plugins influence behavior without tight coupling.

---

## 11. Subsystem: Service Layer

Game rules live in services, not in command handlers. Command handlers translate input into service calls.

### MovementService

```python
class MovementService:
    def move(self, direction: str, ctx: GameContext) -> None:
        # 1. Find exit in current room
        # 2. Check rule engine (locked doors, flags, etc.)
        # 3. Broadcast departure to current room
        # 4. Update player.current_room_id
        # 5. Update ConnectionManager room membership
        # 6. Load target room
        # 7. Broadcast arrival to new room
        # 8. Update ctx with new room
        # 9. Emit PLAYER_MOVED event
        # 10. Add visited_rooms entry if new
        # 11. Trigger auto-save if configured
```

### InventoryService

```python
class InventoryService:
    def take_item(self, item: Item, ctx: GameContext) -> None
    def drop_item(self, item_id: str, ctx: GameContext) -> None
    def use_item(self, item_id: str, ctx: GameContext) -> None
    def transfer_item(self, item_id: str, from_player_id: str, to_player_id: str, ctx: GameContext) -> None
```

### CombatService

See [Combat System](#15-subsystem-combat-system).

### DialogueService

See [NPC System](#13-subsystem-npc-system).

### QuestService

See [Quest Engine](#14-subsystem-quest-engine).

### SaveSlotService

See [Save Slots & Death/Respawn](#17-subsystem-save-slots--deathrespawn).

---

## 12. Subsystem: Audit Log

**The DB audit log is canonical.** The text log is a derived operational mirror. They are never written independently.

### The Rule

One `AuditEvent` object is created → saved to `audit.db` → then rendered to the text log. **One truth, two views.**

```python
class AuditService:
    def record(self, ctx: GameContext, event_type: GameEvent, target_id: str = None,
               severity: str = "INFO", summary: str = "", payload: dict = None) -> AuditEvent:
        event = AuditEvent(
            transaction_id=ctx.transaction.transaction_id,
            correlation_id=ctx.transaction.correlation_id,
            parent_transaction_ids=ctx.transaction.parent_transaction_ids,
            actor_id=ctx.player.id,
            event_type=event_type.value,
            source_type=ctx.transaction.source_type,
            target_id=target_id,
            room_id=ctx.room.id,
            game_time=ctx.clock.game_epoch,
            real_time=time.time(),
            severity=severity,
            summary=summary,
            payload_json=payload or {},
        )
        self.audit_repo.append(event)
        self._render_to_text_log(event)
        return event

    def _render_to_text_log(self, event: AuditEvent) -> None:
        # logfmt format
        # 2026-06-27T14:03:22Z game=08:15 actor=Alice action=TAKE_ITEM target=sword room=tavern tx=T500 result=success
        ...
```

Audit events are written **unconditionally** — including blocked commands (`severity="WARNING"`, summary includes reason). This is how you debug permission issues post-hoc.

### Audit Log Queries Needed by Admin

- Filter by `actor_id`, `room_id`, `event_type`, time range
- Fetch all events for a `transaction_id` (see all effects of one command)
- Fetch full chain by `correlation_id` (see everything a player did in a session)
- Replay a session chronologically for investigation

---

## 13. Subsystem: NPC System

### Dialogue Trees

Authored in YAML. The engine walks the tree based on player choices and flag state.

```yaml
# npcs/blacksmith.yaml
id: blacksmith
name: Gruff the Blacksmith
dialogue_tree_id: blacksmith_dialogue
behavior: defensive
schedule:
  - game_hour: 8
    target_room_id: forge
  - game_hour: 20
    target_room_id: tavern_nook

dialogue_trees:
  - id: blacksmith_dialogue
    root_node: greeting
    nodes:
      - id: greeting
        text: "What do you want? I'm busy."
        choices:
          - label: "I need a weapon."
            condition_flags: []
            next_node: weapons_menu
          - label: "Tell me about the cave."
            condition_flags: ["heard_rumor"]
            next_node: cave_info
            side_effects:
              set_flags: ["blacksmith_warned_me"]
      - id: cave_info
        text: "Dark things stir in the deep cave. Take this."
        side_effects:
          give_item: "torch"
          set_flags: ["blacksmith_quest_started"]
```

### Dialogue Walker

```python
class DialogueService:
    def start_dialogue(self, npc_id: str, ctx: GameContext) -> DialogueNode
    def choose(self, choice_index: int, ctx: GameContext) -> DialogueNode
    def apply_side_effects(self, node: DialogueNode, ctx: GameContext) -> None
```

The dialogue overlay on the frontend sends a `dialogue_choice` message type to the WebSocket. While a dialogue is active, the command input is disabled.

### NPC Movement

NPCs check their schedule on every `HOUR_CHANGED` event. If the current game hour matches a schedule entry, the NPC moves to the target room.

```python
bus.on(GameEvent.HOUR_CHANGED, lambda event, ctx: npc_scheduler.process_schedules(event.payload["hour"]))
```

### NPC State Machine

NPCs have distinct modes: `idle`, `in_dialogue`, `in_combat`, `following_schedule`, `fled`. Combat mode is an extension of this — **not** a separate bolt-on system.

---

## 14. Subsystem: Quest Engine

### YAML Definition

```yaml
quests:
  - id: cave_rescue
    title: "Rescue from the Deep Cave"
    description: "Someone is trapped in the cave north of town."
    stages:
      - id: start
        description: "Find out who needs rescuing."
        conditions:
          - type: flag_set
            flag: "heard_rumor"
        completion_flags:
          quest_cave_rescue_stage1: true
      - id: enter_cave
        description: "Enter the cave and find the prisoner."
        conditions:
          - type: room_visited
            room_id: "cave_prison"
        completion_flags:
          quest_cave_rescue_stage2: true
      - id: complete
        description: "Escort the prisoner back to town."
        conditions:
          - type: room_visited
            room_id: "town_gate"
          - type: flag_set
            flag: "prisoner_following"
        completion_flags:
          quest_cave_rescue_complete: true
        rewards:
          xp: 200
          items: ["silver_coin"]
```

### Quest Service

```python
class QuestService:
    def check_progression(self, player: Player, ctx: GameContext) -> None:
        # Called on every relevant event; checks all active quest stages
        # Stage conditions evaluated against player flags, visited rooms, inventory
        # On stage completion: update PlayerQuestProgress, set completion_flags, emit QUEST_UPDATED
        # On quest completion: emit QUEST_COMPLETED, award rewards
```

Quest progression is driven by event subscriptions, not polling. The `QuestService` subscribes to `ITEM_TAKEN`, `PLAYER_MOVED`, `NPC_DIED`, `FLAG_CHANGED` etc., and evaluates active quest conditions in response.

---

## 15. Subsystem: Combat System

### Stat Model

Six core attributes, each serving both combat and world-skill roles:

| Stat | Combat Role | World Role |
|---|---|---|
| Strength | Melee damage bonus | Forced entry, heavy object interaction |
| Agility | Hit chance, speed | Lockpicking, evasion, stealth |
| Vitality | Max HP, HP regen | Endurance, poison resistance |
| Intellect | Magic power (future) | Puzzle solving, lore checks |
| Presence | NPC persuasion, threat | Dialogue branch unlocks, intimidation |
| Fortitude | Armor effectiveness | Disease resistance, willpower checks |

Derived stats computed at runtime from base stats + equipment + buffs. Never store derived stats.

### Combat Model

Tick-based, leveraging the real-time clock. Each combatant has a `next_action_tick` and `speed`. Multiple players can engage the same NPC concurrently on independent rhythms.

```
CombatSession
  ├── combatant: Player A (speed=10 ticks, next_action=tick 10)
  ├── combatant: Player B (speed=15 ticks, next_action=tick 15)
  └── combatant: NPC (speed=12 ticks, next_action=tick 12)
```

On each `COMBAT_TICK_DUE` work event: resolve actions for any combatant whose `next_action_tick ≤ current_tick`, set `next_action_tick = current_tick + speed`, emit results.

### Damage Resolution

```
hit_roll = d20 + agility_modifier
if hit_roll < target_defense_threshold → miss
else:
    raw_damage = weapon_min + random(weapon_max - weapon_min) + strength_modifier
    final_damage = max(0, raw_damage - target_armor_flat_reduction)
    if hit_roll == 20 (natural 20): final_damage *= 2  # crit
```

### NPC Combat Behaviors

```python
class NPCCombatBehavior(str, Enum):
    AGGRESSIVE   # attacks on sight or when threatened
    DEFENSIVE    # fights back when attacked, may flee if losing
    COWARDLY     # flees early (< 50% HP); negotiates if cornered
    TERRITORIAL  # attacks only in their zone, otherwise ignores
    GUARD        # calls for reinforcements instead of fleeing
```

Decision logic fires each time the NPC's combat tick resolves. Fleeing NPCs transition back to their schedule (or a `FLED` waypoint). Negotiating NPCs re-enter the dialogue tree with a `combat_context=CORNERED` flag.

### Death & Respawn (Combat-Side)

**Player death:**
1. Emit `PLAYER_DIED`
2. Player enters `ghost_state=True` — can observe room but not act
3. Drop corpse object in room containing 30% of carried gold (not items)
4. Respawn at `respawn_room_id` after 30-second ghost period
5. Lose 10% of XP progress toward next level (never lose a whole level)
6. Corpse TTL: 10 real minutes; player or allies can loot it back

**NPC death:**
1. Emit `NPC_DIED`
2. Drop loot per NPC's `loot_table`
3. Respawn per `respawn_seconds` config (None = never respawns — boss kills matter)

### Progression: Dual-Track System

**Track 1 — Experience Levels (1–20):** Coarse-grained; gate major content. Grant +2 stat points on level-up.

**Track 2 — Skill Proficiency (per-skill, 0–100):** Fine-grained; earned by doing:
- Win melee combats → `combat_skill` rises → unlock combo attacks
- Successfully lockpick → `lockpicking` rises → lower difficulty thresholds
- Pass persuasion checks → `presence_skill` rises → new dialogue options

### Combat-Gated Commands

Commands like `SLEEP`, `FAST_TRAVEL`, `TRADE` require condition `NOT_IN_COMBAT`.
Commands like `FLEE`, `ATTACK`, `USE_SKILL` require condition `IN_COMBAT`.
The check: `player.active_combat_session_id is not None` → in combat.

### Events Emitted by Combat System

| Event | When | Consumers |
|---|---|---|
| `COMBAT_STARTED` | Session created | Audit, quest engine, room broadcast |
| `PLAYER_ATTACKED` | Player takes damage | Audit, quest triggers |
| `NPC_ATTACKED` | NPC takes damage | Quest triggers |
| `NPC_FLED` | NPC flee action succeeds | Quest engine, room broadcast |
| `NPC_DIED` | NPC HP → 0 | Quest engine, loot spawn, audit |
| `PLAYER_DIED` | Player HP → 0 | Audit, quest engine, room broadcast |
| `COMBAT_ENDED` | Session resolves | Unlock non-combat commands, award XP |

---

## 16. Subsystem: Weather & Seasons

Weather and season state is stored on `WorldClock`. Changes are driven by `TIME_ADVANCED` events.

```python
SEASONS = ["spring", "summer", "autumn", "winter"]
DAYS_PER_SEASON = 30

WEATHER_TABLE = {
    "spring": ["clear", "light_rain", "overcast", "clear", "clear"],
    "summer": ["clear", "clear", "hot", "clear", "thunderstorm"],
    "autumn": ["overcast", "heavy_rain", "clear", "fog", "clear"],
    "winter": ["snow", "clear", "blizzard", "fog", "clear"],
}
```

On `DAY_CHANGED`: roll new weather from the current season's table (weighted random). Emit `WEATHER_CHANGED` if the weather actually changed.

On `SEASON_CHANGED`: transition to next season. Emit `SEASON_CHANGED`.

Weather affects:
- Light level in outdoor rooms (storms reduce light)
- NPC schedules (NPCs shelter during blizzards)
- Player messages (atmospheric narration injected into feed)
- Command conditions (some actions require clear weather)

---

## 17. Subsystem: Save Slots & Death/Respawn

### What a Save Captures

**Player-owned state only.** World state is never per-player and is never saved/restored per player.

Save captures: `current_room_id`, `inventory`, `visited_rooms`, `flags`, `stats_snapshot`, `quest_progress`.

### Save Slots

3 named slots (`slot1`, `slot2`, `slot3`) + 1 `auto` slot. The `auto` slot triggers on:
- Quest flag changes
- Room transitions (configurable; can be throttled)
- Admin-triggered saves

### Timeline Branching

Loading a save that predates a death event is allowed. The new `SaveSlot` load sets `timeline_branch_id` in the audit log, creating a traceable branch. This does **not** undo any shared world effects (items dropped on corpse remain, NPC kills remain).

### Quest Item Ownership

Quest-critical items are **player-scoped flags**, not world objects. This prevents cross-player desync bugs where one player's quest item gets stuck in another player's save state.

Tradeable/cosmetic items are world objects and can be dropped, traded, and looted.

---

## 18. Subsystem: Disconnect Handling

**Disconnect is not logout.** A dropped WebSocket connection starts a grace period.

### Grace Period Behavior

1. `PlayerSession.status` → `"grace"`, `grace_expires_at` set (60 seconds default)
2. Player character **remains in the world** during grace period
3. If in combat: **combat pauses** for that player's slots — they neither act nor take damage
4. Other players in the room see: "Alice's connection flickers..."
5. Emit `PLAYER_DISCONNECTED` (notification event — quest/admin hooks can react)

### Reconnect

If player reconnects before `grace_expires_at`:
1. Reattach to existing `PlayerSession`
2. Resume combat if applicable
3. Send full reconnect sync message (see [WebSocket Protocol](#23-websocket-protocol))
4. Emit `PLAYER_RECONNECTED`

### Grace Period Expired

If grace period expires without reconnect:
1. `PlayerSession.status` → `"system_controlled"` (or `"expired"` if not in combat)
2. If in combat: NPC's combat AI takes over for the player character (defensive behavior)
3. If in dialogue: dialogue session cancelled safely
4. If holding trade offer: trade offer auto-cancelled, items returned
5. Emit `GRACE_PERIOD_EXPIRED` (work event — scheduler fires this)

### DB Tables Touched

- `PlayerSession` tracks all of the above
- `AuditEvent` records every state transition with `source_type="SYSTEM"`

---

## 19. Subsystem: World Versioning & Changesets

### Core Problem

A player has `quest_flag = "cave_entrance_unlocked"` in their state. You rename that flag. Now their state points at a ghost.

### Solution: World Schema Versioning + Lazy Migration

`WorldMeta.schema_version` is the global world version. Each player tracks `Player.world_schema_version`. When a player logs in, if their `world_schema_version < WorldMeta.schema_version`, run all pending migrations against their state before loading them into the world.

### Changeset Lifecycle

```
DRAFT → SCANNING → (CONFLICTS | READY) → LIVE → (ROLLED_BACK)
```

1. **DRAFT:** Admin groups edits into a named changeset. Rooms/items/NPCs can be in `is_active=False` state within the changeset (invisible to players until promoted).

2. **SCANNING:** Admin triggers the conflict scanner before promotion. The scanner checks:
   - Broken exit references (target room deactivated/deleted) → ERROR
   - Players currently in rooms being deactivated → WARNING (auto-resolvable via `fallback_room_id`)
   - Renamed flags that active quests reference → ERROR
   - Items held by players that are being deleted → WARNING
   - Quest stages referencing removed NPCs → ERROR

3. **CONFLICTS:** At least one ERROR found. Admin must resolve before re-scan.

4. **READY:** Scan clean (or all auto-resolvable conflicts acknowledged). Admin can promote.

5. **LIVE:** Changeset promoted atomically. `is_active` flipped on all entities simultaneously. `WorldMeta.schema_version` bumped. Players in deactivating rooms auto-displaced to `fallback_room_id`.

6. **ROLLED_BACK:** Promotion can be rolled back by re-importing the previous YAML snapshot and bumping `schema_version`.

### Conflict Scanner Policy

Auto-resolvable conflicts (player displacement, etc.) surface to the admin for acknowledgment before promotion — they don't block, but they require explicit sign-off.

### Optimistic Locking

All world entity tables have a `version: int` field. Admin edits include the `version` they read. If the DB version differs at write time → 409 Conflict, with a diff shown to the admin.

---

## 20. Subsystem: Player Interaction (Trading & PvP)

### Trading

Trading requires both players to be in the same room. All tradeable items have `Item.tradeable=True`. Quest-critical items have `tradeable=False` and can never be transferred.

```
Player A: "trade Bob sword"
  → Creates TradeOffer with TTL (e.g., 60 seconds)
  → Bob sees: "Alice offers you a sword. 'trade accept' or 'trade decline'"
Bob: "trade accept"
  → Rule engine checks: both players present, items tradeable, not in combat
  → Atomic swap: item transferred, both inventories updated in one transaction
  → Emit TRADE_COMPLETED
  → TradeOffer.status = "accepted"
```

If either player disconnects during a pending trade: the trade offer auto-cancels and items are returned.

### PvP Consent

PvP is **explicit opt-in only**. No player can attack another without mutual consent.

```
Player A: "pvp challenge Bob"
Player B: "pvp accept Alice"
  → PvpConsent record created for the pair
  → Either player can "pvp cancel" to revoke consent
  → Consent is revoked automatically on room change (configurable)
```

If a player attempts to `attack <player_name>` without mutual `PvpConsent`:
- Command is blocked by the rule engine
- Audit log records the attempt with `result="blocked"`

---

## 21. Subsystem: Admin & Authoring Tools

### Two Interfaces, One API

**Browser web panel** — no install required; for occasional oversight, world editing, and moderation.

**Textual TUI** — Python terminal client; keyboard-driven power tool for bulk world authoring and real-time monitoring.

Both share one admin REST API. Admin push events use a **separate** admin WebSocket (never mixed with the player WebSocket).

### Auth Model

JWT with short expiry.
- Access tokens: 15-minute lifetime
- Refresh tokens: 8-hour lifetime, rotation on every use
- TUI credentials stored in `~/.config/{game-name}-admin/credentials.json` at mode `0600`; silent token refresh on startup

### Role Hierarchy

```
superadmin ⊃ world-builder ⊃ moderator ⊃ observer
```

| Operation | observer | moderator | world-builder | superadmin |
|---|---|---|---|---|
| View live players, audit log | ✓ | ✓ | ✓ | ✓ |
| Send player messages, teleport, freeze session | | ✓ | ✓ | ✓ |
| Edit rooms, items, NPCs, dialogue | | | ✓ | ✓ |
| Import/export YAML, manage changesets | | | ✓ | ✓ |
| Server clock controls, weather override | | | | ✓ |
| Manage admin accounts, restart engine | | | | ✓ |

### World Authoring Workflow

**YAML is for human authoring and version control. DB is the runtime source of truth. Import is one-directional (YAML → DB).**

**Online build mode:** Admin UI edits write directly to DB (live immediately) and are debounce-flushed to YAML. YAML is committed to the `world-content` git repo.

- Moving `world/live` tag updated on every flush
- Versioned snapshot tags (e.g., `world/v1.1.0`) for releases
- Engine + content tags paired for reproducibility
- Rollback: re-import previous YAML snapshot, bump `schema_version`

**Build mode policies (configurable):**
- `notify` — players get a message that maintenance is occurring
- `restrict` — new players can't join; existing players continue
- `lockout` — all players paused; world frozen

**Startup drift detection:** At startup, compare `WorldMeta.schema_version` with the YAML files in the `world-content` repo. If they diverge, log a warning.

### Admin API Endpoints (key ones)

```
GET  /admin/players                    # live player list
GET  /admin/players/{id}/state         # full player state + flags
POST /admin/players/{id}/teleport      # move player to room
POST /admin/players/{id}/flags         # set/clear flags
POST /admin/players/{id}/freeze        # freeze session for investigation

GET  /admin/audit?actor=&room=&type=&from=&to=   # filtered audit log
GET  /admin/audit/session/{correlation_id}        # full session replay

GET  /admin/world/rooms                # all rooms
PUT  /admin/world/rooms/{id}           # edit room (requires version field for optimistic lock)
POST /admin/world/rooms                # create room

GET  /admin/changesets                 # all changesets
POST /admin/changesets                 # create changeset
POST /admin/changesets/{id}/scan       # trigger conflict scan
POST /admin/changesets/{id}/promote    # promote to live

GET  /admin/clock                      # current world clock state
POST /admin/clock/pause
POST /admin/clock/resume
POST /admin/clock/time-ratio           # adjust game speed
POST /admin/clock/weather              # override weather

POST /admin/npcs/{id}/spawn            # spawn NPC in room
POST /admin/npcs/{id}/despawn
```

### Admin WebSocket Protocol (`/admin/ws`)

Separate from the player WebSocket. The admin client connects once after obtaining a JWT. The server pushes events as they occur; the client may send control commands.

**Server → Admin (push events)**

```json
{"type": "player_connected",    "player_id": "...", "username": "...", "room_id": "..."}
{"type": "player_disconnected", "player_id": "...", "status": "grace"}
{"type": "player_moved",        "player_id": "...", "from_room": "...", "to_room": "..."}
{"type": "audit_event",         "event": { /* AuditEvent fields */ }}
{"type": "clock_tick",          "hour": 14, "minute": 30, "day": 5, "season": "summer", "weather": "clear"}
{"type": "changeset_scan_done", "changeset_id": "...", "conflicts": [...], "status": "ready|conflicts"}
{"type": "build_mode_changed",  "mode": "notify|restrict|lockout|none"}
{"type": "error",               "code": "...", "detail": "..."}
```

**Admin → Server (control commands over WebSocket)**

Prefer REST for mutations; use WebSocket only for live-subscribe actions:

```json
{"type": "subscribe_audit",   "filter": {"actor": "...", "room": "...", "event_type": "..."}}
{"type": "unsubscribe_audit"}
{"type": "subscribe_clock"}
{"type": "unsubscribe_clock"}
```

### Admin Web Panel Screens

Served at `/admin` (separate HTML page from the game client). Guarded by a login screen that issues and stores the JWT in `sessionStorage`. All panels use the same Terminal Gothic CSS variables as the game client for visual consistency.

| Screen | Path | Min Role | Contents |
|---|---|---|---|
| **Dashboard** | `/admin` | observer | Live player table (name, room, session status, connected duration); auto-refreshes via WS push. |
| **Player Detail** | `/admin/players/{id}` | observer | Full state: flags, inventory, active quest progress, session history. Moderator+: teleport, flag edit, message, freeze buttons. |
| **Audit Log** | `/admin/audit` | observer | Paginated table with filter bar (actor, room, event type, time range). Row expand shows full payload. Correlation-ID link opens session replay. |
| **World Editor** | `/admin/world` | world-builder | Room list with search. Clicking a room opens an inline form (name, description, light level, flags, disabled commands, exits). Saves use optimistic-lock `version` field. Item and NPC sub-tabs. |
| **Changesets** | `/admin/changesets` | world-builder | List of changesets with status badges. Create button opens a name field. Per-changeset: scan button → conflict list with severity badges; promote button (disabled until READY). |
| **Clock Control** | `/admin/clock` | superadmin | Live clock readout (time, day, season, weather) fed by WS push. Pause/resume toggle; time-ratio slider (1×–120×); weather override dropdown. |
| **Admin Accounts** | `/admin/accounts` | superadmin | Admin user list; create/revoke; role assignment. |

### Textual TUI Screens

`admin/tui/app.py` — Textual application with a tab bar at the top for screen switching. Keyboard-driven; no mouse required. Credentials stored in `~/.config/lorecraft-admin/credentials.json` (mode `0600`); silent token refresh on startup.

| Screen | Key | Min Role | Contents |
|---|---|---|---|
| **Players** | `F1` | observer | `DataTable` of live players (name, room, status). Selected row: `t` teleport, `f` freeze, `m` message (moderator+). |
| **Audit** | `F2` | observer | Scrollable `RichLog` tailing live audit events. `/` opens filter bar (actor, room, event type). `r` fetches session replay for selected correlation ID. |
| **World** | `F3` | world-builder | Left pane: room list (`ListView`). Right pane: field editor (`Input` per field). `Ctrl+S` saves; conflicts shown inline. Tab to items/NPCs. |
| **Changesets** | `F4` | world-builder | List of changesets. `n` new, `s` scan, `p` promote, `Enter` expand conflicts. |
| **Clock** | `F5` | superadmin | Live `Label` for time/day/season/weather (WS push). `p` pause/resume, `+`/`-` adjust time ratio, `w` override weather (opens dropdown). |

---

## 22. Frontend UI

This section describes the complete browser experience. The implementation sequence is intentionally split in [Build Order Recommendation](#28-build-order-recommendation): first a minimal client harness to exercise WebSocket command dispatch during development, then feature-specific UI slices, then frontend polish.

### Visual Design: Terminal Gothic

The UI feels like a cathode-ray terminal possessed by a medieval scribe. Dark, functional, slightly beautiful in a decayed way.

**CSS Custom Properties (define these globally):**

```css
--bg-void:   #0a0a0f;   /* outer shell, modal backdrops */
--bg-panel:  #11111a;   /* panel backgrounds */
--bg-raised: #1a1a28;   /* input fields, hover states */
--phosphor:  #a8ff78;   /* primary accent — visited rooms, active states */
--amber:     #f0a500;   /* secondary — NPC dialogue, quest titles */
--muted:     #4a4a6a;   /* fog-of-war rooms, system text */
--danger:    #ff4444;   /* combat, errors */
--text-body: #c8c8d8;   /* default readable text */
--text-dim:  #6a6a8a;   /* timestamps, labels */
```

**Typography:**
- Display (room names, panel headers): `'IM Fell English'` (Google Fonts) — serif
- Body (narrative text, feed): `'Fira Code'` — monospace
- Signature element: minimap SVG has a CSS repeating-gradient scanline overlay (`repeating-linear-gradient` at 2px intervals, `rgba(0,0,0,0.15)`)

### Layout

**Desktop (≥ 1024px) — Three-Column Grid:**

```
┌──────────┬──────────────────────────────────┬───────────────┐
│          │                                  │               │
│  MINIMAP │       TEXT OUTPUT FEED           │   INVENTORY   │
│  (top)   │       (scrollable, grows)        │   (scrollable)│
│          │                                  │               │
│  STATUS  │                                  ├───────────────┤
│  BLOCK   │                                  │               │
│  (below  │                                  │  QUEST LOG    │
│  minimap)│                                  │               │
│          ├──────────────────────────────────┤               │
│          │  [command input __________] [>]  │               │
└──────────┴──────────────────────────────────┴───────────────┘
```

- Left column: `240px` fixed. Minimap ~200px height; status block below.
- Center column: `flex-grow: 1`. Feed `overflow-y: auto`. Input `position: sticky; bottom: 0`.
- Right column: `240px` fixed.
- Grid: `display: grid; grid-template-columns: 240px 1fr 240px; height: 100vh`

**Mobile (< 1024px) — Tab Bar:**
Collapse to single-column. Bottom tab bar: **Map · World · Bag · Quests**. "World" (feed + input) is the default active tab.

**Status Bar (top of center column):**
Displays: game time · weather · season · player count in room

### Map Rendering

- **Minimap panel:** SVG, ~200×200px. Shows visited rooms only. Fog-of-war on unvisited rooms (muted color, no exits shown).
- **Full-screen map modal:** Triggered by clicking minimap. Pan + zoom. Same fog-of-war logic.
- **Room coordinates:** Rooms have `map_x` / `map_y` / `map_z` fields. The map builds from `room_change` messages as the player explores. Room data is never sent in bulk — it accumulates incrementally. `build_map_data()`'s `level` filter restricts the minimap/full-map to the current room's `map_z`, so floors that reuse the same `(map_x, map_y)` footprint don't overlap.
- **Exits:** Rendered as invisible SVG hit-target lines between room nodes. Clickable to navigate.
- **Current room:** Highlighted in `--phosphor`.

### Text Feed

Per-message-type CSS styling:

| Message type | Style |
|---|---|
| `response` / narrative | Default body text |
| `room_event` (others' actions) | Italic, `--text-dim` color |
| NPC `dialogue` | Left border accent, name in `--amber` bold |
| Other players' speech | Name in username-hash-derived stable color |
| System / error | Monospace, `--danger` |
| Combat | Red-tinted |

**Markdown-lite:** Bold (`**text**`) and italic only. A 5-line regex pass — no full markdown parser.

### Dialogue Overlay

When a `dialogue` message arrives, render choices as numbered buttons overlaid on the feed. Disable the command input while dialogue is active. Clicking a choice number (or typing the number + Enter) sends `{"type": "dialogue_choice", "choice_index": N}` to the WebSocket.

### Multiplayer Presence

Other players in the same room are tracked in a presence sidebar (or inline in the status block). Each player gets a stable color derived by hashing their username.

### Reconnect Sync

On reconnect (or page refresh), the client sends `{"type": "reconnect_sync_request"}`. The server responds with a full snapshot of the player's current state: current room, inventory, quest state, time/weather, room occupants. Without this, a browser refresh leaves the UI blank until the next natural world event.

---

## 23. WebSocket Protocol

### Client → Server (Player WebSocket)

```json
{"type": "command", "text": "go north"}
{"type": "dialogue_choice", "choice_index": 1}
{"type": "reconnect_sync_request"}
{"type": "trade_offer", "target_player": "bob", "items": ["sword"]}
{"type": "trade_accept"}
{"type": "trade_decline"}
```

### Server → Client (Player WebSocket)

```json
{"type": "response", "messages": ["You head north."], "updates": {"inventory": [...]}}
{"type": "room_change", "room": {"id": "forest_path", "name": "...", "description": "...", "exits": {"north": "...", "south": "..."}, "map_x": 3, "map_y": 5, "map_z": 0, "occupants": [...]}}
{"type": "room_event", "messages": ["Bob arrives from the south."]}
{"type": "time_update", "hour": 14, "minute": 30, "day": 5, "season": "summer"}
{"type": "weather_change", "weather": "light_rain", "season": "summer"}
{"type": "quest_updated", "quest_id": "cave_rescue", "stage_id": "enter_cave", "title": "...", "description": "..."}
{"type": "quest_completed", "quest_id": "cave_rescue", "rewards": {"xp": 200}}
{"type": "dialogue", "npc_id": "blacksmith", "npc_name": "Gruff", "text": "What do you want?", "choices": [{"index": 1, "label": "I need a weapon."}, ...]}
{"type": "dialogue_end"}
{"type": "combat_update", "combat_id": "...", "log": [...], "your_hp": 75, "target_hp": 20}
{"type": "player_died", "respawn_in_seconds": 30}
{"type": "presence_update", "players_in_room": [{"name": "Bob", "id": "..."}]}
{"type": "system", "text": "The server is restarting in 5 minutes."}
{"type": "reconnect_sync", "player": {...}, "room": {...}, "inventory": [...], "quests": [...], "time": {...}}
```

**Key constraint:** `room_change` and `response` arrive independently and must not be coupled in the client message router. Handle each with a named updater function.

---

## 24. World Authoring (YAML)

YAML files live in a separate `world-content` git repository. They are the **authoring format** — not the runtime source of truth. The DB is.

### Import Flow

```
world-content repo (YAML)
    → world/validator.py (Pydantic schema + referential integrity checks)
    → world/loader.py (YAML → SQLModel objects → DB)
    → SQLite (runtime)
```

### YAML Schemas

```yaml
# rooms/tavern.yaml
rooms:
  - id: tavern_main
    name: The Rusty Flagon
    description: "Smoke-stained rafters. A fire crackles. The barkeep eyes you."
    map_x: 5
    map_y: 3
    area_id: town
    light_level: 1
    disabled_commands: []
    exits:
      - direction: north
        target_room_id: town_square
      - direction: east
        target_room_id: tavern_back_room
        locked: true
        key_item_id: tavern_key

# items/weapons.yaml
items:
  - id: sword
    name: Old Sword
    description: "Nicked but serviceable."
    takeable: true
    tradeable: true

  - id: sacred_gem
    name: Sacred Gem
    description: "It hums with an eerie light."
    takeable: false
    tradeable: false

# npcs/blacksmith.yaml (as shown in NPC section above)

# quests/cave_rescue.yaml (as shown in Quest section above)
```

### Validation on Import

The `world/validator.py` runs:
1. Pydantic schema validation (all required fields, correct types)
2. Referential integrity checks:
   - All exit `target_room_id` values reference real rooms
   - All NPC `dialogue_tree_id` values reference real dialogue trees
   - All quest conditions reference real rooms, items, flags
   - All `key_item_id` values reference real items
3. Errors halt import. Warnings are logged.

---

## 25. Testing Infrastructure

### Unit Tests (`tests/unit/`)

Pure function tests — no DB, no async, no WebSocket:
- Parser: `parse("n") == ParsedCommand(verb="go", noun="north", raw="n")`
- Command conditions: condition evaluation given a mock `GameContext`
- Dialogue walker: tree traversal, side effects, flag checks
- Rule engine: rule registration and evaluation
- Weather/season state machine: transition logic

### Integration Tests (`tests/integration/`)

Per-subsystem tests using in-memory SQLite. Test full command dispatch end-to-end:
```python
async def test_movement():
    db = create_in_memory_db()
    ctx = build_test_context(db, player_room="tavern_main")
    await engine.handle_command("go north", ctx)
    assert ctx.player.current_room_id == "town_square"
    assert ctx.messages == ["You head north."]
```

### Simulation Harness (`tests/simulation/`)

N scripted virtual players connecting via **real WebSockets** with randomized timing, designed to surface race conditions.

```python
class VirtualPlayer:
    async def run_script(self, script: list[str], timing_jitter_ms: int = 100):
        # Sends commands with random delays between them
        # Records all received messages
        # Asserts expected state at end of script
```

The simulation harness is also used for **audit log regression testing**: run a known script, capture the audit log, run it again after code changes, diff the logs.

### Test Fixtures

- `build_test_world()` — loads a minimal YAML world into in-memory SQLite
- `build_test_player()` — creates a player in a known room with known state
- `build_test_context()` — constructs a `GameContext` with all repos and services wired

---

## 26. Transaction & Event Lifecycle

**Every command follows this exact order. No exceptions.**

```
1. Parse raw input → ParsedCommand
2. Create TransactionContext (transaction_id, correlation_id, source_type)
3. Build GameContext
4. Evaluate command conditions (registry)
   → If blocked: write audit event (result=blocked), return error message, STOP
5. Consult Rule Engine
   → If blocked: write audit event (result=blocked), return error message, STOP
6. Execute command handler (calls into services)
7. Services write all state changes to DB
8. Commit DB transaction
9. Write AuditEvent(s) to audit.db
10. Emit domain events (bus.emit)
11. Event handlers run (quest checks, NPC reactions, scheduler entries)
12. Broadcast WebSocket messages to room
13. Send response to commanding player
```

**The golden rule:** Never tell clients something happened until the database says it happened. Steps 12 and 13 always happen after step 8.

---

## 27. Intentionally Deferred

These are real future concerns. Do not design or build them in the initial implementation. Leave seams (don't actively block them), but don't implement.

- **Party/group system** — following, shared loot, group XP
- **Generic entity/location abstraction** — solve movement/location/visibility once via shared services; shape TBD
- **Plugin/mod system**
- **Localization / string tables** — all output text is currently hardcoded English
- **Content moderation** — player-chosen names, chat content
- **Horizontal scaling** — single authoritative process for v1; WebSocket affinity becomes a problem at scale
- **Backup implementation** — backups must cover player state, world state, and audit history; automate before shipping
- **Monitoring & alerting implementation** — expose connected players, command throughput, scheduler health, DB latency, WebSocket health, world clock status
- **Magic resource model** — mana vs. cooldowns; intentionally unresolved
- **Scripted event sequences** — multi-step cutscenes; not tied to a single command response
- **World reset / seasonal events** — does the world ever fully reset?
- **PvP griefing prevention** — exit blocking, item hoarding
- **Anti-cheat** — command rate limiting, exploit detection via audit log

---

## 28. Gaps & Future Considerations

Lower-severity items identified during architecture review. None of these block Phase 1–9 implementation, but each should get a deliberate decision before it becomes load-bearing.

### Authentication & Security Hardening

**LAN-party auth hardening, if this ever leaves the LAN:** Local accounts (username + password) deliberately skip login rate limiting, password reset, and email verification — reasonable for a same-room trusted group, not reasonable if the server is ever exposed beyond that. Add login attempt throttling and consider the no-verification model before any non-LAN deployment; this is also the trigger point for adding Google OAuth as a second provider.

**Action:** When the engine moves to a real domain, add login attempt throttling and revisit the no-verification model before any non-LAN deployment.

### Command Throughput & Rate Limiting

**Distinct from the deferred anti-cheat item** — this is about basic stability. One player spamming commands shouldn't be able to degrade the experience for the room. A simple per-session token bucket in `ConnectionManager` would cover it.

**Action:** Implement a per-session token bucket (e.g., 1 command per 200ms, burst of 5) as a stabilization gate, not exploit detection.

### Audit Log Retention & Archival Policy

**audit.db grows forever with no stated rotation, compaction, or cold-storage plan.** Needs a policy before it becomes an operational problem.

**Action:** Before shipping, define a policy (e.g., archive events older than N days to compressed JSON, keep recent window queryable in audit.db).

### Changeset Staleness & Lifespan Management

**Carried over from Builder Mode design:** A DRAFT changeset and its builder clone can live indefinitely if abandoned. Need a TTL or staleness flag so abandoned drafts don't accumulate.

**Action:** Unresolved. A DRAFT changeset should have a policy (e.g., auto-flag stale after N days, require explicit renewal, or garbage-collect on server startup).

### Conflict Auto-Resolve Acknowledgment Policy

**Conflict scanner can surface auto-resolvable conflicts (player displacement, etc.).** Current doc text assumes acknowledgment is required; hasn't been explicitly confirmed whether auto-resolvable conflicts should require explicit sign-off or can pass through silently.

**Action:** Decide before Builder Mode ships: require explicit acknowledgment of auto-resolvable conflicts, or allow them through silently?

### Engine Code-Schema Migrations

**World Versioning (Section 19) handles content migrations (renamed flags/rooms in world data). It does not cover engine migrations** (e.g., adding a column to Player). A separate tool (Alembic, given the SQLAlchemy stack) is needed and isn't yet specified.

**Action:** Specify a migration strategy for engine-side schema changes (Alembic or equivalent) before any incompatible schema revision.

### Process Supervision

**The engine is explicitly single-process by design (Section 1).** That process needs a supervisor (systemd unit, container restart policy, or equivalent) with a health check, since there's no redundancy to fall back on.

**Action:** Document the expected deployment unit (systemd, container, etc.) and health-check endpoint before shipping to production.

---

## 29. Build Order Recommendation

Build in this sequence. The browser is split across the build order so client-facing protocol, context, event, and WebSocket behavior can be exercised as vertical slices instead of waiting until every gameplay subsystem exists. The early browser work is a harness, not the final frontend.

### Phase 1 — Foundation (no gameplay yet)
1. `config.py` — env-driven configuration
2. `models/` — all SQLModel table definitions; `create_tables()` at startup
3. `repos/` — thin data access wrappers
4. `game/context.py` — `GameContext` and `TransactionContext`
5. `game/connection_manager.py` — WebSocket connection pool
6. `game/events.py` — `GameEvent` enum and `EventBus`
7. `main.py` — FastAPI app, `/ws` WebSocket endpoint, startup/shutdown lifecycle
8. **Test:** Can a player register (first login creates the account), log in, obtain a ws ticket, connect a WebSocket, and send/receive JSON messages?

### Phase 2 — Command Dispatch
1. `game/parser.py` — raw text → `ParsedCommand`
2. `game/registry.py` — command registration, condition evaluation
3. `game/rules.py` — `RuleEngine` (empty rule set initially)
4. `game/engine.py` — `handle_command()` with the full 13-step lifecycle
5. `commands/meta.py` — `help`, `quit`
6. `commands/movement.py` — `go`, cardinal directions
7. `services/movement.py` — `MovementService`
8. **Test:** Player can connect, `go north`, see a response, and change rooms.

### Phase 2.5 — Minimal Web Client
1. Single HTML file with browser WebSocket client (login form → POST /auth/login, fetch ws-ticket, connect)
2. Message router for server response, room event, error, and structured update messages
3. Plain JavaScript state object for current room, feed, status, and connection state
4. Basic text feed and command input
5. Basic room/status display
6. **Test:** Browser smoke/end-to-end test can log in, connect, send a command, and render the response.

### Phase 3 — World & Time
1. `clock/world_clock.py` — clock loop as background asyncio task
2. `clock/weather.py` — weather/season state machine
3. `commands/inventory.py` — `look`, `take`, `drop`, `examine`, `inventory`
4. `services/inventory.py` — `InventoryService`
5. World YAML loader + validator
6. **Test:** Clock advances. Weather changes. Player can pick up items.

### Phase 3.5 — World UI
1. Inventory panel backed by inventory command responses and structured updates
2. Minimap SVG with fog-of-war
3. Basic layout refinement around the feed, room/status display, inventory, and minimap
4. **Test:** Browser can show room changes, inventory updates, and visited-room map state.

### Phase 4 — NPCs & Quests
1. `npc/dialogue.py` — dialogue tree walker
2. `npc/scheduler.py` — NPC movement via `HOUR_CHANGED`
3. `services/dialogue.py` — `DialogueService`
4. `commands/social.py` — `talk`, `say`
5. `services/quest.py` — `QuestService`
6. **Test:** Player can talk to an NPC, make choices, trigger quest flags.

### Phase 4.5 — Dialogue UI
1. Dialogue overlay with numbered choices
2. Command input disabled or mode-switched while dialogue is active
3. **Test:** Browser can render dialogue choices and send a dialogue selection.

### Phase 5 — Persistence & Safety
1. `services/save.py` — `SaveSlotService`, auto-save triggers
2. `commands/meta.py` — `save`, `load`
3. Disconnect handling — grace period, reconnect, system-controlled state
4. **Test:** Save mid-quest, disconnect, reconnect, load save — state is preserved.

### Phase 6 — Admin Tools
1. `admin/auth.py` — JWT, roles
2. `admin/api.py` — admin REST endpoints
3. `admin/websocket.py` — admin push WebSocket
4. `world/versioning.py` — changesets, conflict scanner, promotion
5. **Test:** Admin can view live players, edit a room, promote a changeset.

### Phase 7 — Frontend Polish
1. Three-column CSS Grid layout with custom-property theming (Terminal Gothic)
2. Full-screen map modal with pan/zoom
3. Responsive behavior for mobile tab layout and desktop grid layout
4. Visual polish for the Terminal Gothic theme
5. **Test:** Full browser end-to-end coverage: connect, explore, talk to NPC, fight.

### Phase 8 — Combat
1. `models/combat.py` — `CombatSession`, `CombatSlot`, `PlayerStats`
2. `services/combat.py` — `CombatService`, tick resolution, damage calc
3. `npc/combat_ai.py` — NPC decision logic
4. `commands/combat.py` — `attack`, `flee`
5. **Test:** Player can fight an NPC; HP changes; NPC can die and drop loot.

### Phase 8.5 — Combat UI
1. Combat message styling in the text feed
2. Combat status display for HP, active target, and turn/tick state
3. **Test:** Browser reflects combat start, combat updates, and combat end messages.

### Phase 9 — Player Interaction
1. `services/trading.py` — trade offer lifecycle
2. `commands/social.py` — `trade`, `pvp challenge`, `pvp accept`
3. PvP consent system
4. **Test:** Two players can trade items; PvP requires mutual consent.

---

*End of implementation guide. All systems described here have been designed across multiple architecture sessions. Where a system notes open questions (magic model, PvP griefing, changeset staleness), those are intentionally unresolved and should be designed before implementing that specific feature.*

---

## 28. Build Order Recommendation

Build in this sequence. The browser is split across the build order so client-facing protocol, context, event, and WebSocket behavior can be exercised as vertical slices instead of waiting until every gameplay subsystem exists. The early browser work is a harness, not the final frontend.

### Phase 1 — Foundation (no gameplay yet)
1. `config.py` — env-driven configuration
2. `models/` — all SQLModel table definitions; `create_tables()` at startup
3. `repos/` — thin data access wrappers
4. `game/context.py` — `GameContext` and `TransactionContext`
5. `game/connection_manager.py` — WebSocket connection pool
6. `game/events.py` — `GameEvent` enum and `EventBus`
7. `main.py` — FastAPI app, `/ws` WebSocket endpoint, startup/shutdown lifecycle
8. **Test:** Can connect a WebSocket? Can send/receive JSON messages?

### Phase 2 — Command Dispatch
1. `game/parser.py` — raw text → `ParsedCommand`
2. `game/registry.py` — command registration, condition evaluation
3. `game/rules.py` — `RuleEngine` (empty rule set initially)
4. `game/engine.py` — `handle_command()` with the full 13-step lifecycle
5. `commands/meta.py` — `help`, `quit`
6. `commands/movement.py` — `go`, cardinal directions
7. `services/movement.py` — `MovementService`
8. **Test:** Player can connect, `go north`, see a response, and change rooms.

### Phase 2.5 — Minimal Web Client
1. Single HTML file with browser WebSocket client
2. Message router for server response, room event, error, and structured update messages
3. Plain JavaScript state object for current room, feed, status, and connection state
4. Basic text feed and command input
5. Basic room/status display
6. **Test:** Browser smoke/end-to-end test can connect, send a command, and render the response.

### Phase 3 — World & Time
1. `clock/world_clock.py` — clock loop as background asyncio task
2. `clock/weather.py` — weather/season state machine
3. `commands/inventory.py` — `look`, `take`, `drop`, `examine`, `inventory`
4. `services/inventory.py` — `InventoryService`
5. World YAML loader + validator
6. **Test:** Clock advances. Weather changes. Player can pick up items.

### Phase 3.5 — World UI
1. Inventory panel backed by inventory command responses and structured updates
2. Minimap SVG with fog-of-war
3. Basic layout refinement around the feed, room/status display, inventory, and minimap
4. **Test:** Browser can show room changes, inventory updates, and visited-room map state.

### Phase 4 — NPCs & Quests
1. `npc/dialogue.py` — dialogue tree walker
2. `npc/scheduler.py` — NPC movement via `HOUR_CHANGED`
3. `services/dialogue.py` — `DialogueService`
4. `commands/social.py` — `talk`, `say`
5. `services/quest.py` — `QuestService`
6. **Test:** Player can talk to an NPC, make choices, trigger quest flags.

### Phase 4.5 — Dialogue UI
1. Dialogue overlay with numbered choices
2. Command input disabled or mode-switched while dialogue is active
3. **Test:** Browser can render dialogue choices and send a dialogue selection.

### Phase 5 — Persistence & Safety
1. `services/save.py` — `SaveSlotService`, auto-save triggers
2. `commands/meta.py` — `save`, `load`
3. Disconnect handling — grace period, reconnect, system-controlled state
4. **Test:** Save mid-quest, disconnect, reconnect, load save — state is preserved.

### Phase 6 — Admin Tools
1. `admin/auth.py` — JWT, roles
2. `admin/api.py` — admin REST endpoints
3. `admin/websocket.py` — admin push WebSocket
4. `world/versioning.py` — changesets, conflict scanner, promotion
5. **Test:** Admin can view live players, edit a room, promote a changeset.

### Phase 7 — Frontend Polish
1. Three-column layout with Tailwind CDN
2. Full-screen map modal with pan/zoom
3. Responsive behavior for mobile tab layout and desktop grid layout
4. Visual polish for the Terminal Gothic theme
5. **Test:** Full browser end-to-end coverage: connect, explore, talk to NPC, fight.

### Phase 8 — Combat
1. `models/combat.py` — `CombatSession`, `CombatSlot`, `PlayerStats`
2. `services/combat.py` — `CombatService`, tick resolution, damage calc
3. `npc/combat_ai.py` — NPC decision logic
4. `commands/combat.py` — `attack`, `flee`
5. **Test:** Player can fight an NPC; HP changes; NPC can die and drop loot.

### Phase 8.5 — Combat UI
1. Combat message styling in the text feed
2. Combat status display for HP, active target, and turn/tick state
3. **Test:** Browser reflects combat start, combat updates, and combat end messages.

### Phase 9 — Player Interaction
1. `services/trading.py` — trade offer lifecycle
2. `commands/social.py` — `trade`, `pvp challenge`, `pvp accept`
3. PvP consent system
4. **Test:** Two players can trade items; PvP requires mutual consent.

---

*End of implementation guide. All systems described here have been designed across multiple architecture sessions. Where a system notes open questions (magic model, PvP griefing), those are intentionally unresolved and should be designed before implementing that specific feature.*
