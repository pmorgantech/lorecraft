# Zone Naming Reference

A bank of evocative zone names for new areas, grouped by terrain type, in the same
atmospheric register as the shipped zones (`ashmoore`, `whisperwood`, `cogsworth`,
`port_veridian`, `brass_vaults`). Use these as inspiration or drop them in directly when
naming a new `zone`/`area_id` in `world_content/world.yaml` — sensory, mysterious, and
slightly poetic, hinting at danger, wonder, or age in the room title alone.

Each name is a display name (`name:`/prose usage); derive the machine `zone`/`area_id` by
lowercasing and snake_casing it (e.g. "Emberwhisper Grove" → `emberwhisper_grove`), matching
the existing convention.

## Forests & Groves

- Emberwhisper Grove
- Thornveil Thicket
- Moonshadow Wildwood
- Sighing Reedwood
- Dreadroot Canopy
- Silverveil Glade
- Ghostsong Thicket
- Lullaby Briarwood
- Frostwhisper Enclave

## Lakes, Rivers & Wetlands

- Mirrorveil Mere
- Abysswhisper Lake
- Starweave Lagoon
- Bloodroot Depths
- Echoing Glasswater
- Murkveil Marsh
- Crystalwhisper River
- The Weeping Mere
- Silent Tidepool

## Deserts & Wastelands

- Duneveil Expanse
- Scorchwhisper Wastes
- Miragebound Dunes
- Ashen Boneveil
- Phantomshift Sands
- Emberstorm Flats
- Wandering Caravan Wastes
- Crimson Quicksand Sea
- Hollowwind Desert

## Mountains & Highlands

- Stormcrown Spires
- Frostveil Peaks
- Thunderwhisper Range
- Ironroot Highlands
- Skybreaker Cliffs
- Avalanche Crown
- Runeveil Mountains

## Using a name

1. Pick (or riff on) a name from the matching terrain group above.
2. Derive the `zone`/`area_id` key by snake_casing the display name.
3. Follow `docs/worldbuilding_guide.md` and
   [`.agents/skills/worldbuilding/SKILL.md`](../../.agents/skills/worldbuilding/SKILL.md) for the
   actual room/NPC/trigger authoring workflow once the zone is named.
