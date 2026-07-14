# Lorecraft — Genuine Gaps: Ready-to-Build Content Features

Generated 2026-07-08. This is a curated subset of [`wishlist.md`](wishlist.md) — the features
that are **not blocked by a product decision** (unlike combat/PvP, leveling/XP, guilds, or
remort, which need a call from the product owner first) and **not explicit non-goals**. Every
item below can be designed and built today on primitives that already exist in the engine.

For each gap: what it is, how to build it on Lorecraft's actual Tier 1/Tier 2 primitives, and
the gameplay it unlocks once it exists.

---

## How to read the implementation notes

Lorecraft's engine already ships these load-bearing primitives (see `engine_core.md`), which
every idea below reuses rather than inventing a parallel mechanism:

- **`ActiveEffect` + `EffectService`** — a generic, clock-expiring effect row keyed by
  `(entity_type, entity_id)`. Already used for player buffs/debuffs *and* room-scoped timers
  (Sprint 39 proved `entity_type="room"` works with zero new code). Auto-expires via the
  `TIME_ADVANCED` sweep; carries a JSON `payload` for instance parameters.
- **`ItemInstance.state` + `ComponentRegistry`** — per-instance item state keyed by component
  name (`durability`, `openable`, ...). New components (a `"charges"` or `"socket"` component)
  register with zero core changes.
- **Modifier resolver (`game/modifiers.py`)** — one function that stacks `add`/`mult`/`clamp`
  modifiers from many registered sources (equipment, traits, terrain, active effects) in a
  fixed order. New sources (a room aura, a quest buff) just implement the `ModifierSource`
  protocol.
- **`CommandConditionRegistry` / `QuestConditionRegistry`** — named, pluggable predicates
  (`object_present`, `npc_present`, flag checks) gating command availability and quest-stage
  transitions. New conditions register a name + predicate function.
- **Quest side-effect registry** (`features/npc/side_effects.py`) — named, pluggable actions
  (set a flag, grant an item, adjust reputation) fired when a quest stage or dialogue branch
  resolves.
- **`SchedulerService`** — DB-backed due-jobs dispatched as `SCHEDULED_JOB_DUE` on the world
  clock's `TIME_ADVANCED` tick. Drives anything time-based without a second timer mechanism.
- **`MobileRouteService`** — the generic "moving room" state machine (built for transit
  vehicles) that advances an entity along waypoints with scheduler-driven ticks and dwell/
  travel timing.

Every feature below is written as "reuse X, extend it this way" — the engine's own convention
(see engine_core.md §3.9: "extend each behavior through its own existing owner, don't add a
parallel system").

---

## Part 1 — Exploration

### 1. Full-world map viewer (region/zoom modal)

**What it is.** A browser modal showing a zoomed-out view of an entire explored region —
not just the immediate-room fog-of-war minimap Lorecraft already has, but a full map the
player can pan and zoom, with fog-of-war shading for unvisited tiles.

**Implementation.** The minimap already tracks per-player visited-room state and room
coordinates. The region map is a rendering-layer feature, not a new data model:

- Reuse the existing room `(x, y, area_id)` coordinate fields and the player's visited-room
  set (already the fog-of-war source of truth).
- Add a new HTMX/Alpine panel (`webui/player/templates/`) that queries "all rooms in this
  area, plus visited state" and renders a scrollable/zoomable grid — a client-side concern,
  no new server model.
- Gate it behind a new panel slot in the existing `WebHost` panel registry (the same seam
  Sprint 26's minimap and the transit presentation module already use).
- Optional: a `cartographer` trait (already in the trait registry) reveals more of the map
  than raw visited-state would (e.g., adjacent unvisited rooms sketched in outline).

**Gameplay it unlocks.**
- Players plan multi-room routes visually instead of by memory — valuable once dungeons or
  trade networks get large.
- A "you are here" marker during transit vehicle travel (the moving-room's interpolated
  position from `MobileRouteService.position()` is already computed for the minimap; the
  region map just renders it at a larger scale).
- Quest markers: pin an active quest's target room on the map (reads existing quest-state
  flags, no new mechanism).
- A visible canvas for "explore to 100% of this region" style discovery goals feeding the
  marks/journal systems that already exist.

---

### 2. Cartography / tradeable maps

**What it is.** Physical map items players can buy, sell, or find that reveal terrain/room
layout for a region without the player having physically explored it.

**Implementation.**
- A map is just an `Item` with a new `map` component registered in `ComponentRegistry`
  (`applies_to: item.item_type == "map"`), whose `state` holds `{"area_id": ..., "revealed_rooms": [...]}`.
- A `read map` command (or a context-attached command via the existing
  `context_commands` mechanism from Sprint 55) merges the map's `revealed_rooms` into the
  player's visited-room set for rendering purposes only — it does **not** grant marks/
  discovery credit, since the player didn't actually go there. That distinction is a single
  `if` in the discovery-reward side effect, not a new system.
- Selling/trading maps reuses the existing P2P trade escrow and shop-stock machinery
  unchanged — a map is just an item with a value.

**Gameplay it unlocks.**
- A whole trade-good category: "the cartographer in the capital sells a map of the eastern
  coast for 40 coins" — pairs directly with the Trading pillar.
- Quest rewards: "the old sailor gives you a hand-drawn map of the smugglers' cove" as a
  puzzle/exploration shortcut reward.
- Regional price differences (already shipped) apply naturally: maps of dangerous or remote
  areas cost more, creating a market for exploration-adjacent goods that isn't just weapons
  or potions.
- A partial-knowledge mechanic: a torn or low-quality map only reveals some rooms, an
  "authoritative" surveyor's map reveals all — reuses the existing item-quality tiers
  (common → legendary) for a non-combat use of that system.

---

### 3. Dungeon complexity (z-levels / structural depth)

**What it is.** Rooms with vertical structure — up/down exits, basements, towers, hidden
floors — using room coordinates that already support it but that world content hasn't
exercised yet.

**Implementation.**
- **Shipped (Sprint 66):** `Room.map_z: int = 0` (additive column, defaults to "ground
  floor," no migration risk to existing content) and `build_map_data()`'s `level` param —
  the player-facing minimap and full-map modal now filter candidate rooms to
  `current_room.map_z`, so a floor that reuses the same `(map_x, map_y)` footprint as
  another floor no longer overlaps on the 2D plot. `up`/`down` exits work exactly as
  before — `map_z` only affects what's *drawn*, not traversal.
- **Still content-only from here:** world YAML hasn't exercised multi-floor structures yet
  (towers, basements, hidden floors) — that's authoring, not engine work.
- **Deferred (not started):** the full-map modal still hard-filters to the current floor
  rather than offering a level selector or plotting inter-level connections (dashed lines
  to `up`/`down` neighbors on a different floor). `level=None` (show every floor at once)
  is already wired as a `build_map_data()` option for whenever that UI lands.
- Secret/structural exits that only *appear* after a puzzle solves reuse Part 3's
  **conditional exits** primitive (see Puzzles section) rather than inventing a second
  mechanism for "hidden" vs. "conditional."

**Gameplay it unlocks.**
- Towers, dungeons, and multi-story buildings with real navigational structure instead of a
  flat room graph.
- "Descend into the crypt" as its own discrete exploration beat, separate from horizontal
  wandering — a natural home for escalating difficulty/atmosphere within one location.
- Verticality gives cartography (item 2) and the region map (item 1) something to actually
  differentiate ("the map shows the ground floor, not the sub-basement") — these three ideas
  compound.

---

### 4. Environmental puzzle gates (terrain-interaction obstacles)

**What it is.** Exploration blocked by a solvable environmental obstacle tied to terrain,
not just a locked door: a collapsed bridge needing planks, a chasm needing a climbing skill
check, a flooded tunnel needing to wait for low tide.

**Implementation.**
- Terrain types already exist and already modify fatigue/travel time/required skills
  (Sprint 25). This extends the same seam: a terrain-gated exit adds a
  `CommandConditionRegistry` entry (e.g. `skill_check:climbing:12`) to the exit's existing
  `condition_flags` — the same field `lock`/`unlock` already writes to for keyed doors.
- Item-based solutions ("place planks across the chasm") are a quest-style side effect: an
  `apply_item_to_exit` side effect (new, small, registered the same way existing side effects
  are) that flips the exit's `condition_flags` permanently or for a duration (reusing the
  Sprint 39 timed-room-effect pattern if it should collapse again later — e.g. planks rot).
- Tide-gated causeways reuse the already-shipped celestial/tide state (Sprint 54) as another
  `CommandConditionRegistry` predicate reading world-clock tide phase — zero new state.

**Gameplay it unlocks.**
- Exploration that rewards preparation (bring planks, learn to climb, time your arrival to
  the tide) rather than just walking in a direction — directly serves the "combat is optional,
  cleverness is a resolution path" design pillar.
- A causeway that's only crossable at low tide creates a natural puzzle/timing beat that pairs
  the celestial system with exploration for the first time in actual content.
- Skill investment (climbing, swimming — both already in the skill list) gets a genuine
  exploration payoff beyond flavor text.

---

## Part 2 — Trading

### 5. Caravans & trade routes

**What it is.** NPC-run (and later escortable) caravans that travel fixed routes on a
schedule, carrying cargo between towns — the trade-network analog of the already-shipped
passenger transit (ferry/rail/balloon).

**Implementation.**
- This is close to a direct reuse of `MobileRouteService` (§3.8) — the same generic
  waypoint/dwell/travel state machine that already drives ferries and rail. A caravan is a
  `RouteSpec` whose `RouteHooks.on_arrive` triggers a cargo-delivery side effect instead of
  (or alongside) passenger boarding.
- Cargo itself is just `ItemStack`s owned by the caravan entity via the existing
  item-location model (§3.2) — no new ownership concept; a caravan is "a holder," the same
  abstraction rooms, players, and containers already use.
- Quest hooks (escort, investigate a missing caravan) are ordinary quest stages whose
  conditions check the caravan's `MobileRouteState.status` (e.g., `status == "halted"` after
  a scripted "robbed" event) — no new quest primitive needed.

**Gameplay it unlocks.**
- **The signature trading feature**: "buy low in the harvest town, the caravan carries it to
  the capital, sell high" — makes the regional-pricing system (already shipped) into an
  active loop instead of a static fact.
- A whole quest genre: escort the caravan (pairs with the set-aside combat spec when it
  ships), investigate why it's late, recover stolen cargo.
- Direct synergy with the **Robbers & highway risk** design (already specified in
  `death_resurrection.md` §8): a caravan carrying visible cargo is exactly the kind of
  "carried wealth is at risk" target that makes banking/safe-transit choices matter.
- Commissions: an NPC pays the player to personally escort or expedite a caravan run — reuses
  existing quest reward/currency plumbing.

---

### 6. Rare & seasonal goods

**What it is.** Shop inventory that varies by season, weather, or world event — a beach town
sells fish only near the coast, a mountain town sells furs after winter arrives.

**Implementation.**
- Shops already have season-aware fields (per the trading design) that aren't yet exercised
  by world content. The gap is **content**, not engine: author shop stock tables with
  `season`/`weather` gates and let the existing restock-on-world-clock scheduler
  (Sprint 28.2, `economy/restock.py`) pick them up — no code changes required for the base
  case.
- If finer-grained gating is wanted (e.g., "only during a festival window," which Sprint 54's
  celestial/scavenger-hunt scheduling already demonstrates), the same
  `CommandConditionRegistry`-style predicate pattern used for tides/exits applies to shop
  stock visibility.

**Gameplay it unlocks.**
- A reason to revisit towns across seasons — direct synergy with the celestial-cycle system
  (moon phases, tides) that currently has no consumer besides puzzles.
- Trade-route content that's genuinely temporal: "the fur caravan only runs after first
  snowfall" ties caravans (item 5) + seasons + transit together.
- Event-driven economy texture without new mechanism: festival tokens, harvest goods, storm-
  damaged stock are all just seasonal shop-stock authoring.

---

### 7. Haggling / dynamic prices (skill & reputation price-flex)

**What it is.** Prices that flex based on the player's bartering skill and standing with an
NPC/faction, not just a static shop-price table.

**Implementation.**
- Bartering skill and reputation both already exist as tracked player state. The gap is
  wiring them into the price calculation, which is exactly what the **modifier resolver**
  (§3.5) is for: register a `ModifierSource` that emits a `price.buy` / `price.sell` `mult`
  modifier derived from `(bartering skill, NPC standing)`, feature-side-capped at a sane
  bound (the engine docs explicitly call out that the *feature* clamps its own discount
  input, e.g. ≤ 25%, before emitting the modifier — the resolver's clamps are for final-value
  bounds only).
- No new persistence: this reads existing skill/reputation state and existing shop-price
  fields; it's a pure calculation change at the point of sale.

**Gameplay it unlocks.**
- Makes the bartering skill and reputation systems (both already shipped) mechanically
  meaningful instead of just flavor — a `silver-tongued` trait or high standing with a
  merchant now visibly saves coins.
- Regional pricing + haggling compound: a well-liked, skilled trader can profitably work
  routes a stranger can't — deepens the buy-low-sell-high loop without new content, just
  richer math on existing numbers.

---

### 8. Commodity markets / boards

**What it is.** A read-only (to start) public display of current supply/demand or notable
prices — "the Grain Board" a player can check before deciding where to sell.

**Implementation.**
- The simplest version is purely a **read** feature: a new panel or command that queries
  existing shop-stock/price state across known shops and renders it — no new data model,
  since prices and stock already live in the economy service.
- A richer version (players post buy/sell offers) would need a new lightweight `MarketOffer`
  model, but that's explicitly **not** required for the "genuine gap" version — the
  read-only board delivers most of the value (visibility into a system that already exists)
  with almost no new surface area.

**Gameplay it unlocks.**
- Removes the "walk to every shop to compare prices" tedium and turns price-comparison into
  a first-class, visible decision — reinforces the trade pillar without adding grind.
- A natural home for surfacing the analytics the admin dashboard already computes
  (item sink/source ledgers, price trends) to *players*, not just admins — a public-facing
  slice of existing observability data.

---

## Part 3 — Questing

### 9. Quest-generated consequences (cross-quest chains)

**What it is.** Player choices in one quest visibly reshape later quests and dialogue —
saving an NPC means they show up later with a discount or a new quest hook; betraying a
faction locks out a questline.

**Implementation.**
- The primitives already exist and are already used *within* a single quest
  (`QuestConditionRegistry` predicates + the shared side-effect registry that sets flags,
  adjusts reputation, grants items). The gap is authoring discipline, not new mechanism:
  quest B's stage conditions read flags that quest A's side effects set.
- NPC memory (already shipped) is the natural carrier for "remembers what you did" — a quest
  side effect that calls the existing `remember` side effect with a durable memory key is
  the whole mechanism; quest B's dialogue conditions check `npc_remembers(key)`.
- No new registry, model, or service — this is a **content pattern** to establish
  ("quests should read flags/memories other quests wrote") more than a code gap.

**Gameplay it unlocks.**
- A world that feels like it remembers the player, which is the single most-cited
  differentiator of narrative-focused MUDs (Discworld's civic depth, story-driven worlds) —
  achievable with zero new engine work, just cross-referencing existing flags/memories
  across quest YAML files.
- Branching regional storylines: helping one town's harvest quest could unlock (or block) a
  neighboring town's trade-caravan quest, tying Questing and Trading pillars together.

---

### 10. Puzzle-locked quest stages

**What it is.** A quest stage that requires solving an environmental puzzle (not just
picking a dialogue option) to advance — a riddle answer, a lever sequence, an item
combination.

**Implementation.**
- Quest stages already advance on `QuestConditionRegistry` predicates. A puzzle-locked stage
  is simply a stage whose advance-condition is a **new predicate type** reading puzzle state
  — e.g. `lever_sequence_correct:<puzzle_id>` reading a small state blob (itself an
  `ActiveEffect`-less plain flag or a dedicated `PuzzleState` row if the puzzle needs to
  persist across sessions).
- The puzzle mechanics themselves (levers, riddles, item combination — items 13–15 below)
  are the actual new surface; once they exist, gating a quest stage on their resulting state
  is a one-line condition, not a new system.

**Gameplay it unlocks.**
- Quests that are genuinely solved, not just clicked through — direct payoff for the Puzzles
  pillar inside the Questing pillar rather than treating them as separate features.
- Investigation-style quests (item 12) become quest-stage puzzles rather than a parallel
  system.

---

### 11. Escort quests (moving-NPC companions)

**What it is.** Guide an NPC through a route to a destination; if the NPC is lost, delayed,
or (once combat ships) harmed, the quest can fail or branch.

**Implementation.**
- The moving-room concept (`MobileRouteService`, §3.8) was built generically enough to drive
  *any* scheduled entity along waypoints, not just vehicles — but an escorted NPC isn't a
  room the player boards; it's an NPC that follows the player's own movement. The right reuse
  is closer to the **`follow` command** (Sprint 47, already shipped) extended so an NPC can
  be the follower instead of only a player: the NPC's location update piggybacks on the
  player's `MovementService.move()` calls, gated by a quest-stage condition
  (`npc_following:<npc_id>`).
- Quest branches on separation/danger are ordinary quest-stage conditions
  (`npc_present: false` in the expected room = "you lost them").

**Gameplay it unlocks.**
- A whole quest genre (guide the merchant to the capital, escort the wounded scout home)
  using almost entirely existing plumbing (`follow` + quest stages + NPC memory for a
  reputation payoff at the end).
- Sets up cleanly for when combat ships: an escorted NPC becoming a target is a natural
  first non-player-vs-player combat scenario.

---

### 12. Investigation / detective quests (clue synthesis)

**What it is.** Gather clues across multiple rooms/NPCs/items, then synthesize them into a
conclusion; a wrong conclusion fails or branches the quest negatively.

**Implementation.**
- The discovery journal (already shipped) is the clue-storage substrate — it already tracks
  discovered lore/items/NPCs per player. The new piece is a **synthesis check**: a quest
  stage condition that counts how many of a named clue-set the player's journal contains
  (`clues_known_count:<set_id> >= N`) before allowing an "accuse"/"conclude" command to
  succeed.
- Wrong-conclusion branching is just an ordinary quest-stage branch keyed off which option
  the player chose relative to which clues they'd actually found — content authoring, not
  new mechanism.

**Gameplay it unlocks.**
- Leans directly into the design pillar note that "text games are uniquely good at
  investigation" — libraries, rumor archives, coded notes all become clue sources feeding
  one quest mechanic instead of one-off flag hacks per quest.
- Replayability: a player who explores more finds more clues and can reach a *better*
  conclusion (extra reward branch) without the quest needing bespoke code per clue count.

---

### 13. Rotating discovery/trade objectives (careful, non-grind repeatables)

**What it is.** Time-windowed objectives that reset (daily/weekly) but are framed as
*rotating opportunities*, not a combat treadmill — "three towns want goods delivered today,"
not "kill 10 rats."

**Implementation.**
- Reuses the scheduler exactly like the already-shipped scavenger hunts (Sprint 48): a
  scheduled job spins up a fresh quest instance from a template at a reset boundary (the
  existing scavenger-hunt cadence design already solved the "noon vs. midnight" reset-window
  question).
- The **only** discipline required is content-side: objectives must be drawn from
  exploration/trade template pools (visit a new region, deliver goods between towns) never
  combat-kill counts, per the design pillar's explicit rejection of grind loops.

**Gameplay it unlocks.**
- A light returning-player hook ("what's today's opportunity?") without inventing a new
  system — literally the same scaffolding as scavenger hunts, pointed at trade/exploration
  content instead.

---

## Part 4 — Puzzles

### 14. Lever / switch / plate mechanics (interactive room-element state)

**What it is.** Room elements with their own on/off or triggered state — a lever, a
pressure plate, a rotating dial — whose state change has a mechanical effect (open a door,
trigger an event, start a timer).

**Implementation.**
- This is precisely the pattern engine_core.md documents for timed room effects
  (§3.9): the authoritative state (an exit's `locked`/`condition_flags`) has **one owner**;
  a lever is a context-attached command (`pull lever`, via Sprint 55's context-commands
  mechanism) whose side effect writes that state directly, optionally through an
  `ActiveEffect` if the change should auto-revert after a duration (the plate-opens-a-gate-
  for-30s case already has a worked design in §3.9).
- A **non-timed** lever (permanent toggle) is even simpler: the side effect just flips
  `Exit.locked` or a room flag with no `ActiveEffect` involved at all — reuse the write-path
  the `lock`/`unlock` commands already use.
- Sequenced puzzles (pull levers in the right order) track a small ordered-progress blob —
  either quest-stage flags (if scoped to one active quest) or a lightweight room/puzzle state
  object if it should persist independent of any quest.

**Gameplay it unlocks.**
- The bread-and-butter of environmental puzzle design: multi-lever sequences, pressure-plate
  traps, timed mechanisms — all buildable from *content* once the one write-path convention
  is established, no new engine primitive per puzzle.
- Feeds directly into puzzle-locked quest stages (item 10) and dungeon complexity (item 3):
  a lever on one floor unlocking a passage on another is a natural combination once z-levels
  exist.

---

### 15. Item-combination / synthesis puzzles

**What it is.** Combine two (or more) items to produce a new one — merge components into a
tool, mix two reagents into a potion — framed as a puzzle mechanic, not a crafting grind.

**Implementation.**
- A `combine <item1> <item2>` command resolves against a small registered recipe table
  (`{(item_a, item_b): result_item}` or a more general N-input table) — structurally almost
  identical to the existing equip/unequip command shape: validate both items are held
  (existing item-location checks), consume them via the existing atomic item-transfer
  primitive (§3.2 — the same "one family of atomic operations" used by take/drop/give/trade),
  then spawn the result item into the player's inventory.
- No new persistence model: recipes are a static registry (Tier 2 content), not per-instance
  state; the *interesting* per-instance behavior (a combined item inheriting some component
  state from its inputs, e.g. a repaired item keeping partial durability) reuses the existing
  `ComponentRegistry` initial-state hooks.

**Gameplay it unlocks.**
- Puzzle-flavored crafting: "combine the rusty key and the whetstone to get a usable key,"
  "mix nightshade and spring water for an antidote" — serves the Puzzles pillar without
  opening the door to a full crafting-economy grind (explicitly out of scope per the wishlist
  decision table).
- Quest integration: a quest can require a combined item as its completion condition, reusing
  ordinary inventory-possession quest checks — no special-casing needed.

---

### 16. Riddle / knowledge-gate puzzles

**What it is.** An NPC or inscription poses a riddle whose answer must be *known*, drawn
from lore the player has actually discovered (journal entries, dialogue, examined objects) —
not an arbitrary free-text parser challenge.

**Implementation.**
- Riddles are best modeled as a **multiple-choice dialogue node** (reusing the existing
  dialogue-tree walker) whose available answer options are filtered by which knowledge flags
  the player currently holds — i.e., a dialogue-option visibility condition
  (`knowledge_flag_known:<flag>`) using the same `QuestConditionRegistry`-style predicate
  pattern already used elsewhere.
- Free-text answer matching (if wanted for flavor) is a thin normalize-and-compare layer on
  top of the parser's existing text resolution — not a new NLU system; scope it to fixed,
  author-known answer strings only.

**Gameplay it unlocks.**
- Turns the discovery journal / knowledge-flag system (already shipped) into an active gate
  instead of a passive log — "you can only answer this because you read the inscription in
  the ruined chapel earlier," rewarding attentive exploration with puzzle access.
- Natural pairing with investigation quests (item 12): the riddle *is* the synthesis step for
  a mystery quest.

---

### 17. Conditional exits (state-gated passages)

**What it is.** An exit that only exists/opens under a condition — a secret door that
appears after a key item is collected, a portal open only at night, a bridge that solidifies
after a puzzle stage completes.

**Implementation.**
- Exits already carry `condition_flags` checked by `MovementService.move()` before allowing
  passage — the same field the world-content lock/key mechanic already exercises (see the
  playtesting notes: "Locked door... Vault Hall"). A conditional exit is the *same* field
  gated by a different predicate: a quest-stage flag, a world-clock day/night check, or the
  already-shipped celestial/tide state — all are just different `CommandConditionRegistry`
  entries plugged into the one exit-gating seam.
- "Secret exit only appears after a puzzle" is a **visibility** question (should `look`/exits
  list even show it) as well as a **passability** one — both read the same condition, so
  there's no risk of the two disagreeing.

**Gameplay it unlocks.**
- Night-only encounters and portals (pairs with celestial cycles, already shipped but under-
  used).
- Secret-room payoffs for puzzle-solving (pairs with levers, item 14, and puzzle-locked
  quest stages, item 10) — "the bookshelf slides aside" becomes a real mechanic instead of
  flavor text with no backing state change.
- Tide-gated causeways (already called out in item 4) are a specific instance of this general
  primitive.

---

### 18. Stateful room decorations (state-aware `examine`)

**What it is.** `examine` output that reflects live entity/room state rather than static
prose — a torch is lit or unlit, a door is open or closed, an altar shows different text
before/after a ritual.

**Implementation.**
- Item/room state already exists (`ItemInstance.state` via the `ComponentRegistry`, room
  flags for doors). The gap is purely in the **render layer**: `examine`'s text-assembly
  step should interpolate current component state into the description template instead of
  always emitting the item's static `long` description.
- Concretely: a description template becomes a small conditional (`{% if state.lit %}...{%
  else %}...{% endif %}`-style) resolved at render time from the same `state` bag the engine
  already persists — no new data, just a smarter renderer.

**Gameplay it unlocks.**
- Makes puzzle feedback legible: after pulling a lever, `examine door` should say "ajar"
  instead of nothing changing in the text the player sees — this is the missing feedback
  loop that makes items 14/16/17 feel responsive rather than silent.
- General immersion win across all existing content (lanterns, doors, containers) for
  relatively little render-layer work, since the state already exists everywhere it'd apply.

---

## Part 5 — Tooling & World-Building

### 19. Content preview / diff view

**What it is.** Before publishing a YAML edit (a room, quest, or item change) made through
the web builder tools, show the builder a diff of what will change.

**Implementation.**
- The YAML import/export pipeline and content validators already exist and already produce
  a canonical serialized form of world content. A diff view is a matter of running the
  existing exporter against both the pre-edit and post-edit in-memory state and rendering a
  standard unified diff in the admin UI — no new content model, just a new admin-console
  view over data the export path already knows how to produce.
- Pairs naturally with the existing linting pass (`lorecraft.tools.validators`): run
  validation on the *proposed* diff before allowing publish, surfacing errors pre-commit
  instead of post-commit.

**Gameplay/production value it unlocks.**
- Builder confidence: catch an accidental quest-stage regression or a broken exit reference
  before it ships to players, using validation infrastructure that already exists.
- A natural stepping stone toward safe multi-builder collaboration (see a builder's change
  before it lands) without needing a full versioned-branches system.

---

### 20. World versioning & rollback (snapshot restore)

**What it is.** The ability to restore world state (prices, room descriptions, quest
definitions) to an earlier point — "revert the market prices to two days ago."

**Implementation.**
- The audit log is already the canonical, replayable history of every change (a foundational
  architectural commitment, not a gap). The missing piece is purely a **UI/tooling** layer:
  an admin-console view that lets an operator pick a timestamp and either (a) preview a diff
  against current state (reusing item 19's diff renderer) or (b) replay-and-restore specific
  fields from the audit trail.
- No new persistence or audit schema needed — this is exposing existing data, not capturing
  new data.

**Gameplay/production value it unlocks.**
- Fast recovery from a bad content push or an accidental admin action, using data that's
  already being captured — currently that data exists but isn't surfaced for restore, only
  for forensic reading.
- Confidence to let more builders touch live content, knowing mistakes are recoverable.

---

### 21. Public REST API expansion (read-only ecosystem endpoints)

**What it is.** A narrow, public (non-admin) REST surface exposing read-only world data —
room/item/NPC lookups, aggregate world stats — for community tools and bots, distinct from
the existing admin-only REST API.

**Implementation.**
- The admin REST API already demonstrates the pattern (FastAPI routers, auth middleware,
  JSON responses over existing service-layer queries). A public API is the same shape with
  a different auth policy (no admin session required, rate-limited) and a narrower query
  surface (read-only, no mutation endpoints).
- The "player-facing world graphs / stats" idea already in the wishlist (aggregate world
  statistics, distinct from admin analytics) is a natural first consumer — the analytics
  queries (Sprint 13/51) already exist; this just exposes a public-safe subset of them.

**Gameplay/ecosystem value it unlocks.**
- Community tooling: a companion web page showing "who's online," "recent news," or "world
  population over time" without needing admin credentials.
- A foundation for any future bot/Discord-relay work (explicitly deferred elsewhere) without
  committing to that integration now — the API surface is useful on its own.

---

## Summary table

| # | Feature | Pillar | Reuses | New surface |
|---|---------|--------|--------|--------------|
| 1 | Full-world map modal | Exploration | Room coords, visited-state, panel registry | Render-only |
| 2 | Cartography / tradeable maps | Exploration | ComponentRegistry, trade/shop, context-commands | New `map` component |
| 3 | Dungeon complexity (z-levels) | Exploration | Room coords, exits | Content + optional `z` field |
| 4 | Environmental puzzle gates | Exploration | Terrain, CommandConditionRegistry, tides | New condition types |
| 5 | Caravans & trade routes | Trading | MobileRouteService, item-location model | New RouteSpec + hooks |
| 6 | Rare & seasonal goods | Trading | Shop restock scheduler, celestial state | Content only |
| 7 | Haggling / dynamic prices | Trading | Modifier resolver, skills, reputation | New ModifierSource |
| 8 | Commodity markets/boards | Trading | Existing economy service queries | New read-only view |
| 9 | Cross-quest consequences | Questing | Flags, NPC memory, side-effect registry | Content pattern only |
| 10 | Puzzle-locked quest stages | Questing | QuestConditionRegistry | New condition types |
| 11 | Escort quests | Questing | `follow` command, quest stages | Follower-NPC extension |
| 12 | Investigation / detective quests | Questing | Discovery journal, quest stages | New synthesis condition |
| 13 | Rotating trade/discovery objectives | Questing | Scavenger-hunt scheduler pattern | Content templates |
| 14 | Lever / switch / plate mechanics | Puzzles | Context-commands, ActiveEffect, Exit state | New side effects |
| 15 | Item-combination puzzles | Puzzles | Item-transfer primitive, ComponentRegistry | New `combine` command + recipe table |
| 16 | Riddle / knowledge-gate puzzles | Puzzles | Dialogue tree, knowledge flags | New condition type |
| 17 | Conditional exits | Puzzles | Exit `condition_flags`, existing predicates | New condition types |
| 18 | Stateful room decorations | Puzzles | ItemInstance/room state | Render-layer only |
| 19 | Content preview / diff view | Tooling | YAML export, validators | New admin view |
| 20 | World versioning & rollback | Tooling | Audit log | New admin view |
| 21 | Public REST API expansion | Tooling | Admin REST pattern, analytics queries | New router + auth policy |

---

_Curated 2026-07-08 from `wishlist.md`'s decision table, cross-referenced against
`engine_core.md`'s Tier 1 primitive specifications. Excludes combat/PvP, leveling/XP, guilds/
clans, remort, and other items that need a product decision before design work starts — see
`wishlist.md` and `architecture_comparison.md` for those._
