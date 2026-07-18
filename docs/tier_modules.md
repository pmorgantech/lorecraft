---
kindle_doc_weaver: ignore
---

# Tier Classification — File by File

> **Reference:** See [`architecture_tiers.md`](architecture_tiers.md) for the three-tier model and [`architecture.md`](architecture.md) §4 for the full directory tree. This page is the quick per-module lookup.

The codebase is split on three axes (the tier split, CHANGELOG 0.15.0–0.32.0):

- **Tier 1 — `src/lorecraft/engine/`** — content-agnostic primitives. Runs headless; imports only `engine.*` + `lorecraft.types` (enforced by `tests/unit/test_tier_boundaries.py`).
- **Tier 2 — `src/lorecraft/features/`** — 24 optional feature packages, each declared by a `FeatureManifest`, discovered via `discover_features()`, and gated by the enabled set.
- **Web — `src/lorecraft/webui/`** — `player/` + `admin/` delivery hosts; compose engine + features.
- **Composition root** — `main.py`, `commands/`, `services/container.py`, `state.py`: may import features/web; the engine may not.

---

## Tier 1 — `src/lorecraft/engine/`

### `engine/game/` — primitives & registries

| Module | Purpose |
|--------|---------|
| `registry.py` | Command registration and dispatch |
| `context.py` | `GameContext` — universal request object |
| `events.py` | Event bus + `GameEvent` enum |
| `engine.py` | Main command handling loop (`CommandEngine`) |
| `parser.py` / `grammar.py` / `command_patterns.py` | Text → `ParsedCommand`; noun/verb/object extraction; reusable patterns |
| `command_conditions.py` | Condition registry for command gating |
| `holders.py` | Item holder-type registry + validation |
| `modifiers.py` | Modifier stacking (add → mult → clamp) |
| `components.py` | Item component registry |
| `rng.py` | Seedable deterministic RNG |
| `checks.py` | Skill-check formula (roll-under d100) |
| `effects.py` | Active-effect (buff/debuff) definitions |
| `meters.py` | Meter (vital) definitions (HP, fatigue, …) |
| `traits.py` | Trait **registry** + modifier/condition source types (standard content lives in `features/traits/`) |
| `transaction.py` | Transaction context (audit correlation) |
| `diagnostics.py` | Debug/diagnostic helpers |
| `broadcast.py` | Room broadcast of command effects |
| `connection_manager.py` | WebSocket connection pool + room broadcast (feature-agnostic) |

### `engine/services/`

| Module | Purpose |
|--------|---------|
| `scheduler.py` | Scheduled-job dispatch (`SchedulerService`) |
| `item_location.py` | Atomic item-stack movement + validation |
| `item_components.py` | Per-instance component-state accessor |
| `meters.py` / `effects.py` | Meter and active-effect services |
| `ledger.py` | Coin balances + atomic multi-leg `execute_exchange` |
| `mobile_route.py` | Scheduled route runner (transit vehicles, NPC patrols) |
| `save.py` | Save-slot snapshots |
| `audit.py` | Audit write + render |

### `engine/repos/` — data access

`base`, `player_repo`, `room_repo`, `item_repo`, `stack_repo`, `npc_repo`, `audit_repo`, `meter_repo`, `scheduler_repo`, `ledger_repo`.

### `engine/models/` — Tier 1 tables

`player`, `player_auth`, `world` (`Room`/`Exit`/`Item`/`NPC`/`WorldClock`/`WorldMeta`), `items` (`ItemStack`/`ItemInstance`), `meters`, `ledger`, `mobile`, `scheduler`, `audit`, `session`.

### `engine/clock/`

| Module | Purpose |
|--------|---------|
| `world_clock.py` | World clock runner + time advancement |

---

## Tier 2 — `src/lorecraft/features/`

Each feature is a self-contained package (a subset of `models.py` / `service.py` / `repo.py` / `commands.py` / `conditions.py` / `holders.py` / `presentation.py` / …) plus an `__init__.py` exporting a `FeatureManifest`. The 33 packages:

| Feature | Owns (highlights) |
|---------|-------------------|
| `movement` | Player movement (terrain-gated, skill-checked — hence Tier 2) |
| `inventory` | take/drop/look/examine/get/put; item-location commands |
| `npc` | Dialogue trees, conditions, side effects, NPC scheduler |
| `npc_memory` | Per-(player,NPC) memory table + conditions/side effects |
| `quests` | `Quest`/`QuestStage`/`PlayerQuestProgress`, quest conditions, timer |
| `trading` | Player-to-player `offer`/`accept`/`decline` escrow |
| `economy` | Shops (`buy`/`sell`/`list`/`appraise`), shop holder, restock scheduler |
| `bank` | Bank accounts (`deposit`/`withdraw`/`balance`), bank holder |
| `equipment` | Wear/wield slots, equipment modifier + trait sources, slot validators (deps: `traits`) |
| `traits` | Standard boon/bane trait definitions + innate source |
| `disciplines` | Disciplines & Abilities — unified Discipline → Ability model (replaced `skills`/`skill_tree`) |
| `progression` | Progression & Leveling — XP curve, level-up payouts (Tier 2 policy over engine deltas) |
| `exploration` | Search/fog-reveal, journal, cartography |
| `fatigue` | Fatigue meter + skill-check penalty; `rest`/`sleep`/`camp` |
| `warmth` | Warmth/thermals; `warmth_bonus` item effect |
| `terrain` | Terrain type definitions + travel gating |
| `weather` | Weather/season handlers; self-registers |
| `light` | Light-source fuel consumption |
| `reputation` | Reputation/standing conditions + adjust side effect |
| `containers` | Container open/capacity/nesting validators (deps: `item_components`) |
| `item_components` | Standard components (durability/openable/lit/container/mechanism) |
| `items` | Item effect + rule definitions (bound-item enforcement, perks) |
| `character` | Character-info service (`abilities`/`traits`/`stats` commands) |
| `encumbrance` | Encumbrance/weight bands |
| `transit` | Transit lines/stops, vehicle state machine, `presentation.py` minimap panel |
| `consumables` | Consumables — `eat`/`drink` and nourishment effects |
| `celestial` | Celestial Cycles — moon/sun phase state over the world clock |
| `npc_ai` | Autonomous NPC Behavior — wander/patrol route driving |
| `spawns` | Area Spawn Controllers — data-driven mobile/item spawns |
| `hunts` | Scavenger Hunts — spread-placement item hunts + coin reward tiers |
| `marks` | Marks & Attunements — player marks/attunement state + conditions |
| `follow` | Follow — party/leader follow movement |
| `context_commands` | Context-attached commands — verbs bound to rooms/items/NPCs |

`features/manifest.py` (`FeatureManifest`, registry) and `features/loader.py` (`discover_features` / `load_features` / `resolve_enabled_features` / `wire_features`) are the Tier 2 framework, not a feature.

---

## Web — `src/lorecraft/webui/`

| Path | Purpose |
|------|---------|
| `player/host.py` | `WebHost` — multi-dir Jinja `ChoiceLoader` + panel/slot registry |
| `player/__init__.py` | `create_web_host` / `load_feature_presentations` |
| `player/frontend.py` `session.py` `rendering.py` | Player routes, state resolution, HTML rendering |
| `player/auth.py` `player_auth.py` `password_policy.py` | Player login / JWT / WS tickets / password policy |
| `player/templates/` `static/` | Base shell templates + CSS/JS |
| `admin/api.py` `routers/*` | Admin REST API (players, world, clock, audit, accounts, issues, news, analytics) |
| `admin/websocket.py` `broadcaster.py` `auth.py` | Admin push WS + JWT |
| `admin/tui/` | Textual TUI client |

---

## Composition root & shared infrastructure

| Path | Tier | Purpose |
|------|------|---------|
| `main.py` | root | FastAPI app + startup lifespan; builds services/registries per enabled features |
| `state.py` | root | `AppState` (services, registries, `web_host`) |
| `commands/{meta,social,news,report}.py` + `__init__.py` | root | Shell/OOC verbs + `register_all_commands` (wires engine + feature verbs) |
| `services/container.py` | root | `ServiceContainer` — builds Tier 2 services per enabled set |
| `content/{issues,news,paths}.py` | mixed | Issues/news YAML↔DB sync |
| `world/{loader,bootstrap}.py` | 1 | YAML → DB import, initial setup |
| `world/{versioning,validator}.py` | 2 | World versioning + content linting |
| `tools/{world_cli,validators}.py` | 2 | World CLI + validation |
| `config.py` `db.py` `errors.py` `types.py` `observability.py` `analytics.py` | 1 | Cross-cutting infra |

---

## `world_content/` — Game Content (Tier 3)

| File/Dir | Purpose |
|----------|---------|
| `world.yaml` | Rooms, items, NPCs, dialogue, quests, economy, transit definitions |
| `items/`, `npcs/`, `rooms/`, `quests/` | Supporting documentation for world.yaml |

---

## Key Insights

### Tier 1 minimum set (cannot remove)

To run *any* game with lorecraft you need `engine/` in full: `game/` (registry, context, events, engine, parser, grammar, command_conditions/patterns, holders, modifiers, components, rng, checks, traits-registry, effects, meters, transaction, broadcast, connection_manager), `services/` (scheduler, item_location, item_components, meters, effects, ledger, mobile_route, save, audit), `repos/`, `models/`, `clock/world_clock`, plus the Tier 1 shell verbs `commands/{meta,social,news,report}`.

### Feature registration (no more side-effect imports)

Features are no longer enabled by `import lorecraft.game.<x>  # noqa` side effects in `main.py`. Each feature package's `__init__.py` builds a `FeatureManifest` and calls `register_feature(...)`; `discover_features()` imports the packages, `resolve_enabled_features()` picks the enabled set (`enabled_features` arg > `LORECRAFT_FEATURES` env > all), and `wire_features()` calls each manifest's `register_fn`. A feature's service is built only when enabled (`ServiceContainer` + the `main.py` feature-owned schedulables); a manifest's optional `presentation` module is loaded only by the web host. See [`archive/tier_split_refactor.md`](archive/tier_split_refactor.md) and `tests/integration/test_feature_toggling.py`.

### Usage tips

- **Finding a module's tier:** its directory *is* its tier — `engine/` = Tier 1, `features/` = Tier 2, `webui/` = web.
- **Disabling a feature:** pass `enabled_features=[…]` to `create_app` or set `LORECRAFT_FEATURES`; no code edits.
- **Adding new code:** decide the tier first ([`architecture_tiers.md`](architecture_tiers.md) §8), then place it in `engine/`, a `features/<feature>/` package, or a `webui/` host accordingly.
