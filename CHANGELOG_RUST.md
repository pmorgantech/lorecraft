# Changelog — Rust Migration (rust-port branch)

All notable changes to the Rust migration and hybrid runtime are documented here. This branch
tracks the porting of Lorecraft's core engine from Python to Rust, following the phased
strangler pattern outlined in `docs/rust_migration_plan.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Phase 4 sub-slice 4c implementation (movement migration, the first mutating verb, live cutover):
  new `lorecraft-feature-move` Rust crate with `MoveEntity` derive/validate/parse, leave/arrival
  narration, and skill-gated defer protocol. State-snapshot hashing (`hash_state`) in both languages
  (Phase-0-deferred piece: `current_room_id` + `visited_rooms` oracle-matched). New additive fields
  `CommandOutcome.room_narration`/`arrival_narration` (Option A narration conveyance). New
  `GatewayOutbound::DeferToPython` frame for skill-gated moves. Python `build_move_request` handler
  (reuses live movement service reads), `MoveEntity` effect-applier (byte-identical state mutation:
  current_room_id, visited_rooms, connection-map relocation, narration placement). `flush_events()`
  now completes BEFORE commit, ensuring quest/NPC/follow/trigger reactions fire identically.
  Skill-gated moves defer to Python so RNG never enters Rust (OPEN ITEM #3). Movement `move_only`
  golden family (`move_only.json`/`.audit.json`/`.effects.json`/`.state_hash.json`, oracle-captured)
  proves 5-dimension state-parity. Registry-move fix: new `OutcomeApplied.moves` field; Rust applies
  each move to `ConnectionRegistry` BEFORE relaying deliveries (GAP #1 resolved). Movement enabled
  in `DEFAULT_RUST_VERBS` (`look,north,south,east,west`; rollback = `LORECRAFT_RUST_VERBS=""`).
  Direction routing extended in `route::decide` for `go <direction>` (decision b, precisely gated).
- Phase 4 sub-slice 4b implementation (live `look` cutover, hardening fixes, COMMAND_EXECUTED
  parity fix): `LORECRAFT_RUST_VERBS=look` default enable (real WS clients' `look` Rust-executed
  by default; rollback = explicit empty). New `GatewayOutbound::ExecutionRejected{command_id,
  direct_reply}` frame for adapter error/exception replies (replaces silent continue). Rust
  `tokio::time::timeout` backstop (`execute_timeout_ms`) on execute driver. Frozen-session guard
  checked first in `_on_build_snapshot` with short-circuit `ExecutionRejected` reply. Pending-slot
  map cleanup sweep on disconnect + cap (leak fix). Shared `webui/player/messages.py` de-duping
  frozen/error strings across Python path.
- COMMAND_EXECUTED bus emission from `apply_outcome` (was audit-row-only), restoring admin audit-feed
  + observer-driven reactions (achievement/quest/analytics) parity with Python path.
- Explicit DEFERRED decision record: Option (c) transport split — WS `look` live-cut over to Rust,
  `POST /command` `look` stays Python (HTMX rendering, WS receive-only). Browser-command-transport
  flagged as future-phase open item (dedicated increment AFTER Phase 4c, BEFORE broad Phase 5+
  migration) with three options and recommendation (option (i): browser→WS, Rust as real authority,
  FRONTEND SPECIALIST project).
- Phase 4 sub-slice 4a implementation (execution-routing protocol + Python persistence handlers
  + Rust routing seam + headless `look` parity harness, no live client cutover): new
  `GatewayInbound::BuildSnapshot`/`ApplyOutcome` and `GatewayOutbound::SnapshotReady`/
  `OutcomeApplied` framing protocol types in `lorecraft-protocol` plus Python mirror, reusing
  `CommandEnvelope`/`CommandOutcome`/`ScriptRequest`/`DeliveryDirective` verbatim with recursive
  `to_json`/`from_json`.
- Python `src/lorecraft/gateway/` persistence handlers: `snapshots.build_look_request` (reuses
  existing `InventoryService._build_look_request`), `effect_apply.apply_outcome` (applies
  effects via existing `engine/repos/*`, commits both game and audit SQLite DBs, records audit
  `command_executed` row, builds byte-identical `command_result` + `state_change` deliveries),
  `_on_build_snapshot`/`_on_apply_outcome` adapter handlers, `command_id`-keyed pending-execution map.
- Rust routing seam (`lorecraft-server::route.rs`): verb allow-list from `LORECRAFT_RUST_VERBS`
  (default EMPTY = pure Phase 3 rollback), `MigratedVerb` closed enum, conservative fallback
  (multi-command, arguments, disambiguation-number, non-migrated verb all → Python).
- Rust `look` execution driver (`lorecraft-server::execute.rs`): BuildSnapshot→run
  `lorecraft-feature-look`→ApplyOutcome→publish deliveries via Phase 3 `Deliver` path; `ws_player`
  consults `route::decide` to determine execution path.
- Headless `look` parity harness (`tests/simulation/test_phase4_look_parity.py`): real
  `lorecraft-gateway` subprocess + real Python adapter over real UDS + real WS client with
  `LORECRAFT_RUST_VERBS=look` proves byte-for-byte `command_result` and `look_only.audit.json`
  reproduction, with actor-exclusion confirmed. No live client cutover — exit tests only.

### Fixed
- Phase 4 sub-slice 4b parity fix: `apply_outcome` now emits `COMMAND_EXECUTED` on the bus (was
  audit-row-only), restoring admin audit-feed (`audit_appended` broadcast) and observer-driven
  reactions (achievement/quest/analytics listener callbacks) to fire identically to the Python path.
  Closed a real admin-audit-feed parity gap and restored the regressed slow-client backpressure test.
- Phase 4 sub-slice 4b round-trip hardening: adapter no longer silently continues on `BuildSnapshot`/
  `ApplyOutcome` handler exceptions; instead emits new `ExecutionRejected` reply frame. Rust execute
  driver wrapped in `tokio::time::timeout` backstop to prevent indefinite hangs on unresponsive
  Python adapter. Frozen-session guard checked first in `_on_build_snapshot` with short-circuit
  `ExecutionRejected` reply (fixes the two MUST-FIX-BEFORE-4b dormant defects from 4a).
- Pending-slot map now swept on disconnect + capped, preventing leak from long-lived connections.

### Phase 4 sub-slice 4c status (2026-07-13)
**4c's exit check is MET (movement + 5-dimension parity):** a non-skill-gated directional move
issued by a real WS client is LIVE-executed by Rust, reproduces the Python engine's `command_result`,
`audit` trail, `effects` list, and POST-COMMAND `state_hash` byte-for-byte via `move_only.*`
goldens. Mover is correctly relocated in Rust's `ConnectionRegistry`, reaches subsequent new-room
broadcasts. Skill-gated moves defer to Python (RNG stays Python). Rollback (allow-list empty
→ Python unchanged) intact. **Phase 4 is NOW COMPLETE** (all sub-slices 4a/4b/4c landed). See
`docs/rust_migration_plan.md`'s Phase 4 section 4c status for full detail, the three code-review
advisories (TOCTOU/WorldActor, audit-timing, unreachable panic), carry-forward deferrals, accepted
phase-scoping decisions (Option a: Python DB persistence, Option c: transport split), and next-
increment choices (browser-transport increment vs Phase 5). Phase 4 exit criterion: Rust owns
EXECUTION for migrated verbs on WS path (byte-identical effects/audit/state); Python owns persistence.

### Phase 4 sub-slice 4b status (2026-07-13)
**4b's exit check is MET (WS path):** a real WS client's `look` is LIVE-executed by Rust
default-on (`LORECRAFT_RUST_VERBS=look`), byte-identical `command_result` + audit golden +
admin `audit_appended` broadcast, actor-excluded room fan-out. Rollback (allow-list empty
→ Python unchanged) intact. **CONFIRMED DECISION — Option (c) transport split (deferred):**
WS `look` = Rust-executed; `POST /command` `look` stays Python (HTMX rendering, WS receive-only,
read-only parity). See `docs/rust_migration_plan.md`'s Phase 4 section 4b and "Future-phase open
items" (browser-command-transport) for full rationale, three options, and scheduling recommendation
(dedicated increment AFTER 4c, BEFORE Phase 5+ broad verb migration; FRONTEND SPECIALIST project).

### Phase 4 sub-slice 4a status
**4a's exit check is MET:** a headless `look` driven through Rust-execute→Python-persist
reproduces the byte-identical `command_result` + `look_only.audit.json` audit, with no real
client routed. Two MUST-FIX-BEFORE-4b dormant defects identified: (1) Rust-side indefinite hang
if Python handler raises, (2) frozen-session guard not reproduced on Rust path. See
`docs/rust_migration_plan.md`'s Phase 4 section 4a status for detail, the two must-fix findings,
and four 4c follow-ups (duplicate parse, TTL/disconnect-sweep, missing duration fields, debug
assertion gap).

---

## [0.3.1] - 2026-07-13

### Fixed
- Gateway follow-up #1: Rust `ConnectionRegistry` now learns room moves via new
  `GatewayOutbound::MovePlayer` frame (commit `a41f6fe`). A `POST /command` or WS
  room move now updates the authoritative Rust registry in-order, so players see
  new broadcasts in their NEW room immediately after moving.
- Gateway follow-up #3: Autonomous broadcasters (`NpcBehaviorService`,
  `QuestTimerService`, `WeatherFrontService`, `TransitService`, `MobileRouteService`)
  now route through `GatewayPushManager` instead of the empty-in-gateway-mode real
  `ConnectionManager` (commit `d408711`), so their server-initiated broadcasts reach
  gateway-connected clients.

### Changed
- Agent roster/tooling updates (`AGENTS.md`, `.claude/agents/`): model-tier
  assignments, re-added the `pytest-writer` agent, documented the 2-lane
  Test & QA split, and corrected `AGENTS.md`'s stale "e2e is serial" claim
  (e2e has run parallel since `a7f76b4`; simulation remains serial). No
  crate or Python engine code changed.

---

## [0.3.0] - 2026-07-13

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
- Sub-slice 3a implementation (forwarding protocol + Python adapter + Rust
  gateway plumbing, no live client cutover): `GatewayInbound`/
  `GatewayOutbound`/`DeliveryDirective`/`DeliveryTarget` gateway-framing
  protocol types in `lorecraft-protocol` plus the Python mirror
  `src/lorecraft/protocol/gateway.py`, with `command_id` added to
  `CommandReply` for request/reply correlation over the multiplexed UDS
  stream.
- Python `src/lorecraft/gateway/adapter.py` — a UDS listener + the
  `DirectiveConnectionManager`, backed by a new `ConnectionManagerProtocol`
  structural-typing seam in `engine/game/connection_manager.py` so the
  connection manager is injectable without `cast`/`type: ignore`; the shared
  command-handling core was extracted out of `main.py` into
  `webui/player/ws_command.py` + `ui_snapshots.py` so both the live `/ws`
  handler and the new adapter run identical logic.
- Rust `lorecraft-events` crate: `ConnectionRegistry` (three sorted-read
  connection maps) and `dispatch.rs` bounded, non-blocking `try_send` fan-out,
  proving one slow/full recipient queue never stalls delivery to a sibling
  recipient.
- Rust `lorecraft-server` crate: `forward.rs` UDS framed client
  demultiplexing correlated `CommandReply`s from uncorrelated `Deliver`
  pushes, an Axum app skeleton with a working health-check route, and
  honestly-scoped `ws_player.rs`/`ws_admin.rs`/`auth.rs` stubs for sub-slices
  3b/3c; added `tokio` as the workspace's first async dependency and pinned
  `axum = "=0.8.4"` exactly (0.8.9+ requires rustc 1.80, above this
  workspace's 1.75 MSRV).
- A cross-manager `DeliveryDirective` parity harness proving the adapter's
  recorded directives resolve to the same payloads the real
  `ConnectionManager` would send to a room-mate, closing sub-slice 3a's exit
  check. **Sub-slices 3b (player `/ws` cutover) and 3c (admin cutover +
  backpressure) are not yet built** — the Phase 3 phase-level exit criterion
  remains open.
- Sub-slice 3b implementation (player `/ws` cutover via Rust front-door):
  `GatewayAdapter` wired with `gateway_enabled` flag (default off, immediate
  rollback); UDS hardening (0600 socket perms, stale-socket cleanup);
  follow-break-on-disconnect wired.
- Rust player `/ws` termination: `?ticket=` handoff, single-live-connection
  rule, one UDS link per WS (closes OPEN ITEM 1), per-connection bounded
  outbound writer task, new `lorecraft-gateway` binary with port-discovery
  output.
- Rust transparent HTTP reverse proxy for all non-WS requests to Python
  uvicorn backend (reqwest 0.13.3, loopback-only, no TLS); hop-by-hop header
  stripping, Set-Cookie passthrough; no SSE in player UI confirmed.
- Test harness: dual-process fixture gated by `LORECRAFT_THROUGH_RUST=1` that
  builds+spawns gateway and Python app; exit tests (reconnect, multiplayer,
  simulation) run through Rust front door; bad-ticket→WS-1008 test; rollback
  (flag off) verified.
- Autonomous clock/weather broadcasts through gateway via `GatewayPushManager`
  + per-connection outbound queues so server-initiated pushes reach gateway
  clients.
- Fixed BLOCKING disconnect-fan-out race via `GatewayOutbound::DisconnectAck`
  frame with 5s backstop, ensuring tear-down deliveries reach remaining
  players before link tears down.
- Fixed EXIT-BLOCKING `POST /command` broadcast routing: `broadcast_command_effects`
  now routes through `GatewayPushManager` so cross-player broadcasts from
  non-WS commands reach Rust-connected browsers.
- Sub-slice 3c implementation (admin `/admin/ws` cutover + backpressure/slow-client
  policy): distinct `AdminAuthResult{accepted}` frame in `lorecraft-protocol` (resolves
  the deferred admin `AuthResult.player_id` shape), `DeliveryTarget::Admin` for
  fan-out to all admin consoles, `DeliveryDirective.coalesce_key: Option<String>` for
  efficient frame deduplication.
- Rust `lorecraft-events::backpressure`: consecutive-overflow slow-client detection
  → `SlowConsumer` disconnect (WS 1013), `AdminRegistry` (push-only deterministic
  fan-out), `CoalescingQueue` (keep-latest by key; feed_append/keyless never dropped),
  `TokenBucket` rate-limit primitive.
- Rust admin `/admin/ws` cutover: accept-before-validate semantics with close 1008 on
  reject (preserving admin UI's 1008-vs-1006 distinction from current Python handler);
  `validate_admin_token` handoff; `DisconnectHub` watch-channel close propagation
  that closes slow consumers with 1013 without blocking co-located siblings; coalescing
  writer; player command rate-limit with in-band `{"type":"error","code":"rate_limited"}`
  frame.
- Python `AdminGatewaySink`: routes `AdminBroadcaster` pushes to Rust as
  `Deliver{DeliveryTarget.Admin}` frames; adapter `ValidateAdminToken` now returns
  `AdminAuthResult`; policy helper `coalesce_key_for(payload)` (Tier 2: `state_change`
  with sorted-panel keys, admin `content_changed` with resource key, coalescible;
  feed_append/chat/join-leave/time_update/audit_appended keyless). Flag-off remains
  byte-identical.
- Operational env-knobs for backpressure/rate-limit tuning: `LORECRAFT_GATEWAY_QUEUE_DEPTH`,
  `_MAX_OVERFLOW`, `_COMMAND_BURST`, `_COMMAND_RATE`, `_SEND_BUFFER_BYTES` (static config,
  defaults unset = production unchanged; flagged as future operational live-tunable
  candidates per AGENTS.md pattern).
- Fixed FALSE-GREEN slow-client test: replaced implicit-skip test with deterministic
  raw-socket stall (genuinely stops reading, ~18.77s, cannot skip, hard-asserts
  teardown without blocking a co-located well-behaved consumer).

### Fixed
- Slow-client backpressure test no longer skips silently — now a genuinely-stalled
  raw non-reading socket producing deterministic, host-independent behavior.

### Phase 3 completion note
**All three sub-slices (3a / 3b / 3c) are now complete.** The phase-level exit
criterion is MET: both player and admin clients run through the Rust gateway;
disconnect/reconnect + slow-client tests match current Python semantics. Ten follow-ups
flagged (6 from 3b correctness gaps / hardening, 4 from 3c advisories) — must be
addressed before "gateway enabled by default" but do not block Phase 3's phase-level
gate. See `docs/rust_migration_plan.md`'s Phase 3 section for the consolidated
follow-up list and the natural next increment (Phase 4: vertical gameplay slice).

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
