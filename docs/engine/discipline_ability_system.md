# Discipline / Ability System

> **Status:** Implemented (Sprints 77–78). This is the current-state reference — what exists
> today, not how it was designed. For the full design rationale (why 5 disciplines, why
> `skill.<name>` modifier keys were retained, the Tier 1/2 split reasoning, the migration from
> the old flat-skills + skill-tree systems), see the archived
> [`archive/discipline_ability_system_design.md`](../archive/discipline_ability_system_design.md).

Lorecraft's single progression system for non-combat competence: players spend **skill
points** to train **abilities**, grouped into themed **disciplines**, and grow a
**proficiency rank** in each discipline by using its abilities. It replaced two older,
overlapping systems (a flat skill-level catalog and a separate skill-point tree) that both
used the word "skill" for different things.

---

## Concepts

- **Discipline** — a themed body of practice a player specializes in (e.g. *Survival*,
  *Subterfuge*). Has a `governing_stat`, a proficiency-growth rate (`improve_chance`), and a
  rank ceiling (`max_rank`).
- **Ability** — one concrete thing within a discipline: an active verb, a passive stat
  modifier, or a dialogue/interaction unlock. Bought with skill points.
- **Proficiency (discipline rank)** — a 0–100 competence value per discipline that grows by
  use (not by spending points) and feeds the base value of related dice-roll checks.

## The 5 disciplines and 7 abilities (current content)

| Discipline | Governing stat | Abilities | Grants |
|---|---|---|---|
| **Survival** | fortitude | `forage` | active verb (`forage`, outdoor-only) |
| **Subterfuge** | agility | `keen_senses`, `pick_locks`, `sharp_eyes` | active verbs (`sense`, `pick`) + passive perception modifier |
| **Commerce** | presence | `haggler` | passive buy-price modifier |
| **Rhetoric** | presence | `silver_tongue` | dialogue/interaction unlock |
| **Fortitude** | (n/a) | `mule` | passive carry-capacity modifier |

Content lives in `world_content/disciplines.yaml` (structure) and
`world_content/abilities.yaml` (the 7 abilities, each with `discipline`, `cost`,
`prerequisites`, `ability_type`, `activation_type`, an optional `usage:` block, and an
`unlock:` payload). Both are static YAML — no live-tunable admin surface yet (see
`roadmap.md` backlog).

## Architecture (Tier 1 / Tier 2 split)

**Tier 1 — `src/lorecraft/engine/game/abilities.py`** (opinion-free mechanism):
- `AbilityDef`, `UsageRequirements`, `ResourceCost` — structural value objects.
- `check_acquisition(stats, ability, discipline_rank)` — can this player learn it (cost,
  prerequisites, rank, level)?
- `check_usage(actor_state, ability, target_state, world_state)` — can this ability be
  performed right now (terrain, character/target state, resource, cooldown)?
- `resolve_proficiency(rng, base_level, modifiers, improve_chance, max_rank)` — one use-based
  growth roll, composing `checks.py::skill_check()` + `modifiers.py::resolve()`.

**Tier 2 — `src/lorecraft/features/disciplines/`** (the opinionated, data-driven policy layer):
- `abilities.py` — `DisciplineDef`/`DisciplineRegistry` and `AbilityRecord`/`AbilityRegistry`,
  loaded from the YAML above; `AbilityRecord.to_ability_def()` projects down to the Tier 1
  shape.
- `service.py` — `ProficiencyService` (per-discipline rank growth, backed by
  `PlayerStats.discipline_ranks`) and `AbilityService` (the skill-point sink: `purchase()`
  drives `check_acquisition`, then dual-writes `unlocked_nodes` + the `ability.<id>` player
  flag).
- `usage.py` — usage-requirement checks for active abilities.
- `modifier_source.py` — bridges owned passive abilities into the engine's modifier resolver.
- `commands.py` — player verbs (below).

## Player state

`PlayerStats` (`src/lorecraft/engine/models/player.py`):
- `skill_points: int` — the spendable currency.
- `discipline_ranks: dict[str, int]` — per-discipline proficiency (0–100), JSON column.
- `unlocked_nodes: list[str]` — ids of every owned ability.

Owning an ability also sets a `ability.<id>` flag on `Player.flags`, which is what gates the
ability's verb registration (`conditions=["actor_has_flag:ability.<id>"]`) or dialogue check.

## The `skill.<name>` modifier-key convention

Dice-roll checks (`skill_check()`) and modifiers (`resolve()`) are keyed by an arbitrary
resolver string — `skill.perception`, `skill.persuasion`, `skill.survival`,
`skill.cartography`, `skill.lockpicking`, `skill.bartering` — independent of which package
owns the underlying value. These six keys are retained permanently as the fine-grained
per-check namespace; a discipline's `check_keys` list (in `disciplines.yaml`) declares which
of these it supplies the *base value* for. Traits, consumable buffs, marks, and item effects
that reference `skill.<name>` needed **no changes** when the old flat-skills package was
removed — only where the base value comes from changed.

## Commands

Registered by `features/disciplines/commands.py`:

- **`train [ability]`** (alias `learn`) — with no argument, lists what's trainable now and
  what's still locked (and why); with an ability id, attempts the purchase.
- **`abilities`** (alias `abils`) — read-only: abilities you own + what's currently trainable.
- **`disciplines`** — read-only: your rank in each discipline (lives in
  `features/character/`, alongside the other character-info verbs).

Each command emits one cohesive multi-line `ctx.say()` call rather than one line per item.

## Combat seam

The mechanism is generic enough that if/when combat abilities are added, they become
additional disciplines using the same `AbilityDef`/`check_acquisition`/`check_usage`
primitives — the `ability_type`/`activation_type` fields are open strings (not a closed
Python enum), and `ResourceCost`/`cooldown_seconds` already exist in the schema, unused by
any current ability but ready. No engine change would be needed, only content.
