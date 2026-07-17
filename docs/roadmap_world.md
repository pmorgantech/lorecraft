# Lorecraft World — Roadmap & Build Plan

**Goal:** Build a rich, multi-zone test world to exercise the engine's features across all three tiers (Tier 1 primitives, Tier 2 features, Tier 3 content) with particular attention to areas that are high-risk or low-mileage in the current Ashmoore sample.

**Current date:** 2026-07-14
**Current engine version:** v0.102.0 (multi-level maps, full UI system, NPC movement framework, zone climate, spawns, room loot, ambient room events)
**Status:** Active world-build plan. Sprint 80 closed the former zone-climate/spawn/loot/ambient/NPC-route blockers; remaining unsupported items are marked **[BLOCKED]**.

---

## Engine Feature Inventory

### ✅ Fully Supported (ready to use now)

| Feature | Support | Notes |
|---------|---------|-------|
| **Multi-level rooms** | `Room.map_z` (v0.55.0) | Floors/levels via z-coordinate; minimap filters by current level |
| **NPCs** | `features/npc/` | Place NPCs in rooms; dialogue trees with pluggable conditions (`actor_reputation_at_least`, `npc_remembers`, flags) and side effects (`give_item`, `start_quest`, `adjust_reputation`, `remember`) |
| **NPC scheduled state changes** | `NPC.schedule` + `NpcScheduler` (`features/npc/scheduler.py`) | Data-driven `[{game_hour, target_room_id?, behavior?, ai?}, ...]`; on `HOUR_CHANGED`, a row may relocate the NPC, switch disposition, and replace/clear simple autonomous AI. Room jumps remain instant teleports, not pathed movement. |
| **NPC context-attached verbs** | `NPC.context_commands` (Sprint 55) | Data-driven custom verbs (e.g. `bow`) available only while the NPC is present, each with `{aliases, help, say, side_effects, requires}` |
| **Weather system** | `features/weather/` | Global weather state, traveling fronts, and per-zone climate rolls; transit lines can block on global weather |
| **Zone climate** | `features/weather/climate.py` + `weather_fronts.yaml` `climates:` | Daily per-zone climate rolls bias Whisperwood rainy/misty and Cogsworth clear/overcast while preserving the global clock weather |
| **Random spawns** | `features/spawns` + `world_content/spawns.yaml` | Data-driven area controllers top zones up to `max_count` clones of a template NPC on world ticks |
| **Treasure/loot** | `Room.loot_table` + `RoomLootService` | Rooms can declare weighted random treasure entries; rolls are one-shot per player-room and spawn through `ItemLocationService` |
| **Ambient messages** | `Room.ambient_events` + `RoomAmbientService` | Rooms can declare timed flavor lines with tick intervals and chance, emitted only for occupied rooms |
| **NPC fixed-route patrol** | `NPC.ai.mode: route` + `NpcRouteLoader` | NPC-specific `RouteHooks` run over `MobileRouteService`, updating `NPC.current_room_id` and broadcasting depart/arrive |
| **NPC autonomous idle actions** | `NPC.ai.actions` + `NpcBehaviorService` | NPCs can act without moving: deterministic cadence/chance-gated `say`, `emote`, and raw `narrate` room output on `TIME_ADVANCED`, with `NPC_ACTED` events for tests/analytics. |
| **Item types** | weapon, armor, utility, coin | Color-coded in UI (rarity system available too) |
| **Shops/stores** | `features/economy/` | Create shops with inventory, NPC shopkeepers, prices |
| **Quests** | `features/quest/` | Quest givers, objectives, rewards, dialogue conditions |
| **Locked doors** | `locked: true` + `key_item_id` | Exits can require keys to traverse |
| **Item effects/buffs** | Traits/effects system | Wearable items can grant traits; potions can apply temporary effects |
| **Inventory persistence** | Tier 1 item/inventory model | Items follow players across sessions; weight/volume tracked |
| **Lighting** | `light_level` per room | Dark rooms, illuminating items (torches, lanterns) |
| **Areas/zones** | `Room.zone` + `Room.room_type` | Group rooms by geographic zone for lore/admin/weather/economy and by room kind for content taxonomy |
| **Safe rest** | `safe_rest: true` flag | Rooms where players can safely sleep |
| **Indoor/outdoor** | `Room.indoor: bool` | Weather narration and storm fronts skip sheltered interiors; all four shipped zones are tagged |
| **Day/night NPC behavior** | `NPC.schedule` state changes | NPCs can switch daytime/nighttime room, `behavior`, and simple autonomous `ai` loops at authored game hours. Example: Watchman Holt stands defensive in the grand plaza by day and switches to an alert night patrol between the smithy district and grand plaza. |

### ⚠️ Partially Supported (needs design/content work)

| Feature | Support | Notes |
|---------|---------|-------|
| **Reputation as an NPC behavior gate** | Reputation itself is real; nothing *acts* on it autonomously | `features/reputation` gives per-(player, npc-or-faction) standing with `actor_reputation_at_least` (the one canonical predicate, registered on both the command and dialogue condition registries) and `adjust_reputation` (side effect) — so standing can already gate what a player can *say/do* to an NPC. What's missing is any NPC decision loop that *reads* standing on its own initiative (e.g. to refuse service, flee, or turn hostile without the player first triggering dialogue). |
| **NPC autonomous behavior beyond movement** | Idle actions supported; decision behaviors remain future work | `features/npc_ai` now supports `wander`, fixed-list `patrol`, route-backed patrols, and non-movement `ai.actions` (`say`, `emote`, `narrate`). Aggro, flee, service-refusal, stealing, and autonomous combat-initiation policies need explicit rules and remain separate future work. |

### ❌ Not Yet Supported (requires engine work)

| Feature | Blocker | Notes |
|---------|---------|-------|
| **[BLOCKED] Combat / attack system (any trigger source)** | Not built — schema stub only | `models/combat.py`'s `CombatSession` is a bare table (`id, room_id, started_at, status, combatants: JSON`) with **no service, repo, command, event, or side-effect handler anywhere in the codebase**. `features/npc/side_effects.py`'s docstring name-drops `combat.start_combat` only as an *illustrative example* of the registration pattern — never implemented. NPC movement agency exists, but NPCs cannot act against a player under any condition (reputation, marks, or otherwise) because there is no combat resolution path for an "attack" to resolve into. Matches `docs/wishlist.md`'s deliberate stance: combat is set aside as "a supporting system, not the centerpiece." |
| **[BLOCKED] Alignment system** | Doesn't exist | Zero references anywhere in the codebase. `features/marks` are discovery/exploration badges (visited rooms, met NPCs, items found), not a morality/alignment axis — don't conflate the two when scripting "good/evil" NPC reactions. |
| **[BLOCKED] Dynamic room description rotation** | Needs design | Timed ambient feed lines are supported; rewriting base room descriptions by time/weather remains future scope. |
| **[BLOCKED] Weather particle effects** | UI-only, not engine** | Can describe weather in text; visual rain/snow is future stretch. |

---

## World Zones — Build Plan

### 1. **Steampunk City: Cogsworth** (multi-level vertical)

**Aesthetic:** Industrial revolution meets high fantasy—brass, copper, steam vents, gears, oil lamps, pneumatic tubes, wrought-iron balconies.

**Core theme:** A sprawling city built upward and downward. Sky-piercing clock tower, research academy, factory districts, residences on mid-levels, sewers/utilities below.

#### Map structure

```
Levels (map_z):
  2 — Clock Tower Peak (administrative, views)
  1 — Mid-city (shops, academy, residences, plazas)
  0 — Ground/street level (main hubs, grand plaza, market)
  -1 — Undercity (sewers, maintenance tunnels, steam vents, homeless encampments)
  -2 — Deep sewers / industrial foundry
```

#### 1.1 Clock Tower (map_z: 2)
- **clock_tower_peak** (the spire; exterior view)
- **clockworks_chamber** (working gears; machinery room; contains the world clock)
- **tower_landing_2** (mid-level observation deck, safe rest)
- **tower_landing_1** (lower landing, exits to mid-city)

**NPCs:** Clockmaster (grumpy, maintains the tower; gives maintenance-themed quests), Observation Attendant (guide; sells maps).
**Items:** Brass keys, pocket watch (time-sensitive item, shows server time), oil can.

#### 1.2 Academy of Aetheric Arts (map_z: 1)
- **academy_courtyard** (central quad; lecture posters)
- **library_main** (vast repository; many books; Librarian NPC)
- **alchemy_lab** (potions, reagents; Professor Aldwin; gives ingredient-hunting quests)
- **artifice_workshop** (golems, constructs; Professor Mirabel)
- **dormitory** (student housing; safe rest)

**NPCs:** Headmaster Cornelius (aging, quest-giver: "restore the archive"), Librarian (sells research materials), Professors Aldwin & Mirabel (quest givers).
**Items:** Spellbooks, vials, alembic, student robes (wearable, gives trait).

#### 1.3 Market District (map_z: 0)
- **grand_plaza** (central hub; fountains; sky-gazers)
- **market_row_east** (produce, food vendors)
- **market_row_west** (crafts, curiosities)
- **smithy_district** (metal-workers; vendor NPC; sells weapons/armor)
- **curiosity_shop** (owner: eccentric Dealer; sells rare items, potions, one-of-a-kind trinkets)

**NPCs:** Market Master (administrator), multiple vendor NPCs (with shops), Blacksmith (forge master; sells weapons/equipment), Dealer (curiosity vendor).
**Items:** Everything—food, coins, basic weapons, armor, curiosities.

#### 1.4 Residences (map_z: 1)
- **clockwork_manor** (wealthy merchant house; safe rest; key-locked)
- **scholar_apartments** (academic living; safe rest)

#### 1.5 Undercity Sewers (map_z: -1)
- **sewer_junction_main** (central hub; grates; steam vents)
- **sewer_tunnel_north**, **_east**, **_west**, **_south** (maze of tunnels)
- **steam_foundry_antechamber** (heavy doors; hot; machinery sounds)
- **maintenance_alcove** (workers' rest area; *not* safe rest—grungy)

**Aesthetic:** Damp stone, wrought-iron grates, echoing water, steam hissing from vents, oil-stained walls. Some areas flooded ankle-deep.

**NPCs:** Maintenance Crew (work gang; can offer labor-related quests), Sewer Guide (knows the maze; sells maps), Vagrants (lore-givers; tell stories of the city's history).
**Items:** Tools, oil cans, salvage, copper wire, rusted machinery parts (lore-items).

**Lighting notes:** Dark; players need torches or light-source items to navigate safely.
**Weather:** Not weather-sensitive (underground), but always damp/musty.

#### 1.6 Deep Foundry (map_z: -2)
- **foundry_floor** (massive forge; molten metal; very hot; extremely bright)
- **furnace_chamber** (the furnace itself; dangerous; lore-rich)
- **storage_vault** (metal ingots, finished goods)

**NPCs:** Forge Master (ancient, mysterious; gives artifact-crafting quests).
**Items:** Steel ingots, rare metals, cursed tools (flavor).

**Notes:** Very hostile environment (extreme heat); optional area for advanced players; lore suggests it's been abandoned for centuries but the forge still burns.

---

### 2. **Ancient Forest: Whisperwood** (expansive horizontal)

**Aesthetic:** Old-growth temperate/subtropical forest, misty mornings, shafts of light through dense canopy, sounds of wildlife, ancient standing stones, mushroom rings, crystal-clear streams.

**Core theme:** An unexplored wilderness outside the city. Layered ecology: forest floor, mid-canopy, treetop city. Deep underground cave network below.

#### Map structure

```
Levels (map_z):
  1 — Canopy City (treetop dwellings; rope-bridge network)
  0 — Forest floor (clearings, trails, streams; main exploration area)
  -1 — Cave system (2 levels of caverns; crystal caves, underground lake)
```

#### 2.1 Forest Floor (map_z: 0)

**Spatial layout:** Forest trails radiate from central Whispering Clearing. Each "direction" branches into sub-trails (multiple rooms per cardinal direction).

- **whispering_clearing** (central hub; ancient standing stone; safe rest)
- **north_trail**, **south_trail**, **east_trail**, **west_trail** (four main paths)

**North branch (darker, more threatening):**
- **north_trail** → **old_oak_grove** → **shadow_thicket** (dangerous; lurking danger flavor)

**South branch (pastoral):**
- **south_trail** → **meadow_clearing** → **wildflower_glade** → **babbling_stream** (beautiful, peaceful)

**East branch (mysterious):**
- **east_trail** → **monolith_grove** (standing stones; eerie)
- **east_trail** → **mushroom_circle** (fairy rings; lore-rich)

**West branch (industrial/sad):**
- **west_trail** → **old_lumber_mill** (abandoned; nature reclaiming; melancholy)
- **west_trail** → **flooded_quarry** (water-filled; dangerous edges)

**NPCs:**
- **Ranger Elena** (in Whispering Clearing; quest giver: "Map the forest trails")
- **Hermit Mage** (in Old Oak Grove; gives knowledge-exchange quests)
- **Merchant Caravans** (traveling between clearings; seasonal presence)
- **Fey creatures** (flavor NPCs; don't necessarily offer quests; add color)

**Items:** Herbs, mushrooms, berries, wood (crafting materials), ancient coins (lore), carved tokens (Fey-related).

**Lighting notes:** Variable; dappled light in clearings, darker on trails. Items like lanterns/torches useful but not required (light_level = 0.5 / medium).
**Weather:** Rain/mist common; fog can reduce visibility flavor (future feature). Clear days alternate with overcast.

#### 2.2 Canopy City (map_z: 1)

**Aesthetic:** Treehouses, rope bridges, wind chimes, bird calls, soft moss, hanging gardens.

- **elder_tree_hub** (central treehole; communal gathering space)
- **weaver_platform** (NPC: Weaver artisan)
- **hunter_lodge** (Ranger base; safe rest)
- **merchant_branch** (trading post; vendor)
- **healer_nest** (healer NPC; lore-rich; can purchase salves/tonics)

**NPCs:**
- **Elder Oakwhisper** (leader; gives stewardship quests)
- **Weaver Thistle** (artisan; sells woven goods)
- **Hunter Sage** (provides travel supplies)
- **Healer Moss** (sells potions; gives ingredient-finding quests)

**Items:** Woven cloth, feathers, seeds, rope, healing salves.

**Traversal:** Rope bridges between platforms. (Future feature: rope-bridge events? Wind swaying bridges?)

**Safe rest:** Hunter Lodge.

#### 2.3 Cave System (map_z: -1 & -2)

**Map structure:**
```
Level -1:
  cave_entrance (from forest floor)
  → limestone_passage
  → crystal_cavern (main chamber; lit by bioluminescent crystals)
  → underground_lake (shallow; wading; fish in water; mystery)
  → side_cavern_a, _b, _c (small dead-end rooms with treasures/puzzles)

Level -2:
  deep_passage (from level -1)
  → bone_chamber (fossils; ancient remains)
  → lava_tube (dried lava; otherworldly formations)
  → sealed_vault (locked; key hidden in crystal cavern)
```

**Aesthetic:** Limestone walls, stalactites, bioluminescent fungi and crystals, echoing drips, smell of minerals and deep earth, sense of age and isolation.

**NPCs:**
- **Geomancer Shard** (crystal-touched sage; lives in Crystal Cavern; quest giver)
- **Skeleton Keeper** (flavor; in Bone Chamber; doesn't interact but adds atmosphere)

**Items:** Crystals (crafting), fossils (lore), luminescent moss (lighting item; can be picked up), ancient relics (flavor).

**Lighting notes:** Crystals provide natural glow (light_level = 0.7); most areas navigable without torches but feel richer with them.
**Weather:** Completely weather-proof; underground.

**Notes:** Deep lore anchor; highest-level puzzle/exploration content in the forest zone.

---

### 3. **Coastal Settlement: Port Veridian** (trade hub, transitional)

**Aesthetic:** Sea town; fishing docks, warehouses, taverns, shipyards, salt-worn wood, rope-and-rigging everywhere, gulls, sea-spray smell.

**Core theme:** Gateway zone; connects city to wider world (future feature: sea travel?). Lower-class, rough-around-the-edges. Good starting point for merchant/trade quests.

#### Map structure (all map_z: 0)

- **docks_main** (loading/unloading; dock workers; central hub)
- **shipyard** (under construction; NPC: Shipwright; sells special items)
- **maritime_tavern** (sailor hangout; safe rest; lore repository)
- **warehouse_district** (storage; some areas locked; treasure hiding)
- **fisherfolk_quarter** (residential; nets drying; smell of fish)
- **lighthouse** (tower; climbed via stairs; Keeper NPC)

**NPCs:**
- **Captain Iris** (dock master; quest giver: "Manage cargo")
- **Shipwright Thorne** (builds/repairs; sells rare ship-salvage items)
- **Tavern Keeper Sal** (story-teller; gives information quests)
- **Lighthouse Keeper** (gives navigation/scouting quests)

**Items:** Rope, netting, fish, sea-glass (decoration), ship-salvage (crafting), trade goods.

**Safe rest:** Maritime Tavern.

**Notes:** Low-magic, high-grit aesthetic. Good contrast to City and Forest.

---

## Content Roadmap — Detailed Tasks

### Phase 1: Foundation Zones (Weeks 1–2)

Focus: Build the world structure, test room/NPC/item basics across all zones.

#### P1.1 — Steampunk City core skeleton ✅ (2026-07-10, v0.76.0)
- [x] Steampunk City: Clock Tower (4 rooms — Tower Peak, Clockworks Chamber, 2 landings)
- [x] Steampunk City: Market District (6 rooms — Grand Plaza, Market Row E/W, Smithy, Curiosity Shop, Tavern)
- [x] Steampunk City: Undercity Sewers (6 rooms, dark — junction + 4 tunnels + foundry antechamber)
- [x] Add 3 test NPCs (Clockmaster Grimlock, Blacksmith Thorne, Dealer Vex — shopkeepers/quest-givers; below the 5–8 target, revisit in Phase 3)
- [x] Create 15 basic items (weapons, armor, tools, trade goods — below the 20–30 target, revisit in Phase 2)
- [x] Map exits carefully; `world_cli validate` passing (23 rooms added, all refs resolved)

**Verification:** Can navigate all four levels (z=2..-1), meet NPCs, inspect items. Full-world traversal is now covered by an automated reachability regression (`tests/tools/test_world_content_reachability.py` — every room reachable from the `village_square` seed except board-only transit vehicle rooms). A manual in-client playtest (actually walking the UI) is a separate check and remains outstanding.

#### P1.2 — Whisperwood core skeleton ✅ (2026-07-10, v0.77.0)
- [x] Whisperwood: Forest Floor central clearing + 4 main trails (16 rooms total)
- [x] Whisperwood: Canopy City (5 rooms)
- [x] Whisperwood: Cave entrance + crystal cavern (7 rooms across 2 levels, incl. locked sealed_vault)
- [x] Add 2 Whisperwood NPCs (Ranger Elena, Geomancer Shard — below the 4–6 target, revisit in Phase 3)
- [x] Create 8 forest-themed items (herbs, mushrooms, crystals, Fey token, lore items)

**Verification:** `world_cli validate` passing (28 rooms added, all refs resolved). Lighting: caves dark (0) except crystal_cavern/underground_lake lit; note engine's `light_level` is int-only (0/1), so the roadmap's fractional 0.5/0.7 "dappled" figures were mapped to the nearest valid value — see commit `8ddd112`. Full-world traversal is now covered by an automated reachability regression (`tests/tools/test_world_content_reachability.py`); a manual in-client playtest remains a separate, still-outstanding check.

#### P1.3 — Port Veridian skeleton ✅ (2026-07-10, v0.77.0)
- [x] Port Veridian: Docks, Tavern, Warehouse, Lighthouse (22 rooms — expanded well past the original 6-room sketch: docks hub + shipyard cluster + fisherfolk cluster + warehouse cluster incl. locked vault + promenade/tavern/lighthouse loop)
- [x] Add 4 port NPCs (Captain Iris, Tavern Keeper Sal, Lighthouse Keeper, Shipwright Calloway)
- [x] Create 11 nautical items (rope, netting, salvage, sea glass, warehouse key, tavern fare)

**Verification:** `world_cli validate` passing (22 rooms added, all refs resolved). Port is now interconnected with the rest of the world via the `river_bend` coast-road connector (Whisperwood ↔ Port Veridian) — see the zone-linking note below. That interconnection is now guarded by an automated reachability regression (`tests/tools/test_world_content_reachability.py` — every port room is reachable from the `village_square` seed). A manual in-client trade test (buying/selling at port shops through the UI) is a separate check and remains outstanding.

**Phase 1 world totals:** 99 rooms, 78 items, 10 NPCs, 3 quests across 4 zones
(town, wilderness, cave — Ashmoore — plus cogsworth, whisperwood, port_veridian).

**Zone linking (done, v0.79.0; field terminology updated by later schema work):** the four zones
now form one traversable graph via three single-room outdoor road connectors:

- `old_trade_road` (`zone: cogsworth`) — an old cobbled trade road linking Ashmoore's
  `deep_forest` (wilderness) to Cogsworth's `market_row_west`.
- `forest_road` (`zone: whisperwood`) — a quiet road linking Cogsworth's `smithy_district`
  to Whisperwood's `west_trail`.
- `river_bend` (`zone: port_veridian`) — a riverside footbridge where the forest stream runs
  out to the coast, linking Whisperwood's `babbling_stream` to Port Veridian's `tide_pools`.

All connectors are open (no locks), outdoor, `terrain: road`, and reachable from
`village_square`; `world_cli validate` reports zero reachability warnings.

---

### Phase 2: Rich Item Inventory (Week 2–3)

Build a diverse inventory of item *types* and *instances* that test the engine's item system.

#### P2.1 — Weapons (20+ items) ✅ (2026-07-11, v0.81.0)
- [x] Swords: iron, steel, decorated, crude, enchanted-flavor (Cogsworth longsword, gearwork saber, crude cleaver, sailor's cutlass)
- [x] Axes, maces, spears, pikes (foundry battleaxe, riveted war mace, footman's spear, brass pike, boarding axe, hunter's hatchet)
- [x] Bows, crossbows (ranged) (clockwork crossbow, ranger's longbow, hunter's shortbow)
- [x] Daggers, knives (off-hand) (hunting knife, throwing dagger, flint knife, rigging knife, belaying pin)
- [x] Each weapon: unique description, `weight`, `quality` tier, `value`, `slot: main_hand`/`off_hand`

**Guidance:** Item descriptions should evoke the world (e.g., "A steel blade forged in Cogsworth's foundry, still warm from the anvil").

**Test:** Equip weapons; drop/pick up; verify weight calculations work. — 21 weapons added, `world_cli validate` clean; stocked into Thorne's smithy + placed loose across all three new zones.

#### P2.2 — Armor (20+ items) ✅ (2026-07-11, v0.81.0)
- [x] Leather gear (light) (studded leather jerkin, ranger's leather cuirass, work apron)
- [x] Chain mail (medium) (riveted chainmail hauberk, brass scale shirt, leaf-scale vest)
- [x] Plate armor (heavy) (iron plate cuirass, salvaged breastplate, iron greaves, steel sabatons, brass gauntlets)
- [x] Cloaks, hats, boots (wearable; hooded forest cloak, storm hood, oilskin coat, sailor's cap — several grant a `warmth_bonus` effect)
- [x] Each armor: `wearable: true`, appropriate `slot`, `weight`, `value`

**Test:** Equip multiple armor pieces; inventory weight; wear/unequip. — 21 armor pieces added across `torso`/`head`/`hands`/`legs`/`feet`/`back`/`waist` slots; `world_cli validate` clean.

#### P2.3 — Utility & Crafting (30+ items) ✅ (2026-07-11, v0.82.0)
- [x] Tools: hammer, lockpick, wrench, shovel, pickaxe (cross-peen hammer, jeweler's lockpick, iron pickaxe, shovel, pry bar, brace drill, tin snips — `mechanical_wrench` already existed)
- [x] Light sources: torch, lantern, candle, glow-stone (pitch torch, brass hand lantern, beeswax candle, Whisperwood glowcap lantern, pocket glowstone — all `light: 1`)
- [x] Containers: backpack, pouch, satchel (leather backpack `capacity: 30`, canvas satchel `15`, belt pouch `5`, forager's basket `12`)
- [x] Crafting materials: wood, metal ingots, herbs, crystals, thread (iron/steel/copper/brass ingots, oak plank, raw crystal shard, flax thread, tanned hide, beeswax)
- [x] Rope, chain, nails, springs, gears (tarred twine, mooring chain, iron chain, nail pouch, clockwork springs, assorted gears, sinew bowstring, kindling)
- [x] Each item: rich lore, `weight`, `value`, thematic zone placement

**Test:** Pick up multiple utility items; carry tests; light sources in dark rooms. — 33 items added; metals in the Cogsworth foundry, wood/fiber/crystal in Whisperwood, cordage at Port; stocked into Thorne/Vex/Calloway. `world_cli validate` clean.

#### P2.4 — Consumables & Potions (15+ items) ✅ (2026-07-11, v0.83.0)
- [x] Healing potions (minor, standard, major) (minor healing draught, healing tonic, major healing elixir)
- [x] Stamina/fatigue remedies (stamina restorative)
- [x] Buff potions (temporary strength, clarity, luck) (draught of vigor → `fortified`, philter of clarity → `keen_minded`; vial of luckwater flavor-only — no luck stat to key it to)
- [x] Poisons (flavor; can't be consumed, but lore-rich) (nightshade extract kept `category: trade_good`, so not drinkable; antidote phial flavor-only — no status-ailment system to cure)
- [x] Food: bread, cheese, fruit, fish, stew (crusty loaf, farmhouse cheese, apples, smoked sausage, venison stew, forest berries, honeycomb — plus existing fish)
- [x] Drink: water, ale, wine, elixir (spring water, brown ale, red wine, hot cider)

**Test:** Consume potions (if mechanic exists); verify effect application. — **Consumption mechanic now exists (v0.90.0):** the `consumables` Tier 2 feature adds `eat`/`drink`/`quaff` and the one-shot `heal`/`apply_effect` item descriptors. Healing potions restore `hp` (15/40/80), the stamina restorative restores `fatigue` (40), and the two buff potions apply the new `fortified`/`keen_minded` EffectDefs. Plain food/drink stay flavor-effect-free by design. `world_cli validate` clean; unit + command tests in `tests/unit/test_consumables.py`.

#### P2.5 — Wearables with Traits (10+ items) ✅ (2026-07-11, v0.84.0)
- [x] Blessed Amulet (grants "Blessed" trait) — `slot: neck`
- [x] Scholar's Robes (grants "Learned" trait) — Scholar's Robes of Insight, `slot: torso`
- [x] Rogue's Cloak (grants "Stealthy" trait) — Rogue's Shadowed Cloak, `slot: back`
- [x] Ranger's Boots (grants "Swift" trait) — Ranger's Swift Boots, `slot: feet`
- [x] Sailor's Ring (grants "Seaworthy" trait) — `slot: finger`
- [x] Plus 6 more: Artificer's Fine Gloves (Precise + skill_bonus), Fey-Touched Cloak, Circlet of Focus (Focused + stat_bonus), Warden's Signet, Tideglass Pendant, Forgemaster's Bracer (Ironhide + warmth_bonus)

**Test:** Equip item; verify trait appears in `score` output; unequip; trait disappears. — 11 items added, one per thematically apt room across all zones. Trait names have no pre-registered `TraitDef` (out of scope for content), so they surface by name with an empty description; `world_cli validate` clean.

#### P2.6 — Keys & Special Items (10+ items) ✅ (2026-07-11, v0.85.0)
- [x] Gate keys, tower keys, vault keys, chest keys (archive master-key, strongroom key, customs seal key, root-iron key — 4 new keys, each opening a new locked room)
- [x] Locked-door test: can't traverse without key; pick it up; traverse succeeds (4 NEW locked exits added — Restricted Archive off `library_main`, Foundry Strongroom off `steam_foundry_antechamber`, Bonded Store off `shipyard_office`, Hollow Oak Cache off `old_oak_grove` — each key placed reachably before its door)
- [x] Puzzle items (idols, crystals, tablets) (Weathered Bronze Idol + Standing-Stone Alcove via `usable_with`/`combination_side_effects`; Carved Bone Tablet)
- [x] Lore items (diary, map, ancient coin — flavor only) (dockmaster's diary, faded sea chart, ancient Veridian coin, foundrymaster's ledger, hermit's field journal)

**Test:** Use key on locked door; verify locked-door system works end-to-end. — 4 new locked rooms (world 100→104 rooms), each with a return exit and reachable from `village_square`; `world_cli validate` clean.

**Phase 3 coordination — RESOLVED (v0.87.0):** `archive_vault_key` was relocated out of the `dormitory` floor placement and is now earned as the reward of Headmaster Cornelius's `restore_the_archive` quest (`rewards.items` → `give_item`). The Restricted Archive is now opened by completing the quest.

---

### Phase 3: NPCs & Interaction (Week 3–4)

Build NPC variety; add dialogue, quests, and flavor.

#### P3.1 — Shopkeeper NPCs (5+ unique) ✅ (2026-07-11, v0.86.0)
- [x] Dealer (Curiosity Shop, Cogsworth): sells rare items; unique banter — `dealer_vex` enriched with collector-commission branch + `find_impossible_thing` quest
- [x] Blacksmith (Smithy, Cogsworth): sells weapons/armor; gives crafting quests — `blacksmith_thorne` enriched with `thornes_rare_commission`
- [x] Herbalist (Alchemy Lab, Academy): sells potions; ingredient-hunting quests — **new** `professor_aldwin` (10-item potion shop + `aldwin_ingredients`)
- [x] Tavern Keeper (Port Veridian): sells food/drink; story-exchange quests — `tavern_keeper_sal` enriched with `sals_sea_stories`
- [x] Ranger Quartermaster (Canopy City): sells travel supplies; scouting quests — **new** `hunter_sage` (12-item travel shop + `sage_scout_stones`)

**For each NPC:**
- [x] 3–5 unique dialogue lines
- [x] Emoji/appearance descriptor
- [x] Quest offer (simple: "bring me X"; medium: "explore Y"; complex: multi-step)
- [x] Shop inventory (5–10 items each)

**Test:** Talk to NPC; see dialogue; buy from shop; complete quest.

#### P3.2 — Quest-giver NPCs (5+ unique) ✅ (2026-07-11, v0.87.0)
- [x] Academy Headmaster (restore the archive) — **new** `headmaster_cornelius`; quest `restore_the_archive` rewards the archive vault key + scholar's robes
- [x] Ranger Elena (map the forest) — enriched with three-state before/in-progress/after dialogue around the existing `map_forest_trails`
- [x] Clockmaster (repair the tower) — dangling `repair_tower_bearing` now defined (bring `brass_shavings`); after-completion dialogue added
- [x] Captain Iris (manage cargo shipments) — dangling `manage_cargo_shipments` now defined (survey warehouses + haul a crate); after-completion dialogue added
- [x] Geomancer Shard (seek the sealed vault) — enriched with before/after dialogue around the existing `the_sealed_vault`
- [x] **Bonus:** Lighthouse Keeper's dangling `scout_coastal_waters` also defined (closes all three pre-existing dangling `start_quest` references)

**For each quest:**
- [x] Clear objective description
- [x] Reward (coins-as-item, Phase 2 item, and/or xp; "trait mark" = a `grant_trait` wearable)
- [x] Dialogue before/after completion (gated on `npc_remembers` and/or quest completion flags)
- [x] Prerequisite quest or free-for-all (all free-for-all; started via dialogue `start_quest`)

**Test:** Accept quest; complete objective (travel to location, collect item, etc.); turn in; receive reward.

#### P3.3 — Flavor/Lore NPCs (10+) ✅ (2026-07-11, v0.88.0) — 13 new
- [x] Vagrants in sewers (tell city history) — `vagrant_pike`, `vagrant_needle`
- [x] Scholars in academy courtyard (gossip) — `scholar_finch`, `scholar_dabble`
- [x] Sailors in tavern (sea stories) — `sailor_bright`, `sailor_gull`
- [x] Fey creatures in forest (cryptic remarks) — `fey_wisp`, `fey_gloam`, `fey_thornkin`
- [x] Skeleton Keeper in bone chamber (pure atmosphere, silent) — `skeleton_keeper`
- [x] Canopy City color (artisan/steward/healer) — `weaver_thistle`, `elder_oakwhisper`, `healer_moss`
- [x] Lighthouse Keeper (weather observations) — already present (Phase 1) with navigation lore + now a scouting quest (P3.2)

**For each:** 2–3 unique lines, no quest, just color. Verify they appear/disappear as expected.

#### P3.4 — NPC Movement (3+ NPCs)
Room-list/loop **patrol** now has NPC-specific glue on top of `MobileRouteService` (v0.99.0).
The older scheduled relocation examples now also support day/night behavior and simple AI
branching, while Scout Wren uses a visible route-backed patrol. Zone-wide autonomous roam is
also available through `NPC.ai.mode: wander`.
- [x] Dock Worker — `dock_worker_bram` relocates `docks_main` (hr 8) → `warehouse_district` (hr 18)
- [x] Night Guard — `night_watch_holt` relocates `grand_plaza` (hr 8) → `smithy_district` (hr 20), switching between daytime defensive posture and an alert night patrol
- [x] Forest Scout — `forest_scout_wren` loops `whispering_clearing` → `old_oak_grove` → `wildflower_glade` via `ai.mode: route`, broadcasting route departure/arrival through NPC-specific `RouteHooks`.

**Test:** Check NPC location at different game-hours; confirm the room-relocation actually fires on `HOUR_CHANGED`.

---

### Phase 4: World Polish & Advanced Features (Week 4+)

#### P4.1 — Descriptive Writing Pass ✅ (2026-07-11, v0.90.1)
- [x] Room descriptions: vivid, sensory, 50–150 words each — audit found the baseline already strong
  (Whisperwood/Port/Ashmoore all vivid and near-bar). Upgraded the six genuine outliers, all
  early-built (P1.1) Cogsworth rooms that read flat/tell-y/manual-like, to 77–98 words in-voice:
  `sewer_tunnel_south`, `market_row_west`, `scholar_apartments`, `dormitory`, `clockwork_manor`,
  `tower_landing_2`. (Tight-but-vivid rooms in the 36–49w range were left as-is, not padded for count.)
- [x] Item descriptions: unique, evocative, 1–3 sentences — 190/198 already met the bar; the 8
  sub-10-word entries are intentionally terse disambiguation/puzzle keys (near-identical text is the
  vault-hall puzzle mechanic) and were deliberately left unchanged.
- [x] NPC descriptions: appearance, demeanor, memorable details — 28/29 already excellent; gave the
  Ashmoore innkeeper Mira a memorable detail (cellar keys; never writes a tab yet never misremembers one).
- [x] **NO** placeholder text ("a generic sword"); every item has character — confirmed none present.

**Quality bar:** Descriptions should feel like a novel excerpt, not a game manual.

#### P4.2 — Thematic Consistency ✅ (2026-07-11, v0.90.2) — audit-only, no fixes needed
- [x] **Steampunk City:** brass, copper, steam, gears, industry — confirmed throughout Cogsworth
  prose and item set (ingots, gears, clockwork springs, brass fittings, foundry tools).
- [x] **Whisperwood:** mist, ancient stones, wildlife, growth, mystery — confirmed; the zone holds
  **zero** metal/gear items (crystals, mushrooms, herbs, hides, bows, fey tokens, oak/wood only).
- [x] **Port Veridian:** salt, wood, rope, labor, trade — confirmed (rope, nets, fish, salvage,
  tarred twine, boat chain, cutlass/harpoon).
- [x] Room exits/connections make geographical sense — verified the three cross-zone connectors are
  bidirectional with geographically-consistent opposite-direction exits: `old_trade_road`
  (west↔`deep_forest`, south↔`market_row_west`), `forest_road` (north↔`smithy_district`,
  east↔`west_trail`), `river_bend` (north↔`babbling_stream`, east↔`tide_pools`). All neighbor rooms
  carry the reciprocal exit.
- [x] Items match zone aesthetic (no "steel gears" in forest floor) — audited all 165 `room_items`
  placements grouped by zone; no cross-contamination found (the example failure mode — metal/gears in
  Whisperwood — does not occur). Nothing to relocate.

#### P4.3 — Lighting & Atmosphere ✅ (2026-07-11, v0.90.2) — audit-only, all correct
**Note:** `Room.light_level` is int-only (0 or 1), *not* fractional — the "0.5/0.7 dappled" figures
in the original sketch below are aspirational, never real schema values (documented in P1.2, commit
`8ddd112`). The engine gates `take`/`drop`/etc. via `CommandCondition.REQUIRES_LIGHT`: `light_level == 0`
blocks those verbs unless the actor carries a lit source (`command_conditions.py` `_light_check`).
- [x] Dark rooms: caves, undercity, sewers, sealed vaults (light_level = 0) — confirmed all 14 dark
  rooms are `0` and their prose reads dark: Ashmoore cave (`cave_chamber`/`cave_pool`/`cave_alcove`),
  Cogsworth undercity (`sewer_junction_main` + 4 tunnels + `steam_foundry_antechamber`), Whisperwood
  caves (`whisperwood_cave_entrance`, `limestone_passage`, `deep_passage`, `bone_chamber`,
  `sealed_vault`). `deep_passage` explicitly reads "the glow fades… true, absolute dark" (correctly 0).
- [x] Bright/normal rooms (light_level = 1) — confirmed the other 90 rooms are lit and read lit.
  Spot-checked the bioluminescent-cave edge cases the roadmap flagged: `crystal_cavern` and
  `underground_lake` are correctly `1` — their prose explicitly describes bioluminescent crystal glow,
  not darkness. `cave_tunnel` is correctly `1` (prose: "not entirely dark — a faint phosphorescence")
  and `cave_entrance` correctly `1` (daylight at the hillside mouth).
- [x] Navigation challenge verified against the mechanism (not fractional): dark rooms block
  take/drop without a carried light. **No misassignments found — zero light-level edits made.**

#### P4.4 — Safe-Rest Zones ✅ (2026-07-11, v0.90.2) — audit-only, 9 rooms all justified
- [x] Marked rooms as `safe_rest: true` — **9 rooms** (one over the 5–8 *estimate*; per the roadmap's
  acceptance bar the real test is "thematically placed, not random", which 5–8 approximates rather than
  caps). Each is a plausible rest location; none is a workshop/alley/hazard mistakenly tagged:
  - `wandering_crow_inn` (Ashmoore inn) — an actual inn with a landlord.
  - `tower_landing_2` (Cogsworth clock-tower observation deck) — cushioned benches "worn soft by
    decades of quiet watchers"; roadmap-named safe-rest.
  - `dormitory` (Academy student housing) — cots, common room, porter's bell keeps the peace; roadmap-named.
  - `clockwork_manor` (wealthy merchant townhouse) — carpeted, secured by a heavy iron door; roadmap-named.
  - `scholar_apartments` (faculty/senior-student residence) — quiet study wing; roadmap-named.
  - `clockwork_tavern` (Cogsworth market tavern) — a tavern serving "hearty and reliable" food/drink;
    a tavern is a canonical rest spot even though not in the original zone sketch. Thematically sound.
  - `whispering_clearing` (Whisperwood central clearing, ancient standing stone) — roadmap-named.
  - `hunter_lodge` (Canopy City ranger base) — "the safest, most solid-feeling place in the whole
    treetop settlement"; roadmap-named.
  - `maritime_tavern` (Port Veridian sailor tavern) — roadmap-named.
- [x] Thematic: inns, taverns, scholar quarters, ranger lodges, a merchant manor, an observation deck
  (not random) — confirmed; no hostile/hazardous room is tagged safe.
- [x] Verify players can sleep there; can't (reliably) in hostile areas — mechanic read in
  `features/fatigue/service.py` `sleep()`: in a `safe_rest` room `sleep` is a guaranteed full restore
  (advances clock, dream flavor); **anywhere else it is a survival skill-check gamble** (cold-weather
  penalty from insufficient warmth), and on failure the sleep is interrupted for only a partial,
  dreamless rest. So non-safe-rest rooms are not *blocked* from sleeping but are unreliable/risky —
  matching the "can't safely sleep in hostile areas" intent. No `safe_rest` flags added or removed.

#### P4.5 — Weather Integration (if time)
- [x] Coastal zones: occasionally foggy/stormy — **done via a traveling storm front.** Added `coastal_squall` to `world_content/weather_fronts.yaml` (`path: [port_veridian, port_veridian, whisperwood]`, `room_effect: storm_lashed`, autumn/winter): it rolls a per-hour chance, sweeps the coast → river connector → forest, lashes outdoor rooms in each zone, and auto-skips `indoor: true` interiors. This remains the transient storm-front layer alongside the Sprint 80 per-zone climate model.
- [x] Forest: rainy/misty common — **done (v0.99.0).** `world_content/weather_fronts.yaml` now includes a `climates.whisperwood` seasonal table weighted toward fog/rain; `ZoneClimateService` rolls it daily and narrates only to occupied outdoor Whisperwood rooms.
- [x] City: clear/overcast (not weather-sensitive underground) — **done (v0.99.0).** `climates.cogsworth` is weighted toward clear/overcast states, and existing `Room.indoor` filtering keeps underground/interior rooms from receiving sky-weather narration.
- [x] Test transit: blocked by weather on specific routes (e.g., ship departure in storm) — **done.** Added the first `transit:` section in `world_content/world.yaml`: the **Harbor Ferry** (`harbor_ferry`) runs `docks_main → breakwater` from an open-deck vehicle room (`harbor_ferry_deck`, `indoor: false`), `weather_sensitive: true`, `blocking_weather: [thunderstorm, heavy_rain, blizzard]`. Grounding is enforced by `TransitService.may_depart` against the global `WorldClock.weather`. Ticket item `harbor_ferry_token` (3 placed at the docks).

#### P4.6 — Indoor/Outdoor Tagging — ✅ DONE (real field, not a workaround)
- [x] **RESOLVED:** `Room.indoor: bool` is a real, shipped Tier 1 schema field (Sprint 69, v0.72.0). No naming-convention/comment workaround is needed — set `indoor: true` directly on interior rooms in world YAML.
- [x] All 4 zones tagged (30+ rooms); a content pass closed the one gap (5 Cogsworth sewer rooms) and confirmed full, correct coverage.

**Note:** This *supersedes* the earlier "Option B: naming convention" decision — the field exists; use it. See **Blocked Items §1**.

---

## Blocked Items & Dependencies

### 1. **Indoor/Outdoor Flag**
**Status:** ✅ Resolved — real field shipped (Sprint 69, v0.72.0)
**Impact:** Weather effects (ambient + storm narration is suppressed indoors), spawn logic, future day-cycle NPC behavior
**Mechanism:** `Room.indoor: bool` is a live Tier 1 schema field in `src/lorecraft/engine/models/world.py`, threaded through world YAML and documented in `.agents/skills/worldbuilding/SKILL.md`. Set `indoor: true` on sheltered interiors (inns, cellars, shops, vaults, caves, sewers). No naming-convention or comment workaround is needed — the earlier "Option B" plan is obsolete.
**Coverage pass (v0.79.1):** (a) Closed the one tagging gap found — 5 Cogsworth underground sewer rooms (`sewer_junction_main`, `sewer_tunnel_north/east/west/south`) that were missing `indoor: true` despite matching their sibling `steam_foundry_antechamber` and Ashmoore's `cave_tunnel`/`cave_chamber`. (b) Swept all rooms across Cogsworth, Whisperwood, and Port Veridian and confirmed full, correct indoor/outdoor coverage (30+ rooms tagged appropriately; open plazas/courtyards/trails/docks/yards left outdoor). A few treetop-settlement rooms (`hunter_lodge`, `healer_nest`, `elder_tree_hub`) are intentionally left outdoor — they are a uniformly open-air canopy village with wind/weather cues in their descriptions.

### 2. **Spawn / Respawn Rates**
**Status:** ✅ Supported (v0.99.0)
**Current:** `features/spawns` loads `world_content/spawns.yaml` and tops a zone back up to
`max_count` clones of a template NPC every `every_ticks` world ticks. Shipped content includes
Whisperwood wisps and Cogsworth sewer vagrants.
**Remaining future scope:** Persisted spawn-controller state and richer template-only NPC authoring
could be added later if needed; the data-driven random spawn/respawn loop itself is live.

### 3. **Climate/Zone Weather Binding**
**Status:** ✅ Supported (v0.99.0)
**Current:** Global `WorldClock.weather` still exists, but `features/weather/climate.py` now adds
Tier 2 per-zone climate rolls from `world_content/weather_fronts.yaml`'s `climates:` block. This
gives standing zone bias: Whisperwood is commonly foggy/rainy; Cogsworth is commonly clear or
overcast. Narration is scoped to occupied outdoor rooms in the matching zone.
**Still supported alongside climate:** traveling storm fronts remain transient, zone-path storms;
weather-blockable transit still keys off the global clock weather.

### 4. **Ambient / Timed Room Events**
**Status:** ✅ Supported for timed room-feed flavor (v0.99.0)
**Current:** Rooms can declare `ambient_events:` entries with `text`, `every_ticks`, and `chance`.
`RoomAmbientService` emits them on world ticks only to occupied rooms.
**Remaining future scope:** dynamic rewriting of the room's base description by time/weather is still
not built; use feed flavor lines for ambient motion and recurring sensory details.

### 5. **NPC Reputation / Faction Standing**
**Status:** ⚠️ Engine has reputation, but not NPC-specific.
**Current:** Player reputation per faction exists (audit log); NPCs don't have it yet.
**Engine work needed:** NPC faction data + standing checks (Tier 1 extension)
**Workaround:** Simple quest chains instead (NPC remembers if you did their quest).
**Plan:** Phase 3 quests use "complete this quest to progress" rather than standing thresholds.

### 6. **Day-Night Cycle NPC Behavior**
**Status:** ✅ Supported for scheduled room/behavior/AI state changes
**What it is:** NPCs work during day, sleep at night; shops close at evening.
**Engine work:** `NPC.schedule` now owns hour-based NPC state changes in the Tier 2 NPC
feature. Schedule rows may set `target_room_id`, `behavior`, and/or `ai`; `ai: {}` clears a
simple autonomous loop for off hours.
**Remaining scope:** There is still no first-class shop-hours policy, service-refusal rule,
or visible walked commute narration; use scheduled relocation/behavior changes for now.

### 7. **Duplicate room ids (`meadow_clearing`, `cave_entrance`) — ✅ RESOLVED (2026-07-11)**
**Status:** ✅ Fixed. Whisperwood's two colliding rooms were renamed; no duplicate ids remain in
`world_content/world.yaml`.
**What it was:** Two room ids each appeared as an `id:` **twice** in `world_content/world.yaml` —
once in the Ashmoore wilderness zone and once in Whisperwood (different physical rooms, identical
ids): `meadow_clearing` and `cave_entrance`. YAML/loader took the last-wins entry, so any exit,
`room_items`, `NPC.schedule`, or `room_visited` quest condition that referenced either id resolved
ambiguously.
**Fix applied:** Whisperwood's copies were renamed to `whisperwood_meadow_clearing` and
`whisperwood_cave_entrance` (Ashmoore's originals kept their unprefixed ids). Every Whisperwood-side
reference was repointed in the same change: the two `id:` definitions, four meadow exits
(`south_trail` south, `fern_hollow` east, `wildflower_glade` north) plus the cave exits
(`shadow_thicket` down, `limestone_passage` south), and the `silverleaf_herb` `room_items` placement.
The Ashmoore-side references (including the `deep_delver` mark in `marks.yaml`, which is about the
Ashmoore cave) were left untouched. `world_cli validate` stays clean at 104 rooms with all
references resolved and zero duplicate ids.
**Historical color (was the Phase 3 workaround):** While the collision existed, new Phase 3 content
deliberately avoided both ids — the Forest Scout (P3.4) and all P3.x forest quests/dialogue targeted
unambiguous forest ids only (`whispering_clearing`, `old_oak_grove`, `wildflower_glade`,
`monolith_grove`, `mushroom_circle`, `babbling_stream`). That avoidance is no longer a constraint;
both `whisperwood_meadow_clearing` and `whisperwood_cave_entrance` are now safe to reference directly.

---

## Content Writing Guidelines

### Room Descriptions

**Quality standard:** Evocative, specific, 50–150 words. Show, don't tell. Emphasize sensory details.

**Good example:**
> The forge exhales a wave of heat before you even cross the threshold. A barrel of black water hisses where hot metal cools. Tools hang on pegs with a craftsman's precision: hammers graded from tack to sledge, tongs of every gauge, punches, drifts, and files. The anvil in the centre is pocked and stained with a lifetime of use.

**Bad example:**
> The forge is hot. There are tools here. It is a place where metal is worked.

### Item Descriptions

**Standard:** 1–3 sentences, tactile, suggest the item's story.

**Good examples:**
- "A sword of blue steel, forged in the depths of Cogsworth's foundry. The blade still holds warmth from the anvil."
- "Rope, worn smooth by the hands of dock workers. Smells of salt and tar."
- "A potion of midnight-blue glass, filled with liquid that swirls with its own inner light. The stopper is cork-sealed with wax."

### NPC Descriptions

**Standard:** Appearance + one memorable detail.

**Good examples:**
- "Dealer — a rail-thin merchant with ink-stained fingers and a knowing smile. Collects impossible things."
- "Elena — a ranger with one wolf-grey eye and one missing; a scar maps the story of the missing one."
- "Sal — the tavern keeper. Built like a barrel, red nose from tasting the wares, but his hands are gentle."

---

## Testing Plan

### End-to-End Flows to Verify

1. **Navigation:** Start in Market → traverse all three city levels → descend to sewers → climb back out.
2. **Item collection:** Pick up diverse items across all types; carry heavy load; drop/pick items.
3. **Inventory management:** Check weight/volume; equip/unequip items; check traits apply/disappear.
4. **NPC interaction:** Talk to 5+ NPCs; get dialogue + quest; complete quest; receive reward.
5. **Shop transaction:** Enter shop; list wares; buy item; coins deducted; item added; sell item.
6. **Lighting:** Enter dark room without light source; attempt action (flavor challenge); pick up torch; try again.
7. **Locked doors:** Try to enter vault without key; get rejection; find key; traverse successfully.
8. **Multi-zone travel:** Start in Port Veridian; travel to City; travel to Forest; travel back (verify exit consistency).
9. **NPC patrol:** Visit location with patrolling NPC; move to adjacent room; check NPC moved.
10. **Weather / transit:** (If weather feature is used) Attempt travel during storm; get blocked; wait for clear; traverse.

---

## Success Criteria

- [x] All three zones (City, Forest, Port) are navigable from end to end
- [ ] 80+ unique rooms across all zones (minimum 30 per zone)
- [x] 100+ unique items (weapons, armor, utility, consumables, keys, lore) — 197 items as of v0.85.0 (Phase 2 complete: P2.1–P2.6)
- [x] 15+ NPCs with dialogue and quests — **29 NPCs** as of v0.89.0 (Phase 3 complete: 5 shopkeepers, 6 quest-givers, 13 flavor/lore, 3 scheduled-movement, plus Phase 1 NPCs); 12 quests total
- [x] 5+ locked doors requiring keys (puzzle component) — 8 key-locked exits as of v0.85.0 (4 pre-existing: inner_vault/good_key, sealed_vault/vault_root_key, warehouse_north/warehouse_vault_key, plus the vault-hall door; 4 new in P2.6: Restricted Archive, Foundry Strongroom, Bonded Store, Hollow Oak Cache)
- [x] Dark areas requiring light sources (caves, sewers) — 14 rooms `light_level: 0`; verified against
  `REQUIRES_LIGHT` gating (P4.3, v0.90.2)
- [x] At least 8 safe-rest zones — **9 safe-rest rooms**, all thematically justified (P4.4, v0.90.2):
  `wandering_crow_inn`, `tower_landing_2`, `dormitory`, `clockwork_manor`, `scholar_apartments`,
  `clockwork_tavern`, `whispering_clearing`, `hunter_lodge`, `maritime_tavern`
- [x] Thematic consistency: no "sci-fi" items in fantasy forest, etc. — audited all zones; no
  cross-zone item/aesthetic contamination (P4.2, v0.90.2)
- [x] All items, NPCs, and rooms described in prose (not placeholder text) — confirmed; no placeholder
  text anywhere. Six flat Cogsworth rooms + one NPC upgraded (P4.1, v0.90.1); rest already met the bar
- [x] Full traversal test passing (can visit every room from every other room) — automated regression: `tests/tools/test_world_content_reachability.py` runs `check_room_reachability` over the real `world_content/world.yaml` from the `village_square` seed; the only expected-unreachable rooms are transit vehicle rooms (board-only), derived generically from `transit.lines[].vehicle_room_id`
- [x] No orphaned rooms (every room has at least 2 exits; dead ends exist but can exit) — asserted by the same test: every room has ≥1 exit except transit vehicle rooms (`harbor_ferry_deck`, board/disembark only). Note the "≥2 exits" wording is aspirational; the enforced invariant is "≥1 exit (no dead-end with no way out)", matching the roadmap's own "dead ends exist but can exit" definition
- [ ] CI lint/validation passing (world YAML well-formed; all room IDs unique; all exit targets exist)

---

## Schedule

| Phase | Scope | Target Duration |
|-------|-------|-----------------|
| P1 | Core zone skeletons (rooms, basic NPCs, items) | Week 1–2 |
| P2 | Rich item inventory (100+ items, all types) | Week 2–3 |
| P3 | NPCs, quests, dialogue, patrol | Week 3–4 |
| P4 | Polish, descriptions, thematic pass | Week 4+ |
| **Total** | Full world ready for feature testing | 4 weeks |

---

## Next Steps

1. **Approve this roadmap** (especially design decisions: indoor flag, climate, ambient events)
2. **Create `world_content/zones/` subdirectory structure** to organize by zone
3. **Begin Phase 1:** Export skeleton YAML; verify git workflow (commits per zone, not monolithic)
4. **Implement verification tests** as content is added (room traversal, NPC presence, item availability)
5. **Iterate & refine** based on engine gaps discovered during build

---

## Appendix: Useful References

- **Room schema:** `world_content/world.yaml` (existing Ashmoore example)
- **Item types:** `src/lorecraft/items/` (rarity system, type classification)
- **NPC model:** `src/lorecraft/features/npc/` (NPC creation, dialogue, quest integration)
- **Weather system:** `src/lorecraft/features/weather/` (global weather, transit blocking)
- **Movement/patrol:** `src/lorecraft/services/mobile_route.py`, `src/lorecraft/features/movement/`
- **Shop system:** `src/lorecraft/features/economy/` (vendor management, inventory, pricing)
- **Quest system:** `src/lorecraft/features/quest/` (quest definition, objectives, rewards)
- **Lighting:** `light_level` in rooms; items with light properties (e.g., `emits_light: true`)

---

*World branch created 2026-07-09. Last reconciled with engine support on 2026-07-14. This roadmap document is the source of truth for world-building priorities and status.*
