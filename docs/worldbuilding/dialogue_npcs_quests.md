---
kindle_doc_weaver: ignore
---

# Setting Up Dialogue, NPCs, and Quests

This guide explains how to create dialogue trees, NPCs, and quests in Lorecraft using YAML.

## Table of Contents

1. [NPCs](#npcs)
2. [Dialogue Trees](#dialogue-trees)
3. [Quests](#quests)
4. [Integration Examples](#integration-examples)

---

## NPCs

NPCs (non-player characters) are living entities in your world. They can be found in rooms, engage in dialogue, and follow daily schedules.

### Basic NPC Definition

```yaml
npcs:
  - id: blacksmith_thor
    name: Thor Ironhand
    description: A weathered dwarf with soot-stained hands and a commanding presence.
    home_room_id: blacksmith_forge
    current_room_id: blacksmith_forge
    dialogue_tree_id: blacksmith_dialogue
    behavior: defensive
    max_hp: 75
    schedule:
      - game_hour: 8
        target_room_id: blacksmith_forge
      - game_hour: 12
        target_room_id: village_square
      - game_hour: 18
        target_room_id: blacksmith_forge
    loot_table: {}
```

### NPC Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✓ | Unique identifier for the NPC |
| `name` | string | ✓ | Display name |
| `description` | string | ✓ | Description shown when examining the NPC |
| `home_room_id` | string | ✓ | Room where NPC respawns or returns |
| `current_room_id` | string | | Initial room (defaults to `home_room_id`) |
| `dialogue_tree_id` | string | | ID of dialogue tree (omit if no dialogue) |
| `behavior` | string | | "defensive", "aggressive", or "neutral" (default: "defensive") |
| `max_hp` | integer | | Maximum health points (default: 50) |
| `schedule` | array | | Daily movement schedule (see below) |
| `loot_table` | object | | Items dropped when defeated (see Quests section) |

### Schedules

NPCs follow a schedule that moves them between rooms at specific game hours:

```yaml
schedule:
  - game_hour: 8    # At 8 AM
    target_room_id: blacksmith_forge
  - game_hour: 12   # At noon
    target_room_id: village_square
  - game_hour: 14   # At 2 PM
    target_room_id: wandering_crow_inn
  - game_hour: 18   # At 6 PM
    target_room_id: blacksmith_forge
```

**Note:** The game clock runs faster than real time (typically 60x). Use 24-hour format (0-23).

---

## Dialogue Trees

Dialogue trees are branching conversations between players and NPCs. They're tree-structured with a root node and choices that branch to other nodes.

### Basic Dialogue Tree Structure

```yaml
dialogue_trees:
  - id: blacksmith_dialogue
    root_node: greeting
    nodes:
      greeting:
        text: "Greetings, traveller. Looking for fine metalwork?"
        side_effects: {}
        choices:
          - label: "I need a weapon."
            next_node: weapons
            actor_has_flag: []
            actor_lacks_flag: []
            side_effects: {}
          - label: "Just browsing."
            next_node: browsing
            actor_has_flag: []
            actor_lacks_flag: []
            side_effects: {}
          - label: "Farewell."
            next_node: null  # null ends dialogue
            actor_has_flag: []
            actor_lacks_flag: []
            side_effects: {}

      weapons:
        text: "Aye, I've got steel for cutting and steel for bashing. Which suits your hand?"
        side_effects: {}
        choices:
          - label: "Show me blades."
            next_node: blades
          - label: "Back to main menu."
            next_node: greeting

      blades:
        text: "This sword was forged with the hammer-song of my grandfather..."
        side_effects: {}
        choices:
          - label: "I'll take it!"
            next_node: purchase
            side_effects:
              give_item: iron_sword
          - label: "Too expensive."
            next_node: greeting

      browsing:
        text: "Feel free to look around. Mind you don't touch the hot metal."
        side_effects: {}
        choices:
          - label: "Thanks, I'll look around."
            next_node: null  # Ends dialogue

      purchase:
        text: "Excellent choice. Use it well."
        side_effects: {}
        choices:
          - label: "I will. Goodbye."
            next_node: null
```

### Dialogue Node Fields

Each node in `nodes` has:

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | What the NPC says |
| `side_effects` | object | Actions triggered when entering this node |
| `choices` | array | Player response options |

### Choice Fields

Each choice has:

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | Player sees this text as the option |
| `next_node` | string or null | Node to transition to; `null` ends dialogue |
| `actor_has_flag` | array | Player must have ALL these flags to see this choice |
| `actor_lacks_flag` | array | Player must NOT have ANY of these to see this choice |
| `side_effects` | object | Actions triggered when choosing this option |

### Side Effects

Side effects are triggered when:
1. Entering a dialogue node
2. Choosing a dialogue option

Supported side effects:

```yaml
side_effects:
  set_flags:
    - "talked_to_blacksmith"
    - "learned_about_sword"
  clear_flags:
    - "curiosity_flag"
  give_item: "iron_sword"  # Give player an item (single item)
  start_quest: "fetch_rare_metal"  # Begin a quest
  end_dialogue: true  # Force end dialogue (optional)
  remember: ["helped"]  # Sprint 30.1: NPC memory (see below)
  adjust_reputation:  # Sprint 30.1: standing as a consequence, not just a gate
    target_type: npc
    target_id: blacksmith_thor
    delta: 10
```

**Note:** `give_item` is a single item ID. `start_quest` starts a quest if the player hasn't already.

### NPC Memory (Sprint 30.1)

Player flags (`set_flags`/`actor_has_flag`) are global — one flag means the same thing to
every NPC. NPC memory is scoped **per (player, NPC)**: the same key, e.g. `"helped"`, can be
true for Thor and false for Mira, without inventing `helped_thor`/`helped_mira` flags.

```yaml
dialogue_trees:
  - id: blacksmith_dialogue
    root_node: greeting
    nodes:
      greeting:
        text: "Need something forged?"
        choices:
          - label: "I fixed your bellows earlier."
            next_node: thanked
            side_effects:
              remember: ["helped"]  # scoped to "whichever NPC this conversation is with"
          - label: "Remember when I helped you?"
            next_node: recalled
            npc_remembers: ["helped"]  # choice hidden until remembered
```

`remember` accepts a list of keys (sets each to `true`) or a `{key: value}` dict for explicit
values. `npc_remembers` is a dialogue condition (like `actor_has_flag`) — all listed keys must
be remembered for the NPC currently being talked to. The same `npc_remembers` type is also a
quest condition (see below), where the NPC must be named explicitly since there's no "current
conversation" outside dialogue.

### Conditional Dialogue Example

```yaml
dialogue_trees:
  - id: merchant_dialogue
    root_node: greeting
    nodes:
      greeting:
        text: "Welcome to my shop!"
        choices:
          - label: "Do you have any rare items?"
            next_node: rare_items
            actor_has_flag: ["merchant_quest_active"]
          - label: "Goodbye."
            next_node: null

      rare_items:
        text: "Ah, I see you're on a quest. I have what you seek."
        side_effects:
          set_flags: ["obtained_rare_item"]
          give_item: "rare_gemstone"
        choices:
          - label: "Thank you!"
            next_node: null
```

---

## Quests

Quests are multi-stage objectives for the player. They track progress through stages and can reward items or achievements.

### Basic Quest Definition

```yaml
quests:
  - id: fetch_rare_metal
    title: "Fetch the Rare Metal"
    description: "Thor needs a rare metal ore from the deep caves."
    stages:
      - id: stage_1
        description: "Travel to the deep caves and find rare metal ore."
        conditions:
          - type: "in_room"
            room_id: "deep_forest"
        completion_flags:
          - key: "found_ore_location"
            value: true

      - id: stage_2
        description: "Return the ore to Thor at the forge."
        conditions:
          - type: "in_room"
            room_id: "blacksmith_forge"
          - type: "has_item"
            item_id: "rare_metal_ore"
        completion_flags:
          - key: "returned_ore"
            value: true
        rewards:
          xp: 500
          coins: 50
          skill_points: 1
```

### Quest Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique quest identifier |
| `title` | string | Quest name shown to player |
| `description` | string | Quest log description |
| `stages` | array | Ordered list of quest stages |

### Stage Fields

Each stage has:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique stage identifier within the quest |
| `description` | string | What the player needs to do |
| `conditions` | array | Conditions that must be met to progress |
| `completion_flags` | object | Flags set when stage completes |
| `rewards` | object | Rewards for completing this stage (`xp`, `items`, `coins` [alias `money`], `skill_points`) — see [Quest rewards and the progression system](admin_builder_guide.md#quest-rewards-and-the-progression-system-sprint-73) for the full vocabulary and admin-tunable XP curve. Any other key must be a known numeric player stat; `reputation` is **not** a valid reward key — use a `side_effects: adjust_reputation` block instead (see Branching Stages below) |
| `branches` | array | Sprint 30.1: alternate outcomes — see below |
| `terminal` | bool | Sprint 30.1: complete the quest once this stage's `conditions` pass, regardless of array position (needed for a branch-reached ending that isn't last in `stages`) |
| `timeout_ticks` | number | Sprint 30.2: game-clock ticks after which, if the player hasn't progressed past this stage, `on_timeout` fires |
| `on_timeout` | object | Sprint 30.2: `{next_stage, message, set_flags}` — see below |

Without `branches`, a stage advances to `stages[idx+1]` when its `conditions` pass (or
completes the quest if it's the last stage) — the original linear behavior, unchanged.

### Condition Types

Conditions describe what must happen for a stage (or branch) to progress. Every condition
type is a pluggable predicate on `game/quest_conditions.py`'s registry — new types register
without touching the quest service.

```yaml
conditions:
  - type: "room_visited"      # Player has ever visited a room
    room_id: "deep_forest"

  - type: "item_in_inventory" # Player is carrying an item
    item_id: "rare_metal_ore"

  - type: "flag_set"          # Player has a flag set
    flag: "found_treasure"

  - type: "flag_clear"        # Player does NOT have a flag set
    flag: "quest_abandoned"

  - type: "npc_remembers"     # Sprint 30.1: NPC memory (see NPC Memory above)
    npc_id: "blacksmith_thor"
    flag: "helped"            # the memory key
```

### Branching Stages (Sprint 30.1)

Once a stage's own `conditions` pass, `branches` are evaluated **in order**; the first branch
whose *own* `conditions` also pass wins — its `side_effects` (any handler on the shared
dialogue side-effects registry: `set_flags`, `give_item`, `adjust_reputation`, `remember`,
...) are the consequence, and `next_stage` becomes the new current stage (`null` completes the
quest). If no branch's conditions pass yet, the quest simply stalls at the current stage.

```yaml
stages:
  - id: decide_how_to_help
    description: "Decide how to help the merchant."
    conditions:
      - type: flag_set
        flag: ready_to_help
    branches:
      - conditions:
          - type: room_visited
            room_id: docks
        next_stage: safe_route
        side_effects:
          set_flags: ["took_safe_route"]
          adjust_reputation: {target_type: npc, target_id: merchant, delta: 10}
      - conditions:
          - type: room_visited
            room_id: smugglers_cave
        next_stage: risky_route
        side_effects:
          set_flags: ["took_risky_route"]
          adjust_reputation: {target_type: npc, target_id: merchant, delta: -5}

  - id: safe_route
    description: "You took the safe way."
    conditions: []
    terminal: true          # a branch target, not necessarily last in the array
    rewards: {xp: 10}

  - id: risky_route
    description: "You took the dangerous shortcut."
    conditions: []
    terminal: true
    rewards: {xp: 20}
```

### Timed Quest Events (Sprint 30.2)

A stage's `timeout_ticks` (game-clock ticks, not wall time) starts counting from the moment
the stage becomes current. If the player hasn't progressed past it before the deadline,
`QuestTimerService` (a background sweep on every `TIME_ADVANCED` tick, independent of any
player command) applies `on_timeout`:

```yaml
stages:
  - id: wait_at_depot
    description: "Get to the depot before the caravan leaves."
    conditions:
      - type: flag_set
        flag: boarded
    timeout_ticks: 200
    on_timeout:
      next_stage: missed_caravan   # or omit/null to fail the quest outright
      message: "The caravan leaves without you."
      set_flags:
        missed_caravan: true
```

### Multi-Stage Quest Example

```yaml
quests:
  - id: rescue_villager
    title: "Rescue the Lost Villager"
    description: "A child has wandered into the dark forest. Help find them."
    stages:
      - id: find_child
        description: "Search the forest for signs of the child."
        conditions:
          - type: "in_room"
            room_id: "deep_forest"

      - id: return_child
        description: "Bring the child back to the village square."
        conditions:
          - type: "in_room"
            room_id: "village_square"

      - id: speak_with_parent
        description: "Speak with the child's parent at the inn."
        conditions:
          - type: "in_room"
            room_id: "wandering_crow_inn"
        rewards:
          xp: 50
          coins: 20
```

---

## Integration Examples

### Starting a Quest via Dialogue

Connect dialogue to quests using side effects:

```yaml
dialogue_trees:
  - id: elder_dialogue
    root_node: greeting
    nodes:
      greeting:
        text: "A terrible curse has fallen upon our village. Will you help?"
        choices:
          - label: "I'll help you."
            next_node: accepted
            side_effects:
              set_flags: ["curse_quest_accepted"]
              start_quest: "break_the_curse"
          - label: "I cannot help."
            next_node: refused

      accepted:
        text: "Thank you, brave one. Seek the source in the deep caves."
        choices:
          - label: "I'll find it."
            next_node: null

      refused:
        text: "Then I fear our village is doomed."
        choices:
          - label: "Goodbye."
            next_node: null
```

### NPC That Only Talks After Quest

Use flags to gate dialogue:

```yaml
npcs:
  - id: cursed_warrior
    name: Aldric the Cursed
    description: "A warrior bound by dark magic."
    home_room_id: deep_forest
    dialogue_tree_id: cursed_warrior_dialogue

dialogue_trees:
  - id: cursed_warrior_dialogue
    root_node: cursed
    nodes:
      cursed:
        text: "The curse... I cannot speak freely..."
        choices:
          - label: "I am here to break the curse."
            next_node: hope
            actor_has_flag: ["curse_quest_active"]
          - label: "Leave me."
            next_node: null

      hope:
        text: "You seek to free me? There is a crystal in the pool below..."
        side_effects:
          set_flags: ["knows_crystal_location"]
        choices:
          - label: "I will find it."
            next_node: null
```

### Giving Items Through Dialogue

```yaml
dialogue_trees:
  - id: alchemist_dialogue
    root_node: greeting
    nodes:
      greeting:
        text: "I sense you need aid. Take this potion."
        side_effects:
          give_item: "healing_potion"
        choices:
          - label: "Thank you!"
            next_node: null
```

---

## Tips and Best Practices

1. **Use clear IDs**: Use underscores for NPC and quest IDs (e.g., `blacksmith_thor`, `fetch_rare_metal`).

2. **Plan dialogue trees**: Sketch out your conversation flow before writing YAML. Keep trees manageable (5-10 nodes per character).

3. **Use flags strategically**: Flags track conversation state, quest progress, and world changes. Name them descriptively (e.g., `talked_to_blacksmith`, `curse_active`).

4. **Schedule realism**: NPCs should return home at night. Use game hours 8-18 for activity.

5. **Test dialogue**: Play through all paths. Ensure null choices end dialogue properly.

6. **Quest design**: Keep early quests simple (1-2 stages). Add complexity with multi-stage quests.

7. **NPC descriptions**: Write evocative descriptions. Players often examine NPCs before talking.

---

## Validation

The world loader validates all references:
- NPC `dialogue_tree_id` must match a `dialogue_trees[].id`
- NPC `home_room_id` and schedule `target_room_id` must exist
- Quest references in dialogue side effects must exist
- Quest stage/branch `room_id`/`item_id`/`npc_id` conditions must reference real rooms/items/NPCs
- Stage ids are unique within a quest; a branch's or `on_timeout`'s `next_stage` must reference
  a real stage id in the same quest
- `on_timeout` requires `timeout_ticks` to also be set on that stage
- Item `mechanism_side_effects` keys must be one of that item's own `mechanism_states`, and
  `mechanism_states` (if set) needs at least 2 entries
- Item `combination_side_effects` keys must reference a real item id

Run the loader to catch errors early.
