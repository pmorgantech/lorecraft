---
name: worldbuilding
description: Author or edit Lorecraft world content — rooms, exits, items, NPCs, dialogue trees, scripted on/when/do triggers, autonomous NPC behavior (wander/patrol), traveling weather fronts, and area spawns — using the Phase A scripting engine. Use whenever asked to create or change an NPC, a room, a scripted/reactive event, a dialogue branch, a weather effect, or a spawner in world_content/*.yaml. Read this before writing any `triggers:`, `when:`, `do:`, `ai:`, `behavior:`, dialogue `side_effects:`, weather_fronts.yaml, or spawns.yaml.
---

# Lorecraft world-building

Use the canonical repo skill at [`.agents/skills/worldbuilding/SKILL.md`](../../../.agents/skills/worldbuilding/SKILL.md) — read that file directly before authoring any world content or scripting.

Quick orientation (full detail in the canonical file):

- World content is **data** in `world_content/*.yaml`, imported into the game DB. Never bake
  room ids or content into `src/`.
- The valid `when:` / `do:` vocabulary is **generated** into `docs/worldbuilding/scripting_api.md` — consult
  it, use exact names, and `python -m lorecraft.tools.world_cli validate` before committing
  (the validator is fail-closed; the runtime is fail-open, so validation is your safety net).
- Reactive scripting is the `{on, when?, do}` trigger model on rooms and NPCs
  (events: `encounter`, `player_entered`, `item_stored`, `item_removed`).
- NPCs also support autonomous `ai:` (wander/patrol), dialogue trees with conditional choices,
  and context verbs. Weather lives in `weather_fronts.yaml`, spawns in `spawns.yaml`.
- After adding a new engine-side descriptor, run `make scripting-docs` in the same commit.
- Naming a new zone? Check `docs/worldbuilding/zone_naming.md` for a bank of evocative names by terrain
  type before inventing one from scratch.
