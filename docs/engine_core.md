# Engine Core — the framework / game boundary & Tier 1 primitives

> **Status:** Implementation-ready design (2026-07-03, deep-dive revision). Anchor doc for the
> question *"where does the engine end and game customization begin?"* — and the **binding
> specification** for the Tier 1 engine-core band (roadmap
> [Sprints 16–21](roadmap.md#engine-core-band-tier-1-primitives--sprints-1621)).
>
> **Directive (product owner, 2026-07-03):** design Tier 1 (engine primitives) now, implement
> **all or most of Tier 1 before Tier 2** (the opinionated modules). §3 of this doc is the
> implementation spec; [`roadmap.md`](roadmap.md) sequences the build.
>
> **How to read this doc as an implementer:** §3.0 gives conventions that apply to every
> primitive. §3.1–§3.8 are per-primitive specs — schemas, APIs, invariants, migration blast
> radius, and tests. Where a spec says *"decided"*, do not re-open the decision during
> implementation; raise it for review instead.

---

## 1. The three tiers

"Engine vs game" collapses two different things. The useful split is three layers:

| Tier | Lives in | What it is | Opinion level |
|---|---|---|---|
| **1 — Engine core** | `src/lorecraft/` | Content-agnostic primitives + registries the loop runs on | **None** — no named skills, slots, factions, or damage formulas |
| **2 — Standard modules** | `features/*` (shipped, toggleable) | The mechanics most games want, with knobs | Opinionated *defaults*, replaceable per world |
| **3 — Content** | `world_content/*.yaml` + registered handlers | The actual slots, skills, prices, lines, numbers | Fully game-specific |

**"Some mechanics are universal, so include them"** lands in **Tier 2**: we ship equipment,
fatigue, shops, banks, transit, and a default combat ruleset — but each is built *only* on Tier 1
and registers itself through the same seams a third-party author would use. Nothing in Tier 2 is
reachable by hard-coded reference from Tier 1.

### Two litmus tests for the boundary

1. **"Could a different game reasonably want the opposite choice?"** Yes → Tier 2/3, never core.
   - *d20 combat?* A game could want real-time or narrative resolution → **Tier 2**.
   - *Items can carry per-instance state?* No game wants the opposite → **Tier 1**.
2. **"Does the game loop need it to run?"** Transaction/event/scheduler/dispatch → **Tier 1**.
   *Swords deal slashing damage* → **Tier 3 content**.

If a primitive passes test 1 (nobody wants the opposite) *and* is needed by ≥2 feature sprints,
it belongs in Tier 1 and should be designed here, not re-invented per sprint.

---

## 2. Tier 1 that already exists (foundation band output)

The foundation band ([Sprints 5–15](roadmap.md#sprint-5--error-handling--exception-hierarchy-))
already shipped much of the Tier 1 extension surface. **Do not rebuild these** — the new
primitives compose with them:

- **Registries** — `CommandRegistry` (`game/registry.py`), `CommandConditionRegistry`
  (`game/command_conditions.py`), dialogue `side_effects` + `conditions`, `RuleEngine`
  (`game/rules.py`). These are the primary "register, don't edit core" seam.
- **Event bus + `register(bus)` convention** (`game/events.py`) and one `ServiceContainer`
  (`services/container.py`).
- **Scheduler** (`services/scheduler.py`) — DB-backed `ScheduledJob`s
  (`id, job_type, due_at_epoch, status, payload`), dispatched as `SCHEDULED_JOB_DUE` on
  `TIME_ADVANCED`. Handlers receive a `SchedulerEventContext(game_engine, bus)` — **not** a
  `GameContext` — and filter on `event.payload["job_type"]`. Drives everything time-based
  (combat ticks, restock, corpse decay, transit, meter regen, effect expiry).
- **Unified command lifecycle + rollback-on-error**
  ([Sprint 14](roadmap.md#sprint-14--unify-command-lifecycle-)) — one transaction path;
  `GameContext.rollback_state_changes()` undoes half-applied state on a handler crash.
- **`build_game_context()` factory** (`game/context.py`) — the single `GameContext`
  construction path; both entry points call it.
- **Typed errors** (`errors.py`): `GameError` base with machine-readable `code`;
  `ValidationError`, `NotFoundError`, `PermissionError`, `ConflictError`.
- **Content validators** (`lorecraft.tools.validators`) and the world CLI.

### One trap in the existing surface: fail-open vs fail-closed

`CommandConditionRegistry.evaluate()` **fails open** — an unknown condition name returns
`allowed=True` (deliberate forward-compat for command definitions). That is fine for *availability*
gates (a typo just makes a command available) but **dangerous for security-relevant gates** (PvP
consent, "can't loot while in combat"). Rule of thumb, already implied by
[`feature-registration.md`](feature-registration.md) §"When Rules Matter":

- **Availability / UX gate** → a **condition** (fails open, cheap, forward-compatible).
- **Security / integrity veto** (consent, escrow, anti-dupe) → a **rule** (`RuleEngine` fails
  closed — a rule must *explicitly* `allow()`).

Design new gates on the correct side of this line.

---

## 3. Tier 1 primitive specifications (Sprints 16–21)

### 3.0 Conventions binding on every primitive

**Module placement.** Pure logic (no DB session) → `src/lorecraft/game/`. DB-touching data
access → `src/lorecraft/repos/`. Behavior orchestration → `src/lorecraft/services/`. Table
definitions → `src/lorecraft/models/` in a new file per subsystem (`items.py`, `meters.py`,
`ledger.py`, `mobile.py`), **each imported from `models/__init__.py`** — `db.py` creates tables
from SQLModel metadata, so an un-imported model silently never gets a table.

**Session & commit discipline.** Primitive APIs operate on the **caller's `Session`** (directly
or via a repo bound to it) and **never call `commit()`/`rollback()` themselves**. Inside a
command, the engine lifecycle owns commit/rollback (Sprint 14); inside scheduler work, the
handler owns its session. The two service shapes in the codebase:

- *Stateless per-call* (like `InventoryService`): methods take `ctx` or a `Session`. Use for
  `ItemLocationService`, `LedgerService`, `MeterService` command-path APIs.
- *Engine-holding schedulable* (like `SchedulerService`): constructed with the game `Engine`,
  exposes `register(bus)`, opens its own short-lived sessions inside event handlers, commits
  them itself. Use for the meter-regen / effect-expiry sweeps and `MobileRouteService`.

**Errors.** Mechanical failures raise typed errors: unknown holder/entity → `NotFoundError`,
bad arguments/slots → `ValidationError`, quantity/balance underflow or integrity violation →
`ConflictError`. Never return sentinel values for failures that must not be ignored.

**Two-layer gating (decided).** Tier 1 services enforce **mechanical invariants only**
(existence, quantity, balance, slot occupancy, cycle prevention, capacity via registered
validators). **Game-policy gates** (bound items can't be sold, can't loot in combat, PvP
consent) are `RuleEngine` rules checked by the **command/feature layer before** calling the
primitive. A primitive never consults the rule engine itself — it has no `ctx`.

**Events.** Primitives produce no narration (`ctx.say` is the caller's job). New `GameEvent`
enum members are listed per sprint below; payloads must be JSON-serializable (they flow into
`Event.payload: JsonObject` and the audit log). Reuse existing members where they exist —
e.g. the enum already has `PLAYER_DIED`, `PLAYER_RESPAWNED`, `SKILL_IMPROVED`,
`TRADE_COMPLETED`; do **not** invent `PLAYER_RESURRECTED`.

**Registries.** Follow the `game/command_conditions.py` pattern exactly: a module-level
registry instance, `register(...)` mutators, `get_registry()` accessor. Tier 1 registers
nothing game-flavored; Tier 2 features register at app lifespan per
[`feature-registration.md`](feature-registration.md).

**Determinism.** Any randomness goes through `GameRng` (§3.6). Any iteration whose order
reaches an event payload, audit record, or WS message must be deterministic (explicit
`ORDER BY` / sorted keys).

**Schema migration.** These sprints bump `WorldMeta.schema_version` **once, 1 → 2**, with the
Sprint 16 storage change. Dev flow: regenerate `test_dbs/` from YAML
(`scripts/import_world.py --fresh`). Existing-DB flow: one-shot
`scripts/migrate_schema_v2.py` (convert `Player.inventory` lists and `RoomItem` rows to
stacks; copy hp columns to meters in Sprint 19's amendment). `world/versioning.py` already
gates players on `world_schema_version` — reuse that seam, don't invent a parallel one.

**Definition of done, per sprint.** Unit tests for every invariant listed; integration tests
through `POST /command` **and** `/ws` where a command path changes; a simulation test where
multi-player atomicity is claimed; `make lint` + `make typecheck` (basedpyright `standard`)
clean; `CHANGELOG.md` + `docs/roadmap.md` updated; the consuming feature docs' assumptions
unchanged (or updated in the same PR).

---

### 3.1 Entity component / instance-state model — Sprint 16 (with §3.2)

*Consumers: [22](roadmap.md#sprint-22--standard-item-components--definition-fields) item state,
[23](roadmap.md#sprint-23--inventory--equipment) containers/durability,
[27](roadmap.md#sprint-27--character-condition-fatigue--sleep) condition,
[30](roadmap.md#sprint-30--quests--puzzles-depth) puzzles,
[31](roadmap.md#sprint-31--combat-core-services-supporting-system) corpses.*

Per-instance state expressed as **registered components**, not a fixed column set.

**Model** (`models/items.py`):

```python
class ItemInstance(SQLModel, table=True):
    id: str = Field(primary_key=True)                      # uuid4
    item_id: str = Field(foreign_key="item.id", index=True)
    state: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))
    # state is keyed BY COMPONENT NAME:
    #   {"durability": {"current": 480}, "openable": {"open": true}}
```

**Decided:** an instance is *identity + state only*. Its **location lives on its `ItemStack`
row** (§3.2) — never duplicated on the instance. (Supersedes the earlier draft in
[`inventory_equipment.md`](inventory_equipment.md) §7 that put `owner_type`/`owner_id` and
typed `durability`/`is_open`/`lit` columns on the instance; those become component state.)

**Component registry** (`game/components.py`):

```python
@dataclass(frozen=True)
class ComponentDef:
    name: str                                   # "durability", "openable", "container", ...
    applies_to: Callable[[Item], bool]          # e.g. lambda i: i.max_durability is not None
    initial_state: Callable[[Item], JsonValue]  # state fragment for a fresh instance
    validate: Callable[[JsonValue], list[str]]  # content-lint errors for a state fragment

class ComponentRegistry:
    def register(self, component: ComponentDef) -> None: ...
    def components_for(self, item: Item) -> list[ComponentDef]: ...
    def requires_instance(self, item: Item) -> bool:      # any component applies
    def __contains__(self, name: str) -> bool: ...

def get_registry() -> ComponentRegistry: ...
```

- **Tier 1 registers no components.** Durability/openable/lit/container/mechanism are Tier 2
  ([Sprint 22](roadmap.md#sprint-22--standard-item-components--definition-fields)); a
  game-specific "rune-charge" registers identically with zero core edits.
- **Instantiation rule (decided):** an item gets instances iff `requires_instance(item)` at
  spawn time, or a caller explicitly `materialize`s a stack (splitting one unit off a fungible
  stack into an instanced stack — needed when a generic torch becomes *this 40%-burned* torch).
- Component state is read by pluggable **conditions** and written by pluggable **side effects**
  (the existing Sprint 10 registries), plus direct service access for feature code.
- Content lint: `lorecraft.tools.validators` gains a pass that runs each registered
  component's `validate` over instance state and over any YAML-declared initial state.

**Why not typed columns:** columns bake game opinions into core and can't be extended by a
world author. A bare `state` bag alone is untyped mush; the component registry is the middle
path — validated, documented, *and* extensible.

---

### 3.2 Item location & ownership model — Sprint 16  ⚠️ highest-leverage

*Consumers: everything that moves an item — take/drop/give, equip, put/take-from, buy/sell,
P2P trade escrow, loot corpse, drop-on-death.*

**One** way to say where an owned item-stack lives, and **one** family of atomic operations to
move it. This **replaces** both `Player.inventory: list[str]` and `RoomItem` (resolution of
§4.a — decided: unify, don't layer).

**Model** (`models/items.py`):

```python
class ItemStack(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    item_id: str = Field(foreign_key="item.id", index=True)
    owner_type: str = Field(index=True)     # registered holder type: "player" | "room" | "container" | ...
    owner_id: str = Field(index=True)
    slot: str | None = None                 # sub-position within the holder (equipment slot); None = loose
    quantity: int = 1                       # CHECK (quantity > 0)
    instance_id: str | None = Field(default=None, foreign_key="iteminstance.id", unique=True)
```

**Invariants (enforce in code; add CHECK constraints where SQLite allows):**

1. `quantity >= 1` always; a stack at 0 is deleted, never stored.
2. `instance_id IS NOT NULL ⇒ quantity == 1` (instanced items never stack).
3. At most one stack per `(owner_type, owner_id, slot, item_id)` with `instance_id IS NULL`
   (fungible stacks auto-merge on move; instanced stacks never merge).
4. An `ItemInstance` is referenced by **exactly one** stack (the `unique=True` FK) — an
   instance with no stack is an orphan and a bug.
5. A container may not contain itself, directly or transitively (ancestor-walk check on every
   move into a `container` holder; violation → `ConflictError("conflict_container_cycle")`).
6. Moves are all-or-nothing within the caller's session (no partial multi-leg application —
   see `execute_exchange`, §3.7, which composes with this).

**Location & holder registry** (`game/holders.py`):

```python
@dataclass(frozen=True)
class Location:
    owner_type: str
    owner_id: str
    slot: str | None = None

@dataclass(frozen=True)
class HolderTypeDef:
    name: str
    exists: Callable[[Session, str], bool]          # does owner_id resolve?

class HolderRegistry:
    def register(self, holder: HolderTypeDef) -> None: ...
    def register_move_validator(
        self, owner_type: str,
        validator: Callable[[Session, Location, Item, int], None],  # raise typed error to veto
    ) -> None: ...
```

- **Tier 1 registers holder types** `player`, `room`, `container` (a container's `owner_id`
  is an `ItemInstance.id`). Tier 2 registers `shop` and `escrow`
  ([`trade_economy.md`](trade_economy.md)); a corpse is **not** a holder type — it is an
  ordinary `container` instance ([`death_resurrection.md`](death_resurrection.md)).
- **Move validators** are the mechanical-capacity hook: the Tier 2 container component
  registers one on `container` (capacity, open/closed); the equipment module registers one on
  `player` for `slot is not None` (valid slot key, slot occupancy, wearability). Tier 1 ships
  none. Validators must be deterministic and side-effect-free.

**Service** (`repos/stack_repo.py` for queries/row ops; `services/item_location.py` for
semantics):

```python
class ItemLocationService:
    def stacks_at(self, session: Session, loc: Location) -> list[ItemStack]:
        """All stacks at loc (slot=None means loose only; use stacks_for_owner for all).
        ORDER BY ItemStack.id — creation order; this IS the UI/disambiguation order."""
    def stacks_for_owner(self, session: Session, owner_type: str, owner_id: str) -> list[ItemStack]: ...
    def quantity_of(self, session: Session, loc: Location, item_id: str) -> int: ...
    def spawn(self, session: Session, item_id: str, loc: Location, quantity: int = 1) -> list[ItemStack]:
        """Create items from nothing (world import, loot, admin). If the item requires an
        instance (§3.1), creates `quantity` instances each on its own quantity-1 stack."""
    def destroy(self, session: Session, stack_id: int, quantity: int) -> None: ...
    def materialize(self, session: Session, stack_id: int) -> ItemStack:
        """Split 1 unit off a fungible stack into a new instanced stack."""
    def move(self, session: Session, stack_id: int, dest: Location, quantity: int) -> ItemStack:
        """THE move primitive. Validates: source exists & has quantity (ConflictError),
        dest holder exists (NotFoundError), registered validators pass, no container cycle.
        Splits when quantity < stack.quantity; merges into an existing fungible dest stack.
        Returns the destination stack. Never commits."""
```

- **Events (decided):** the primitive emits **nothing**. Callers keep emitting the existing
  domain events (`ITEM_TAKEN`, `ITEM_DROPPED`, `ITEM_GIVEN`, …) with their current payloads —
  no audit-trail change from this sprint, which is what keeps the Sprint 12 audit-regression
  suite green through the migration.
- **`Item.bound: bool = False`** is added here (resolution of §4.e/§4.f): the *field* is
  Tier 1 data; *enforcement* (can't drop/sell/trade; kept on death) is Tier 2 rules + policy.

**Migration blast radius (enumerated — every file below currently touches
`Player.inventory` or `RoomItem` and must be converted in this sprint; missing one is the
likeliest implementation bug):**

| File | What changes |
|---|---|
| `services/inventory.py` | take/drop/give/use resolve against `stacks_at(room)` / `stacks_for_owner(player)`; `_remove_from_room_and_carry`/`_remove_from_inventory_slots` collapse into `move()`; indexed selection (`2.coin`) enumerates instanced/fungible units in `stacks_at` order |
| `repos/item_repo.py` | matcher (`_best_matches`, `_any_matches`) stays; the `RoomItem`-shaped query helpers (`room_items`, `items_in_room`, `search_in_room`, `inventory_slots_matching`, `remove_from_room`, `increment_room_item`, `expanded_room_instances`) are reimplemented over `ItemStack` with the same signatures where possible, or moved to `StackRepo` with re-exports removed in the same PR |
| `game/context.py` | `get_inventory()` / `get_visible_entities()` read stacks |
| `game/command_conditions.py` | `item_in_inventory` condition checks `quantity_of(player_loc, item_id) > 0` |
| `commands/inventory.py`, `commands/__init__.py` | wiring only; verbs unchanged |
| `services/movement.py`, `services/quest.py`, `npc/side_effects.py` | `give_item`/`has_item`-style reads/writes go through the service |
| `main.py`, `web/frontend.py`, `web/session.py` | `push_update("inventory", …)` payload becomes `list[InventoryEntry]` — add `class InventoryEntry(TypedDict): item_id: str; name: str; quantity: int; instance_id: str | None` to the Sprint 6.4 TypedDicts; update the template/JS consumers of that update key |
| `services/save.py` | `SaveSlot.inventory` snapshot becomes a list of stack dicts; **loading a v1 snapshot (`list[str]`) converts on read** — old saves must not break |
| `world/loader.py` | room-item import creates stacks via `spawn()` (line ~119 today) |
| `world/versioning.py` | player-state carry-over across changesets reads/writes stacks |
| `admin/routers/players.py`, `admin/routers/world.py` | inventory/room-item admin views read stacks |
| `models/player.py` | **`Player.inventory` column is deleted** (not deprecated — foundation rule: no half-done seams) |
| `models/world.py` | **`RoomItem` table is deleted**; `Item` gains `bound` |

**Tests:** unit — every invariant above, split/merge, materialize, cycle guard, underflow;
integration — take/drop/give through both entry points, indexed & quantity selectors, save/load
round-trip incl. a v1 snapshot; simulation — the existing concurrent-`take` test must pass
unmodified in behavior (single winner, no duplication), plus a two-player give/drop race.

---

### 3.3 Meters / vitals — Sprint 19 (with §3.4)

*Consumers: [27](roadmap.md#sprint-27--character-condition-fatigue--sleep) fatigue,
[31](roadmap.md#sprint-31--combat-core-services-supporting-system) combat HP; latent: hunger,
mana, sanity, warmth.*

Named, bounded resources that drain/restore on the clock — **one primitive**, not one column
per resource.

**Model** (`models/meters.py`):

```python
class Meter(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    entity_type: str = Field(index=True)     # "player" | "npc" (open set)
    entity_id: str = Field(index=True)
    key: str                                  # "hp", "fatigue", ... (registered)
    current: float
    maximum: float
    # UNIQUE(entity_type, entity_id, key)
```

**Registry + service** (`game/meters.py` defs, `services/meters.py`):

```python
@dataclass(frozen=True)
class MeterDef:
    key: str
    base_maximum: Callable[[str, str, Session], float]   # (entity_type, entity_id) -> base max
    regen_per_tick: float = 0.0                          # applied on TIME_ADVANCED; 0 = none
    start_full: bool = True

class MeterService:                          # engine-holding schedulable (register(bus))
    def get(self, session, entity_type, entity_id, key) -> Meter:        # creates lazily from MeterDef
    def adjust(self, session, meter: Meter, delta: float) -> MeterChange:
        """Clamp to [0, maximum]. Crossing to 0 emits METER_DEPLETED (once per crossing,
        not per tick at 0). Recovery above 0 re-arms it."""
    def set_current(self, session, meter, value) / def recompute_maximum(...) -> None:
        """maximum = resolve(f"meter.{key}.max", base_maximum(...), modifiers) — §3.5;
        current is re-clamped, never scaled."""
    def _on_time_advanced(...):  # regen sweep, own session, commits itself
```

**New `GameEvent` members:** `METER_DEPLETED` (`entity_type, entity_id, key`),
`METER_RECOVERED` (crossing back above 0). Death is then Tier 2: the death module listens for
`METER_DEPLETED` with `key == "hp"` ([`death_resurrection.md`](death_resurrection.md)).

**HP migration (decided — definitional max stays, runtime current moves):**

- `PlayerStats.max_hp` and `NPC.max_hp` **stay** as the *definition/base* (YAML-authored, fed
  to `MeterDef.base_maximum`). `PlayerStats.current_hp` and `NPC.current_hp` **are deleted**;
  runtime hp is `Meter(entity, "hp")`.
- Registering the `"hp"` `MeterDef` itself is Tier 1-adjacent bootstrap: register it in
  `main.py`'s lifespan (it is the proof-of-primitive), `base_maximum` reading
  `PlayerStats.max_hp` / `NPC.max_hp`.
- Blast radius (complete — verified by grep): `world/loader.py` (NPC seeding, 2 sites),
  `admin/routers/world.py` (NPC listing), `world/validator.py` (NPC schema keeps `max_hp`),
  `services/save.py` (`stats_snapshot` drops `current_hp`, gains a `meters` dict; v1
  snapshots convert on load). Nothing in `web/` renders hp yet — no UI change.

---

### 3.4 Timed active effects — Sprint 19

*Consumers: [31](roadmap.md#sprint-31--combat-core-services-supporting-system) "weakened"
debuff, buffs, temporary traits; latent: potions, spells, weather effects.*

Buffs/debuffs with **clock-driven expiry**. Distinct from equipment effects (last *while
equipped*) and traits (semi-permanent): these fade on their own.

**Model + registry** (`models/meters.py`, `game/effects.py`, `services/effects.py`):

```python
class ActiveEffect(SQLModel, table=True):
    id: str = Field(primary_key=True)                    # uuid4
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    effect_key: str                                       # must be a registered EffectDef
    payload: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))  # instance params
    applied_at_epoch: float
    expires_at_epoch: float | None = None                 # None = until explicitly removed

@dataclass(frozen=True)
class EffectDef:
    key: str
    modifiers: Callable[[ActiveEffect], list[Modifier]]   # §3.5; may read payload for magnitude
    grants_traits: Callable[[ActiveEffect], list[str]] = lambda e: []

class EffectService:                          # engine-holding schedulable
    def apply(self, session, entity_type, entity_id, effect_key, *,
              duration_ticks: float | None, payload: JsonObject | None = None,
              clock_epoch: float) -> ActiveEffect     # unknown effect_key -> ValidationError
    def remove(self, session, effect_id) -> None
    def active_for(self, session, entity_type, entity_id) -> list[ActiveEffect]
    def _on_time_advanced(...):  # delete expired rows, emit EFFECT_EXPIRED; own session
```

**New `GameEvent` members:** `EFFECT_APPLIED`, `EFFECT_EXPIRED`, `EFFECT_REMOVED`
(`entity_type, entity_id, effect_key`).

**Trait registry** (also Sprint 19, `game/traits.py` — the "smaller surface" item):
`TraitDef(name, modifiers: list[Modifier], description)` + registry; a `TraitSource` protocol
(`traits_for(session, entity_type, entity_id) -> set[str]`) with registered sources. Tier 1
ships one source: active effects' `grants_traits`. Tier 2 adds equipment (`grant_trait`
effect descriptors) and innate traits (new `PlayerStats.traits: list[str]` JSON column, added
here, empty by default). Traits contribute their `modifiers` through §3.5.

---

### 3.5 Modifier resolution (runtime, stacked, capped) — Sprint 18

*Consumers: [23](roadmap.md#sprint-23--inventory--equipment) equipment effects,
[24](roadmap.md#sprint-24--traits--skills) traits/skills,
[25](roadmap.md#sprint-25--exploration-depth) terrain,
[27](roadmap.md#sprint-27--character-condition-fatigue--sleep) condition,
[28](roadmap.md#sprint-28--trading--economy) pricing.*

One resolver that stacks bonuses from many sources with a **defined order** (resolution of
§4.d). Generalizes `inventory_equipment.md`'s `EquipmentEffects.resolve()`.

**Spec** (`game/modifiers.py` — pure logic, no DB):

```python
ModifierKind = Literal["add", "mult", "clamp_min", "clamp_max"]

@dataclass(frozen=True)
class Modifier:
    key: str            # namespaced target: "stat.strength", "skill.perception",
                        # "meter.hp.max", "carry_capacity", "price.buy" ...
    kind: ModifierKind
    amount: float
    source: str         # provenance: "item:miners_helm", "trait:weakened", "effect:<uuid>"

def resolve(key: str, base: float, modifiers: Iterable[Modifier]) -> float:
    """Filter to key, then apply in FIXED bucket order:
       1. add:   value = base + sum(amounts)
       2. mult:  value = value * product(amounts)
       3. clamp: value = min(value, min(clamp_max)); value = max(value, max(clamp_min))
    Order WITHIN a bucket never matters (commutative). Returns float; the CONSUMER
    rounds/ints at its edge (prices round(), stats int(), meters keep float)."""
```

**Collection** — a `ModifierSource` protocol + registry (`modifiers_for(session, entity_type,
entity_id) -> Iterable[Modifier]`); `resolve_for(session, entity, key, base)` collects from
all registered sources then calls `resolve`. Tier 1 registers the **active-effect** and
**trait** sources (§3.4); Tier 2 registers equipment
([Sprint 23](roadmap.md#sprint-23--inventory--equipment)) and terrain/region sources.

**Decided semantics:**

- **Never stored, never cached across commands.** Recompute per use (perf is fine at this
  scale; correctness beats caching until proven otherwise).
- **Feature-level caps are the feature's job**: the barter module clamps *its own* discount
  input (≤ 25%) before emitting a `mult` modifier; the resolver's clamps are for final-value
  bounds (e.g. `meter.hp.max ≥ 1`). Don't encode game policy as resolver behavior.
- **Percentages are `mult` amounts** (0.75 = 25% off), never `add` of a fraction.

**Worked example (put in the unit tests):** base perception 30; helm `+5 add`; trait
`sure-eyed ×1.1 mult`; effect `weakened ×0.8 mult`; clamp_max 95 →
`(30+5) × 1.1 × 0.8 = 30.8` → consumer ints to 30.

---

### 3.6 Skill-check + seedable RNG — Sprint 17  ⚠️ audit-regression-critical

*Consumers: [24](roadmap.md#sprint-24--traits--skills) skills,
[25](roadmap.md#sprint-25--exploration-depth) search,
[28](roadmap.md#sprint-28--trading--economy) barter/appraise,
[31–32](roadmap.md#sprint-31--combat-core-services-supporting-system) combat hit/damage.*

**RNG** (`game/rng.py`):

```python
class GameRng:
    """Deterministic when seeded. The ONLY sanctioned randomness source in src/lorecraft."""
    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)          # the one permitted `random` import
    def randint(self, a: int, b: int) -> int: ...
    def uniform(self, a: float, b: float) -> float: ...
    def choice(self, seq: Sequence[T]) -> T: ...
    def chance(self, p: float) -> bool: ...          # uniform(0,1) < p
```

**Wiring (decided):**

- One instance per app, created in `create_app()` from new `Settings.rng_seed: int | None`
  (env `LORECRAFT_RNG_SEED`, default `None` → OS entropy), stored on `AppState`.
- `GameContext` gains a **required** field `rng: GameRng`; `build_game_context()` gains the
  required keyword param (both entry points + every test fixture updated — the factory being
  the single construction path is what makes this a bounded change).
- `SchedulerEventContext` gains `rng: GameRng` (scheduler-driven work rolls too).
- `clock/weather.py` (the only current `random` user; it already takes an injectable
  `choice`) is converted to receive the app rng.
- **Lint enforcement** (this is what keeps the invariant true forever) — `pyproject.toml`:

  ```toml
  [tool.ruff.lint.flake8-tidy-imports.banned-api]
  "random".msg = "use GameRng (ctx.rng) — module-level random breaks audit-regression"
  ```

  with a `# noqa: TID251` solely on the `import random` inside `game/rng.py`.

**Determinism contract:** same seed + same single-client script ⇒ identical draw sequence ⇒
identical audit trail (what `tests/simulation/test_audit_regression.py` diffs). Multi-player
interleaving legitimately changes the shared stream — audit-regression scripts stay
single-actor or fully-ordered; document this in the test module, not as an engine promise.

**Skill check** (`game/checks.py`, pure logic over §3.5 + rng):

```python
@dataclass(frozen=True)
class CheckResult:
    success: bool
    roll: int              # the raw d100
    effective: float       # resolved skill after modifiers
    target: int            # clamped success threshold actually used
    margin: int            # target - roll (positive = comfortable success)

def skill_check(rng: GameRng, *, base: float, difficulty: int,
                modifiers: Iterable[Modifier] = (), key: str = "check") -> CheckResult:
    """roll-under d100. effective = resolve(key, base, modifiers);
    target = clamp(round(effective) - difficulty, CHECK_FLOOR=5, CHECK_CEIL=95);
    success = rng.randint(1,100) <= target.
    difficulty 0 = routine; positive = harder. Floor/ceiling: there is ALWAYS
    a 5% chance either way — no impossible checks, no sure things (engine constants;
    a world that wants different bounds overrides via Tier 2 config later)."""
```

Skill *identity* (which skills exist, use-based improvement) is Tier 2
([Sprint 24](roadmap.md#sprint-24--traits--skills)); this helper only defines *how a check
resolves*, identically for perception, lockpicking, bartering, and combat-to-hit.

---

### 3.7 Value / ledger + atomic transfer — Sprint 20

*Consumers: [28](roadmap.md#sprint-28--trading--economy) coins/shops/banks,
[28](roadmap.md#sprint-28--trading--economy).4 P2P escrow,
[31](roadmap.md#sprint-31--combat-core-services-supporting-system).2 death coin-loss, robbers.*

A **coin balance as an attribute of any holder** (resolution of §4.c — a corpse holds coins
with zero special-casing) and one atomic multi-leg exchange for coins *and* items together.

**Model** (`models/ledger.py`):

```python
class CoinBalance(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    holder_type: str = Field(index=True)   # SAME holder registry as §3.2 (player, container, ...)
    holder_id: str = Field(index=True)
    balance: int = 0
    # UNIQUE(holder_type, holder_id); CHECK (balance >= 0)
```

**Decided:** there is **no `Player.coins` column** (supersedes `trade_economy.md` §2's draft).
A player's carried money is `CoinBalance("player", player_id)`; a bank account's money is
`CoinBalance("bank_account", account_id)` where the Tier 2 bank module owns the
`BankAccount` row and registers the `bank_account` holder type; a corpse's money is
`CoinBalance("container", corpse_instance_id)`. Rows are created lazily at first credit.

**Service** (`services/ledger.py`, stateless per-call):

```python
@dataclass(frozen=True)
class ExchangeLeg:
    give_from: Location            # §3.2 Location, slot ignored for coins
    give_to: Location
    coins: int = 0                                     # >= 0
    stacks: list[tuple[int, int]] = ()                 # (stack_id, quantity)

class LedgerService:
    def balance_of(self, session, holder_type, holder_id) -> int: ...
    def credit(self, session, holder_type, holder_id, amount: int) -> None:
        """Money creation — world import, admin, loot. The ONLY way coins enter play."""
    def execute_exchange(self, session, legs: Sequence[ExchangeLeg]) -> ExchangeReceipt:
        """VALIDATE EVERY LEG FIRST (balances sufficient, every stack present at its
        give_from with quantity, holders exist), THEN apply all mutations via §3.2 move()
        + balance updates. Any validation failure raises ConflictError with a code naming
        the failing leg; nothing is applied. Never commits — the caller's transaction
        (command lifecycle) makes the whole exchange atomic and rollback-safe."""
```

- **Escrow shape (decided):** `offer` moves **nothing** (it records intent); `accept`
  composes ONE `execute_exchange` with both directions as legs — this *is* the accept-time
  revalidation ([`trade_economy.md`](trade_economy.md) §8). Trade-policy gates (tradeable,
  bound, consent) are rules checked by the trade module **before** the call (§3.0 two-layer
  rule).
- **Conservation invariant (test as such):** across any `execute_exchange`, the sum of all
  `CoinBalance.balance` and the multiset of `(item_id, quantity)` are unchanged. Only
  `credit`/`spawn`/`destroy` may change totals, and each is audited by its caller.
- **Concurrency:** same posture as the Sprint 12 concurrent-`take` guarantee — one DB
  transaction per command, validate-then-apply inside it; add a simulation test with two
  players racing `accept` on the same offer (exactly one succeeds, totals conserved).
- **Events:** none from Tier 1. `TRADE_COMPLETED` already exists for the trade module;
  banking/death emit their own domain events.

---

### 3.8 Scheduled mobile entity ("moving room") — Sprint 21

*Consumers: [29](roadmap.md#sprint-29--transit--travel-systems) transit vehicles; latent:
wandering NPCs, patrols.*

The generic **route runner**: a state machine advancing an entity along a waypoint route on
scheduler time, with position interpolation for the minimap. Transit line *semantics*
(express/local, tickets, doors, weather) stay Tier 2 — they plug in via hooks.

**Model + spec** (`models/mobile.py`, `services/mobile_route.py`):

```python
@dataclass(frozen=True)
class Waypoint:
    position_id: str          # for transit: a station room_id
    x: int; y: int            # map coords for interpolation
    dwell_ticks: float        # wait at this waypoint before departing
    travel_ticks: float       # travel time to the NEXT waypoint

@dataclass(frozen=True)
class RouteSpec:
    route_id: str
    waypoints: tuple[Waypoint, ...]     # len >= 2
    reverses: bool = True               # ping-pong at ends; False + loop=True = circular
    loop: bool = False
    tick_pushes: int = 0                # interpolated position pushes per segment (0 = none)

class MobileRouteState(SQLModel, table=True):
    route_id: str = Field(primary_key=True)
    status: str = "at_stop"             # "at_stop" | "in_transit" | "halted"
    current_index: int = 0
    next_index: int = 1
    direction: int = 1                  # +1 / -1
    depart_epoch: float | None = None
    arrive_epoch: float | None = None
```

**Service** (engine-holding schedulable, exactly the `SchedulerService` shape):

```python
@dataclass(frozen=True)
class RouteHooks:
    may_depart: Callable[[Session, RouteSpec, MobileRouteState], str | None] = ...
        # None = go; a string = halt reason (weather!); runner re-checks after dwell_ticks
    on_depart: Callable[[Session, RouteSpec, MobileRouteState], None] = ...
    on_arrive: Callable[[Session, RouteSpec, MobileRouteState], None] = ...
    on_tick:   Callable[[RouteSpec, MobileRouteState, float], None] = ...   # progress 0..1

class MobileRouteService:
    def register(self, bus) -> None            # listens for SCHEDULED_JOB_DUE, job_type="mobile_route"
    def add_route(self, spec: RouteSpec, hooks: RouteHooks) -> None    # at lifespan
    def start(self, route_id) / def halt(self, route_id) / def resume(...) -> None
    def progress(self, state, now_epoch) -> float      # (now-depart)/(arrive-depart), clamped 0..1
    def position(self, spec, state, now_epoch) -> tuple[float, float]  # lerp between waypoint coords
```

**Mechanics (decided):**

- All timing runs through the existing `SchedulerService` with `job_type="mobile_route"` and
  payload `{"route_id": ..., "action": "depart" | "arrive" | "tick"}` — no second timing
  mechanism.
- The state machine: `at_stop` --(dwell elapses, `may_depart` → None)--> `in_transit`
  --(arrive job)--> `at_stop` at next waypoint; index/direction advance with reverse-at-ends
  or loop-wraparound. `may_depart` returning a reason sets `status="halted"` and reschedules
  a re-check; `resume` is also available for manual control.
- `on_tick` fires `tick_pushes` times per segment (scheduler jobs, **throttled by design** —
  never per world-tick) with interpolated progress; the Tier 2 transit module turns that into
  its `transit_update` WS message. Tier 1 pushes nothing to clients itself.
- Route *specs* are provided by the owner at lifespan (transit builds them from its YAML
  tables); Tier 1 persists only runtime `MobileRouteState`. A route whose spec disappears on
  restart is halted and logged, not crashed.

---

## 4. Cross-doc surprises caught by the vertical read — resolutions

Each of these was a seam that would have bitten mid-implementation. All are now **decided**
and folded into §3 and into the feature docs:

- **(a) Dual item representation** → **resolved** by §3.2: one `ItemStack` shape; fungible
  vs instanced is an engine-internal detail. `Player.inventory` and `RoomItem` are deleted,
  not wrapped.
- **(b) Non-seedable RNG breaks audit-regression** → **resolved** by §3.6: `GameRng` on
  `ctx`/scheduler context, ruff `banned-api` enforcement, determinism contract stated.
  [`combat_system.md`](combat_system.md) updated to roll through `ctx.rng`.
- **(c) Coins scalar vs coins-in-corpse** → **resolved** by §3.7: `CoinBalance` on any
  registered holder; no `Player.coins` column; corpse = container instance holder.
  [`trade_economy.md`](trade_economy.md) + [`death_resurrection.md`](death_resurrection.md)
  updated.
- **(d) Modifier stacking undefined** → **resolved** by §3.5: fixed `add → mult → clamp`
  bucket order; percentages are `mult`; feature caps live in the feature.
- **(e) `equipped_weapon_id` vs `Player.equipment` map** → **resolved** by §3.2: *both*
  drafts are superseded — equipment is a **slot-bearing `ItemStack`**
  (`Location("player", id, slot="main_hand")`); no JSON map, no ad-hoc column.
  [`combat_system.md`](combat_system.md) + [`inventory_equipment.md`](inventory_equipment.md)
  updated.
- **(f) `bound` flag assumed, not designed** → **resolved**: `Item.bound` added in §3.2
  (Sprint 16); enforcement is Tier 2 rules/policy.
- **(g) Fail-open conditions for integrity gates** → **resolved** as the §3.0 two-layer rule:
  primitives = mechanical invariants; features = `RuleEngine` (fail-closed) checked before the
  primitive call.
- **(h) Event-name drift** (found in this revision): `death_resurrection.md` invented
  `PLAYER_RESURRECTED`; the enum has had `PLAYER_RESPAWNED` since Phase 5. The doc now uses
  the existing member. Rule: check `game/events.py` before naming an event in a design doc.

---

## 5. How the feature band decomposes onto Tier 1

Every feature sprint becomes **primitive (Tier 1) + standard module (Tier 2) + content (Tier 3)**:

| Feature sprint | Tier 1 it needs | Tier 2 module | Tier 3 content |
|---|---|---|---|
| 22 item state | 3.1 component model, 3.2 stacks, (f) bound | durability/light/container components | which items, values |
| 23 equipment | 3.2 slots, 3.5 resolver | encumbrance bands, standard slot set | slot list, weights |
| 24 traits/skills | 3.6 skill-check, 3.4 trait registry, standing | use-based improvement curve | the skills/traits/factions |
| 25 exploration | journal, fog reveal, 3.5 (terrain mods), 3.6 | search-reveal, terrain table | hidden exits, terrain |
| 27 condition | 3.3 meters, 3.4 timed effects | fatigue/sleep ruleset | drain rates, per-world toggle |
| 28 trade | 3.7 ledger + exchange, 3.2 shop/escrow holders | shop/pricing/banks | currencies, prices, stock |
| 29 transit | 3.8 route runner, 3.2 (tickets are items) | express/local, tickets, weather, doors | the lines/stops |
| 30 quests/puzzles | existing registries + 3.1 state | branch/consequence engine | the quests/puzzles |
| 31–33 combat | 3.3 hp meter, 3.4 debuff, 3.6 RNG+checks, 3.7, 3.2 | combat ruleset, death policy, AI | numbers, behaviors |
| 34 PvP | 3.7 exchange, (g) consent rule | PvP ruleset | per-world toggle |

Note combat — the designated first consumer of the feature-registration pattern — is the *last*
consumer of a primitive stack that 22–29 quietly build. That's the argument for engine-first.

---

## 6. Build order → sprint mapping (decided 2026-07-03)

The engine-first band is sequenced in [`roadmap.md`](roadmap.md) as:

| Sprint | Spec | Rationale for position |
|---|---|---|
| [16](roadmap.md#sprint-16--item-locationownership--instance-state) | §3.1 + §3.2 | highest leverage; most expensive to retrofit; everything item-shaped sits on it |
| [17](roadmap.md#sprint-17--determinism-seedable-rng--skill-check) | §3.6 | small; keeps audit-regression green for every later random system |
| [18](roadmap.md#sprint-18--modifier-resolution) | §3.5 | stacking semantics must exist before the first consumer (equipment) |
| [19](roadmap.md#sprint-19--meters--timed-effects) | §3.3 + §3.4 (+ traits) | HP migration proves the meter primitive; effects need the resolver |
| [20](roadmap.md#sprint-20--ledger--atomic-transfer) | §3.7 | needs §3.2 locations; before trade/death |
| [21](roadmap.md#sprint-21--scheduled-moving-entity-moving-room) | §3.8 | most self-contained; only transit consumes it |

Dependencies within the band: 18 ← nothing; 19 ← 18 (effects emit modifiers); 20 ← 16
(exchange moves stacks); 21 ← nothing (scheduler only). 17 is independent — it can land
first or in parallel with 16.

---

## 7. Docs organization

The design docs sprawl across [`architecture.md`](architecture.md), [`roadmap.md`](roadmap.md), and
per-feature docs. That's fine **as long as they stay aligned and cross-linked**. Conventions:

- **`roadmap.md` is authoritative for sequencing** and links out to each feature doc from its
  sprint row. Each feature doc links back to its roadmap sprint.
- **`architecture.md` is authoritative for the built engine**; where it predates a re-sequence
  (e.g. §28's combat-first phase order) it says so and defers to the roadmap.
- **This doc (`engine_core.md`) is authoritative for the Tier boundary and the Tier 1
  schemas/APIs.** Feature docs reference the primitive they consume rather than re-specifying
  it; where a feature doc's earlier draft conflicts (superseded schemas are called out in §4),
  **this doc wins**.
- **`docs/implemented/`** — once a feature's sprints are done *and* the mechanics are described in
  the living guides (`architecture.md`, `user_guide.md`, `admin_builder_guide.md`), move its design
  doc there to mark it historical (candidates when their sprints close: `player_authentication.md`,
  `tooling_infrastructure.md`, `world_versioning_changesets.md`, `disconnect_handling.md`). Update
  inbound links on move. **Defer the actual moves until each feature lands** ("clean up afterward"),
  so we don't break links to still-active designs.

---

*See [`roadmap.md`](roadmap.md) for sequencing, [`feature-registration.md`](feature-registration.md)
for the registration pattern these primitives extend, and the per-feature docs
([`inventory_equipment.md`](inventory_equipment.md), [`combat_system.md`](combat_system.md),
[`trade_economy.md`](trade_economy.md), [`transit_systems.md`](transit_systems.md),
[`death_resurrection.md`](death_resurrection.md)) for the use cases each primitive serves.*
