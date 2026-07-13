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
disconnect/reconnect and slow-client tests matching current semantics. See the
Phase 3 kickoff design spec below.

## Phase 3 kickoff — design spec (2026-07-13)

### Summary / scope

This section is the concrete kickoff design for Phase 3 (migrate transport and
connection ownership), handed off from Research to Backend Engineering. Per the
"Migration plan" section above, Phase 3 moves HTTP/WebSocket ingress, connection
maps, room/global fan-out, connection backpressure, and authentication handoff into
Rust, forwarding commands to the existing Python command processor through the
versioned protocol. Its exit criterion is that **existing player and admin clients
run through the Rust gateway, with disconnect/reconnect and slow-client tests
matching current semantics.** This phase improves transport isolation and proves
the protocol; it is explicitly **not** the performance finish line — command
execution (parse/rules/handler/DB/commit) still runs in Python this phase, so
head-of-line blocking *within a single Python command processor* persists until
Phase 4+ moves execution to Rust.

**What the current Python transport actually is** (grounded in a read of the code,
not assumption):

- **Player WS** (`main.py`, route `resolved_settings.websocket_path` = `/ws`): auth
  is a single-use `?ticket=` handshake — `_resolve_ws_player_id` calls
  `consume_ws_ticket` (`webui/player/auth.py`), which atomically pops a ticket from
  the in-memory `AppState.ws_tickets` dict (minted by `POST /ws-ticket` after
  validating a JWT bearer token or the `lorecraft_session` cookie; 60 s TTL,
  single-use). A legacy `?player_id=` fallback is gated off by default
  (`allow_query_player_id`). A single-live-connection-per-player rule rejects a
  second tab with close code 1008. The receive loop is
  `command = await websocket.receive_text()` →
  `response = await _handle_websocket_command(state, player_id, session_id, command)`
  → `await websocket.send_json(response)`.
- **`_handle_websocket_command`** builds two SQLModel sessions + a `GameContext` via
  `build_game_context`, runs `state.command_engine.handle_command(command, ctx)`,
  then `broadcast_command_effects(state.manager, ctx, pre_room_id=...)`, and returns
  a legacy `command_result` JsonObject
  (`command`/`verb`/`noun`/`messages`/`room_messages`/`chat_messages`/`updates`). It
  also owns disambiguation-number resolution and the crash-capture path.
- **`ConnectionManager`** (`engine/game/connection_manager.py`): three in-memory
  maps — `_connections: {player_id → ws}`, `_player_rooms: {player_id → room_id}`,
  `_room_players: {room_id → set[player_id]}`. Fan-out
  (`broadcast_to_room`/`broadcast_global`) is confirmed **sequential
  await-per-recipient** (a `for player_id in ...: await send_to_player(...)` loop) —
  exactly the head-of-line hazard the plan doc suspected. A failed send drops that
  connection (logged, never silent). `players_in_room` returns a **sorted** list
  (deterministic ordering already relied on).
- **Admin WS** (`webui/admin/websocket.py`, route `/admin/ws`): auth is a `?token=`
  JWT (`decode_token` vs `admin_jwt_secret`), **accept-before-validate** so a bad
  token yields an application-level 1008 the admin UI distinguishes from a
  transient 1006. It is push-only: a per-connection `asyncio.Queue(maxsize=200)`
  drained by a `_send_loop` task, fed by `AdminBroadcaster.push` which does
  `put_nowait` and **silently drops on `QueueFull`** — the one piece of real
  backpressure that exists today.
- **No player-side rate limiting, throttle, or semaphore exists anywhere** (grep
  for `rate_limit`/`throttle`/`Semaphore` is empty outside admin's bounded queue).
  Per-connection command serialization is only implicit: the WS loop awaits each
  reply before reading the next frame.
- **Disconnect** is detected as a `WebSocketDisconnect` raised from
  `receive_text()`. The handler distinguishes an involuntary drop (socket still
  live in the manager → begin 60 s grace via `SessionSafetyService`, "connection
  flickers." room broadcast, `players-online` state_change, follow-break,
  `manager.disconnect`, `player_left` broadcast) from a graceful quit (already torn
  down → `is_connected` is False → bail, avoiding double teardown).
  `disconnect_grace_seconds` defaults to 60 s (`config.py`). **Session/player
  identity is DB-backed** (`SessionSafetyService`, `engine/services/save.py`,
  `PlayerSession` rows) — the in-memory maps are the only ephemeral part.
- A **second command entry point** exists: `POST /command`
  (`webui/player/frontend.py::handle_command`) — the HTMX classic-mode path that
  also handles graceful quit (`disconnect=True`), calling `mgr.disconnect`
  directly. This returns rendered HTML, not JSON.

### Confirmed design decisions (from Research-Planner analysis)

1. **Phase 3 is split into three sequenced sub-slices, each with its own exit
   check.** The phase is genuinely large (WS ingress + connection map + fan-out +
   backpressure + auth handoff, for *both* player and admin), and a single
   implementation slice would couple the risky socket cutover to the new
   protective backpressure work. The split:
   - **3a — Forwarding protocol + Python adapter + Rust gateway plumbing (no live
     cutover).** Build the transport, the Python-side listener, and the Rust
     connection-map + fan-out, proven against a harness while real clients still
     hit Python. Mirrors how Phases 1/2 built the contract before any cutover.
   - **3b — Player `/ws` cutover through Rust**, including auth handoff,
     connection-lifecycle events, and disconnect/reconnect.
   - **3c — Admin `/admin/ws` cutover + backpressure / slow-client policy for both
     client types.**
   Each sub-slice's exit check is stated in its task block below; the phase-level
   exit criterion (both client types through Rust; disconnect/reconnect +
   slow-client tests match current semantics) is met only when all three land.

2. **Transport mechanism between Rust and Python: a Unix-domain socket carrying
   length-prefixed JSON frames, two long-lived processes.** Rust gateway owns the
   client sockets; the Python app runs headless-of-transport with a new inbound UDS
   listener (the "gateway adapter"). Rejected alternatives and why: **HTTP
   loopback** adds per-command request/response overhead and can't cleanly carry
   the *async, Python-initiated* fan-out directives (see decision 4);
   **subprocess stdin/stdout** would make Rust own Python's lifecycle,
   contradicting "Python stays the authoritative deployable this phase" and
   complicating supervision/restart; **TCP loopback** needs port management and
   isn't localhost-confined by default. UDS is localhost-only (a security property
   for the un-authenticated internal channel), low-overhead, supports framed
   bidirectional messaging, and lets either process restart independently.
   Framing: 4-byte big-endian length prefix + UTF-8 JSON (serde on the Rust side,
   the existing frozen-dataclass mirror + `canonical_json` discipline on the
   Python side).

3. **`CommandEnvelope` (Phase 1) is reused verbatim to forward a command — no
   additive field needed.** Field sourcing at Rust ingress: `player_id`/`actor_id`
   from ticket redemption (actor == player for a player command); `session_id`
   returned to Rust by the Python `Connected` lifecycle handshake (Python's
   `SessionSafetyService.start_or_resume_session` mints/resumes it) and stamped on
   subsequent envelopes; `command_id` minted by Rust (idempotency key);
   `receive_sequence` a Rust per-connection monotonic; `deadline_ms` from Rust
   config; `world_id` a Rust config constant (single world for now); `raw` the
   command line. This confirms the Phase 1 envelope design holds under real
   ingress.

4. **The player *reply* and *fan-out* are carried as opaque legacy payloads this
   phase, not remapped onto `CommandOutcome`/`OutboundMessage`.** The plan's rule
   "Preserve current WebSocket payloads until the frontend migration is a separate
   deliberate project" governs here. The frontend expects the legacy
   `command_result` shape and legacy `feed_append`/`state_change`/
   `player_joined`/`player_left` frames; rewriting them into
   `CommandOutcome`/`OutboundMessage` is Phase 4+ work (when Rust owns the
   pipeline). Therefore the gateway wire protocol adds two **new
   gateway-framing types** in `lorecraft-protocol` (additive, Tier 1 mechanism):
   - `GatewayInbound` (Rust→Python): `RedeemTicket{ticket}`,
     `ValidateAdminToken{token}`, `Connected{player_id}`,
     `Disconnected{player_id, reason: ClientClose|GracefulQuit}`,
     `Command{CommandEnvelope}`.
   - `GatewayOutbound` (Python→Rust): `AuthResult{player_id|reject}`,
     `ConnectAck{session_id, room_id, direct_frames}`,
     `CommandReply{direct_reply: Value, deliveries: Vec<DeliveryDirective>}`, and
     standalone `Deliver{DeliveryDirective}` for async pushes (e.g. clock ticks,
     weather, cross-player follow deliveries).
   - `DeliveryDirective { target: DeliveryTarget, exclude: Option<PlayerId>,
     payload: serde_json::Value }` where
     `DeliveryTarget = Player(id) | Room(id) | Global`. Rust does **not**
     interpret `payload` — it resolves recipients from its authoritative map and
     relays the frame. This preserves payloads byte-exactly and defers the
     `OutboundMessage` convergence to Phase 4+ (flagged:
     `DeliveryDirective.payload` and `OutboundMessage` are different layers and
     will converge once Python stops emitting legacy frames).

5. **The Python adapter reuses ALL existing command + fan-out logic by injecting a
   directive-recording `ConnectionManager`.** `broadcast_command_effects` and the
   connect/disconnect handlers already take a `manager` parameter and call a fixed
   API surface (`broadcast_to_room`, `send_to_player`, `broadcast_global`,
   `move_player`, `players_in_room`, `connected_player_ids`, `occupied_rooms`). A
   new `DirectiveConnectionManager` implements that identical API but *records*
   `DeliveryDirective`s instead of awaiting sockets. This is the key move that
   keeps Phase 3's Python churn minimal — no rewrite of `broadcast_command_effects`
   or the chat/narration routing. To satisfy the recipient-selection logic that
   needs the connected set (P2ALL chat subscription filtering iterates
   `connected_player_ids()` + checks subscriptions), the
   `DirectiveConnectionManager` maintains a lightweight **read-mirror** of the
   connection map, kept consistent by the `Connected`/`Disconnected`/`move`
   lifecycle events from Rust. Python resolves all per-recipient policy against
   the mirror and emits concrete `Player`-targeted directives; simple whole-room
   broadcasts may emit `Room` directives for Rust to resolve. **Rust's map is the
   source of truth for delivery; the Python mirror is advisory for selection** —
   a directive to a just-disconnected player is a harmless no-op in Rust, exactly
   matching today's `send_to_player` "ws is None → return" behavior. (Future work:
   move channel-subscription state into the snapshot/effect model so Rust resolves
   everything and the mirror disappears.)

6. **Auth handoff = Rust owns transport, Python owns credential/session policy.**
   Rust extracts `?ticket=` (player) or `?token=` (admin) from the WS-upgrade
   query and forwards it (`RedeemTicket`/`ValidateAdminToken`); it never sees the
   JWT secret and never touches `AppState.ws_tickets`. Python runs
   `consume_ws_ticket` (keeping single-use atomicity in the in-memory dict) /
   `decode_token`, returns accept+player_id or reject; Rust closes with 1008 on
   reject. Rust reproduces the admin **accept-before-validate** nuance (accept the
   upgrade, then close 1008 on Python reject) so the admin UI's 1008-vs-1006
   distinction survives. This is the mechanism/policy split in spirit: transport
   handoff (mechanism) vs. credential validation (policy, stays Python).

7. **`lorecraft-store` stays a stub this phase — session/connection state is
   deliberately NOT persisted in Rust.** Rust connection maps are intentionally
   in-memory and ephemeral. This is *safe* precisely because durable session
   identity already lives in Python's DB (`PlayerSession` rows + 60 s grace via
   `SessionSafetyService`), and ws-tickets are re-minted per reconnect via
   Python's `POST /ws-ticket`. A Rust gateway crash loses only "who is currently
   socket-connected"; every client's auto-reconnect re-mints a ticket and
   re-establishes, and Python's `start_or_resume_session` resumes within grace.
   **This is the safety property that makes Rust-owns-connections acceptable**
   and must be stated as a design invariant, not left implicit.

8. **Rollback is a routing toggle; the old Python WS handlers are KEPT, not
   deleted.** Per the plan's "Make rollback a routing/configuration decision
   while the old path still exists," the existing `/ws` and `/admin/ws` handlers
   in `main.py`/`admin/websocket.py` stay in place behind a config flag; cutover
   points clients at the Rust gateway address, and rollback points them back.
   `HTTP POST /command` (HTMX classic mode, renders HTML) **stays on Python** this
   phase — it is a request/response form post, not a connection-ownership
   concern, and moving it would require Rust to render HTMX partials (out of
   scope). One required Python-track change: the `POST /command` graceful-quit
   path currently calls `mgr.disconnect` directly; when Rust owns the map it must
   instead route its socket-close through the gateway adapter (emit a
   `GracefulQuit` close instruction to Rust).

9. **Crate boundaries.** Confirm **Axum** (`axum::extract::ws`, Tokio-based,
   `Query` extractor maps directly onto today's `?ticket=`/`?token=` query-param
   auth) — the natural Rust equivalent of the current Starlette/FastAPI WS. Build
   out two crates, keep the rest as stubs:
   - **`lorecraft-server`** — Axum HTTP/WS ingress + auth-handoff client + the
     Rust-side UDS forwarding client. Files: `lib.rs`, `gateway.rs` (Axum
     router/app + config), `ws_player.rs`, `ws_admin.rs`, `auth.rs`
     (ticket/JWT handoff client), `forward.rs` (UDS framed client to Python).
   - **`lorecraft-events`** — the connection-map + fan-out *mechanism* (Rust-owned,
     headless-testable). Files: `connections.rs` (`ConnectionRegistry`:
     player↔handle, `player→room`, `room→set`, all with sorted deterministic
     reads mirroring Python's `sorted()`), `dispatch.rs` (per-connection bounded
     outbound mpsc + writer task; fan-out via non-blocking `try_send` so one slow
     client never head-of-line-blocks a broadcast — the core improvement over
     Python's sequential await), `backpressure.rs` (slow-client policy). Keeping
     fan-out here (not crammed into `-server`) keeps it reusable and
     unit-testable without a live socket. `lorecraft-store` / `lorecraft-script*`
     stay stubs.

10. **Backpressure is NEW protective behavior, not a port of an existing limit.**
    Player-side has *no* current limit, so "match current semantics" for this
    dimension means "don't regress correctness for well-behaved clients," **not**
    "reproduce an existing rate limit." Design: each connection gets a bounded
    outbound queue (config depth, e.g. 256) drained by its own writer task. On
    sustained overflow (N consecutive `try_send` failures or a time budget), the
    slow client is disconnected (dedicated close code). Coalescing policy:
    `state_change`/panel-refresh frames are idempotent and **coalescible** (keep-
    latest per panel key); `feed_append` frames each matter and are **not**
    coalesced (they queue; overflow → disconnect). Which frame types coalesce is
    *policy* (Tier 2); the bounded-queue + disconnect *mechanism* is Tier 1.
    Per-connection at-most-one-outstanding-command is preserved (matches today's
    implicit serialization); a per-player command rate limit is added as new,
    generous-by-default protective config (off/loose enough not to regress
    well-behaved clients).

11. **Tier classification** (per AGENTS.md "Tier 1 = mechanism, Tier 2 = policy"):
    - **Tier 1 / mechanism** (Rust `lorecraft-server` + `lorecraft-events`): WS
      ingress/upgrade, connection registry, room membership, bounded concurrent
      fan-out, per-connection outbound queue, backpressure *enforcement*,
      command-forwarding transport, sequence assignment, deadline stamping,
      lifecycle-event emission.
    - **Tier 2 / policy**: which frame types coalesce vs. queue, slow-client
      disconnect thresholds/grace lengths, per-player rate-limit values, and
      (Python-owned) credential validation (ticket/JWT) and channel-subscription
      recipient selection.
    - **Explicit cross-axis note:** AGENTS.md's Tier 1/2 rule and
      `tests/unit/test_tier_boundaries.py` govern **only Python `src/lorecraft/`
      import direction** — they do **not** apply to Rust crates. The Rust
      gateway's own mechanism/policy split is an analogous-in-spirit but distinct
      axis. The **new Python forwarding-adapter code lives under
      `src/lorecraft/` and IS subject to the import-direction rule**: it needs
      `command_engine`, `ConnectionManager`, `SessionSafetyService`,
      `consume_ws_ticket`, and admin `decode_token`, so it is a
      **composition/web-host-layer** module (`src/lorecraft/gateway/`), may
      import engine + features (like `main.py`), and must **not** be imported
      *by* `engine/`. State this so a reviewer doesn't file it under `engine/` by
      reflex.

12. **Tunables note** (per AGENTS.md "Prefer live-tunable configuration"): this
    phase's dials — outbound queue depth, slow-client disconnect threshold,
    per-player command rate limit, `deadline_ms` — are **operational**, not
    game-balance. Following the same judgment call Phases 1/2 made for
    `deadline_ms`/`ScriptBudget`: **static config this phase** (Rust config /
    env), flagged as candidate *operational* live-tunables later (an operator
    retuning under load) but **not** warranting the `WorldClock` DB-singleton
    pattern, which is for *game-balance* dials an admin retunes.
    `disconnect_grace_seconds` (60 s) already exists as Python config and stays
    Python-owned. No game-balance dial is introduced.

### Proposed tasks (Phase 3)

Two implementation tracks (Rust `rust/crates/`, Python `src/lorecraft/gateway/` +
`webui/`), each agent in its own scratch worktree off `rust-port`, no file overlap.
**Sequencing: 3a before 3b before 3c**; within 3a the protocol/framing types are
the ordering dependency (they unblock both the Python adapter and the Rust
client).

**Sub-slice 3a — forwarding protocol + adapter + gateway plumbing (no live
cutover). Exit check: a synthetic command driven Rust→Python→Rust produces the
byte-identical `command_result` payload and the same set of `DeliveryDirective`s
the real `ConnectionManager` path produces today (parity harness), with no real
client cutover.**

- [ ] `lorecraft-protocol`: add `GatewayInbound`, `GatewayOutbound`,
  `DeliveryDirective`, `DeliveryTarget` (additive; `CommandEnvelope` unchanged) +
  Python frozen-dataclass mirror with recursive `to_json`/`from_json` — **Tier 1**
  — serde/JSON round-trip parity both languages; `CommandEnvelope` still reused
  verbatim — tunable: PROTOCOL_VERSION static.
- [ ] Python `src/lorecraft/gateway/adapter.py`: UDS listener (length-prefixed
  JSON) dispatching `RedeemTicket`/`ValidateAdminToken`/`Connected`/
  `Disconnected`/`Command` to existing `consume_ws_ticket`/`decode_token`/
  `SessionSafetyService`/`_handle_websocket_command` — **Tier 1
  (composition/web-host layer, respects import-direction rule)** — round-trips a
  command; emits `CommandReply` — tunable: socket path static.
- [ ] Python `DirectiveConnectionManager` (same API surface as
  `ConnectionManager`, records `DeliveryDirective`s + maintains lifecycle-fed
  read-mirror) injected into `broadcast_command_effects` — **Tier 1 (web-host
  layer)** — parity test: directives recorded == frames the real manager would
  send for the same command — tunable: static.
- [ ] `lorecraft-events`: `ConnectionRegistry` (three maps, sorted reads) +
  `dispatch.rs` per-connection bounded outbound queue + concurrent fan-out —
  **Tier 1** — unit tests: join/leave/move, broadcast-to-room resolves sorted
  membership, one blocked queue doesn't stall a co-recipient — tunable: queue
  depth static-now/ops-live-later.
- [ ] `lorecraft-server`: `forward.rs` UDS framed client + Axum app skeleton
  (routes not yet serving real clients) — **Tier 1** — integration test: Rust
  client sends `Command`, receives `CommandReply`, relays directives to the
  registry — tunable: static.

**Sub-slice 3b — player `/ws` cutover through Rust. Exit check:
`tests/e2e/test_reconnect.py`, `tests/e2e/test_multiplayer_realtime.py`, and
`tests/simulation/test_multiplayer_scenarios.py` pass with clients pointed at
the Rust gateway; bad/expired ticket → 1008 through Rust.**

- [ ] `lorecraft-server::ws_player`: Axum `/ws` upgrade, `?ticket=` extraction →
  `RedeemTicket` handoff, single-live-connection rule, receive-loop → `Command`
  forward → relay `direct_reply` to client — **Tier 1** — a real client completes
  a `look` through Rust with identical payload — tunable: deadline_ms static.
- [ ] Connection lifecycle: Rust emits `Connected` (receives
  `ConnectAck{session_id, room_id, direct_frames}`) and `Disconnected{reason}` on
  socket close; Python runs grace/flicker/follow-break/player_left via existing
  handlers, returning directives — **Tier 1 (Rust) + web-host (Python)** —
  disconnect drops the map entry immediately; grace/`player_left` fan-out arrives
  as directives — tunable: grace_seconds Python-owned static.
- [ ] Disconnect/reconnect semantics: graceful-quit (command `disconnect=True`,
  incl. `POST /command` path) tags the close `GracefulQuit` so Python skips
  double-teardown; reconnect after gateway restart re-mints ticket + resumes
  session within grace (DB-backed) — **Tier 1** — reconnect e2e green; documented
  invariant: Rust map ephemeral, Python DB durable — tunable: static.

**Sub-slice 3c — admin `/admin/ws` cutover + backpressure/slow-client policy.
Exit check: `tests/e2e/test_admin_session.py` passes through Rust (bad token →
1008, preserving 1008-vs-1006); a new slow-client test shows a stalled consumer
is bounded/disconnected without blocking a co-located client; well-behaved
clients unaffected.**

- [ ] `lorecraft-server::ws_admin`: Axum `/admin/ws`, accept-before-validate,
  `?token=` → `ValidateAdminToken` handoff, push-only via `lorecraft-events`
  outbound queue — **Tier 1** — admin push arrives through Rust; bad token →
  1008 after accept — tunable: static.
- [ ] `lorecraft-events::backpressure`: bounded outbound queue + sustained-
  overflow slow-client disconnect + `state_change`-coalesce /
  `feed_append`-no-coalesce policy — **Tier 1 mechanism, Tier 2 policy (which
  frames coalesce / thresholds)** — slow consumer disconnected within threshold,
  sibling delivery unaffected — tunable: queue depth + threshold
  static-now/ops-live-later; coalesce set = policy.
- [ ] Per-player command rate limit + at-most-one-outstanding-per-connection —
  **Tier 1 mechanism, Tier 2 policy (limit values)** — generous default doesn't
  regress well-behaved clients; abusive client throttled — tunable: rate values
  static-now/ops-live-later.

### Existing test coverage + gaps to flag (for Pytest Writer / Test & QA)

**Defines "current semantics" the gateway must match:** e2e —
`test_reconnect.py::test_ws_reconnects_and_resumes_live_delivery`,
`test_multiplayer_realtime.py` (5 tests: say propagation, `player_joined`
here-now, `player_left` panel, dropped-item visibility, third-person
narration), `test_admin_session.py`, `test_auth_flows.py` (ticket auth);
simulation — `test_multiplayer_scenarios.py`,
`test_load.py::test_concurrent_players_command_latency`,
`test_soak.py::test_mixed_scenarios_soak`. The `virtual_player.py` harness
connects to `ws_url/ws?player_id=` — a new conftest fixture must boot **both**
the Rust gateway and the Python adapter and point clients at Rust (harness
work, flag it).

**Gaps needing NEW tests (author later; flag now so they're not missed):** (1) a
**slow-client backpressure test** — no player-side equivalent exists; a client
that stops reading must be bounded + disconnected without blocking a
co-located player. (2) A **gateway-restart reconnect test** — Rust restart
mid-session; client reconnects; Python resumes within grace (may be hard in
the current harness — flag feasibility). (3) **Auth-handoff rejection** —
bad/expired ticket and bad admin token both yield 1008 through Rust,
preserving the admin 1008-vs-1006 distinction. (4) **Forwarding-adapter
parity unit test** — `DirectiveConnectionManager` emits the same directives
the real `ConnectionManager` would. (5) **Re-interpret
`test_event_loop_blocking.py`:** because command *execution* still runs in
Python via forwarding this phase, the intra-processor head-of-line assertion
likely still holds; the Rust gateway only removes cross-*connection* delivery
blocking. Confirm the characterization test's meaning is updated, not silently
broken, and note it fully inverts only at Phase 4+.

### OPEN ITEMS

1. **`GatewayOutbound` async-push channel vs. request/reply multiplexing.**
   Python emits both synchronous `CommandReply`s and unsolicited `Deliver`s
   (clock ticks, weather, cross-player follow deliveries) on the same UDS
   connection. Recommendation: a single multiplexed framed stream with a
   correlation id on request/reply frames and un-correlated `Deliver` frames; a
   dedicated Python→Rust push task. Flagged rather than silently decided —
   Backend Engineering should confirm the multiplexing shape in 3a before the
   Rust client hardens around it.
2. **Channel-subscription read-mirror longevity.** The Python mirror (decision
   5) is a Phase 3 expedient. Recommendation stated: move subscription state
   into the snapshot/effect model in a later phase so Rust resolves all
   recipients and the mirror disappears — noted as future work, not this phase.

### Kickoff status — sub-slice 3a (2026-07-13)

**Only sub-slice 3a has landed.** 3b (player `/ws` cutover) and 3c (admin
cutover + backpressure) have **not** been built yet — see "Still pending"
below. The phase-level exit criterion is therefore **not yet met**; this
section documents 3a alone.

Five commits landed on branch `rust-port-phase3-impl`, all after `51eb284`
(the design-spec-only commit):

- `447eb7b` — gateway protocol types: `GatewayInbound`/`GatewayOutbound`/
  `DeliveryDirective`/`DeliveryTarget` in `lorecraft-protocol` + the Python
  mirror `src/lorecraft/protocol/gateway.py`. Resolved OPEN ITEM 1 (async-push
  vs. request/reply multiplexing) by adding `command_id` to `CommandReply` for
  request/reply correlation over the multiplexed UDS stream.
- `02d6a422` — Python `src/lorecraft/gateway/adapter.py` UDS listener +
  `DirectiveConnectionManager`, plus a new `ConnectionManagerProtocol`
  structural-typing seam in `engine/game/connection_manager.py` that makes the
  manager injectable without any `cast`/`type: ignore`. Extracted the shared
  command-handling core out of `main.py` into `webui/player/ws_command.py` +
  `ui_snapshots.py` so both the live `/ws` handler and the new adapter call
  identical logic.
- `aee1a7a` — Rust `lorecraft-events` crate: `ConnectionRegistry` (three
  sorted-read connection maps) + `dispatch.rs` bounded, non-blocking
  `try_send` fan-out, proving the headline property that one slow/full
  recipient queue never stalls delivery to a sibling recipient.
- `47acb50` — Rust `lorecraft-server` crate: `forward.rs` UDS framed client
  demultiplexing correlated `CommandReply`s from uncorrelated `Deliver`
  pushes, plus an Axum app skeleton with a working health-check route and
  honestly-scoped `ws_player.rs`/`ws_admin.rs`/`auth.rs` stubs for 3b/3c to
  fill in. Added `tokio` as the workspace's first async dependency and pinned
  `axum = "=0.8.4"` exactly, since 0.8.9+ requires rustc 1.80 above this
  workspace's 1.75 MSRV.
- `7720a9a` — test-only: a new cross-manager `DeliveryDirective` parity test
  proving the adapter's recorded directives resolve to the same payloads the
  real `ConnectionManager` would actually send to a room-mate, closing the
  "same `DeliveryDirective` set" half of 3a's exit check; the "byte-identical
  `command_result`" half was already covered by earlier per-task tests.

**3a's own exit check is met:** "a synthetic command driven Rust→Python→Rust
produces the byte-identical `command_result` payload and the same set of
`DeliveryDirective`s the real `ConnectionManager` path produces today (parity
harness), with no real client cutover" — proven via a hermetic real-UDS-socket
round-trip (a raw `asyncio` client standing in for Rust's `forward.rs`, since
both speak the identical length-prefixed-JSON wire format) plus the
two-player parity comparison added in `7720a9a`. No real client (`/ws` or
`/admin/ws`) was cut over — both still run through the pre-existing Python
handlers, exactly as designed.

**Code Review:** zero blocking findings across all five commits. Four
advisory (non-blocking) notes, all forward-looking for the 3b/3c implementer,
not defects in 3a:

1. Once 3b actually starts the UDS listener live, the socket file should get
   restrictive permissions (0600) since the channel is intentionally
   unauthenticated internally and currently trusts `player_id` on faith —
   inert risk today since nothing starts the listener yet.
2. A lock-discipline note: lifecycle-event and command-handling directive
   draining share one buffer safely today only because there's a single Rust
   peer and no real `await` in the delivery methods — worth a comment or
   shared-lock fix before a second peer/async delivery method could exist.
3. The axum `=0.8.4` exact pin is sound but forgoes intra-0.8.x patch
   pickup — a `>=0.8.4, <0.8.9` range would preserve the MSRV ceiling while
   allowing patches, flagged for whoever owns workspace toolchain policy.
4. `start_unix_server` doesn't unlink a stale socket file from a prior crash,
   and `stop()` doesn't unlink either — a live-restart robustness gap for 3b
   to close when it wires the listener into a real process lifecycle.

**Test & QA, full independent re-run:**

- Python: `make lint` clean; `make typecheck` 0 errors; `make test` 1471
  passed / 2 skipped; `make test-cov` 90.96% (gate 80%);
  `tests/unit/test_tier_boundaries.py` 2 passed, confirming
  `src/lorecraft/gateway/` is not imported by anything under `engine/`.
- Rust (from `rust/`): `cargo build --all` clean; `cargo test --all` 60
  passed across 8 crates (core 5, feature-look 5, protocol 20, replay 8,
  runtime 4, scheduler 6, events 10, server 2); `cargo clippy --all-targets
  -- -D warnings` clean; `cargo fmt --all -- --check` clean.
- One flagged non-blocking observation, **not** part of Phase 3a's own
  changes: a first full-suite run hit 3 transient failures in
  `tests/unit/test_save.py` ("No MeterDef registered for key 'hp'") that were
  not reproducible on an immediate re-run or in isolation — looks like a
  pre-existing test-order/xdist-file-distribution flake unconnected to any of
  the five Phase 3a commits (none touch MeterDef/progression code). Noted
  plainly as a pre-existing item worth separate investigation, not
  attributed to this phase's work.

**Still pending / explicitly NOT done:** sub-slice 3b (player `/ws` cutover
through Rust — real client traffic still goes through the existing Python
`/ws` handler; `ws_player.rs`/`auth.rs`'s ticket-handoff logic is still a
stub) and sub-slice 3c (admin `/admin/ws` cutover + backpressure/slow-client
policy — `ws_admin.rs` is still a stub, `lorecraft-events::backpressure`
doesn't exist yet). **The phase-level exit criterion — both client types
through the Rust gateway, disconnect/reconnect + slow-client tests matching
current semantics — is NOT yet met** — only the 3a foundation is proven. This
is stated explicitly so a future reader doesn't assume Phase 3 is complete.

**Recommended next increment:** sub-slice 3b (player `/ws` cutover), per the
design spec's own stated sequencing (3a before 3b before 3c) — do not skip
ahead to 3c.

### Kickoff status — sub-slice 3b (2026-07-13)

**Sub-slice 3b is complete and exit-check verified.** The player `/ws` cutover
via the Rust gateway front-door is now implemented and tested through real
clients (browser e2e via Playwright+Chromium in-env). 3c (admin cutover +
backpressure/slow-client policy) is **still pending** — see "Still pending"
below. **The phase-level exit criterion is therefore NOT yet fully met**; this
section documents 3b alone. Two sub-slices (3b player + 3c admin) must both land
before the phase gate closes.

Seven commits landed on branch `rust-port-phase3-impl`, all after 3a's docs
commit `6a1083e`:

- `ae646cc` — Python: `GatewayAdapter` wired into the app lifespan behind a
  `gateway_enabled` flag (default off = immediate rollback safety); UDS
  hardening (0600 socket perms + stale-socket unlink — actionable 3a review
  advisory notes 1+3); lifecycle-vs-command directive-drain lock safeguard
  (note 2); follow-break-on-disconnect wired (deferred from 3a).
- `7bc8d9e` — Rust: player `/ws` termination via the Rust gateway — `?ticket=`
  handoff from the Python adapter, single-live-connection rule (rejects if
  client already connected), one dedicated UDS link per WS connection (resolves
  OPEN ITEM 1's bidirectional-channel shape), per-connection bounded outbound
  writer task for fair delivery, and a new `lorecraft-gateway` binary (prints
  `GATEWAY_LISTENING <addr>` for harness port-discovery). MSRV 1.75 held
  (uuid <1.21, tokio-tungstenite <0.27, axum-core pinned).
- `63cbed5` — Rust: transparent HTTP reverse proxy (reqwest 0.13.3, MSRV-fit,
  no TLS stack — plain loopback only) of all non-WS requests to the Python
  uvicorn backend; hop-by-hop header stripping, redirect-non-following,
  Set-Cookie passthrough; confirmed no SSE in the player UI.
- `cff4ab9` — Test harness: dual-process fixture (`tests/_rust_gateway.py`)
  that builds+spawns the Rust gateway and boots the Python app with the adapter,
  gated by `LORECRAFT_THROUGH_RUST=1` env var; points the three named exit tests
  at the Rust front door; sim harness mints real tickets through the proxy; a
  bad-ticket→WS-1008 close-code test.
- `c7327f6` — Python: autonomous clock/weather broadcasts pushed through the
  gateway as `Deliver` frames (a new `GatewayPushManager` + per-connection
  outbound queue), so server-initiated pushes reach gateway-connected browsers.
- `0359f76` — Rust+Python: fixed a gate-found BLOCKING disconnect-fan-out race
  via an additive `GatewayOutbound::DisconnectAck` frame (Rust awaits the ack,
  bounded 5s backstop, so asynchronous tear-down `Deliver`s —
  `player_left`/follow-break/players-online — reach remaining players before the
  link tears down).
- `5696002` — Python: fixed a second gate-found EXIT-BLOCKING gap — the browser
  sends commands via `POST /command` (HTMX), whose `broadcast_command_effects`
  was using the empty-in-gateway-mode real `ConnectionManager`; now routes
  through the `GatewayPushManager` (both fan-out and command execution path) so
  cross-player broadcasts from non-WS commands reach Rust-connected browsers.

**3b's own exit check is met:** all three named exit tests pass **through the
Rust front door** (not just Python-direct):

- `tests/e2e/test_reconnect.py` — 6/6 via Playwright+Chromium (browser e2e
  automation; verified in-env with real browser subprocess).
- `tests/e2e/test_multiplayer_realtime.py` — 6/6 via Playwright+Chromium
  (browser e2e).
- `tests/simulation/test_multiplayer_scenarios.py` — 5/5 (live-server harness,
  direct player protocol).
- Bad/expired/reused ticket → WS close code 1008 through Rust (3/3 variants).
- Rollback (Python-direct, flag off) intact (6/6, same test suite still passes
  without the gateway).

A full secondary verification run by Test & QA confirmed:

- Python: `make lint` clean; `make typecheck` 0 errors; `make test` 1486
  passed / 1 skipped; `make test-cov` 91% (gate 80%); `tests/unit/test_tier_boundaries.py`
  clean, confirming `src/lorecraft/gateway/` is not imported by `engine/`.
- Rust (from `rust/`): `cargo build --all` clean; `cargo test --all` 81 tests
  passed; `cargo clippy -D warnings` clean; `cargo fmt --check` clean.

**Code Review:** zero blocking findings across all seven commits. One
advisory note on the 5-second `DisconnectAck` timeout — appropriate for
in-test use; production deployments may tune it, flagged for future runbook
documentation.

**Still pending / explicitly NOT done:** sub-slice 3c (admin `/admin/ws`
cutover + backpressure/slow-client policy — `ws_admin.rs` remains a stub,
`lorecraft-events::backpressure` module does not yet exist) and several
non-blocking follow-ups that must be resolved before "gateway enabled by
default" (see below). **The phase-level exit criterion — both client types
through the Rust gateway; disconnect/reconnect + slow-client tests matching
current semantics — is NOT yet met** — 3b delivers the player half, 3c is
still needed.

**KNOWN FOLLOW-UPS** (NOT exit-blocking for 3b, but MUST be listed — several
must be closed before "gateway on by default"; recorded here so the phase isn't
overclaimed):

1. **Rust `ConnectionRegistry` room-move staleness (correctness gap).** A `POST
   /command` room move updates only the Python adapter's mirror, not Rust's
   authoritative `ConnectionRegistry` — so after a browser-UI move, if the mover
   sits still and a third party enters the mover's NEW room, the mover misses
   that later room broadcast. Untested by the exit tests (they only assert a
   stationary observer seeing a mover's leave/arrival). Needs a Python→Rust
   move instruction in the `GatewayInbound` protocol.
2. **Graceful-quit via `POST /command` (design decision 8).** The
   `disconnect=True` teardown still uses the real `ConnectionManager`; in
   gateway mode the Rust side owns the socket, so a proper close needs a new
   Python→Rust close instruction. A `TODO(decision 8)` marks it in
   `frontend.py`. Flag-off (rollback to Python-direct) is unaffected.
3. **"Dark" autonomous broadcasters (mechanical gap).** Only clock + weather
   narration route through the gateway; `NpcBehaviorService`, `TransitService`,
   `QuestTimerService`, `WeatherFrontService` storm effects, and
   `MobileRouteService` still target the real `ConnectionManager` and are dark
   to gateway clients. A guard test covers clock/weather; the rest is the same
   mechanical `broadcast_manager` swap once verified.
4. **Unbounded Python push queue (hardening).** `_ClientLink.outbound` in the
   adapter has no depth limit; the Rust side is bounded. A late-phase hardening
   item to prevent memory growth under slow-client conditions before going to
   production.
5. **`players_here` presence dots (cosmetic staleness).** On the actor's own
   panel, the live presence dots remain cosmetically stale in gateway mode —
   Rust sees the right set, but the update message to the actor itself may
   reflect a slightly earlier snapshot. Low priority, non-functional.
6. **CI browser e2e coverage.** The exit tests (Playwright+Chromium) were
   verified in-env here; ensure CI has the `.[e2e]` extras + `playwright install
   chromium` in the build matrix for ongoing automated coverage.

**Recommended next increment:** sub-slice 3c (admin `/admin/ws` cutover), per
the design spec's own stated sequencing (3a before 3b before 3c) — do not skip
ahead.

### Where things stand / Next

After this lands, the natural next increment is Phase 4 — migrate one vertical
gameplay slice (`look`, then movement) so Rust owns parsing/repo-reads/
transaction/effect-validation/audit-outbox for the selected verb, routing only
migrated commands to Rust, with the `look_only.audit.json` golden as the
pipeline-owned parity target.

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
