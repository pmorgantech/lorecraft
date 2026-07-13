# Discipline / Ability System — Design & Implementation Guide

> **Status:** Design proposal (2026-07-13). Not yet on the roadmap as a numbered sprint —
> see the "Sprint 77 (proposed)" summary in [`roadmap.md`](roadmap.md)'s Backlog.
> **Origin:** user-provided design brief (2026-07-13) proposing a Discipline → Ability model
> for MUD progression systems, reworked here to fit Lorecraft's existing Tier 1/2 architecture,
> data-driven conventions, and **combat-shelved** status.
> **Companion docs:** [`engine_core.md`](engine_core.md) (Tier 1/2/3 boundary),
> [`combat_system.md`](combat_system.md) (shelved combat design — see §7, "Combat seam"),
> [`roadmap.md`](roadmap.md) §73 design (mechanism/policy split precedent this guide follows),
> §74 (the skill-tree system this guide replaces).

---

## 0. TL;DR

Lorecraft currently has **two separate, confusingly-overlapping systems** that both use the
word "skill": a **skill-level catalog** (`features/skills/` — `perception`, `lockpicking`,
`bartering`, `cartography`, `survival`, `persuasion`, numeric 0–100, improves by use, feeds
dice-roll checks) and a **skill-*tree*** (`features/progression/skill_tree.py` — nodes bought
with skill points, each setting an `ability.<id>` flag that gates a verb or grants a passive
modifier). They don't share storage, don't share a registry, and a player has no way to tell
from the UI which one a given `score`/`skills`/`abilities` line refers to. This is the
confusion the user flagged.

**The fix is not a patch — it's a replacement.** Both existing systems get absorbed into one
coherent **Discipline → Ability** model:

- **Discipline** = a themed body of practice (e.g. *Survival*, *Subterfuge*) — the thing a
  player specializes in.
- **Ability** = one concrete thing within a discipline — an active verb, a passive bonus, or
  an interaction unlock. This *is* Sprint 74's `SkillTreeNode`, generalized.
- **Proficiency** = a per-ability (or per-discipline) numeric competence that grows with use —
  this *is* the old flat `SkillRegistry` levels, now attached to the tree instead of floating
  free of it.

Pre-1.0, no back-compat aliases (matching the Sprint 71.2 `area_id` disposition) — this is a
clean replace of `features/skills/` and `features/progression/skill_tree.py`'s node shape, not
an additive layer alongside them.

**Combat note (important):** the user's source brief's seed disciplines (Swordsmanship,
Defense, Pyromancy, Necromancy) are combat-flavored. Lorecraft has combat/PvP explicitly
shelved (`wishlist.md` → *Combat, reframed*; `AGENTS.md` "foundation before features"). §6
below proposes a **non-combat seed set** grounded in Lorecraft's actual world and existing
content instead. The underlying *mechanism* stays generic enough that `combat_system.md`'s
shelved design can plug in as additional Disciplines later without a redesign — see §7.

---

## 1. Current state — the two systems being replaced

### 1.1 `features/skills/` — the skill-level catalog

- `SkillDef` / `SkillRegistry` (`features/skills/definitions.py:14-42`): a flat, hardcoded
  `STANDARD_SKILLS` list — `perception`, `lockpicking`, `bartering`, `cartography`,
  `survival`, `persuasion` — each with a `governing_stat`.
- Per-player state: `PlayerStats.skills: dict[str, int]` (0–100 level).
- Growth: `SkillService.record_use()` (`features/skills/service.py:30-52`) — ~10% chance to
  +1 on every use, capped at `MAX_LEVEL=100`. Pure "learn by doing," no deliberate spend.
- Consumed by: `skill_check()` (`engine/game/checks.py:33-56`) — the Tier 1 roll-under-d100
  resolver. **This module is the one piece of the current design that's already correctly
  factored** — its own docstring explicitly separates "which skills exist" (Tier 2) from "how
  a check resolves" (Tier 1). Keep it; nothing here needs to change.
- Commands: `skills` (lists all 6, one `ctx.say()` per line — see the "Info commands
  cohesion" roadmap item, a separate but related fix).

### 1.2 `features/progression/skill_tree.py` — the ability tree

- `SkillTreeNode` (`features/progression/skill_tree.py:80-140ish`): `id`, `name`,
  `description`, `cost` (skill points), `prerequisites: list[str]`, `unlock` (`flags`,
  optional `modifier: NodeModifier`, optional `enables_verb`).
- Definition source: `world_content/skill_tree.yaml`, loaded into `SkillTreeRegistry`
  (marks-def pattern — data-driven already, this part is correct and worth preserving as-is).
- Per-player state: `PlayerStats.unlocked_nodes: list[str]` + `ability.<id>` flags on
  `Player.flags`.
- Acquisition: spend `PlayerStats.skill_points` via `train`/`learn`
  (`features/progression/commands.py`), gated by `cost` + `prerequisites` only — no notion of
  "discipline rank," no usage requirements beyond the flag check.
- Three "flavors," each converging on the `ability.<id>` flag: active verb (gated via
  `conditions=["actor_has_flag:ability.<id>"]` at command registration,
  `engine/game/registry.py:72-116`), passive modifier (feeds
  `engine/game/modifiers.py`'s `ModifierRegistry`/`resolve()`), interaction/dialogue (flag
  alone, `world.yaml` gates on it).
- Today's content: 7 nodes total — `forage`, `keen_senses`, `pick_locks` (active verbs),
  `mule`, `sharp_eyes`, `haggler` (passives), `silver_tongue` (interaction). All flat, no
  discipline grouping, no branches, no tiers beyond simple prerequisite chains.

### 1.3 Why these two systems are genuinely confusing together

They're not redundant (traced precisely in the earlier investigation — see roadmap's "Info
commands cohesion" item for the full comparison table), but nothing in the UI or vocabulary
tells a player *why* `lockpicking` (a skill, levels by use) and `pick_locks` (an ability, must
be bought) are different things, when both are about picking locks. A player reasonably
expects one system, not two. **This guide's core recommendation is to actually make it one
system** — not just explain the difference better.

---

## 2. The Tier 1 / Tier 2 split (mandatory per `AGENTS.md`)

Per the project's design principles, every design must state explicitly which parts are Tier 1
(mechanism, opinion-free) and which are Tier 2 (policy, data-driven, admin/content-authorable).

### Tier 1 (`engine/game/`) — provides the ability to do things, knows nothing about *what*

New module: `engine/game/abilities.py` (mirrors `engine/game/leveling.py`'s shape — a pure,
data-driven mechanism module, no IO, no session, no hardcoded ability IDs):

- **`AbilityDef`** — a value object holding one ability's *structural* data (id, discipline
  id, tier, ability_type, activation_type, prerequisites, cost, usage-requirement
  descriptors — see §4). Constructed from data the caller passes in (loaded from YAML by
  Tier 2), never hardcoded.
- **`check_acquisition(player_state, ability: AbilityDef, discipline_rank: int) -> AcquisitionResult`**
  — the generic "can this player learn this ability" mechanism: cost affordable, prerequisites
  held, discipline rank met, level met. Knows nothing about *what* an ability unlocks — only
  whether the abstract conditions are satisfied. Mirrors `leveling.award_xp`'s "generic rollover
  mechanism, no reward opinions" shape.
- **`check_usage(actor_state, ability: AbilityDef, target_state, world_state) -> UsageResult`**
  — the generic "can this ability be performed right now" mechanism: weapon-tag match,
  character-state match (via the existing `Player.flags`/`ActiveEffect` state system — see
  §4.3), target-state match, cooldown/resource affordability. This is new — today's system has
  no usage-requirement mechanism at all (a `forage`-flavor node's only "usage requirement" is
  hardcoded into the verb's own Python `conditions=[...]`, not data). Generalizing this into
  Tier 1 is the single biggest structural addition this guide proposes.
- **`resolve_proficiency(base_level, modifiers) -> float`** — thin wrapper composing the
  *existing* `engine/game/modifiers.py::resolve()` and `engine/game/checks.py::skill_check()`
  Tier 1 primitives; proficiency growth-by-use logic itself is lifted near-verbatim from
  `SkillService.record_use()` (already Tier 1-appropriate in character, just misplaced under
  `features/skills/` today — see §5's migration note).
- **Cooldown/resource primitives** — a small, generic `ResourceLedger`-style check (does the
  actor have enough of `resource_type` — stamina is the only resource that exists in Lorecraft
  today, via the `fatigue` feature's meter) and a cooldown-timestamp check, both keyed off
  `ActiveEffect`/meter primitives that already exist (§4.3). **Not** a new resource-type
  registry — Lorecraft has exactly one resource (stamina) today; don't build a generic
  multi-resource system speculatively (mana/rage/energy) with nothing to consume it.

**What Tier 1 explicitly does NOT do:** decide which disciplines exist, what any ability
actually grants (a verb, a modifier, a flag), what it costs, or what its usage requirements
are. All of that is data, supplied by the Tier 2 caller — exactly the line Sprint 73's
`leveling.py`/`ProgressionConfig` split already established.

### Tier 2 (`features/disciplines/` — new package, replaces `features/skills/` +
`features/progression/skill_tree.py`) — the opinionated, data-driven policy layer

- **`DisciplineDef`** / **`DisciplineRegistry`** — loaded from `world_content/disciplines.yaml`
  (see §4 for schema), mirroring the existing `SkillTreeRegistry` load pattern exactly (marks-
  def pattern, `discover_features()`-compatible).
- **`AbilityRegistry`** — loaded from the same YAML (or a companion `abilities.yaml` — see
  §4.4 for the file-split recommendation), each entry validated into the Tier 1 `AbilityDef`
  shape plus Tier-2-only fields (display name, description, flavor text).
- **Per-player state**: extends `PlayerStats` — see §5.2 for the exact field changes (this is
  a real schema migration, flagged for Database Specialist review when implemented).
- **`train`/`learn` command** — same UX shape as today's, now driving the generalized Tier 1
  `check_acquisition` instead of the flat cost+prerequisite check.
- **New: ability *usage* is data-driven too.** Where today a verb like `forage` hardcodes its
  own `Room.indoor == False` condition in Python, the new model lets an ability's YAML entry
  declare `usage_requirements: {character_states: [...], target_states: [...], terrain: [...]}`
  and have the Tier 1 `check_usage` mechanism enforce it generically — the verb's Python code
  becomes thinner (just narration + the actual effect), not gatekeeping logic. This is the
  "usage requirements separate from acquisition requirements" half of the source brief's core
  lesson, and it's genuinely new capability, not just a rename.

---

## 3. Reconciling "Discipline rank" vs. "character level"

The source brief's `required_rank` (a per-discipline numeric gate, separate from
`required_level`) doesn't exist in Lorecraft today — only a flat character `level`
(`PlayerStats.level`, Sprint 73) and a flat `skill_points` currency. Two ways to realize
"discipline rank" without inventing a second currency:

- **(Recommended) Rank = a discipline-scoped proficiency accumulator.** Every ability use
  within a discipline (not just the specific ability) contributes toward that discipline's
  rank — e.g. using any Survival ability nudges "Survival rank" up, the same way using
  `perception` today nudges the flat skill level. This directly repurposes
  `SkillService.record_use()`'s existing growth-by-use mechanic, just re-scoped from "one flat
  skill" to "one discipline," and requires no new currency. `PlayerStats.skills` becomes
  `PlayerStats.discipline_ranks: dict[str, int]` (renamed, same shape).
- **(Rejected for v1) A separate rank-up currency/ceremony.** More faithful to some MUD
  traditions (train-with-an-NPC-trainer rank ceremonies) but adds a second progression
  currency alongside `skill_points`, which the source brief's own model doesn't strictly
  require and which Lorecraft has no content precedent for (no trainer NPCs exist yet). Revisit
  only if playtesting shows use-based rank growth feels too passive.

---

## 4. Data schema (YAML — this is the load-bearing "data-driven, not code" requirement)

### 4.1 Discipline record (`world_content/disciplines.yaml`)

```yaml
version: 1
disciplines:
  - id: survival
    name: Survival
    description: Reading the wild — foraging, tracking, and finding the way.
    governing_stat: fortitude   # mirrors today's SkillDef.governing_stat
```

### 4.2 Ability record (`world_content/abilities.yaml` — see §4.4 for why split from
disciplines.yaml)

Directly generalizes today's `SkillTreeNode`, adding the fields §2's Tier 1 mechanism needs:

```yaml
- id: forage
  name: Forage
  discipline: survival
  branch: foraging          # optional; groups abilities within a discipline for UI/tree display
  tier: 1
  ability_type: active      # active | passive | interaction | reaction (see §4.5 — trimmed from
                             # the source brief's 10 types; see rationale)
  activation_type: instant  # instant | maintained | triggered (trimmed from the source brief's
                             # 6 types — see rationale)
  cost: 1                   # skill points
  prerequisites: []
  required_discipline_rank: 0
  required_level: null
  acquisition:              # what's needed to LEARN it (today's cost+prerequisites, unchanged)
    cost: 1
    prerequisites: []
  usage:                    # what's needed to PERFORM it (NEW — see §2 Tier 1 check_usage)
    character_states: []    # e.g. ["hidden"] for a stealth ability
    target_states: []
    terrain: [outdoor]      # replaces forage's hardcoded Room.indoor==False check
    resource:
      type: stamina
      cost: 0                # forage costs no stamina today; field exists for future abilities
    cooldown_seconds: 0
  unlock:                   # what it GRANTS (unchanged shape from today's SkillTreeNode.unlock)
    enables_verb: forage
  proficiency_model: none   # none | success_only | success_and_magnitude (see §4.6)
  mutually_exclusive_group: null
  tags: [outdoor, gathering]
```

### 4.3 The generic state system

The source brief calls for a generic state vocabulary (`hidden`, `burning`, `bleeding`,
`prone`, `guarding`, `marked`). **Lorecraft already has the precedent — don't build a new
one.** `engine/models/meters.py::ActiveEffect` (clock-driven buff/debuff, `effect_key` +
`payload` + `expires_at_epoch`, swept by `EffectService._on_time_advanced()`) is exactly this
mechanism, already Tier 1, already used by the `consumables` feature's `apply_effect`
descriptors. `usage_requirements.character_states`/`target_states` in §4.2's schema should
resolve against **held `ActiveEffect.effect_key`s** (for transient states like "burning") plus
**`Player.flags`** (for durable states, the same flag namespace `ability.<id>` already uses,
just a different prefix — e.g. `state.hidden`). No new state-tracking table needed.

### 4.4 Why split `disciplines.yaml` from `abilities.yaml`

The source brief's example puts everything in one flat list. Recommend splitting because
disciplines are few and rarely change (content-authoring cadence: rare) while abilities will
grow continuously as content is added (cadence: frequent, per-sprint) — same rationale as
splitting `world.yaml` rooms from `skill_tree.yaml` nodes today. Keeps diffs small and
merge-conflict-prone content (abilities) separate from stable structural content
(disciplines).

### 4.5 Trimmed `ability_type`/`activation_type` enums — rationale

The source brief proposes 10 ability types and 6 activation types, largely to support combat
(`stance`, `spell`, `ritual`, `craft`, `movement`, `social`, `gathering` — several of which are
implicitly combat- or magic-flavored) and complex real-time activation (`channeled`,
`maintained` while-held). **Recommend starting with 4 ability types** (`active`, `passive`,
`interaction`, `reaction`) **and 3 activation types** (`instant`, `maintained`, `triggered`) —
covering everything Lorecraft's actual non-combat content needs today (an interaction unlock
like `silver_tongue` is `interaction`/`instant`; a hypothetical "keep hidden while moving"
ability would be `active`/`maintained`; a hypothetical "counter when pickpocketed" ability
would be `reaction`/`triggered`). The schema field is a plain string, not a hardcoded Python
enum member list validated by the engine — **adding `spell`/`ritual`/`stance` later when
combat unshelves is a content change, not an engine change**, so trimming now costs nothing
and avoids designing UI/copy for ability types with zero content.

### 4.6 `proficiency_model` — trimmed from the source brief's freeform string

Recommend a closed enum (`none | success_only | success_and_magnitude`) rather than the source
brief's implied freeform strings (`accuracy_and_damage`, `success_and_damage` — both
combat-specific). `none` = binary owned/not-owned (today's interaction/passive nodes need
nothing more). `success_only` = feeds `skill_check()`'s pass/fail roll, proficiency-as-base
(today's `forage`/`pick`/`sense` verbs, once ported). `success_and_magnitude` reserved for a
future case where proficiency also scales an effect's strength (no current content needs this
— included for forward-compatibility with combat, not built out now).

---

## 5. Migration plan

### 5.1 Content migration (mechanical, low risk)

Today's 7 `skill_tree.yaml` nodes map onto disciplines cleanly (see §6 for the full mapping) —
this is a content-authoring pass, not new engine work, once §2's Tier 1/Tier 2 modules exist.

### 5.2 Schema migration (`PlayerStats` — flag for Database Specialist review)

- `skills: JsonObject` → rename/repurpose as `discipline_ranks: JsonObject` (§3) — same dict
  shape, different keys (discipline ids instead of flat skill names). A straightforward
  reflection-scanner-compatible additive column if renamed rather than reused in place (see
  the Sprint 75 precedent, `_ensure_additive_columns` — this migration should follow the same
  generic-scanner pattern, not a hand-written shim).
- `unlocked_nodes: list[str]` → keep as-is; still the query/UI record for owned abilities,
  vocabulary otherwise unchanged (a "node" *is* an "ability" now, just renamed in code/docs).
- `Player.flags` — `ability.<id>` prefix unchanged; new `state.<name>` prefix added for
  transient usage-requirement states (§4.3) — additive, no migration needed (flags dict is
  already schemaless JSON).

### 5.3 Code migration

- Delete `features/skills/definitions.py` (`SkillRegistry`, `STANDARD_SKILLS`) — absorbed into
  `features/disciplines/`'s ability registry. Pre-1.0, no alias kept (matches the `area_id`
  disposition precedent).
- `features/progression/skill_tree.py` → becomes `features/disciplines/abilities.py`
  (renamed/extended, not rewritten from scratch — the existing `SkillTreeNode`/
  `NodeModifier`/`NodeUnlock` Pydantic models are ~70% of the way to `AbilityDef` already).
- `engine/game/checks.py::skill_check()` — **unchanged**, just now called with a
  discipline-rank-derived base instead of a flat-skill-derived one.
- `engine/game/modifiers.py` — **unchanged**, already the correct Tier 1 primitive.
- Existing verb code (`features/exploration/forage.py`, `sense.py`,
  movement/lockpicking's `pick`) — each verb's hardcoded `conditions=[...]` gains the new
  data-driven `check_usage` call in place of (or alongside, during transition) its bespoke
  Python condition; `Room.indoor == False`-style checks become
  `usage.terrain: [outdoor]` data.

---

## 6. Proposed non-combat seed disciplines (replaces the source brief's combat-flavored set)

Curated to (a) absorb all 7 existing nodes + all 6 existing skills with zero combat content,
(b) fit Lorecraft's actual world (Cogsworth/Whisperwood/Port Veridian, no weapons-as-abilities
system, no spellcasting), (c) follow "several short branches, not one giant constellation" —
5 disciplines for a starting ~13-ability roster, not 8 disciplines for 40+ as the source brief
sketches for a combat-heavy game:

| Discipline | Absorbs | Purpose |
|---|---|---|
| **Survival** | `forage` (existing), `survival`+`cartography` skills | Outdoor competence — foraging, tracking, pathfinding, camping |
| **Subterfuge** | `pick_locks`, `keen_senses` (existing), `lockpicking`+`perception` skills | Stealth and unseen access — locks, awareness, sneaking |
| **Commerce** | `haggler` (existing), `bartering` skill | Trade and pricing — ties into the `economy` feature's `price.buy` modifier precedent |
| **Rhetoric** | `silver_tongue` (existing), `persuasion` skill | Social/dialogue unlocks — interaction-flavor abilities, ties into NPC dialogue gating |
| **Fortitude** | `mule` (existing) | Physical resilience — carry capacity and (future) endurance-flavored passives |

Each existing ability keeps its id/behavior unchanged — only gains a `discipline:` field and,
for the three that were skill-tree-only, a paired discipline-rank contribution from the
matching legacy skill (e.g. `pick_locks`'s discipline is `subterfuge`, and using it now also
nudges `discipline_ranks.subterfuge`, replacing the old flat `skills.lockpicking` bump).

**Deliberately excluded from v1**, matching the source brief's own disciplines but requiring
combat: Swordsmanship, Defense, Pyromancy, Restoration, Necromancy, Leadership (the
group-combat-tactics half of it — a non-combat "Leadership" *could* exist later for
morale/social group buffs, but nothing in Lorecraft's current content needs it yet; don't
build ahead of content).

---

## 7. Combat seam — how this stays open for `combat_system.md` later

`combat_system.md`'s shelved design already specifies Tier 1 primitives this guide reuses
directly (modifier resolver, seedable `skill_check`, timed effects) — no conflict. When/if
combat unshelves, its abilities (Swordsmanship/Defense-style) become **additional
disciplines** authored the same way §6's do, using the `ability_type`/`activation_type`
values §4.5 trimmed out but didn't forbid (`stance`, `spell`, `reaction`-with-`triggered`
already fit the schema; `weapon_tags`/`cooldown_seconds`/`resource.type: stamina` are already
in §4.2's schema, unused by any v1 ability but ready). **No engine change needed to add combat
abilities later** — purely a content-authoring + (if a second resource type like "rage" is
wanted) a small `ResourceLedger` extension. This is the "generic engine, opinionated content"
line held correctly.

---

## 8. Phased implementation plan (roadmap-ready)

Mirrors the Sprint 73/74 mechanism-then-policy sequencing precedent:

1. **Phase A — Tier 1 mechanism.** `engine/game/abilities.py`: `AbilityDef`,
   `check_acquisition`, `check_usage`, `resolve_proficiency`, cooldown/resource primitives.
   Pure, unit-tested, no content yet.
2. **Phase B — Tier 2 registry + schema.** `features/disciplines/` package,
   `world_content/disciplines.yaml` + `abilities.yaml` loaders, `PlayerStats` migration
   (§5.2, Database Specialist gate).
3. **Phase C — Content migration.** Port the 7 existing nodes + 6 existing skills into the 5
   disciplines (§6), zero new abilities yet — proves the migration is lossless before adding
   scope.
4. **Phase D — `train`/`learn`/`abilities`/`skills` command rework**, folding in the "one
   `ctx.say()` per command" fix already flagged in `roadmap.md`'s Backlog (same commands, same
   sprint makes sense — don't fix formatting on a command whose underlying data model is about
   to change shape).
5. **Phase E — Usage-requirements data-drive existing verbs.** Retrofit `forage`/`sense`/
   `pick` to read `usage:` from YAML instead of hardcoded Python conditions — proves the new
   mechanism actually replaces, not just duplicates, the old gating.
6. **Phase F — Docs.** `docs/user_guide.md` (disciplines/abilities/proficiency explained to
   players), `docs/admin_builder_guide.md` (authoring new abilities/disciplines).

Each phase is independently shippable and testable, matching how Sprint 73 (mechanism) shipped
before Sprint 74 (policy/content) did.
