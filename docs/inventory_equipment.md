# Inventory, Equipment & Item State — Design

> **Status:** Implementation-ready design (2026-07-03; revised same day for Tier 1 alignment).
> First feature to promote off [`wishlist.md`](wishlist.md) after the foundation gate.
> Implements the "Inventory & equipment 💚 (foundational)" and the item-state prerequisites for
> "Character condition", "Exploration depth", and "Quests & puzzles" mechanics.
>
> **Tier 1 dependencies (build first — [`engine_core.md`](engine_core.md)):** this feature is
> the first Tier 2 consumer of the **item location/ownership model** (`ItemStack` +
> `ItemLocationService`, engine_core §3.2,
> [Sprint 16](roadmap.md#sprint-16--item-locationownership--instance-state)), the **component
> registry** (`ItemInstance` + `ComponentDef`, §3.1, Sprint 16), and the **modifier resolver**
> (§3.5, [Sprint 18](roadmap.md#sprint-18--modifier-resolution)). Schemas for stacks, instances,
> holders, and modifiers live in `engine_core.md` and are **not** re-specified here; this doc
> defines what the inventory/equipment feature *registers and adds on top*.
>
> **Pillars this serves** (see [`wishlist.md`](wishlist.md) → *Design pillars*): equipment
> exists to gate **exploration** (light, warmth, carry capacity, skill bonuses) and **trade**
> (value, quality, containers) at least as much as combat. Design accordingly — combat stat
> bonuses are one effect among several, not the point.

---

## 1. Where we build from (after Sprint 16)

By the time this feature starts, Tier 1 has already replaced the old item storage:

- **`ItemStack`** rows are the *only* item location representation — `Player.inventory` and
  `RoomItem` no longer exist (engine_core §3.2). Carried = `Location("player", id)`; on the
  floor = `Location("room", id)`; equipped = `Location("player", id, slot="head")`.
- **`ItemInstance`** carries per-instance `state`, keyed by component name (engine_core §3.1).
- **`Item.bound: bool`** already exists (Sprint 16); this feature registers its enforcement.
- **`PlayerStats`** — six attributes (STR/AGI/VIT/INT/PRE/FOR), `max_hp`, `skills: dict`.
  Equipment feeds *derived* values via the modifier resolver — never stored back.
- **`Room.light_level: int`** and **`Exit.hidden` / `Exit.condition_flags`** already exist —
  the light/darkness and hidden-exit mechanics have partial data support to build on.

`services/inventory.py` centralizes take/drop/give/use over stacks (rewired in Sprint 16) via
the shared find→disambiguate→act helper and the consolidated item matcher. **New commands
(`wear`, `remove`, `wield`, `put`, `open`) extend that service, they don't fork it.**

---

## 2. Scope & build order

Three layers, built in order. Each is independently shippable.

| Layer | Adds | Unblocks |
|---|---|---|
| **A. Item definition fields** ([Sprint 22](roadmap.md#sprint-22--standard-item-components--definition-fields).1) | `slot`, `weight`, `wearable`, `quality`, `max_durability`, `light`, `capacity`, `effects` on `Item` | equipment, encumbrance, light |
| **B. Equipment & encumbrance** ([Sprint 23](roadmap.md#sprint-23--inventory--equipment).1–.2) | slot-bearing stacks; `wear`/`remove`/`wield`; carry capacity via resolver | passive effects, combat, trade value |
| **C. Standard components & containers** ([Sprint 22](roadmap.md#sprint-22--standard-item-components--definition-fields).2 + [Sprint 23](roadmap.md#sprint-23--inventory--equipment).3) | `durability`/`openable`/`lit`/`container`/`mechanism` components; `open`/`put`/`take from`; nesting | puzzles, durability, lanterns, quest stashes |

Layer C is the deferred Sprint 2.5 `open`/container/state modeling — the shared prerequisite
for containers, durability, light-source fuel, and mechanism puzzles.

---

## 3. Layer A — Item definition fields

Additive, nullable/defaulted fields on `Item` so existing world YAML keeps loading unchanged
(`bound` arrives with Sprint 16; the rest land here):

```python
class Item(SQLModel, table=True):
    # ... existing fields ...
    slot: str | None = None          # equip slot key (see §4); None = not equippable
    wearable: bool = False           # worn (armor/clothing) vs. wielded (weapon/tool/light)
    weight: float = 0.0              # units; drives encumbrance (§5)
    quality: str = "common"          # common|fine|superior|rare|legendary — value & trade
    max_durability: int | None = None  # None = indestructible; else tracked per-instance (§7)
    light: int = 0                   # light radius/level this item emits when equipped & lit (§8)
    capacity: float | None = None    # if set, item is a container holding up to `capacity` weight (§6)
    bound: bool = False              # Sprint 16 field: can't be dropped/sold/traded; kept on death
    effects: list[JsonObject] = Field(default_factory=list, sa_column=Column(JSON))  # (§9)
```

`effects` is a list of pluggable **effect descriptors** (registry-driven, mirroring the
dialogue side-effect registries from
[Sprint 10](roadmap.md#sprint-10--extensibility-seams-)), e.g.:

```yaml
effects:
  - { type: stat_bonus,  stat: strength,     amount: 2 }
  - { type: grant_trait, trait: warm }
  - { type: skill_bonus, skill: perception,  amount: 10 }
  - { type: carry_bonus, amount: 20 }        # a worn backpack
```

Each descriptor `type` is registered with a compiler to Tier 1 terms (§9): `stat_bonus` →
`Modifier(key="stat.strength", kind="add", amount=2)`; `skill_bonus` →
`Modifier(key="skill.perception", kind="add", amount=10)`; `carry_bonus` →
`Modifier(key="carry_capacity", kind="add", amount=20)`; `grant_trait` feeds the trait
source, not a modifier. Unknown descriptor types are a **content-lint error**, not a runtime
fallthrough.

---

## 4. Layer B — Equipment slots

Slots are **data**, not hardcoded, so worlds can add slots without engine edits. A default
slot set ships as feature config, overridable in world meta:

| Slot key | Kind | Typical item | Non-combat effect example |
|---|---|---|---|
| `head` | worn | hat, helm | warmth, light (miner's helm) |
| `face` | worn | mask, goggles | see-in-smoke, disguise |
| `neck` | worn | amulet | grant_trait |
| `shoulders` | worn | cloak | warmth, weather protection |
| `torso` | worn | tunic, armor | warmth, armor |
| `back` | worn | backpack | **carry_bonus** (container, §6) |
| `hands` | worn | gloves | skill_bonus (lockpicking) |
| `finger_l` / `finger_r` | worn | ring | grant_trait, stat_bonus |
| `waist` | worn | belt | container slots |
| `legs` | worn | trousers | warmth |
| `feet` | worn | boots | terrain traversal (climbing) |
| `main_hand` | wielded | weapon, tool | combat; tools gate actions (pick, torch) |
| `off_hand` | wielded | shield, lantern | armor; **light source** |

**Storage (decided — supersedes the earlier `Player.equipment` JSON-map draft and
`combat_system.md`'s old `equipped_weapon_id`):** equipped-ness **is a location**. Wearing a
helm is `ItemLocationService.move(stack, Location("player", player_id, slot="head"), 1)`;
removing it moves the stack back to `slot=None`. There is no equipment column of any kind —
one storage model for carried, equipped, and contained (engine_core §3.2, §4.e).

This feature registers with the Tier 1 holder registry:

- a **move validator on `player`** for `slot is not None`: slot key must be in the configured
  slot set (`ValidationError`), the item must be `wearable` (worn slots) or wieldable
  (`main_hand`/`off_hand`), the item's `slot` must match (rings may go in either finger slot —
  the validator owns that mapping), and the slot must be empty (`ConflictError`; the `wear`
  command offers swap by first moving the occupant out).
- **rules (fail-closed, engine_core §2)**: `bound` items refuse `drop`/`give`/`sell` via a
  `RuleEngine` rule checked at the command layer — not inside `move()`.

Commands (extend `InventoryService`):

- `wear <item>` / `remove <item>` — worn items.
- `wield <item>` / `unwield` — `main_hand`/`off_hand`.
- `equipment` / `eq` — list equipped items by slot (reads `stacks_for_owner`, `slot != None`).

Equipping/removing emits **new `GameEvent` members added in this sprint**: `ITEM_EQUIPPED` /
`ITEM_UNEQUIPPED` (`player_id, item_id, slot, instance_id?`) so combat, exploration, and
condition recompute derived state.

---

## 5. Encumbrance

Total carried weight = Σ `Item.weight × quantity` over all the player's stacks (loose,
equipped, and container contents — reduced rates per §6). Bands (tunable, forgiving):

| Band | Threshold | Effect |
|---|---|---|
| Unburdened | ≤ capacity | none |
| Burdened | ≤ 1.5× | travel costs extra fatigue (ties to condition mechanic) |
| Overloaded | > 1.5× | cannot pick up more; travel heavily penalized |

Carry capacity is **resolved, never stored** (engine_core §3.5):
`resolve_for(session, player, "carry_capacity", base=carry_base(strength))` — the equipment
modifier source contributes `carry_bonus` descriptors automatically. "Cannot pick up more" is
this feature's move validator on the `player` holder (mechanical, Tier 1 hook); the fatigue
cost lands with [Sprint 27](roadmap.md#sprint-27--character-condition-fatigue--sleep) but the
band computation ships here.

---

## 6. Layer C — Containers & nested inventory

A container is an `Item` with `capacity` set — which makes the **`container` component**
(§7) apply, so every container is instanced. Contents are ordinary stacks at
`Location("container", <instance_id>)` — **never** serialized into instance state.

- `put <item> in <container>` / `take <item> from <container>` — both are `move()` calls.
- Worn containers (backpack in `back`) contribute `carry_bonus`; their contents count at a
  reduced rate (feature config; the weight sum in §5 applies it).
- Nesting works naturally (a pouch's stack lives at the backpack's container location);
  Tier 1's cycle guard (engine_core §3.2 invariant 5) prevents a bag containing itself, and
  this feature's container move-validator enforces a max nesting depth (default 3) and
  capacity/open checks.
- World/room chests: the YAML loader `spawn()`s the chest item into the room; because the
  container component applies, it gets an instance — quest stashes and puzzle rewards are
  stacks inside it.

---

## 7. Standard components (registered by this feature)

Per-instance state uses the Tier 1 component registry (engine_core §3.1) — instance `state`
is keyed by component name; there are **no typed columns** on `ItemInstance`. This feature
registers the standard set:

| Component | `applies_to` | Initial state | Read/written by |
|---|---|---|---|
| `durability` | `item.max_durability is not None` | `{"current": item.max_durability}` | use/weather decrements; at 0 → item becomes broken (repair = trade hook) |
| `openable` | container or `openable` flag in YAML | `{"open": false}` | `open`/`close` commands; container move-validator requires open |
| `lit` | `item.light > 0` | `{"lit": false}` | `light`/`extinguish`; fuel = durability drain per world tick while lit |
| `container` | `item.capacity is not None` | `{}` (contents are stacks, not state) | capacity/nesting validator |
| `mechanism` | explicit YAML `mechanism:` block | the block's initial values | pluggable conditions/side effects (puzzles, [Sprint 30](roadmap.md#sprint-30--quests--puzzles-depth)) |

Each ships a `validate` for content lint. A stateless stackable (coin, salt sack) matches no
component and stays a fungible quantity-N stack — no instance, no churn.

---

## 8. Light & darkness (exploration payoff)

Already half-modeled (`Room.light_level`). Rule: if `Room.light_level == 0` and the player
has no **equipped** item with `light > 0` whose instance state has `lit == true`, the room
description hides exits and items ("It is pitch black. You need a light."). A lit lantern
drains durability on world-clock ticks (an `TIME_ADVANCED` handler registered by this
feature) — a gentle resource loop that makes exploration deliberate and creates demand for
oil/torches (trade).

---

## 9. Effects resolution (runtime, not stored)

**Superseded draft note:** the earlier `EquipmentEffects.resolve()` helper is replaced by the
Tier 1 modifier resolver (engine_core §3.5). This feature ships two registrations:

1. an **equipment `ModifierSource`**: walk the player's `slot != None` stacks, compile each
   item's `effects` descriptors into `Modifier`s (see §3) with `source=f"item:{item.id}"`;
2. an **equipment trait source**: `grant_trait` descriptors → the Tier 1 trait registry.

Consumers simply call `resolve_for(...)` with the right key:

- **Combat** — `stat.strength`, armor keys (per [`combat_system.md`](combat_system.md)).
- **Exploration** — `skill.perception` / `skill.survival` for hidden-exit and terrain checks;
  granted traits (`warm`, `sure-footed`).
- **Encumbrance** — `carry_capacity` (§5).
- **Trade** — `quality` multiplies price (that's the trade module's own pipeline, not a
  modifier — see [`trade_economy.md`](trade_economy.md) §3).

Never write derived values back to `PlayerStats`. Recompute lazily per command (the resolver
is never cached — engine_core §3.5); `ITEM_EQUIPPED`/`ITEM_UNEQUIPPED` exist for services
that keep UI state.

---

## 10. World YAML

Additive keys on item definitions; old worlds load unchanged:

```yaml
items:
  - id: miners_helm
    name: "miner's helm"
    slot: head
    wearable: true
    weight: 2.0
    quality: fine
    light: 2
    effects:
      - { type: skill_bonus, skill: perception, amount: 5 }
  - id: worn_backpack
    name: "worn backpack"
    slot: back
    wearable: true
    weight: 1.5
    capacity: 40
    effects:
      - { type: carry_bonus, amount: 40 }
  - id: brass_lantern
    name: "brass lantern"
    slot: off_hand
    wearable: false
    weight: 1.0
    light: 3
    max_durability: 500      # fuel ticks
  - id: sealed_letter
    name: "sealed letter"
    bound: true              # quest item: can't be dropped, sold, or lost on death
```

Content validators (`lorecraft.tools.validators`) gain checks: unknown `slot`, `wearable`
item with no `slot`, `capacity` on a non-takeable item, unknown `effects` descriptor `type`,
descriptors referencing unknown stat/skill/trait keys, plus each component's `validate` over
any YAML-declared initial state (engine_core §3.1).

---

## 11. Testing

- **Unit:** slot occupancy/swap via move-validator, encumbrance bands, descriptor→modifier
  compilation (equip → bonus → unequip reverses), container capacity/nesting/open checks,
  durability→break, light-gated visibility, bound-item rule refusals.
- **Integration:** `wear`/`remove`/`wield`/`put`/`open` through `POST /command` and `/ws`;
  equipment survives save/load and disconnect/reconnect (equipment is stacks, so the Sprint 16
  save format already covers it — assert the slot survives).
- **Simulation:** two players contending for a single wearable; a lantern burning out
  mid-session (scheduler-driven durability drain observed over a real socket).
- **Content lint:** the validator checks above.

---

## 12. Non-goals (for this design)

- Set bonuses / socketing / enchanting — later, if demand appears.
- Full crafting/production — see [`wishlist.md`](wishlist.md) (🤔, deferred).
- Auction house / player shops — trade design, separate.
- Wear-slot combat balance tuning — deferred to the combat sprints ([`combat_system.md`](combat_system.md)).

---

*See [`engine_core.md`](engine_core.md) §3.1–§3.2/§3.5 for the primitives this feature
consumes, [`roadmap.md`](roadmap.md) for the sprint breakdown, and [`wishlist.md`](wishlist.md)
for the full mechanics menu this is the first slice of.*
