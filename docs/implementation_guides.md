# Implementation Guides Index

This directory contains focused, code-focused implementation guides extracted from the comprehensive architecture document. Each guide covers a specific subsystem with detailed workflows, code examples, and testing patterns.

## Quick Reference

### Core System Guides

| Guide | Subsystem | Purpose |
|-------|-----------|---------|
| [player_authentication.md](player_authentication.md) | Player Authentication (§21) | Local username/password auth, JWT flow, WebSocket ticket system, OAuth extensibility |
| [disconnect_handling.md](disconnect_handling.md) | Disconnect Handling (§18) | Grace periods, reconnection, system-controlled state, combat pause behavior |
| [world_versioning_changesets.md](world_versioning_changesets.md) | World Versioning & Changesets (§19) | Changeset lifecycle, Builder Mode, lazy migration, conflict scanning |
| [combat_system.md](combat_system.md) | Combat System (§15) | Tick-based combat, damage resolution, NPC AI, kill credit, loot drops |

## What's in Each Guide

Each implementation guide includes:

1. **Overview** — High-level concept and design rationale
2. **Data Model** — SQLModel table definitions with schema examples
3. **Workflows** — Step-by-step execution flows with code examples
4. **Configuration** — Environment variables and tuning knobs
5. **Testing** — Pytest patterns for unit and integration tests

### player_authentication.md

**Covers:**
- Account creation on first login (no separate registration)
- Username/password hashing (bcrypt/argon2)
- JWT access tokens (15-minute lifetime)
- Refresh token rotation (8-hour lifetime)
- WebSocket ticket flow (single-use, 60-second TTL)
- OAuth extensibility path for when deployed off-LAN

**Key Code Examples:**
- `issue_access_token()` and `issue_refresh_token()` functions
- `/auth/login` endpoint (creates account or logs in)
- `/auth/ws-ticket` endpoint (exchanges JWT for WebSocket ticket)
- `/auth/refresh` endpoint (rotates refresh token)
- WebSocket handshake with ticket validation
- Google OAuth callback handler (for future use)

### disconnect_handling.md

**Covers:**
- Grace period behavior (60 seconds default)
- Player character remaining in world during grace period
- Combat pause for disconnected players
- Reconnection flow (within grace period)
- Expiration handling (system-controlled state, defensive AI takeover)
- Dialogue and trade cancellation on expiration

**Key Code Examples:**
- `handle_disconnect()` — transition to grace period
- `handle_reconnect()` — reattach and resume
- `handle_grace_period_expired()` — system takeover
- Full reconnect sync message structure
- `ConnectionManager` integration
- Scheduler integration for expiration checks

### world_versioning_changesets.md

**Covers:**
- Changeset lifecycle (DRAFT → SCANNING → READY → LIVE)
- Conflict scanner (broken refs, active players, renamed flags)
- Lazy player migration on login
- Builder Mode (isolated SQLite clone per changeset)
- Ghost sessions (preview changes without affecting live players)
- Optimistic locking (version field on all editable entities)
- Rollback strategy (re-import previous YAML + bump version)

**Key Code Examples:**
- `Changeset` and `ChangesetItem` table definitions
- `scan_changeset()` — comprehensive conflict detection
- `promote_changeset()` — atomic promotion workflow
- `apply_migration()` — lazy player flag migration
- `create_builder_clone()` — SQLite clone setup
- Room displacement and fallback handling

### combat_system.md

**Covers:**
- Tick-based combat model (speed determines action frequency)
- Six-stat system (Strength, Agility, Vitality, Intellect, Presence, Fortitude)
- Damage rolls (d20 + modifiers, armor reduction, crits)
- NPC combat behaviors (aggressive, defensive, cowardly, territorial, guard)
- Fleeing and negotiation (re-enter dialogue with `combat_context=CORNERED`)
- Kill credit (participation-based, not last-hit)
- Loot drops from NPC death
- Combat-gated commands (`NOT_IN_COMBAT`, `IN_COMBAT` conditions)

**Key Code Examples:**
- `CombatSession` table and combatant structure
- `create_session()` — initiate combat
- `resolve_combat_tick()` — action resolution each tick
- `resolve_attack()` — hit roll + damage calculation
- `npc_combat_ai_decide()` — NPC decision logic per behavior type
- `compute_kill_credit()` — participation-based credit
- `drop_loot()` — loot generation on death

---

## How to Use These Guides

### During Implementation

1. **Start with [architecture.md](architecture.md)** — Get the full picture, understand the 5-layer model (Services → Rules → Transactions → Events → Scheduler)
2. **Pick a subsystem** — When implementing a specific feature, jump to the corresponding guide
3. **Follow the code examples** — Copy patterns, adapt to your codebase
4. **Run the tests** — Each guide includes pytest patterns; use them as templates

### For Code Review

When reviewing a pull request touching authentication, combat, or world state, reference the relevant guide to ensure the implementation matches the design.

### For Onboarding

New developers should:
1. Read [architecture.md § 1–5](architecture.md#1-project-identity--philosophy) for foundational concepts
2. Skim the [Build Order Recommendation (§28)](architecture.md#29-build-order-recommendation) to understand phase dependencies
3. Deep-dive into the guide for the phase they're working on

---

## Relationship to architecture.md

The comprehensive [architecture.md](architecture.md) remains the source of truth for the overall design. These guides are **extracted vertical slices** that provide:

- **More code:** Actual Python/SQLModel examples, not pseudocode
- **More detail:** Implementation edge cases, testing patterns
- **More context:** Why specific design choices were made

Think of architecture.md as the blueprint and these guides as the contractor's handbook.

---

## Open Questions & Future Work

See [architecture.md § Gaps & Future Considerations](architecture.md#28-gaps--future-considerations) for:

- LAN-party auth hardening for off-LAN deployment
- Command throughput rate limiting
- Audit log retention policy
- Changeset staleness management
- Engine code-schema migrations (Alembic strategy)
- Process supervision (systemd/container health checks)

---

## Contributing

When adding a new major subsystem:

1. Update [architecture.md](architecture.md) with the high-level design (following §1–28 structure)
2. Create a focused implementation guide (following the pattern here)
3. Update this index

---

*Last updated: 2026-07-01*
*Extracted from: [text-adventure-engine-implementation-guide-1.pdf](../text-adventure-engine-implementation-guide-1.pdf)*
