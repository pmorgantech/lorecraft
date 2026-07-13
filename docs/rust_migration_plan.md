# Lorecraft Rust Migration and Hybrid Runtime Plan

> Repository review basis: `pmorgantech/lorecraft` at commit
> `b2044a987a70eab39f06d5cc34064237da2bcbcf` (July 2026), focused on
> `src/lorecraft`.

## Executive recommendation

The migration is feasible, and Lorecraft already has several useful seams for it:

- Tier 1 engine primitives are separated from optional Tier 2 features.
- Commands already run through a common context and transaction lifecycle.
- Events, scheduling, deterministic RNG, repositories, and WebSocket delivery are
  identifiable subsystems rather than scattered accidents.
- Simulation, replay, audit, and latency tooling already exist and can serve as
  compatibility gates during an incremental migration.

The recommended destination is **a Rust-owned authoritative engine with a
versioned scripting boundary**, not a Python application with a growing pile of
Rust extension functions.

Rust should eventually own:

- network listeners and WebSocket connection state;
- command admission, queues, deadlines, and backpressure;
- world clock, tick/event ordering, scheduler, and deterministic RNG streams;
- authoritative entity state and state-transition validation;
- database transactions, migrations, audit/outbox writes, and repository access;
- the event bus and delivery fan-out;
- script loading, capability enforcement, quotas, and result validation.

Scripts should implement policy and game-specific behavior:

- command mechanics and feature rules;
- NPC decisions and quest transitions;
- content-specific conditions, descriptions, and effects;
- builder-created extensions that operate through a deliberately small API.

For the hot-path scripting language, **Lua/Luau is the lowest-complexity fit** for
an embedded, multi-core Rust engine. Keep Python for authoring tools, importers,
admin workflows, tests, and optionally trusted mechanics running in isolated
worker processes. Supporting Python scripts is reasonable, but the first design
should not depend on multiple embedded CPython subinterpreters.

The core rule is:

> Rust owns truth. Scripts inspect bounded input and propose effects. Rust
> validates, orders, commits, audits, and publishes those effects.

That rule provides both flexibility and predictable performance. It also avoids
passing live ORM sessions, sockets, mutable entities, or Rust locks into a script
runtime.

## Feasibility verdict

| Question | Assessment |
| --- | --- |
| Can the core engine move to Rust? | Yes. The Tier 1 split gives it a credible boundary. |
| Can existing Python mechanics be retained during migration? | Yes, through a message/effect contract or temporary compatibility host. |
| Will moving only WebSockets and timing to Rust solve performance? | No. Current Python handlers and synchronous DB work would remain the serialized hot path. |
| Can multiple CPU cores be used? | Yes, with actor/shard ownership and independent script runtimes—not shared mutable world objects. |
| Are multiple embedded Python interpreters the best first step? | No. They add package, FFI, lifecycle, and state-isolation risk. |
| Is Lua/Luau a plausible primary scripting layer? | Yes. Independent VMs can be assigned to shards and tightly capability-limited. |
| Can this remain deterministic under load? | Yes, if ordering, RNG, clocks, script versions, and commit/publish semantics are made explicit. |
| Is this a simple language port? | No. It is an architectural migration and should use a strangler approach. |

Overall: **high technical feasibility, medium-to-high migration complexity, high
risk if attempted as a rewrite, and manageable risk if migrated by vertical
slices with replay and load-test gates.**

## What the current code says

### The useful seams

Lorecraft's current architecture is unusually well prepared for a hybrid
migration:

- `engine/` is content-agnostic and prevented from importing `features/` or
  `webui/` by a boundary test.
- `FeatureManifest`, feature discovery, and registration already express a
  plugin model.
- `CommandEngine` centralizes parse, conditions, rules, handler execution,
  event flushing, commit, rollback, audit, and command completion.
- `EventBus` centralizes ordered synchronous event dispatch.
- `SchedulerService` turns clock advances into due-work events.
- `GameRng` is already the sole sanctioned randomness source.
- `ConnectionManager` owns player/socket and room/player mappings.
- simulation replay and audit regression provide the beginnings of a semantic
  compatibility suite.

Those are natural Rust crate boundaries and scripting host calls.

### The current bottleneck shape

The WebSocket receive loop calls `_handle_websocket_command()`, which creates
synchronous SQLModel sessions and runs `CommandEngine.handle_command()` directly
inside the async request task. A command can therefore perform all of the
following before the event loop gets control back:

1. SQL reads to build `GameContext` and resolve entities;
2. parsing, condition evaluation, and rules;
3. a Python feature handler;
4. synchronous event handlers;
5. SQL state and audit commits;
6. response snapshot construction;
7. sequential WebSocket fan-out.

This is more important than the headline fact that Python has a GIL. The
architecture currently combines:

- CPU-bound Python work;
- blocking/synchronous DB access;
- one shared in-process event bus;
- one shared RNG instance;
- single-writer SQLite;
- mutable application-wide registries;
- network delivery in the command completion path.

Moving the socket acceptor to Rust while leaving this pipeline intact would
improve connection handling and fan-out, but command latency and head-of-line
blocking would still be dominated by the Python/DB transaction path.

### Repository-specific migration pressure points

| Current area | Observation | Migration implication |
| --- | --- | --- |
| `main.py` | Large composition root wires transport, DB, clock, features, schedulers, services, admin pushes, and content. | Split boot/composition from the runtime before or during migration. |
| `GameContext` | Carries SQLModel `Session`, repositories, mutable models, WebSocket manager, event bus, services, callbacks, messages, and deferred async deliveries. | Do not expose this object across FFI. Replace it with immutable script input plus effect output. |
| `CommandEngine` | Strong central lifecycle, but handlers mutate live ORM state through `GameContext`. | Preserve lifecycle semantics while replacing direct mutation with validated effects. |
| `EventBus` | Synchronous and priority ordered; handler failures are isolated. | Rust can preserve this semantic contract, with explicit work vs notification events. |
| `pending_deliveries` | Sync handlers enqueue coroutine factories for later WebSocket delivery. | Evidence that transport and mechanics need a formal outbox boundary. |
| `WorldClockRunner` | Async task performs synchronous DB/session work and emits inline handlers. | Move early to a Rust clock/scheduler actor with bounded work per tick. |
| `SchedulerService` | Reads due jobs, marks them dispatched, then synchronously emits work events. | Define stable due-job ordering, retry/idempotency, and ownership before parallelizing. |
| `ConnectionManager` | In-memory maps are simple; room/global broadcasts await recipients sequentially. | A good early Rust migration target, but not sufficient alone. |
| `GameRng` | One application RNG gives deterministic single-thread behavior. | Parallel execution requires independent deterministic streams so thread scheduling cannot change outcomes. |
| `db.py` | Core table creation imports feature models; SQLite WAL is supported. | Move toward manifest-declared schemas/migrations and a Rust-owned transaction layer. |
| `ServiceContainer` | Feature services are still hand-listed and hold Python service objects. | Evolve manifests to declare commands, scripts, schema versions, event subscriptions, and capabilities. |

## Target architecture

### Runtime model

Use a Rust server process built around Tokio, but do not treat arbitrary Tokio
task concurrency as the simulation consistency model. Network tasks can be
fully concurrent; authoritative world mutations should be routed to actors that
own their state.

```text
WebSocket/HTTP ingress
        |
        v
Command admission and routing
        |
        v
World coordinator
        |
        +----> Zone actor A ----> Script VM/worker A
        +----> Zone actor B ----> Script VM/worker B
        +----> Global actor  ----> Global systems
                    |
                    v
          Rust transaction/effect validator
                    |
                    v
          Database + audit/outbox commit
                    |
                    v
           WebSocket delivery workers
```

Recommended ownership rules:

- A player command is routed to exactly one authoritative actor.
- An actor processes mutations sequentially in a stable order.
- Different actors may run concurrently on different cores.
- Cross-actor operations use messages and explicit protocols, never shared
  mutable entity references.
- Database state is mutated only through the Rust transaction runner.
- Network publishing happens from a committed outbox, not while holding world
  locks or a DB transaction.

This is actor-style concurrency: parallelism between independently owned
partitions and determinism within each partition.

### What should a shard be?

Do not begin by making every room an actor. That creates excessive message
traffic and makes movement, area broadcasts, quests, weather, and NPC routes
needlessly cross-actor.

Start with one of these coarse ownership units:

1. **One actor per world** — simplest and maximally deterministic. Network,
   parsing, serialization, read-only work, and persistence preparation can still
   use other cores. This may already support a substantial MUD population.
2. **One actor per region/zone** — preferred when measurements show one world
   actor is insufficient. Room-local interactions remain cheap; cross-zone
   movement is an explicit transfer.
3. **One actor per world instance** — ideal if Lorecraft later supports multiple
   worlds, shards, or instanced areas.

Start with one world actor and design messages so a zone split is possible.
Partitioning before load demands it would spend complexity without buying
players anything.

### Command lifecycle

A target command path should look like this:

1. The gateway authenticates the connection and assigns/validates a monotonically
   increasing client sequence.
2. Admission creates a `CommandEnvelope` with world, actor, player, session,
   command ID, receive sequence, and deadline.
3. The router sends it to the owning world/zone actor through a bounded queue.
4. The actor loads or references the authoritative state snapshot.
5. Rust parses the command and performs core validation.
6. If feature policy is scripted, the actor invokes the assigned script runtime
   with immutable input and a fixed budget.
7. The script returns messages and proposed effects.
8. Rust validates effects, applies them in a transaction, appends audit events and
   an outbound delivery record, and commits.
9. Only after a successful commit are messages published to connections.
10. Replay metadata records input order, script/content version, RNG identity,
    effects, and resulting state/event hashes.

The existing golden rule—never tell clients something happened until the DB says
it happened—survives intact.

## The scripting boundary

### Do not expose live engine objects

Avoid a PyO3 API shaped like this:

```python
def handle(ctx: RustGameContext):
    ctx.player.hp -= 4
    ctx.session.add(...)
    ctx.broadcast(...)
```

It looks ergonomic, but it creates difficult questions about lifetimes, locks,
transactions, interpreter affinity, deadlocks, partial mutation, rollback, and
objects retained beyond the callback. It also makes scripts capable of bypassing
the invariant checks that justify moving the core to Rust.

Prefer a value-oriented contract:

```text
ScriptRequest {
  api_version,
  script_id,
  script_version,
  command_or_event,
  actor_snapshot,
  room_snapshot,
  selected_related_entities,
  logical_time,
  rng_stream_id,
  capability_set,
  budget
}

ScriptResult {
  messages,
  proposed_effects,
  emitted_events,
  scheduled_work,
  diagnostics
}
```

Example effect variants:

- `MoveEntity`
- `TransferItem`
- `AdjustMeter`
- `SetFlag`
- `ApplyEffect`
- `EmitEvent`
- `ScheduleJob`
- `SendNarration`
- `RequestFollowupChoice`

Rust verifies that each effect is permitted, internally consistent, and valid
against current authoritative state. The same contract can be implemented by
Lua, Python workers, WebAssembly, native Rust features, and test doubles.

### Keep the boundary coarse

Repeated script-to-Rust calls such as `get_room()`, `get_player()`,
`find_item()`, and `set_flag()` turn the FFI or IPC boundary into a chatty remote
object system. Instead:

- send the relevant snapshot in one call;
- permit a small number of explicitly bounded queries only when the state cannot
  be predicted cheaply;
- return all proposed effects together;
- avoid `async` inside ordinary mechanics scripts;
- keep sockets, files, wall clock, environment variables, and database drivers
  outside the script capability set.

This improves performance, testability, hot reload, replay, and language
independence.

### Language choices

| Runtime | Strengths | Costs/risks | Recommended role |
| --- | --- | --- | --- |
| Embedded CPython via PyO3, one interpreter | Maximum compatibility with existing Python mechanics; convenient migration bridge. | GIL remains for Python code; two async/runtime models; weak fault isolation; unsafe for untrusted scripts. | Temporary compatibility layer or low-volume trusted scripting. |
| Multiple CPython subinterpreters | True parallel Python execution with isolation between interpreters. | Mutable objects cannot be shared; package compatibility varies; PyO3 subinterpreter support remains a moving target; lifecycle is complex. | Research spike only, not the foundational design. |
| Free-threaded CPython | Parallel Python threads and current PyO3 support. | Requires the free-threaded build; some extension modules can re-enable the GIL; code and dependencies must be audited for thread safety. | Optional future optimization after a clean value boundary exists. |
| Python worker processes | True parallelism, familiar Python, crash/restart containment, no subinterpreter constraints. | Serialization/IPC overhead and operational supervision. | Recommended way to retain substantial Python mechanics. |
| Embedded Lua/Luau (`mlua`) | Small, fast VMs; straightforward per-shard ownership; async hooks; memory limits; instruction/interrupt controls; good hot reload. | New language for contributors; sandbox and capability design still require care. | Recommended primary in-process mechanics runtime. |
| WebAssembly components | Strong isolation, deterministic interfaces, multiple source languages. | More tooling and host-interface complexity; less friendly for casual builders. | Future option for untrusted or distributable extensions. |

### Python parallelism: what is real in 2026

CPython 3.14 provides `concurrent.interpreters` and
`InterpreterPoolExecutor`; interpreters have separate GILs and can execute on
multiple cores. They are isolated, and mutable objects generally must be copied
or synchronized by message passing. Python also supports a free-threaded build,
but extension compatibility matters and an incompatible extension can cause the
GIL to be enabled again.

Those capabilities are useful, but they do not make Lorecraft's current shared
`AppState`, `GameContext`, SQLModel sessions, registries, and feature singletons
safe to distribute across interpreters. Converting that object graph into
messages is the real work. Once that work is done, worker processes are often
simpler and safer than embedded subinterpreters, while Lua/Luau is cheaper for
the hot path.

PyO3 remains excellent for:

- prototyping Rust domain types behind a Python test API;
- calling pure or coarse Rust computations from Python;
- building migration adapters;
- supporting free-threaded Python where every exposed Rust type is audited.

It should not dictate the final process architecture.

### Builder and player flexibility

Use a tiered extension model rather than giving all authors arbitrary server
code:

| Audience | Preferred extension surface |
| --- | --- |
| World builders | YAML/data schemas, templates, declarative conditions/effects, visual tools. |
| Trusted game developers | Lua/Luau mechanics and native Rust plugins; optionally Python workers. |
| Server administrators | Python tools and admin APIs outside the simulation hot path. |
| Players/untrusted creators | A narrow declarative DSL or capability-limited Lua/Luau/Wasm with strict quotas. |

Embedded Python is not a security sandbox. Lua/Luau is easier to restrict, but
still needs an allowlist of host functions, read-only libraries, memory limits,
instruction/time budgets, output limits, and cancellation. A script timeout
must fail its command without leaving partial state.

## Deterministic performance under load

Rust removes the GIL from the authoritative core, but determinism comes from
design choices rather than language choice.

### Ordering

Define stable ordering keys for every source of work:

- commands: `(world_id, shard_id, admission_sequence)`;
- scheduled jobs: `(due_logical_time, priority, stable_job_id)`;
- events: `(transaction_sequence, event_sequence, handler_priority,
  registration_key)`;
- outbound messages: `(commit_sequence, message_sequence)`.

Never allow hash-map iteration order, DB row order without `ORDER BY`, Tokio task
wake order, or interpreter completion order to determine game results.

### Randomness

The current single `GameRng` is deterministic only while calls occur in a stable
serial order. Parallel execution would make random outcomes depend on which task
reaches the RNG first.

Derive independent streams from stable identities, for example:

```text
stream_seed = H(world_seed, shard_id, transaction_id, subsystem, draw_domain)
```

Scripts should receive an opaque RNG capability or predeclared stream ID. Record
the stream identity and draw count in replay metadata. Do not expose wall-clock
time or system randomness to mechanics.

### Time

Separate:

- monotonic real time for deadlines and performance measurement;
- persisted wall time for operations/audit;
- logical game time for mechanics and scheduling.

Scripts should see logical game time only. A slow tick may delay wall-clock
delivery, but it must not change the relative order or number of logical events.

### Backpressure and budgets

Use bounded queues and explicit overload behavior:

- per-connection inbound command limit;
- per-player command rate and maximum outstanding commands;
- per-shard queue depth and deadline;
- maximum due jobs processed per tick, with lag metrics;
- script wall/instruction/memory/output budgets;
- bounded outbound queues with disconnect/coalesce policy for slow clients;
- bounded DB pool and transaction timeout.

Without these, Rust can accept work faster than the game can process it—which is
an efficient way to manufacture an outage.

### Persistence

SQLite WAL is a sensible current deployment choice, but SQLite still has one
writer. A threaded Rust engine does not change that.

Recommended progression:

1. Keep SQLite initially and use one explicit writer/transaction path. Measure
   whether it is actually limiting throughput.
2. Batch scheduler work and reduce unnecessary commits/queries before replacing
   the database.
3. Add PostgreSQL when parallel world/zone transactions or operational scaling
   justify it.
4. Use explicit Rust queries and transactions (`sqlx` is a good fit) rather than
   reproducing a large mutable ORM graph.

Each command should have an idempotency/command ID. State changes, audit rows,
and the delivery outbox should commit together when they share a database. If
game and audit data remain in separate databases, document the failure semantics
because there is no single atomic transaction across both SQLite files.

### Observability targets

Measure queueing separately from execution:

- ingress-to-admission delay;
- shard queue delay;
- parse, rule, script, DB, commit, and publish durations;
- scheduler lag and number of deferred due jobs;
- per-script timeout/error/memory counts;
- outbound queue depth and slow-client disconnects;
- p50/p95/p99 end-to-end command latency by command and feature;
- state/replay hash mismatches.

The existing `perf_baseline.py`, simulation load tests, audit regression, and
session replay should be extended rather than replaced.

## Suggested Rust workspace

Names are illustrative:

```text
rust/
  Cargo.toml
  crates/
    lorecraft-protocol/     # IDs, envelopes, script requests/results, WS schema
    lorecraft-core/         # entities, effects, validation, rules, transactions
    lorecraft-runtime/      # world/zone actors, routing, queues, lifecycle
    lorecraft-events/       # event types, stable dispatch, outbox
    lorecraft-scheduler/    # logical clock, due queue, retries, deterministic order
    lorecraft-store/        # sqlx repositories, migrations, transaction runner
    lorecraft-server/       # axum HTTP/WS, auth adapters, admin/core APIs
    lorecraft-script/       # common script host trait, budgets, versioning
    lorecraft-script-luau/  # mlua/Luau host
    lorecraft-python-worker/# IPC protocol/client and worker supervision
    lorecraft-replay/       # event/state hashing and replay runner
```

Likely foundational crates:

- Tokio for the async runtime;
- Axum for HTTP/WebSockets;
- Serde for stable value contracts;
- SQLx for explicit async persistence and migrations;
- `tracing` for structured spans;
- `mlua` with Luau for embedded scripting;
- a deterministic RNG such as ChaCha with explicit seed/stream derivation;
- a schema format that supports compatibility checks for protocol and script API
  versions.

Do not make every crate a service. A single deployable Rust server with internal
crate boundaries is simpler until independent scaling is demonstrably useful.

## Migration plan

### Phase 0 — freeze semantics and gather evidence

Before migrating code:

- record current p50/p95/p99 latency at increasing concurrent-player counts;
- record scheduler performance for increasing due-job counts;
- add a slow-handler test proving current event-loop blocking behavior;
- turn replay scenarios into required semantic fixtures;
- define canonical state and event normalization/hashing;
- document transaction, audit, disconnect, and delivery guarantees;
- identify which feature handlers perform direct SQL/ORM mutation.

Exit criterion: the team can say whether two implementations behaved the same,
not merely whether both test suites are green.

### Phase 1 — define language-neutral contracts

Create versioned schemas for:

- `CommandEnvelope` and `CommandOutcome`;
- entity/world snapshots used by scripts;
- effect variants;
- events and scheduled jobs;
- outbound player/admin messages;
- error, timeout, retry, and idempotency behavior.

Implement the contract in Python first and adapt `GameContext` handlers to it
for one small feature. This exposes missing capabilities before Rust is blamed
for them.

Exit criterion: one Python feature can run without direct access to a SQLModel
session, WebSocket manager, or mutable model.

### Phase 2 — build the Rust skeleton and shadow runner

Build:

- protocol types;
- deterministic logical clock/scheduler ordering;
- RNG stream derivation;
- effect validation;
- replay/state hashing;
- basic world actor and bounded queues.

Run Rust in shadow mode against recorded scenarios. It should not mutate the
production DB yet.

Exit criterion: Rust reproduces selected clock, scheduler, RNG, and pure-rule
fixtures exactly.

### Phase 3 — migrate transport and connection ownership

Move HTTP/WebSocket ingress, connection maps, room/global fan-out, connection
backpressure, and authentication handoff into Rust. Forward commands to the
existing Python command processor through the versioned protocol.

This phase improves transport isolation and proves the protocol, but it is not
the performance finish line.

Exit criterion: existing player and admin clients run through the Rust gateway;
disconnect/reconnect and slow-client tests match current semantics.

### Phase 4 — migrate one vertical gameplay slice

Choose a narrow but real slice, such as `look`, then movement:

- Rust parsing/routing for the selected verb;
- Rust repository reads/writes;
- Rust transaction and effect validation;
- Rust audit/outbox commit;
- existing UI response shape;
- golden replay comparison.

Route only migrated commands to Rust and all others to Python. Do not allow both
implementations to mutate the same command.

Exit criterion: the vertical slice is behavior-compatible and measurably bounded
under load.

### Phase 5 — move Tier 1 authority

Migrate, in roughly this order:

1. transaction IDs, ordering, and outbox;
2. world clock and scheduler;
3. event types and dispatch;
4. RNG streams;
5. core models/effects/holders/meters;
6. repositories and DB ownership;
7. parser/registry/command lifecycle;
8. audit and replay.

Once Rust owns DB writes, Python features must use the script/effect protocol;
they may not retain an alternate write path.

Exit criterion: no authoritative Tier 1 mutation occurs in Python.

### Phase 6 — introduce production scripting

Add Lua/Luau first, with:

- manifest and API versions;
- module loading and dependency declarations;
- capability allowlists;
- memory/instruction/time/output budgets;
- deterministic inputs and RNG;
- hot reload that pins each in-flight transaction to one script version;
- structured errors and circuit breaking.

Add Python worker compatibility only for features that gain enough from Python
to justify the extra runtime.

Exit criterion: at least one nontrivial feature is script-defined, reloadable,
budgeted, replayable, and unable to bypass Rust validation.

### Phase 7 — port features by value, not file count

Port the highest-load or most central features first. Keep low-volume admin and
content tooling in Python indefinitely if desired. A successful Rust migration
does not require deleting Python.

Candidate order:

1. movement/inventory and shared item-location effects;
2. scheduler-heavy systems, meters, effects, transit, NPC routes;
3. quests and event-driven features;
4. economy/trading/ledger features;
5. remaining commands and presentation adapters;
6. admin APIs only where Rust ownership materially simplifies them.

Exit criterion: the Python server is no longer required for normal player
runtime, though Python tooling/workers may remain supported.

## Compatibility and rollout rules

- Never dual-write gameplay state from Rust and Python.
- Shadow execution may compare decisions, but only one side commits.
- Every migrated command needs golden replay, integration, concurrency, and
  failure-injection coverage.
- Preserve current WebSocket payloads until the frontend migration is a separate
  deliberate project.
- Pin protocol, script API, content, and engine versions in audit/replay data.
- Make rollback a routing/configuration decision while the old path still
  exists.
- Test DB failures after state preparation but before commit, and delivery
  failures after commit.
- Use deterministic fake time and seeded streams in unit tests; use real clock
  only in boundary tests.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Rewrite stalls while Python continues changing | Strangler slices; keep schemas and replay fixtures as the shared contract. |
| FFI becomes a second object model | Value snapshots and effect batches; no live ORM/session/socket objects. |
| Parallel execution changes outcomes | Actor ownership, stable ordering keys, per-transaction RNG streams, state hashing. |
| SQLite remains the bottleneck | Measure first; one writer path; batching; PostgreSQL only when justified. |
| Scripts block actors | Hard budgets, worker supervision, bounded queues, circuit breakers, no ordinary script I/O. |
| Player-authored scripts compromise the server | Do not embed unrestricted Python; use narrow capabilities and Lua/Luau or Wasm isolation with quotas. |
| Cross-zone mechanics become difficult | Start with one world actor; split only at coarse, explicit boundaries. |
| Hot reload breaks replay | Version scripts/content and pin each transaction to the loaded version. |
| Rust core becomes opinionated and harms builders | Keep mechanics in effects/scripts; keep Rust focused on invariants and execution. |
| Too many services/processes | One Rust deployable with internal crates; add Python workers only when needed. |

## Recommended first implementation experiment

Before committing to the full migration, build a thin proof of architecture:

1. Define `CommandEnvelope`, `ScriptRequest`, `ScriptResult`, and a small effect
   enum in Rust and Python.
2. Adapt one read-only command and one mutating command to the effect model in
   Python.
3. Build a Rust world actor with bounded input, deterministic ordering, logical
   clock, RNG stream derivation, and an in-memory state model for those commands.
4. Execute the same replay scenarios through Python and Rust and compare
   normalized outcomes/state hashes.
5. Implement the same small mechanic once in Lua/Luau and once in a Python worker.
6. Load test the gateway, script boundary, actor queue, and SQLite transaction
   path independently.

This experiment answers the important questions cheaply:

- Is the effect API pleasant enough for mechanics authors?
- Does a coarse actor preserve the gameplay model?
- Is SQLite already sufficient?
- Is Lua/Luau acceptable to builders?
- Which Python mechanics truly need to survive as Python?
- Where does latency actually accumulate?

## Phase 0/1 kickoff — design spec (2026-07-12)

This section is the concrete kickoff design for Phase 0 (evidence gate) and Phase 1
(language-neutral contracts), handed off from Research to Backend Engineering. It
grounds the "Recommended first implementation experiment" above in specific files,
types, and tasks. Two Backend Engineers implement Part A and Part B in parallel, each
in their own scratch worktree branched from `rust-port`.

### Part A — Phase 0 evidence gate (Python side)

**A1. Canonical state/event hashing.** New module `src/lorecraft/tools/replay_hash.py`
(kept separate from `session_replay.py` to stay dependency-light):

- `canonical_json(obj: JsonValue) -> bytes`: implemented as
  `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")`.
  Float policy: **reject floats** (raise `TypeError`) — forces pre-quantized int/str
  values and pre-empts a future Rust-serde float-formatting parity divergence.
- `hash_events(events: Iterable[AuditEvent]) -> str`: `sha256(canonical_json(normalize_events(events))).hexdigest()`
  — a thin composition over the existing `session_replay.normalize_events`.
- In scope now: event-trail hashing only (proves Python==Python replay determinism as
  a single digest instead of a list `==` comparison).
- Deferred to Phase 2: state-snapshot hashing — no state-snapshot shape exists yet;
  once the Phase 1 `EntitySnapshot` contract lands, `replay_hash.py` gains
  `hash_state(snapshot)` reusing the same `canonical_json` serializer.

**A2. Promote replay scenarios to required fixtures.** Two parts:

(a) Add `tests/simulation/scenarios/look_only.json` (a single `look` command in a
fixed room, `rng_seed: 1`) plus its golden `look_only.audit.json` — a tight
read-only parity fixture for the `look` slice specifically (the existing
`golden_path.json`/`load_default.json` fixtures are mutation-heavy, not a clean
read-only target). Refactor `tests/simulation/test_audit_regression.py` to iterate a
scenario list rather than hardcoding `golden_path`. Do not add combat/economy/trading
scenarios now — scenario coverage should track migrated verbs only.

(b) Document policy (this doc section itself is that documentation): any rust-port
change touching the protocol/effect contract or a migrated verb must run
`make test-simulation` green, confirmed by the reviewer — since the `simulation`
pytest marker is excluded from default `make test` and cannot self-enforce.

**A3. Slow-handler event-loop-blocking test.** New
`tests/simulation/test_event_loop_blocking.py` (`pytest.mark.simulation`, needs a
live async server). Inject a synchronous `time.sleep(SLOW)` (not `asyncio.sleep` — it
must actually block the loop) into one command handler via monkeypatch or a
dedicated test-only slow verb. Run two concurrent connections: A issues the slow
command at t0, B issues a fast command (e.g. `who`) shortly after. Assert B's
round-trip latency is delayed by ~`SLOW` (head-of-line blocking) and/or that a world-
clock heartbeat tick is delayed similarly. This is a characterization test of
**current (undesirable) behavior** — the migration is expected to invert this
assertion once command execution moves off the ingress task.

**A4. SQL/ORM direct-mutation inventory.** Definition of a violation: (1)
`.add`/`.delete`/`.commit`/`.flush`/`.exec(<mutating stmt>)` called on a
SQLModel/SQLAlchemy `Session` obtained via `ctx.session` or constructed directly,
from `features/**` or composition layers; or (2) an attribute assignment on a
persisted engine model that bypasses an `engine/repos/*` method. Reads are excluded.
New tool: `src/lorecraft/tools/mutation_scan.py` (AST-based), walks `features/` +
composition layers, flags both patterns, and emits a JSON/markdown checklist keyed
by `file:line` — this becomes the Phase 4/5 conversion backlog.

### Part B — Phase 1 contracts (`lorecraft-protocol` crate + Python mirror)

Current crate state: `rust/crates/lorecraft-protocol/src/lib.rs` has only
`PROTOCOL_VERSION: u32 = 1` and `ProtocolError`. Everything below is additive — no
breaking change to what exists.

**ID newtypes (Tier 1/mechanism):** `WorldId`, `ActorId`, `PlayerId`, `SessionId`,
`CommandId` — `struct XId(String)` with `#[serde(transparent)]`. Python mirror: plain
`str` type aliases (keeps JSON identical, no wrapping).

**`CommandEnvelope` (Tier 1):**

```rust
CommandEnvelope {
  protocol_version: u32,
  world_id: WorldId,
  actor_id: ActorId,
  player_id: PlayerId,
  session_id: SessionId,
  command_id: CommandId,     // idempotency key
  receive_sequence: u64,     // monotonic admission/client sequence
  deadline_ms: u64,          // monotonic execution budget
  raw: String,               // raw command line
}
```

**`CommandOutcome` (Tier 1):**

```rust
CommandOutcome {
  command_id: CommandId,
  status: OutcomeStatus,          // enum { Executed, Blocked, Failed, TimedOut }
  commit_sequence: Option<u64>,
  messages: Vec<OutboundMessage>,
  applied_effects: Vec<Effect>,
  diagnostics: Vec<Diagnostic>,
}
```

**`ScriptRequest` / `ScriptResult` (Tier 1**, reusing the field lists already defined
in "The scripting boundary" above):

```rust
ScriptRequest {
  api_version: u32,
  script_id: String,
  script_version: u32,
  command_or_event: String,
  actor_snapshot: EntitySnapshot,
  room_snapshot: EntitySnapshot,
  selected_related_entities: Vec<EntitySnapshot>,
  logical_time: u64,
  rng_stream_id: String,
  capability_set: Vec<String>,
  budget: ScriptBudget,   // { wall_ms, instructions, memory_bytes, output_bytes }
}

ScriptResult {
  messages: Vec<OutboundMessage>,
  proposed_effects: Vec<Effect>,
  emitted_events: Vec<EmittedEvent>,
  scheduled_work: Vec<ScheduledWork>,
  diagnostics: Vec<Diagnostic>,
}
```

**`EntitySnapshot` (Tier 1 — the anti-leak decision):**

```rust
EntitySnapshot {
  id: String,
  kind: String,                                     // "room" | "player" | "item" | ...
  attributes: BTreeMap<String, serde_json::Value>,   // OPAQUE — no feature keys typed here
}
```

The mechanism knows an entity has id/kind/attributes; it does not know a room has
exits or a player has HP — those are Tier 2 policy filled by the feature. Do **not**
add a typed `exits: Vec<Exit>` field to the crate — that is the leak signal to reject
in review.

**Effect enum (Tier 1**, minimal set for this kickoff — more variants added as later
slices need them):

```rust
enum Effect {
  MoveEntity   { entity: String, from: String, to: String },
  TransferItem { item: String, from: String, to: String, quantity: u32 },
  AdjustMeter  { entity: String, meter: String, delta: i64 },
  SetFlag      { entity: String, key: String, value: serde_json::Value },
  EmitEvent    { event_type: String, payload: serde_json::Value },
  SendNarration{ text: String, message_type: String },
}
```

**`OutboundMessage` (Tier 1):**

```rust
enum OutboundMessage {
  Feed        { text: String, message_type: String },   // maps to ctx.say / WsFeedAppend
  PanelUpdate { key: String, value: serde_json::Value }, // maps to ctx.push_update / WsStateChange
}
```

**`look` produces zero effects** — the crisp read-only proof of the Phase 1 exit
criterion: each `ctx.say(...)` line maps to `OutboundMessage::Feed`; the
`push_update("room_id", ...)` maps to `OutboundMessage::PanelUpdate` (a client panel
refresh, not an authoritative state change, so **not** an `Effect`);
`proposed_effects = []`, `emitted_events = []`, `scheduled_work = []`.

Flagged judgment call: the plan lists `SendNarration` as an effect variant, but
narration for command handlers flows through `ScriptResult.messages` /
`OutboundMessage::Feed` instead (matching existing `ctx.say`) — `SendNarration`
stays in the enum for scripts/events that need narration ordered relative to state
effects, but `look` uses `messages`, not this effect variant.

**Python mirror — representation choice:** frozen dataclasses
(`@dataclass(frozen=True, slots=True)`), **not** pydantic/msgspec/TypedDict — no new
dependency, matches the existing `session_replay.py` convention, immutability matches
"immutable snapshot," and `dataclasses.asdict(...)` feeding the new `canonical_json(...)`
gives byte-level JSON parity control against Rust serde output. New Python package
`src/lorecraft/protocol/` (top-level, sibling to `src/lorecraft/types.py`, so
engine+features+parity harness can all import without a feature/web dependency) with
`version.py`, `envelope.py`, `script.py`, `effects.py`, `snapshot.py`, `messages.py`.
`EntitySnapshot.attributes` mirrors as `dict[str, JsonValue]` reusing
`lorecraft.types.JsonValue`.

**Versioning.** `PROTOCOL_VERSION` stays `1` for this kickoff. Bump policy: bump on
any breaking change to envelope/effect/script/snapshot shapes; additive optional
fields don't bump (Rust `#[serde(default)]` + Python `field(default=...)`). Python
mirror declares `PROTOCOL_VERSION: int = 1` in `src/lorecraft/protocol/version.py`.
Cross-language parity check: a Rust test in `lorecraft-protocol` writes the constant
to a checked-in `rust/crates/lorecraft-protocol/schema/version.json`; a Python
drift-test `tests/unit/test_protocol_version_parity.py` reads it and asserts equality
(same shape as the existing `make ai-graph`/`make scripting-docs` drift checks).

**`look` adapter structure** (Phase 1 exit criterion — **not** a live cutover, must
be byte-identical to current behavior):

- New pure function (Tier 2/policy): `src/lorecraft/features/inventory/look_pure.py`
  → `def look_effects(request: ScriptRequest) -> ScriptResult`. Reads only from
  `request.room_snapshot.attributes` (keys like `"name"`, `"description"`,
  `"terrain"`, `"exits"`) and `request.selected_related_entities` (room items).
  Returns messages (Feed lines in the same order as today's `ctx.say` calls, plus the
  `PanelUpdate("room_id", ...)`) and `proposed_effects=[]`. No `GameContext`, no
  session, no repo access inside this function.
- `InventoryService.look(ctx)` becomes a thin shim: (1) build the `ScriptRequest`
  snapshot from `ctx` using the same reads it does today (`ctx.room`,
  `ctx.room_repo.exits`, `ctx.item_repo.items_in_room`, terrain registry) — reads
  only; (2) call `look_effects`; (3) apply the result the old way — each `Feed` →
  `ctx.say(text, message_type)`, each `PanelUpdate` → `ctx.push_update(key, value)`,
  in the same order.
- Hard requirement: existing `look` unit tests and the golden-path/`look_only` audit
  goldens must show zero diff — this is a refactor, not a behavior change.

**Tier classification** (explicit, per AGENTS.md "Tier 1 = mechanism, Tier 2 =
policy"):

- Tier 1/mechanism: the `lorecraft-protocol` crate + `src/lorecraft/protocol/`
  mirror — `CommandEnvelope`, `CommandOutcome`, `ScriptRequest`, `ScriptResult`,
  `Effect`, `EntitySnapshot`, `OutboundMessage`, ID newtypes, `PROTOCOL_VERSION`. No
  feature-specific fields; `EntitySnapshot.attributes` is opaque precisely so no
  feature's opinion lands in the type.
- Tier 2/policy: `features/inventory/look_pure.py` — `look_effects` and which
  attribute/message keys it reads/emits are `look`'s opinion and live in the
  feature, never the protocol type.

**Tunables note** (per AGENTS.md "Prefer live-tunable configuration"): this kickoff
introduces no game-balance dials. The only dials are operational (`deadline_ms`,
`ScriptBudget` fields) — static config for this kickoff, but flagged as strong
live-tunable candidates once the actor + script host land in Phase 2+ (mirror the
`WorldClock` DB-backed-singleton + admin-endpoint pattern rather than YAML+reseed).
`PROTOCOL_VERSION` is a static code constant, never live-tunable.

### Proposed tasks

**Phase 0:**

- [x] `src/lorecraft/tools/replay_hash.py`: `canonical_json` (float-reject) + `hash_events` over existing `normalize_events` — Tier 1 — deterministic sha256 for a trail; state-hash deferred to Phase 2 — tunable: static.
- [x] `tests/simulation/scenarios/look_only.json` + golden; refactor `test_audit_regression.py` to iterate scenarios — Tier 2 (test content) — read-only parity fixture for the `look` slice — tunable: static content.
- [x] Document `make test-simulation` as a mandatory rust-port review gate — N/A (policy doc) — reviewers confirm it green on contract/verb changes — tunable: n/a.
- [x] `tests/simulation/test_event_loop_blocking.py`: sync-sleep handler injection; assert concurrent command delayed ~SLOW — N/A (characterization test) — proves current head-of-line blocking — tunable: n/a.
- [x] `src/lorecraft/tools/mutation_scan.py`: AST inventory of direct SQL/ORM mutation → checklist — N/A (Phase 0 tooling) — enumerates the Phase 4/5 conversion backlog — tunable: n/a.

**Phase 1:**

- [x] `lorecraft-protocol` crate: add CommandEnvelope, CommandOutcome, ScriptRequest, ScriptResult, Effect (6 variants), EntitySnapshot (opaque attrs), OutboundMessage, ID newtypes — Tier 1 — serde JSON round-trips; no feature fields — tunable: PROTOCOL_VERSION static / budgets static-now-live-later.
- [x] `src/lorecraft/protocol/` package: frozen-dataclass mirror of the above; `version.py`; parity drift-test vs Rust `schema/version.json` — Tier 1 — Python<->Rust JSON parity — tunable: static.
- [x] `src/lorecraft/features/inventory/look_pure.py`: `look_effects(ScriptRequest) -> ScriptResult`; make `InventoryService.look` a thin snapshot-building shim — Tier 2 — byte-identical player output (goldens unchanged); no session in the pure fn — tunable: static.

### Kickoff status (2026-07-12)

Both tracks are implemented, reviewed, and tested green:

- **Part A** (Phase 0 evidence gate) landed on branch `rustport-phase0-python-evidence`
  (commit `2300847`). **Part B** (Phase 1 contracts) landed on branch
  `rustport-phase1-protocol-contracts` (commit `51ed270`).
- Both branches passed Code Review with no blocking findings, and passed Test & QA:
  Rust side — `cargo build`, `cargo test`, and `cargo clippy` all clean, 11 new
  protocol tests; Python side — `make lint`, `make typecheck`, and `make test` all
  clean, full suite 1420-1425 tests passed depending on branch, coverage 88.93% on
  Track A, well above the 80% gate.
- `mutation_scan.py`, run against the real `features/` tree, found 87 findings across
  32 files (85 session-mutation, 2 model-attribute-write) — this is the expected
  Phase 4/5 conversion backlog the tool exists to produce, not a defect to fix now.
- `test_event_loop_blocking.py` ran green and stable across repeated runs, confirming
  current synchronous command handlers do block the event loop — the expected,
  documented characterization of current behavior, not a regression.

**Two non-blocking follow-ups flagged by Code Review** — recommended for the next
increment before they're forgotten:

1. `tests/simulation/conftest.py`'s `audit_trail_for` sorts by `real_time` only (no
   `id` tiebreaker) — a latent replay-determinism gap, since `real_time` isn't
   guaranteed unique. `session_replay.py`'s `record_scenario` already does this
   correctly with a `(real_time, id)` tiebreaker. Should be aligned before Phase 0's
   hashing work (`replay_hash.py`) is leaned on more heavily.
2. The Python protocol mirror's container types (`CommandOutcome`, `ScriptRequest`,
   `ScriptResult`, `CommandEnvelope`) don't yet have their own `to_json`/`from_json` —
   `dataclasses.asdict()` would silently drop the `Effect`/`OutboundMessage` tag and
   the `from`/`from_` wire-key rename if a container holding one were serialized that
   way. Not a bug yet (nothing serializes a container across the boundary in this
   kickoff), but must be fixed with a proper recursive `to_json` before Phase 2
   actually sends a `ScriptResult`/`CommandOutcome` over the wire.

Also flagged: the unused `tokio` (full feature set), `uuid`, and `thiserror`
dependencies in `lorecraft-protocol`'s `Cargo.toml` — should be trimmed or put to use
in a follow-up cleanup pass.

**Recommended next increment:** Phase 2's Rust world-actor skeleton (bounded input
queue, deterministic ordering, RNG stream derivation) running `look` in shadow mode
against the new `look_only` replay fixture, comparing Rust output to the Python golden
via the new `replay_hash.py` hashing utility — the natural next slice per the plan's
"Recommended first implementation experiment" steps 3-4 above.

### Where things stand / Next

These tasks are the active kickoff work queue for the two Backend Engineers about to
implement Part A and Part B in parallel, each in their own scratch worktree branched
from `rust-port`. Part A (Phase 0 evidence gate) and Part B (Phase 1 contracts) have
no file overlap and can proceed concurrently. Once both land, the Phase 1 exit
criterion (`look` running through the protocol contract with zero effects and
byte-identical output) closes out this kickoff and Phase 2 (Rust skeleton + shadow
runner) can begin.

## Phase 2 kickoff — design spec (2026-07-12)

### Summary / scope

This section is the concrete kickoff design for Phase 2 (build the Rust world-actor
skeleton and run `look` in shadow mode), handed off from Research to Backend
Engineering. It is the "Recommended next increment" named at the end of the Phase 0/1
kickoff status above: build the Rust world-actor skeleton (bounded input queue,
deterministic ordering, RNG stream derivation) and run `look` in shadow mode against
the `look_only` replay fixture, comparing Rust output to a Python golden via
`replay_hash.py`'s canonical hashing.

### Confirmed design decisions (from Research-Planner analysis)

1. **Hash target is the `ScriptResult`, not the existing audit-event golden.**
   `tests/simulation/scenarios/look_only.audit.json` is a DB audit-event projection
   from the full command pipeline (parser/dispatch/audit-writer/commit) — reproducing
   it needs Phase 4 (Rust owns the pipeline), not Phase 2. The Phase 1 contract
   boundary that exists today is `look_effects(ScriptRequest) -> ScriptResult`
   (`src/lorecraft/features/inventory/look_pure.py`) — that pure-rule output is what
   Phase 2 hashes and compares. **The audit golden is preserved as the Phase 4
   target**, not deprecated or superseded by this slice.
2. **Crate placement:**
   - `lorecraft-replay` — canonical-JSON + sha256 hashing, ported from
     `replay_hash.py`'s `canonical_json`/`hash_events` (sorted keys via
     `serde_json::Value`'s BTreeMap-backed Map — **not** derived-struct
     serialization, which preserves field-declaration order and would silently
     diverge from Python's `sort_keys=True`; no whitespace; UTF-8; reject floats to
     mirror Python's float-reject).
   - `lorecraft-scheduler` — logical clock + deterministic ordering-key comparator:
     `(logical_time, receive_sequence)`.
   - `lorecraft-core` — RNG stream derivation: `derive_stream(world_seed, stream_id)
     -> ChaCha8Rng`, seeded via SHA-256 of the stream identity (adds
     `rand`/`rand_chacha` deps).
   - `lorecraft-runtime` — the world-actor skeleton itself: bounded input queue
     (`std::sync::mpsc::sync_channel`, no new deps), drain-then-sort-by-ordering-key-
     then-dispatch loop (determinism must not depend on channel arrival
     order/FIFO). Unopinionated — invokes an injected policy fn, holds no feature
     opinion.
   - **New crate `lorecraft-feature-look`** — the Rust port of `look_pure.py`'s
     policy (message ordering/formatting opinion). Explicitly **not** placed in
     `runtime`/`core`/`scheduler` `src/` — that would be a Tier 1/Tier 2 policy leak
     (AGENTS.md "Tier 1 = mechanism, Tier 2 = policy"), the same class of finding a
     reviewer would reject. Fallback if a new crate is rejected later: a
     `lorecraft-replay/tests/` fixture, but the new-crate approach is recommended and
     what's being built.
3. **RNG cross-language parity is explicitly deferred, not attempted.** Python's
   `GameRng` (`src/lorecraft/engine/game/rng.py`) is `random.Random` (Mersenne
   Twister); Rust's target is `ChaCha8Rng`. A byte-level draw comparison across
   languages isn't achievable without an RNG-algorithm decision that belongs to Phase
   5 ("RNG streams" under Tier 1 authority migration). Phase 2 proves **Rust-internal**
   RNG determinism only: same `(world_seed, stream_id)` twice → identical draws;
   different `stream_id` → independent streams; interleaved/out-of-order dispatch
   doesn't perturb a stream's own draw sequence.
4. **Fixture capture reuses the existing shim, never hand-authored** (avoids
   fixture/production drift): a Python golden test boots a fresh
   `world_content/world.yaml` world (`rng_seed=1`), creates `player-1`, derives the
   starting room from world config (not a hardcoded string in capture logic — the
   room id only appears in the *generated* fixture data), calls
   `InventoryService._build_look_request` for the resulting `ScriptRequest`, and
   writes two checked-in artifacts so they can't drift apart:
   `rust/fixtures/look_only/request.json` (the `ScriptRequest.to_json()`, Rust's
   input) and `rust/fixtures/look_only/expected_result_hash.txt`
   (`sha256(canonical_json(look_effects(request).to_json()))`). Regeneration gated by
   `LORECRAFT_UPDATE_RUST_FIXTURES=1`, mirroring `LORECRAFT_UPDATE_GOLDENS`.
5. **Recursive `to_json`/`from_json` on protocol container types is a hard
   prerequisite, not just Phase 1 cleanup.** Confirmed still missing on
   `ScriptResult`, `ScriptRequest`, `EntitySnapshot`, `ScriptBudget`, `EmittedEvent`,
   `ScheduledWork`, `CommandEnvelope`, `CommandOutcome`, `Diagnostic` (present already
   on `Effect`/`OutboundMessage`). `dataclasses.asdict()` would silently drop the
   `{"type": ...}` tag on nested effect/message variants and the `from`/`from_`
   wire-key rename. Must land before anything is hashed — blocks the fixture-capture
   task.
6. **Scope guardrails:** this slice is fixture-driven and read-only — no Rust
   DB/store/events wiring (`lorecraft-store`/`-events`/`-server` stay stubs this
   phase); the Python capture script must boot a disposable/temp world and must not
   mutate any production/committed DB, matching the plan's "Rust runs in shadow
   mode... should not mutate the production DB yet." The 87-finding mutation-scan
   backlog remains out of scope (Phase 4/5).
7. **No game-balance tunables in this slice** — pure protocol/determinism plumbing.
   Queue capacity and `deadline_ms`/`ScriptBudget` fields are the only tunables
   (operational, not gameplay), stay static-now for the skeleton, flagged as
   live-tunable candidates once the actor/script host mature (Phase 3+), consistent
   with the AGENTS.md live-tunable-config preference.

### Proposed tasks (Phase 2)

These map to two Backend Engineers implementing in parallel scratch worktrees off
`rust-port`, no file overlap — Python task 1 is the only ordering dependency, since it
unblocks the fixture the Rust side consumes.

**Backend Engineer (Python)** — `src/lorecraft/protocol/`, `tests/simulation/`,
`rust/fixtures/`:

- [x] Recursive `to_json`/`from_json` on the protocol container types listed in point
  5 above — Tier 1 — round-tripped `ScriptResult` keeps nested `{"type":...}` tags;
  parity test vs Rust JSON shape — tunable: static. (blocks all downstream Phase 2
  work)
- [x] Fixture-capture + Python golden test
  (`tests/simulation/test_look_scriptresult_parity.py`) per point 4 above — Tier 2
  (test content/fixture) — regenerable, deterministic, no production-DB mutation —
  tunable: static content.
- [x] Doc note that `look_only.audit.json` remains the Phase 4 pipeline-owned target,
  distinct from this ScriptResult hash — N/A (doc) — tunable: n/a.

**Backend Engineer (Rust)** — `rust/crates/` (+ new `lorecraft-feature-look`):

- [x] `lorecraft-replay`: `canonical_json` + `hash_bytes` port — Tier 1 — unit test:
  known ScriptResult JSON hashes to a fixed hex; float input errors — tunable:
  static.
- [x] `lorecraft-scheduler`: logical clock + `(logical_time, receive_sequence)`
  ordering comparator — Tier 1 — test: out-of-order enqueue dispatches in
  sorted-key order — tunable: static.
- [x] `lorecraft-core`: `derive_stream(world_seed, stream_id) -> ChaCha8Rng` — Tier 1
  — tests: repeatability, stream independence, interleave/order-independence —
  tunable: static.
- [x] `lorecraft-runtime`: world-actor skeleton, bounded `sync_channel` queue,
  drain→sort→dispatch — Tier 1 — test: queue accepts up to capacity; dispatch order
  == ordering-key order — tunable: queue capacity/deadline_ms operational,
  static-now/live-later.
- [x] `lorecraft-feature-look` (new crate): Rust `look` policy fn + shadow-run parity
  test reading `rust/fixtures/look_only/request.json`, hashing its output, asserting
  equality with `expected_result_hash.txt` — Tier 2 — Rust hash matches Python's
  byte-for-byte — tunable: static.
- [x] Cleanup: trim unused `tokio`(full)/`uuid`/`thiserror` from
  `lorecraft-protocol/Cargo.toml` (flagged in the Phase 0/1 kickoff status) — N/A
  (hygiene) — tunable: n/a.

### OPEN ITEMS resolved

1. Rust `look` policy crate placement — resolved: new `lorecraft-feature-look` crate
   (not `lorecraft-replay/tests/` fallback), to avoid a Tier 1/Tier 2 policy leak.
2. Cross-language RNG parity — resolved: deferred to Phase 5; Phase 2 proves
   Rust-internal RNG determinism only.

### Kickoff status (2026-07-12)

Both tracks are implemented, reviewed, and tested green:

- **Python prerequisite** (recursive `to_json`/`from_json` + fixture capture) landed
  on branch `rustport-phase2-protocol-tojson`: recursive `to_json`/`from_json` on the
  protocol container types, the fixture-capture golden test, and the checked-in
  `rust/fixtures/look_only/{request.json,expected_result_hash.txt}` artifacts, plus a
  follow-up commit pinning the integer-valued-float (`2.0`) edge case in
  `canonical_json`'s float-reject logic.
- **Rust world-actor skeleton** landed on branch `rustport-phase2-actor-skeleton`:
  `lorecraft-replay` (canonical JSON + sha256 hashing), `lorecraft-scheduler`
  (ordering key + logical clock), `lorecraft-core` (`derive_stream` RNG derivation),
  `lorecraft-runtime` (bounded-queue world-actor skeleton), the new
  `lorecraft-feature-look` crate (Rust port of `look_pure.py` + the cross-language
  parity test), and the `lorecraft-protocol` `Cargo.toml` cleanup (removed unused
  `tokio`-full/`uuid`, put `thiserror` to genuine use), plus a follow-up commit
  adding the mirroring `2.0` float-reject test and moving `lorecraft-replay` to
  `[dev-dependencies]` in `lorecraft-feature-look`.
- **The Phase 2 exit criterion is proven and independently verified twice:** the
  Rust `look_only_fixture_parity` test computes a canonical-JSON sha256 hash of its
  `look_effects` output and asserts it equals the Python-captured golden — both
  sides produce `ff78f14d4adff1daf3fa1c6a4ce3aa4a537f4384ff29011dca14460c7b2c95ca`.
- Code Review found zero blocking issues on either branch (only minor advisories,
  since closed by the two follow-up commits above).
- Full verification once all three branches (this design spec plus the two above)
  are combined: Python `make lint`/`make typecheck`/`make test` (1448 tests) all
  clean; Rust `cargo build`/`cargo test --all` (39 tests across 6 crates: core 5,
  feature-look 5, protocol 11, replay 8, runtime 4, scheduler 6)/
  `cargo clippy --all-targets -- -D warnings`/`cargo fmt --all -- --check` all
  clean.

### Where things stand / Next

Phase 0, Phase 1, and Phase 2 are landed (see the Phase 0/1 kickoff status and the
Phase 2 kickoff status above). Rust reproduces the `look_only` `ScriptResult` hash
exactly, in shadow mode, with no DB mutation — Phase 2's exit criterion is met.

**Phase 3 (migrate transport and connection ownership)** is the recommended next
increment, per the "Migration plan" section above: move HTTP/WebSocket ingress,
connection maps, room/global fan-out, connection backpressure, and authentication
handoff into Rust, forwarding commands to the existing Python command processor
through the versioned protocol. This phase improves transport isolation and proves
the protocol, but it is not the performance finish line; its exit criterion is that
existing player and admin clients run through the Rust gateway, with
disconnect/reconnect and slow-client tests matching current semantics.

## Final position

Lorecraft should not migrate to Rust merely because Rust is faster or Python has
a GIL. A text game can support a great many players in Python, and the existing
server may first hit SQLite transaction shape, synchronous event-loop blocking,
sequential fan-out, or feature query patterns.

The stronger case for Rust is architectural:

- an authoritative, memory-safe core with explicit ownership;
- predictable queues, deadlines, and overload behavior;
- deterministic actor-local ordering with multi-core scaling between actors;
- durable transactions and an outbox before publication;
- a safe, versioned boundary for multiple scripting languages;
- freedom to retain Python where it is productive without letting it define the
  server's concurrency ceiling.

Therefore:

1. **Adopt Rust as the target authoritative runtime.**
2. **Use a coarse actor model, beginning with one actor per world.**
3. **Use Lua/Luau as the preferred embedded mechanics language.**
4. **Retain Python for tools and optional process-isolated trusted scripts.**
5. **Do not make multiple PyO3 subinterpreters a prerequisite.**
6. **Migrate by vertical slices and prove semantic equivalence with replay.**

This path serves the north star: builders get flexible, reloadable mechanics;
players get reliable behavior under load; and the engine gets multi-core
headroom without turning shared state into a lock-shaped puzzle.
