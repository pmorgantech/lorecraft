# Inventory, Equipment & Item State — Design

> **Status:** Design (2026-07-03). First feature to promote off [`wishlist.md`](wishlist.md)
> after the foundation gate. Implements the "Inventory & equipment 💚 (foundational)" and
> the item-state prerequisites for "Character condition", "Exploration depth", and
> "Quests & puzzles" mechanics.
>
> **Pillars this serves** (see [`wishlist.md`](wishlist.md) → *Design pillars*): equipment
> exists to gate **exploration** (light, warmth, carry capacity, skill bonuses) and **trade**
> (value, quality, containers) at least as much as combat. Design accordingly — combat stat
> bonuses are one effect among several, not the point.

---

## 1. Where we are today

Current models (`src/lorecraft/models/`):

- **`Player.inventory: list[str]`** — a flat list of item IDs. Duplicates repeat for quantity.
  No equipped state, no containers, no per-instance data.
- **`Item`** — `id, name, description, takeable, tradeable, aliases, usable_with, loot_table`.
  **No** `slot`, `weight`, `wearable`, `quality`, or `durability`.
- **`RoomItem`** — has `quantity`; item stacks on the floor already work.
- **`PlayerStats`** — six attributes (STR/AGI/VIT/INT/PRE/FOR), `max_hp`, `skills: dict`.
  Equipment is expected to feed *derived* stats (see [`combat_system.md`](combat_system.md):
  "Never store derived stats").
- **`Room.light_level: int`** and **`Exit.hidden` / `Exit.condition_flags`** already exist —
  the light/darkness and hidden-exit mechanics have partial data support to build on.

`services/inventory.py` already centralizes take/drop/give/use via a shared
find→disambiguate→act helper (Sprint 9.3) and the consolidated item matcher (Sprint 9.4).
**New commands (`wear`, `remove`, `wield`, `put`, `open`) extend that service, they don't
fork it.**

---

## 2. Scope & build order

Three layers, built in order. Each is independently shippable.

| Layer | Adds | Unblocks |
|---|---|---|
| **A. Item definition fields** | `slot`, `weight`, `wearable`, `quality`, `max_durability`, `light`, `capacity` on `Item` | equipment, encumbrance, light |
| **B. Equipment & encumbrance** | `Player.equipment` map; `wear`/`remove`/`wield`; weight totals | passive effects, combat, trade value |
| **C. Item state & containers** | per-instance item state (`ItemInstance`); `open`/`put`/`take from`; durability; nesting | puzzles, durability, lanterns, quest stashes |

Layers A+B are the "inventory & equipment" sprint. Layer C is the deferred Sprint 2.5
`open`/container/state modeling — it's the shared prerequisite for containers, durability,
light-source fuel, and mechanism puzzles, so it lives here.

---

## 3. Layer A — Item definition fields

Additive, nullable/defaulted fields on `Item` so existing world YAML keeps loading unchanged:

```python
class Item(SQLModel, table=True):
    # ... existing fields ...
    slot: str | None = None          # equip slot key (see §4); None = not equippable
    wearable: bool = False           # worn (armor/clothing) vs. wielded (weapon/tool/light)
    weight: float = 0.0              # units; drives encumbrance (§5)
    quality: str = "common"          # common|fine|superior|rare|legendary — value & trade
    max_durability: int | None = None  # None = indestructible; else current tracked per-instance (§7)
    light: int = 0                   # light radius/level this item emits when equipped/lit (§8)
    capacity: float | None = None    # if set, item is a container holding up to `capacity` weight (§6)
    effects: list[JsonObject] = Field(default_factory=list, sa_column=Column(JSON))  # passive effects (§4)
```

`effects` is a list of pluggable effect descriptors (registry-driven, mirroring the dialogue
side-effect and condition registries from [Sprint 10](roadmap.md#sprint-10--extensibility-seams-)), e.g.:

```yaml
effects:
  - type: stat_bonus     # strength +2
    stat: strength
    amount: 2
  - type: grant_trait    # while equipped, character is "warm"
    trait: warm
  - type: skill_bonus    # +10 perception
    skill: perception
    amount: 10
  - type: carry_bonus    # +20 carry capacity (a backpack worn)
    amount: 20
```

**Effects are resolved at runtime** from currently-equipped items — never persisted onto
`PlayerStats`. This matches the combat doc's derived-stat rule and lets `unwear` cleanly
reverse a bonus.

---

## 4. Layer B — Equipment slots

Slots are **data**, not hardcoded, so worlds can add slots without engine edits. A default
slot set ships in config / world meta:

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
| `light` | wielded | torch, lantern | **light (§8)** — may alias `off_hand` |

Player gains an equipment map (slot key → item id/instance):

```python
class Player(SQLModel, table=True):
    # ... existing fields ...
    equipment: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))  # slot -> item ref
```

Commands (extend `InventoryService`):

- `wear <item>` / `remove <item>` — worn items; validates `wearable` and `slot` free (or swap).
- `wield <item>` / `unwield` — `main_hand`/`off_hand`.
- `equipment` / `eq` — list equipped items by slot.

`GameContext.get_visible_entities()` and the item matcher already resolve names/aliases;
equip commands reuse that resolution. Equipping/removing emits events
(`ITEM_EQUIPPED` / `ITEM_UNEQUIPPED`) so services (combat, exploration, condition) recompute
derived state.

---

## 5. Encumbrance

Total carried weight = sum of `weight` over inventory + equipped items, minus container
reductions (§6). Bands (tunable, forgiving by default):

| Band | Threshold | Effect |
|---|---|---|
| Unburdened | ≤ capacity | none |
| Burdened | ≤ 1.5× | travel costs extra fatigue (ties to condition mechanic) |
| Overloaded | > 1.5× | cannot pick up more; travel heavily penalized |

Carry capacity derives from `PlayerStats.strength` + `carry_bonus` effects (a worn backpack).
Encumbrance is the first real consumer of the fatigue/condition system — keep the hook
(`ctx` exposes current carried weight) even if the fatigue sprint lands later.

---

## 6. Layer C — Containers & nested inventory

A container is an `Item` with `capacity` set. It holds other items up to `capacity` weight.
Containers may **reduce** effective carried weight (a "bag of holding" style reduction factor)
or simply organize.

- `put <item> in <container>` / `take <item> from <container>`.
- Worn containers (backpack in `back`) contribute `carry_bonus`; their contents count at a
  reduced rate.
- Containers can nest (a pouch in a backpack) — bounded recursion depth to avoid abuse.
- World/room chests are containers too (a `RoomItem` with `capacity`), enabling quest stashes
  and puzzle rewards.

This requires per-instance data (a specific bag holds specific items), which motivates §7.

---

## 7. Item instances & state

Flat `list[str]` item IDs can't express "*this* torch is 40% burned" or "*this* chest is
open and holds a key". Introduce a per-instance record **only for items that need state**
(stateless stackables stay as ID lists / `RoomItem` quantities — no migration churn):

```python
class ItemInstance(SQLModel, table=True):
    id: str = Field(primary_key=True)
    item_id: str = Field(foreign_key="item.id", index=True)   # definition
    owner_type: str        # "player" | "room" | "container"
    owner_id: str          # player id / room id / container instance id
    durability: int | None = None   # current; from Item.max_durability
    is_open: bool = False            # containers, chests, doors-as-items
    lit: bool = False                # light sources
    state: JsonObject = Field(default_factory=dict, sa_column=Column(JSON))  # puzzle/mechanism state
```

- **Durability** decrements on use / weather exposure; at 0 the item breaks or becomes
  "broken" (repairable via a service NPC — a trade hook). Drives consumable trade.
- **`lit`** + `Item.light` + `Room.light_level` implement the light/darkness exploration
  mechanic: in a dark room, only a lit light source reveals exits/items.
- **`state`** is the generic bag for mechanism puzzles (lever positions, dial codes) — read by
  pluggable conditions, written by pluggable side effects (same registries as dialogue).

`open <item>` toggles `is_open` for containers/chests; puzzle mechanisms use their own
verbs registered via the command/condition registries.

---

## 8. Light & darkness (exploration payoff)

Already half-modeled (`Room.light_level`). Rule: if `Room.light_level == 0` (or "dark") and
the player has no lit light source (equipped item with `light > 0` and `lit == True`), the
room description hides exits and items ("It is pitch black. You need a light."). A lit lantern
consumes fuel (durability) over world-clock ticks — a gentle resource loop that makes
exploration deliberate and creates demand for oil/torches (trade).

---

## 9. Effects resolution (runtime, not stored)

A single `EquipmentEffects.resolve(player)` helper walks equipped items' `effects`, sums
`stat_bonus`/`skill_bonus`/`carry_bonus`, and collects granted traits. Consumers:

- **Combat** — reads derived STR/armor (per `combat_system.md`).
- **Exploration** — reads derived `perception`/`survival` skills for hidden-exit and terrain
  checks; reads granted traits (`warm`, `sure-footed`).
- **Encumbrance** — reads `carry_bonus`.
- **Trade** — reads `quality` for pricing.

Never write these back to `PlayerStats`. Recompute on `ITEM_EQUIPPED`/`ITEM_UNEQUIPPED` or
lazily per command.

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
```

Content validators (`lorecraft.tools.validators`) gain checks: unknown `slot`, `wearable`
item with no `slot`, `capacity` on a non-takeable item, `effects` referencing unknown
stat/skill/trait keys.

---

## 11. Testing

- **Unit:** slot occupancy/swap, encumbrance bands, effects resolution (equip → bonus →
  unequip reverses), container capacity limits, durability→break, light-gated visibility.
- **Integration:** `wear`/`remove`/`wield`/`put`/`open` through `POST /command` and `/ws`;
  equipment survives save/load and disconnect/reconnect.
- **Simulation:** two players contending for a single wearable; a lantern burning out mid-session.
- **Content lint:** the validator checks above.

---

## 12. Non-goals (for this design)

- Set bonuses / socketing / enchanting — later, if demand appears.
- Full crafting/production — see [`wishlist.md`](wishlist.md) (🤔, deferred).
- Auction house / player shops — trade design, separate.
- Wear-slot combat balance tuning — deferred to the combat sprints ([`combat_system.md`](combat_system.md)).

---

*See [`roadmap.md`](roadmap.md) for the sprint breakdown and [`wishlist.md`](wishlist.md) for
the full mechanics menu this is the first slice of.*
