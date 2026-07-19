---
kindle_doc_weaver: ignore
---

# Tier 1/Tier 2 Architecture: Current State & Extensibility

> **Status (updated 2026-07-05, Sprint 31.4): the tier split is fully implemented and this document reflects the shipped layout.** Tier 1 lives in `src/lorecraft/engine/` and Tier 2 in `src/lorecraft/features/` (33 feature packages); web hosts are in `src/lorecraft/webui/{player,admin}/`. The engine imports nothing from `features/` or `webui/` (enforced by `tests/unit/test_tier_boundaries.py`), features load via manifests / `discover_features()`, and `ServiceContainer` builds conditionally from the enabled set (`tests/integration/test_feature_toggling.py`). See [`archive/tier_split_refactor.md`](../archive/tier_split_refactor.md) for the migration history and `CHANGELOG.md` 0.15.0–0.32.0 for what shipped. The layout is summarized in §0 below.
>
> **Purpose:** This document describes how the lorecraft engine is layered into three tiers and how to extend or disable Tier 2 features.
>
> **Reference docs:** See [`engine_core.md`](engine_core.md) for authoritative tier definitions and primitive specs; [`archive/feature-registration.md`](../archive/feature-registration.md) for the registration pattern; [`tier_modules.md`](tier_modules.md) for a file-by-file tier classification.

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
├── commands/               # composition layer: shell/OOC verbs (meta, social, news, report) +
│                           #   register_all_commands, which wires engine + every feature's verbs
├── webui/                  # web hosts: player/ (HTMX UI + WebHost) + admin/ (console + TUI)
├── services/container.py   # ServiceContainer — composes engine + feature services (not in engine/)
├── content/, world/, tools/  # issues/news YAML↔DB, world loader/versioning, world CLI
└── main.py, config.py, db.py, state.py, errors.py, types.py, observability.py, analytics.py
```

**Feature UI seam (Sprint 31):** a feature MAY ship a `presentation.py`; the player web host (`webui/player.load_feature_presentations`) picks it up via `FeatureManifest.presentation`, registering panels on the `WebHost` (`webui/player/host.py`) — loaded only when the web host runs, never headless.

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

The three tiers are **physically separated** by directory (see §0 above for the tree, and [`architecture.md`](architecture.md) §4 for the annotated version):

- **`engine/`** — Tier 1 primitives. Runs headless; imports only `engine.*` + `lorecraft.types`.
- **`features/`** — 24 Tier 2 feature packages, each self-contained behind a `FeatureManifest`.
- **`webui/`** — the `player/` and `admin/` web hosts (compose engine + features).
- **composition root** — `main.py`, `commands/`, `services/container.py`, `state.py`.

The import direction (`engine ⇏ features ⇏ webui`) is enforced by `tests/unit/test_tier_boundaries.py`; a per-file tier classification lives in [`tier_modules.md`](tier_modules.md). The subsections that follow (§3 onward) describe the *mechanisms* — how features register, how to add/disable one — which are current; only the pre-refactor flat-tree snapshots have been removed.

---

## 3. How Tier 2 Features Register

Each feature package's `__init__.py` builds a `FeatureManifest` and calls `register_feature(...)`. At startup `main.py` resolves the enabled set and wires only those features onto the shared registries — no side-effect imports:

```python
# src/lorecraft/main.py — current wiring (abridged)

available_features = discover_features()                       # imports feature packages → manifests self-register
enabled = resolve_enabled_features(enabled_features, available_features.keys())
loaded = load_features(enabled, available_features)            # validates dependencies, orders them

services = ServiceContainer.build(enabled=set(loaded))        # gated services (None when off)
register_all_commands(state.registry, state.services, transit=transit_service)  # verbs guarded per service
wire_features(state, loaded)                                  # each manifest.register_fn(state)
```

Each `register_fn(state)` registers that feature's conditions, side effects, modifier/trait sources, holders, and event handlers onto the Tier 1 registries. A feature with only passive definitions (e.g. `weather`) may omit `register_fn`. Because registration is idempotent-by-key for keyed registries and flag-guarded for append registries (see [`archive/tier_split_refactor.md`](../archive/tier_split_refactor.md) migration note), the same feature can be wired once per process safely.

**Key point:** enabling/disabling is a single config decision (§5) — the enabled set drives discovery, service construction, command registration, and event wiring together.

---

## 4. Tier 1 Boundaries (What Cannot Be Removed)

These are the true **engine-core primitives** that every game using lorecraft must have:

- **`engine/game/registry.py`** — command registration and dispatch
- **`engine/game/context.py`** — `GameContext`, the universal request object
- **`engine/game/events.py`** — event bus and `GameEvent` enum
- **`engine/game/engine.py`** — main command handling loop
- **`engine/game/parser.py`** — text parsing to commands
- **`engine/game/holders.py`** — item holder type registry + validation
- **`engine/game/modifiers.py`** — modifier stacking (add, mult, clamp)
- **`engine/game/components.py`** — item component registry
- **`engine/game/rng.py`** — seedable deterministic RNG
- **`engine/game/checks.py`** — skill-check formula
- **`engine/game/effects.py`** — active effect definitions
- **`engine/game/meters.py`** — meter (vital) definitions
- **`engine/game/traits.py`** — trait registry and modifier/condition source types
- **`engine/services/scheduler.py`** — scheduled job dispatch
- **`engine/services/item_location.py`** — item stack movement and validation
- **`engine/services/meters.py`** — meter service (adjust, regen, etc.)
- **`engine/services/effects.py`** — active effect service
- **`engine/services/save.py`** — save slot snapshots
- **`engine/services/mobile_route.py`** — scheduled route runner (for transit waypoints)
- **`engine/models/` (core tables)** — Room, Item, ItemInstance, ItemStack, Meter, ActiveEffect, etc.

---

## 5. Disabling a Tier 2 Feature

Feature toggling is **config-driven** — no code edits. The enabled set is resolved by `resolve_enabled_features()` with this precedence:

1. the `enabled_features=[...]` argument to `create_app(...)` (tests, alternate entrypoints);
2. the `LORECRAFT_FEATURES` env var (comma-separated keys);
3. default — every discovered feature (behaviour-preserving "all on").

`enabled_features` / `LORECRAFT_FEATURES` is a **whitelist**, so to disable one feature you list the others. Example — run without transit:

```bash
LORECRAFT_FEATURES="movement,inventory,npc,quests,trading,economy,bank,equipment,traits,skills,exploration,fatigue,warmth,terrain,weather,light,reputation,containers,item_components,items,character,npc_memory,encumbrance"
```

What happens when a feature is off:

- its `register_fn` never runs (no conditions/side-effects/modifiers/holders registered);
- `ServiceContainer.build(enabled=...)` leaves its service `None`, so `register_all_commands` skips its verbs and `main.py` skips its schedulables;
- its optional `presentation.py` panel is never loaded.

**Dependencies are declared**, not implicit: `FeatureManifest.dependencies` (e.g. `equipment → traits`, `containers → item_components`), validated by `load_features()` — disabling a depended-on feature raises at startup rather than silently half-working. Coverage lives in `tests/integration/test_feature_toggling.py`.

> **Caveat.** A few features are near-core in practice (`movement`, `inventory`, `npc`): the engine boots without them, but a playable world usually wants them. Toggling is designed for the genuinely optional systems (`transit`, `economy`, `bank`, `fatigue`, `equipment`, …).

---

## 6. Adding a Custom Tier 2 Feature

**See [`archive/feature-registration.md`](../archive/feature-registration.md) for the full pattern.** In brief, create a package under `src/lorecraft/features/<my_feature>/`:

```python
# features/my_feature/__init__.py
from lorecraft.features.manifest import FeatureManifest, register_feature

def _wire(state) -> None:
    # register conditions / side effects / modifiers / holders / event handlers
    ...

manifest = FeatureManifest(
    key="my_feature",
    name="My Feature",
    dependencies=("skills",),          # optional; validated at load
    register_fn=_wire,                 # optional; None for definition-only features
    presentation="lorecraft.features.my_feature.presentation",  # optional feature UI
)
register_feature(manifest)
```

- Put verbs in `features/my_feature/commands.py` and register them from `register_all_commands` (guarded on the service being present).
- Put a service in `service.py` and add it to `ServiceContainer` (gated in `_FEATURE_GATED_SERVICES`) if commands/wiring need a shared instance.
- `discover_features()` finds the package automatically; enable it via the enabled set.

Because the package is self-contained and declared by a manifest, nothing in `engine/` changes and the feature is toggleable from day one.

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

2. **If Tier 1:** Place it in `engine/game/` or `engine/services/` and register through an existing registry. It must import only `engine.*` + `lorecraft.types`.

3. **If Tier 2:**
   - Create/extend a `features/<my_feature>/` package with a `FeatureManifest` (§6).
   - Register through existing Tier 1 registries (commands, conditions, modifiers, etc.) in the manifest's `register_fn`.
   - Gate any shared service in `ServiceContainer` and guard its verbs in `register_all_commands`.

4. **Never import Tier 2 from Tier 1.** If you see `import lorecraft.features.equipment...` in `engine/game/context.py`, that's a bug — and `tests/unit/test_tier_boundaries.py` will fail on it.

### When Modifying Existing Code

- Check [`tier_modules.md`](tier_modules.md) to understand the module's tier
- If you're modifying Tier 1, ensure it has no game opinions
- If you're adding a feature to Tier 2, use registries instead of editing core

---

## 10. References

- **Engine Core Specs:** [`engine_core.md`](engine_core.md) § 1–3 (definitions and Tier 1 primitive specs)
- **Feature Registration Pattern:** [`archive/feature-registration.md`](../archive/feature-registration.md) (how to add Tier 2 features)
- **Module Classification:** [`tier_modules.md`](tier_modules.md) (file-by-file tier breakdown)
- **Roadmap:** [`roadmap.md`](../project/roadmap.md) (Tier 1 primitives are Sprints 16–21)
- **Architecture Overview:** [`architecture.md`](architecture.md) §4 (annotated directory tree, kept in sync with this doc)

---

**Summary:** The tier model is fully separated in the codebase — Tier 1 in `engine/`, Tier 2 in `features/` (33 manifest-declared packages), web in `webui/`. Features register via `FeatureManifest` + `discover_features()`, and enabling/disabling is a config decision (`enabled_features` / `LORECRAFT_FEATURES`) with no code edits. The engine→features→web import direction is enforced by tests, and feature toggling is covered end to end.
