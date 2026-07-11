# Scripting & Behavior Engine — Design Plan

**Status:** Design proposal (2026-07-09). Not yet on the roadmap.
**Scope:** Engine support for scripting NPC behavior and world reactivity (rooms,
items, containers, zones, weather, ambient events).
**Companion docs:** [`roadmap_world.md`](roadmap_world.md) (content that needs this),
[`engine_core.md`](engine_core.md) (Tier 1 primitive specs), [`wishlist.md`](wishlist.md)
(§ "Scripting layer for builders", § "Dynamic area behaviors").

---

## 0. TL;DR — the recommendation

**Do not add Lua. Do not (yet) invent a new scripting language.** The engine already
*has* a de-facto scripting substrate: declarative **trigger → conditions → side-effects**
authored in world YAML and executed by pluggable registries (`SideEffectRegistry`,
`CommandConditionRegistry`, dialogue/quest `ConditionRegistry`, `RuleEngine`,
`ModifierRegistry`, `MobileRouteService` hooks). Dialogue trees, mechanism puzzles,
item-combination puzzles, context-verbs, timed quests, and escort quests are all already
"scripts" in this model.

What's actually missing is **not a language** — it's three engine primitives that let that
same declarative vocabulary run **without a player actor**:

1. **An actor-less execution context** (`WorldContext`) so side-effects/conditions can fire
   from a tick, not just a player command. Today every side-effect handler hard-depends on
   `ctx.player` (`GameContext` is player-centric — see `engine/game/context.py:48`).
2. **An NPC agency loop** — a per-tick "what does this NPC do now" driver keyed off
   `NPC.behavior` (which exists on the model at `engine/models/world.py:124` but is **dead
   schema — read by nothing**).
3. **A declarative trigger-binding layer** — "when EVENT happens at/to this room|item|npc,
   run these guarded actions" — attachable in YAML to any entity.

Close those three and **every example** in the prompt and in `roadmap_world.md` (zone
patrol, random wander, weather that travels between zones, room narrative triggers, a magic
container that buffs/curses its contents) becomes expressible in **plain declarative YAML**
over primitives we already ship.

**One cross-cutting prerequisite (sprint A0):** the declarative vocabulary itself must be a
*designed, self-describing* API — a descriptor-carrying registry + a generated catalog + a
naming convention — so it stays consistent and, crucially, **auto-detects duplicated
functionality** as many hands (human and AI) register into it. See §8.

**A real scripting *language* (a small DSL) is Phase B — and only when YAML repetition
proves it's needed.** Even then it should be a data-expressed behavior-tree/rule grammar
interpreted by a ~200-line deterministic tree-walker over the Phase-A primitives — never an
embedded general-purpose interpreter. Lua specifically is the wrong tool for this codebase
(reasons in §4).

---

## 1. Why this question matters now

`roadmap_world.md` marks a cluster of content as **[BLOCKED]** on engine work:

- NPC autonomous behavior (patrol-a-zone, wander, aggro, flee, follow-on-own-initiative)
- Ambient/flavor text rotation and timed room events
- Day/night-driven NPC behavior branching
- Zone-bound climate / weather that varies by area
- Data-driven spawn/respawn policies

Every one of these is an **autonomy** gap, not a content-authoring gap. The player-triggered
half of scripting is mature; the world-acts-on-its-own half doesn't exist. Deciding *how* we
add autonomy (typed primitives vs. embedded DSL vs. Lua) is the fork in the road, and it
constrains the engine/content-separation plan (`wishlist.md` flags scripting as "the sharpest
edge" of that split).

---

## 2. What already exists — the scripting substrate (don't rebuild it)

The dive through the graph (`GameContext` 370 edges, `EventBus` 246, `CommandEngine` 265)
confirms a rich, already-pluggable extension surface. Every one of these is a place content
already injects behavior without touching engine code:

| Primitive | File | What it is | Actor-bound? |
|-----------|------|-----------|--------------|
| **`EventBus`** | `engine/game/events.py` | Synchronous, priority-ordered, exception-isolated pub/sub. The nervous system. | no |
| **`SchedulerService`** | `engine/services/scheduler.py` | DB-backed "run job at game-epoch T", emits `SCHEDULED_JOB_DUE`. Restart-safe. Knows no game rules. | no |
| **`MobileRouteService`** | `engine/services/mobile_route.py` | Waypoint state machine on the scheduler; `RouteHooks` = `may_depart`/`on_depart`/`on_arrive`/`on_tick`. Only transit uses it today. | no |
| **`EffectService` / `ActiveEffect`** | `engine/services/effects.py` | Timed effects generic over `entity_type` (`player`/`npc`/**`room`**). `EffectDef.on_apply`/`on_expire` + `modifiers`. §3.9 room auras reuse it. | no |
| **`SideEffectRegistry`** | `features/npc/side_effects.py` | Named handlers `(JsonValue, GameContext) → None`: `give_item`, `start_quest`, `set_flags`, `start_escort`, … Powers dialogue, mechanisms, item-combos, context-verbs, quests. | **YES — needs `ctx.player`** |
| **`CommandConditionRegistry`** | `engine/game/command_conditions.py` | Named predicates `"name:param"` gating commands. Fail-open on unknown. | via GameContext |
| **dialogue/quest `ConditionRegistry`** | `features/npc/dialogue_conditions.py`, `features/quests/conditions.py` | Named predicates gating dialogue choices & quest-stage branches. | via GameContext |
| **`RuleEngine`** | `engine/game/rules.py` | `allow`/`block(reason)` gates on events, with modified-payload passthrough. | no |
| **`ModifierRegistry` + `ModifierSource`** | `engine/game/modifiers.py` | Stacked, capped value resolution from pluggable sources (equipment, traits, terrain, effects). | no |
| **`FeatureManifest` + loader** | `features/manifest.py`, `features/loader.py` | Features self-wire onto the shared registries via `register_fn(app_state)`; auto-discovered, config-enabled. | no |

**The pattern is uniform and healthy:** a *named* handler/predicate in a registry, referenced
by *string* from YAML, fired by the engine. Content can only name registered primitives —
unknown names fail-open/ignored, which is a natural sandbox. This is the thing to grow, not
replace.

### The actor-less workaround that reveals the gap

Three services already run "scripts" on a tick with **no player**: `QuestTimerService`
(`features/quests/timer.py`), transit narration (`features/transit/service.py`), and the
`EffectService` expiry sweep. Look at how they cope (`timer.py:12-16`):

> *"Runs with no GameContext (a global sweep, not one player's command): reads/writes
> `Player.flags` directly and narrates via `ConnectionManager.send_to_player` … the same
> pattern `services/transit.py` uses."*

Each one **hand-rolls its own actor-less context**: raw `Engine` → its own `Session` → direct
model mutation → `asyncio.create_task(manager.broadcast_to_room(...))` for narration. There is
**no shared abstraction** for "the world does something to a room/npc/item on its own." That
duplication *is* the gap. Autonomy today means writing a new bespoke service every time.

---

## 3. The real gap — three primitives, then it's all YAML

### 3.1 `WorldContext` — an actor-less execution context (Tier 1)

The blocker: `SideEffectRegistry` handlers take `GameContext`, whose `player` and `room` are
**non-optional** (`context.py:48-49`), and most handlers dereference `ctx.player` immediately
(`_handle_give_item`, `_handle_set_flags`, …). So the rich side-effect vocabulary **cannot be
reused by a tick-driven trigger** — the exact thing autonomy needs.

**Proposal:** extract the actor-independent capabilities into a base the two contexts share:

```python
@dataclass
class WorldContext:                     # NEW — no player, no room
    session: Session
    clock: WorldClock | None
    bus: EventBus
    rng: GameRng                        # keep determinism (§3.6 audit-critical)
    manager: ConnectionManager          # narration to rooms/players
    room_repo: RoomRepo
    item_repo: ItemRepo
    stack_repo: StackRepo
    npc_repo: NpcRepo
    item_location: ItemLocationService
    ledger: LedgerService
    meters: MeterService
    effects: EffectService
    # narration helpers that broadcast to a room/player rather than an actor's feed
    def narrate_room(self, room_id: str, text: str) -> None: ...
    def defer_delivery(self, factory) -> None: ...

@dataclass
class GameContext(WorldContext):        # player-command context = WorldContext + actor
    player: Player
    room: Room
    parsed_command: ParsedCommand | None = None
    # …existing say()/tell_room()/chat_* actor-facing helpers…
```

Then split the side-effect handler signature into two tiers:

- **World-safe effects** (`(JsonValue, WorldContext, target: EntityRef) → None`): `set_flags`
  on an explicit entity, `give_item`/`spawn_item` into an explicit location, `apply_effect`,
  `adjust_reputation`, `emit_event`, `narrate`. These take an **explicit target** instead of
  the implicit `ctx.player`, so they work from a tick *or* a command.
- **Actor-only effects** (`(JsonValue, GameContext) → None`): `end_dialogue`, actor-feed
  messaging — genuinely need the actor. Stay on `GameContext`.

The existing registry keeps working (a `GameContext` *is-a* `WorldContext`); we're widening the
domain, not breaking callers. This is the single highest-leverage change — it unlocks
everything else.

> **Determinism guard rail (non-negotiable):** all world-context randomness routes through
> `ctx.rng` (`GameRng`), never `random`. The engine's audit-log replay + seedable RNG
> (`engine_core.md` §3.6, "audit-regression-critical") is the invariant that makes autonomous
> behavior reproducible. Any autonomy that rolls dice off-`GameRng` breaks replay.

### 3.2 The NPC agency loop — `NpcBehaviorService` (Tier 2 feature `npc_ai`)

`NPC.behavior` is dead schema. Give it an owner: a service subscribed to a coarse tick
(`HOUR_CHANGED` for cheap cadence, or a dedicated `NPC_MOVE_DUE` scheduler job for finer
control) that, for each NPC, dispatches on a **behavior mode** to a registered handler.

```python
# features/npc_ai/modes.py  — a registry, exactly like SideEffectRegistry
BehaviorMode = Callable[[NPC, WorldContext], None]
_registry: dict[str, BehaviorMode] = {}     # "patrol", "wander", "guard", "hunt", …
```

Behavior config lives on the NPC in YAML (extend `NPC.behavior` from a bare string into a
structured blob, or add `NPC.behavior_config: JsonObject`):

```yaml
- id: sewer_guard
  behavior:
    mode: patrol
    route: [sewer_junction_main, sewer_tunnel_north, sewer_tunnel_east]
    dwell_ticks: 2
    on_see_player:                      # a trigger (see §3.3), evaluated when a player is co-located
      when: { player_reputation_below: -50 }
      do:   [{ narrate: "The guard glares and blocks your path." }]
```

Modes map to the roadmap examples directly:

| Mode | Mechanism it reuses |
|------|--------------------|
| `patrol` (fixed room list / loop) | wire **`MobileRouteService`** with an NPC `RouteHooks` (moves `NPC.current_room_id`, broadcasts arrive/depart). The hard scheduling is already built — this is the "modest glue" `roadmap_world.md` calls out. First real emitter of `GameEvent.NPC_MOVED`. |
| `wander` (random within `area_id`) | pick a random adjacency-valid room in the NPC's `area_id` via `ctx.rng.choice` each tick. |
| `guard` / `hunt` / `flee` | read reputation/marks/traits of co-located players; enqueue actions. (Aggression that *resolves* to damage waits on combat — but "block", "refuse service", "flee to home_room", "summon", "narrate a threat" need no combat system.) |
| `shopkeeper` / `quest_giver` | mostly already handled by dialogue + shop; the AI loop only adds proactive greetings/idle banter. |
| `item_stealer` / `looter` / `recycler` | tick action: move an item stack from room/player-adjacent location via `item_location`; drop-tables via existing `loot_table`. |

This is a **Tier 2 feature** (`features/npc_ai/`), not engine code — it composes engine
primitives, obeys the boundary, and can be enabled/disabled per world.

### 3.3 Declarative trigger binding — `on_<event>` blocks on any entity

Unify the scattered ad-hoc hooks (mechanism `side_effects`, dialogue effects, escort) into one
attachable shape. A **trigger** = `{ on: EVENT, when: <conditions>, do: [<effects>] }`,
declarable on a Room, Item, NPC, or Exit in YAML. A single `TriggerService` subscribes to the
relevant `GameEvent`s, and on each event finds triggers bound to the involved entity, evaluates
`when` via the **condition registries**, and runs `do` via the **side-effect registry** — now
against a `WorldContext` (§3.1), so triggers fire whether the cause was a player or a tick.

```yaml
rooms:
  - id: crystal_cavern
    triggers:
      - on: player_entered
        when: { not_flag: heard_the_hum }
        do:
          - { set_flags_on_actor: [heard_the_hum] }
          - { narrate: "A low crystalline hum rises as you enter." }
          - { schedule_effect: { effect: cavern_glow, ticks: 30 } }
```

The vocabulary is exactly what already exists (`set_flags`, `narrate`, `apply_effect`,
`give_item`, `start_quest`, `adjust_reputation`, `emit_event`) plus a couple of new world-safe
ones. No new evaluator — `TriggerService` is a thin dispatcher over the two registries we
already have.

### 3.4 Area / spawn controllers (Tier 2, `wishlist.md` "dynamic area behaviors")

A per-`area_id` controller behind the feature-registration pattern, driven by the scheduler:
respawn policy (gradual / waves / depleted-stays-depleted), ambient-event emission (fires §3.3
triggers on rooms in the area), and zone-climate binding (see §5 weather). Swappable per area,
not a hardcoded global timer.

---

## 4. Custom DSL vs. Lua binding — the decision

**Recommendation: a small data-expressed DSL *if and when* needed (Phase B); never Lua.**

### Why not Lua (or any embedded general-purpose interpreter)

1. **It breaks the determinism/replay invariant.** The engine's correctness model is
   seedable `GameRng` + audit-log-as-source-of-truth + deterministic replay
   (`engine_core.md` §3.6, session-replay tooling exists). Arbitrary Lua can call `os.time`,
   `math.random`, do I/O, and hold non-persisted coroutine state — none of which replays. To
   make Lua safe you'd force every Lua effect back through the audited side-effect path… at
   which point Lua bought nothing over calling the registry directly.
2. **It's a code-execution surface across the content boundary.** `wishlist.md`'s
   engine/content-separation plan wants content (world YAML, and *any* scripting) to load from
   a **separate, validated** repo through a clean boundary. Untrusted Lua from a content repo
   is RCE; a declarative model where content can only *name* registered primitives is
   inherently sandboxed and validatable by `lorecraft.tools.validators`.
3. **It violates the tier boundary and tooling.** `engine/` may not depend on features/web and
   is covered by basedpyright + deterministic pytest. A Lua binding (lupa/LuaJIT) is a heavy
   C-extension dependency, opaque to the type checker and the test suite, and its callback
   surface would either be anemic or expose the whole repo/service layer.
4. **Paused-coroutine state doesn't survive restart.** All engine timing is DB-backed and
   restart-resumable (`SchedulerService`, `MobileRouteState`). Lua's `yield`-based pausing
   (Evennia's model) is lost on reload — `wishlist.md` already flags this. The
   scheduler+flags model persists by construction.
5. **It targets an audience Lorecraft doesn't have.** Lua/MobProg's whole value is
   *in-game-editable, non-programmer builders*. Lorecraft's builders use web forms + YAML
   import/export and version control. There's no telnet OLC and no stated demand for
   in-game code editing.

### Why a small DSL — but only later

- It's the **natural evolution of what exists**, not a new paradigm. Builders already author
  `when`/`do` structures. A DSL just adds *sequencing, guards, and a few control constructs*
  (`sequence`, `selector`, `if`, `repeat`, `random-choice`) — i.e. a **behavior tree / rule
  grammar expressed in YAML**, interpreted by a small deterministic tree-walker whose leaves
  are the existing condition predicates and side-effect handlers.
- It **stays data**: loads through the same validated YAML boundary, so the
  engine/content-repo split stays possible. It's typable (a Pydantic/`TypedDict` AST),
  testable (pure functions over `WorldContext`), and deterministic (`ctx.rng` only).
- The interpreter is ~200 lines because it **owns no primitives** — every leaf is already
  registered. Contrast a Lua binding, which is a permanent dependency + sandbox-maintenance
  burden.

### The honest trigger for Phase B

Per `wishlist.md`'s own guidance: **hold the language decision; watch for YAML pain.** Build
Phase A (§3) first. If authoring the roadmap_world behaviors in declarative `when`/`do`
triggers starts producing copy-pasted, hard-to-express-conditionally YAML — *that's* the
signal to add the behavior-tree grammar (Phase B). Not before.

### If a language is ever unavoidable, prefer Python-subset over Lua

Should Phase B's data-DSL genuinely hit a wall (unlikely for this content style), evaluate a
**sandboxed Python-subset** (`asteval` / a `RestrictedPython` expression layer) *for pure
expressions only* (computing a value/condition), never for effectful control flow — because it
stays in-ecosystem for typing/testing and can be pinned to deterministic builtins. Lua would
only win for an in-game-editable non-Python builder community, which is an explicit non-goal
today.

---

## 5. The prompt's examples, mapped to mechanism

Everything below is **declarative YAML over Phase-A primitives** — no language required.

| Example | How it's built |
|---------|----------------|
| **NPC patrol a zone / room list** | `behavior: {mode: patrol, route: [...]}` → `MobileRouteService` + NPC `RouteHooks`. |
| **NPC wander randomly** | `behavior: {mode: wander, area: sewers}` → agency-loop picks `rng.choice` of adjacent rooms in `area_id`. |
| **NPC chats with other NPCs / players** | agency-loop `mode: social` emits `narrate_room` banter on a cadence; player-directed lines reuse dialogue. |
| **NPC hunts a player by trait/mark/alignment** | `mode: hunt` reads co-located players' reputation/marks/traits via existing repos; acts (block/flee/summon/threaten). Damage-resolution defers to combat; non-lethal reactions don't. |
| **NPC reacts to attribute/mark/alignment** | §3.3 trigger `on: player_entered, when: {player_has_mark: outlaw}, do: [...]`. |
| **NPC guard / attack** | `mode: guard`; "attack" that deals damage is the one piece gated on the (deliberately deferred) combat system — everything up to the swing works now. |
| **loot-dropper / item-stealer / recycler** | agency-loop actions over `item_location` + existing `loot_table`. |
| **shopkeeper / quest-giver** | already shipped (shop + dialogue + quests); AI loop only adds proactive idle behavior. |
| **Weather events by season, traveling zone→zone** | extend `features/weather`: per-`area_id` climate tables (weather already rolls per-season in `weather/handlers.py:15`); a scheduler job propagates a front from area to adjacent area over N ticks — a `MobileRouteService`-style state machine whose "position" is which zones are currently under the front. Fires §3.3 room triggers for arrival narration. |
| **Room/item trigger starts a narrative script / enqueues effects** | §3.3 `triggers: [{on: player_entered, do: [narrate, schedule_effect, start_quest]}]`. "Enqueue effects" = `SchedulerService.schedule` / `EffectService.apply`. |
| **Magic container that buffs/degrades/curses contained items** | new §3.3 trigger events `item_stored` / `item_removed` on containers (containers already exist as `Item.capacity` + `features/containers`). `on: item_stored, do: [{apply_effect_to_item: {effect: blessing}}]`; degradation over time = an `ActiveEffect` with `entity_type="item"` whose `on_expire` writes durability/quality via the item component system. Reuses `EffectService` generically — **no new timer**. |

---

## 6. Phased roadmap

> **Status — Phase A COMPLETE (2026-07-10, v0.57.0–v0.70.0).** All of A0–A6 plus the acceptance
> harness are implemented, tested, and wired into the running game. Governance lives in
> `engine/scripting/` (vocabulary/catalog/validator/triggers); the actor-less `WorldContext` in
> `engine/game/`; the agency loop, weather fronts, and spawn controllers in `features/npc_ai`,
> `features/weather`, `features/spawns`. Authoring reference: **`docs/scripting_api.md`** (generated).
> Acceptance: `tests/unit/test_phase_a_acceptance.py`. Phase B (a behavior-tree DSL) remains
> deferred until YAML authoring proves painful.

**Phase A — Autonomy primitives (foundation; no language).** *This is the whole unlock.*
- A0. **Vocabulary governance foundation (precedes A2, §8).** Descriptor-carrying condition/
  effect registry (name / typed-params / subject / reads-or-writes / category / doc /
  **capability-signature** — no aliases); the generated catalog **plus an auto-generated
  builder-guide scripting API doc** (`lorecraft world vocabulary` + admin page + regenerated
  Appendix B + `docs/scripting_api.md`), kept honest by a **CI drift-check** and a matching
  `AGENTS.md` "regenerate on registration change" rule; registration-time exact-collision error
  + CI signature-overlap warning; author-time fail-closed linter at load + CI (runtime stays
  fail-open; editor-LSP / webui-builder surfaces deferred to Phase 3/4); hard-rename of the
  existing drifted names to the §8.4 convention in place (code + tests + the ~7 uses in the one
  in-repo `world.yaml`; **no aliases** — §8.6). The self-check that keeps the vocabulary
  consistent and non-duplicative as everything else registers into it.
- A1. `WorldContext` extraction + split side-effects into world-safe/actor-only (§3.1). **Gates everything.**
- A2. `TriggerService` + `on_<event>` binding on Room/Item/NPC/Exit; `triggers` YAML schema + validator (§3.3).
- A3. `features/npc_ai` agency loop with `patrol` (via `MobileRouteService` NPC hooks) + `wander` modes; wake `NPC.behavior` (§3.2). Emits `NPC_MOVED`.
- A4. Container effect-triggers + item-targeted `ActiveEffect` (magic-container example) (§5).
- A5. Per-`area_id` climate binding + traveling-weather propagation (§5).
- A6. Area spawn/respawn controllers behind the feature pattern (§3.4).

**Phase B — Behavior-tree / rule DSL (only if A's YAML gets painful).**
- B1. A typed YAML AST (`sequence`/`selector`/`if`/`repeat`/`random`) + a deterministic
  tree-walking interpreter over Phase-A conditions & effects.
- B2. Migrate the hairiest Phase-A behaviors to it; keep flat `when`/`do` as the common case.

**Phase C — Embedded evaluator (probably never; revisit only under real pressure).**
- Sandboxed Python-subset for *pure expressions* only, deterministic builtins. Not Lua.

**Sequencing note:** Phase A slots into the `roadmap_world.md` "Blocked Items" — it's the
engine work those blocks wait on. Per `AGENTS.md` "foundation before features", A1 (the
`WorldContext` split) is the clean seam worth doing carefully before any content leans on it. A0 (vocabulary governance, §8) precedes A2: the naming convention and self-describing catalog must exist before new predicates/effects are registered, or the drift bakes in permanently.

---

## 7. Risks & guard rails

- **Determinism.** Every autonomous roll through `GameRng`; audit every state-changing
  autonomous action so replay stays faithful. Add a simulation test that replays a scripted
  autonomous run and diffs the audit log (the harness exists in `tests/simulation/`).
- **Tick cost.** The agency loop and trigger sweep run on the world clock. Keep per-tick work
  O(active NPCs / bound triggers), reuse the `SCHEDULED_JOB_DUE` batching seam, and lean on the
  existing scheduler rather than a second timer. `roadmap_world.md`'s perf notes and the
  deferred scheduler-commit-batching (`wishlist.md`) are the levers if it bites.
- **Fail-open discipline.** Unknown trigger events, conditions, and effects must ignore-not-
  crash, consistent with the current registries — content forward-compat depends on it.
- **Tier boundary.** `WorldContext` and `TriggerService` are the only new **engine** pieces;
  agency modes, spawn/area controllers, and climate live in **features**. Enforced by
  `tests/unit/test_tier_boundaries.py`.
- **Content-repo readiness.** Design the `triggers`/`behavior` YAML and its loader as if the
  content repo were already external (`wishlist.md`'s engine/content-split constraint), so the
  eventual split doesn't have to retrofit the scripting surface.

---

---

## 8. Vocabulary governance & auto-discovery — the "language" is a designed API

The registries **are** the language; the registered strings **are** the API; today **nothing
curates them** (evidence in §2 and the drift audit: three naming schemes for flags —
`set_flags`/`flag_set`/`required_flags` — two names for the same reputation check —
`min_reputation` *and* `reputation_at_least` — and two param encodings). This section makes the
vocabulary a **designed, self-describing, auto-discoverable** API, and uses that
self-description as a **duplication detector**. It is sprint **A0** (§6): it precedes every
sprint that registers a new predicate or effect.

### 8.1 Self-describing registration (descriptors, not bare strings)

Replace `register("name", fn)` with a descriptor that carries everything the catalog, the
linter, and the dedup checker need:

```python
@dataclass(frozen=True)
class ConditionSpec:
    name: str                       # THE canonical name — one per capability, no aliases (§8.6)
    params: type                    # typed param schema (TypedDict/pydantic) — validated at load
    subject: Subject                # SELF | ACTOR | TARGET — which role it reads
    reads: tuple[str, ...]          # feature/state it consults, e.g. ("reputation",)
    category: str                   # catalog grouping: "social" | "world_clock" | "flags" | …
    doc: str                        # one-line human description
    capability: CapabilitySig       # (subject, domain, attribute, comparator) — the dedup key
    fn: ConditionHandler
```

An `EffectSpec` mirrors it with `writes`/`target`/`mutation` in place of `reads`/`comparator`.
The extra fields are cheap to write once and pay for the next three subsections.

### 8.2 Auto-discovery: the catalog is generated, single source of truth

Because every entry self-describes, the engine **emits** the reference — nothing is
hand-maintained, nothing can drift from the code:

- `lorecraft world vocabulary [--category X] [--json]` — the authoritative catalog.
- An admin "Scripting vocabulary" page.
- Appendix B of this doc, regenerated on build (so the doc physically cannot lie).
- A builder-facing **scripting API reference** (`docs/scripting_api.md`) rendered from the same
  descriptors — grouped by category, each entry showing name / params / subject / reads-writes /
  doc / example. A *generated* chapter of the builder guide, never hand-written.
- The same catalog feeds the author-time linter (§8.5) and, later, editor autocomplete for
  world YAML.

This is the direct answer to "how do I know what the language is, exactly?" — **you ask the
engine, and it tells you from the code.**

**Keeping it honest (staleness is the enemy of a generated doc).** Because the reference is
generated, a **CI drift-check** regenerates it and *fails the build if the committed copy
differs* — that automation, not human diligence, is the real guarantee it never goes stale.
`AGENTS.md` gets the matching human-facing rule: regenerate the catalog (`make scripting-docs`)
in the **same commit** that changes any registration — exactly the shape of the existing
"run `make ai-graph` after code changes" rule. Both the CI check and the `AGENTS.md` rule are
A0.3 deliverables, landing *with* the generator so they never reference a tool that doesn't
exist yet.

### 8.3 Duplication detection — the catalog as a self-check against re-invention

**This is a primary design goal, not a side benefit.** A self-describing registry is a
guardrail against the single most common failure mode when many contributors — human *or AI* —
extend a shared vocabulary independently: **silently re-adding functionality that already
exists under a different name.** `min_reputation` and `reputation_at_least` are exactly that
failure, already in the tree. As LLM-assisted authoring grows (`wishlist.md`), an agent that
can't *see* the existing vocabulary will confidently invent a synonym every time.

Three enforcement points turn self-description into an active check:

- **Registration time (hard error):** an exact-name collision fails loudly instead of today's
  silent overwrite. Two features can't both quietly claim `npc_present`.
- **Build / CI (warning → review gate):** **capability-signature overlap across *different*
  names** is flagged. Two conditions with signature `(actor, reputation, standing, at_least)`
  →  *"likely duplicate of `reputation_at_least` — alias or remove."* Two effects that write
  the same `(target, field)` → the same. This is the mechanism that catches a near-duplicate
  **before it lands**, whether a person or an agent proposed it.
- **Catalog presentation:** entries group by category *and* by capability signature, so
  near-duplicates sit adjacent — anyone (or any agent) scanning the catalog to "add a
  reputation check" meets the existing one first and reuses it.

The payoff compounds with the engine/content-repo split: a bounded, introspectable,
dedup-checked vocabulary is far safer to hand to an LLM building content than an open-ended
string space where every typo or synonym silently forks the language. In effect the catalog
does for *content vocabulary* what Graphify does for *code structure* — makes overlap visible
so it can be discouraged.

### 8.4 Naming convention (normative)

- **Subjects are roles, not entity types:** `self` (the entity the script is attached to),
  `actor` (the triggering party, usually the player), `target` (explicit). Kill the
  `player_`/`npc_`/`object_` subject-prefix soup.
- **Predicate shape:** `<subject>_<attribute>_<comparator>`, comparator drawn from a **fixed
  set** — `at_least | below | is | has | lacks`. Retire `min_`/`max_`/`required_`/`forbidden_`.
- **Effects:** imperative verb + **explicit** `target` (`apply_effect: {target: actor, …}`);
  never an implicit actor — the `WorldContext` split (§3.1) enforces this anyway.
- **Params:** structured maps only; the `"name:param"` colon-string is legacy, alias-only.
- **One flat namespace with collision detection** (feature-prefixed only if flatness is ever
  shown to collide in practice) — decided once at A0, not per feature.

### 8.5 Fail-closed authoring, fail-open runtime

- **Author time (fail-closed):** the load-time linter validates every `when:`/`do:` name *and*
  param shape against the current catalog; an unknown name or bad param is a **content error
  surfaced where it was authored.**
- **Runtime (fail-open):** unknown names are still ignored during execution, preserving
  forward-compatibility (an old engine reading newer content). The linter is precisely what
  makes fail-open *safe* — typos are caught before they ship, so silent no-ops stop hiding
  bugs.

**Where the check surfaces** is a spectrum over one shared validator. The **load-time + CI**
pass is the A0.4 baseline — it catches everything before content ships, and needs no editor
integration. Richer, more immediate surfaces are deferred UX that reuse the *same* catalog and
validator: an **editor LSP** (neovim / VS Code inline squiggles on `world.yaml` as you type)
and **inline validation in the webui/admin builder** form. Worth building around **Phase 3/4**,
noted here so the validator is designed as a reusable library from day one, not welded into the
load path.

### 8.6 Canonicalizing the existing drift — hard rename, no migration aliases

There is effectively **no authored content to protect**, so A0 hard-renames to the convention
in place rather than carrying deprecated aliases. The audit bears this out: the true synonym
pairs (`min_reputation`↔`reputation_at_least`, the `flag_set`/`required_flags`/`set_flags`
sprawl) live **only in code registration and tests**, which we own; a scan of
`world_content/*.yaml` found just a handful of content-facing uses (`set_flags` ×4,
`room_visited`, `moon_phase_is`, plus the already-canonical `start_quest`). The single in-repo
world (`world_content/world.yaml`) is fully editable today — the engine/content-repo split
(`wishlist.md`) hasn't happened.

So A0 renames to the §8.4 canonical forms **in one atomic commit** — the registrations, the
tests, and the ~7 content occurrences — and does **not** ship legacy back-compat aliases. This
is strictly better than migration-aliasing: we enter the content-repo era with a clean,
convention-conformant vocabulary and zero deprecated cruft. Aliasing would only earn its keep
once content is *frozen* or lives in a repo we don't control — neither is true now, and doing
the rename *before* autonomy (A2–A6) multiplies the surface is the cheapest it will ever be.

**No aliases at all in the scripting vocabulary** — one canonical name per capability, full
stop. This is deliberate: an alias is just a second name for one thing, which is exactly the
drift/duplication we're eliminating, and it would blunt the dedup check (§8.3) by making "two
names for one capability" sometimes-legal. With aliases banned, the rule is absolute — *any*
two names resolving to one capability signature is a defect, no exceptions. (This is distinct
from the separate, existing **command-verb** alias mechanism — `look`/`l`, `examine`/`x` — which
is player-facing CLI ergonomics on the command parser, untouched by this and not part of the
scripting vocabulary.)

**Execution note — A0.5 as built (safe sequencing over one big-bang).** The "one atomic
commit" ideal above assumed all the drift is code/test-only. One class isn't: `set_flags`
appears in `world_content/world.yaml`, and the runtime is **fail-open** — a *missed* rename of a
content-facing name silently stops firing instead of erroring, which for a quest flag is a
gameplay bug with no trace. So the rename splits by safety:

- **Reputation pair → `actor_reputation_at_least` (A0.5, done).** Fully content-free (only the
  reputation feature + tests referenced `min_reputation`/`reputation_at_least`), so it renames
  cleanly now. The command and dialogue registries both register the one canonical name (a
  legal, non-colliding "same predicate, two surfaces" — enabled by the catalog's idempotent
  same-capability registration; see `Vocabulary.register`).
- **Flag family → `actor_has_flag`/`actor_lacks_flag` (Sprint 69, done).** The condition drift
  (`flag_set`/`flag_not_set` on the command surface, `required_flags`/`forbidden_flags` on the
  dialogue surface) collapsed to the one §8.4 canonical name per capability, registered on both
  surfaces (idempotent same-capability, like the reputation pair). The catalog's overlap report
  is now empty. Done safely *after* A2 wired the §8.5 validator into the load path, so any missed
  rename would surface as a fail-closed load error — though the audit held: there were zero uses
  in `world_content/`. Intentionally left as-is: the `set_flags`/`clear_flags` **effects** (already
  imperative-verb form, no capability duplicate) and the separate quest-stage condition registry
  (`{type: flag_set, …}`, not part of the `when:`/`do:` catalog).
- **Feature-enable-time descriptors → follow-up.** Registrations that run in a feature's
  `register()` (reputation, follow, npc_memory, …) only enter the generated catalog once the
  doc generator *enables* features rather than merely importing them; until then A0.5's
  reputation rename stays on bare `register`. Landing that (and migrating those registrations to
  `register_spec`) is tracked as a small follow-up so `docs/scripting_api.md` becomes complete.

---

## Appendix A — Authoring examples (the Phase-A surface)

What a builder actually writes. Two new authoring surfaces, both declarative YAML: a
**`behavior:`** block on an NPC (its proactive per-tick loop) and **`triggers:`** blocks
(reactive `on`/`when`/`do` hooks) attachable to any NPC, room, item, or exit. `when:` clauses
are the condition registries; `do:` actions are the side-effect registry run against
`WorldContext` (§3.1). One synthetic event does most of the work: **`encounter`**, fired when
an NPC and a player become co-located from *either* direction (the NPC's `wander`/`patrol`
walks in → `NPC_MOVED`; or a player walks into the NPC's room → `PLAYER_MOVED`).

### A.1 Guard patrols a route, reacts on conditions

```yaml
npcs:
  - id: brass_sentinel
    name: Brass Sentinel
    home_room_id: grand_plaza
    dialogue_tree_id: sentinel_dialogue
    behavior:
      mode: patrol
      route: [grand_plaza, market_row_east, smithy_district, market_row_west]
      dwell_ticks: 3            # pause at each stop
      loop: true               # circular beat (reverses:false + loop:true in MobileRouteService)
      triggers:
        - on: encounter
          when: { actor_reputation_below: { faction: city_watch, value: -50 } }
          do:
            - { narrate_room: "The Brass Sentinel levels its halberd at {actor}. \"Halt.\"" }
            - { apply_effect: { target: actor, effect: watched, ticks: 20 } }
        - on: encounter
          when: { chance: 0.25, actor_reputation_at_least: { faction: city_watch, value: 0 } }
          do:
            - { narrate_to_actor: "The Sentinel gives you a crisp brass-jointed salute." }
```

`mode: patrol` wires a `MobileRouteService` route with NPC `RouteHooks` (`on_arrive` moves
`NPC.current_room_id`, broadcasts arrive/depart — first real emitter of `NPC_MOVED`). Triggers
evaluate in order; first matching `do:` runs. `chance` rolls through `GameRng` (replay-safe).

### A.2 Wanderer offers maps to anyone it meets (once each)

```yaml
npcs:
  - id: cartographer_wren
    name: Wren the Cartographer
    home_room_id: whispering_clearing
    dialogue_tree_id: wren_map_offer
    behavior:
      mode: wander
      area: whisperwood_floor     # random adjacency-valid room within this area_id
      move_every: 4
      triggers:
        - on: encounter
          when: { actor_lacks_flag: got_wren_map }
          do:
            - { start_dialogue: wren_map_offer }   # NPC opens the offer; player accepts/declines
```

The `wren_map_offer` tree (dialogue + `give_item`/`set_flags` side-effects) is **shipped
today** — unchanged. `mode: wander` is the agency loop picking `rng.choice` over the current
room's exits filtered to `area`, every `move_every` ticks.

### A.3 Zone-wanderer that attacks players with a given trait/mark

```yaml
npcs:
  - id: thornstalker
    name: The Thornstalker
    home_room_id: shadow_thicket
    behavior:
      mode: wander
      area: whisperwood_floor
      move_every: 2
      triggers:
        - on: encounter
          when:
            any:                              # one-level OR-group (see vocabulary note)
              - { actor_has_mark: poacher }
              - { actor_has_trait: reeks_of_iron }
              - { actor_reputation_below: { faction: fey, value: -75 } }
          do:
            - { narrate_room: "Thorns bristle along its spine. It lunges at {actor}!" }
            - { start_combat: { target: actor, stance: aggressive } }   # combat-gated, see A.5
```

Detection and reaction are pure Phase A. `start_combat` that **deals damage is NOT** — see
A.5. There is **no alignment axis**; "evil" is authored as a reputation threshold against the
relevant faction, not a morality check.

### A.4 Weather: roll for storms, time them, rotate through zones

Authored as a weather/area controller (Tier-2 feature on the scheduler), not an NPC.

```yaml
weather:
  climates:                            # per-zone base tables (generalizes today's global roll)
    whisperwood:        { calm: 0.6, mist: 0.3, storm: 0.1 }
    port_veridian:      { calm: 0.5, fog: 0.2, storm: 0.3 }
    cogsworth_undercity: { indoor: true }        # never rolls weather

  storms:
    fey_tempest:
      trigger: { on: hour_changed, when: { chance: 0.05, season: [spring, autumn] } }
      duration_ticks: { min: 30, max: 90 }       # rng-rolled per occurrence
      path: [whisperwood, port_veridian]         # front rotates through these zones in order
      travel_ticks: 20                           # time to move the front zone->zone
      while_active:
        room_effect: storm_lashed                # ActiveEffect on every room in the current zone
        on_enter_zone: { narrate_zone: "The sky darkens; a fey tempest rolls in." }
        on_leave_zone: { narrate_zone: "The storm moves on, leaving dripping silence." }

effects:
  storm_lashed:
    entity_type: room
    modifiers:
      - { stat: travel_speed, mult: 0.5 }
      - { stat: perception,   add: -2 }
    on_apply:  { narrate_room: "Rain hammers down; visibility drops." }
    on_expire: { narrate_room: "The rain eases." }
```

Lifecycle: the controller rolls on `HOUR_CHANGED` (`chance` via `GameRng`); on a hit it rolls
`duration_ticks`, applies `storm_lashed` to zone 1's rooms via
`EffectService.apply(entity_type="room", …)`, and schedules two DB-backed jobs — *move front*
after `travel_ticks` and *expire* at the rolled end-epoch. Same waypoint/dwell/travel shape as
`MobileRouteService`, "position" = which zone is under the front. Restart-safe (scheduler jobs
persist); replay-faithful (all rolls on `GameRng`). Use `rooms: [...]` instead of a zone list
in `path` for room-granular storms.

### A.5 What resolves at end of the Phase-A sprints (and what doesn't)

Directly answering "is this exact syntax available when Phase A ships?" — **yes for the
authoring surface, with three caveats:**

| Demonstrated construct | End of Phase A? | Note |
|---|---|---|
| `behavior: {mode: patrol/wander …}`, `encounter`/`player_entered`/`tick` triggers, `when`/`do` | Yes | This *is* Phase A (A2 + A3). |
| `narrate_room` / `narrate_to_actor` / `narrate_zone`, `apply_effect`, `chance`, `season`, `once` | Yes | New world-safe effects/conditions on the existing registries (A1/A2/A5). |
| `give_item`, `set_flags`, `start_dialogue`, `adjust_reputation` fired autonomously | Yes | Handlers ship today; Phase A only widens them to run without a player actor (A1). |
| Storm roll → duration → traveling front → room effects (A.4 in full) | Yes | A5 + reused `EffectService`/scheduler. |
| `actor_has_trait` / `actor_has_mark` / `actor_reputation_below` conditions | Yes* | *Assumes the `traits`/`marks`/`reputation` features are **enabled in the world**; each needs a small world-context predicate registered under A2. |
| `any:` / `all:` boolean groups (A.3) | One level only | A single-level `any`/`all` is cheap and in-scope for A2. **Arbitrarily nested** boolean logic is exactly the Phase-B (behavior-tree grammar) line — don't author deep nesting against Phase A. |
| `start_combat` that **deals damage** (A.3's payoff) | No | Combat is deliberately set aside (`wishlist.md`). Phase A ships `start_combat` as a **registered stub** plus the *non-lethal* seam (`emit_event: npc_hostile`, threaten/flee/subdue narration). The wanderer detects the marked player and reacts now; the actual swing waits for the combat sprint. |

Two smaller honesty notes: (1) the exact key spellings here (`narrate_to_actor` vs `narrate`,
etc.) are the **proposal** — the final vocabulary firms up during A2 and this table is the
spec to firm it against; (2) "alignment" is not a thing — moral reactions are reputation
thresholds.

## Appendix B — Proposed vocabulary

The authoring API the examples imply. This is the surface A2 should nail down.

**Trigger events (`on:`)** — `encounter`, `player_entered`, `player_left`, `npc_arrived`
(A2/A3); `item_stored`, `item_removed` (A4, container/magic-chest); `tick` (periodic, A2).

**Conditions (`when:` — AND-ed; wrap in `any:`/`all:` for one level of OR/AND):**

| Condition | Param | Reads | Status |
|---|---|---|---|
| `actor_has_flag` / `actor_lacks_flag` | flag name | `Player.flags` | new predicate (trivial) |
| `actor_has_trait` | trait key | `traits` feature | needs feature enabled |
| `actor_has_mark` | mark key | `marks` feature | needs feature enabled |
| `actor_attribute_below` / `_at_least` | `{attr, value}` | character attributes | needs attributes feature |
| `actor_reputation_below` / `_at_least` | `{faction, value}` | `reputation` feature | needs feature enabled |
| `chance` | `0.0-1.0` | `GameRng` | new |
| `season` | list of seasons | `WorldClock` | new |
| `time_between` | `[start_hour, end_hour]` | `WorldClock` | new (day/night gating) |
| `once` | `true` | auto-managed flag guard | new |

**Effects (`do:`):**

| Effect | Param | Mechanism | Status |
|---|---|---|---|
| `narrate_to_actor` | text | `manager.send_to_player` | new (world-safe) |
| `narrate_room` | `{room?, text}` | `broadcast_to_room` | new (world-safe) |
| `narrate_zone` | text | broadcast to `area_id` rooms | new (A5) |
| `give_item` | item id | `SideEffectRegistry` | shipped → widened to `WorldContext` |
| `set_flag_on_actor` / `clear_flag_on_actor` | flag | `Player.flags` | shipped → widened |
| `adjust_reputation` | `{faction, delta}` | `reputation` feature | shipped → widened |
| `apply_effect` | `{target: actor\|room\|item, effect, ticks}` | `EffectService` | shipped mechanism, new binding |
| `start_dialogue` | tree id | dialogue walker | new autonomous-initiate wrapper |
| `emit_event` | `{type, …}` | `EventBus` | new |
| `schedule` | `{after_ticks, do: [...]}` | `SchedulerService` | new binding |
| `start_combat` | `{target, stance}` | combat system | **stub until combat sprint** |

**NPC behavior modes (`behavior.mode`):** `patrol` `{route, dwell_ticks, loop}` →
`MobileRouteService` (A3); `wander` `{area\|route, move_every}` → agency loop + `GameRng` (A3);
`guard`/`hunt`/`flee` → A3 reaction only, damage combat-gated; `shopkeeper`/`quest_giver` →
existing dialogue/shop, AI adds only idle banter (later).

---

*Written 2026-07-09 (examples appendix 2026-07-10). A design proposal, not a committed
roadmap item — graduates into `roadmap.md` only when scoped and scheduled.*
