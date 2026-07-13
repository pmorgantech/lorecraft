# Changelog — Rust Migration (rust-port branch)

All notable changes to the Rust migration and hybrid runtime are documented here. This branch
tracks the porting of Lorecraft's core engine from Python to Rust, following the phased
strangler pattern outlined in `docs/rust_migration_plan.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-07-12

### Added
- Initial Rust workspace setup with Cargo.toml and crate stubs
- `rust/crates/lorecraft-protocol` — protocol types, versioning, and serialization
- `docs/rust_migration_plan.md` — comprehensive architecture guide for the port
- `docs/rust_migration_plan.md` — Phase 0/1 kickoff design spec: replay hashing,
  slow-handler and mutation-scan tooling (Phase 0), and `lorecraft-protocol` crate +
  Python `protocol/` mirror contracts with a `look` pure-function adapter (Phase 1)
- Phase 0 evidence tooling: canonical replay-event hashing (`replay_hash.py`), a
  read-only `look_only` parity fixture, an event-loop-blocking characterization test,
  and an AST-based SQL/ORM mutation scanner (`mutation_scan.py`, 87 findings across 32
  files as the Phase 4/5 conversion backlog).
- Phase 1 language-neutral contracts: `CommandEnvelope`/`CommandOutcome`/
  `ScriptRequest`/`ScriptResult`/`Effect`/`EntitySnapshot`/`OutboundMessage` defined in
  the `lorecraft-protocol` Rust crate with a symmetric Python mirror
  (`src/lorecraft/protocol/`), and the `look` command adapted to the effect model via a
  pure `look_effects` function with zero behavior change.
- Agent configuration updates (`AGENTS.md`, `.claude/agents/`) scoped for Rust + Python work
- `README.md` updates with Rust tooling requirements and worktree setup guidance

### Changed
- Branch `rust-port` established as long-lived integration point (never `main` or `develop`)
- Agent descriptions now emphasize dual Python/Rust capability requirements

### Deprecated
- Python-only dev workflow; Rust tooling now required for rust-port branch work

### Security
- None yet

### Fixed
- None yet

---

## Notes on Version Coordination

During the migration (Phases 0–7 per `docs/rust_migration_plan.md`):

- **Rust-port versions** track architectural milestones (protocol definition, shadow runner,
  transport layer, vertical slices, Tier 1 authority, Lua/Luau scripting, feature ports).
- **Python versions** on `main` follow the existing semver scheme independently.
- Version bumps on rust-port reflect the port's progress, not feature feature parity with
  main's concurrent work.
- Merging between branches (if/when needed) will reconcile version numbers explicitly.

---

## Historical Context

Prior to this branch, Lorecraft was a pure-Python engine (v0.94.0+). The Rust port is a
multi-year, phased effort to move the authoritative core to Rust while retaining Python
for tools, worker processes, and gradual feature migration. See
`docs/rust_migration_plan.md` for the full strategy.
