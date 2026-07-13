# Changelog — Rust Migration (rust-port branch)

All notable changes to the Rust migration and hybrid runtime are documented here. This branch
tracks the porting of Lorecraft's core engine from Python to Rust, following the phased
strangler pattern outlined in `docs/rust_migration_plan.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- `docs/rust_migration_plan.md` — Phase 3 kickoff design spec: transport/
  connection-ownership migration split into three sequenced sub-slices (3a
  forwarding protocol + adapter + gateway plumbing, 3b player `/ws` cutover,
  3c admin `/admin/ws` cutover + backpressure), a UDS length-prefixed-JSON
  transport between the Rust gateway and a new Python forwarding adapter, new
  `GatewayInbound`/`GatewayOutbound`/`DeliveryDirective` gateway-framing
  protocol types, the `DirectiveConnectionManager` design for reusing existing
  Python fan-out logic, auth-handoff and disconnect/reconnect semantics, and
  the new-protective (not ported) backpressure/slow-client policy.

---

## [0.2.0] - 2026-07-12

### Added
- `docs/rust_migration_plan.md` — Phase 2 kickoff design spec: hash target
  (`ScriptResult` via `look_effects`, not the audit-event golden), Rust crate
  placement (`lorecraft-replay`/`lorecraft-scheduler`/`lorecraft-core`/
  `lorecraft-runtime` plus new `lorecraft-feature-look`), deferred cross-language
  RNG parity, fixture-capture design (`rust/fixtures/look_only/`), and the
  recursive `to_json`/`from_json` prerequisite carried over from the Phase 0/1
  kickoff follow-ups.
- Recursive `to_json`/`from_json` on the Python protocol container types
  (`CommandEnvelope`, `CommandOutcome`, `ScriptRequest`, `ScriptResult`, and
  friends), plus a fixture-capture golden test and the checked-in
  `rust/fixtures/look_only/{request.json,expected_result_hash.txt}` artifacts used
  as the cross-language parity input.
- Rust world-actor skeleton: a bounded input queue with deterministic
  drain-then-sort-then-dispatch ordering in `lorecraft-runtime`, a logical clock and
  `(logical_time, receive_sequence)` ordering-key comparator in
  `lorecraft-scheduler`, and per-stream RNG derivation (`derive_stream(world_seed,
  stream_id) -> ChaCha8Rng`) in `lorecraft-core`.
- `lorecraft-replay` — canonical-JSON serialization and sha256 hashing ported from
  Python's `replay_hash.py`, including matching float-reject behavior (an
  integer-valued float such as `2.0` is rejected on both sides).
- New `lorecraft-feature-look` crate — a Rust port of `look_pure.py`'s
  `look_effects` policy function, kept out of `lorecraft-runtime`/`-core`/
  `-scheduler` to avoid a Tier 1/Tier 2 policy leak.
- Cross-language `look` `ScriptResult` parity proof: the Rust
  `look_only_fixture_parity` test hashes its `look_effects` output and asserts it
  matches the Python-captured golden hash — both sides produce
  `ff78f14d4adff1daf3fa1c6a4ce3aa4a537f4384ff29011dca14460c7b2c95ca`, closing out
  Phase 2's exit criterion.

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
