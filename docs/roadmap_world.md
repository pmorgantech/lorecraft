# Lorecraft World — Roadmap & Build Plan

**Goal:** Build a rich, multi-zone test world to exercise the engine's features across all three tiers (Tier 1 primitives, Tier 2 features, Tier 3 content) with particular attention to areas that are high-risk or low-mileage in the current Ashmoore sample.

**Current date:** 2026-07-09
**Current engine version:** v0.55.3 (multi-level maps, full UI system, NPC/movement framework)
**Status:** Planning phase — all tasks below are feasible with current engine features unless marked **[BLOCKED]**.

---

## Engine Feature Inventory

### ✅ Fully Supported (ready to use now)

| Feature | Support | Notes |
|---------|---------|-------|
| **Multi-level rooms** | `Room.map_z` (v0.55.0) | Floors/levels via z-coordinate; minimap filters by current level |
| **NPCs** | `features/npc/` | Place NPCs in rooms; dialogue trees with pluggable conditions (`actor_reputation_at_least`, `npc_remembers`, flags) and side effects (`give_item`, `start_quest`, `adjust_reputation`, `remember`) |
| **NPC scheduled teleport** | `NPC.schedule` + `NpcScheduler` (`features/npc/scheduler.py`) | Data-driven `[{game_hour, target_room_id}, ...]`; jumps the NPC's room on `HOUR_CHANGED`. **Instant teleport, not pathed movement** — no interim rooms/narration. |
| **NPC context-attached verbs** | `NPC.context_commands` (Sprint 55) | Data-driven custom verbs (e.g. `bow`) available only while the NPC is present, each with `{aliases, help, say, side_effects, requires}` |
| **Weather system** | `features/weather/` | Global weather state; transit lines can block on weather |
| **Item types** | weapon, armor, utility, coin | Color-coded in UI (rarity system available too) |
| **Shops/stores** | `features/shop/` | Create shops with inventory, NPC shopkeepers, prices |
| **Quests** | `features/quest/` | Quest givers, objectives, rewards, dialogue conditions |
| **Locked doors** | `locked: true` + `key_item_id` | Exits can require keys to traverse |
| **Item effects/buffs** | Traits/effects system | Wearable items can grant traits; potions can apply temporary effects |
| **Inventory persistence** | Tier 1 item/inventory model | Items follow players across sessions; weight/volume tracked |
| **Lighting** | `light_level` per room | Dark rooms, illuminating items (torches, lanterns) |
| **Areas/zones** | `area_id` (organizes rooms thematically) | Group rooms by zone for lore/admin purposes |
| **Safe rest** | `safe_rest: true` flag | Rooms where players can safely sleep |

### ⚠️ Partially Supported (needs design/content work)

| Feature | Support | Notes |
|---------|---------|-------|
| **Indoor/outdoor** | ✅ `Room.indoor: bool` — real Tier 1 field (shipped Sprint 69, v0.72.0) | Live in `engine/models/world.py` and world YAML; weather narration (ambient + storms) is suppressed where `indoor: true`. Documented in `.agents/skills/worldbuilding/SKILL.md`. All 4 zones tagged (30+ rooms); see Blocked Items §1 for the closed gap. |
| **Random spawns** | Scheduler-based | Can schedule NPC spawns; respawn rates not yet modeled in world YAML. (Likely needs a spawn template table.) |
| **Climate/biome** | Weather exists but not tied to zones | A forest should have rain/fog; a desert dry heat. No zone-climate mapping yet. (Minor content work, depends on indoor flag.) |
| **Treasure/loot** | Items can be placed in rooms | No randomized loot tables yet. (Tier 2 feature, probably Sprint 16+ backlog.) |
| **Ambient messages** | Not yet | Rooms could narrate ambient events (wind, birds, dripping water). (Tier 2 feature; would need room-effect scheduler.) |
| **NPC fixed-route patrol** | `MobileRouteService` primitive exists, unwired for NPCs | The Tier 1 route-runner (`engine/services/mobile_route.py` — waypoints, ping-pong/loop, dwell/travel ticks, restart-safe state) is genuinely content-agnostic, but today only the **transit** feature instantiates it (ferries/trains). No NPC-specific `RouteHooks` exist to move `NPC.current_room_id` + broadcast arrival/departure on `on_arrive`/`on_depart`. Real but modest glue work — the hard scheduling logic is already built. |
| **Reputation as an NPC behavior gate** | Reputation itself is real; nothing *acts* on it autonomously | `features/reputation` gives per-(player, npc-or-faction) standing with `actor_reputation_at_least` (the one canonical predicate, registered on both the command and dialogue condition registries) and `adjust_reputation` (side effect) — so standing can already gate what a player can *say/do* to an NPC. What's missing is any NPC decision loop that *reads* standing on its own initiative (e.g. to refuse service, flee, or turn hostile without the player first triggering dialogue). |

### ❌ Not Yet Supported (requires engine work)

| Feature | Blocker | Notes |
|---------|---------|-------|
| **[BLOCKED] NPC autonomous behavior (patrol-an-area, aggro, flee, follow)** | No NPC-agency loop | Everything NPC-side today is either scheduled-teleport or player-triggered (dialogue/context verbs). There is no per-tick "NPC decides what to do" loop. Zone-wide roam ("wander anywhere in `area_id: sewers`") isn't built at all — would need new logic to sample a valid room by `area_id` (ideally adjacency-aware) each scheduler tick. `NPC.behavior: str = "defensive"` **exists on the model and round-trips through world YAML/admin API but is never read by any game logic** (confirmed by grep) — dead schema, presumably laid down for a combat-stance system that was never built. |
| **[BLOCKED] Combat / attack system (any trigger source)** | Not built — schema stub only | `models/combat.py`'s `CombatSession` is a bare table (`id, room_id, started_at, status, combatants: JSON`) with **no service, repo, command, event, or side-effect handler anywhere in the codebase**. `features/npc/side_effects.py`'s docstring name-drops `combat.start_combat` only as an *illustrative example* of the registration pattern — never implemented. NPCs cannot act against a player under any condition (reputation, marks, or otherwise) because there is neither an NPC-agency loop nor a combat resolution path for an "attack" to resolve into. Matches `docs/wishlist.md`'s deliberate stance: combat is set aside as "a supporting system, not the centerpiece." |
| **[BLOCKED] Alignment system** | Doesn't exist | Zero references anywhere in the codebase. `features/marks` are discovery/exploration badges (visited rooms, met NPCs, items found), not a morality/alignment axis — don't conflate the two when scripting "good/evil" NPC reactions. |
| **[BLOCKED] Ambient/flavor text rotation** | Needs event loop | Rooms with descriptions that change over time (sunrise, shadows, NPC banter). Needs a timed-event framework beyond schedulers. (Design-time decision: too much scope for foundation?) |
| **[BLOCKED] Weather particle effects** | UI-only, not engine** | Can describe weather in text; visual rain/snow is future stretch. |
| **[BLOCKED] Day/night cycle tied to NPC behavior** | Needs NPC schedule model | NPCs could sleep at night, work during day. The hour-based teleport schedule is a start but isn't behavior-branching (it only relocates). Roadmap future, not critical for testing. |

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

**Zone linking (done, v0.79.0):** the four zones now form one traversable graph via three
single-room connectors, each in its own `area_id`:

- `old_trade_road` (`area_id: trade_road`) — an old cobbled trade road linking Ashmoore's
  `deep_forest` (wilderness) to Cogsworth's `market_row_west`.
- `forest_road` (`area_id: forest_road`) — a quiet road linking Cogsworth's `smithy_district`
  to Whisperwood's `west_trail`.
- `river_bend` (`area_id: coast_road`) — a riverside footbridge where the forest stream runs
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
- [x] Buff potions (temporary strength, clarity, luck) (draught of vigor, philter of clarity, vial of luckwater — flavor-only)
- [x] Poisons (flavor; can't be consumed, but lore-rich) (nightshade extract; antidote phial as its counter)
- [x] Food: bread, cheese, fruit, fish, stew (crusty loaf, farmhouse cheese, apples, smoked sausage, venison stew, forest berries, honeycomb — plus existing fish)
- [x] Drink: water, ale, wine, elixir (spring water, brown ale, red wine, hot cider)

**Test:** Consume potions (if mechanic exists); verify effect application. If no consumption, at least test inventory. — **No consumption mechanic exists** (no registered `apply_effect` key for drinking); 20 items authored as flavor/inventory items only, no `apply_effect` hookup. `world_cli validate` clean.

#### P2.5 — Wearables with Traits (10+ items)
- [ ] Blessed Amulet (grants "Blessed" trait)
- [ ] Scholar's Robes (grants "Learned" trait)
- [ ] Rogue's Cloak (grants "Stealthy" trait)
- [ ] Ranger's Boots (grants "Swift" trait)
- [ ] Sailor's Ring (grants "Seaworthy" trait)

**Test:** Equip item; verify trait appears in `score` output; unequip; trait disappears.

#### P2.6 — Keys & Special Items (10+ items)
- [ ] Gate keys, tower keys, vault keys, chest keys
- [ ] Locked-door test: can't traverse without key; pick it up; traverse succeeds
- [ ] Puzzle items (idols, crystals, tablets—used to solve quests)
- [ ] Lore items (diary, map, ancient coin—picked up but no mechanical use; flavor)

**Test:** Use key on locked door; verify locked-door system works end-to-end.

---

### Phase 3: NPCs & Interaction (Week 3–4)

Build NPC variety; add dialogue, quests, and flavor.

#### P3.1 — Shopkeeper NPCs (5+ unique)
- [ ] Dealer (Curiosity Shop, Cogsworth): sells rare items; unique banter
- [ ] Blacksmith (Smithy, Cogsworth): sells weapons/armor; gives crafting quests
- [ ] Herbalist (Alchemy Lab, Academy): sells potions; ingredient-hunting quests
- [ ] Tavern Keeper (Port Veridian): sells food/drink; story-exchange quests
- [ ] Ranger Quartermaster (Canopy City): sells travel supplies; scouting quests

**For each NPC:**
- [ ] 3–5 unique dialogue lines
- [ ] Emoji/appearance descriptor
- [ ] Quest offer (simple: "bring me X"; medium: "explore Y"; complex: multi-step)
- [ ] Shop inventory (5–10 items each)

**Test:** Talk to NPC; see dialogue; buy from shop; complete quest.

#### P3.2 — Quest-giver NPCs (5+ unique)
- [ ] Academy Headmaster (restore the archive)
- [ ] Ranger Elena (map the forest)
- [ ] Clockmaster (repair the tower)
- [ ] Captain Iris (manage cargo shipments)
- [ ] Geomancer Shard (seek the sealed vault)

**For each quest:**
- [ ] Clear objective description
- [ ] Reward (coins, items, trait mark)
- [ ] Dialogue before/after completion
- [ ] Prerequisite quest or free-for-all

**Test:** Accept quest; complete objective (travel to location, collect item, etc.); turn in; receive reward.

#### P3.3 — Flavor/Lore NPCs (10+)
- [ ] Vagrants in sewers (tell city history)
- [ ] Scholars in academy courtyard (gossip)
- [ ] Sailors in tavern (sea stories)
- [ ] Fey creatures in forest (cryptic remarks)
- [ ] Lighthouse Keeper (weather observations)

**For each:** 2–3 unique lines, no quest, just color. Verify they appear/disappear as expected.

#### P3.4 — NPC Movement (3+ NPCs) — **scope corrected, see Blocked Items**
True room-list/loop **patrol** requires new glue on top of `MobileRouteService` (unwired for
NPCs today — see Blocked Items). Zone-wide roam requires new logic entirely (not built). For
v1 of this world, scope down to what's actually wired:
- [ ] Dock Worker — `NPC.schedule` relocates docks → warehouse at set game-hours (teleport, not a walked loop)
- [ ] Night Guard — `NPC.schedule` relocates city streets → guardhouse after dark
- [ ] Forest Scout — `NPC.schedule` relocates between 2–3 clearings across the day

**Stretch (blocked on engine work):** true patrol (visibly walking a room loop, broadcast to
players present) needs NPC-specific `RouteHooks` built against `MobileRouteService` first — see
Blocked Items. Don't build content that assumes this exists.

**Test:** Check NPC location at different game-hours; confirm the room-relocation actually fires on `HOUR_CHANGED`.

---

### Phase 4: World Polish & Advanced Features (Week 4+)

#### P4.1 — Descriptive Writing Pass
- [ ] Room descriptions: vivid, sensory, 50–150 words each
- [ ] Item descriptions: unique, evocative, 1–3 sentences
- [ ] NPC descriptions: appearance, demeanor, memorable details
- [ ] **NO** placeholder text ("a generic sword"); every item has character

**Quality bar:** Descriptions should feel like a novel excerpt, not a game manual.

#### P4.2 — Thematic Consistency
- [ ] **Steampunk City:** brass, copper, steam, gears, industry
- [ ] **Whisperwood:** mist, ancient stones, wildlife, growth, mystery
- [ ] **Port Veridian:** salt, wood, rope, labor, trade
- [ ] Room exits/connections make geographical sense
- [ ] Items match zone aesthetic (no "steel gears" in forest floor)

#### P4.3 — Lighting & Atmosphere
- [ ] Dark rooms: caves, undercity, some forest trails (light_level = 0)
- [ ] Medium light: forest floor, port docks, academy corridors (light_level = 0.5)
- [ ] Bright rooms: market, smithy, tower peak (light_level = 1)
- [ ] Test navigation: can you see in dark rooms without torches? (flavor challenge)

#### P4.4 — Safe-Rest Zones
- [ ] Mark 5–8 rooms as `safe_rest: true`
- [ ] Thematic: inns, temples, scholar quarters, ranger lodges (not random)
- [ ] Verify players can sleep there; can't in hostile areas

#### P4.5 — Weather Integration (if time)
- [x] Coastal zones: occasionally foggy/stormy — **done via a traveling storm front, not zone climate.** Added `coastal_squall` to `world_content/weather_fronts.yaml` (`path: [port_veridian, coast_road, whisperwood]`, `room_effect: storm_lashed`, autumn/winter): it rolls a per-hour chance, sweeps the coast → river connector → forest, lashes outdoor rooms in each zone, and auto-skips `indoor: true` interiors. This is content on the existing front mechanism — there is still no per-zone climate model (see Blocked Items §3).
- [ ] Forest: rainy/misty common — **not changed; nothing to do at content level.** Weather is a single *global* `WorldClock.weather` value; there is no per-zone climate hook to make Whisperwood reliably rainier than Cogsworth. The `coastal_squall` front above gives the forest *occasional* coastal storms, but "misty/rainy common" would require new Tier 2 zone-climate code (Blocked Items §3), which is out of scope.
- [ ] City: clear/overcast (not weather-sensitive underground) — **not changed; same reason.** No zone-specific content is possible for this without a climate model; Cogsworth already benefits from ambient global weather being suppressed in its `indoor: true` sewers/interiors (Room.indoor, P4.6). Left unchecked deliberately — nothing zone-specific actually changed here.
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
**Status:** ⚠️ Partial support
**Current:** NPCs can be placed in rooms; movement can be scheduled.
**Missing:** Data-driven respawn templates (e.g., "Patrol Guard appears in random sewer rooms every 10 minutes").
**Engine work needed:** Spawn template table + scheduler integration (Tier 2 feature, backlog)
**Workaround:** Hard-code specific NPC instances in rooms; use scheduler for patrolling only.
**Plan:** Phase 1–3 uses static NPCs; consider spawn templates in Phase 4 if desired.

### 3. **Climate/Zone Weather Binding**
**Status:** ⚠️ Partial support — two *content-level* hooks now exercised for the new zones (v0.80.0); true zone climate still unbuilt.
**Current:** Global weather exists (single `WorldClock.weather`). Two data-driven hooks give *content-level* zone flavor without a real climate model:
- **Traveling storm fronts** (`world_content/weather_fronts.yaml`): a front declares an ordered `path:` of `area_id`s and rolls a per-hour chance; on a hit it applies `room_effect: storm_lashed` and narrates zone-by-zone, skipping `indoor: true` rooms. Fronts now cover the new zones — `coastal_squall` runs `port_veridian → coast_road → whisperwood` (in addition to the town/wilderness `spring_squall`).
- **Weather-blockable transit** (`transit:` in `world_content/world.yaml`): `TransitLine.weather_sensitive` + `blocking_weather` grounds a line when global weather matches. First live use: the **Harbor Ferry** grounds on `thunderstorm`/`heavy_rain`/`blizzard`.

**What this pass covered (v0.80.0):** a real per-zone storm-front *path* through the coastal/forest zones + one weather-blockable transit line. Both are *content on existing engine mechanisms* — no new engine code.
**Still genuinely missing (out of scope):** true zone-level climate — e.g. "Whisperwood is *always* rainier than Cogsworth", "the desert runs hot/dry". Global weather remains a single value; a front is a transient traveling event, **not** a standing per-zone bias.
**Engine work needed:** Zone climate data + conditional/biased weather transitions (a new **Tier 2** feature — do NOT build under a content task).
**Workaround:** Use traveling fronts for transient zone storms and `weather_sensitive` transit for grounding; accept global baseline weather otherwise.

### 4. **Ambient / Timed Room Events**
**Status:** ❌ Not supported
**What it is:** Rooms with flavor text that changes over time ("morning light slants through windows" → "afternoon sun high" → "sunset shadows lengthen").
**Engine work needed:** New Tier 2 feature: timed-effect scheduler + narration injection.
**Current workaround:** Static descriptions; player exploration discovers detail.
**Plan:** Out of scope for v0.1; candidate for future "world flavor" sprint.

### 5. **NPC Reputation / Faction Standing**
**Status:** ⚠️ Engine has reputation, but not NPC-specific.
**Current:** Player reputation per faction exists (audit log); NPCs don't have it yet.
**Engine work needed:** NPC faction data + standing checks (Tier 1 extension)
**Workaround:** Simple quest chains instead (NPC remembers if you did their quest).
**Plan:** Phase 3 quests use "complete this quest to progress" rather than standing thresholds.

### 6. **Day-Night Cycle NPC Behavior**
**Status:** ❌ Not supported
**What it is:** NPCs work during day, sleep at night; shops close at evening.
**Engine work needed:** NPC schedule model + time-based behavior (Tier 1 extension, Roadmap future)
**Current workaround:** All NPCs available 24/7; no time-based variant behavior.
**Plan:** Out of scope; noted for future flavor enhancement.

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
- [x] 100+ unique items (weapons, armor, utility, consumables, keys, lore) — 174 items as of v0.83.0 (P2.1 weapons + P2.2 armor + P2.3 utility/crafting + P2.4 consumables); further Phase 2 batches (trait-wearables/keys) continue to grow it
- [ ] 15+ NPCs with dialogue and quests
- [ ] 5+ locked doors requiring keys (puzzle component)
- [ ] Dark areas requiring light sources (caves, sewers)
- [ ] At least 8 safe-rest zones
- [ ] Thematic consistency: no "sci-fi" items in fantasy forest, etc.
- [ ] All items, NPCs, and rooms described in prose (not placeholder text)
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
- **Shop system:** `src/lorecraft/features/shop/` (vendor management, inventory, pricing)
- **Quest system:** `src/lorecraft/features/quest/` (quest definition, objectives, rewards)
- **Lighting:** `light_level` in rooms; items with light properties (e.g., `emits_light: true`)

---

*World branch created 2026-07-09. Roadmap document is the source of truth for world-building priorities and status.*
