# Implementation Guides Index

This document is a master index of feature design and implementation guides. Guides are organized by status:
- **In Design:** Sprints planned but not yet implemented
- **Implemented:** Completed sprints with documented implementation patterns (reference/archive)
- **Foundational:** Architectural docs and patterns for all implementation

Each guide provides detailed workflows, code examples, testing patterns, and design rationale.

> **Note on organization:** Feature guides are being reorganized into a `docs/features/` structure. Completed guides can be moved to `docs/features/implemented_*` to keep active development docs separate. This index will be updated as the reorganization proceeds.

---

## In-Design Guides (Active Development)

| Guide | Sprint | Subsystem | Purpose | Status |
|-------|--------|-----------|---------|--------|
| [combat_system.md](combat_system.md) | 31–33 | Combat | Tick-based combat, damage, NPC AI, kill credit, loot | Design phase; implementation TBD |
| [death_resurrection.md](death_resurrection.md) | 32 | Death & Resurrection | Death mechanics, corpse loot, resurrection spawn | Design phase; implementation TBD |
| [dialogue_npcs_quests.md](dialogue_npcs_quests.md) | 10, 30 | NPCs, Quests, Dialogue | NPC scheduling, dialogue trees, quest branching | Sprint 10 implemented; Sprint 30 in design |

---

## Implemented Guides (Reference/Archive)

These features are fully implemented. The guides below document the design and implementation patterns used. They can be moved to [`docs/features/implemented_*`](#feature-docs-organization) when no longer actively developed.

| Guide | Sprint | Subsystem | Purpose | Completion |
|-------|--------|-----------|---------|-------------|
| [player_authentication.md](player_authentication.md) | 4 | Player Authentication | JWT flow, WebSocket tickets, account creation, OAuth extensibility | ✅ Complete |
| [disconnect_handling.md](disconnect_handling.md) | 13 | Disconnect Handling | Grace periods, reconnection, system-controlled state | ✅ Complete |
| [world_versioning_changesets.md](world_versioning_changesets.md) | 11 | World Versioning | Changeset lifecycle, Builder Mode, lazy migration | ✅ Complete |
| [command_parser.md](command_parser.md) | 2–3 | Command Parsing | Text parsing, command dispatch, grammar rules | ✅ Complete |
| [parser_and_commands.md](parser_and_commands.md) | 2–3, 9–10 | Parser & Commands | Command registration, conditions, patterns | ✅ Complete |
| [inventory_equipment.md](inventory_equipment.md) | 22–23 | Inventory & Equipment | Item stacks, slots, encumbrance, modifiers | ✅ Complete |
| [tooling_infrastructure.md](tooling_infrastructure.md) | 10.5 | Admin Tooling | World CLI, content validators, analytics queries | ✅ Complete |
| [trade_economy.md](trade_economy.md) | 28 | Trading & Economy | Shops, currency, player-to-player trading, escrow | ✅ Complete |
| [transit_systems.md](transit_systems.md) | 29 | Transit & Travel | Routes, waypoints, schedules, position interpolation | ✅ Complete |
| [discipline_ability_system.md](discipline_ability_system.md) | 77–78 | Disciplines & Abilities | Replaced `features/skills/` + `features/progression/skill_tree.py` with a unified Discipline → Ability model (Tier 1 mechanism in 77, Tier 2 policy/content in 78); data-driven, non-combat seed disciplines, combat-ready seam | ✅ Complete (pending Integrator merge) |

---

## Foundational & Architectural Docs

These documents are not feature-specific but provide foundational patterns, APIs, and design principles for all implementation.

| Document | Purpose |
|----------|---------|
| [`architecture.md`](architecture.md) | Comprehensive architecture overview; master design reference for the 5-layer model (Services → Rules → Transactions → Events → Scheduler) |
| [`engine_core.md`](engine_core.md) | Tier 1 primitive specifications (Sprints 16–21); binding reference for schemas, APIs, invariants, and migration blast-radius tables |
| [`feature-registration.md`](feature-registration.md) | How to build and register Tier 2 features; shows the pluggable architecture pattern all new features should follow |
| [`architecture_tiers.md`](architecture_tiers.md) | Explains the Tier 1/2/3 split, current filesystem layout, and how to disable or extend Tier 2 features |
| [`tier_modules.md`](tier_modules.md) | File-by-file classification of each module as Tier 1, Tier 2, or mixed; quick reference for understanding the codebase |
| [`roadmap.md`](roadmap.md) | **Single source of truth** for what's done and what's next — sprint-by-sprint task tables, dependency reference, and current status |

---

## End-User & Builder Guides

These documents are for players and world builders, not implementers.

| Document | Audience | Purpose |
|----------|----------|---------|
| [`user_guide.md`](user_guide.md) | Players | In-game commands, mechanics, how to play |
| [`admin_builder_guide.md`](admin_builder_guide.md) | World Builders | Admin tools, world design workflow, NPC/quest creation |
| [`world_building.md`](world_building.md) | World Builders | YAML authoring conventions, schema reference, content patterns |
| [`wishlist.md`](wishlist.md) | Product Designers | Planned features, design pillars, longer-term ideas |

---

## Feature Docs Organization

### Structure

Feature design documents are gradually being reorganized into a `docs/features/` directory structure:

```
docs/features/
├── in_design/
│   ├── combat_system.md              # Sprint 31–33 (in design)
│   ├── death_resurrection.md         # Sprint 32 (in design)
│   └── dialogue_npcs_quests.md       # Sprint 30 (in design)
│
└── implemented/
    ├── player_authentication.md      # Sprint 4 (complete)
    ├── disconnect_handling.md        # Sprint 13 (complete)
    ├── world_versioning.md           # Sprint 11 (complete)
    ├── command_parser.md             # Sprints 2–3 (complete)
    ├── parser_and_commands.md        # Sprints 2–3, 9–10 (complete)
    ├── inventory_equipment.md        # Sprints 22–23 (complete)
    ├── tooling_infrastructure.md     # Sprint 10.5 (complete)
    ├── trade_economy.md              # Sprint 28 (complete)
    └── transit_systems.md            # Sprint 29 (complete)
```

### Purpose of Each Section

**`docs/features/in_design/`** — Active sprint work. Guides in this section:
- Define the design and architecture for upcoming implementation
- Include code examples, schemas, and workflows
- Are living documents updated during implementation
- Move to `implemented/` once the sprint completes

**`docs/features/implemented/`** — Reference and archive. Guides in this section:
- Document completed implementation patterns
- Serve as reference for how similar features should be built
- Can be archived or moved to a read-only section when no longer actively developed
- Remain linked from [`roadmap.md`](roadmap.md) for context

### Current Status

> **Transition in progress (2026-07-04):** Implementation guides are currently in the root `docs/` directory. A gradual migration to `docs/features/` will:
> 1. Keep active development docs (`in_design/`) separate from archived guides
> 2. Clarify which docs are "live" (actively being implemented) vs. "reference" (complete)
> 3. Make the doc structure mirror the codebase's Tier 1/2 split
>
> This index will be updated as docs are moved. For now, the guides are listed by status (above) and remain in their original locations.

---

## What Each Guide Contains

Each implementation guide typically includes:

1. **Overview** — High-level concept, design rationale, and key decisions
2. **Data Model** — SQLModel table definitions with schema examples and constraints
3. **Workflows** — Step-by-step execution flows with code examples and error handling
4. **Configuration** — Environment variables, tuning knobs, and deployment considerations
5. **Testing** — Pytest patterns for unit, integration, and simulation tests
6. **Appendices** — Migration strategies, deprecated patterns, or related systems

---

## How to Use These Guides

### During Implementation

1. **Check [`roadmap.md`](roadmap.md)** — Find which sprint you're working on and its dependencies
2. **Review [`engine_core.md`](engine_core.md)** — Understand Tier 1 primitives your feature depends on
3. **Read the feature guide** — Jump to the guide for the sprint you're implementing (either in this index or under `docs/features/in_design/`)
4. **Follow code examples** — Each guide includes actual Python/SQLModel patterns; adapt them to your implementation
5. **Reference the tests** — Each guide includes pytest patterns; use them as templates for your test suite

### For Code Review

When reviewing a PR for a completed feature, reference the corresponding guide (in [`docs/features/implemented/`](#feature-docs-organization)) to verify the implementation matches the design. For in-progress features, use guides in `docs/features/in_design/`.

### For Onboarding

New developers should:

1. Read [`README.md`](../README.md) for a high-level project overview
2. Read [`architecture.md` § 1–5](architecture.md#1-project-identity--philosophy) for foundational concepts (Services, Rules, Transactions, Events, Scheduler)
3. Read [`engine_core.md`](engine_core.md) to understand Tier 1 primitives
4. Skim [`roadmap.md`](roadmap.md) to understand sprint sequencing and dependencies
5. Check [`tier_modules.md`](tier_modules.md) to understand the Tier 1/2 split in the actual codebase
6. Deep-dive into the feature guide for the work you're about to do

### For Customizing the Engine

If you're building a custom game or disabling Tier 2 features, start with:
1. [`architecture_tiers.md`](architecture_tiers.md) — Understand Tier 1 vs. Tier 2
2. [`tier_modules.md`](tier_modules.md) — See which modules you can safely remove
3. [`feature-registration.md`](feature-registration.md) — Learn how to add your own Tier 2 features

---

## Relationship to Other Docs

### Architectural vs. Implementation

- **[`architecture.md`](architecture.md)** — Master design reference; the "blueprint"
- **[`engine_core.md`](engine_core.md)** — Tier 1 binding specifications; what never changes
- **Feature guides** (here) — "Contractor's handbook"; vertical slices with code examples and edge cases
- **[`roadmap.md`](roadmap.md)** — **Single source of truth**: sprint sequencing, what to build in what order, and what's actually done

Think of it this way:
- Read **architecture.md** to understand *why* the design is structured this way
- Read **engine_core.md** to understand the immutable Tier 1 contracts
- Read **feature guides** to understand *how* to implement a specific feature
- Check **roadmap.md** to know what's done and what to work on next

### Living Documents vs. Historical Reference

**Living documents** (actively maintained):
- `roadmap.md` (sequencing changes as priorities evolve; updated as sprints complete — the single source of truth for progress)
- `architecture.md` (updated when design patterns change)
- `architecture_tiers.md` (clarifies Tier split in evolving codebase)
- `user_guide.md`, `admin_builder_guide.md`, `world_building.md` (growing as features ship)

**Historical reference** (snapshot of design at completion):
- `player_authentication.md` — Sprint 4 complete; design is frozen
- `world_versioning_changesets.md` — Sprint 11 complete; design is frozen
- (Other completed guides) — Reference for "how we built similar features"

---

## Contributing

When adding a new major subsystem:

1. **Design phase:** Update [`roadmap.md`](roadmap.md) to sequence the work and [`engine_core.md`](engine_core.md) or [`feature-registration.md`](feature-registration.md) if it affects Tier 1
2. **Implementation:** Create a focused implementation guide following the pattern above (store in `docs/features/in_design/` once the directory structure is finalized)
3. **After completion:** Move the guide to `docs/features/implemented/` and update this index
4. **Update cross-references:** Ensure [`roadmap.md`](roadmap.md) and this index both point to the guide

---

## Quick Links

**Getting started?** Start here:
- [`README.md`](../README.md) — Project overview
- [`architecture.md`](architecture.md) — Design principles
- [`roadmap.md`](roadmap.md) — What to work on

**Building a feature?** Refer to:
- [`engine_core.md`](engine_core.md) — Tier 1 specs you must follow
- [`feature-registration.md`](feature-registration.md) — How to register your feature
- Related feature guide — From the "In Design" or "Implemented" sections above

**Customizing the engine?** Read:
- [`architecture_tiers.md`](architecture_tiers.md) — Tier 1/2 split
- [`tier_modules.md`](tier_modules.md) — Which modules are which tier
- [`feature-registration.md`](feature-registration.md) — How to add custom features

---

*Last updated: 2026-07-04*
*This index is kept up-to-date with the roadmap and sprint completion.*
