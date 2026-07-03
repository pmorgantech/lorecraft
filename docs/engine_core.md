# Engine Core — the framework / game boundary & Tier 1 primitives

> **Status:** Design (2026-07-03). Anchor doc for the question *"where does the engine end and
> game customization begin?"* Written **before** the feature band (roadmap [Sprints 22](roadmap.md#sprint-22--standard-item-components--definition-fields)+) so we
> build the engine's extension points first and don't bake opinionated mechanics into core.
>
> **Directive (product owner, 2026-07-03):** design Tier 1 (engine primitives) now, implement
> **all or most of Tier 1 before Tier 2** (the opinionated modules). This doc is the design;
> [`roadmap.md`](roadmap.md) sequences the build.

---

## 1. The three tiers

"Engine vs game" collapses two different things. The useful split is three layers:

| Tier | Lives in | What it is | Opinion level |
|---|---|---|---|
| **1 — Engine core** | `src/lorecraft/` | Content-agnostic primitives + registries the loop runs on | **None** — no named skills, slots, factions, or damage formulas |
| **2 — Standard modules** | `features/*` (shipped, toggleable) | The mechanics most games want, with knobs | Opinionated *defaults*, replaceable per world |
| **3 — Content** | `world_content/*.yaml` + registered handlers | The actual slots, skills, prices, lines, numbers | Fully game-specific |

**"Some mechanics are universal, so include them"** lands in **Tier 2**: we ship equipment,
fatigue, shops, banks, transit, and a default combat ruleset — but each is built *only* on Tier 1
and registers itself through the same seams a third-party author would use. Nothing in Tier 2 is
reachable by hard-coded reference from Tier 1.

### Two litmus tests for the boundary

1. **"Could a different game reasonably want the opposite choice?"** Yes → Tier 2/3, never core.
   - *d20 combat?* A game could want real-time or narrative resolution → **Tier 2**.
   - *Items can carry per-instance state?* No game wants the opposite → **Tier 1**.
2. **"Does the game loop need it to run?"** Transaction/event/scheduler/dispatch → **Tier 1**.
   *Swords deal slashing damage* → **Tier 3 content**.

If a primitive passes test 1 (nobody wants the opposite) *and* is needed by ≥2 feature sprints,
it belongs in Tier 1 and should be designed here, not re-invented per sprint.

---

## 2. Tier 1 that already exists (foundation band output)

The foundation band ([Sprints 5–15](roadmap.md#sprint-5--error-handling--exception-hierarchy-)) already shipped much of the Tier 1 extension surface. **Do not
rebuild these** — the new primitives compose with them:

- **Registries** — `CommandRegistry` (`game/registry.py`), `CommandConditionRegistry`
  (`game/command_conditions.py`), dialogue `side_effects` + `conditions`, `RuleEngine`
  (`game/rules.py`). These are the primary "register, don't edit core" seam.
- **Event bus + `register(bus)` convention** (`game/events.py`) and one `ServiceContainer`.
- **Scheduler** (`services/scheduler.py`) — DB-backed jobs dispatched on `TIME_ADVANCED`. Drives
  everything time-based (combat ticks, restock, corpse decay, transit).
- **Unified command lifecycle + rollback-on-error** ([Sprint 14](roadmap.md#sprint-14--unify-command-lifecycle-)) — one 13-step transaction path;
  `GameContext.rollback_state_changes()` undoes half-applied state on a handler crash.
- **`build_game_context()` factory** — the single `GameContext` construction path.
- **Content validators** (`lorecraft.tools.validators`) and the world CLI.

### One trap in the existing surface: fail-open vs fail-closed

`CommandConditionRegistry.evaluate()` **fails open** — an unknown condition name returns
`allowed=True` (deliberate forward-compat for command definitions). That is fine for *availability*
gates (a typo just makes a command available) but **dangerous for security-relevant gates** (PvP
consent, "can't loot while in combat"). Rule of thumb, already implied by
[`feature-registration.md`](feature-registration.md) §"When Rules Matter":

- **Availability / UX gate** → a **condition** (fails open, cheap, forward-compatible).
- **Security / integrity veto** (consent, escrow, anti-dupe) → a **rule** (`RuleEngine` fails
  closed — a rule must *explicitly* `allow()`).

Design new gates on the correct side of this line.

---

## 3. Tier 1 primitives to design & build (the gaps)

Eight primitives are hiding underneath the feature band. Each is needed by ≥2 sprints; building
them per-sprint yields N opinionated implementations and blurs the boundary. Each entry lists the
**vertical use cases** (why it's Tier 1) and the **surprise it prevents** (from the cross-doc read
in §4).

### 3.1 Entity component / instance-state model
*Consumers: 22 item state, 23 containers/durability, 27 condition, 30 puzzles, 31 corpses.*

Per-instance state expressed as **registered components**, not a fixed column set. Core provides
the `ItemInstance` carrier and a component registry; *which* components exist (durability, openable,
lit, container, mechanism-state) is Tier 2/3 data.

- Core: `ItemInstance(id, item_id, location…, state: JsonObject)` + a component/aspect registry
  (a component brings its own fields, validation, and the conditions/side-effects that read/write
  it — same registry pattern as dialogue).
- Durability, light, container, lever/dial are **standard components** (Tier 2). A game-specific
  "rune-charge" component registers the same way with zero core edits.
- **Why not typed columns:** columns bake game opinions into core and can't be extended by a world
  author. A generic `state` bag alone is untyped mush; the component registry is the middle path —
  typed, validated, *and* extensible.

### 3.2 Item location & ownership model  ⚠️ highest-leverage
*Consumers: everything that moves an item — take/drop/give, equip, put/take-from, buy/sell, P2P
trade escrow, loot corpse, drop-on-death.*

**One** way to say where an owned item-stack lives, and **one** atomic operation to move it. Today
there are three representations (`Player.inventory: list[str]`, `RoomItem`, proposed `ItemInstance`)
plus equipment slots, containers, shop stock, and corpses — each doc invents its own move logic.

- Core concept: an **owned stack** = `(item_id, quantity, instance?)` at a **location**
  = `(owner_type, owner_id, slot?)` where `owner_type ∈ {player, room, container, equipment,
  shop, corpse, escrow}`.
- Core op: `move_stack(stack, from_loc, to_loc, qty)` — atomic, audited, rollback-safe.
- **Decision needed (§4.a):** unify the stackable (`list[str]`/`quantity`) and instanced
  (`ItemInstance`) representations behind this one abstraction so consumers see a single shape,
  instead of every downstream system branching on "is it stacked or instanced?"

### 3.3 Meters / vitals
*Consumers: 27 fatigue, 31 combat HP; latent: hunger, mana, sanity, warmth.*

Named, bounded resources that can drain/restore on the clock and expose modifier hooks — **one
primitive**, not one column per resource.

- Core: `Meter(key, current, max, regen_rate?)` attached to an entity; ticks via the scheduler;
  low values feed the modifier resolver (§3.5).
- HP becomes the first registered meter (migrating `PlayerStats.current_hp/max_hp`); fatigue the
  second; a game adds "sanity" as data. Avoids fatigue-in-27 and HP-in-31 being two unrelated
  hand-rolled systems.

### 3.4 Timed active effects
*Consumers: 31 "weakened" debuff, buffs, temporary traits; latent: potions, spells, weather.*

Buffs/debuffs with **clock-driven expiry**. Distinct from equipment effects (permanent *while
equipped*, §3.5) and traits (semi-permanent): these fade on their own.

- Core: `ActiveEffect(entity_id, effect_key, payload, expires_epoch)` swept by the scheduler;
  contributes to the modifier resolver while live.
- The death "weakened" debuff, a barter buff, a warmth-from-fire effect all ride this. Without it,
  each feature re-implements expiry timers.

### 3.5 Modifier resolution (runtime, stacked, capped)
*Consumers: 23 equipment effects, 24 traits/skills, 25 terrain, 27 condition, 28 pricing.*

One resolver that stacks bonuses from many sources with a **defined order and caps**. Generalizes
the doc's `EquipmentEffects.resolve()`.

- Core: collect modifiers (from equipment §3.1 `effects`, traits, active effects §3.4, region) for
  a target key (a stat, skill, or price) and resolve in buckets: **flat add → multiplier → clamp/
  cap**. Trade caps (`barter_discount ≤ 25%`), combat crit (`×2`), encumbrance multipliers, and
  skill bonuses all fit one model.
- **Never stored** — recomputed on change (`ITEM_EQUIPPED`) or lazily per command, per the
  engine-wide "never store derived stats" rule ([`combat_system.md`](combat_system.md)).
- **Surprise prevented (§4.d):** if 23 ships an additive-only summer, 28's multiplicative capped
  pricing can't reuse it. The stacking model must be defined once, now.

### 3.6 Skill-check + seedable RNG  ⚠️ audit-regression-critical
*Consumers: 24 skills, 25 search, 28 barter/appraise, 31–32 combat hit/damage.*

One `check(actor, skill, difficulty, modifiers) → outcome` helper, and — critically — a **seedable
RNG injected through `ctx`** (`ctx.rng`), never module-level `random`.

- **Surprise prevented (§4.b):** [Sprint 12](roadmap.md#sprint-12--simulation-harness-mvp-)'s audit-regression harness diffs two runs of a fixed
  script and expects identical audit trails. `random.randint` in combat/skill-checks breaks that.
  A per-run seedable `ctx.rng` makes *every* random system reproducible and testable. This is a
  cross-cutting requirement that combat, skills, and trade all silently depend on.

### 3.7 Value / ledger + atomic transfer
*Consumers: 28 coins/shops/banks, 28.4 P2P escrow, 31.2 death coin-loss, robbers.*

A **coin balance as an attribute of any holder** (player, bank account, corpse, shop till) and one
atomic check-and-transfer for coins *and* items together.

- Core: `transfer(from_holder, to_holder, coins?, stacks?)` — validates balances/ownership and
  moves in one transaction or rolls back (reuses [Sprint 14](roadmap.md#sprint-14--unify-command-lifecycle-) rollback).
- P2P trade escrow, buy/sell, deposit/withdraw, and death "drop coins into corpse" are all this op.
- **Surprise prevented (§4.c):** trade models coins as a scalar `int`; death drops coins *into a
  corpse container*. Define once that a coin balance can live on any holder (incl. a corpse), so a
  corpse isn't a special case. Escrow is "revalidate both sides hold the goods at accept-time, then
  transfer atomically" — the ledger must support that check-and-move, since offer and accept are
  two separate commands/transactions.

### 3.8 Scheduled mobile entity ("moving room")
*Consumers: 29 transit vehicles; latent: wandering NPCs, patrols, respawn placement.*

A room (or entity) whose position updates on the scheduler and interpolates for the minimap.

- Core: the state machine + position interpolation (`at_stop → in_transit → arrive`, reverse/loop)
  and the `transit_update`-style position push. Transit *line semantics* (express/local, ticket
  gating, weather grounding) are **Tier 2** ([`transit_systems.md`](transit_systems.md)); the
  moving-room carrier and its scheduler wiring are Tier 1.

### Smaller Tier 1 surface (fold into existing patterns, not new subsystems)

- **Trait registry** (24) — a registered catalog of named boon/bane modifier-bundles; a thin
  specialization of §3.1 + §3.5, same registry pattern as dialogue side-effects.
- **Keyed relationship values** (24 reputation/standing) — like `Player.flags`, a keyed
  numeric store gating conditions/prices. Extends the flags primitive; not a new subsystem.
- **`bound`/`soulbound` item flag** — see §4.e; a single field, but it's *assumed* by two docs and
  designed in none, so it must be added deliberately.

---

## 4. Cross-doc surprises caught by the vertical read

These are the concrete seams that will bite if unresolved before the feature band. Each needs a
one-time decision:

- **(a) Dual item representation.** Keeping stackables as `list[str]`/`RoomItem.quantity` while
  stateful items become `ItemInstance` taxes *every* consumer (take, drop, give, put, buy, sell,
  trade, loot, encumbrance weight-sum) with dual-mode branching. **Recommendation:** one owned-stack
  abstraction (§3.2) — `item_id + quantity + optional instance` — so consumers see one shape.
  Instances are an implementation detail behind it, not a second code path.
- **(b) Non-seedable RNG breaks audit-regression.** `combat_system.md` uses module-level
  `random`; [Sprint 12](roadmap.md#sprint-12--simulation-harness-mvp-)'s harness expects reproducible audit trails. **Recommendation:** `ctx.rng`
  seedable service (§3.6), mandated for all random resolution.
- **(c) Coins scalar vs coins-in-corpse.** `trade_economy.md` = scalar `int`; `death_resurrection.md`
  = dropped into a container. **Recommendation:** ledger balance on any holder (§3.7), corpse
  included — no special case.
- **(d) Modifier stacking undefined.** Additive (skills), multiplicative (region/quality), capped
  (barter/rep), ×2 (crit) all coexist. **Recommendation:** define the flat→mult→cap order once
  (§3.5).
- **(e) `equipped_weapon_id` vs `Player.equipment` map.** `combat_system.md` reads
  `player.equipped_weapon_id`; `inventory_equipment.md` designs a `Player.equipment` slot→ref
  dict. **These conflict.** **Recommendation:** the slot map is canonical; combat reads the
  `main_hand` slot through the resolver. Fix `combat_system.md` when [Sprint 23](roadmap.md#sprint-23--inventory--equipment) lands.
- **(f) `bound`/`soulbound` flag is assumed, not designed.** Death "keeps bound items"; trade
  "refuses bound items." Neither doc adds the field. **Recommendation:** add `Item.bound` (or a
  per-instance bind) in the [Sprint 22](roadmap.md#sprint-22--standard-item-components--definition-fields) field pass, and document what binds an item.
- **(g) Fail-open conditions for integrity gates.** See §2 — route consent/escrow/anti-dupe through
  `RuleEngine` (fails closed), not `CommandConditionRegistry` (fails open).

---

## 5. How the feature band decomposes onto Tier 1

Every feature sprint becomes **primitive (Tier 1) + standard module (Tier 2) + content (Tier 3)**:

| Feature sprint | Tier 1 it needs | Tier 2 module | Tier 3 content |
|---|---|---|---|
| 22 item state | 3.1 component model, 3.2 stacks, (f) bound | durability/light/container components | which items, values |
| 23 equipment | 3.2 slots, 3.5 resolver | encumbrance bands, standard slot set | slot list, weights |
| 24 traits/skills | 3.6 skill-check, trait registry, standing | use-based improvement curve | the skills/traits/factions |
| 25 exploration | journal, fog reveal, 3.5 (terrain mods) | search-reveal, terrain table | hidden exits, terrain |
| 27 condition | 3.3 meters, 3.4 timed effects | fatigue/sleep ruleset | drain rates, per-world toggle |
| 28 trade | 3.7 ledger + atomic transfer | shop/pricing/banks | currencies, prices, stock |
| 29 transit | 3.8 moving entity | express/local, ticket gating, weather | the lines/stops |
| 30 quests/puzzles | *(existing registries + 3.1 state)* | branch/consequence engine | the quests/puzzles |
| 31–33 combat | 3.3 HP meter, 3.4 debuff, 3.6 RNG, 3.7 (coin loss) | combat ruleset, death policy, AI | numbers, behaviors |
| 34 PvP | 3.7 escrow, (g) consent rule | PvP ruleset | per-world toggle |

Note combat — the designated first consumer of the feature-registration pattern — is the *last*
consumer of a primitive stack that 22–29 quietly build. That's the argument for engine-first.

---

## 6. Build order (engine-first)

Per the directive, build most of Tier 1 before any Tier 2. Suggested order by dependency + leverage
(open for review — sequencing is still under discussion):

1. **3.2 item location/ownership + 3.1 component model** — highest leverage; unblocks 22/23 and
   underpins containers, corpses, escrow, shop stock.
2. **3.6 seedable RNG + skill-check** — small, unblocks all random systems and keeps
   audit-regression green as combat/skills land.
3. **3.5 modifier resolver** — needed by 23/24/27/28; define stacking before the first consumer.
4. **3.3 meters + 3.4 timed effects** — pair; migrate HP onto meters as the proof.
5. **3.7 ledger + atomic transfer** — before trade/death.
6. **3.8 moving entity** — before transit; most self-contained, can slot late.

The two ⚠️ items (§3.2, §3.6) are the ones most expensive to retrofit — do them first.

---

## 7. Docs organization

The design docs sprawl across [`architecture.md`](architecture.md), [`roadmap.md`](roadmap.md), and
per-feature docs. That's fine **as long as they stay aligned and cross-linked**. Conventions:

- **`roadmap.md` is authoritative for sequencing** and links out to each feature doc from its
  sprint row. Each feature doc links back to its roadmap sprint.
- **`architecture.md` is authoritative for the built engine**; where it predates a re-sequence
  (e.g. §28's combat-first phase order) it says so and defers to the roadmap.
- **This doc (`engine_core.md`) is authoritative for the Tier boundary and Tier 1 primitive
  design.** Feature docs reference it for the primitive they consume rather than re-specifying it.
- **`docs/implemented/`** — once a feature's sprints are done *and* the mechanics are described in
  the living guides (`architecture.md`, `user_guide.md`, `admin_builder_guide.md`), move its design
  doc there to mark it historical (candidates when their sprints close: `player_authentication.md`,
  `tooling_infrastructure.md`, `world_versioning_changesets.md`, `disconnect_handling.md`). Update
  inbound links on move. **Defer the actual moves until each feature lands** ("clean up afterward"),
  so we don't break links to still-active designs.

---

*See [`roadmap.md`](roadmap.md) for sequencing, [`feature-registration.md`](feature-registration.md)
for the registration pattern these primitives extend, and the per-feature docs
([`inventory_equipment.md`](inventory_equipment.md), [`combat_system.md`](combat_system.md),
[`trade_economy.md`](trade_economy.md), [`transit_systems.md`](transit_systems.md),
[`death_resurrection.md`](death_resurrection.md)) for the use cases each primitive serves.*
</content>
</invoke>
