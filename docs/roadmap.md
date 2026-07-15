# Lorecraft — Roadmap

**A concise list of *remaining* work.** Every **completed** sprint — 1–34 (foundation, the Tier 1
engine-core primitives, the Tier 2 pillar feature band, the tier-split follow-ons), the performance
& scaling band (35–37), and everything since (39–83) — lives in
[`roadmap_completed.md`](roadmap_completed.md) with full task-level detail. Per-version detail is in
[`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and the deferred
multiplayer test pass + concurrency/batching gates are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-14, v0.104.0 on develop; Sprints 1–84 all shipped)

**Everything through Sprint 84 is shipped on `develop`** (currently v0.104.0). `roadmap.md` now tracks
remaining work only; the full task-level history for completed Sprints 1–84 lives in
[`roadmap_completed.md`](roadmap_completed.md), with release-level detail in
[`../CHANGELOG.md`](../CHANGELOG.md).

The latest completed band is archived as Sprints 77–80: the Discipline/Ability replacement for the
old skills/skill-tree split, the Sprint 79 cleanup pass for its review follow-ups, and the Sprint
80 world-system pass for zone climate, data-driven spawns, room loot tables, ambient room flavor,
NPC route hooks, and admin multi-weather controls. Sprint 81 adds the Ashmoore graveyard, the
Brass Vaults steampunk zone, new mobile hazards, and local quest content using those world-system
surfaces. Sprint 82 adds fixed-location Ashmoore shops for potions, food/drink, general goods,
and armory basics using stationary NPC shopkeepers and the existing economy model. Sprint 83
expands Ashmoore's scavenger-hunt content pattern with spread placement for 3-7 item hunts and
speed-scaled coin reward tiers. Sprint 84 adds database query-span logging and an analyzer for
slow/frequent statements plus index candidates, so future schema/index work is evidence-driven.

Sprint 73's cleanup backlog and the 2026-07-13 UI-cohesion items are closed and preserved in
[`roadmap_completed.md`](roadmap_completed.md).

**Set aside to [`wishlist.md`](wishlist.md):** the multiplayer trade/transit **test pass**; and the
deferred **scheduler-commit batching (37.1)** + **concurrency/threading gate (38)** — the measured
wall was fsync serialization on a single SQLite writer, which WAL (37.4) already removed, so threads
wouldn't help. Revisit the latter only if a *post-WAL* realistic-load test shows a hard
single-process wall.

**Activated (2026-07-14):** Combat & PvP (Sprints 85–88, see below) — the Scheduled Intent design
from [`combat_design.md`](combat_design.md). Combat is a **supporting** system (Exploration >
Trading > Questing > Puzzles) — it serves stories; stealth/persuasion/bribery/flee are first-class
alternatives. It ships as `features/combat/` with no Tier 1 edits needed.

Design anchors: [`engine_core.md`](engine_core.md) (the Tier 1/2/3 boundary) and
[`wishlist.md`](wishlist.md) (design pillars + idea backlog).

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| Database inspector / state editor | Admin tool for advanced troubleshooting |
| Multiplayer trade/transit test pass | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Multiplayer sim-test coverage* (was Sprint 65) |
| E2E coverage gap for the new discipline/ability command surface | Added 2026-07-13 (Sprint 78 Test & QA pass). `train`/`abilities`/`disciplines`/`forage`/`pick`/`sense` are unit-tested but not directly exercised by browser-driven e2e tests. Not a current defect — flagged as worth a follow-up e2e pass. |
| Ability tuning live-admin controls | Added 2026-07-14 (Sprint 79 triage). Per-ability `cost`, `cooldown_seconds`, resource costs, and proficiency-growth values (`improve_chance`/`max_rank`) remain static YAML by design. Build a DB-backed, admin-live-tunable config only if admins ask to retune these without restart/reseed; do not build it speculatively. |


---

## Sprint numbering (avoid duplicates)

- **Used (complete):** 1–84, except for deliberately skipped/deferred numbers below. Full task
  detail lives in [`roadmap_completed.md`](roadmap_completed.md).
- **Deferred to [`wishlist.md`](wishlist.md):** 37.1 (scheduler-commit batching), 38
  (concurrency/threading gate), and 65 (multiplayer trade/transit test pass).
- **Newly active (2026-07-14):** 85–88 (combat phases 1–4, Scheduled Intent).
- **Next genuinely free sprint number:** 89. Do not recycle a number that appears here, in
  [`roadmap_completed.md`](roadmap_completed.md), or in [`wishlist.md`](wishlist.md).

---

## Sprints 85–88 — Combat (Scheduled Intent)

Combat is now **active** (no longer set-aside). See [`combat_design.md`](combat_design.md) for
the full design. Built as `features/combat/`, all opinion/data in Tier 2; no Tier 1 edits
needed beyond what exists.

### Sprint 85 — Combat Phase 1: Foundation (Scheduled Intent core)

**Goal:** A player can attack/defend/flee a static NPC through the full intent pipeline; one
primary channel; encounter graph; downed/defeat; structured events + audit; browser state.

**Depends on:** SchedulerService, EventBus, rules engine, transaction/UoW, MeterService,
modifier resolver, seeded rng + skill_check, ItemLocationService, audit. All shipped.

**Tier:** Tier 2 (all features/combat/).

- [ ] 85.1 Encounter aggregate (CombatEncounter/Participant/Relationship) — multiple sides, start/end rules
- [ ] 85.2 Action submission pipeline (Txn A) — validate, persist, emit started, schedule resolve
- [ ] 85.3 Action resolution pipeline (Txn B) — re-validate, calculate, apply atomically, emit events
- [ ] 85.4 Primary-channel readiness + one queued action — derived readiness, single replaceable queue
- [ ] 85.5 Basic attack/defend/flee — opposed margin, staged damage stack, hybrid armor
- [ ] 85.6 Health + stamina via MeterService; downed/defeat states
- [ ] 85.7 Immutable CombatResolution object — resolver/snapshot boundary
- [ ] 85.8 Structured events + audit resolution record + engaged/unengaged position
- [ ] 85.9 Basic browser combat state over WebSocket — structured updates + prose with sequence numbers
- [ ] 85.10 NPC utility-selection stub — single primary action, same intent pipeline as players

### Sprint 86 — Combat Phase 2: Tactical Depth

**Goal:** Stances, guarding, bounded reactions, wind-up interruption, near/distant positioning,
basic status effects, threat/NPC roles, party assistance, duel rules.

**Depends on:** Sprint 85; engine timed-effects service hook coverage verification (86.5).

**Tier:** Tier 2 (all features/combat/).

- [ ] 86.1 Stances (balanced/aggressive/defensive/mobile) + persistent policies
- [ ] 86.2 Guarding + protect-ally + intercept edges
- [ ] 86.3 Bounded reactions (single window, no recursion) + reaction policy
- [ ] 86.4 Wind-up interruption — resolution-time interrupt outcome
- [ ] 86.5 Status-effect lifecycle + hooks — game-time deadlines, hook coverage verification (Tier 1 if missing)
- [ ] 86.6 Near/distant positioning + advance/retreat/disengage
- [ ] 86.7 Decaying-attention threat + NPC personality roles — qualitative cues only
- [ ] 86.8 Party assistance + duel contracts — assistance counts as participation

### Sprint 87 — Combat Phase 3: Content Power

**Goal:** Data-authored actions, equipment traits, more effect hooks, boss phases,
crime/faction consequences, versioning, simulation harness, live-tunable config.

**Depends on:** Sprints 85–86; features/equipment + features/traits (shipped).

**Tier:** Tier 2 (all features/combat/).

- [ ] 87.1 Data-driven action definitions (YAML) + registered calculators/resolvers
- [ ] 87.2 Equipment traits + weapon/armor as effect descriptors
- [ ] 87.3 Extended effect hooks (on_damage_received/on_movement/on_action_admission)
- [ ] 87.4 Boss scripted phases overriding utility AI — registered Python resolver by id
- [ ] 87.5 Crime + faction consequences via rule obligations
- [ ] 87.6 Ruleset/resolver versioning + random-trace persistence
- [ ] 87.7 Simulation & balancing harness + reports — headless runs for balance analysis
- [ ] 87.8 Live-tunable ruleset config (WorldClock pattern) — DB-backed, admin endpoint

### Sprint 88 — Combat Phase 4: Advanced (defer until justified by playtesting)

**Goal:** Depth layers gated behind demonstrated need. Do not build speculatively.

**Depends on:** Sprints 85–87 + playtesting/balance evidence.

**Tier:** Tier 2 (all features/combat/). Each item independently deferrable.

- [ ] 88.1 Wounds + body locations — persist after health recovery
- [ ] 88.2 Grappling/screening/flanking edges — extends engagement-edge model
- [ ] 88.3 Formation mechanics
- [ ] 88.4 Terrain & cover — feeds defense_score; ties to features/terrain
- [ ] 88.5 Combo systems
- [ ] 88.6 Simultaneous-planning encounter mode (optional, arena/boss) — alternate combat_mode
- [ ] 88.7 Mounted / siege combat
- [ ] 88.8 Utility/movement action channels — add only if playtesting shows need

---

## Playtesting (Ashmoore dev world)

`start.sh` copies `test_dbs/lorecraft-dev-game.db`, which is built from `world_content/world.yaml`.

Regenerate after world edits:

```bash
python scripts/import_world.py --fresh --db test_dbs/lorecraft-dev-game.db
```

**Starting room:** `village_square` as `player-1`

| Try | Command |
|-----|---------|
| Move east | `go east` → market stalls |
| Pick up coin | `take coin` |
| Talk to Mira | `go west` → Wandering Crow Inn, then `talk mira` |
| Shop village | `go east`, `shop`; then `east` to Vale's General Store or `south` to Hearthloaf Bakery and `shop` again |
| Quest hook | Choose "Any news around town?" in dialogue |
| Wear armor | `go north` → forge, `take helmet`, `wear helmet`, `remove helmet` |
| Locked door | `north`→`north`→`east` to Vault Hall; `take good key`, `unlock east`, `go east` → Inner Vault (the Bad Key won't work) |
| Context verb | `go south` past the creek to the Ruined Chapel; `read altar` (reveals lore) |

Empty databases import `world_content/world.yaml` on startup (configurable via `LORECRAFT_WORLD_YAML_PATH`). Integration tests use the same Ashmoore data — no parallel hardcoded world in production code.
