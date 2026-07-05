# Tier Classification — File by File

> **Reference:** See [`architecture_tiers.md`](architecture_tiers.md) for context on the three-tier model and current filesystem layout.

This document provides a quick lookup table for which modules are Tier 1 (engine primitives) and which are Tier 2 (optional features).

> **⚠️ Paths updated by the tier split (2026-07-05).** The tier *classifications* below still hold, but the files have physically moved (CHANGELOG 0.15.0–0.27.0). Translate the old paths in the tables using this map:
>
> | Old location | New home |
> |---|---|
> | `game/<tier-1 module>` (registry, context, events, engine, parser, grammar, holders, modifiers, components, rng, checks, effects, meters, transaction, diagnostics, rules, command_conditions, command_patterns) | `engine/game/` |
> | `game/traits` (registry only) | `engine/game/traits.py` (Tier 2 sources → `features/traits/`) |
> | `services/<tier-1>` (scheduler, item_location, meters, effects, save, mobile_route, audit, item_components-accessor, ledger) | `engine/services/` |
> | `repos/<tier-1>` (base, item, player, room, stack, npc, audit, meter, scheduler, ledger) | `engine/repos/` |
> | `models/<tier-1>` (world, player, player_auth, items, meters, scheduler, mobile, audit, session, ledger) | `engine/models/` |
> | `clock/world_clock` | `engine/clock/world_clock.py` |
> | every Tier 2 module (`game/*`, `services/*`, `models/*`, `repos/*`, `npc/*`, `clock/weather`, standard component/trait/holder/validator/condition modules, commands' feature verbs' services) | `features/<feature>/` — see the 24 packages listed in `architecture_tiers.md` §0 |
>
> Notable tier *re-classifications* the refactor made from the tables below: `services/item_components` (per-instance component-state accessor) and the whole `ledger` (service/model/repo) are **Tier 1** (the `GameContext` carries `LedgerService`); `movement` is **Tier 2** (terrain-gated, skill-checked, so it depends on the `terrain`/`skills` features); the `traits`/`skills` registries stay Tier 1 primitives while their standard content/sources are Tier 2.

---

## `src/lorecraft/game/` — Game Logic & Registries

| Module | Tier | Purpose |
|--------|------|---------|
| `registry.py` | 1 | Command registration and dispatch |
| `context.py` | 1 | `GameContext` — universal request object |
| `events.py` | 1 | Event bus + `GameEvent` enum |
| `engine.py` | 1 | Main command handling loop |
| `parser.py` | 1 | Text parsing to commands + `ParsedCommand` |
| `command_patterns.py` | 1 | Reusable command parsing patterns |
| `command_conditions.py` | 1 | Condition registry (for command gating) |
| `grammar.py` | 1 | Command parser helper (noun/verb/object extraction) |
| `holders.py` | 1 | Item holder type registry + validation |
| `modifiers.py` | 1 | Modifier stacking (add, mult, clamp) |
| `components.py` | 1 | Item component registry |
| `rng.py` | 1 | Seedable deterministic RNG |
| `checks.py` | 1 | Skill check formula (roll-under d100) |
| `effects.py` | 1 | Active effect definitions (buffs/debuffs) |
| `meters.py` | 1 | Meter (vital) definitions (HP, fatigue, etc.) |
| `traits.py` | 2 | Trait registry + modifier/condition sources; self-registers |
| `transaction.py` | 1 | Transaction context (audit logging) |
| `diagnostics.py` | 1 | Debug/diagnostic tools |
| `encumbrance.py` | 2 | Encumbrance/weight system |
| `exploration.py` | 2 | Exploration feature (fog reveal, etc.) |
| `equipment_slots.py` | 2 | Equipment slot definitions |
| `equipment_source.py` | 2 | Equipment modifier + trait source; self-registers |
| `equipment_validators.py` | 2 | Equip-slot move validators; self-registers |
| `container_validators.py` | 2 | Container open/capacity/nesting validators; self-registers |
| `standard_components.py` | 2 | Durability/openable/lit/container components; self-registers |
| `standard_traits.py` | 2 | Standard trait defs (boons/banes, innate source); self-registers |
| `fatigue_source.py` | 2 | Fatigue meter + skill-check modifier; self-registers |
| `bank_holders.py` | 2 | Bank account holder type; self-registers |
| `economy_holders.py` | 2 | Shop holder type; self-registers |
| `item_effects.py` | 2 | Item effect definitions (item perks) |
| `item_rules.py` | 2 | Item-related rules (bound item enforcement, etc.) |
| `reputation_conditions.py` | 2 | Reputation-based command conditions; self-registers |
| `skills.py` | 2 | Skill definitions |
| `terrain.py` | 2 | Terrain type definitions |
| `warmth.py` | 2 | Warmth/thermals system |

---

## `src/lorecraft/commands/` — Command Handlers

| Module | Tier | Purpose |
|--------|------|---------|
| `__init__.py` | Mixed | Command registration dispatcher |
| `movement.py` | 1 | `go`, `north`, `south`, etc. |
| `social.py` | 1 | `say`, `emote`, `who`, etc. |
| `meta.py` | 1 | `help`, `save`, `load`, `status`, `quit` |
| `report.py` | 1 | `/report` (out-of-character issue reporting) |
| `news.py` | 1 | `/news` (out-of-character news) |
| `inventory.py` | 2 | `take`, `drop`, `look`, `examine`, `get`, `put` |
| `character.py` | 2 | Character info (`skills`, `traits`, `stats`) |
| `condition.py` | 2 | Condition-related (`fatigue`, `sleep`, `warmth`) |
| `economy.py` | 2 | Economy (`sell`, `buy`, `appraise`, `list`) |
| `bank.py` | 2 | Banking (`deposit`, `withdraw`, `balance`) |
| `trade.py` | 2 | Player-to-player trading (`offer`, `accept`, `decline`) |
| `transit.py` | 2 | Transit vehicles (`board`, `disembark`, `schedule`) |
| `exploration.py` | 2 | Exploration (`journal`, `search`, `map`) |

---

## `src/lorecraft/services/` — Service Layer

| Module | Tier | Purpose |
|--------|------|---------|
| `scheduler.py` | 1 | Scheduled job dispatch + `SchedulerService` |
| `item_location.py` | 1 | Item stack movement + validation |
| `meters.py` | 1 | Meter (vital) service — adjust, regen, etc. |
| `effects.py` | 1 | Active effect service |
| `save.py` | 1 | Save slot snapshots |
| `mobile_route.py` | 1 | Scheduled route runner (for transit, NPCs) |
| `container.py` | 2 | `ServiceContainer` — wires all services |
| `movement.py` | 2 | Player movement + pathfinding |
| `inventory.py` | 2 | Inventory management (take, drop, etc.) |
| `quest.py` | 2 | Quest progress tracking |
| `trade.py` | 2 | Player-to-player trading |
| `economy.py` | 2 | Shops, buying, selling |
| `bank.py` | 2 | Bank accounts |
| `fatigue.py` | 2 | Fatigue-specific service |
| `exploration.py` | 2 | Exploration service |
| `journal.py` | 2 | Journal entries |
| `character_info.py` | 2 | Character info service |
| `light_fuel.py` | 2 | Light source fuel consumption |
| `restock.py` | 2 | NPC restock scheduler |
| `transit.py` | 2 | Transit system (vehicles, schedules) |

---

## `src/lorecraft/models/` — Database Tables

| Module | Tier | Purpose |
|--------|------|---------|
| `world.py` | Mixed | `Room`, `Exit`, `Item`, `NPC`, `WorldClock` (Tier 1); `ItemEffect`, `Skill` (Tier 2) |
| `player.py` | Mixed | `Player`, `PlayerStats` (core is Tier 1); skill/trait columns (Tier 2) |
| `audit.py` | 1 | `AuditEvent` (audit log) |
| `quest.py` | 2 | `Quest`, `QuestStage`, `PlayerQuestProgress` |
| `session.py` | 1 | `PlayerSession` (disconnect tracking) |
| `changeset.py` | 2 | `Changeset` (world versioning) |

---

## `src/lorecraft/repos/` — Data Access Layer

| Module | Tier | Purpose |
|--------|------|---------|
| `item_repo.py` | 1 | Item queries + matching |
| `player_repo.py` | 1 | Player queries |
| `room_repo.py` | 1 | Room queries |
| `stack_repo.py` | 1 | Item stack queries |

---

## `src/lorecraft/npc/` — NPC Subsystem

| Module | Tier | Purpose |
|--------|------|---------|
| `dialogue.py` | 2 | NPC dialogue trees (conditions, side effects) |
| `dialogue_conditions.py` | 2 | Dialogue condition predicates |
| `side_effects.py` | 2 | Dialogue side effects (narrative actions) |
| `scheduler.py` | 2 | NPC movement scheduling |

---

## `src/lorecraft/admin/` — Admin Tools

| Module | Tier | Purpose |
|--------|------|---------|
| All modules | 2 | Admin API, TUI, authentication — not core engine |

---

## `src/lorecraft/world/` — World Loading & Versioning

| Module | Tier | Purpose |
|--------|------|---------|
| `loader.py` | 1 | YAML → DB world import (core mechanism) |
| `bootstrap.py` | 1 | Initial world setup |
| `versioning.py` | 2 | World versioning + changesets |
| `validator.py` | 2 | Content validation (linting) |

---

## `src/lorecraft/web/` — Web Frontend & WebSocket

| Module | Tier | Purpose |
|--------|------|---------|
| All modules | 2 | Frontend UI, WebSocket handlers, routing — not core engine |

---

## `src/lorecraft/clock/` — Time & Weather

| Module | Tier | Purpose |
|--------|------|---------|
| `world_clock.py` | 1 | World clock runner + time advancement |
| `weather.py` | 2 | Weather/season system; self-registers |

---

## `world_content/` — Game Content

| File/Dir | Tier | Purpose |
|----------|------|---------|
| `world.yaml` | 3 | Rooms, items, NPCs, dialogue, quest definitions |
| `items/`, `npcs/`, `rooms/`, `quests/` | 3 | Supporting documentation for world.yaml |

---

## Key Insights

### Tier 1 Minimum Set (Cannot Remove)

To run *any* game with lorecraft, you need these:

**Game Logic:**
- `game/{registry, context, events, engine, parser, command_conditions, command_patterns}`
- `game/{holders, modifiers, components, rng, checks, traits (registry only), effects, meters}`
- `commands/{movement, social, meta, report, news}`

**Services:**
- `services/{scheduler, item_location, meters, effects, save, mobile_route}`

**Models & Repos:**
- Core tables + data access

**Time:**
- `clock/world_clock.py`

### Tier 2 Self-Registering Modules

These import triggers module-level registration:

```python
import lorecraft.game.traits                   # TraitSource registration
import lorecraft.game.fatigue_source          # Meter + condition
import lorecraft.game.equipment_source        # Modifier + trait sources
import lorecraft.game.equipment_validators    # Move validators
import lorecraft.game.container_validators    # Move validators
import lorecraft.game.standard_components     # Component defs
import lorecraft.game.standard_traits         # Trait defs
import lorecraft.game.bank_holders            # Holder type
import lorecraft.game.economy_holders         # Holder type
import lorecraft.game.reputation_conditions   # Conditions
```

Remove any of these imports from `main.py` to disable that feature (with caveats — see [`architecture_tiers.md`](architecture_tiers.md) § 5).

---

## Usage Tips

- **Finding a module's tier:** Ctrl+F this page or grep for the filename
- **Understanding dependencies:** If a Tier 2 module is removed, check `main.py` for its import; check `services/container.py` for its service
- **Adding new code:** Determine your tier first (see [`architecture_tiers.md`](architecture_tiers.md) § 8), then place the file accordingly
