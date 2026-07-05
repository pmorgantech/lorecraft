# Tier 1/Tier 2 Architecture: Current State & Extensibility

> **⚠️ Status update (2026-07-05): the tier split is now implemented in the directory structure.** Tier 1 lives in `src/lorecraft/engine/` and Tier 2 in `src/lorecraft/features/` (24 feature packages). The engine no longer imports `features/` at all (enforced by `tests/unit/test_tier_boundaries.py`), features load via manifests/`discover_features()`, and `ServiceContainer` builds conditionally from the enabled set. **Sections below that say the split is "not yet reflected" or "planned" describe the pre-refactor state** and are retained for historical context — see [`tier_split_refactor.md`](tier_split_refactor.md) (the single source of truth for this work) and `CHANGELOG.md` 0.15.0–0.27.0 for what shipped. The implemented layout is summarized in §0 immediately below.
>
> **Purpose:** This document describes how the lorecraft engine is layered into three tiers and how to extend or disable Tier 2 features.
>
> **Reference docs:** See [`engine_core.md`](engine_core.md) for authoritative tier definitions and primitive specs; [`feature-registration.md`](feature-registration.md) for the registration pattern; [`tier_modules.md`](tier_modules.md) for a file-by-file tier classification.

---

## 0. Implemented Layout (2026-07-05)

```
src/lorecraft/
├── engine/                 # Tier 1 — pure engine primitives, runs headless, imports no features/web
│   ├── game/               # registry, context, events, engine, parser, grammar, holders, modifiers,
│   │                       #   components, rng, checks, effects, meters, traits (registry only),
│   │                       #   command_conditions, command_patterns, diagnostics, rules, transaction
│   ├── services/           # scheduler, item_location, meters, effects, save, mobile_route, audit,
│   │                       #   item_components (state accessor), ledger
│   ├── repos/              # base, item/player/room/stack/npc/audit/meter/scheduler/ledger repos
│   ├── models/             # world, player, player_auth, items, meters, scheduler, mobile, audit,
│   │                       #   session, ledger
│   └── clock/              # world_clock (+ season calendar)
│
├── features/               # Tier 2 — 24 optional feature packages, each with a FeatureManifest
│   └── <feature>/          # __init__.py (manifest) + service/models/repo/commands/conditions/... as needed
│                           #   bank, character, containers, economy, encumbrance, equipment, exploration,
│                           #   fatigue, inventory, item_components, items, light, movement, npc,
│                           #   npc_memory, quests, reputation, skills, terrain, trading, transit,
│                           #   traits, warmth, weather
│
├── commands/               # composition layer: register_all_commands wires engine + feature verbs
│                           #   (step 9 will relocate verbs into engine/commands + features/*/commands)
├── web/                    # player + admin web host (step 10 → webui/player + webui/admin)
├── services/container.py   # ServiceContainer — composes engine + feature services (not in engine/)
├── models/, repos/         # residual non-feature tables/repos (combat stub, changeset, issue, news)
└── main.py, config.py, db.py, state.py, errors.py, types.py, world/, content/, admin/, analytics.py
```

---

## 1. The Three-Tier Model (Quick Recap)

| Tier | Purpose | Lives in | Can be disabled? |
|---|---|---|---|
| **1 — Engine Core** | Content-agnostic primitives + registries | `src/lorecraft/engine/` | No — foundational |
| **2 — Standard Modules** | Opinionated gameplay (equipment, trading, fatigue, etc.) | `src/lorecraft/features/<feature>/` | **Yes** — optional |
| **3 — Content** | Game-specific data (items, NPCs, world) | `world_content/*.yaml` | **Yes** — per-world |

The key principle: **Tier 1 never imports or depends on Tier 2.** Tier 2 registers itself through Tier 1 extension points (registries, rules, conditions, side effects, event handlers).

---

## 2. Current Filesystem Layout

**The tier split is NOT yet reflected in directory structure.** Both Tier 1 and Tier 2 live in `src/lorecraft/`, mixed together:

```
src/lorecraft/
├── game/                          # 40+ files, Tier 1 + Tier 2 mixed
│   ├── registry.py                # Tier 1: command registry
│   ├── context.py                 # Tier 1: GameContext
│   ├── events.py                  # Tier 1: event bus
│   ├── holders.py                 # Tier 1: item holder registry
│   ├── modifiers.py               # Tier 1: modifier stacking
│   ├── meters.py                  # Tier 1: meter definitions
│   ├── effects.py                 # Tier 1: active effects
│   ├── components.py              # Tier 1: item component registry
│   ├── rng.py                     # Tier 1: seedable RNG
│   ├── checks.py                  # Tier 1: skill check helper
│   ├── grammar.py                 # Tier 1: command parser helpers
│   ├── traits.py                  # Tier 2: trait registry + sources
│   ├── standard_traits.py          # Tier 2: shipped traits (boons/banes)
│   ├── equipment_source.py         # Tier 2: equipment modifier source
│   ├── equipment_validators.py     # Tier 2: equip-slot move validators
│   ├── container_validators.py     # Tier 2: container open/capacity validators
│   ├── standard_components.py      # Tier 2: durability/openable/lit/container
│   ├── fatigue_source.py           # Tier 2: fatigue meter + condition
│   ├── bank_holders.py             # Tier 2: bank account holder type
│   ├── economy_holders.py          # Tier 2: shop holder type
│   ├── item_effects.py             # Tier 2: item effect definitions
│   ├── item_rules.py               # Tier 2: item-related rules (bound, etc.)
│   ├── reputation_conditions.py     # Tier 2: reputation conditions
│   ├── skills.py                   # Tier 2: skill definitions
│   ├── terrain.py                  # Tier 2: terrain definitions
│   ├── warmth.py                   # Tier 2: warmth (thermals)
│   ├── exploration.py              # Tier 2: exploration feature
│   ├── command_conditions.py        # Tier 1: condition registry
│   ├── command_patterns.py          # Tier 1: command parsing patterns
│   ├── diagnostics.py              # Tier 1: debug tools
│   ├── encumbrance.py              # Tier 2: encumbrance system
│   ├── equipment_slots.py           # Tier 2: equipment slot definitions
│   └── __init__.py
│
├── commands/                       # Command handlers, Tier 1 + Tier 2 mixed
│   ├── movement.py                 # Tier 1: go, north, south, etc.
│   ├── social.py                   # Tier 1: say, emote, who
│   ├── meta.py                     # Tier 1: help, save, load, status
│   ├── inventory.py                # Tier 2: take, drop, look, examine
│   ├── character.py                # Tier 2: character info, skills
│   ├── condition.py                # Tier 2: condition (fatigue/sleep)
│   ├── economy.py                  # Tier 2: sell, buy, appraise
│   ├── bank.py                     # Tier 2: bank accounts
│   ├── trade.py                    # Tier 2: trading
│   ├── transit.py                  # Tier 2: transit/vehicles
│   ├── exploration.py              # Tier 2: exploration commands
│   ├── report.py                   # Tier 1: /report out-of-character
│   └── news.py                     # Tier 1: /news out-of-character
│
├── services/                       # Service layer, Tier 1 + Tier 2 mixed
│   ├── scheduler.py                # Tier 1: scheduled jobs
│   ├── container.py                # Tier 2: wires all services together
│   ├── item_location.py            # Tier 1: item stack movement
│   ├── movement.py                 # Tier 2: player movement + pathfinding
│   ├── inventory.py                # Tier 2: inventory management
│   ├── quest.py                    # Tier 2: quest progress
│   ├── trade.py                    # Tier 2: player-to-player trading
│   ├── economy.py                  # Tier 2: shops, buying, selling
│   ├── bank.py                     # Tier 2: bank accounts
│   ├── meters.py                   # Tier 1: meter (vital) service
│   ├── effects.py                  # Tier 1: active effects service
│   ├── fatigue.py                  # Tier 2: fatigue-specific service
│   ├── exploration.py              # Tier 2: exploration service
│   ├── journal.py                  # Tier 2: journal entries
│   ├── character_info.py           # Tier 2: character info service
│   ├── save.py                     # Tier 1: save slot snapshots
│   ├── light_fuel.py               # Tier 2: light source fuel
│   ├── restock.py                  # Tier 2: NPC restock scheduler
│   ├── mobile_route.py             # Tier 1: scheduled route runner
│   └── transit.py                  # Tier 2: transit system
│
├── models/                         # Database table definitions, Tier 1 + Tier 2 mixed
│   ├── __init__.py
│   ├── world.py                    # Tier 1 + Tier 2: Room, Item, NPC, etc.
│   ├── player.py                   # Tier 1 + Tier 2: Player, PlayerStats
│   ├── audit.py                    # Tier 1: audit log
│   └── [others omitted; see tier_modules.md]
│
├── repos/                          # Data access layer, mostly Tier 1
│   ├── item_repo.py                # Tier 1: item queries
│   └── [others omitted]
│
├── npc/                            # NPC subsystem, Tier 2
├── admin/                          # Admin tools, Tier 2
└── world/                          # World loading/versioning, mixed

world_content/
├── world.yaml                      # Tier 3: rooms, items, NPCs, layout
├── items/
├── npcs/
├── rooms/
└── quests/
```

---

## 3. How Tier 2 Features Currently Register

**There is no `features/` directory yet.** Instead, Tier 2 modules self-register via **side-effect imports in `main.py`**:

```python
# src/lorecraft/main.py — current wiring

import lorecraft.game.traits                   # Registers trait defs and trait sources
import lorecraft.game.fatigue_source          # Registers "fatigue" meter + skill-check modifier
import lorecraft.game.economy_holders         # Registers "shop" holder type
import lorecraft.game.bank_holders            # Registers "bank_account" holder type
import lorecraft.game.standard_components     # Registers component defs (durability, openable, etc.)
import lorecraft.game.equipment_source        # Registers equipment modifier + trait sources
import lorecraft.game.equipment_validators    # Registers equip-slot move validators
import lorecraft.game.container_validators    # Registers container move validators
import lorecraft.game.standard_traits         # Registers standard trait defs (boons/banes, innate source)
import lorecraft.game.reputation_conditions   # Registers reputation conditions

# Then services are instantiated and wired:
services = ServiceContainer.build()

# Then commands are registered:
from lorecraft.commands import register_all_commands
register_all_commands(registry, services)
```

**Key point:** Each import triggers module-level code that calls `get_registry()` and registers definitions. There's no explicit "enable/disable" mechanism — either the import is there or it isn't.

---

## 4. Tier 1 Boundaries (What Cannot Be Removed)

These are the true **engine-core primitives** that every game using lorecraft must have:

- **`game/registry.py`** — command registration and dispatch
- **`game/context.py`** — `GameContext`, the universal request object
- **`game/events.py`** — event bus and `GameEvent` enum
- **`game/engine.py`** — main command handling loop
- **`game/parser.py`** — text parsing to commands
- **`game/holders.py`** — item holder type registry + validation
- **`game/modifiers.py`** — modifier stacking (add, mult, clamp)
- **`game/components.py`** — item component registry
- **`game/rng.py`** — seedable deterministic RNG
- **`game/checks.py`** — skill-check formula
- **`game/effects.py`** — active effect definitions
- **`game/meters.py`** — meter (vital) definitions
- **`game/traits.py`** — trait registry and modifier/condition sources
- **`services/scheduler.py`** — scheduled job dispatch
- **`services/item_location.py`** — item stack movement and validation
- **`services/meters.py`** — meter service (adjust, regen, etc.)
- **`services/effects.py`** — active effect service
- **`services/save.py`** — save slot snapshots
- **`services/mobile_route.py`** — scheduled route runner (for transit waypoints)
- **`models/` (core tables)** — Room, Item, ItemInstance, ItemStack, Meter, ActiveEffect, etc.

---

## 5. Disabling a Tier 2 Feature (Current Method)

To disable a feature (e.g., equipment, fatigue, trading), you must:

### Example: Disable Equipment

1. **Remove the registration import** from `main.py`:
   ```python
   # Comment out:
   # import lorecraft.game.equipment_source
   # import lorecraft.game.equipment_validators
   # import lorecraft.game.standard_components  # (only if you don't want other components)
   ```

2. **Remove equipment-related commands** from `commands/__init__.py`:
   ```python
   # In register_all_commands():
   # from lorecraft.commands.inventory import register_equipment_commands
   # register_equipment_commands(registry, services.inventory)
   ```

3. **Remove services** from `ServiceContainer`:
   ```python
   # In services/container.py, remove or stub:
   # inventory: InventoryService = field(default_factory=InventoryService)
   ```

4. **Verify no hard-coded dependencies** (brittle point):
   - Grep for `equipment` or slot-related logic in other modules
   - E.g., `movement.py` might check encumbrance; `save.py` might snapshot equipment
   - These need to be made optional or gutted

5. **Test thoroughly** — implicit dependencies may exist

### Limitations of This Approach

- ❌ **Error-prone:** Dependencies are implicit, not enforced by the compiler or filesystem
- ❌ **Scattered:** You may miss a command, a service, a side-effect registration, or a hard-coded reference
- ❌ **No clean "feature toggles"** at startup (env var or config file)
- ❌ **No dependency declaration** (e.g., "fatigue depends on meters, which depends on modifiers")

---

## 6. Adding a Custom Tier 2 Feature (Current Method)

**See [`feature-registration.md`](feature-registration.md) for the full pattern.** In brief:

1. Create a new module under `src/lorecraft/game/` or `src/lorecraft/services/`:
   ```python
   # src/lorecraft/game/my_feature.py
   from lorecraft.game.modifiers import get_registry as get_modifiers_registry

   def register_my_feature() -> None:
       registry = get_modifiers_registry()
       registry.register_source(my_feature_modifiers)

   # Module-level side effect:
   register_my_feature()
   ```

2. Import it in `main.py`:
   ```python
   import lorecraft.game.my_feature  # triggers register_my_feature()
   ```

3. Register commands if needed:
   ```python
   from lorecraft.commands import my_feature_commands
   my_feature_commands.register(registry, services)
   ```

4. Add any services to `ServiceContainer`.

**This works, but it's not as clean as a dedicated `features/` directory.**

---

## 7. The `features/` Directory (✅ implemented 2026-07-05)

**This refactor has shipped** (CHANGELOG 0.15.0–0.27.0). All 24 Tier 2 modules now live in `features/<feature>/` packages, each exporting a `FeatureManifest`; the engine moved to `engine/`. The structure below is what the plan targeted and what now exists (feature verbs still register through the `commands/` composition layer pending step 9):

```
features/
├── equipment/
│   ├── __init__.py                 # register_equipment(app_state)
│   ├── models.py
│   ├── service.py
│   ├── commands.py
│   └── rules.py
├── trading/
│   ├── __init__.py
│   ├── service.py
│   ├── commands.py
│   └── ...
├── transit/
│   ├── __init__.py
│   ├── service.py
│   ├── commands.py
│   └── ...
├── fatigue/
│   ├── __init__.py
│   ├── service.py
│   ├── commands.py
│   └── ...
└── ...
```

Each feature would export a `register(app_state)` function that main.py calls conditionally:

```python
# main.py (future)
from features import equipment, trading, transit, fatigue

def lifespan(app):
    features_to_load = [equipment, trading, transit, fatigue]  # Config-driven
    for feature in features_to_load:
        feature.register(app_state)
```

**This is a large refactor** and is deferred until Tier 1 is fully stable (post-Sprint 21 in the roadmap).

---

## 8. Identifying Tier 1 vs Tier 2 in Code

When looking at a file, use these heuristics:

- **Tier 1:** Does it define a primitive that other Tier 2 features need? Does it have no game opinions?
  - ✅ `holders.py` — all games need holders; no opinion on what holders exist
  - ✅ `modifiers.py` — all games need modifier stacking; no opinion on what modifiers exist
  - ❌ `traits.py` — **mixed**: the registry is Tier 1, but trait definitions are Tier 2

- **Tier 2:** Does it assume specific game mechanics (combat, trading, skills, equipment)?
  - ✅ `equipment_source.py` — assumes equipment exists
  - ✅ `economy.py` — assumes a money/shop system
  - ✅ `fatigue_source.py` — assumes fatigue is a desired mechanic

- **Tier 3:** Is it world data (YAML, items, NPCs)?
  - ✅ `world_content/world.yaml`

See [`tier_modules.md`](tier_modules.md) for a detailed file-by-file breakdown.

---

## 9. Best Practices for Contributors

### When Adding New Code

1. **Ask: Is this a Tier 1 primitive or a Tier 2 feature?**
   - Tier 1: Can multiple games reasonably want *different* choices? If yes → Tier 2.
   - Tier 1: Does the game loop need it to run? (Scheduler, transactions, event bus) → Tier 1.

2. **If Tier 1:** Place it in `game/` or `services/` and register through an existing registry (no side-effect import needed).

3. **If Tier 2:**
   - Place it in a module that makes sense (e.g., `game/my_feature.py` for now; `features/my_feature/` after the refactor)
   - Register through existing Tier 1 registries (commands, conditions, modifiers, etc.)
   - Add a side-effect registration in the module
   - Import it in `main.py` (for now) or call its `register()` function

4. **Never import Tier 2 from Tier 1.** If you see `import lorecraft.game.equipment_source` in `game/context.py`, that's a bug.

### When Modifying Existing Code

- Check [`tier_modules.md`](tier_modules.md) to understand the module's tier
- If you're modifying Tier 1, ensure it has no game opinions
- If you're adding a feature to Tier 2, use registries instead of editing core

---

## 10. References

- **Engine Core Specs:** [`engine_core.md`](engine_core.md) § 1–3 (definitions and Tier 1 primitive specs)
- **Feature Registration Pattern:** [`feature-registration.md`](feature-registration.md) (how to add Tier 2 features)
- **Module Classification:** [`tier_modules.md`](tier_modules.md) (file-by-file tier breakdown)
- **Roadmap:** [`roadmap.md`](roadmap.md) (Tier 1 primitives are Sprints 16–21)
- **Architecture Overview:** [`architecture.md`](architecture.md) (predates the tier refactor; still useful for subsystem overview)

---

**Summary:** The tier model is well-designed but not yet fully separated in the codebase. Tier 2 features currently register via side-effect imports in `main.py`. To disable or customize Tier 2, you must remove imports and wire manually. The planned `features/` directory refactor will make this cleaner, but the architecture is sound now.
