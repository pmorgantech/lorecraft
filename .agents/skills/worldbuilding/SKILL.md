---
name: worldbuilding
description: Author or edit Lorecraft world content — rooms, exits, items, NPCs, dialogue trees, scripted on/when/do triggers, autonomous NPC behavior (wander/patrol), traveling weather fronts, and area spawns — using the Phase A scripting engine. Use whenever asked to create or change an NPC, a room, a scripted/reactive event, a dialogue branch, a weather effect, or a spawner in world_content/*.yaml. Read this before writing any `triggers:`, `when:`, `do:`, `ai:`, `behavior:`, dialogue `side_effects:`, weather_fronts.yaml, or spawns.yaml.
---

# Lorecraft world-building (Phase A scripting)

World content is **data**, not code. Everything below is authored in
`world_content/*.yaml` and imported into the game DB (`./start.sh`, or
`python -m lorecraft.tools.world_cli import`). The engine loads behavior from this
YAML — never hard-code room ids or content into `src/`.

## The one rule: the vocabulary is generated — consult it, don't guess

The set of valid `when:` conditions and `do:` effects is **generated from the engine's
registered descriptors** into [`docs/scripting_api.md`](../../../docs/scripting_api.md).
That file is the single source of truth. Before writing a condition or effect name:

1. **Read `docs/scripting_api.md`** and use an exact name from it.
2. After changing any scripting registration in `src/` (a `register_spec(...)` call),
   regenerate it: `make scripting-docs` (a CI drift-check fails otherwise).
3. **Validate before shipping:**
   `python -m lorecraft.tools.world_cli validate --file world_content/world.yaml`
   — the validator is **fail-closed**: an unknown `when:`/`do:` name is a hard error at
   author/load time. (The *runtime* is fail-open — an unrecognized name silently no-ops —
   so the validator is your safety net. Always run it.)

Current vocabulary (verify against the generated doc — this is a snapshot, not the source):

- **Conditions (`when:`)** — `actor_has_flag`, `actor_lacks_flag` (the canonical flag
  predicates — command surface takes a single colon-string flag, dialogue surface takes a list),
  `actor_reputation_at_least`, `item_in_inventory`, `npc_present`, `object_present`,
  `requires_light`, `in_combat`, `not_in_combat`. Dialogue-only: `moon_phase_is`. (Quest-stage
  conditions are a *separate* registry using `{type: flag_set, flag: …}` — don't confuse them
  with the `when:` vocabulary here.)
- **Effects (`do:` / dialogue `side_effects:`)** — `narrate_room`, `narrate_zone`,
  `apply_effect`, `set_flags`, `clear_flags`, `give_item`, `start_quest`, `end_dialogue`,
  `adjust_reputation`.

> Some vocabulary registers only when its **feature is enabled** (e.g. reputation's
> `actor_reputation_at_least`/`adjust_reputation`). If a name is missing from
> `docs/scripting_api.md`, confirm the owning feature is enabled before assuming it's absent.

## Rooms (`world_content/world.yaml` → `rooms:`)

A room is a list entry. Fields:

| Field | Meaning |
|---|---|
| `id` | Stable string key (e.g. `wandering_crow_inn`). Referenced by exits, NPCs, triggers. |
| `name`, `description` | Display text. |
| `zone` | Zone the room belongs to (`ashmoore`, `whisperwood`, `cogsworth`, etc.). Used by pricing, weather/climate, spawns, and zone-qualified addressing. |
| `map_x`, `map_y`, `map_z` | Minimap coords; `map_z` is floor/level. |
| `light_level` | 0 = dark (needs a light source to look/act). |
| `terrain` | Travel-gating terrain (`normal`, `forest`, `water`, …). |
| `safe_rest` | Inns/camps: `sleep` here is reliable. |
| `indoor` | `true` for sheltered interiors — **weather narration (ambient + storms) is suppressed here.** Set it on inns, cellars, shops, vaults, caves. |
| `flags` | Free-form room flags. |
| `exits` | `- {direction, target_room_id, locked?, key_item_id?, hidden?}`. |
| `triggers` | Reactive scripting (below). |

## Scripted events: `triggers:` (the on/when/do model)

Rooms **and** NPCs carry a `triggers:` list. Each entry is `{on, when?, do}`:

```yaml
triggers:
  - on: encounter                     # the synthetic event that fires this
    when:                             # optional AND-ed conditions (omit = always)
      actor_lacks_flag: [met_mira]
    do:                               # ordered effects
      - narrate_room: "Mira glances up and gives you a nod of welcome."
      - set_flags: [met_mira]
```

**Trigger events (`on:`):**

| Event | Fires when | Lives on |
|---|---|---|
| `encounter` | A player and this NPC share a room (player walks in, or the NPC walks in) | NPC |
| `player_entered` | A player enters this room | Room |
| `item_stored` | An item is placed into a container in this room | Room |
| `item_removed` | An item is taken from a container in this room | Room |

`when:` conditions are evaluated against the **actor** (the triggering player). `do:` effects
run in order; targets like `narrate_room` broadcast to the room, `narrate_zone` to the whole
zone, and `apply_effect` to `actor|room|stored_item`.

## NPCs (`world_content/world.yaml` → `npcs:`)

```yaml
npcs:
  - id: innkeeper
    name: Mira the Innkeeper
    description: A stout woman who surveys the room with a practiced eye.
    home_room_id: wandering_crow_inn
    current_room_id: wandering_crow_inn
    dialogue_tree_id: innkeeper_dialogue   # references a dialogue_trees: entry
    behavior: defensive                    # combat disposition
    triggers:                              # reactive scripting (as above)
      - on: encounter
        do:
          - narrate_room: "Mira glances up from behind the counter."
    ai:                                    # optional autonomous movement (A3)
      mode: patrol                         # or: wander
      move_every: 3                        # ticks between moves
      route: [gate, market_stalls, square] # patrol: ordered room ids (loops)
      # wander uses `area:` to confine roaming instead of `route:`
      actions:                             # optional non-movement autonomy
        - type: say                         # say | emote | narrate
          every_ticks: 5
          chance: 0.6
          lines:
            - "Keep the lane clear."
        - type: emote
          every_ticks: 8
          text: checks the latch on a side gate.
    schedule:                              # optional hour-based state changes
      - game_hour: 8
        behavior: defensive
        ai: {}
      - game_hour: 20
        behavior: alert
        ai:
          mode: patrol
          move_every: 2
          route: [market_stalls, square]
    context_commands:                      # verbs available only where this NPC is (Sprint 55)
      tip:
        help: leave a small tip at the counter
```

- **Dialogue trees** live under `dialogue_trees:` — nodes of `{text, side_effects, choices}`;
  each choice is `{label, next_node?}` and may carry a **condition** (e.g. `moon_phase_is: full`
  to gate visibility) and/or `side_effects:` (any `do:` effect, e.g. `set_flags`, `start_quest`,
  `end_dialogue`, `adjust_reputation`).
- **`ai`** drives autonomous movement; an NPC that moves fires *its* `encounter` triggers for
  players it walks into.

## World-building quality bars

Use `docs/worldbuilding_guide.md` as the deeper reference when planning zones, shops,
quests, or dense room clusters. Naming a new zone? Check
[`docs/zone_naming.md`](../../../docs/zone_naming.md) first — a bank of evocative names by
terrain type in the same register as the shipped zones — before inventing one from scratch.
The durable rules for Lorecraft content:

- Keep areas modular and geographically coherent. Exits should be reciprocal unless the
  one-way route is deliberate and signposted.
- Prefer dense, useful rooms over corridors. Every new room should usually offer at least
  one concrete feature: an NPC, shop stock, readable/usable item, clue, trigger, ambience,
  rest point, or navigational choice.
- Descriptions should be objective, static, and multi-sensory. Avoid "you feel/you stand,"
  assumed actions, relative directions like left/right, parser instructions, or dynamic facts
  that should live on NPCs, triggers, ambient events, or items.
- Implement important people and objects separately. If prose makes a shopkeeper, guard,
  sign, key item, or special shelf sound interactive, add the NPC/item/dialogue/trigger when
  feasible instead of leaving it as unreachable flavor.
- Keep rewards and shop stock thematic and proportionate. Avoid flooding the economy with
  excessive coins, unlimited high-power gear, or off-theme items just to fill shelves.

## Shops and service NPCs

Lorecraft shops are currently NPC-attached economy data (`features/economy`), not standalone
room records. For a normal fixed shop, place a stationary shopkeeper in the shop room:
`home_room_id == current_room_id`, no roaming `ai`, and a `shop:` block. A roving merchant is
the same shape with a schedule/route, but use that intentionally.

```yaml
npcs:
  - id: ashmoore_general_keeper
    name: Cora Vale
    description: A practical shopkeeper with twine cuts across both thumbs.
    home_room_id: ashmoore_general_store
    current_room_id: ashmoore_general_store
    dialogue_tree_id: cora_vale_dialogue
    behavior: defensive
    shop:
      name: Vale's General Store
      buys_categories: [trade_good, food, utility]
      sell_ratio: 0.5
      region_mult: 1.0
      starting_coins: 400
      stock:
        - item_id: pitch_torch
          quantity: -1
        - item_id: leather_backpack
          quantity: 3
          restock_to: 3
          restock_every_ticks: 168
```

Shop authoring checklist:

- Put the shop in an `indoor: true` room unless it is explicitly an outdoor stall.
- Give the shopkeeper short, role-specific dialogue; avoid generic "welcome to my shop."
- Prefer existing items first. Add new items only when the role needs missing stock or
  local flavor.
- Use finite `starting_coins` and `quantity` for meaningful stock; `quantity: -1` only for
  mundane staples that should not run out.
- Use `restock_to`/`restock_every_ticks` for finite staples. Leave rare items finite with no
  restock unless repeat availability is intended.
- Set `buys_categories` narrowly enough that each shop has an identity.
- There is no first-class shop-hours field yet. If hours are needed, use NPC `schedule`
  entries to move the shopkeeper away and/or switch its `behavior`/simple autonomous `ai`;
  service refusal rules remain future work.

## Weather fronts (`world_content/weather_fronts.yaml`)

Traveling storms (A5), rolled every in-game hour by `WeatherFrontService`:

```yaml
storms:
  spring_squall:
    chance: 0.12                 # per-hour odds while dormant and in season
    seasons: [spring, autumn]
    duration_ticks: {min: 3, max: 6}
    travel_ticks: 2              # hours before the front moves to the next zone
    path: [town, wilderness]     # ordered area_ids it crosses
    room_effect: storm_lashed    # a registered EffectDef applied across the zone
    on_enter: "Dark clouds gather overhead and a cold rain begins to fall."
    on_leave: "The rain eases and the clouds thin to a pale grey."
```

`on_enter`/`on_leave` narrate to every **outdoor** room in the zone (interiors with
`indoor: true` are skipped). Distinct from the ambient world-clock weather, which announces
short lines (e.g. "A light rain begins to fall.") to outdoor players on any weather change.

## Spawns (`world_content/spawns.yaml`)

Area population controllers (A6) — keep `max_count` clones of a template NPC alive in an area:

```yaml
spawns:
  wolf_pack:
    area: wilderness
    template: wolf              # an NPC id used as the clone template
    max_count: 3
    every_ticks: 5             # re-check/top-up cadence (in-game hours)
```

Clones copy the template's `dialogue` and `ai`, get a `<spawn_id>#<hash>` id, and are placed
in a random area room via the seeded RNG (runs replay faithfully).

## Workflow for "create an NPC / a scripted event"

1. Read `docs/scripting_api.md` for the exact `when:`/`do:` names you'll use.
2. Add/edit the entry in the right `world_content/*.yaml` (room, npc, dialogue tree, weather,
   spawn). Reuse existing zones (`area_id`) and follow the demo's structure.
3. `python -m lorecraft.tools.world_cli validate --file world_content/world.yaml` — fix any
   `unknown condition/effect '<name>'` before committing.
4. Re-import to see it live: `rm test_dbs/* && ./start.sh` (the seed DB is only rebuilt when
   missing, so wipe it to pick up content changes), or `world_cli import`.
5. If you added a *new* condition/effect/behavior descriptor in `src/`, run `make scripting-docs`
   in the same commit (CI drift-check enforces it) and add unit tests.

## Merging parallel zone-building branches (git gotcha)

When multiple agents build separate zones in parallel (each in its own worktree, each
appending rooms/items/npcs/dialogue_trees/room_items/economy.regions/quests to the same
`world_content/world.yaml`), combining their branches with a plain `git merge` is
**unreliable, even with `-X histogram` or `-X patience`**. Every zone's addition lands at the
same insertion point (right before the next top-level key), and the file is full of short
lines that repeat across dozens of unrelated entries — `light_level: 1`, `exits:`,
`- direction: north`, `side_effects: {}`. Git's line-based diff can lock onto these as false
alignment points instead of treating each zone's block as atomic, and *interleave* two
unrelated records — for example, splicing one NPC's dialogue-choice label directly onto
another zone's unrelated dialogue node's text. The output can still be syntactically valid
YAML with every ID resolvable, so `world_cli validate` passes clean on a genuinely corrupted
merge — the validator checks structure and references, not narrative coherence.

**Recipe: structural section-merge**, done once per top-level YAML key (`rooms:`, `items:`,
`room_items:`, `dialogue_trees:`, `npcs:`, `economy:`, `quests:`), instead of trusting `git
merge`'s conflict resolution:

1. Get the full file text at three points: the shared base commit (before any zone branch
   diverged), and each zone branch's tip (each is base + that zone's own pure-addition diff).
2. For each top-level key, slice out that section's lines (from the key to the next
   top-level key, or EOF for the last one) in all three versions.
3. For each zone, compute the **common prefix** and **common suffix** between the base
   section and that zone's section (both computed line-by-line). Since each zone only adds
   lines and never edits existing ones, `prefix_len + suffix_len` should equal the base
   section's total length exactly — **verify this before trusting the split**; if it doesn't
   match, that zone's branch touched existing content and needs manual review, not this
   recipe.
4. That zone's actual added content is the slice between the prefix and the suffix.
5. Reassemble each section as: `prefix + zoneA_added + zoneB_added + ... + suffix`, then
   concatenate all reassembled sections (plus the file header before `rooms:`) into the final
   file.

A short Python script doing exactly this (list-of-lines slicing, no YAML parsing needed —
parsing and re-serializing with a YAML library risks reformatting the hand-authored
`>-` description blocks and losing comments) is faster and more reliable here than resolving
conflict markers by hand. After merging, run `world_cli validate` **and** spot-check at least
one multi-line dialogue/description block from each merged zone directly in the file — the
validator won't catch a splice, only a human skim will.

## Key source files (for engine-side changes)

- `src/lorecraft/engine/scripting/` — `vocabulary.py` (descriptors + global catalog),
  `triggers.py` (`on:` event mapping + `TriggerService`), `validator.py` (fail-closed linting),
  `catalog.py` (renders `docs/scripting_api.md`).
- `src/lorecraft/features/npc/side_effects.py` + `dialogue_conditions.py` — effect/condition
  registrations (`register_spec` → catalog).
- `src/lorecraft/features/npc_ai/` (agency), `features/weather/fronts.py` (storms),
  `features/spawns/` (population), `features/reputation/` (standing gating).
- `src/lorecraft/world/{validator.py,loader.py}` — the YAML schema + importer. Add a room/NPC
  field here (and to the model + a `db.py` migration) when extending world data.
- `docs/archive/scripting_engine_design.md` — the design spec (sections §3, §6, §8).
