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
| `area_id` | **Zone** the room belongs to (`town`, `wilderness`, `cave`). Used by `narrate_zone`, weather fronts, spawns, and zone-qualified addressing. |
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
`area_id`, `apply_effect` to `actor|room|stored_item`.

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
- `docs/scripting_engine_design.md` — the design spec (sections §3, §6, §8).
