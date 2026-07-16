# Combat System — Design (Scheduled Intent Combat)

> **Status:** Active implementation, 2026-07-14. Merges three source proposals (v2 framework, MUD
> deep-dive, mechanics deep-dive) into one architecture. **Supersedes the tick-based
> `combat_system.md`** where they conflict (see §0). Combat is a **supporting** system
> per `wishlist.md` — one of several ways to resolve an encounter (stealth/persuasion/bribery/
> flee are first-class), often avoidable. Ships as `features/combat/`.

---

## 0. Relationship to the superseded `combat_system.md`

`combat_system.md` describes **tick-based combat**: combatants act on a shared world-clock
rhythm (`speed` ticks between actions), one `combat_tick` job re-evaluates every ready
combatant. This document proposes **Scheduled Intent Combat** instead: each *action* schedules
its own resolution via an individual wind-up + recovery timer; inactive actors have no
scheduled work at all. The two are mutually exclusive core-timing models. **Adoption: Scheduled
Intent** (rationale in §2). The prior doc's still-valid pieces are retained — avoidance-first
framing, rules-as-fail-closed-gate, weapon/armor as effect descriptors, the
`SCHEDULED_JOB_DUE` + `job_type` convention, seeded-`rng` determinism, participation-based
credit. Its `CombatSession` model (tick bookkeeping in a JSON blob) is replaced by the
encounter graph (§4). NPC behavior stays deliberately modest: existing `NPC.behavior` and optional
`NPC.ai.combat_role` provide qualitative cues, not a Behavior Tree engine or tactical planner.

---

## 1. Guiding principles (from v2, with rationale from the deep-dives)

- **Continuous but discrete** — time flows continuously; state changes only through
  individually scheduled, atomic actions. Borrowed from Iron Realms *balance/equilibrium*
  (individual readiness) rather than Diku global pulses, which produce synchronized bursts and
  re-evaluate idle combatants needlessly.
- **Intent-first** — every action (player command, NPC decision, auto-attack, trap, script,
  admin) becomes one `CombatActionIntent` through one pipeline. No privileged internal path.
- **Optional auto-attacks** — a *policy-generated intent*, never a heartbeat that deducts HP
  directly. Preserves Diku accessibility (combat never stalls) without making escape,
  stealth, or dialogue-mid-combat second-class.
- **Wind-up + recovery split** — modest wind-up (immediate acknowledgment + counterplay
  window) followed by larger recovery (paces the next action). All-before = laggy + interrupts
  too strong; all-after = instant hits + no defense + first-command-wins races.
- **No typing-speed advantage** — one queued action; a small server-side decision window
  (100–200 ms) with attribute-based tie-breakers, not packet arrival; idempotency keys; rate
  limits. This keeps combat readable even before any future PvP work exists.
- **Encounter graph, not boolean flags** — `in_combat`/`target_id` collapses the moment you add
  guarding, allied assistance, downed participants, or audit-visible contribution tracking.
- **Rules own policy, service owns mechanics** — combat submits questions to the rules engine;
  no `if room.safe … elif target.pvp …` forest in the service.
- **Immutable resolutions, narration separated from mechanics** — the resolver returns a frozen
  `CombatResolution`; the service applies it transactionally; the narrator renders it. Enables
  replay, audit, simulation, and per-observer prose.
- **Data-driven content** — actions/weapons/effects authored as YAML that *selects registered
  mechanical components* — not a programming language in YAML.
- **Auditable & replayable** — every resolution records its random trace and ruleset version.

## Summary of key decisions

Scheduled Intent Combat · optional policy-driven auto-attacks · individual per-action recovery
timers (no global round) · wind-up + recovery split · encounter aggregate
(Encounter/Participant/Relationship) with explicit hostile/supportive edges · double validation
(admission + resolution) · rules engine separated from service (with obligations) · immutable
`CombatResolution` objects, narration decoupled from mechanics · data-driven action YAML
selecting registered calculators/resolvers · lightweight ranged/vantage semantics instead of
formation or near/far band systems · bounded single-window reactions · stances + policies ·
qualitative NPC role and threat cues · downed/defeat states with non-lethal outcomes · party
assistance as participation metadata · durable scheduler jobs with idempotency, readiness derived
from `primary_ready_at` · ruleset/resolver versioning · simulation harness built early.

---

## 2. Why Scheduled Intent (paradigm survey)

| Model | Verdict for Lorecraft |
|---|---|
| Diku pulse auto-combat | Accessible but players feel like spectators; global pulse re-scans idle actors; hurts non-lethal resolution. **Borrow accessibility only** (optional auto-attack). |
| Strict turn-based | Legible/testable but one idle player stalls a shared persistent room. **No.** |
| Simultaneous round planning | Fair under latency, good for arenas. **Keep as an optional mode (Phase 4), not the default.** |
| Iron Realms balance/equilibrium | Fluid individual readiness — **adopt the individual-recovery core**, but not the affliction/curing automation arms race. |
| Discworld tactics/wimpy | **Adopt via stances + policies**, not a server-side scripting language. |

Fit to engine: `SchedulerService` schedules per-action resolutions/effect ticks/expirations;
`EventBus` makes combat reactive/auditable; the transaction/unit-of-work layer keeps mutations
atomic; `MeterService` already provides generic HP/stamina meters; the modifier resolver
already derives stats; seeded `rng` + `skill_check` give determinism. Combat is where these
boundaries earn their keep.

---

## 3. The action lifecycle & timing

Phases: `submitted → validated → queued → wind-up → resolving → recovery → ready`.

Channels: begin with **one primary channel + reactions**. Add utility/movement channels only
if playtesting demands. (Four independent "balances" from day one = excessive parallelism.)

Initial tuning ranges (live-tunable, not constants):

| Class | Wind-up | Recovery |
|---|---:|---:|
| Fast | 0–200 ms | 900–1500 ms |
| Normal | 250–500 ms | 1500–2500 ms |
| Heavy | 600–1200 ms | 2200–4000 ms |
| Ritual | multi-stage, 3–15 s total |

Pacing note: 2–3 s effective base cadence lets players read and choose; tune via
the scheduler. Wind-up opens the reaction/interrupt window; recovery gates the next major
action; the player may queue exactly one next action during recovery.

---

## 4. Encounter graph (replaces `CombatSession`)

```text
CombatEncounter( id, location_id, state, started_at_game_time, started_at_real_time,
                 version, ruleset_id, combat_mode, last_hostile_action_at )
CombatParticipant( encounter_id, actor_id, side_id, joined_at, status,
                   primary_ready_at, reaction_ready_at, queued_action_id,
                   position, stance, threat, contribution )
CombatRelationship( source_id, target_id, hostility, engagement, visibility )
```

Multiple `side_id`s (players / town guards / bandits / summons / a neutral that joins late) —
never hard-coded team A vs B. **Encounter begins** when an action creates confirmed hostility.
**Encounter ends** when no hostile relationships remain / all sides disengage / all enemies
escaped, unreachable, or unengaged / inactivity timeout / a victory rule fires — **not** merely
because one actor's current target died. Readiness is **derived** (`primary_ready_at <= now`), so
recovery completion needs no DB write; schedule a job only when readiness must *do* something
(start a queued action, ask NPC AI, generate an auto-attack, send a "ready" nudge).

---

## 5. Range And Engagement — no formations

The active design deliberately avoids persistent near/far bands, party formations, and
advance/retreat/disengage verbs. They add state and UI burden without serving the current
exploration-first combat goals.

Combat stores only:

- `engaged` / `unengaged` participant position derived from active relationship edges.
- Hostile/supportive relationship edges, including `guarding` for protect-ally behavior.
- `action_range` on resolved actions, currently `engaged`, `ranged`, or `self`.

This supports the useful ranged cases: a player can `shoot <target>`, a bow or crossbow can be
audited as ranged, and authored content can later put a guard in a tower or a sniper-like NPC on
a vantage point. Ranged attacks do not use guard interception. If playtesting later proves a need
for cover or explicit vantage rules, add them as narrow action-admission/resolution checks rather
than a general formation system.

---

## 6. Action resolution pipeline & double validation

```text
parse intent → resolve refs → build CombatActionRequest → ADMISSION rules →
create/join encounter → calculate schedule → persist pending action → emit ActionStarted →
[due] load current state → RESOLUTION rules → calculate outcome → apply mutations atomically →
commit → emit domain events → render observations → schedule recovery-ready
```

**Admission** (command time): conscious? target visible? command allowed here? possesses weapon?
ability known? channel ready? target initially valid for the action range?
**Resolution** (execution time): still conscious? target still present/reachable? weapon
disarmed? interrupted? encounter ended? rule added during wind-up?
Never assume state held. Failed resolution yields a *reasoned outcome* —
`missed / cancelled / interrupted / retargeted / converted / partially_resolved` — not an
exception.

---

## 7. Rules engine (policy) — questions & obligations

Combat asks named questions of the existing rules engine (`engine/game/rules.py`), fail-closed:
`combat.action.admit`, `combat.action.resolve`, `combat.target.valid`,
`combat.damage.modify`, `combat.reaction.eligible`, `combat.escape.permitted`,
`combat.encounter.join`, `combat.death.resolve`, `combat.reward.eligible`. Future opt-in PvP
can add a `combat.pvp.permitted` rule when that work is active; it is not part of the current
NPC-first combat scope. Facts in, decision out:

```python
@dataclass(frozen=True)
class CombatActionFacts:
    actor_id: UUID; target_ids: tuple[UUID, ...]; encounter_id: UUID | None
    action_id: str; location_id: UUID; weapon_id: UUID | None
    tags: frozenset[str]; game_time: datetime

@dataclass(frozen=True)
class RuleDecision:
    allowed: bool
    reasons: tuple[Reason, ...] = ()
    modifiers: tuple[Modifier, ...] = ()
    obligations: tuple[Obligation, ...] = ()   # e.g. emit_crime: assault; alert_faction: city_watch
```

Obligations let a rule permit-with-consequence without the rule mutating the world directly.

---

## 8. Combat maths (boring core, interesting choices)

Opposed contest, single margin → outcome band (avoid separate hit + crit rolls):

```text
attack_score = skill + weapon accuracy + ability accuracy + situational + bounded variance
defense_score = defense skill + stance + shield/cover + situational + bounded variance
margin = attack_score - defense_score
  large-neg → miss | small-neg → glancing/defended | small-pos → hit |
  large-pos → strong hit | exceptional → critical
```

Implemented Sprint 88.2 keeps cover deliberately narrow: the resolver reads the encounter room and
adds only a target defense-score bonus. Default terrain bonuses apply to `forest`, `mountain`, and
`swamp`; authored cover comes from room flags (`combat_cover` or `combat_cover_defense_bonus`).
The resolution trace records the terrain, cover, and total environment bonus for audit/admin
inspection. This is not a range-band, formation, facing, or movement-position system.

Randomness: bounded/bell-shaped (`rng.randint(-10,10)+rng.randint(-10,10)`), through seeded
`ctx.rng` only. Damage via a **staged modifier stack** (base additions → multiplicative →
mitigation → post-mitigation → clamp), each modifier **naming its source** (auditability).
Armor: **hybrid bounded reduction** — flat `block` (adjusted by penetration) then a modest
`resistance_factor`, both capped so neither weak nor heavy hits become pathological.

Implementation note: the first Sprint 85 slice derives weapon and armor profiles from equipped
item descriptors (`category`, `slot`, `weight`, `quality`) and stores each resolved action's
random trace plus staged damage trace in `CombatResolutionRecord`.

Browser-state note: scheduled resolutions emit combat prose and structured `combat_update`
payloads with per-encounter sequence numbers. The browser stores the latest ordered state; a
dedicated combat panel/resync endpoint remains a later UI refinement.

---

## 9. Resources, status effects, wounds

Start with **health + stamina** — not six body resources. Stamina *gates choices*
(heavy actions cost more recovery <60%, disabled <20%, winded at 0), not an invisible penalty.
Don't give warriors a renamed mana bar.

Status effects have a formal lifecycle (`EffectInstance`: type, source_actor, source_action,
applied_at, expires_at, stacks, potency, tags, state) with hooks `on_apply /
on_action_admission / on_action_resolution / on_damage_received / on_movement / on_interval /
on_expire / on_remove`. **Duration = game-time timestamps** for world effects (persist the
game-time deadline for restart recovery) + real monotonic scheduling for near-term firing;
trigger-count durations only where authored ("expires after 3 primary actions", never "3
turns"). Effects are driven by the existing `engine/services/effects.py` + scheduler.

**Wounds** (bleeding, fractured arm, concussion…) persist past health recovery and impose
targeted consequences — a **later layer** (Phase 4), generated only on meaningful events, never
every hit.

---

## 10. Reactions & interrupts — strictly bounded

One action opens **one** reaction window; a reaction does **not** open another (no
parry→counter→riposte recursion). Types: block/dodge/parry/intercept/counterspell/brace/
opportunity attack/protect ally. Default reaction *policy* (`reaction defensive/conserve/
protect <ally>/manual`). Manual reactions only where wind-up is long and the UI clearly
announces the opening; ordinary attacks use auto-selected reactions.

## 11. Stances & policies (Discworld tactics/wimpy, tamed)

Stances: `balanced / aggressive / defensive / mobile` (offense/defense/escape trade-offs).
Policies: `autoattack on/off`, `autofollow`, `pursue`, `protect <char>`, `flee at <hp%>`,
`use reactions always/conserve/never`. **No arbitrary server-side combat scripts.**

## 12. Auto-attacks — policy-generated intents

```text
on ready: queued action? → run it
          elif autoattack policy on → create basic_attack intent
          else → remain ready
```

The generated intent goes through the **same** rules/transaction/audit/events/range/interrupt/
scheduler path as any action. NPCs pick an intent in the same slot a player's queued command
would occupy.

---

## 13. NPC combat behavior — qualitative, not a planner

> **Codebase reality:** do not add a Behavior Tree engine or a full tactical planner for normal
> NPC combat. The current implementation uses simple scheduled counter-intents plus qualitative
> combat-role cues.

Division of labor: **Rules** = *can I?* · **Service** = *do it* · **Content** = *what kind of NPC
is this?* NPCs should think only at decision points, never on a global combat tick. Bosses may
later override ordinary behavior with explicit scripted phases, but that should be content-specific
and registered by id, not a generic AI framework.

## 14. Threat / target selection — decaying attention

`attention[target] += damage`, decaying over time. The implementation stores qualitative cues
(`aware`, `watching`, `focused`) and an NPC combat role from `NPC.ai.combat_role` or
`NPC.behavior`. Avoid exact player-facing numbers and avoid a threat-management minigame.

## 15. Death & defeat — contextual, not one universal respawn

Distinct states: `defeated / downed / unconscious / dying / dead`. Default: at 0 HP a player is
**downed** (allies can stabilize/revive); hostile behavior depends on personality + encounter
rules; PvE defeat usually = injury/relocation/resource loss/narrative consequence (bandits rob,
guards arrest, beasts leave you wounded). Permanent item loss rare and telegraphed. Reuses
`docs/death_resurrection.md` policy + `LedgerService` for coin loss.

## 16. PvP and duels — deferred

Full PvP, duel consent, duel stakes, and multiplayer formation rules are not part of the active
combat plan. Keep combat NPC-first until the basic loop has playtest evidence.

The current "contract" work is intentionally small: `assist <player>` joins a nearby player's
active encounter on the same side and stores `party_assist` contribution metadata so assistance
counts as participation for future reward/audit policy. If opt-in PvP is revisited later, build it
as an admission/join policy layer over the same encounter graph, not as a parallel combat mode.

---

## 17. Transactions, scheduler, events, audit

- **Submission (Txn A):** validate → create pending `CombatAction` → reserve resources → set
  channel state → commit → emit `CombatActionStarted` → schedule `combat.resolve_action`.
- **Resolution (Txn B):** claim scheduled work → load action+encounter → revalidate → compute
  deterministic outcome → apply damage/effects/movement → update encounter → mark resolved →
  commit → emit `CombatActionResolved` / `CombatDamageApplied` / `CombatEffectApplied` /
  `CombatParticipantDefeated`.
- **Scheduler job:** `kind: combat.resolve_action`, `idempotency_key:
  combat-action:{action_id}:resolve`, `due_at: action.resolve_at` — handler atomically claims;
  a retry sees "already resolved" and exits. Uses the existing `SCHEDULED_JOB_DUE` +
  `job_type` filter convention and `SchedulerEventContext(engine, bus, rng)`.
- **Events notify; they never perform the authoritative damage.** Domain events:
  `CombatEncounterStarted, CombatParticipantJoined, CombatActionStarted, CombatActionInterrupted,
  CombatActionResolved, CombatDamageApplied, CombatEffectApplied/Removed,
  CombatParticipantDowned/Defeated/Escaped, CombatEncounterEnded`. Handlers broadcast prose,
  update quests, alert guards, record crime/metrics/achievements, schedule retaliation, update
  the browser.

## 18. Output & browser UI

Three verbosity levels (`brief/standard/verbose`). Actor sees state + readiness + queued
action; observers see prose only. **No numeric spam** by default — an opt-in `combat explain
last` (qualitative for players, exact for admins). WebSocket sends **structured** combat
updates *and* prose, with **sequence numbers** so the client can detect gaps and request an
encounter resync. Browser panels: participants, health *state* (not exact enemy HP unless
knowledge permits), simple engaged/unengaged state, readiness, queued action, wind-up, active
effects, reaction policy, escape control, and a compact event feed.

## 19. Data-driven action definitions

Implemented in Sprint 87.1: `world_content/combat_actions.yaml` selects **registered**
calculators/resolvers — never inline scripts. The current schema is deliberately small:

```yaml
version: 1
actions:
  - id: basic_attack
    channel: primary
    action_range: engaged
    calculator: opposed_attack
    resolver: opposed_attack
    timing: { windup: 0.25, recovery: 2.0 }
    stamina_delta: -6.0
    tags: [melee, physical]
  - id: ranged_attack
    channel: primary
    action_range: ranged
    calculator: opposed_attack
    resolver: opposed_attack
    timing: { windup: 0.35, recovery: 2.2 }
    stamina_delta: -6.0
    tags: [ranged, physical]
```

`action_range` is broad action semantics (`self`, `engaged`, `ranged`), not a persistent near/far
tactical band. Complex boss abilities may later reference a Python resolver **registered by
identifier**. Same registry philosophy as the scripting vocabulary (`register_spec`).

## 20. Resolution objects, randomness, versioning

The resolver takes a `CombatSnapshot` + action + `rng` and returns a frozen `CombatResolution`
(target results, resource changes, effects added/removed, encounter changes, explanations,
`random_trace`) — it does **not** mutate ORM objects; the service applies it
transactionally. Store enough random trace to explain/reproduce (algorithm version, stream id,
draw indices, resolved inputs, selected modifiers, outcome). Version formulas
(`combat_ruleset_version`, `resolver_version = "opposed-v2"`); a pending action keeps the
ruleset it was admitted under. Distinguish historical replay / simulation replay / audit
explanation — not bit-perfect cross-version determinism.

## 21. Performance

No 10 Hz scan of all combatants. Durable SQLite pending jobs → in-memory min-heap of near-term
jobs → handler → transaction → authoritative state. Complexity ~log(scheduled jobs), not
per-entity-per-pulse. Single process is fine if idle actors aren't polled, resolution avoids
excessive queries, broadcasts/metrics/audit are buffered, and NPCs decide only at decision
points. Don't split combat into another process (SQLite + cross-process authority is the harder
problem); measure queue delay, resolution latency, transaction duration, WS fanout first.

---

## 22. Tier split (engine mechanism vs. feature policy)

**Tier 1 (`engine/`), all already present** — reused, not combat-specific: `SchedulerService`,
`EventBus`, rules-engine mechanism, transaction/unit-of-work, `MeterService` (HP + stamina are
just meter configs), modifier resolver, seeded `rng` + `skill_check`, timed-effects service,
`ItemLocationService`, `LedgerService`, audit. Any *new* Tier 1 need is a **generic primitive
only**: e.g. a staged modifier-stack resolution with source attribution, or effect-lifecycle
hooks — these must not encode combat's opinion (no "leveling grants coins" leaks).

**Tier 2 (`features/combat/`), all combat opinion & data:** the encounter aggregate, action
definitions (YAML), the resolution pipeline, damage/armor formulas, range semantics, reactions,
stances, qualitative threat, death/defeat policy, participation metadata, narrator/renderers, and
the combat commands (`attack`, `shoot`, `defend`, `guard`, `assist`, `flee`, `stance`, `reaction`).
Keep package layout focused: `models`, `service`, `repo`, `resolution`, `damage`, `effects`,
`targeting` if needed, `reactions` if it grows, `rewards`, `definitions`, `events`, `jobs`,
`renderers`, `rules`.

## 23. Tunables (static vs. live-tunable)

| Value | Classification |
|---|---|
| Per-action identity (windup/recovery, tags, targeting) | **YAML content** (reseed) — authored |
| Global pacing scalar, per-class windup/recovery defaults | **Live-tunable** (admin, no restart) |
| Formula constants (to-hit scale, crit margin, variance bounds, armor block/resist caps) | **Live-tunable** ruleset singleton, versioned |
| Stance modifier magnitudes | **Live-tunable** |
| Individual weapon/ability damage numbers | **YAML content** (reseed) + a **live-tunable global damage scalar** |
| Per-player policies (autoattack, flee-at-%, reaction policy, stance) | player state (not admin) |
| Default policy values, downed/defeat thresholds | **Live-tunable** defaults |

Follow the `WorldClock` live-tunable pattern (`webui/admin/routers/clock.py`): a DB-backed,
optionally-YAML-seeded singleton mutated via an admin endpoint that pushes the new value into
running state in the same call. Explicitly avoid the `economy.regions` reseed-only gap for
balance dials an admin would plausibly retune mid-session.

---

*See `engine_core.md` (Tier 1 primitives), `death_resurrection.md` (death/respawn),
`inventory_equipment.md` (weapon/armor descriptors), `feature-registration.md` (module layout).*
