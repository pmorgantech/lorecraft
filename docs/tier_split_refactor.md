# Tier 1/Tier 2 Separation Refactor Plan

**Status:** In progress (branch `tier_split`)
**Scope:** Restructure code layout, feature loading, and service wiring to enforce Tier 1/Tier 2 boundary
**Estimated effort:** Large refactor (3–5 sprints)
**Tracking:** This document is the single source of truth for this work — it stays **off** `roadmap.md`. Progress is tracked in the checklist directly below.

---

## Progress Tracker

Legend: ✅ done · 🚧 in progress · ⬜ not started

**Sequencing decision (2026-07-04):** we build the **additive foundation first** (feature manifest + loader, then the config-driven feature list), *before* the risky directory moves. Rationale: the manifest system is new code that breaks nothing and everything else composes on top of it, so it can land green and reviewable while the codebase still runs on the current layout. The `engine/`/`features/`/`webui/` moves (originally "Phase 1") then happen against a working manifest backbone. Each step below is its own commit; the suite stays green at every commit.

**Migration note — `register()` must be idempotent (2026-07-04):** converting a module's import-time registration into a `register()` function means it can now be called more than once per process (each test file that needs it, plus app startup, sharing a pytest-xdist worker). Registries that store by **name/key** (holders, components, command/dialogue/quest conditions, side effects, meters) are naturally idempotent — re-registering overwrites. But registries that **append** (modifier sources, trait sources, holder move-validators) will double-register and silently double their effect (e.g. an equipment stat bonus applied twice). For those, guard `register()` with a module-level `_registered` flag. When migrating a feature, check whether its target registry appends or replaces.

| # | Step | Phase | Status |
|---|------|-------|--------|
| 0 | Branch, doc rename, progress tracker, changelog | setup | ✅ |
| 1 | `features/manifest.py` — `FeatureManifest`, `FEATURE_REGISTRY`, `register_feature` + unit tests | 2 | ✅ |
| 2 | `features/loader.py` — `discover_features` + `load_features` (dependency validation) + unit tests | 2 | ✅ |
| 3 | Feature-config resolution (`LORECRAFT_FEATURES` env / `create_app` arg) + `discover`/`load`/`wire` in `create_app`, defaulting to "all on" (behavior-preserving) | 3 | ✅ |
| 4 | Wrap **one** existing self-registering feature (`reputation`) in a manifest as a vertical slice, loaded via the new path | 2/3 | ✅ |
| 5 | Migrate remaining Tier 2 self-registrations to manifests; delete side-effect imports from `main.py` | 3 | ✅ |
| 6 | `ServiceContainer` builds conditionally from enabled features (economy/bank/fatigue gated; container goes fully feature-driven in step 8) | 3 | ✅ |
| 7 | Create `engine/` package; move Tier 1 modules; update imports (batched) | 1 | 🚧 |
| 7a | ↳ `engine/game/` — 18 Tier 1 game modules moved; imports rewritten (0.15.0) | 1 | ✅ |
| 7b | ↳ `engine/services/` + `engine/repos/` — Tier 1 services/repos moved (0.16.0) | 1 | ✅ |
| 7c | ↳ `engine/clock/world_clock` moved; season calendar decoupled from weather (0.17.0) | 1 | ✅ |
| 7d | ↳ `engine/models/` (Tier 1 tables) + `engine/npc/` (dialogue engine) — deferred; models split sequenced with step 8 | 1/2 | ⬜ |
| 8 | Move Tier 2 modules into `features/<x>/` packages | 2 | ✅ |
| 8a | ↳ Tier 1 models → `engine/models/` (folded in per sequencing decision) (0.18.0) | 1/2 | ✅ |
| 8b | ↳ `reputation` fully co-located (conditions/service/models/repo) — first vertical slice (0.19.0) | 2 | ✅ |
| 8c | ↳ traits (split: registry stays Tier 1), equipment, fatigue, item_components, containers co-located (0.20.0) | 2 | ✅ |
| 8d | ↳ economy, bank, npc_memory, skills, exploration co-located (0.21.0) | 2 | ✅ |
| 8e | ↳ warmth, terrain, weather, light, encumbrance co-located (0.22.0) | 2 | ✅ |
| 8f | ↳ transit, quests, trading, inventory co-located (0.23.0) | 2 | ✅ |
| 8g | ↳ ledger→engine (Tier 1 fix), items + character features, restock→economy (0.24.0) | 1/2 | ✅ |
| 8h | ↳ movement (Tier 2: terrain/skill-gated) + npc/dialogue subsystem co-located; step 8 done (0.25.0) | 1/2 | ✅ |
| 9 | Commands: dissolve shared `commands/`; engine built-ins → `engine/commands/`, feature verbs → their feature | 4 | ⬜ |
| 10 | Extract web into `webui/player/` + `webui/admin/`; add `WebHost` (multi-dir Jinja loader + panel/slot registry) | 4 | ⬜ |
| 11 | Implement the `presentation.py` seam (§1c); prove with `transit` minimap | 4 | ⬜ |
| 12 | Import-direction lint + CI checks; feature enable/disable integration tests | 5 | 🚧 |
| 12a | ↳ import-direction boundary test (`test_tier_boundaries.py`) — engine⇏features/web, features⇏web (0.27.0) | 5 | ✅ |
| 12b | ↳ feature enable/disable integration tests | 5 | ⬜ |
| 13 | Graduate §1c into `admin_builder_guide.md`; update `architecture_tiers.md`, `tier_modules.md`, `AGENTS.md` | 5 | ⬜ |

---

## Executive Summary

The lorecraft engine is well-designed at the architectural level (see `architecture_tiers.md`), but the **implementation does not yet match the design**. Tier 1 (engine primitives) and Tier 2 (optional features) are mixed together in the same directories, and features are loaded via brittle side-effect imports in `main.py`. This plan refactors the codebase to:

1. **Physically separate Tier 1 and Tier 2** via directory structure
2. **Enable/disable Tier 2 features via configuration** (not manual imports)
3. **Eliminate implicit dependencies** through explicit feature manifests
4. **Make the tier boundary enforceable** by tooling (linting, CI checks)

The end result: the filesystem layout matches the architecture, features are pluggable, and the engine core is protected from accidental Tier 2 creep.

---

## Current Problems

### 1. Directory Structure Doesn't Reflect Tier Model

**Current state:**
```
src/lorecraft/
├── game/              # 40+ files: Tier 1 + Tier 2 mixed
├── commands/          # Tier 1 + Tier 2 mixed
├── services/          # Tier 1 + Tier 2 mixed
└── models/            # Tier 1 + Tier 2 mixed
```

**Problem:** You cannot tell from the directory structure which code is Tier 1 and which is Tier 2. You must refer to `tier_modules.md` every time. There's no enforcement — Tier 1 can accidentally import Tier 2 and the compiler won't catch it.

### 2. Features Load via Implicit Side-Effect Imports

**Current state in `main.py` (lines 45–55):**
```python
import lorecraft.game.traits                   # noqa: F401
import lorecraft.game.fatigue_source          # noqa: F401
import lorecraft.game.economy_holders         # noqa: F401
import lorecraft.game.bank_holders            # noqa: F401
# ... 10+ more imports ...
```

Each import triggers module-level code that registers definitions. If you want to disable a feature, you must:
- Find and comment out the import
- Find and remove any service from `ServiceContainer`
- Find and remove any command registration
- Hope you didn't miss anything

**Problem:** Error-prone, scattered across multiple files, no explicit dependency declaration.

### 3. ServiceContainer Instantiates All Services Unconditionally

**Current state in `services/container.py`:**
```python
@dataclass
class ServiceContainer:
    movement: MovementService = field(default_factory=MovementService)
    inventory: InventoryService = field(default_factory=InventoryService)
    # ... all services, even disabled ones ...
    trade: TradeService = field(default_factory=TradeService)
```

**Problem:** Services are always created, even if their feature is disabled. No way to conditionally wire only enabled services.

### 4. No Way to Enable/Disable Features at Runtime

**Current limitations:**
- No feature flag system
- No configuration file that declares which Tier 2 features are active
- No dependency graph (e.g., "fatigue depends on meters, which depends on modifiers")
- Cannot easily run tests with only Tier 1, or with a custom subset of Tier 2

---

## Desired End State

### 1. Directory Structure Enforces Tier Model

```
src/lorecraft/
├── engine/                          # NEW: Tier 1 only (engine primitives)
│   ├── game/
│   │   ├── registry.py              # Command registry
│   │   ├── context.py               # GameContext
│   │   ├── events.py                # Event bus
│   │   ├── engine.py                # Command engine
│   │   ├── parser.py                # Text parsing
│   │   ├── holders.py               # Item holder registry
│   │   ├── modifiers.py             # Modifier stacking
│   │   ├── components.py            # Component registry
│   │   ├── rng.py                   # Seedable RNG
│   │   ├── checks.py                # Skill check helper
│   │   ├── effects.py               # Active effects
│   │   ├── meters.py                # Meter definitions
│   │   ├── traits.py                # Trait registry (registry only, not trait defs)
│   │   ├── command_conditions.py    # Condition registry
│   │   ├── command_patterns.py      # Command patterns
│   │   ├── diagnostics.py           # Debug tools
│   │   ├── rules.py                 # Rule engine
│   │   └── transaction.py           # Transaction context
│   ├── services/
│   │   ├── scheduler.py             # Job scheduling
│   │   ├── item_location.py         # Item movement
│   │   ├── meters.py                # Meter service
│   │   ├── effects.py               # Effect service
│   │   ├── save.py                  # Save slots
│   │   └── mobile_route.py          # Route runner
│   ├── models/
│   │   ├── core.py                  # Room, Item, ItemInstance, ItemStack, Player (core only)
│   │   ├── audit.py                 # AuditEvent
│   │   └── session.py               # PlayerSession
│   ├── repos/
│   │   ├── item_repo.py
│   │   ├── player_repo.py
│   │   └── room_repo.py
│   ├── npc/
│   │   └── dialogue.py              # NPC dialogue trees (engine for conditions/side effects)
│   ├── clock/
│   │   └── world_clock.py           # World clock runner
│   ├── commands/                    # Tier 1 built-in verbs (owned by the engine)
│   │   ├── __init__.py              # register_engine_commands(registry, services)
│   │   ├── movement.py             # go, north, south, ...
│   │   ├── social.py               # say, emote, who
│   │   ├── meta.py                 # help, save, load, status, quit
│   │   ├── report.py              # /report (out-of-character)
│   │   └── news.py                # /news (out-of-character)
│   ├── auth.py                      # Auth primitives (JWT, password hash) — shared
│   └── config.py
│
├── features/                         # NEW: Tier 2 only (optional features)
│   ├── equipment/
│   │   ├── __init__.py              # register_equipment(app_config)
│   │   ├── models.py                # EquipmentSlot, etc.
│   │   ├── service.py
│   │   ├── commands.py
│   │   ├── modifiers.py             # Equipment modifier source
│   │   ├── validators.py            # Equip-slot move validators
│   │   └── rules.py
│   ├── fatigue/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── service.py
│   │   ├── commands.py
│   │   ├── conditions.py            # Skill-check penalty condition
│   │   └── meter.py                 # Fatigue meter definition
│   ├── inventory/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── commands.py
│   │   └── components.py            # Durability, openable, lit, container components
│   ├── skills/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── definitions.py
│   │   └── service.py
│   ├── trading/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   └── commands.py
│   ├── economy/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── commands.py
│   │   ├── holders.py               # Shop and bank holder types
│   │   └── rules.py
│   ├── transit/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   └── commands.py
│   ├── exploration/
│   │   ├── __init__.py
│   │   ├── service.py
│   │   ├── commands.py
│   │   └── rules.py
│   ├── quests/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── service.py
│   │   └── commands.py
│   ├── traits/
│   │   ├── __init__.py
│   │   ├── standard.py              # Standard boon/bane traits
│   │   └── sources.py               # Trait sources (innate, equipment)
│   ├── warmth/
│   │   ├── __init__.py
│   │   ├── definitions.py
│   │   └── rules.py
│   ├── weather/
│   │   ├── __init__.py
│   │   └── handlers.py
│   ├── terrain/
│   │   ├── __init__.py
│   │   └── definitions.py
│   ├── containers/
│   │   ├── __init__.py
│   │   └── validators.py
│   ├── reputation/
│   │   ├── __init__.py
│   │   └── conditions.py
│   ├── npc_memory/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── conditions.py
│   │   └── side_effects.py
│   ├── light/
│   │   ├── __init__.py
│   │   └── service.py
│   └── __init__.py                  # Feature registry + loader
│
├── webui/                           # NEW: web delivery hosts that DRIVE the engine (a third axis)
│   ├── player/                      # the default shipped player web UI (HTMX/Jinja + WS)
│   │   ├── __init__.py              # register_player_ui(app, state)
│   │   ├── host.py                 # WebHost: template loader, panel/slot registry, static mounts
│   │   ├── connection_manager.py    # WS connection tracking (feature-agnostic)
│   │   ├── websocket.py            # WS handshake, auth tickets, dispatch loop
│   │   ├── routes.py               # /lobby, /game, /command, /partials/...
│   │   ├── shell/                  # base page templates + named slots (no feature UI baked in)
│   │   └── static/                 # css/js for the base shell
│   └── admin/                       # admin console (its own web UI, not a game feature)
│       ├── __init__.py
│       ├── api.py
│       └── websocket.py
│
├── world/                           # Mixed (loader is Tier 1, versioning is Tier 2)
└── __init__.py
```

Note the two structural moves versus the earlier draft: **there is no top-level `commands/` directory**, and **web is a top-level `webui/` host, not a `features/` entry or an `engine/` subpackage.** The reasoning is in §1a below.

**Key principles:**
- ✅ `src/lorecraft/engine/` is **pure Tier 1** — no Tier 2 imports, and it runs **headless** (no web dependency)
- ✅ `src/lorecraft/features/` is **pure Tier 2** — features only import from `engine/` and each other
- ✅ Feature directories are **self-contained** — each feature owns its models, service, **commands**, conditions, side effects, rules
- ✅ **Commands are owned by whoever provides them:** engine built-ins in `engine/commands/`, each feature's verbs in `features/<x>/commands.py`. There is no shared command bucket to keep in sync — handlers register into the Tier 1 `CommandRegistry`.
- ✅ `src/lorecraft/webui/` holds the **web hosts** that compose an engine + features and expose them: `webui/player/` (the shipped player UI) and `webui/admin/` (the admin console). Both are swappable; a future non-web host (CLI/telnet/Discord) is a *different* delivery tech and gets its own top-level dir (e.g. `cli/`) rather than living under `webui/`.

### 1a. Why commands and web are structured this way

The earlier draft treated "commands" and "web" as *layers* that each needed a Tier 1 half and a Tier 2 half (`commands/engine` + `commands/features`, and a `web/` bucket). That was wrong: neither is a layer.

**Commands are a capability a tier/feature provides — not a shared bucket.**
The `CommandRegistry` (`engine/game/registry.py`) is the Tier 1 primitive; handlers just register into it. So the owner of a verb owns its handler:
- Engine built-in verbs (`go`, `say`, `help`, `save`) → `engine/commands/`
- A feature's verbs (`buy`, `board`, `offer`) → *inside that feature* (`features/economy/commands.py`)

The old `register_all_commands` dispatcher disappears. The engine registers its built-ins; each feature registers its own verbs in its `register()` (§2b). Nothing keeps a central list — that is the payoff of the manifest system, and a top-level `commands/` dir (Tier 1 *or* Tier 2) would reintroduce exactly the coupling we're removing.

**Web is a delivery host — a third axis, not Tier 1 and not a feature.**
- It **cannot live in `engine/`**: the engine must run headless. Tests, the simulation harness, the world CLI, and any future CLI/telnet/Discord host all drive the engine with no web server. Putting web inside `engine/` breaks that invariant.
- It **does not belong in `features/`**: `fatigue` and `trading` are *game mechanics*; web is *presentation*. Toggling a UI host is a different axis from toggling a game rule, so mixing them into the same feature-flag list conflates two concerns.

So `webui/` is its own top-level concern holding `player/` (the default shipped player UI) and `admin/` (the admin console) — named by audience, both happening to be web. Each host *composes* an engine + a set of features and exposes them. `webui/player/` owns only the feature-agnostic plumbing: the WebSocket handshake, connection manager, auth tickets, the command-dispatch loop, and the base page shell.

> **Naming note.** We use `webui/player` + `webui/admin` (audience-named) rather than `frontends/web` + `frontends/admin` (role-named) because the meaningful split here is *who the UI is for*, and both are web today. If a genuinely different delivery tech ever ships (CLI, telnet, Discord bot), it is a sibling top-level package, not a `webui/` entry.

### 1b. Feature-specific UI (the one real coupling)

Some features genuinely have UI — the transit minimap animation, an inventory panel, a quest log. Two ways to handle it:

1. **Heavy (not now):** a UI-extension registry where features register panels/partials and the web host composes them. Powerful but it is a whole framework to build and own — the kind of half-done seam `AGENTS.md` warns against adding speculatively.
2. **Light (recommended):** the web host is allowed to know about features through **one thin optional seam**. A feature MAY ship a `presentation.py` (server-rendered partials + any client JS) that the web host picks up **only when both that feature and the web host are enabled**. Document the seam; implement it lazily. Grow toward the heavy version only if a second host ever needs the same contract. **The full loading mechanism is specified in §1c below** — that section is the guidance builders and admins will rely on when adding feature UI.

```
features/transit/
├── __init__.py
├── service.py
├── commands.py
└── presentation.py          # OPTIONAL: web partials/JS for the transit minimap;
                             # loaded only if `transit` AND the web host are both on
```

### 1c. How feature UI loads into the web host

> **This subsection is authoritative builder/admin guidance.** It explains exactly how a feature contributes UI to the player web host — the discovery, the server-side wiring, and the JavaScript path — grounded in the panel/partials mechanism the web tier already uses today. When the refactor lands, this content graduates verbatim into `docs/admin_builder_guide.md` as the "Adding feature UI" chapter.

#### The update loop that already exists (the seam we build on)

A "panel" in the player UI is already just a convention with three parts, and no new framework is needed to extend it:

1. A DOM element with a stable id, e.g. `<div id="inventory">`, sitting in a slot in `game.html`.
2. A route `GET /partials/inventory` that renders `partials/inventory.html`.
3. The engine *naming* that panel when it changes: a command handler puts a key in `ctx.updates`, and the web layer turns that into a WebSocket push `{"type": "state_change", "affected_panels": ["inventory", ...]}`.

The browser closes the loop generically (this is the current `webui/player/static/js/app.js` handler):

```js
case "state_change":
  const panels = data.affected_panels || [...];
  panels.forEach((panelId) => {
    htmx.ajax("GET", `/partials/${panelId}`, { target: `#${panelId}`, swap: "outerHTML" });
  });
```

The client never knows what "inventory" *means* — it re-fetches `/partials/inventory` and swaps the returned HTML. **That indirection is the entire extension seam.** A feature that wants UI supplies a template, a partial route, a shell slot, and gets its panel name into `affected_panels`.

#### What `presentation.py` registers

The web host passes each enabled feature a small `WebHost` extension object. The feature's `presentation.py` registers into three points:

```python
# features/transit/presentation.py
from pathlib import Path
from lorecraft.webui.player.host import WebHost, Panel

def register(web: WebHost) -> None:
    # 1. Add this feature's own templates/ dir to the Jinja search path.
    web.add_template_dir(Path(__file__).parent / "templates")

    # 2. Contribute panel(s): a stable id, which named shell slot the panel
    #    lives in, the partial to render, and the function that builds its
    #    template context. The host auto-generates GET /partials/<id>.
    web.add_panel(Panel(
        id="transit-minimap",
        slot="right-rail",
        partial="partials/transit_minimap.html",
        context=build_minimap_context,      # (player, db) -> dict
    ))

    # 3. Ship static assets — ONLY for genuinely interactive panels.
    web.add_static(mount="/features/transit", path=Path(__file__).parent / "static")
    web.add_script("/features/transit/minimap.js", module=True)
```

Under the hood, each call generalizes something the web tier does by hand today:

| `WebHost` call | What the host does with it | Generalizes (today) |
|---|---|---|
| `add_template_dir(path)` | Builds `Jinja2Templates` over a `ChoiceLoader` of the base dir **plus every enabled feature's dir**, so `partials/transit_minimap.html` resolves. | `Jinja2Templates(directory="…/web/templates")` — a single hard-coded dir. |
| `add_panel(Panel(...))` | Auto-registers `GET /partials/transit-minimap` (renders the partial with `context(...)`) and records that a `<div id="transit-minimap">` is emitted into the `right-rail` slot when `game.html` renders. | One hand-written `@router.get("/partials/<name>")` per panel in `frontend.py`. |
| `add_static(mount, path)` | One `app.mount("/features/transit", StaticFiles(...))`. | The single `/static` mount. |
| `add_script(url, module=True)` | Injects `<script type="module" src="…">` into the base shell `<head>`. | Scripts hard-coded in `base.html`. |

#### Discovery — how it actually gets loaded

The manifest gains one optional field, and the **web host** (never the engine) resolves it, only for features that are enabled *and* only because the web host itself is the running host:

```python
# features/transit/__init__.py
manifest = FeatureManifest(
    key="transit",
    ...,
    presentation="lorecraft.features.transit.presentation",  # optional dotted path
)

# webui/player/__init__.py — during host composition
for m in enabled_features.values():
    if m.presentation:
        try:
            import_module(m.presentation).register(web_host)
        except Exception:
            log.exception("feature UI failed to load: %s", m.key)  # degrade, don't crash
```

Consequence: running **headless** (tests, simulation harness, world CLI, a future non-web host) imports no `presentation.py` at all, so feature UI code never loads and costs nothing. That is the payoff of web being a separate axis — `engine/` and `features/` stay import-clean of anything web.

#### The JavaScript tier — two cases

**Most features need zero JavaScript.** A schedule board, a quest log, an inventory list are just server-rendered partials. When the engine flags the panel in `affected_panels`, the existing `app.js` handler re-fetches `/partials/<id>` and swaps it. The feature ships an HTML template and nothing else — no JS module, no bundler.

**Interactive panels (rare, e.g. the transit minimap animation)** ship a JS module. How it reaches the page and hooks updates without touching engine internals:

- *Reaching the page:* `add_script` injected a native `<script type="module">` for this enabled feature. No build step — consistent with the current vanilla `app.js`.
- *Hooking updates:* the module does **not** open its own WebSocket. The host owns the single WS and already re-dispatches. The module subscribes to a DOM event instead — two established hook points:
  - `htmx:afterSwap` on its own panel element — fires whenever `/partials/transit-minimap` is re-fetched, so the module (re)starts its animation against the fresh DOM. Needs no new plumbing.
  - a host-provided `document.addEventListener('lorecraft:ws', e => …)` — the host re-emits raw WS frames as a `CustomEvent`. Use this when the animation needs richer data than "the panel changed" (e.g. interpolated vehicle position). This mirrors the existing `lorecraft:refresh-panel` custom event in `game.html`.

So a feature's JS is always a leaf: the host injects it and hands it an event stream; it reads the DOM/event and animates. It imports no engine or feature Python and never manages a socket.

#### Contracts and failure modes builders must know

- **Named slots are a fixed contract.** The base shell declares slots (`left-rail`, `right-rail`, `hud`, `feed`); a panel targets one by name. Unknown slot name → the panel is dropped with a logged warning.
- **Panel ids are global and stable.** They are the URL (`/partials/<id>`), the DOM id, and the `affected_panels` token, so they must be unique across enabled features. Convention: prefix with the feature key (`transit-minimap`, not `minimap`).
- **Slot ordering is deterministic** — by feature load order, which comes from the enabled-features list. Two features targeting the same slot stack in that order.
- **A broken `presentation.py` degrades to "no panel," never a crashed page** — the host wraps each `register()` in try/log (shown above).
- **The engine still drives visibility.** A feature makes its panel refresh by adding its panel id to `ctx.updates`/`affected_panels` from its own command handlers or event handlers — the same mechanism core panels use. The web host does not poll.

### 2. Feature Manifest & Configuration

Each feature declares what it provides and what it needs. Create `features/manifest.py`:

```python
# src/lorecraft/features/manifest.py

from dataclasses import dataclass, field
from typing import Callable

@dataclass
class FeatureManifest:
    """Metadata about a Tier 2 feature."""
    key: str                                           # e.g., "equipment", "fatigue"
    name: str                                          # e.g., "Equipment System"
    dependencies: list[str] = field(default_factory=list)  # e.g., ["modifiers", "inventory"]
    models: list[str] = field(default_factory=list)        # e.g., ["EquipmentSlot"]
    services: list[tuple[str, type]] = field(default_factory=list)  # e.g., [("equipment", EquipmentService)]
    register_fn: Callable[..., None] | None = None         # Feature-specific setup function
    presentation: str | None = None                   # OPTIONAL dotted path to a presentation.py
                                                      # with register(web_host) — loaded by the web
                                                      # host only, never by the engine (see §1c)
    optional: bool = True                             # Can be disabled without breaking core

# Feature registry at startup time
FEATURE_REGISTRY: dict[str, FeatureManifest] = {}

def register_feature(manifest: FeatureManifest) -> None:
    FEATURE_REGISTRY[manifest.key] = manifest

def get_feature(key: str) -> FeatureManifest | None:
    return FEATURE_REGISTRY.get(key)
```

Each feature's `__init__.py` exports a manifest:

```python
# src/lorecraft/features/equipment/__init__.py

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.equipment.service import EquipmentService
from lorecraft.features.equipment.commands import register_equipment_commands
from lorecraft.features.equipment.modifiers import register_equipment_modifiers

manifest = FeatureManifest(
    key="equipment",
    name="Equipment System",
    dependencies=["inventory"],
    services=[("equipment", EquipmentService)],
    register_fn=lambda state: _register(state),
)

def _register(state) -> None:
    register_equipment_commands(state.registry, state.services.equipment)
    register_equipment_modifiers()
    # ... etc.

# Auto-register when imported
register_feature(manifest)
```

### 3. Configuration File Drives Feature Loading

Create `config/features.yaml`:

```yaml
# config/features.yaml
# Declares which Tier 2 features are enabled

features:
  enabled:
    - equipment        # Equipment system
    - inventory        # Inventory management
    - fatigue          # Fatigue/sleep mechanics
    - skills           # Skill definitions
    - traits           # Trait system
    - trading          # Player-to-player trading
    - economy          # Shops and banks
    - transit          # Transit vehicles
    - quests           # Quest system
    - exploration      # Exploration/journal
    - weather          # Weather system
    - reputation       # Reputation conditions
    - npc_memory       # NPC memory/learning
    - light            # Light/fuel system
    - warmth           # Warmth/thermals

  disabled: []          # Explicitly disabled features (for documentation)

# Optional: declare feature dependencies (for validation)
dependencies:
  equipment: [inventory, modifiers]
  fatigue: [meters]
  # ... etc.
```

Or make it config-driven via environment variable:

```bash
LORECRAFT_FEATURES=equipment,inventory,fatigue,skills,traits,trading,economy
```

### 4. Refactored main.py

```python
# src/lorecraft/main.py (after refactor)

from pathlib import Path
import yaml

from lorecraft.config import Settings, load_settings
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.services.container import ServiceContainer
from lorecraft.features.manifest import FEATURE_REGISTRY
from lorecraft.features import load_features

def create_app(
    *,
    settings: Settings | None = None,
    game_engine: Engine | None = None,
    audit_engine: Engine | None = None,
    features_config: str | dict[str, any] | None = None,
) -> FastAPI:
    settings = settings or load_settings()

    # Load which features are enabled
    features = _load_features_config(features_config, settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # ... setup code ...

        manager = ConnectionManager()
        bus = EventBus()
        registry = CommandRegistry()
        rules = RuleEngine()

        # Only load enabled features
        loaded_features = load_features(features, FEATURE_REGISTRY)

        # Build service container only with enabled services
        services = ServiceContainer.build(loaded_features)

        # Create app state
        state = AppState(...)

        # Register commands from enabled features
        _register_commands(state, loaded_features)

        # Register event handlers from enabled features
        _register_event_handlers(state, loaded_features)

        app.state.lorecraft = state
        try:
            yield
        finally:
            # ... teardown ...

def _load_features_config(
    features_config: str | dict | None,
    settings: Settings,
) -> list[str]:
    """Load feature list from config file or env var or default."""
    if isinstance(features_config, dict):
        return features_config.get("enabled", [])

    if features_config:
        # Load from YAML file path
        with open(features_config) as f:
            config = yaml.safe_load(f)
            return config.get("features", {}).get("enabled", [])

    # Load from env var (comma-separated)
    import os
    env_features = os.getenv("LORECRAFT_FEATURES")
    if env_features:
        return env_features.split(",")

    # Default: all features enabled (for backward compat)
    return list(FEATURE_REGISTRY.keys())

def _register_commands(state: AppState, loaded_features: dict[str, FeatureManifest]) -> None:
    """Register commands from Tier 1 and all loaded Tier 2 features."""
    from lorecraft.engine.commands import register_engine_commands
    register_engine_commands(state.registry, state.services)

    for manifest in loaded_features.values():
        # Each feature's manifest has already wired its commands
        # (in manifest.register_fn or via feature's __init__.py)
        pass
```

### 5. Refactored ServiceContainer

```python
# src/lorecraft/services/container.py (after refactor)

from dataclasses import dataclass, field

@dataclass
class ServiceContainer:
    """Dynamically instantiated services based on enabled features."""

    # Tier 1 (always present)
    scheduler: SchedulerService = field(default_factory=SchedulerService)
    item_location: ItemLocationService = field(default_factory=ItemLocationService)
    meters: MeterService = field(default_factory=MeterService)
    effects: EffectService = field(default_factory=EffectService)
    save: SaveSlotService = field(default_factory=SaveSlotService)
    mobile_route: MobileRouteService = field(default_factory=MobileRouteService)

    # Tier 2 (optional, keyed by feature)
    _services: dict[str, object] = field(default_factory=dict)

    def get_service(self, key: str) -> object | None:
        """Get a service by feature key (e.g., 'equipment', 'quest')."""
        return self._services.get(key)

    def register_service(self, key: str, service: object) -> None:
        """Register a feature service."""
        self._services[key] = service

    @classmethod
    def build(cls, enabled_features: dict[str, FeatureManifest] | None = None) -> ServiceContainer:
        """Construct container with only enabled feature services."""
        container = cls()

        if enabled_features:
            for manifest in enabled_features.values():
                for service_key, service_class in manifest.services:
                    service = service_class()
                    container.register_service(service_key, service)

        return container
```

---

## Implementation Strategy

### Phase 1: Create Engine Directory & Move Tier 1 Code (~2 sprints)

1. **Create `src/lorecraft/engine/` directory structure** — copy Tier 1 modules into new location
2. **Update imports** across the codebase to use `lorecraft.engine.game.*` instead of `lorecraft.game.*`
3. **Run tests** after each major move
4. **Update documentation** to reflect new layout
5. **Add linting rules** to prevent Tier 1 from importing Tier 2

### Phase 2: Create Features Directory & Reorganize Tier 2 (~2–3 sprints)

1. **Create `src/lorecraft/features/` with manifest system**
2. **Move each Tier 2 feature into its own subdirectory:**
   - `features/equipment/`
   - `features/fatigue/`
   - `features/inventory/`
   - `features/skills/`
   - `features/traits/`
   - `features/trading/`
   - `features/economy/`
   - `features/transit/`
   - `features/exploration/`
   - `features/quests/`
   - `features/weather/`
   - `features/reputation/`
   - `features/npc_memory/`
   - `features/light/`
   - `features/warmth/`
   - `features/terrain/`
   - `features/containers/`
3. **Create a manifest for each feature** declaring dependencies, services, register functions
4. **Update `features/__init__.py`** with the feature loader
5. **Run tests** after reorganizing each feature

### Phase 3: Refactor Service Wiring (~1 sprint)

1. **Refactor `ServiceContainer`** to conditionally instantiate services
2. **Create `config/features.yaml`** with feature configuration
3. **Refactor `main.py`** to use feature loader instead of side-effect imports
4. **Remove all side-effect imports** (the `# noqa: F401` lines)
5. **Test feature enabling/disabling** with feature config

### Phase 4: Commands, Frontends & Event Wiring (~1 sprint)

1. **Delete the top-level `commands/` package.** Move Tier 1 verbs into `engine/commands/` (exposing `register_engine_commands`); move each Tier 2 verb module into its owning feature (`features/<x>/commands.py`). Remove `register_all_commands`.
2. **Ensure each feature's `register_fn` wires its own commands** instead of `main.py` doing it.
3. **Extract the web layer into `webui/player/`** as a host that composes engine + features (WS handshake, connection manager, auth tickets, dispatch loop, base shell); move the admin console to `webui/admin/`. Verify the engine imports nothing from `webui/`. **Prerequisite:** replace the single-directory `Jinja2Templates(directory=...)` with a multi-directory `ChoiceLoader` and a panel/slot registry (the `WebHost` object) — see §1c.
4. **Add the optional `presentation.py` seam** (§1b): the web host loads a feature's partials/JS only when both that feature and the web host are enabled. Start with one consumer (transit) to prove the seam.
5. **Refactor event handler registration** to be feature-driven.
6. **Run tests** to ensure all commands, frontends, and handlers are wired correctly.

### Phase 5: Validation & Testing (~1 sprint)

1. **Add integration tests** that enable/disable features and verify the engine still works
2. **Add a test mode** that runs with only Tier 1 to verify core functionality
3. **Add a linting rule** (via pre-commit or CI) that prevents `engine/` from importing `features/`
4. **Update CI/CD** to run test suites for each feature combination
5. **Manual testing** of the full game with all features enabled
6. **Update CLAUDE.md** with new structure and guidelines

---

## Detailed Implementation Steps

### Step 1a: Create engine/ Directory & Move Tier 1

```bash
mkdir -p src/lorecraft/engine/{game,services,models,repos,npc,clock,admin,commands}
cp src/lorecraft/game/registry.py src/lorecraft/engine/game/
cp src/lorecraft/game/context.py src/lorecraft/engine/game/
# ... copy all Tier 1 game modules ...
cp src/lorecraft/services/scheduler.py src/lorecraft/engine/services/
# ... copy all Tier 1 service modules ...
```

### Step 1b: Update All Imports

Use a script to replace imports across the codebase:

```bash
find src -name "*.py" -type f -exec sed -i \
  's/from lorecraft.game.registry import/from lorecraft.engine.game.registry import/g' {} \;
find src -name "*.py" -type f -exec sed -i \
  's/from lorecraft.services.scheduler import/from lorecraft.engine.services.scheduler import/g' {} \;
# ... etc. for all Tier 1 modules ...
```

Verify by running type-checking and tests after each major batch.

### Step 2a: Create Features Manifest System

```python
# src/lorecraft/features/manifest.py
# (as shown above)

# src/lorecraft/features/__init__.py
"""Feature loader and registry."""

from lorecraft.features.manifest import FEATURE_REGISTRY, FeatureManifest

def load_features(
    enabled_keys: list[str],
    registry: dict[str, FeatureManifest],
) -> dict[str, FeatureManifest]:
    """Load and validate enabled features."""
    loaded = {}

    for key in enabled_keys:
        manifest = registry.get(key)
        if manifest is None:
            raise ValueError(f"Feature {key!r} not registered")

        # Validate dependencies
        for dep_key in manifest.dependencies:
            if dep_key not in enabled_keys:
                raise ValueError(
                    f"Feature {key!r} requires {dep_key!r}, which is not enabled"
                )

        loaded[key] = manifest

    return loaded
```

### Step 2b: Create Feature Packages

For each Tier 2 feature, create `features/FEATURE/__init__.py`:

```python
# src/lorecraft/features/equipment/__init__.py

from lorecraft.features.manifest import FeatureManifest, register_feature
from lorecraft.features.equipment.service import EquipmentService

manifest = FeatureManifest(
    key="equipment",
    name="Equipment System",
    dependencies=["inventory"],  # Must be enabled if we are
    services=[("equipment", EquipmentService)],
)

def register(state):
    """Wire commands, conditions, modifiers, and event handlers."""
    from lorecraft.features.equipment.commands import register_commands
    from lorecraft.features.equipment.modifiers import register_modifiers
    from lorecraft.features.equipment.validators import register_validators

    register_commands(state.registry, state.services.get_service("equipment"))
    register_modifiers()
    register_validators()

manifest.register_fn = register
register_feature(manifest)
```

### Step 3: Refactor ServiceContainer

```python
# src/lorecraft/services/container.py

@dataclass
class ServiceContainer:
    # Tier 1 services (always instantiated)
    scheduler: SchedulerService
    item_location: ItemLocationService
    meters: MeterService
    effects: EffectService
    save: SaveSlotService
    mobile_route: MobileRouteService

    # Tier 2 services (optional, lazy)
    _feature_services: dict[str, object] = field(default_factory=dict)

    def get(self, key: str) -> object | None:
        return self._feature_services.get(key)

    def register(self, key: str, service: object) -> None:
        self._feature_services[key] = service

    @classmethod
    def build(cls, features: dict[str, FeatureManifest]) -> ServiceContainer:
        container = cls(
            scheduler=SchedulerService(...),
            item_location=ItemLocationService(...),
            # ... Tier 1 services ...
        )

        # Instantiate services for enabled features
        for manifest in features.values():
            for service_key, service_class in manifest.services:
                service = service_class()
                container.register(service_key, service)

        return container
```

### Step 4: Refactor main.py

Remove all side-effect imports and use the feature loader:

```python
# src/lorecraft/main.py (key changes)

from lorecraft.features import load_features
from lorecraft.features.manifest import FEATURE_REGISTRY

def create_app(...):
    # Load which features are enabled
    features = _load_features_config(settings)
    enabled_features = load_features(list(features.keys()), FEATURE_REGISTRY)

    # Build service container with only enabled services
    services = ServiceContainer.build(enabled_features)

    # Let each feature register itself
    for manifest in enabled_features.values():
        if manifest.register_fn:
            manifest.register_fn(state)
```

---

## Testing Strategy

### Unit Tests

- **Test feature manifests** — verify dependencies are declared correctly
- **Test feature loader** — verify enabled/disabled combinations work
- **Test each feature in isolation** — mock out dependencies

### Integration Tests

- **Test Tier 1 only** — no Tier 2 features enabled (smoke test)
- **Test all features enabled** — current behavior
- **Test custom feature combinations** — e.g., enable equipment but disable trading
- **Test feature dependency validation** — verify errors are raised for invalid configs

### Linting / Static Analysis

- **Pre-commit hook** to enforce the import direction: `engine/` must not import `features/` or `webui/`; `features/` must not import `webui/`. (Web hosts may import both; that is the composition direction. A feature's `presentation.py` is the sole exception — it is imported *by* the host, never the reverse.)
- **CI check** to verify no new side-effect imports in `main.py`
- **Type checker** configuration to enforce the boundary

### Manual Testing

- Run the full game with default config (all features enabled)
- Run with a minimal feature set (Tier 1 only)
- Run with custom configs (a few features enabled/disabled)
- Verify that disabling a feature doesn't break the engine

---

## Migration Timeline

| Sprint | Tasks | Dependencies |
|--------|-------|--------------|
| N (planning) | Design & documentation | None |
| N+1 | Create `engine/` dir, move Tier 1 code | Planning done |
| N+1 | Update imports (batch 1: game/) | Engine dir created |
| N+2 | Update imports (batch 2: services/, repos/) | Import batch 1 done |
| N+2 | Update imports (batch 3: rest of codebase) | Import batch 2 done |
| N+3 | Create `features/` dir & manifest system | Imports done |
| N+3 | Move feature 1 (equipment) | Manifest system created |
| N+4 | Move feature 2-5 (fatigue, inventory, skills, traits) | Feature 1 moved |
| N+5 | Move feature 6-10 (trading, economy, transit, exploration, quests) | Features 2-5 moved |
| N+5 | Move feature 11-15 (weather, reputation, npc_memory, light, warmth, terrain, containers) | Features 6-10 moved |
| N+6 | Refactor ServiceContainer & main.py | All features moved |
| N+6 | Refactor commands & event wiring | ServiceContainer refactored |
| N+7 | Add linting rules & CI checks | Commands refactored |
| N+7 | Comprehensive testing & validation | Linting added |
| N+8 | Update documentation (CLAUDE.md, architecture.md, etc.) | Testing done |

---

## Backward Compatibility & Rollback

### During Migration

To avoid breaking the build during multi-sprint refactoring:

1. **Keep duplicate imports temporarily** — both old and new import paths work
2. **Use aliases** — `lorecraft.game = lorecraft.engine.game` in `__init__.py`
3. **Migrate subsystems in order** — core first, then commands, then services
4. **Run tests continuously** — catch issues early

### If Something Goes Wrong

- **Git branch** — the refactor happens on a long-lived branch, not main
- **Revert entire branch** if critical issues arise
- **Keep detailed commit messages** — each step is a reviewable commit
- **Test suite must pass** before merging

### After Migration

- **Remove deprecated imports** after a grace period (e.g., 1 sprint)
- **Update CI/CD** to enforce new structure on new code
- **Add linting rules** to prevent regression

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Large refactor breaks build** | High | Branch strategy, incremental commits, frequent testing |
| **Circular imports between features** | Medium | Feature manifests declare dependencies; CI checks for cycles |
| **Services wired in wrong order** | Medium | Explicit service ordering in ServiceContainer; tests verify |
| **External code depends on old import paths** | Medium | Provide deprecation aliases during grace period |
| **Performance regression** | Low | Benchmark before/after; lazy instantiation mitigates |

---

## Design Principles & Guidelines

Once the refactor is complete, these principles guide future development:

### For Tier 1 Contributions

1. **No imports from `features/`** — ever
2. **Generic, data-driven** — no assumptions about game mechanics
3. **Pluggable registries** — traits, modifiers, conditions, side effects, rules, events
4. **Type-safe primitives** — `GameContext`, `CommandRegistry`, `EventBus`, etc.

### For Tier 2 Contributions

1. **Self-contained** — one feature per directory
2. **Declare dependencies** in manifest
3. **Register via manifest.register_fn** — not via side-effect imports
4. **Use Tier 1 registries** for extensibility
5. **Never reach into another feature's internals** — use public APIs

### For Adding New Features

1. Create `features/my_feature/__init__.py` with manifest
2. Create service, models, commands, conditions, side effects as needed
3. Export a `register()` function that wires everything
4. Add to `config/features.yaml` and test with it enabled/disabled

---

## Success Criteria

At the end of the refactor, we will have:

- ✅ Tier 1 code physically separated in `engine/` directory, and the engine runs headless (no `webui/` dependency)
- ✅ Tier 2 features physically separated in `features/` directory, each owning its own commands
- ✅ Web hosts separated in `webui/` (`player`, `admin`); the player UI is swappable, not baked into the engine
- ✅ Feature UI loads through the documented `presentation.py` seam (§1c), only when both the feature and the host are enabled
- ✅ Import direction enforced by linting: `engine/` ⇏ `features/`/`webui/`; `features/` ⇏ `webui/`
- ✅ Feature manifests declare all dependencies
- ✅ ServiceContainer built conditionally based on enabled features
- ✅ Feature loading driven by configuration (YAML or env var), not manual imports
- ✅ All tests pass (unit, integration, end-to-end)
- ✅ Feature enabling/disabling tested and working
- ✅ Documentation updated (CLAUDE.md, architecture.md, tier_modules.md)
- ✅ CI/CD validates new code follows the pattern

---

## Questions for Discussion

1. **Feature manifest complexity:** Should we include more metadata (description, author, version, license)?
2. **Conditional service instantiation:** Should lazy services be instantiated on first use, or fail loudly if accessed when disabled?
3. **Validation strictness:** Should loading with missing dependencies fail, or silently skip dependent features?
4. **Grace period for deprecated imports:** How long should old import paths work (1 sprint, 1 quarter)?
5. **Test coverage threshold:** Should we require specific test coverage for refactored modules?
6. **Feature toggles at runtime:** Should we support enabling/disabling features after server startup, or only at boot time?

---

## References

- `docs/architecture_tiers.md` — Current tier model and limitations
- `docs/tier_modules.md` — File-by-file tier classification
- `docs/feature-registration.md` — Pattern for adding features (will be updated)
- `docs/engine_core.md` — Tier 1 primitive specifications
- `AGENTS.md` — Repository agent instructions and principles
