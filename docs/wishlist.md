# Lorecraft — Wishlist & Idea Backlog

> **Purpose:** A menu of gaps, unimplemented ideas, and "wouldn't-it-be-cool" features
> gathered from planning sessions comparing Lorecraft against modern MUD engines (Evennia,
> Ranvier, CoffeeMud, FluffOS, tbaMUD, Aardwolf, Materia Magica, BatMUD, Discworld).
>
> **This is not a roadmap.** Nothing here is committed. The roadmap
> ([`roadmap.md`](roadmap.md)) is the authoritative work queue; items graduate _into_ it
> only after they're chosen and scoped. This file is where ideas live before that.
>
> **Codebase sync (2026-07-07):** this file was audited against the code. Several bullets
> that pre-dated their implementation now carry inline **Shipped / Partly shipped** notes —
> notably *timed/scheduled quests* (Sprint 30.2), *attributes*, *item quality/rarity*,
> *durability*, *bound items*, *NPC memory*, *shop restock*, the *soft-cap primitive*, and
> the *guided report flow* (Sprint 33.1). Items without such a note are still genuinely open.

## Engine architecture & design philosophy

Based on analysis of modern MUD engines (Evennia, Ranvier, CoffeeMud, FluffOS, Discworld),
the strongest pattern is **tiny core + everything else is a plugin**. The engine provides
infrastructure (entities, persistence, networking, events, permissions, scheduling, world
builder tools); gameplay is layered on top as optional modules. This enables:

- **AI-friendly content** — all assets are human-readable YAML/structured data, version-controlled, isolated so coding agents can safely modify content.
- **Independent evolution** — engine updates don't require content rewrites; new gameplay features don't change core code.
- **Reusability across worlds** — the same engine can run fantasy, sci-fi, teaching, or experimental settings without forking.

Key architectural principles:

- **Data-driven everything** — world content lives in YAML/JSON/DSLs, not hardcoded logic.
- **Event-driven subsystems** — combat, quests, weather, economy publish events; systems subscribe without direct coupling.
- **Entity/component model** — instead of deep inheritance (Character → NPC → Merchant → Guard), use flat entities with composable components (Position, Health, Inventory, AI, Skills, Merchant, etc.). Avoids massive class hierarchies.
- **Semantically structured output** — text output tags each line with type (room-text, combat, quest, tell, system, warning) so clients (terminal, browser, GUI, screen-reader) can route/filter/speak separately.
- **Protocol abstraction** — game logic is transport-agnostic; telnet, WebSocket, web UI, or future clients all consume the same event stream via capability negotiation.

Not all of these are implemented yet; the design intent is to apply them as subsystems mature.

---

## Guiding stance: borrow selectively, don't clone

Lorecraft is **not** trying to be a standard MUD. The classic MUD feature set (guilds,
clans, 240-level grinds, permadeath economies) is a menu, not a spec. We take the systems
that fit Lorecraft's feel — a living, narrative, browser-based world — and leave the rest.
Some genre-standard features are **explicit non-goals** unless a real reason appears.

### Design pillars (2026-07-03)

The experience Lorecraft is reaching for, in priority order:

1. **Exploration** — discovering places, secrets, and lore is a first-class reward, not
   filler between fights.
2. **Trading** — a living economy where knowing _where_ to buy and sell matters (pairs
   directly with the transit systems below).
3. **Questing** — branching, consequence-bearing stories, not fetch-quest checklists.
4. **Puzzle-solving** — environmental and lore puzzles, item combination, investigation.

**Combat is a supporting system, not the centerpiece.** It's welcome, but it should be one
of several ways to resolve a situation (alongside stealth, persuasion, bribery, cleverness),
often _avoidable_. Design combat to serve exploration/quests, not the other way around. This
reframes several mechanics below: character stats exist to gate exploration and social play,
not just to compute damage.

Each item below is tagged:

- 💚 **Want** — aligned with Lorecraft's direction; strong candidate for a future sprint.
- 🤔 **Maybe** — interesting, but needs a design decision or player demand first.
- 🚫 **Probably not** — genre-standard but not obviously right for Lorecraft; noted so the
  decision is deliberate, not accidental.

---

## Featured idea: travel & transit systems 💚

**The single most-wanted item from this session.** Materia Magica's getting-around systems —
**ferries, hot-air balloons, rail transit with tickets, and travel animations** — are a
standout example of world-as-experience rather than world-as-grid. This is a great fit for
Lorecraft's narrative, real-time, browser-based feel and doesn't depend on combat or economy.

What it could include:

- **Scheduled vehicles** — a ferry or balloon that departs on a world-clock cadence (built
  naturally on the existing `SchedulerService` + `TIME_ADVANCED` tick). Miss the boat, wait
  for the next one. The vehicle is a moving "room" whose exits change as it travels.
- **Tickets as items** — buy/hold a ticket item; boarding checks for it (reuses the
  existing item + condition system, and later the currency model). Route-specific tickets,
  one-use vs. pass.
- **Travel animation** — timed narrative beats streamed to the feed during transit
  ("The balloon lifts above the rooftops…" → "Clouds thin; the coast comes into view…" →
  arrival). A perfect consumer of the WS push + scheduler primitives already in place.
- **Transit modes** — rail (fixed stops, fast), ferry (water-gated routes), balloon
  (scenic, weather-affected?), maybe a fast-travel/recall for known destinations.
- **Weather interplay** — balloon grounded in a storm; ferry delayed by fog. Ties into the
  existing `clock/weather.py` state machine for emergent texture.

Why it's attractive now: it's **mostly buildable on primitives Lorecraft already has**
(scheduler, world clock, weather, items, conditions, WS push, moving-room concept) and
delivers a lot of world personality without waiting on combat/economy. A minimal first cut
(one scheduled ferry with a ticket check and a 3-beat travel animation) would be a strong,
self-contained sprint and a showcase for the feature-registration pattern.

**Now designed:** see [`transit_systems.md`](transit_systems.md) — multiple data-driven modes
(ferry/rail/balloon/caravan), local vs. express stopping patterns, per-segment speed, minimap
animation, ticket-gating, and weather delays, all driven by the existing scheduler + world clock.

Resolved / remaining design questions:

- Vehicle = a special `Room` (moving-room model) — passengers are its occupants; `board`/
  `disembark` gate entry, no static exits. A lighter virtual-journey variant covers abstract
  fast-travel. _(Resolved in the design doc.)_
- Off-vehicle players _do_ see arrivals/departures and can watch the vehicle cross the minimap.
- Tickets are items; free or quest-pass for now, priced once the [Sprint 28](roadmap.md#sprint-28--trading--economy) economy lands.

---

## World model flexibility 💚 (architectural — long-term planning)

Lorecraft's world is currently **room-based** (rooms with exits). Future expansion can support
multiple coordinate and topology systems on the same engine without major rewrites:

**Coordinate-aware worlds:**
- **Hex grid / wilderness** — coordinate regions with distance/terrain-based travel time.
- **2.5D / Z-levels** — vertical stacking (caves below, balconies above, sky).
- **Open world / seamless zones** — exits don't gate movement; walking off one "room" flows into
  the next procedurally or via a loaded adjacent tile.

**Alternative topologies:**
- **Ships / vehicles** — rooms that move (especially useful for the transit systems above).
- **Buildings / interior spaces** — logical room trees (a house contains 3 rooms; exiting all
  rooms re-enters the main world).
- **Instanced dungeons** — per-party or per-player copy of a zone template with independent
  state (boss defeated? treasure taken?).
- **Procedurally generated regions** — seeded randomization so a region generates consistently
  but differently per seed/season.

Today's room model is not a limitation — it's a starting point. The entity/component
architecture means a new location type (hex tile, building, instance) is a component set, not
a new class hierarchy. Design any new topology as a **component bundle** (coordinates + terrain,
or container+interior-rooms, or instance+template-ref) so the engine stays flexible.

When to act: **Not now.** The current room model serves the narrative/exploration pillars well.
Revisit this design when/if a specific topology (hex wilderness, instanced arenas, building
interiors) becomes a real content need — then implement it as a component set reusing the
existing entity framework. Don't speculatively build all topologies.

---

## Mechanics ideas menu

A deliberately large brainstorm of mechanics that serve the exploration / trade / quest /
puzzle pillars. Not everything here should be built — the point is a rich menu to pick from.
Where possible, each notes what Lorecraft primitive it builds on.

### Inventory & equipment 💚 (foundational — wanted next)

The most-requested near-term system. Needed before wear-slot-dependent content, trading depth,
and most combat.

- **Wear / wield slots** — head, face, neck, shoulders/cloak, torso, back, arms, hands (×2 or
  gloves), fingers (rings ×2), waist/belt, legs, feet, plus wielded main/off-hand and a
  light-source slot. Items declare which slot(s) they occupy (data on the `Item` model);
  `Player` gains an equipment map. `wear`/`remove`/`wield` commands. Equipped items grant
  passive effects (traits, warmth, light, carry capacity, skill bonuses) — **not just combat
  stats**, per the pillars.
- **Encumbrance / carry weight** — items have weight; carrying too much slows travel and
  drains fatigue faster. Makes bags and pack animals meaningful; creates trade-off decisions
  during exploration. Keep it forgiving, not a spreadsheet.
- **Containers / nested inventory** — bags, pouches, backpacks, chests. A container is an item
  that holds items (recursive). Enables organization, weight reduction (a "bag of holding"),
  and puzzle/quest stashes. Pairs with the deferred `open`/container modeling noted in Sprint 2.5.
- **Durability / condition** — items wear out or degrade (weather-exposed gear, torches burn
  down). Drives repair services, trade in consumables, and a light-source survival loop.
  **Shipped (Sprint 22.2):** `Item.max_durability` + the `item_components` durability component.
- **Item quality & rarity tiers** — common → legendary, affecting value and trade demand.
  **Shipped:** `Item.quality` (`common|fine|superior|rare|legendary`); shop prices derive from
  `value * quality` (Sprint 28).
- **Bound vs. tradeable / attunement** — quest items bind to a player; some gear must be
  attuned. Protects quest integrity and shapes the economy. **Bound shipped (Sprint 16):**
  `Item.bound` (soulbound; can't drop/sell/trade). _Attunement not built._
- **Consumables & charges** — potions, food, scrolls, lantern oil, tickets (ties to transit).

### Character condition & survival 🤔 (fatigue / sleep — wanted as ideas)

Light survival texture that rewards planning and makes the world feel physical. Keep it
_flavor and pacing_, not punishing micro-management. Runs naturally on the existing
`SchedulerService` + `TIME_ADVANCED` world-clock tick.

- **Fatigue / stamina** — depletes with travel distance, encumbrance, strenuous actions;
  restored by resting and sleeping. Low fatigue penalizes perception/skill checks (you miss
  hidden exits when exhausted) — directly serves exploration. `rest`/`sleep`/`camp` commands.
- **Sleep** — players need periodic sleep; sleeping advances time, restores fatigue, and is a
  natural **content-delivery hook** (dreams as lore/vision/quest nudges). Safe sleep (inns,
  camps) vs. unsafe sleep (wilderness — interruptions, risk). Ties to day/night.
- **Hunger / thirst** — _optional, lightweight._ Rations as trade goods and a reason to visit
  taverns; avoid making it a chore. Could be a per-world toggle.
- **Wounds / afflictions as puzzle gates** — a sprained ankle slows travel, snow-blindness
  blocks a vista, poison needs an antidote. Afflictions as _content_, not just HP loss —
  creates quests (find the healer, brew the cure) rather than annoyance.
- **Rested / well-fed bonuses** — positive modifiers for good self-care, framed as carrots
  rather than sticks for neglect.
- **Warmth / exposure** — weather + terrain + equipped clothing interact (a cloak matters in a
  blizzard). Builds on `clock/weather.py`; gives clothing non-combat purpose.
- **Light & darkness** — dark rooms need a light source (torch/lantern with fuel) or you can't
  see exits/items. A classic exploration mechanic and a gentle resource loop.

### Traits, skills & character identity 🤔 (traits — wanted as ideas)

Defines _who_ a character is in ways that gate exploration and social play, not just combat.
Best implemented as pluggable modifiers via the existing registry pattern rather than hardcoded.

- **Traits** — persistent passive modifiers chosen at creation or earned: _keen-eyed_ (better
  hidden-exit detection), _night-owl_ (no penalty in darkness), _silver-tongued_ (better
  prices/persuasion), _claustrophobic_ (penalties underground), _cartographer_ (auto-maps),
  _iron-stomach_, _light-sleeper_. Traits can be boons and banes for character texture.
- **Backgrounds / origins** — a starting package of traits, skills, starting gear, and known
  lore. Gives replayability and shapes early dialogue ("Ah, a former sailor…").
- **Skills** — perception, lockpicking, bartering, cartography, survival, lore/appraisal,
  stealth, persuasion, swimming/climbing. Skills gate exploration (find secrets, cross terrain)
  and social/trade outcomes far more than combat. Improve through _use_ rather than XP grind.
- **Attributes** — a light STR/DEX/INT-style spread, but explicitly framed for non-combat use
  (STR = carry weight, INT = lore checks, etc.). Keep minimal; resist stat bloat.
  **Shipped (Sprint 19/24):** `PlayerStats` carries `strength`/`agility`/`vitality`/`intellect`/
  `presence`/`fortitude`; skills key off them (e.g. bartering→presence, cartography→intellect).
- **Reputation / standing** — per-NPC and per-faction opinion that unlocks dialogue, prices,
  quests, and access. The social spine of a quest-driven world. NPCs _remember_ you.
- **Knowledge / lore flags** — "known facts" a player accumulates that unlock dialogue options
  and puzzle solutions (already partly expressible via the flag system). Turns exploration into
  a knowledge-progression system parallel to leveling.
- **Languages** — some NPCs/signs/books require a language; learning one is a quest reward.

### Exploration depth 💚 (core pillar)

- **Discovery rewards** — finding a new room, landmark, or vista grants a tangible reward
  (lore, a knowledge flag, a small progression tick). Exploration _is_ progression. Builds on
  the existing minimap fog-of-war.
- **Hidden exits & secret rooms** — perception/search-gated passages; `search` command;
  trait/skill and fatigue interactions. Rewards attentive play.
- **Cartography / player mapping** — the map fills in as you explore; a _cartographer_ trait or
  bought maps reveal more; sellable/tradeable maps as goods (ties to trade).
- **Terrain & travel** — room/exit terrain types (road, forest, mountain, water) affect travel
  time, fatigue cost, and required skills/gear (climbing, swimming). Makes geography meaningful
  and pairs with transit (roads are fast, wilderness is slow).
- **Environmental storytelling** — rooms with examinable detail, readable objects (books,
  inscriptions, signs), layered `examine` targets. Cheap, high-texture content.
- **Journal / auto-log** — the game records discovered places, met NPCs, learned lore, and
  active clues — a living quest/exploration log. Great UI panel candidate.
  **Shipped (Sprint 25.3) minus items** — item discovery tracking promoted to roadmap
  [Sprint 46](roadmap.md#sprint-46--item-discovery-journal) (2026-07-05).

### Trading & economy depth 💚 (core pillar — designed in `trade_economy.md`, roadmap Sprint 28)

Beyond the basic currency→shops→P2P ladder in _Gameplay systems_ below:

- **Regional price differences** — goods cost different amounts in different places; the core
  trade loop is buy-low-here, sell-high-there. **This is the killer pairing with transit
  systems** — the ferry/rail network _is_ the trade network. Exploration feeds trade feeds
  exploration.
- **Bartering skill & reputation pricing** — prices flex with skill, standing, and haggling.
  **Partly shipped:** the `bartering` skill + `reputation` feature exist; deeper
  standing/haggle price-flex is where the remaining work is.
- **Supply & demand / stock** — shops have finite stock that restocks on the world clock;
  flooding a market drops prices. Emergent, driven by existing scheduler.
  **Shipped (Sprint 28.2):** finite stock + clock-driven restock (`economy/restock.py`).
- **Caravans / trade routes / commissions** — deliver goods between towns for profit; escort or
  investigate when they go missing (quest hooks). A whole quest genre falls out of this.
- **Rare & seasonal goods** — availability tied to season/weather/events, rewarding travel and
  timing.

### Robbers & highway risk 💚 (ties money, travel & death)

NPC (later PvP) threats that make _carrying_ wealth risky — the stick that makes banks and safe
transit worth using. Shares its whole core with [`death_resurrection.md`](death_resurrection.md):
**carried is at risk, banked is safe.**

- **Highwaymen / footpads** — hostile NPCs on wilderness roads or in shady districts who can
  **rob without killing**: a successful robbery skims a slice of carried `coins` (and maybe a
  carried item); banked money and equipped/bound gear are untouched. Lower stakes than death,
  same lesson.
- **Avoidance-first, per the pillars** — talk your way out (persuasion), bribe them, sneak past
  (stealth), or fight ([`combat_system.md`](combat_system.md)) — robbery is an _encounter_, not
  an unavoidable tax. Reputation/standing ([Sprint 24](roadmap.md#sprint-24--traits--skills)) can matter (a known friend of the guard,
  or of the thieves).
- **Risk-tiered geography** — safe roads vs. dangerous shortcuts; the fast route may be the
  risky one, trading time against safety (pairs with transit + the fatigue/condition mechanic).
- **Threat scales with what you carry** — hauling a fat purse of trade profit between towns is
  exactly when you're a target, which is exactly when you _should_ have banked or split it.
  Makes the trade loop a real decision, not a spreadsheet.
- **Later:** player-robber roles, bounties, guard NPCs, fences for stolen goods — all deferred;
  v1 is just "NPCs can rob carried wealth, banks/transit mitigate it."

Design intent noted 2026-07-03 (product owner). No dedicated design doc yet; the money-at-risk
mechanics are specified in [`death_resurrection.md`](death_resurrection.md) §8. Sprint TBD —
naturally lands after banks ([Sprint 28](roadmap.md#sprint-28--trading--economy)) and combat ([Sprint 31](roadmap.md#sprint-31--combat-core-services-supporting-system)).

### Quests & puzzles 💚 (core pillar)

- **Branching quests with consequences** — choices that change world state, NPC standing, and
  later options — not linear fetch chains. The current stage/flag system is a start; extend
  toward branch conditions and consequence side-effects (registry-friendly).
- **Environmental & mechanism puzzles** — levers, pressure plates, sequenced switches, doors
  keyed to items or knowledge. Needs the deferred item/room _state_ modeling (Sprint 2.5 note).
- **Item-combination puzzles** — combine/apply items to solve problems (a craft-_like_ mechanic
  framed as puzzle-solving rather than production grind).
- **Riddles & lore puzzles** — answers gated by knowledge flags gathered through exploration;
  investigation quests where you assemble clues in the journal.
- **NPC memory & relationship state** — NPCs recall past interactions and react; unlocks
  dialogue and quests. Overlaps with reputation above; the backbone of a story-driven world.
  **Shipped:** the `npc_memory` feature — per-(player, NPC) memory keys backing the
  `npc_remembers` dialogue/quest condition + the `remember` dialogue side effect.
- **Timed / scheduled quests** — deadlines and world-clock-driven events (the festival is
  tonight; the tide turns at dusk). Runs on the existing scheduler + clock.
  **✅ Shipped (Sprint 30.2):** `QuestTimerService` sweeps active quest progress on
  `TIME_ADVANCED`; a stage's `timeout_ticks`/`on_timeout` advances to a fallback stage or
  fails the quest, data-driven from the quest YAML. World-clock *events* (festivals) are
  covered by scheduled scavenger hunts (Sprint 48) + celestial/weather events (Sprint 44/54).
- **Non-combat resolutions** — quests solvable by stealth, persuasion, bribery, or cleverness,
  not only violence — central to the "combat is optional" pillar.

### Combat, reframed as a supporting system 🤔

Combat is **set aside from the active roadmap** (2026-07-05 — it kept forcing sprint-renumbering
churn and isn't worth the hassle right now) but remains **deliberately not the centerpiece** when
it returns:

- **Avoidance as first-class** — stealth, persuasion, bribery, and clever item use should
  resolve most encounters without a fight. Combat is a fallback, not the default.
- **Non-lethal outcomes** — subdue, intimidate, drive off, or flee; death is one outcome among
  several, and often not the interesting one.
- **Encounters serve stories** — fights exist to raise stakes in quests/exploration, not as a
  grind loop for XP. No "kill 10 rats." See the death-penalty decision (lean soft).

#### Set-aside sprint specs (were roadmap Sprints 61–64, moved here 2026-07-05)

Ready-to-restore, roadmap-grade specs — when combat/PvP graduates back onto the roadmap these
become sprints again (renumber to whatever's next). Design docs:
[`combat_system.md`](combat_system.md), [`death_resurrection.md`](death_resurrection.md).

**1. Combat core services (supporting system).** Server-side resolution, no commands/UI yet;
first real consumer of the feature-registration pattern (roadmap 10.4), reading equipment-derived
stats. Deliberately below trade/transit/quests — combat serves stories, it isn't the loop.
- `services/combat.py` — sessions, ticks, damage.
- Death & resurrection ([`death_resurrection.md`](death_resurrection.md)): resurrect at
  `respawn_room_id`, lose a % of *carried* coins + drop unequipped loot into a corpse container
  (banked/equipped/bound safe); corpse retrieval + decay; weakened debuff.
- `npc/combat_ai.py` — behavior modes from YAML.

**2. Combat commands + UI (avoidance-first).** Combat as one resolution among several —
stealth/persuasion/bribery/flee are first-class alternatives; non-lethal outcomes supported.
- `commands/combat.py` — `attack`, `flee`; non-lethal outcomes (subdue/intimidate/drive-off);
  complete condition eval (`NPC_PRESENT`, `HAS_COMBAT_TARGET`).
- Combat UI in HTMX feed + status panel.

**3. Combat testing.** Integration + browser tests for the combat loop and avoidance/non-lethal
paths.

**4. PvP consent.** Consent-based, opt-in PvP reusing the combat system; soft by default;
challenge/accept. (The multiplayer PvP-consent *simulation tests* moved here from roadmap Sprint 65
along with the rest of that sprint — see *Multiplayer sim-test coverage* under World-building &
tooling.)

### Seeded from MUD patch notes & client comparison (2026-07-03)

A batch of ideas mined from another MUD's patch notes (Alyria/Materia-Magica-style) and
Aardwolf's help system + Fractals-of-the-Weave notes. **De-narrativized on purpose** — we keep
the mechanic/primitive, not the lore. Grouped provisionally here ("keep all for now"); some will
later graduate into the themed subsections above or get pruned.

#### Player settings, accessibility & client UX 💚

Classic clients expose a big `set` menu (`set unformatted-text`, `set vitals-percent`,
clickable-links, `page_length`, AFK/away). The transferable idea is a **per-account preferences
layer**, persisted on the account and read by the render layer.

- ~~**Player Creation** - Character name example is "Ashen Wanderer" but the valid player names
  are "3-30 characters: letters, numbers, - or \_ only", so this example is wrong. Also, we
  do not validate the entered name and reject it immediately (input should turn red).~~
  **Addressed (v0.31.0):** create form uses the valid example `Ashen_Wanderer`, a
  `pattern`-based live validity check (border turns red/green as you type), and a
  server-side backstop.
- ~~**Player Creation** - We should prompt for a password twice and validate that they meet
  password complexity requirements and that they match. Complexity requirements should be
  configuration with defaults. min_length (8), max_length(32), mixed_case: true,
  require_symbol: false, require_number: true~~
  **Addressed (v0.31.0):** create form now has a confirm-password field with live match
  feedback and a per-requirement checklist; the policy is enforced server-side and is
  configurable via `LORECRAFT_PASSWORD_*` (defaults exactly as listed —
  `min_length=8, max_length=32, mixed_case=true, require_symbol=false, require_number=true`).
  See `PasswordPolicy` in `webui/player/password_policy.py`.
- **Preferences system** — display density, feed verbosity, panel visibility, timestamp format,
  reduced-motion (transit/map animation off), colourblind-safe palette. One settings blob, one
  place rendering reads it.
- **Accessibility mode** — an "unformatted / high-contrast / screen-reader-friendly" mode. A
  browser client can do this _better_ than a terminal MUD (semantic HTML, ARIA, real font
  scaling) — a genuine differentiator, and far cheaper to bake in early than to retrofit.
- **Examine surfaces affordances + live state** — `look`/`examine` shows _available verbs_
  ("you can: read, take, light") and _live per-instance state_ (charges, cooldown, "requires a
  key"). Builds on [Sprint 22](roadmap.md#sprint-22--standard-item-components--definition-fields) `ItemInstance` state.
- **Clickable entity affordances** — items/NPCs/exits in the feed are clickable → examine/act.
  Browser-native; terminal clients bolt this on with plugins, we get it for free.
- **Contextual hints 🤔** — gentle, situation-aware nudges beyond the context-aware `help`
  fallback: an idle-in-a-puzzle-room hint, a "you could `search` here" whisper in
  perception-worthy rooms, a first-time-verb tip. Needs a design pass first (trigger rules,
  frequency caps, and an off switch in the preferences blob) so it never becomes nagging. From
  the 2026-07-03 planning list; parked here 2026-07-05 pending that design.

#### More exploration & world-state ideas

- **Collectible "marks" / attunements 💚** — named passive badges earned by _discovering_ things
  ("Mark of Groundwater — go explore"): a progression track parallel to leveling, fed by
  exploration not combat. Some cosmetic/lore, some small mechanical boons (soft-capped, below).
  Builds on flags + trait registry ([Sprint 24](roadmap.md#sprint-24--traits--skills)). Pillar #1.
- **Celestial cycles — moons & tides 💚** — the clock already tracks time/season/weather; add
  lunar phase(s) and tides as world state. Gates content: moon-keyed doors/rituals (puzzles),
  tides that shift a ferry schedule or reveal a causeway (transit + exploration), night-only
  encounters. Small extension, three-pillar reach. Builds on `clock/weather.py` + scheduler.
- **World-placed shrines / altars 🤔** — discoverable stations offering a set of _mutually
  exclusive_ boons, one active per station, bought with a token currency; multiple stations
  stack. An exploration reward + light respec-able customization + currency sink in one. The
  mutex-per-station rule keeps it from becoming a flat power-stack.
- **Timed room effects / auras 💚 (engine primitive)** — apply an effect to a _room_ for a
  duration with a cooldown, scheduler-driven (seeded by "germinate is now a 1-hour room effect").
  A general tool: puzzle timers (a plate opens a gate for 30s), weather hazards, lingering zones,
  farming growth. Worth naming as a primitive — lots of content wants it. Builds on
  `SchedulerService` + `TIME_ADVANCED`.
  **→ Promoted to roadmap [Sprint 39](roadmap_completed.md)**
  (2026-07-05, design-first): decided to **reuse the Sprint 19 `ActiveEffect`/`EffectService`
  timed-effect primitive** (already generic over `entity_type` — a room is just
  `entity_type="room"`) rather than a new `RoomEffect` model or a component carrier.

#### Systems & balance design notes

- **Soft caps / diminishing returns 💚 (principle, not a feature)** — "no 100% resistance",
  "+damage tiered drop-off". Bake into the trait/skill/effect maths _from [Sprint 24](roadmap.md#sprint-24--traits--skills)_: modifiers
  stack with diminishing returns and hard ceilings so nothing goes degenerate. A shared
  `apply_modifier`/soft-cap helper. Cheap now, painful to walk back later.
  **Primitive shipped:** the §3.5 modifier resolver (`engine/game/modifiers.py`) supports
  `clamp_min`/`clamp_max` (hard ceilings/floors); content just isn't broadly using them yet.
- **Effect exclusivity groups 🤔** — affects/traits/marks can declare a mutex group so opposed or
  same-family effects don't stack ("Courage and Fear are mutex"). Small but important trait detail.
- **Multiple / alternate currencies 🤔** — event tokens, faction scrip alongside base gold. Design
  implication for **[Sprint 28](roadmap.md#sprint-28--trading--economy)**: model currency as a _keyed quantity map_ (`{coins, festival_tokens,
…}`), not a single int — near-free now, expensive to retrofit.
- **Item sockets / augments + lifespans 🤔** — heavily stripped from Aardwolf's "relics": items can
  hold per-instance sub-modifiers (sockets), and some items have a lifespan and transform on expiry.
  Natural extension of `ItemInstance.state` (Sprint 22.2); the _socket_ kernel is the keeper — resist
  over-building the rest.
- **Variable-cost / scalable commands 🤔** — a command takes a numeric arg that scales its cost _and_
  effect (`brew 3` = spend 3 reagents for a bigger result). Expressive for any future resource pool.
- **Repeatable / daily objectives 🤔 (with a caveat)** — reset-window design (the noon-vs-midnight
  boundary is a real scheduler UX detail). **Tension:** dailies are the grind loop the pillars reject
  — only pursue as _rotating discovery/trade_ goals ("bring goods from three towns today"), never
  combat treadmills.
- **Categorized, searchable help / codex 💚** — Aardwolf's `HELP CONTENTS` / `CONTENTS <category>` /
  `INDEX <letter>` / `HELP <keyword>` is a browsable, indexed knowledge base. Lorecraft's context-aware
  `help` can grow into a searchable **codex panel/modal** (categories + full-text search + clickable
  cross-links), merged with the journal/lore log. Browser-native.
  **Partly shipped (Sprint 36):** help topics with categories + `help topics [search]` filtering
  already exist; the remaining work is the browser **codex panel/modal** merged with the journal.
- **Player-facing world graphs / stats 🤔** — Alteraeon-style `graph` command: aggregate world
  statistics players can browse (hourly/daily player load, economy/gold offsets, alignment
  distribution), available both in-game _and_ on the web. Distinct from the admin analytics
  ([Sprint 13](roadmap.md#sprint-13--observability--ci-quality-gates-) latency/instrumentation) — this is the _public_ "what is the whole world doing"
  view. Reuses the [Sprint 13](roadmap.md#sprint-13--observability--ci-quality-gates-) metric queries + the `dataviz` skill for rendering; a natural
  browser panel/page. Light community-texture feature, no gameplay dependency.
- **Instanced minigames / scenarios 🤔** — themed self-contained challenge areas (Fractals of the
  Weave: Unseelie Court, caravan defense) that repop on a timer (every 60h, _unannounced_ — players
  learn the rhythm) and restore vitals at checkpoints. Good fit for the feature-registration pattern +
  scheduler; the caravan-defense one pairs with the trade-route idea. Defer, but a strong "special
  content" mould. The simplest *non-instanced* slice — **scavenger hunt events** — was promoted to
  roadmap [Sprint 48](roadmap_completed.md) (2026-07-05).

#### Smaller design details (one line each)

- **Always-allowed commands under status effects** — communication/social verbs still work while
  stunned/paralyzed/"casting". Ties to the command-lifecycle + context-aware availability.
- **Conditional item possession** — items that vanish when the holder stops meeting their requirements.
  Extends bound/attunement.
- **Room/entity flags constrain NPC behaviour** — a `SAFE` flag NPCs won't teleport/wander into;
  directly supports the safe-vs-dangerous geography behind robbers.
- **NPC perception overrides stealth** — "shopkeepers always see shoppers": rules for where stealth
  _shouldn't_ apply (commerce, key NPCs).
- **Feature flags for staged content** — ship-dark content that unlocks on a flag/date ("finished but
  not released until X"). Minor infra.

---

## Gameplay systems

### Combat 💚 (set aside from the roadmap — 2026-07-05)

Set aside to this doc 2026-07-05 (specs above under *Combat, reframed*; moved down from the original 18–20 in the 2026-07-03 pillar re-sequence —
combat is a supporting system, not the centerpiece). **NPC combat first, PvP later** — simpler
state machine, lets death/respawn mechanics settle before adding player-vs-player. First real
consumer of the feature-registration pattern.

**Death penalty: resolved** — see [`death_resurrection.md`](death_resurrection.md) (resurrect,
lose some carried coins/loot; banked and equipped/bound items are safe).

### Trading & currency 💚 (on the roadmap)

[Sprint 28](roadmap.md#sprint-28--trading--economy). Designed in [`trade_economy.md`](trade_economy.md): currency (carried `coins` +
`BankAccount`) → NPC shops → regional pricing → banks → player-to-player trade.
_Deferred:_ auctions, dynamic global market — until there's real trading volume.

### PvP 🤔 (set aside from the roadmap — 2026-07-05)

Consent-based (challenge/accept) reusing the combat system. **Design choice pending:** soft
opt-in PvP (most modern MUDs, Aardwolf's "99% harmless") vs. anything more punishing. Lean
soft unless Lorecraft wants a darker RP tone.

### Leveling & progression 🤔

Player model has an unused `level` field. No XP or skills yet. **Deliberately deferred** —
design _after_ combat is real and there's player feedback. If pursued: model XP→level
separately from combat stats. Multi-class (Materia Magica's parallel tracks) only after
single-class is solid, if ever.

### Crafting 🤔

No system today. Defer until players ask. If built: start with simple `A + B → C` recipes;
avoid deep material trees; keep it independent from combat-loot progression so it's optional.

---

## Getting around & world texture

### Travel & transit systems 💚

See **Featured idea** above. Top candidate.

### Weather-driven world events 🤔

The weather/season state machine exists but mostly flavors descriptions. Could drive real
mechanics: storms delaying transit, seasonal NPC behavior, weather-gated content. Low-cost
texture on top of an existing subsystem.

### Fast travel / recall 🤔

A "recall" or "known destinations" fast-travel could pair naturally with the transit theme
(e.g., a rail pass unlocks quick hops between visited stations). Fits the travel-animation
idea.

---

## Client UI, layout & presentation 💚 (from Aardwolf/MUSHclient screenshots, 2026-07-03)

Three classic MUSHclient/Aardwolf multi-pane layouts were reviewed for pane/layout/style ideas.
Lorecraft is browser-based, so most of these map onto HTMX panels it already has (room, inventory,
minimap, players-online, quest tracker, world-clock bar) — the value is in _what deserves its own
pane_ and _how information is separated_.

**Structured output bus** (accessibility & client flexibility):

The highest-impact insight from comparing Aardwolf, Materia, and Alter Aeon is that each line of
output should be **tagged with semantic type** (room-text, combat, quest-update, tell, channel-chat,
system-message, warning, hint). This enables:

- **Screen readers** — speak only the important lines (warnings/tells), skip flavor.
- **GUI clients** — route combat to a combat pane, tells to a social pane, quests to a tracker.
- **Mobile clients** — collapse verbose room text, expand combat details.
- **Bots & tools** — parse structured JSON instead of regex-ing plain text.
- **Player preferences** — "mute combat spam", "speak warnings aloud", "hide shop spam".

This is not a new protocol; it's **metadata on the existing text stream**. Each event from the
command dispatcher gets a `(output_type, text, json_payload)` tuple. The browser renders `text`
with CSS class; telnet clients ignore the type; GUI clients use it for routing.

Design this early (in the command dispatcher or event layer) rather than retrofitting later.
No new commands needed — it's invisible infrastructure that clients can optionally consume.

**Protocol abstraction & capability negotiation** (future-proofing):

Keep the game logic completely separate from transport. Lorecraft already uses telnet (text)
and WebSocket (JSON) — future clients (mobile app, Discord bot, REST API) should all consume
the same internal event stream. Achieve this via:

- **Capability registry** — on connect, client declares what it can handle (text, JSON, colors, triggers, GMCP, etc.).
- **Transport-agnostic events** — the engine publishes events; adapters translate to the client's capability.
- **Negotiated OOB data** — clients that support it (Mudlet, CMUD, MUSHclient) receive structured data (GMCP-style) alongside text.

Example: a telnet client says "I support plain text + GMCP". It receives `(text, gmcp_json)` tuples; it renders text, parses the JSON for status bars / vitals. A browser client says "I support JSON + semantic types"; it gets structured output with type tags and JSON payloads. One engine, many clients.

**When to act:** Don't implement now. But keep the transport layer in a separate module so
that when a second client type (mobile, Discordbot, whatever) arrives, it's a new adapter, not
engine changes.

Patterns worth stealing:

- **Separate the communication log from the narrative feed 💚** — every screenshot devotes a whole
  pane to channel/social chatter (Friend/Newbie/Helper/Auction), _distinct_ from the main
  room/action feed. **The single biggest takeaway:** chat should never scroll your room description
  or quest/combat output out of view. Split "world/narrative feed" from "social/channel feed" into
  two panes (or tabs).
- **Persistent stats & vitals panel 💚** — attributes + vitals (HP/mana/moves) + progression
  (XP-to-level, gold, quest/trivia points) always visible, never in the scroll. Once traits/skills
  exist ([Sprint 24](roadmap.md#sprint-24--traits--skills)), the _identity_ numbers live here, not in the feed.
- **Bar gauges alongside numbers 💚** — HP/mana/moves/"TNL"/enemy as coloured progress bars _and_ raw
  numbers. Cheap, high-readability; a browser does this beautifully. Reserve an **enemy/target bar**
  slot for when combat exists.
- **Two map zoom levels 🤔** — a _local_ minimap (immediate rooms + exits + coords) and a _zoomed-out
  region/area map_ (tiled grid, colour-coded rooms) shown together. Lorecraft has one fog-of-war
  minimap; the region view pairs with the planned full-screen map modal ([Sprint 26](roadmap.md#sprint-26--map--mobile-ui)) + cartography
  ([Sprint 25](roadmap.md#sprint-25--exploration-depth)) — consider local-inline + region-modal rather than two always-on maps (screen budget).
- **Colour-coded, prefixed channels 💚** — each channel has a consistent colour + bracket tag
  (`(Friend)`, `[Newbie]`, `Auction:`) so the eye filters instantly. Cheap semantic styling in the
  browser; pairs with the accessibility/palette preference above. **→ Promoted:** colored/prefixed
  tags **and per-channel mute** are roadmap
  [Sprint 45.3](roadmap_completed.md)
  (2026-07-05).
- **Structured room header 💚** — room name + exits + "who/what is here" as a consistent styled header
  before prose. Lorecraft's room panel already does much of this; keep exits and occupant list
  _structured and clickable_, not buried in text.
- **Inline prompt line with vitals 🤔** — terminal clients repeat `<hp/mana/moves …>` each prompt. The
  browser equivalent is the persistent status bar (already have the world-clock bar) — no need to
  repeat inline, but the _idea_ (vitals always one glance away) is the point.

Style notes: dark theme, high-contrast semantic colours, monospace for map/exits, generous use of
colour to encode _type_ (channel, NPC, exit, item, quest) — all of which Lorecraft can do more
accessibly than a terminal via real CSS/ARIA. Feeds directly into **Player settings & accessibility**
above (palette, reduced-motion, unformatted mode).

**Layout budget note:** the screenshots pack 5–6 panes because desktop MUSHclient has the room.
Lorecraft's responsive/mobile goal (Sprint 26.2) means panes must collapse into tabs on small screens
— so decide a _priority order_ (feed > vitals > map > social > inventory > quests) for what stays
visible vs. what tabs away.

---

## World-building & tooling

### In-game builder commands (OLC-style) 🤔

SMAUG's `redit`/`medit`/`oedit` let builders edit rooms/mobs/objects live in-game. Lorecraft
has form-based **web** editors + YAML import/export instead, which works. In-game `/redit`-style
commands would be more immersive for builders but duplicate existing logic. **Enhance the web
editor UX first** (autocomplete, validation); consider in-game editors only if builders ask.

### Scripting layer for builders 🤔 (significant design decision)

Today: builders configure **YAML only**; custom behavior needs backend code (via the pluggable
registries). Established MUDs expose a scripting layer — Evennia (Python modules), Ranvier
(JS behaviors), Aardwolf/SMAUG (embedded Lua / MobProgs).

**Recommendation: hold the decision.** Watch the combat/trading implementations. If YAML starts
getting complex/repetitive to express desired behavior, _that's_ the signal. Options when the
time comes:

- **Python modules** (Evennia model) — full power, VCS-friendly, needs builder coding skill.
- **Embedded Lua** (Aardwolf model) — sandboxed, builder-friendly, in-game editable, needs a
  binding layer.
- **Stay YAML-only** — safest; extend via backend registries as needed.

### Context-attached commands 🤔 (distilled from Evennia cmdsets, 2026-07-03)

**→ Promoted to roadmap [Sprint 55](roadmap_completed.md)**
(2026-07-07): items *and* NPCs declare a `context_commands` map; verbs register into the flat
`CommandRegistry` gated by new `object_present`/`npc_present` conditions (help already hides
out-of-context verbs), firing the existing shared side-effect registry. The design notes below are
the source for that sprint.

Evennia attaches command _sets_ to objects — a Tree carries `climb`/`chop`, a Clock carries
`check time` — so verbs appear only when the relevant object is present or held. That
object-scoped-verb idea is a strong fit for the exploration/puzzle pillars (a `pull` lever that
exists in only one room; a `read` inscription on one item). **Adopt the concept, not the machinery.**

- Lorecraft's parser is already _more_ capable than Evennia's base (semantic roles + entity
  resolution + fuzzy disambiguation + `;`/"it" chaining), so the evolution isn't in parsing — it's
  in _where commands come from_: today `CommandRegistry` is a single flat global set.
- Low-complexity path: keep the flat registry, and let world data (rooms/items/NPCs, or a feature via
  the registration pattern) **contribute context verbs gated by the existing condition registry**
  (`object_present:lever`, `item_in_inventory:sundial`). We already have the symmetric half —
  `Room.disabled_commands` _removes_ verbs; this _adds_ them.
- **Explicitly skip** Evennia's cmdset merge algebra (priorities, Union/Replace/Remove merge types,
  reverse-priority grouped merging) and its `yield`-based command pausing — the first is exactly the
  complexity we distrust; the second is better served by our scheduler + `pending_disambig` (and
  doesn't even survive a reload in Evennia).
- Cheap hygiene win spotted along the way: the registry silently overwrites on key/alias collision —
  a dev-time collision warning would catch accidental clashes (Evennia's hard-won "avoid duplicate
  aliases" lesson).
- Cheap wins for when in-game admin/OOC commands land (backlog `/system`, `@someone`): per-command
  **permission locks** (a simple predicate, not Evennia's lockfunc DSL) and **optional-prefix**
  matching (`@look` == `look` when unambiguous).

### Engine / game-data separation 💚 (architectural — plan for it, don't do it yet)

> **Deep-dive plan (2026-07-05): [`engine_content_separation.md`](engine_content_separation.md)** —
> the content contract, an inventory decision (what's world content vs operational vs engine-dev
> artifact), the scripting-layer constraint, and a phased migration. The note below is the summary.

**Design intent (2026-07-03):** be able to cleanly split the **engine** (Lorecraft the
Python/FastAPI codebase) from **game data** (world YAML, dialogue, quests, and — once it
exists — any bolted-on scripting) so a given world's content can live in **its own repo**,
separate from the engine repo. `architecture.md`'s original project structure already
gestures at this (`world_content/` annotated "Separate git repo (symlinked or submodule)") but
it's never been made real — today `world_content/` ships inside the engine repo and is loaded
by path.

Why this matters _now_, before it's built: it constrains decisions we're making anyway —

- **Scripting layer** (see above) is the sharpest edge. If/when a scripting layer is added
  (Python modules, Lua, or otherwise), that scripting is _game data_ too, not engine code — it
  must live in the content repo and load through the same clean boundary as YAML, or the split
  becomes impossible to retrofit later. Whatever scripting decision gets made, **design its
  loading path as if the content repo is already external.**
- **One engine, many worlds** — a clean split is what lets Lorecraft run more than one setting
  (a fantasy world, a sci-fi world, a teaching sandbox) off one engine codebase, each in its own
  content repo, without forking the engine.
- **Versioning** — engine version and content/world-schema version already exist separately
  (`WorldMeta.schema_version`, `engine_version`) — the plumbing for "engine and content evolve
  independently" is partly there.

What "done" looks like (not scheduled — this is a plan-ahead note, not a sprint):

- A defined **content contract**: what the engine expects a content repo to provide (YAML
  schema, directory layout, any scripting entry points) — versioned and validated
  (`lorecraft.tools.validators` already validates content; extend, don't replace).
- `world_content/` (or its successor) becomes an actual separate repo, pulled in via submodule,
  package, or a configured path — `LORECRAFT_WORLD_YAML_PATH` already externalizes _the path_,
  which is most of the way there.
- The Ashmoore dev world (used by tests) either moves to a `tests/fixtures`-style content
  package or stays as an explicitly-labeled "reference/example content repo" — not the engine's
  only world.

**When to act:** once a scripting layer decision is made (or firmly deferred) and/or a second
world/setting is actually wanted — don't build the split speculatively before either pressure
exists. Revisit this note at that point.

### Multiplayer sim-test coverage 🤔 (trade / transit)

Was roadmap **Sprint 65** (moved here 2026-07-05 — the trade/transit subsystems it covers are
already complete and stable, so this is coverage-hardening, not a blocker). A multi-player
simulation-test pass over player-to-player **trade** and **shared-vehicle transit** using the
`tests/simulation/` `VirtualPlayer` harness: concurrent trade escrow (no dupe/loss), shared-vehicle
boarding/arrival with multiple riders, and the audit-regression diff across a scripted multi-player
run. Overlaps the `lorecraft.tools.simulation` CLI idea and the perf band's load test (roadmap
Sprint 37.3). (The PvP-consent portion is under *Combat, reframed* above, with the combat set-aside.)

### Scheduler-commit batching 🤔 (was roadmap Sprint 37.1 — deferred 2026-07-05)

Batch all due scheduler jobs in a tick into **one** commit instead of one session+commit per job.
Currently each `SCHEDULED_JOB_DUE` handler (`mobile_route`) opens its own `Session` and commits;
`scripts/perf_baseline.py`'s `scheduler_tick@Njobs` measured this at ~28 ms/job on the old `DELETE`
journal (50 jobs ≈ 1410 ms). **Deferred because SQLite WAL (Sprint 37.4) cut that to ~48 ms @ 50
jobs**, making batching marginal — and it would touch the decoupled event/session contract (handlers
would share a tick-scoped session and defer commits). Restore under a fresh number **only if** a
scheduler-heavy workload (many concurrent transit routes / timed effects due per tick) actually
appears; the benchmark is already in place to re-justify it.

### Concurrency / multithreading gate 🤔 (was roadmap Sprint 38.1 — deferred 2026-07-05)

Adding an async command loop, a parser thread-pool, or process/region sharding. **Deferred because
the measured wall is fsync serialization on the single SQLite writer, not CPU** — threads don't
parallelize SQLite writes, and WAL (Sprint 37.4) removed most of the commit cost anyway
(load-test p50 254 → 58 ms, p99 475 → 83 ms). The transaction-isolation design (own session per
worker, serialized commits, `GameRng` determinism) is still the right spec if this returns.
**Trigger to revisit:** a *post-WAL* realistic-load run (`tests/simulation/test_load.py`, e.g.
`LORECRAFT_LOAD_TEST_PLAYERS=50 LORECRAFT_LOAD_TEST_JITTER_MS=…`) that still shows a hard
single-process wall — likely after moving to a networked backend (Postgres) where the pool knobs
(Sprint 37.2) start to matter.

### PostgreSQL migration 🤔 (assessed 2026-07-05 — not a performance win yet)

Considered and **deferred**: moving the game/audit DBs from SQLite to Postgres would **not** help
performance at the current single-process design, and would likely regress command latency.

- **Why no win now:** the measured bottleneck was *fsync-per-commit on a single writer*, fixed by
  WAL ([Sprint 37.4](roadmap.md)). Postgres also fsyncs per commit (`synchronous_commit=on`) **plus** a
  network/IPC round-trip per query, so its commit latency is ≥ SQLite+WAL with extra per-query
  overhead. Postgres's real edge is *concurrent writers* (MVCC, no single-writer lock) — but the
  engine is single-threaded/single-process (architecture.md §1) and never issues concurrent writes,
  so it can't exploit that. The wall was fsync serialization, not write-lock contention.
- **When it becomes worth it:** alongside the concurrency gate (see *Concurrency / multithreading
  gate* above, was Sprint 38.1) — i.e. when you scale out to **multiple app processes/workers**
  sharing one DB — or for **operational** reasons independent of speed (managed backups, replication,
  many services on one DB). Measure first, as always.
- **Migration effort (if/when):** code is largely DB-agnostic — `database_url()` already passes
  `postgresql+psycopg://…` through, the pool knobs (Sprint 37.2) already target networked backends,
  and WAL/compat-column code is SQLite-gated; JSON columns use portable `Column(JSON)`; no
  SQLite-specific SQL. So *running* on PG ≈ add a `psycopg` dep + point the URL + test against a real
  PG (~a day). The **non-trivial** parts: there's **no Alembic** (schema is metadata `create_tables`
  + ad-hoc SQLite-only `ALTER TABLE`s), so add a real migration tool before prod; migrating an
  *existing* SQLite world's **data** needs `pgloader` / an export-import script; and CI would need a
  Postgres service to validate.

### News & announcements ✅

Already shipped ([Sprint 10.5](roadmap.md#sprint-105--tooling-infrastructure-)): `docs/news.yaml`, in-game `news` command, RSS feed. Listed here
only to note it's _done_, not wanted.

---

## Onboarding & first-time experience

### Character creation walkthrough + intro tutorial 💚

**Design intent (2026-07-03):** new players need a guided on-ramp — today `/lobby/create` is
just a username/password form (see `web/auth.py` and `player_authentication.md`); there's no
in-game character-creation flow or introductory walkthrough once a player is dropped into the
world.

**Roadmap status (2026-07-05):** this was roadmap **Sprint 32.1** (in-game character-creation /
intro walkthrough — authored like dialogue/quests via YAML + the dialogue & side-effect
registries, **skippable and repeatable**, runs once after first spawn with no in-engine
special-casing). Deferred and moved here 2026-07-05; the open product decision is the **trigger
UX** — an opt-in `tutorial` command vs. auto-open-once after first spawn — which also needs a
guide NPC + onboarding dialogue tree authored in `world.yaml` and a config-driven first-spawn
hook. (Sprint 32.2 preferences + 32.3 accessibility already shipped; 32.1 was the only open piece.)

- **Character creation, in-world** — once traits/backgrounds/skills exist (see _Traits, skills
  & character identity_ above), creation becomes more than a name: choose a background/origin,
  maybe answer a few flavor questions that set starting traits/skills/gear. Could be a scripted
  dialogue-tree-like flow (reusing `npc/dialogue.py`'s walker) rather than a bespoke form.
- **Brief walkthrough / intro** — a short, skippable guided sequence after creation: move,
  look, take an item, talk to an NPC, maybe a first tiny puzzle or discovery — teaching the
  core verbs through doing, not a wall of help text. `commands/meta.py`'s context-aware `help`
  already exists as a fallback/reference.
- **Likely scripted and game-specific** — the intro is _content_, not engine logic: which room
  you start in, what the tutorial NPC says, what the first quest hook is are all per-world
  choices. This should be authored the same way dialogue/quests are (YAML + the dialogue
  walker + quest stages), not hardcoded into the engine — and it's a concrete example of the
  **engine/game-data separation** above: the intro script belongs in the content repo, not in
  `src/lorecraft/`.
- **Skippable / repeatable** — experienced players (or alt characters) should be able to skip
  or fast-forward; the tutorial shouldn't gate returning players.
- **Natural home:** an "Ashmoore" (or per-world) starter quest chain using existing
  dialogue-tree + quest-stage primitives, _plus_ whatever character-creation flavor questions
  traits/backgrounds end up needing. No new engine mechanism required — mostly content +
  maybe a couple of onboarding-specific flags (`tutorial_complete`) and a `skip tutorial`
  command.

**When to act:** natural pairing with traits/backgrounds ([Sprint 24](roadmap.md#sprint-24--traits--skills)) for the creation-flavor
part, and useful any time after — doesn't block other feature work. Not yet scheduled on the
roadmap; a good candidate once [Sprint 24](roadmap.md#sprint-24--traits--skills) (traits/skills) lands, since that's what gives
character creation something to actually choose.

---

## Operations, security & deployment 💚 (reference for architecture decisions)

Modern engines (Evennia, CoffeeMud, Discworld) treat operations as a core feature, not an
afterthought. Based on comparative analysis:

### Security baseline 💚

- **Password hashing** — Argon2id or scrypt, never plaintext or reversible. ✅ **Shipped.**
- **Admin/staff authentication** — separate from player login; staff accounts isolated. ✅ **Shipped (JWT + `is_staff`).**
- **Audit log as source of truth** — all mutations logged with actor, target, payload, timestamp. ✅ **Shipped (Sprint 10).**
- **Per-command & per-entity permission locks** — not just role-based. `can_execute(command, player)` checks `command_lock` + `player.permission` + context. Evennia's lock DSL is a proven model. (Basic pattern in place via `conditions.py`; deeper lock DSL is future.)
- **Runtime script sandbox** — if a scripting layer is added (Python, Lua, etc.), bound evaluation budgets and cancellation so runaway code doesn't kill the server. FluffOS's evaluation-cost model is a reference.
- **Network hardening** — reverse proxy (NGINX/HAProxy) terminates TLS; app binds internally only; `/admin` routes restricted to local IPs or staff VPN.
- **Upload safety** — if asset uploads exist (player avatars, world images), scan and segregate them; never execute user media.

### Observability & debugging 💚

- **Structured logging** — JSON lines for machine processing; human-readable summaries for admins. Not just print statements.
- **Metrics** — command latency, scheduler job duration, database commit time, active-player count. Graphed over time (Grafana, Datadog, etc.).
- **Tracing** — trace a single request/command through the system (what locks were checked, what events fired, what DB queries ran). Invaluable for debugging.
- **Error introspection** — `crash report` or `/admin show crash <id>` shows the full stack, inputs, and game state for post-mortems.
- **Player activity log** — per-player `journal` of their actions (commands run, quests completed, items acquired) for anti-cheating or customer service.

### Deployment patterns 💚

**Single VPS** (v0/early access):
- Containerized app (Docker) + SQLite database → simple restore/migrate/rollback.
- TLS termination + reverse proxy on the host.
- Cron-based backups to S3 or cold storage.

**Production-ready** (post-launch):
- App containers behind a reverse proxy (NGINX + healthchecks).
- Database on a managed service (Postgres in RDS, Azure Database, etc.) or internal replica.
- Object store for uploads / world media (S3, GCS, etc.).
- Monitoring + alerting (Sentry for crashes, Prometheus for latency).
- CI/CD (GitHub Actions or internal) to test and deploy on every commit to `main`.

**Future multi-host** (if needed):
- Multiple app processes sharing one DB (stateless design already in place).
- Session sticky routing (a player's connection stays on the same app instance).
- Shared cache (Redis) for session data, rate limits, and cross-process events.
- Careful queue design for scheduler jobs (one instance wins each job via a `LOCK`/`SELECT FOR UPDATE`).

**When to act:** The single-VPS pattern works until ~50 concurrent players. **Measure first** — don't pre-build multi-host infrastructure. When a real bottleneck appears (commits slower than command throughput, or player base grows), measure it, then choose the next tier.

### Testing & CI as prerequisites 💚

- **Unit tests** — parser, permissions, quest logic, trade math. Target: >70% coverage, zero silent failures.
- **Integration tests** — command flow, NPC dialogue, quest progression, persistence migrations.
- **Browser/e2e tests** — player login, navigation, form submission. Catches UI regressions.
- **Simulation tests** — concurrent players, trade escrow, shared vehicles, scheduler stress. Replays `audit_log` to validate determinism.
- **Golden tests** — capture command output + state deltas; regression-test that future changes match (or explicitly document why they should differ).

CI runs the test suite on every commit and blocks merge to `main` if coverage drops or tests fail. See `Makefile` targets: `make test`, `make test-cov`, `make test-e2e`, `make test-simulation`.

---

## Social & meta layers

### Guilds / clans 🚫 (leaning non-goal)

Genre-standard (Aardwolf clans own recall rooms, treasuries, morgues; SMAUG councils). **The
user is not sure Lorecraft wants these.** Heavy social meta-layer that assumes a large,
competitive playerbase. Parking as _probably not_ unless the game grows a community that
actually forms groups and asks for shared identity/spaces. Revisit only then.

### Player-run economy at scale 🚫

Auctions, player shops, clan banks, dynamic markets. Presupposes a busy economy Lorecraft
doesn't have. Not now; maybe never, depending on scale.

### Player groups / parties 🤔

Lighter-weight than guilds: temporary parties for shared travel or content. Could pair well
with the transit theme (board the ferry together). Worth considering _if_ co-op content
appears, without committing to the full guild apparatus. The lightest slice — a **`follow`
command** — was promoted to roadmap
[Sprint 47](roadmap.md#sprint-47--follow-command-social-movement) (2026-07-05).

### Issue-report wizard (upgrade the shipped `report` command) 🤔

**Status (2026-07-07): the guided flow shipped; only the player-moderation branch remains.**
`report <description>` shipped 2026-07-04 (v0.12.0) as a one-liner, and **Sprint 33.1** then
added the guided multi-turn flow: bare `report` runs a **category (bug/feedback/idea) → title →
detail** wizard with `cancel`, state in `player.flags`, free-text routed via
`resolve_command_text` (tested by `test_report_wizard.py`). So the "guided instead of single
command" ask is **done**.

**What actually remains** is the *player-moderation* branch only:

- **`report player <name>`** — asks what's being reported about that player, and records the
  *target* player alongside the *filer*. Today's `Issue` model has no "reported against"
  concept — only `created_by` — so this needs a new `target_player_id`/similar field (or a
  companion table for the reported-player link).
- The open design decision: whether `report player` moderation reports need different
  handling/visibility (admin surfacing) than the `report issue` bug/feedback reports.

Scope for a future sprint: one new wizard branch + one `Issue` field + admin visibility —
much smaller than the original entry implies.

---

## Advanced integrations & AI-assisted pipeline 🤔

### External APIs & integrations 💚 (reference design)

Based on Evennia's Discord bridge and CoffeeMud's multi-channel integrations:

- **Discord relay** — in-game channel messages ↔ Discord webhook (optional bridge, off by default for privacy).
- **IRC / Grapevine / MUD-wide networks** — plug into multi-MUD social layers.
- **RSS / news feeds** — world news updates via feed instead of hand-edits.
- **REST API** — read-only or admin-scoped CRUD on entities, quests, and world state; useful for external dashboards, mobile apps, or third-party tools.

**When to act:** Post-launch and only if a real use case appears (e.g., "I want to build a mobile quest tracker" or "Discord players want a relay"). Start with REST read-only; webhook writes are higher-security risk.

### AI-assisted content creation 🤔

Evennia ships an async LLM NPC contrib; CoffeeMud documents LLM integrations. The key insight:
**AI assists content creation, not game rules.**

- **NPC personality & flavor text** — an LLM can draft dialogue within constraints (tone, vocabulary, factual grounding). A builder reviews and edits.
- **Quest structure & branching** — an LLM can expand a quest outline into branching dialogue trees and stage conditions. Builders author the YAML.
- **Description generation** — room descriptions, item names, NPC appearances. Draft, then edit.
- **Lore summarization** — distill a player's exploration history or NPC relationships for dynamic quests (e.g., "the NPC mentions that past encounter you had").

**Never use LLM for:**
- Game rules, math, or balance decisions.
- The source of truth for lore or quest outcomes.
- Real-time generation (too slow; all content should be pre-authored).

**Design intent:** Keep LLM calls **async and non-authoritative** — use them to *generate candidates* that humans review, not to *compute* game state. This preserves determinism, auditability, and player trust.

**When to act:** Once the quest/dialogue system is stable and builders are asking for content-generation help — probably post-launch. Not a prerequisite.

---

## Architectural patterns worth keeping (not gaps — validation)

The planning comparison confirmed Lorecraft already matches modern-MUD best practice on:

- **Data-driven world building** (YAML → importer → DB) — same as Ranvier/Evennia.
- **Feature registration / pluggable registries** — same spirit as Ranvier behaviors.
- **Event-driven architecture** (`EventBus` + service subscribers).
- **Audit log as source of truth** — canonical, replayable history.
- **World state vs. player state separation** — never conflated.

These aren't wishlist items; they're the foundation the wishlist builds on.

---

## Decisions to make (when items graduate to the roadmap)

| Question                                                | Affects                                                                            | Current lean                                                                                              |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Inventory/equipment before combat?                      | Sprint order                                                                       | **Yes — foundational, wanted next**                                                                       |
| How deep is survival (fatigue/sleep/hunger)?            | Character-condition scope                                                          | Light/flavor, per-world toggle                                                                            |
| Skills: use-based vs. XP-based improvement?             | Progression feel                                                                   | Use-based (fits exploration)                                                                              |
| Attributes: minimal spread or none?                     | Character system                                                                   | Minimal, non-combat-framed                                                                                |
| Death penalty: soft respawn vs. loss vs. permadeath?    | Combat feel                                                                        | **Resolved: resurrect + lose some carried coins/loot** ([`death_resurrection.md`](death_resurrection.md)) |
| NPC combat before PvP?                                  | [Sprint 31–34](roadmap.md#sprint-31--combat-core-services-supporting-system) order | Yes                                                                                                       |
| Currency model shape (what is "money")?                 | Trading, tickets, shops                                                            | **Resolved: carried `coins` + safe `BankAccount`** ([`trade_economy.md`](trade_economy.md))               |
| Regional pricing + transit as the trade network?        | Trade/transit design                                                               | Yes — signature pairing                                                                                   |
| Scripting layer: Python / Lua / YAML-only?              | Builder extensibility                                                              | Hold; decide during combat                                                                                |
| Guilds/clans: in or out?                                | Social scope                                                                       | Leaning out                                                                                               |
| Vehicle = special Room or new entity?                   | Transit design                                                                     | **Resolved: moving-room** ([`transit_systems.md`](transit_systems.md))                                    |
| Engine/game-data split: when to act?                    | Repo structure, scripting design                                                   | Plan for it now; execute once scripting is decided or a 2nd world is wanted                               |
| Tutorial/character-creation: engine feature or content? | Onboarding design                                                                  | Content (scripted, per-world) — reuses dialogue/quest primitives, not new engine mechanism                |
| Split social/channel feed from narrative feed?          | Client UI/layout                                                                   | **Yes — biggest screenshot takeaway**                                                                     |
| Currency model: single int or keyed quantity map?       | Trade ([Sprint 28](roadmap.md#sprint-28--trading--economy))                        | Keyed map — cheap now, expensive to retrofit                                                              |
| Soft caps / diminishing returns on modifiers?           | Traits/skills ([Sprint 24](roadmap.md#sprint-24--traits--skills))                  | **Primitive shipped** — `clamp_min`/`clamp_max` in the §3.5 resolver; content adoption pending           |
| Player settings/preferences: engine feature?            | Accessibility, UX                                                                  | Yes — thread through the render layer early                                                               |

---

---

## Implementation priorities: why and when

The modern-MUD analysis reveals a progression of engine maturity:

**Foundation (Sprints 5–15, largely complete):** Entity model, persistence, game context, permissions,
world clock, scheduler, events, and core services. Without this, everything else is shaky.

**Gameplay core (Sprints 16–35, in progress):** Combat (deferred), trading, quests, exploration,
progression. What players actually _play_. These sprint on the foundation and drive retention.

**Polish & quality (Sprints 36–50, ongoing):** UI/UX, accessibility, performance, builder tools,
documentation. Turns a playable game into a _good_ game. Works because the foundation is solid.

**Operations & scale (Sprints 51+, as needed):** Multi-host deployments, advanced monitoring,
external integrations, LLM pipelines. Only needed when a real problem appears — don't pre-build
for scale you don't have.

The wishlist items reflect this: transit and trading are gameplay-core (Sprint 28+); accessibility
and structured output are polish (Sprint 45+); REST APIs and multi-host are operations (post-launch).
Items without a sprint number are either deferred (pending a design decision or a real need) or
waiting for a prerequisite (e.g., combat before PvP).

---

_Created 2026-07-03 from an architecture + MUD-comparison planning session. Last updated
2026-07-07 with modern-MUD engine analysis (Evennia, Ranvier, CoffeeMud, FluffOS, Discworld,
Aardwolf, BatMUD, Materia Magica, Alter Aeon). Update as ideas are chosen (move to
[`roadmap.md`](roadmap.md)) or explicitly dropped._
