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
| `area_id` | string | | Area grouping (for organization) |
| `light_level` | integer | | 0 = dark, 1 = lit (default: 1) |
| `is_active` | boolean | | Room accessible (default: true) |
| `fallback_room_id` | string | | Room to return to if disconnected |
| `version` | integer | | Schema version (default: 1) |
| `flags` | object | | Custom flags for this room |
| `terrain` | string | | `normal`/`road`/`forest`/`mountain`/`swamp`/`water` (default: `normal`) — see Terrain below |
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

```yaml
- id: worn_backpack
  slot: back
  wearable: true
  capacity: 40
  effects:
    - { type: carry_bonus, amount: 40 }
```

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
