# Lorecraft — Rust Migration (rust-port branch)

**BRANCH NOTICE:** You are on the `rust-port` integration branch for the Rust engine migration.
**Never commit to `main` or `develop` from this worktree.** See "Branch Structure" below.

This branch contains the Rust port of Lorecraft's core engine, following the phased strangler
pattern outlined in [`docs/rust_migration_plan.md`](docs/rust_migration_plan.md). The Python
implementation remains on `main` for reference and continued maintenance.

---

## Branch Structure & Development Workflow

### rust-port Branch

This branch is the **integration point for all Rust migration work**:

- All Rust engine code lives in `rust/` with a Cargo workspace
- New feature branches should be created **from rust-port**, never from main/develop
- Pull requests merge **into rust-port**, never into main/develop
- `main` branch remains the production Python engine and **must never be modified from this worktree**

**Why this separation?** The Python engine on `main` is stable and used in production. Rust work is
concurrent and experimental. Keeping them on separate branches prevents accidental pollution of the
Python mainline.

### Worktree Isolation

Each agent/task works in its own `.claude/worktrees/<name>` checkout with local isolation:

- **Rust builds:** Each worktree has its own `rust/target/` directory (build artifacts do not pollute
  the primary tree or other worktrees)
- **Python isolation:** Similar isolation via `.venv` per worktree or shared primary venv with
  `PYTHONPATH="$PWD/src"` override
- **Git safety:** Never `cd` into the primary tree (`/home/petem/src/Gamedev/lorecraft/`) for any
  git operation; all work happens in the worktree

See [`AGENTS.md`](AGENTS.md) for detailed worktree discipline and the shared-tree race conditions
to avoid.

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

## Development Setup

### Prerequisites

**Rust (required for rust-port branch):**
- Rustc 1.75+ (install via [rustup](https://rustup.rs/))
- Cargo (included with Rust)
- MSRV: 1.75 (minimum supported Rust version)

**Python (for tools, compatibility testing, and optional worker processes):**
- Python 3.12+
- SQLite (included with Python)

### Tooling Installation

#### macOS / Linux

```bash
# Install Rust (one-time, system-wide)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Verify
rustc --version  # should be 1.75+
cargo --version
```

#### Windows

Download and install from [rustup.rs](https://rustup.rs/), or use:
```powershell
winget install Rustlang.Rust.GNU
```

### Worktree Setup (Agent/Task)

Each agent works in a `.claude/worktrees/<name>` directory with isolated builds:

```bash
# (You are already in your worktree; no extra setup needed.)
# Confirm isolation:
pwd                              # should end in .claude/worktrees/<name>
git branch --show-current        # should be rust-port or a feature branch from rust-port

# Build Rust crates (artifacts stay local to this worktree's rust/target/)
cd rust && cargo build

# Run Rust tests
cd rust && cargo test

# Check with clippy
cd rust && cargo clippy --all-targets -- -D warnings
```

**Important:** Each worktree's `rust/target/` directory is local and separate. Cargo will not
pollute the primary tree or other worktrees.

### Python-Side Setup (Optional)

If working on Python compatibility or worker processes:

```bash
# Install Python dependencies
pip install -e ".[dev]"

# Run Python tests
make test

# Run linting
make lint
```

See [`Makefile`](Makefile) for all Python targets.

---

## Project Structure

### Rust (rust-port branch)

```
rust/
├── Cargo.toml                           # Workspace definition
└── crates/
    ├── lorecraft-protocol/              # IDs, envelopes, serialization, versioning
    ├── lorecraft-core/                  # Entities, effects, rules, validation
    ├── lorecraft-runtime/               # World/zone actors, routing, queues
    ├── lorecraft-events/                # Event types, stable dispatch, outbox
    ├── lorecraft-scheduler/             # Logical clock, due jobs, determinism
    ├── lorecraft-store/                 # sqlx persistence, transactions, migrations
    ├── lorecraft-server/                # Axum HTTP/WebSocket, auth, admin APIs
    ├── lorecraft-script/                # Script host trait, budgets, versioning
    ├── lorecraft-script-luau/           # mlua/Luau integration
    └── lorecraft-replay/                # Event hashing, replay validation
```

Each crate focuses on a subsystem boundary outlined in `docs/rust_migration_plan.md`.

### Python (main branch — reference only)

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
├── rust_migration_plan.md   # Phased Rust port strategy (READ THIS FIRST)
├── architecture_tiers.md    # Tier 1/2/3 split (Python reference)
├── engine_core.md           # Tier 1 specs (Python reference)
├── roadmap.md               # Python roadmap (reference only on rust-port)
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

### Rust Tests

```bash
cd rust

# Run all tests
cargo test --all

# Run with output
cargo test --all -- --nocapture

# Run a specific crate
cargo test -p lorecraft-protocol

# Run with logging (set RUST_LOG env var)
RUST_LOG=debug cargo test --all -- --nocapture

# Documentation tests
cargo test --doc

# Lint with clippy
cargo clippy --all-targets -- -D warnings

# Format check (run without --check to fix)
cargo fmt --all -- --check
```

### Python Tests (reference only)

Python tests on `main` are kept for reference. Rust tests validate the port incrementally
per `docs/rust_migration_plan.md` phases.

```bash
# Full test suite (parallel, excludes e2e/simulation)
make test

# With coverage
make test-cov

# E2E browser tests
make test-e2e

# Live-server simulation tests
make test-simulation
```

Tests use deterministic fixtures (seeded RNG, controlled clock) and golden-file comparisons
for replay validation during the port.

### Determinism & Replay

Both Rust and Python implementations use:
- Seeded pseudo-random number generation (controlled RNG streams per transaction)
- Deterministic ordering keys (command sequence, job priority, event dispatch order)
- Canonical state hashing for cross-implementation validation

See `docs/rust_migration_plan.md` § "Deterministic performance under load" for details.

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
