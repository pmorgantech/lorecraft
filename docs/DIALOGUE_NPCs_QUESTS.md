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
            required_flags: []
            forbidden_flags: []
            side_effects: {}
          - label: "Just browsing."
            next_node: browsing
            required_flags: []
            forbidden_flags: []
            side_effects: {}
          - label: "Farewell."
            next_node: null  # null ends dialogue
            required_flags: []
            forbidden_flags: []
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
| `required_flags` | array | Player must have ALL these flags to see this choice |
| `forbidden_flags` | array | Player must NOT have ANY of these to see this choice |
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
```

**Note:** `give_item` is a single item ID. `start_quest` starts a quest if the player hasn't already.

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
            required_flags: ["merchant_quest_active"]
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
          reputation: 25
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
| `conditions` | array | Conditions that must be met to progress (not enforced yet) |
| `completion_flags` | object | Flags set when stage completes |
| `rewards` | object | Rewards for completing this stage |

### Condition Types

Conditions describe what must happen for a stage to progress:

```yaml
conditions:
  - type: "in_room"          # Player is in a specific room
    room_id: "deep_forest"

  - type: "has_item"         # Player has an item
    item_id: "rare_metal_ore"

  - type: "flag_set"         # Player has a flag
    flag: "found_treasure"
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
          reputation: 50
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
            required_flags: ["curse_quest_active"]
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

Run the loader to catch errors early.
