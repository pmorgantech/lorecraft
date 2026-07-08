# Lorecraft — Persistent Multiplayer Text Adventure Engine

A Python-based text adventure engine designed for persistent, multiplayer worlds with a real-time clock, sophisticated world mechanics, and extensible feature system.

**Status:** Foundation and Tier 1 engine primitives complete (Sprints 1–21); Tier 2 feature band in progress (Sprints 22–35). See [`docs/roadmap.md`](docs/roadmap.md) — the single source of truth for what's done and what's next.

---

## What Is Lorecraft?

Lorecraft is a game engine, not a game. It provides:

- **Core primitives:** Event bus, command parsing, scheduler, transaction model, audit logging
- **Standard features:** Equipment, trading, NPCs with dialogue, quests, inventory management, fatigue system
- **Extensibility:** A clean plugin architecture (registries, side effects, conditions, rules) for adding custom mechanics
- **World authoring:** YAML-based world content (rooms, items, NPCs, dialogue trees) loaded into SQLite

Players connect via WebSocket to a persistent world that runs on real time whether they're connected or not.

---

## Architecture Overview

Lorecraft uses a **three-tier architecture** to separate engine concerns from game content:

| Tier | What | Where | Can you customize it? |
|------|------|-------|---|
| **Tier 1** | Primitives (event bus, scheduler, registries, command dispatch) | `src/lorecraft/game/`, `src/lorecraft/services/` | No — foundational |
| **Tier 2** | Standard features (equipment, trading, fatigue, NPCs, quests) | Currently `src/lorecraft/`; planned `features/` | **Yes** — optional, toggleable |
| **Tier 3** | Game content (rooms, items, NPCs, dialogue, quests) | `world_content/*.yaml` | **Yes** — per-world |

**Key principle:** Tier 1 defines zero game opinions. Tier 2 features register through Tier 1 extension points (registries, rules, event handlers) and can be disabled or replaced. Tier 3 is fully game-specific.

### For Implementers: Architecture Documents

- **[`docs/architecture_tiers.md`](docs/architecture_tiers.md)** — Current state of Tier 1/2 split, how features register, how to disable or extend them (START HERE if customizing the engine)
- **[`docs/tier_modules.md`](docs/tier_modules.md)** — Quick file-by-file classification (Tier 1 vs Tier 2)
- **[`docs/engine_core.md`](docs/engine_core.md)** — Authoritative specs for Tier 1 primitives and the tier boundary (detailed reference for implementers)
- **[`docs/feature-registration.md`](docs/feature-registration.md)** — How to add a new Tier 2 feature or extend existing ones
- **[`docs/architecture.md`](docs/architecture.md)** — Comprehensive subsystem overview (predates tier refactor; still useful reference)

### For World Builders: User Guides

- **[`docs/user_guide.md`](docs/user_guide.md)** — Player-facing features and commands
- **[`docs/admin_builder_guide.md`](docs/admin_builder_guide.md)** — How to design worlds in YAML and use the admin tools
- **[`docs/world_building.md`](docs/world_building.md)** — World authoring conventions
- **[`docs/feature_testing_guide.md`](docs/feature_testing_guide.md)** — Manual + automated testing reference for implemented features

---

## Quick Start (Development)

### Prerequisites
- Python 3.12+
- SQLite (included with Python)

### Setup

```bash
# Install dependencies (including dev tools)
pip install -e ".[dev]"

# Run the server (starts at http://localhost:8000)
./start.sh

# Run tests
make test

# Run linting
make lint

# Run type checking
make typecheck
```

See [`Makefile`](Makefile) for all available targets.

---

## Project Structure

```
src/lorecraft/
├── game/                    # Core engine logic (registry, context, events, rules)
├── commands/                # Command handlers (movement, inventory, etc.)
├── services/                # Service layer (inventory, quest, trading, etc.)
├── models/                  # SQLModel table definitions
├── repos/                   # Data access (queries)
├── npc/                     # NPC dialogue system
├── admin/                   # Admin API and TUI
├── world/                   # World loading, bootstrap, versioning
├── web/                     # WebSocket frontend
└── clock/                   # World time and weather

world_content/
├── world.yaml               # Rooms, items, NPCs, quests, dialogue
├── items/                   # Item definitions and schema docs
├── npcs/                    # NPC behavior and dialogue
└── rooms/                   # Room descriptions and layout

docs/
├── architecture_tiers.md    # Tier 1/2/3 split, extensibility
├── engine_core.md           # Tier 1 primitives specification
├── feature-registration.md  # How to build Tier 2 features
├── roadmap.md               # Sprint breakdown, feature sequence, and current status
└── [many more...]
```

---

## Extending Lorecraft

### Disable a Standard Feature

To disable a Tier 2 feature (e.g., equipment, trading):

1. Remove its registration import from `src/lorecraft/main.py`
2. Remove its commands from command registration
3. Remove its service from `ServiceContainer`

See [`docs/architecture_tiers.md`](docs/architecture_tiers.md) § 5 for detailed guidance.

### Add a Custom Feature

Create a new module that registers with Tier 1 extension points:

1. Define models (if needed)
2. Create a service and register it
3. Register commands, conditions, side effects, or rules
4. Wire it in `main.py`

See [`docs/feature-registration.md`](docs/feature-registration.md) for the complete pattern with examples.

### Customize World Content

Edit `world_content/world.yaml` to define:
- Rooms (with exits and descriptions)
- Items (with properties and effects)
- NPCs (with dialogue trees and behavior)
- Quests (with stages and conditions)

See [`docs/admin_builder_guide.md`](docs/admin_builder_guide.md) for authoring conventions.

---

## Testing

```bash
# Full test suite (parallel, excludes e2e/simulation)
make test

# With coverage
make test-cov

# E2E browser tests
make test-e2e

# Live-server simulation tests
make test-simulation

# Single test file
python -m pytest -n auto --dist=loadfile tests/unit/test_context.py
```

Tests use an in-memory SQLite database and are fully deterministic (with seeded RNG).

---

## Key Concepts

### GameContext
Every command handler receives a `GameContext` object containing:
- Current player + world state
- Event bus for emitting game events
- Transaction context for audit logging
- Service references

### Event Bus
Features communicate via an event bus. Services subscribe to `GameEvent` members (e.g., `PLAYER_MOVED`, `ITEM_TAKEN`) and react accordingly.

### Registries
Tier 2 features register with Tier 1 registries:
- **CommandRegistry** — command handlers and help text
- **CommandConditionRegistry** — predicates for command availability
- **RuleEngine** — policy enforcement (e.g., "can't drop bound items")
- **ModifierRegistry** — equipment effects, stat bonuses, etc.

### Scheduler
Long-running mechanics (fatigue drain, NPC movement, transit schedules) use the `SchedulerService`, which dispatches `SCHEDULED_JOB_DUE` events on world clock ticks.

---

## Contributing

See [`AGENTS.md`](AGENTS.md) for contributor guidelines and current focus areas (foundation before features).

---

## License

See [`LICENSE`](LICENSE).

---

## Status & Roadmap

- **Foundation band (Sprints 5–15):** ✅ Complete. Service infrastructure, player auth, type safety, event bus, scheduler, audit logging, world versioning.
- **Tier 1 primitives (Sprints 16–21):** ✅ Complete. Item model, item location, modifiers, meters, effects, RNG, skill checks, ledger, mobile routes.
- **Tier 2 features (Sprints 22–29):** ✅ Complete. Equipment, traits, skills, exploration, condition (fatigue/sleep), trading, transit.
- **Remaining (Sprints 30–35):** 📅 Planned. Quests/puzzles depth, combat, PvP.

See [`docs/roadmap.md`](docs/roadmap.md) — the single source of truth for detailed sprint breakdowns and current progress.

---

**Questions?** Start with [`docs/architecture_tiers.md`](docs/architecture_tiers.md) if customizing the engine, or [`docs/user_guide.md`](docs/user_guide.md) if playing the game.
