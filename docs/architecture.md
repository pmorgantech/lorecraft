# Lorecraft Architecture

A persistent, multiplayer browser-based text adventure engine. Players connect over
WebSocket to a shared world that runs on real time whether anyone is connected or not.
This is a guide to how the engine is put together today: the tier model, the core
primitives every feature builds on, the feature catalog, and the web layer.

> For deep dives beyond this overview: [`combat_design.md`](combat_design.md) (combat),
> [`discipline_ability_system.md`](discipline_ability_system.md) (progression),
> [`scripting_api.md`](scripting_api.md) (the `when:`/`do:` vocabulary),
> [`parser_and_commands.md`](parser_and_commands.md) (command parsing and authoring),
> [`admin_builder_guide.md`](admin_builder_guide.md) (running a server, building content),
> [`world_building.md`](world_building.md) (YAML authoring reference).

---

## Technology stack

| Layer | Technology |
|---|---|
| Backend language | Python 3.11+ |
| Web framework | FastAPI |
| Real-time | WebSockets (FastAPI native) |
| Database | SQLite (single file, single process) via SQLModel (Pydantic + SQLAlchemy) |
| World authoring | YAML files (`world_content/`), imported into SQLite |
| Frontend | Jinja2 templates + Alpine.js + HTMX + Tailwind CSS (CDN, no build step) |
| Admin TUI | Textual (optional `admin-tui` extra) |
| Testing | pytest (unit / integration / e2e-Playwright / simulation) |

## Design principles

- **Single authoritative process.** One game server, one event bus, one scheduler, one
  world clock, one SQLite database. No premature horizontal scaling.
- **Never tell clients something happened until the database says it happened.** State
  changes commit before WebSocket broadcasts go out.
- **World state is shared; player state is per-player.** These are never conflated.
- **The audit log is canonical.** Everything else is derived from it or consistent with it.
- **Mechanism vs. policy.** The engine (Tier 1) provides unopinionated primitives; features
  (Tier 2) supply the opinions, in data wherever a value is something an admin might
  plausibly want to retune without a deploy.

---

## Codebase layout

Three axes: a content-agnostic engine, a set of optional feature packages, and the web
hosts that compose them.

```
src/lorecraft/
├── engine/                 # Tier 1 — runs headless, imports nothing from features/ or webui/
│   ├── game/                context, registry, parser, events, rules, rng, checks,
│   │                        modifiers, meters, effects, traits, components, holders,
│   │                        broadcast, connection_manager, command_patterns, scripting/
│   ├── models/               player, world, items, meters, ledger, mobile, audit,
│   │                        session, scheduler, player_auth
│   ├── services/              item_location, meters, effects, ledger, scheduler,
│   │                        mobile_route, item_components, audit, save
│   ├── repos/                thin per-entity data access (player/room/item/npc/audit/…)
│   └── clock/               world_clock.py — the real-time loop
│
├── features/                # Tier 2 — 34 optional packages, each a FeatureManifest
│   └── <feature>/            models.py, service.py, repo.py, commands.py,
│                            conditions.py, … as needed
│
├── webui/                   # Web hosts — compose engine + features
│   ├── player/                Jinja/Alpine/HTMX player UI, session, auth
│   └── admin/                 REST API, push WebSocket, Textual TUI
│
├── commands/, services/container.py, world/, content/, tools/, main.py
│                           # Composition root — may import both features and webui;
│                           #   the engine may not import either.
```

Import direction is enforced by `tests/unit/test_tier_boundaries.py`: `engine/` depends
only on other `engine.*`, `lorecraft.types`, stdlib, and third-party. Features may import
`engine.*` and each other, never a web host. A feature's optional `presentation.py` is
imported only by the web host it plugs into.

### Codebase metrics (v0.151.1)

| Layer | Files | Lines of code |
|---|---:|---:|
| Tier 1 — `engine/` | 70 | 8,974 |
| Tier 2 — `features/` (34 packages) | 159 | 18,150 |
| Web — `webui/` | 33 | 7,680 |
| Composition root | 50 | 8,513 |
| **Total** | **312** | **43,317** |

Tier 2 is roughly 2× the size of Tier 1 — most of the engine's bulk is opinionated feature
content, not primitives. Feature packages average ~530 LOC each.

---

## Core engine primitives (Tier 1)

Everything a feature does routes through a small set of shared mechanisms. These are the
things to know before reading or writing feature code.

### GameContext

The object passed to every command handler and most service calls. Built fresh per
request; never stored globally. Carries the acting player, their room, all repos, the
event bus, the rule engine, the RNG, the active transaction, and output buffers
(`messages`, `room_messages`, `chat_outbox`, `updates`). Handlers call `ctx.say(...)`,
`ctx.tell_room(...)`, `ctx.emit(event, **payload)` rather than touching the database or
`ConnectionManager` directly.

### Command registry & parser

`CommandRegistry.register(verb, *aliases, scope=..., conditions=[...])` is a decorator —
features add verbs without touching engine dispatch code. The parser
(`engine/game/parser.py`) turns raw input into a `ParsedCommand` with a `verb` and a
`roles` dict (`object`, `target`, `recipient`, `instrument`, `direction`, …), plus a
`.noun` convenience property most handlers still consume for simplicity. See
[`parser_and_commands.md`](parser_and_commands.md) for the full role vocabulary and
authoring guide.

### Event bus

`EventBus` is synchronous, in-process, priority-ordered, and isolates one handler's
exception from the rest. Two event flavors: **notification events** (`PLAYER_MOVED`,
`ITEM_TAKEN`, …) that handlers observe without reporting back, and **work events**
(`SCHEDULED_JOB_DUE`, `COMBAT_TICK_DUE`) whose handlers return a result. `bus.on(event,
handler)` / `bus.emit(event, ctx)`; `bus.metrics_snapshot()` feeds the admin observability
panel.

### Rule engine

A veto/modify layer between commands and execution. `RuleEngine.register_rule(event_type,
rule_fn)`; a rule returns `RuleResult(allowed, reason, modified_payload)`. Services consult
it before committing a state change — this is how one feature can gate or reshape another's
action (e.g. "can't loot while in combat") without a direct dependency.

### Scheduler

`SchedulerService` is a DB-backed "run this at game-epoch T" primitive, restart-safe and
rule-agnostic — it fires `SCHEDULED_JOB_DUE` and knows nothing about what the job does.
NPC movement, timed quests, transit departures, and area respawns all sit on top of it.

### Modifiers, meters, and effects

- **`resolve(key, base, modifiers)`** (`engine/game/modifiers.py`) — stacks pluggable
  `ModifierSource`s (equipment, traits, terrain, active effects, consumable buffs) into one
  final value for a named check or stat. Any feature can register a source without the
  others knowing about it.
- **`MeterService`** — generic depleting/regenerating numeric tracks (HP, stamina, …),
  entity-type agnostic (`player`/`npc`/`room`).
- **`EffectService` / `ActiveEffect`** — clock-driven timed buffs/debuffs
  (`effect_key` + `payload` + `expires_at_epoch`), swept automatically on `TIME_ADVANCED`.
- **`checks.py::skill_check()`** — the one seeded roll-under resolver every dice-roll check
  in the game uses, keyed by an arbitrary `key=` string (e.g. `skill.perception`) so content
  can target a specific check with a modifier without engine changes.

### World clock

`WorldClock` is a DB-backed singleton (never per-player); an `asyncio` background loop
advances `game_epoch` at `time_ratio` × real seconds and emits `TIME_ADVANCED`,
`HOUR_CHANGED`, `DAY_CHANGED`, `SEASON_CHANGED`. Admins can pause it, change the ratio, or
override weather live, without restarting.

### Item location & ledger

`ItemLocationService` is the single source of truth for "where is this item instance right
now" (room, inventory, or container) — every feature that moves an item goes through it.
`LedgerService` is the analogous primitive for currency, backing `execute_exchange`-style
atomic transfers (shops, trades, quest rewards, loot).

### Transactions & audit

Every command, scheduler job, and admin action runs inside a `TransactionContext`
(`transaction_id`, `correlation_id`, `source_type`). All resulting audit events share that
`transaction_id`. Audit events are written unconditionally — including blocked commands —
so the audit log doubles as a post-hoc permissions debugger. State commits to the database
before any WebSocket broadcast goes out (Never tell clients something happened until the
database says it happened").

---

## Feature catalog (Tier 2)

34 self-contained packages under `features/`, each declaring a `FeatureManifest` and
auto-discovered by `discover_features()`. Grouped by concern:

**World & environment**
| Feature | What it does |
|---|---|
| `weather` | Weather/season transitions on the world clock; traveling weather fronts. |
| `celestial` | Moon phase and tide as content-facing world state. |
| `terrain` | Terrain type definitions and their registry. |
| `warmth` | Exposure/warmth resolution, feeding the fatigue loop. |
| `fatigue` | The `fatigue` meter and its skill-check penalty modifier. |
| `light` | Light-source fuel consumption. |

**Items & inventory**
| Feature | What it does |
|---|---|
| `inventory` | take/drop/get/put/give item management. |
| `items` | Item modifier compilation and item-behaviour effects. |
| `item_components` | Standard item component defs — durability, etc. |
| `containers` | Container move validation (open state, capacity). |
| `equipment` | Equipped-item modifier/trait sources and the equip/unequip flow. |
| `encumbrance` | Carry-weight resolution and its skill/modifier effects. |
| `consumables` | The eat/drink/quaff verbs and their item effects. |

**Character & progression**
| Feature | What it does |
|---|---|
| `character` | The character-sheet aggregator (disciplines/traits/reputation). |
| `disciplines` | The Discipline → Ability progression system's Tier 2 policy layer. See [`discipline_ability_system.md`](discipline_ability_system.md). |
| `progression` | XP/leveling policy — the opinionated layer over the generic leveling mechanism. |
| `traits` | Trait modifier/condition sources plus the shipped trait catalog. |
| `reputation` | Standing-gated command/dialogue conditions. |

**NPCs & dialogue**
| Feature | What it does |
|---|---|
| `npc` | Dialogue trees, dialogue conditions/side effects, NPC definitions. |
| `npc_ai` | The autonomous NPC agency loop — patrol/wander without a player actor. |
| `npc_memory` | Per-(player, NPC) memory keys backing `npc_remembers` conditions. |

**Economy & trade**
| Feature | What it does |
|---|---|
| `economy` | Shops — buy/sell, the `shop` holder type. |
| `bank` | Bank accounts, the `bank_account` holder type. |
| `trading` | Player-to-player trade offers. |

**Exploration & travel**
| Feature | What it does |
|---|---|
| `exploration` | Exit-discovery helpers and the forage/sense/pick verb family. |
| `movement` | Room-to-room movement — locks, terrain gating, exits. |
| `transit` | Vehicles/lines/stops running on scheduled routes (ferries, rail). |
| `marks` | Discovery-fed collectible badges with optional boons. |
| `hunts` | Time-boxed scavenger-hunt world events. |
| `spawns` | Area population / respawn controllers. |

**Social & combat**
| Feature | What it does |
|---|---|
| `follow` | Social movement (follow a player) and escort quests. |
| `combat` | Scheduled Intent combat. See [`combat_design.md`](combat_design.md). |
| `quests` | Quest definitions/progress and quest-condition predicates. |
| `context_commands` | Object-scoped verbs attached to specific rooms/items. |

---

## Combat, progression, and scripting — summary

These three subsystems are large enough to have their own reference docs; this is the
one-paragraph orientation for each.

**Combat** (`features/combat/`) uses a *Scheduled Intent* model: each action schedules its
own wind-up + recovery timer rather than a shared tick — an inactive actor has no scheduled
work at all. Combat is deliberately a supporting system (avoidance, persuasion, and flight
are first-class outcomes, not failure states). Full design: [`combat_design.md`](combat_design.md).

**Disciplines & Abilities** (`features/disciplines/`) is the single progression system:
players spend skill points on **abilities** grouped into themed **disciplines**, and grow a
per-discipline **proficiency rank** by use. The Tier 1 mechanism
(`engine/game/abilities.py`) is opinion-free — acquisition/usage/proficiency checks; the
Tier 2 content (`world_content/disciplines.yaml` + `abilities.yaml`) supplies what
disciplines and abilities actually exist. Full reference:
[`discipline_ability_system.md`](discipline_ability_system.md).

**Scripting** is not a bolted-on DSL — it's the same declarative substrate every feature
already uses (`SideEffectRegistry`, condition registries, `RuleEngine`, `ModifierRegistry`)
exposed to world content as `when:`/`do:` trigger blocks and NPC `behavior:` descriptors in
YAML, plus an actor-less `WorldContext` and a per-tick NPC agency loop (`npc_ai`) so those
same triggers can fire without a player command. The full, generated vocabulary reference
(every registered condition/effect, auto-kept in sync with the code) is
[`scripting_api.md`](scripting_api.md).

---

## Web layer

Two hosts compose the engine + features; the engine never imports either.

**`webui/player/`** — the player-facing HTMX/Alpine/Jinja client. `host.py` is a
multi-directory Jinja loader with a panel/slot registry so a feature's optional
`presentation.py` can register UI (e.g. transit's minimap panel) without the engine or
other features knowing. Multiple selectable themes/layouts exist (dock, e-reader,
immersive, classic CRT) over a shared token architecture, not one fixed layout. Player
auth is local username/password with JWT + short-lived WebSocket tickets.

**`webui/admin/`** — a REST API + a separate push WebSocket (never mixed with the player
socket) + an optional Textual TUI, all sharing one auth layer (JWT, role hierarchy:
observer → moderator → world-builder → superadmin). Routers: `accounts`, `analytics`,
`audit`, `clock`, `combat`, `economy`, `help`, `issues`, `news`, `observability`, `ops`,
`players`, `progression`, `world`. See [`admin_builder_guide.md`](admin_builder_guide.md)
for the operational tour.

### WebSocket protocol (player)

Client sends `{"type": "command", "text": "..."}` (plus `dialogue_choice`,
`reconnect_sync_request`). Server pushes are typed by `"type"`: `connected`,
`player_joined`/`player_left`, `feed_append`, `state_change`, `command_result`,
`reconnect_sync`, `system`, `error`, among others (`src/lorecraft/types.py`'s `Ws*`
TypedDicts are the authoritative list). `room_change`-equivalent state and narrative feed
arrive as independent message types and are never coupled in the client router.

---

## Persistence

Single SQLite file via SQLModel (Pydantic + SQLAlchemy), WAL mode. World content is
authored in `world_content/*.yaml` (`world.yaml` plus per-subsystem files —
`disciplines.yaml`, `abilities.yaml`, `weather_fronts.yaml`, `spawns.yaml`, `hunts.yaml`,
`marks.yaml`, `celestial.yaml`, `combat_actions.yaml`, `forage.yaml`) and imported into the
database; YAML is the authoring format, the database is the runtime source of truth.
Engine-side schema changes use a reflection-based additive-column auto-migration scanner —
adding a nullable/defaulted column to a model doesn't require a hand-written migration.

World versioning uses **changesets**: admins group edits into a named, versioned unit that
goes through a conflict scan before promotion, so in-flight edits never affect live players
until explicitly promoted. See [`world_versioning_changesets.md`](world_versioning_changesets.md).

Disconnect is not logout — a dropped WebSocket starts a grace period during which the
character remains in the world (combat pauses for that player's turns); only after the
grace period expires does the session become system-controlled. See
[`disconnect_handling.md`](disconnect_handling.md).

---

## Testing

| Tier | Location | Characteristics |
|---|---|---|
| Unit | `tests/unit/` | Pure functions, no DB, no async. |
| Integration | `tests/integration/` | In-memory SQLite, full command dispatch. |
| E2E | `tests/e2e/` | Real Chromium + real uvicorn, HTMX/Alpine/WebSocket DOM behavior. |
| Simulation | `tests/simulation/` | N scripted virtual players over real WebSockets, serial, for race conditions and audit-log regression. |

Run via `make test` (parallel, unit+integration), `make test-e2e`, `make test-simulation`,
`make typecheck`. See `AGENTS.md` for the full command reference.
