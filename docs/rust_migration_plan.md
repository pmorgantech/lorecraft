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
