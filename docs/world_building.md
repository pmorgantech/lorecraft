---
kindle_doc_weaver: ignore
---

# Building Worlds with YAML

This guide explains how to design and author game worlds in Lorecraft using YAML. It covers rooms, exits, items, and world structure.

## Table of Contents

1. [World File Structure](#world-file-structure)
2. [Rooms](#rooms)
3. [Exits](#exits)
4. [Items](#items)
5. [Room Items](#room-items)
6. [World Design Tips](#world-design-tips)
7. [Example: Small Town](#example-small-town)

---

## World File Structure

A world YAML file has these top-level sections:

```yaml
# rooms: List of room definitions
rooms:
  - id: village_square
    # ... room fields

# items: List of item definitions
items:
  - id: iron_sword
    # ... item fields

# room_items: Placement of items in rooms
room_items:
  - room_id: village_square
    item_id: iron_sword
    quantity: 1

# npcs: NPC definitions (see dialogue_npcs_quests.md)
npcs:
  - id: blacksmith_thor
    # ... npc fields

# dialogue_trees: Dialogue definitions (see dialogue_npcs_quests.md)
dialogue_trees:
  - id: blacksmith_dialogue
    # ... dialogue fields

# quests: Quest definitions (see dialogue_npcs_quests.md)
quests:
  - id: fetch_ore
    # ... quest fields
```

---

## Rooms

Rooms are locations in your world. They form the connected graph that players navigate.

### Basic Room Definition

```yaml
rooms:
  - id: village_square
    name: The Village Square of Ashmoore
    description: >-
      Cobblestones worn smooth by a hundred years of market-day boots radiate
      outward from a mossy stone well at the centre. A weathervane shaped like
      a rearing stallion creaks overhead.
    map_x: 4
    map_y: 8
    area_id: town
    light_level: 1
    exits:
      - direction: north
        target_room_id: blacksmith_forge
      - direction: east
        target_room_id: market_stalls
```

### Room Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | Unique identifier (snake_case) |
| `name` | string | ✓ | Display name |
| `description` | string | ✓ | Long description shown on entry |
| `map_x` | integer | ✓ | X coordinate for mapping |
| `map_y` | integer | ✓ | Y coordinate for mapping |
| `map_z` | integer | | Floor/level for mapping (default: 0 — "ground floor") |
| `area_id` | string | | Area grouping (for organization) |
| `light_level` | integer | | 0 = dark, 1 = lit (default: 1) |
| `is_active` | boolean | | Room accessible (default: true) |
| `fallback_room_id` | string | | Room to return to if disconnected |
| `version` | integer | | Schema version (default: 1) |
| `flags` | object | | Custom flags for this room |
| `terrain` | string | | `normal`/`road`/`forest`/`mountain`/`swamp`/`water` (default: `normal`) — see Terrain below |
| `safe_rest` | boolean | | `sleep` here is always reliable (default: `false`) — see Safe Rest below |
| `disabled_commands` | array | | Commands not allowed here |
| `exits` | array | | Connections to other rooms |

### Description Best Practices

Use multi-line descriptions with `>-` for readability:

```yaml
description: >-
  This is a long description that spans
  multiple lines. It paints a vivid picture
  of the location and sets the mood.
```

YAML will join lines with spaces, so you can format naturally.

### Map Coordinates

Use a consistent coordinate system within your world:

```yaml
# Good: organized layout
rooms:
  - id: village_square
    map_x: 4
    map_y: 8
  - id: blacksmith_forge
    map_x: 4
    map_y: 9    # North of square
  - id: market_stalls
    map_x: 5
    map_y: 8    # East of square
```

Consider drawing your map on grid paper first. Y increases northward, X increases eastward (standard cartography).

### Multiple Floors/Levels

`map_z` (default `0`) lets rooms on different floors reuse the same `(map_x, map_y)`
footprint — a cellar directly below the village square, or an upper gallery above a
hall — without overlapping on the minimap. The player-facing minimap and full-map
modal only ever plot rooms on the current room's `map_z`; connect floors with a
normal `up`/`down` exit (the exit still works exactly like any other — `map_z`
only affects what's *drawn*, not traversal):

```yaml
rooms:
  - id: village_square
    map_x: 4
    map_y: 8
    # map_z omitted -> 0 (ground floor)
    exits:
      - direction: down
        target_room_id: square_cellar
  - id: square_cellar
    map_x: 4
    map_y: 8
    map_z: -1
    exits:
      - direction: up
        target_room_id: village_square
```

### Light Levels

Rooms can have different light:

```yaml
light_level: 0  # Dark (e.g., caves, cellars)
light_level: 1  # Normal/lit (default)
```

Dark rooms may affect gameplay mechanics (e.g., requiring light sources).

### Room Flags

Custom flags enable complex room mechanics:

```yaml
flags:
  is_resting_place: true
  weather_exposed: true
  flooded: false
```

Access in code via `room.flags`.

### Disabled Commands

Prevent certain actions in specific rooms:

```yaml
disabled_commands:
  - "attack"
  - "cast_spell"
```

### Terrain

`terrain` optionally gates entry on a skill and layers an extra sentence onto `look`:

```yaml
- id: mountain_pass
  name: "Mountain Pass"
  terrain: mountain   # requires survival >= 20 (see game/terrain.py's registry)
```

Standard terrain: `normal` (no effect), `road` (flavor only), `forest` (flavor only),
`mountain`/`swamp`/`water` (each requires a minimum `survival` skill level). Unknown
terrain names fail content validation.

### Safe Rest

`safe_rest: true` marks a room (an inn, a guarded camp) where `sleep` always succeeds —
a full stamina restore, no interruption risk, regardless of weather:

```yaml
- id: wandering_crow_inn
  name: "The Wandering Crow Inn"
  safe_rest: true
```

Everywhere else, `sleep` is a survival skill check (harder in cold weather — `snow`,
`blizzard`, `fog` — unless the player has enough resolved `warmth`, see the Effects
section's `warmth_bonus`); on failure the sleep is interrupted for a shorter, partial
rest. `rest` and `camp` are unaffected by `safe_rest` — they work anywhere.

---

## Exits

Exits define how rooms connect. Each exit is one-directional.

### Basic Exit

```yaml
exits:
  - direction: north
    target_room_id: blacksmith_forge
```

### Exit Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `direction` | string | ✓ | Direction: north, south, east, west, up, down |
| `target_room_id` | string | ✓ | Room this exit leads to |
| `locked` | boolean | | If true, requires key to pass (default: false) |
| `key_item_id` | string | | Item ID that unlocks this exit |
| `hidden` | boolean | | If true, exit not shown in normal descriptions (default: false) |
| `condition_flags` | array | | Flags required to use this exit |

### Two-Way Connections

Exits are one-directional. For two-way movement, define both:

```yaml
rooms:
  - id: room_a
    exits:
      - direction: east
        target_room_id: room_b

  - id: room_b
    exits:
      - direction: west
        target_room_id: room_a
```

### Locked Doors

```yaml
- id: inn_cellar
  name: "The Inn Cellar"
  exits:
    - direction: up
      target_room_id: wandering_crow_inn
    - direction: down
      target_room_id: secret_vault
      locked: true
      key_item_id: cellar_key
```

The player must have `cellar_key` in inventory to pass.

### Conditional Exits

Use flags to gate movement:

```yaml
- direction: north
  target_room_id: forbidden_tower
  condition_flags: ["blessed_by_priest"]
```

### Hidden Exits

Exits can be hidden from descriptions but still usable:

```yaml
- direction: down
  target_room_id: secret_basement
  hidden: true
```

The player must try the command directly (e.g., "go down") without seeing it suggested.

---

## Items

Items are objects that can be picked up, traded, or interacted with.

### Basic Item Definition

```yaml
items:
  - id: iron_sword
    name: Iron Sword
    description: A well-balanced blade, sharp enough to bite steel.
    takeable: true
    tradeable: true
```

### Item Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | Unique identifier (snake_case) |
| `name` | string | ✓ | Display name |
| `description` | string | ✓ | Description shown when examining |
| `takeable` | boolean | | Can player pick this up (default: true) |
| `tradeable` | boolean | | Can player trade/drop this (default: true) |
| `bound` | boolean | | Soulbound: can't be dropped/given/sold (default: false) |
| `usable_with` | array | | IDs of items this can combine with |
| `loot_table` | object | | Items dropped when destroyed/used |
| `slot` | string | | Equip slot (`head`, `main_hand`, `finger`, etc. — see Equipment below) |
| `wearable` | boolean | | Worn (armor/clothing) vs. wielded (weapon/tool/light) (default: false) |
| `weight` | float | | Drives encumbrance (default: 0.0) |
| `quality` | string | | `common`/`fine`/`superior`/`rare`/`legendary` (default: `common`) |
| `max_durability` | integer | | Tracked per-instance; omit for indestructible items |
| `light` | integer | | Light emitted while equipped and lit (default: 0) |
| `capacity` | float | | Makes the item a container holding up to this much weight |
| `effects` | array | | Effect descriptors — see Effects below |
| `value` | integer | | Base coin value; shop prices derive from `value × quality` (default: 0 — see Shops below) |
| `category` | string | | Trade category (e.g. `trade_good`, `food`); gates whether a shop's `buys_categories` will buy it |

### Equipment Slots

`slot` places an item in one of the equip slots: `head`, `face`, `neck`, `shoulders`,
`torso`, `back`, `hands`, `finger_l`, `finger_r`, `waist`, `legs`, `feet` (worn — set
`wearable: true`), or `main_hand`/`off_hand` (wielded — leave `wearable: false`). Rings
use the generic `slot: finger`; the `wear` command places them in whichever of
`finger_l`/`finger_r` is free.

```yaml
items:
  - id: miners_helm
    name: "miner's helm"
    slot: head
    wearable: true
    weight: 2.0
    quality: fine
    effects:
      - { type: skill_bonus, skill: perception, amount: 5 }

  - id: brass_lantern
    name: "brass lantern"
    slot: off_hand
    wearable: false
    weight: 1.0
    light: 3
    max_durability: 500      # fuel: drains 1 per world-clock tick while lit
```

### Effects

Each `effects` entry is a descriptor compiled into a Tier 1 modifier or trait grant at
runtime — equipment bonuses are resolved live, never stored on the player:

| Type | Fields | Effect |
|------|--------|--------|
| `stat_bonus` | `stat`, `amount` | Adds to a stat (`strength`, `agility`, `vitality`, `intellect`, `presence`, `fortitude`) |
| `skill_bonus` | `skill`, `amount` | Adds to a named skill |
| `carry_bonus` | `amount` | Extends carry capacity (e.g. a worn backpack) |
| `grant_trait` | `trait` | Grants a named trait while equipped |
| `warmth_bonus` | `amount` | Adds resolved warmth while equipped — offsets cold-weather sleep risk (see Safe Rest above) |
| `heal` | `meter`, `amount`, `message?` | **One-shot on consume** (`eat`/`drink`): instantly adjusts a meter (`hp`, `fatigue`, …) by `amount`. Only fires on a `food`/`drink` item. |
| `apply_effect` | `effect_key`, `duration_ticks?`, `payload?`, `message?` | **One-shot on consume**: applies a timed active effect (buff) to the drinker. Buff keys registered by the `consumables` feature: `fortified` (+strength), `keen_minded` (+perception); `payload.amount` sets magnitude (default 2). |

The `heal`/`apply_effect` descriptors are **one-shot** — they fire once when the item is
eaten or drunk (and one unit is destroyed), unlike the equip-time bonuses above which apply
continuously while worn. They only take effect on an item with `category: food` (eaten) or
`category: drink` (drunk/quaffed).

```yaml
- id: worn_backpack
  slot: back
  wearable: true
  capacity: 40
  effects:
    - { type: carry_bonus, amount: 40 }

- id: healing_tonic
  category: drink
  effects:
    - { type: heal, meter: hp, amount: 40, message: "Warmth closes your wounds." }

- id: draught_of_vigor
  category: drink
  effects:
    - { type: apply_effect, effect_key: fortified, duration_ticks: 60, payload: { amount: 2 } }
```

### Shops

An NPC becomes a vendor by adding a `shop` block. Prices are derived at runtime from each
item's `value × quality` (never stored) and shown to players via `list`/`shop`:

```yaml
npcs:
  - id: shopkeep_bram
    name: Bram
    description: A weathered trader.
    home_room_id: general_store
    shop:
      name: "Saltmarsh General Store"
      buys_categories: [trade_good, food]  # what the shop will buy FROM players
      sell_ratio: 0.5                       # fraction of buy price paid when buying from players
      region_mult: 1.0                      # per-shop adjustment ON TOP of its area's region_mult
      starting_coins: 300                   # the shop's cash on hand; it can run dry
      stock:
        - item_id: salt_sack
          quantity: 40         # finite; -1 = unlimited (never runs out, no restock needed)
          restock_to: 40        # target quantity a restock jumps to
          restock_every_ticks: 720  # world-clock ticks between restocks; 0 = never restocks
        - item_id: ferry_token
          quantity: -1
```

Commands: `list`/`shop` (show stock and prices), `buy <item> [qty]`, `sell <item> [qty]`
(only if `tradeable`, not `bound`, and `category` is in the shop's `buys_categories`),
`appraise <item>` (any carried or nearby item, shop or not — shows an estimated value).
`bartering` skill and reputation with the vendor both shave a capped discount off buy
prices. A shop's cash is real and finite — sell too much in one place and it runs dry
until it restocks; sold items are consumed, not held as physical stock. Stock with a
`restock_every_ticks` runs dry-then-refills on its own schedule (a background sweep,
independent of anyone visiting); `quantity: -1` opts an item out of restocking entirely
since it never runs out.

### Regional pricing

An optional top-level `economy.regions` block gives each room's `area_id` a price
multiplier and per-item bias, so the same good costs different amounts in different
places — the core of the buy-low/sell-high loop:

```yaml
economy:
  regions:
    - area_id: coast
      region_mult: 1.0
      bias: { salt_sack: 0.6, furs: 1.4 }   # cheap salt, dear furs, on the coast
    - area_id: highlands
      region_mult: 1.1
      bias: { salt_sack: 1.5, furs: 0.7 }   # the reverse inland
```

Effective price = `value × quality_mult × area's region_mult × shop's region_mult ×
item's bias × demand_mult × discounts`. Demand rises as a shop's stock depletes and
falls as it's flooded (bounded, so prices never run away) — dumping goods on one town
tanks the local price, rewarding players who spread sales across the network. A room
whose area has no `economy.regions` entry (or a world with no `economy:` block at all)
just uses a neutral 1.0 multiplier.

### Banks

An NPC becomes a bank branch by adding a `bank` block — just a name, no stock or
pricing:

```yaml
npcs:
  - id: teller_maren
    name: Maren
    description: A careful bookkeeper.
    home_room_id: saltmarsh_bank
    bank:
      name: "Saltmarsh Bank"
```

Commands: `deposit <amount>` and `withdraw <amount>` only work in a branch's room;
`balance` (carried + banked) works anywhere. Banked money is a separate ledger holder
from carried money — safe from death and robbery, since that code only ever touches
what a player is carrying. **One logical account, many branches**: deposit at one
branch, withdraw at another — the whole point of banks as travel/trade infrastructure,
not just a vault.

### Transit lines

A top-level `transit.lines` block defines a ferry/rail/balloon/caravan line — a physical
vehicle (a `Room` players ride inside) that cycles between stations on its own schedule,
driven by the same `MobileRouteService` scheduler that runs any moving room (Sprint 21).
Once defined, a line loads and starts automatically at server startup: `board [line]`
(at a station, doors open) and `disembark`/`leave` (aboard, at a stop) move players in
and out of the vehicle room; `schedule [line]`/`timetable` shows stop order and current
status. Minimap animation of the live vehicle position is Sprint 29.3's job.

```yaml
transit:
  lines:
    - id: coastal_ferry
      name: Coastal Ferry
      mode: ferry               # "ferry"/"rail"/"balloon"/"caravan"/... (open-ended)
      service_type: local        # "local" (boards every stop) or "express"
      vehicle_room_id: ferry_deck  # a Room with NO exits -- board/disembark only
      ticket_item_id: ferry_token  # required to board; omit for a free line
      ticket_consumed: true       # false = reusable pass
      reverses: true              # A->B->C then C->B->A; loop: true jumps C->A instead
      animate_minimap: true
      weather_sensitive: true
      blocking_weather: [fog]     # must be states clock/weather.py's WEATHER_TABLE produces
      stops:
        - { room_id: saltmarsh_pier, sequence: 0, dwell_ticks: 5, travel_ticks: 20 }
        - { room_id: gull_rock,      sequence: 1, dwell_ticks: 5, travel_ticks: 25 }
        - { room_id: harbor_end,     sequence: 2, dwell_ticks: 8, travel_ticks: 0 }
```

`sequence` must be contiguous from 0; an `express` line needs at least 2 stops with
`boarding: true` (the default — set `boarding: false` on a stop an express line passes
through without opening its doors, purely as an animation waypoint). `travel_ticks` on
the last stop is unused (there's no next leg) but still required by the schema.

### Containers

Setting `capacity` makes an item a container: it must be `open`ed before anything can be
`put`/`take`n, has a maximum nesting depth of 3, and its own weight limit.

```yaml
- id: wooden_chest
  name: "wooden chest"
  takeable: false
  capacity: 50
```

### Takeable vs Tradeable

```yaml
# Normal item: can pick up and drop
- id: wooden_staff
  takeable: true
  tradeable: true

# Quest item: pick up but can't drop/trade
- id: magical_amulet
  takeable: true
  tradeable: false

# Scenery: can't pick up
- id: stone_well
  takeable: false
  tradeable: false
```

### Item Combinations

```yaml
items:
  - id: iron_ore
    usable_with:
      - hammer
      - anvil
```

### Loot Tables

Items can contain other items when destroyed:

```yaml
items:
  - id: treasure_chest
    description: "A locked chest filled with riches."
    takeable: false
    loot_table:
      gold_coin: 50
      silver_ring: 1
      ancient_scroll: 1
```

### Item Descriptions

Write evocative descriptions that convey weight, texture, and history:

```yaml
- id: tattered_journal
  name: "Tattered Journal"
  description: >-
    A leather-bound journal with water-stained pages. The handwriting
    deteriorates toward the end, becoming frantic and illegible. The last
    legible entry reads: "They know I'm here..."
```

---

## Room Items

Place items in rooms at world start using `room_items`.

### Placement

```yaml
room_items:
  - room_id: blacksmith_forge
    item_id: iron_sword
    quantity: 1
  - room_id: market_stalls
    item_id: copper_coin
    quantity: 5
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `room_id` | string | ✓ | Room containing the item |
| `item_id` | string | ✓ | Item ID |
| `quantity` | integer | | Number of this item (default: 1) |

### Multiple Items in One Room

```yaml
room_items:
  - room_id: forest_clearing
    item_id: mushroom
    quantity: 3
  - room_id: forest_clearing
    item_id: broken_staff
    quantity: 1
  - room_id: forest_clearing
    item_id: torn_page
    quantity: 1
```

---

## World Design Tips

### 1. Plan Your Map

Sketch your world on paper first:

```
        [Tower]
           |
    [Forest]--[Village]--[Ruins]
           |
        [Caves]
```

Then assign coordinates consistently:

```yaml
village:     map_x: 5, map_y: 5
forest:      map_x: 4, map_y: 5
tower:       map_x: 4, map_y: 6
ruins:       map_x: 6, map_y: 5
caves:       map_x: 5, map_y: 4
```

### 2. Create Coherent Areas

Group rooms by theme with `area_id`:

```yaml
area_id: town         # Village and buildings
area_id: wilderness   # Forest, meadow, creek
area_id: cave         # Underground caves
```

### 3. Vary Descriptions

Don't repeat descriptions. Each room should feel unique:

```yaml
# Good: specific and atmospheric
description: >-
  The scent of fresh bread mingles with sea salt. Fishmongers haggle
  over baskets of eels while children chase pigeons between stalls.

# Poor: generic
description: "A marketplace where people buy and sell goods."
```

### 4. Create Points of Interest

Fill rooms with details that reward exploration:

```yaml
description: >-
  A weathered signpost marks the crossroads. Scratched into the wood are
  dozens of names and dates—travellers marking their passage. One recent
  carving reads: "The caves to the north are NOT empty."
```

### 5. Use Light Strategically

Dark rooms create tension and challenge:

```yaml
- id: cave_chamber
  light_level: 0  # Requires light source
  description: >-
    The darkness here is absolute, pressing against your eyes like a physical
    thing. Only your light source keeps the void at bay.
```

### 6. Design Connective Passages

Transitions between areas should make sense:

```yaml
# Bad: sudden tonal shift
- id: village_square
  # ... cheerful marketplace ...
  exits:
    - direction: south
      target_room_id: alien_spaceship

# Good: gradual transition
- id: village_square
  exits:
    - direction: south
      target_room_id: forest_edge
- id: forest_edge
  exits:
    - direction: south
      target_room_id: deep_forest
- id: deep_forest
  exits:
    - direction: south
      target_room_id: cave_entrance
```

### 7. Make Items Tell Stories

Items should evoke narrative:

```yaml
- id: faded_love_letter
  name: "Faded Love Letter"
  description: >-
    A letter written in careful penmanship, decades old. The ink has faded
    to sepia. It reads: "My love, I leave at dawn for distant shores. Wait
    for me if you can. —J"
```

### 8. Respect Scale

Consider distance. A room shouldn't be instantly adjacent to a distant location:

```yaml
# Makes sense
village_square -> south_gate -> forest_path -> deep_forest -> cave

# Doesn't make sense
village_square -> cave (instant)
```

### 9. Create Secrets

Hide exits or items behind conditions:

```yaml
- direction: north
  target_room_id: wizard_tower
  hidden: true
  condition_flags: ["wizard_tower_revealed"]
```

### 10. Balance Complexity

Too many exits makes navigation confusing. Aim for 3-4 exits per room:

```yaml
exits:
  - direction: north
    target_room_id: blacksmith
  - direction: east
    target_room_id: market
  - direction: west
    target_room_id: inn
  - direction: south
    target_room_id: gate
```

---

## Example: Small Town

Here's a complete small town with rooms, items, and connections:

```yaml
rooms:
  - id: town_square
    name: "The Town Square"
    description: >-
      A modest plaza with a stone fountain at its centre. Weathered buildings
      frame three sides; the southern gate stands open to the forest road.
    map_x: 5
    map_y: 5
    area_id: town
    light_level: 1
    exits:
      - direction: north
        target_room_id: blacksmith
      - direction: east
        target_room_id: general_store
      - direction: west
        target_room_id: tavern
      - direction: south
        target_room_id: gate

  - id: blacksmith
    name: "Ironsmith's Forge"
    description: >-
      A building dominated by a large forge radiating waves of heat. Tools hang
      in neat rows. The smith, a weathered woman, watches you over her work.
    map_x: 5
    map_y: 6
    area_id: town
    light_level: 1
    exits:
      - direction: south
        target_room_id: town_square

  - id: general_store
    name: "General Goods"
    description: >-
      Shelves creak under the weight of supplies: rope, cloth, preserved foods,
      candles. The shopkeeper nods from behind the counter.
    map_x: 6
    map_y: 5
    area_id: town
    light_level: 1
    exits:
      - direction: west
        target_room_id: town_square

  - id: tavern
    name: "The Stumbling Ox"
    description: >-
      Low ceilings, warm lamplight, and the smell of ale and roasted meat.
      Locals huddle in corners, speaking in low voices.
    map_x: 4
    map_y: 5
    area_id: town
    light_level: 1
    exits:
      - direction: east
        target_room_id: town_square

  - id: gate
    name: "Town Gate"
    description: >-
      A simple wooden gate marks the transition from civilisation to wilderness.
      The forest road stretches south into gathering darkness.
    map_x: 5
    map_y: 4
    area_id: town
    light_level: 1
    exits:
      - direction: north
        target_room_id: town_square
      - direction: south
        target_room_id: forest_path

  - id: forest_path
    name: "Forest Road"
    description: >-
      The road narrows as it enters the wood. Tall trees press close; the
      canopy filters the sunlight to a green gloom.
    map_x: 5
    map_y: 3
    area_id: wilderness
    light_level: 1
    exits:
      - direction: north
        target_room_id: gate

items:
  - id: copper_coin
    name: "Worn Copper Coin"
    description: >-
      A small coin, worn smooth by passing through countless hands. Still
      legal tender.
    takeable: true
    tradeable: true

  - id: ale_mug
    name: "Wooden Ale Mug"
    description: >-
      A sturdy mug carved from oak, well-used but well-maintained. Smells of
      ale and wood smoke.
    takeable: true
    tradeable: true

  - id: rope
    name: "Coil of Rope"
    description: >-
      Sturdy hemp rope, about thirty feet. Useful for climbing or securing cargo.
    takeable: true
    tradeable: true

room_items:
  - room_id: town_square
    item_id: copper_coin
    quantity: 1

  - room_id: tavern
    item_id: ale_mug
    quantity: 1

  - room_id: general_store
    item_id: rope
    quantity: 1
```

---

## Validation and Loading

The world loader validates:
- Room IDs are unique
- Exit `target_room_id` values reference existing rooms
- Item IDs are unique
- `room_items` references valid rooms and items
- `key_item_id` references valid items

Load your world with:

```python
from lorecraft.world.loader import load_world_yaml
from lorecraft.db import get_session

with get_session() as session:
    doc = load_world_yaml("world_content/world.yaml", session)
```

Validation errors will raise `WorldValidationError` with details.

---

## Next Steps

1. **Read dialogue_npcs_quests.md** to populate your world with characters and objectives.
2. **Playtest** by moving through rooms, picking up items, reading descriptions.
3. **Iterate** based on feel: does navigation flow? Are descriptions evocative? Do items feel purposeful?
