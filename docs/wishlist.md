# Lorecraft — Wishlist & Idea Backlog

> **Purpose:** A menu of gaps, unimplemented ideas, and "wouldn't-it-be-cool" features
> gathered from a planning session comparing Lorecraft against classic MUDs (Evennia,
> Ranvier, SMAUG, Aardwolf, Materia Magica) — 2026-07-03.
>
> **This is not a roadmap.** Nothing here is committed. The roadmap
> ([`roadmap.md`](roadmap.md)) is the authoritative work queue; items graduate _into_ it
> only after they're chosen and scoped. This file is where ideas live before that.
>
> **Consolidation pass (2026-07-08):** merged in `wishlist2.md` (a MUD-survey quick-reference
> guide that existed only on the `research` branch) and `wishlist3.md` (a shipped-feature audit
> + "genuine gaps" list built for a Kindle doc). Everything the 2026-07-07 codebase sync had
> flagged as **Shipped** was removed outright rather than left as a dead note — *timed/scheduled
> quests*, *attributes*, *item quality/rarity*, *durability*, *bound items*, *NPC memory*, *shop
> restock*, *collectible marks*, *celestial cycles*, *timed room effects*, the *item discovery
> journal*, the *full-screen map modal*, *coloured/prefixed channels*, and *news/announcements*
> are gone from this doc because they're done — see `roadmap_completed.md` for what shipped and
> when. New ideas surfaced by that merge (escort quests, investigation/detective quests,
> cross-quest consequences, dungeon z-levels, commodity boards, dynamic spawn policies, player-
> built world/housing, AI-assisted content, multi-protocol networking, world rollback) are
> folded into the sections below rather than kept as a separate file. `wishlist3.md` is deleted
> from this branch as fully superseded; `wishlist2.md` was never on this branch to begin with.
>
> **Doc-hygiene pass (2026-07-09):** the 2026-07-07 audit missed that Sprints 23, 25, 29, and 30
> (inventory & equipment, exploration depth, transit systems, quests & puzzles) had *already*
> shipped by the time this file's section headers were last touched — those four sections still
> read "wanted next" / "top candidate" / "core pillar" as if unbuilt. Retitled to "✅ Shipped" with
> only the genuinely-open sub-items (mostly the ones already dated 2026-07-08, added after those
> sprints shipped) kept. Also fixed a false claim under *Trading & economy depth* (haggling/
> dynamic pricing was already live in `economy/service.py`, not unbuilt) and removed a dangling
> reference to a `genuine_gaps.md` file that was never created in this repo. **Lesson for future
> passes:** cross-check against `roadmap_completed.md`'s sprint list, not just memory/git-log
> skimming, before annotating something as open.

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

## Featured idea: travel & transit systems 💚 ✅ Shipped — Sprint 29

**Was the single most-wanted item from the original 2026-07-03 planning session** — Materia
Magica's ferries/balloons/rail-with-tickets/travel-animation. **Fully shipped** (see
[`roadmap_completed.md`](roadmap_completed.md#sprint-29--transit--travel-systems)): data-driven
transit lines (ferry/rail/balloon/caravan) in world YAML, a scheduler-driven vehicle state
machine (`board`/`disembark`/`schedule`), ticket-item gating, minimap position animation via WS
push, and weather grounding/delays. Design doc: [`transit_systems.md`](archive/transit_systems.md).
Remaining gap, if any: more world-content routes — the mechanism itself is done.

---

## Mechanics ideas menu

A deliberately large brainstorm of mechanics that serve the exploration / trade / quest /
puzzle pillars. Not everything here should be built — the point is a rich menu to pick from.
Where possible, each notes what Lorecraft primitive it builds on.

### Inventory & equipment 💚 ✅ Shipped — Sprint 23 (one genuine gap remains)

**The core system shipped** (see
[`roadmap_completed.md`](roadmap_completed.md#sprint-23--inventory--equipment)):
`wear`/`remove`/`wield`/`unwield`/`equipment` commands, equipped-ness as a slot on the player's
own item stack, encumbrance bands resolved at runtime from weight + `carry_bonus`
(`game/encumbrance.py`), and containers (`put in`/`take from`, nesting, worn-container capacity,
light/darkness gating). Lantern-oil-style fuel consumption also shipped separately as the `light`
feature (`LightFuelService`). What's left:

- **Attunement** — some gear must be attuned before its passive effects work. Bound items exist
  (`Item.bound`, soulbound, can't drop/sell/trade) but attunement-*before-use* is a distinct,
  still-open mechanic — genuinely unbuilt (confirmed 2026-07-09: the "Marks & Attunements"
  feature package is the unrelated Sprint 53 collectible-marks system, not gear attunement).
  Protects quest integrity and adds a light gearing step.
- **Consumables & charges beyond fuel** — potions, food, scrolls with limited charges (lantern
  oil already works via `light`; a general charge-count mechanic on other consumable items is
  still open).

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
- **Reputation / standing** — per-NPC and per-faction opinion that unlocks dialogue, prices,
  quests, and access. The social spine of a quest-driven world. NPCs _remember_ you.
- **Knowledge / lore flags** — "known facts" a player accumulates that unlock dialogue options
  and puzzle solutions (already partly expressible via the flag system). Turns exploration into
  a knowledge-progression system parallel to leveling.
- **Languages** — some NPCs/signs/books require a language; learning one is a quest reward.

### Exploration depth 💚 ✅ Shipped — Sprint 25 (a few genuine gaps remain)

**Core system shipped** (see
[`roadmap_completed.md`](roadmap_completed.md#sprint-25--exploration-depth)): discovery rewards
(knowledge flags on finding new rooms), the `search` command with hidden-exit/secret-room reveal
gated on perception/traits/light, room/exit `terrain` types affecting travel + required
skill/gear, and a `journal` auto-log of discoveries. Cartography map-reveal is part of the
Sprint 26 map UI. What's left, dated 2026-07-08 (added *after* Sprint 25 shipped, so these are
genuinely new, not duplicates):

- **Environmental puzzle gates 💚** — exploration blocked by a solvable obstacle tied to terrain,
  not just a locked door: a collapsed bridge needing planks, a chasm needing a climbing-skill
  check, a causeway only crossable at low tide. Builds on the same exit `condition_flags` the
  lock/key mechanic already writes to, plus the already-shipped celestial/tide state as another
  gating predicate — no new state, just more predicate types on an existing seam.
- **Dungeon complexity / z-levels 💚 (foundation shipped Sprint 66)** — rooms with real vertical
  structure (basements, towers, hidden floors), not just a flat room graph. `Room.map_z`
  (default 0) now exists and the minimap/full-map filter to the current floor, so multi-floor
  content can reuse `(map_x, map_y)` per floor without overlapping. What remains is purely a
  **content** gap — `world_content/world.yaml` has zero `map_z` usage as of 2026-07-09 — plus a
  region-map level selector / inter-level connection rendering, still undesigned.
- **Conditional / state-gated exits 🤔** — an exit that only opens under a condition: a secret
  door after collecting a key item, a portal open only at night, a bridge that solidifies after
  a puzzle stage. Same `condition_flags` seam as environmental puzzle gates above, just gated by
  a quest flag or the world clock instead of terrain.

### Trading & economy depth 💚 (core pillar — designed in `trade_economy.md`, roadmap Sprint 28)

Beyond the basic currency→shops→P2P ladder in _Gameplay systems_ below:

- **Regional price differences** — goods cost different amounts in different places; the core
  trade loop is buy-low-here, sell-high-there. **This is the killer pairing with transit
  systems** — the ferry/rail network _is_ the trade network. Exploration feeds trade feeds
  exploration.
- ~~**Haggling / dynamic prices**~~ **Shipped as part of Sprint 28.** `EconomyService.buy_price()`
  (`features/economy/service.py`) already applies both a bartering-skill discount
  (`_barter_discount`) and a per-NPC reputation discount (`_rep_discount`), each capped, on top
  of quality/region/demand multipliers — verified in code 2026-07-09.
- **Caravans / trade routes / commissions** — deliver goods between towns for profit; escort or
  investigate when they go missing (quest hooks). A whole quest genre falls out of this. Reuses
  the moving-room/`MobileRouteService` machinery already built for passenger transit — a
  caravan is the same waypoint/dwell/travel state machine with cargo instead of passengers.
- **Rare & seasonal goods** — availability tied to season/weather/events, rewarding travel and
  timing. Shops already have season-aware fields the restock scheduler could read; mostly a
  content gap (world YAML hasn't authored seasonal stock tables yet).
- **Commodity markets / boards 🤔 (2026-07-08)** — a read-only "Grain Board" style display of
  current shop prices/stock across known towns, so players can compare without walking to every
  shop. Pure query over existing economy-service state; no new data model for the simple
  version (a richer player-posted-offers board would need one, but isn't required to get most
  of the value).

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
- **Later:** player-robber roles, guard NPCs, fences for stolen goods — all deferred; v1 is
  just "NPCs can rob carried wealth, banks/transit mitigate it." (Bounty/target marks — a
  related but distinct risk mechanic — now has its own entry under *PvP* below.)

Design intent noted 2026-07-03 (product owner). No dedicated design doc yet; the money-at-risk
mechanics are specified in [`death_resurrection.md`](death_resurrection.md) §8. Sprint TBD —
naturally lands after banks ([Sprint 28](roadmap.md#sprint-28--trading--economy)) and combat ([Sprint 31](roadmap.md#sprint-31--combat-core-services-supporting-system)).

### Quests & puzzles 💚 ✅ Shipped — Sprint 30 (a few genuine gaps remain)

**Core system shipped** (see
[`roadmap_completed.md`](roadmap_completed.md#sprint-30--quests--puzzles-depth)): branching
quests with consequence side-effects and NPC memory, environmental/mechanism puzzles
(`turn`/`pull`/`activate` on `Item.mechanism_states`), item-combination puzzles
(`Item.combination_side_effects` via `use X with Y`), and clock-driven timed quest events
(`QuestTimerService`). Non-combat resolutions (stealth/persuasion/bribery) are the pillar's
default framing throughout. What's left, dated 2026-07-08 (added *after* Sprint 30 shipped —
genuinely new, not duplicates):

- **Investigation / detective quests 💚** — gather clues across rooms/NPCs/items, then
  synthesize them into a conclusion; a wrong conclusion fails or branches the quest negatively.
  The discovery journal already stores the clues; the new piece is a synthesis check — a
  quest-stage condition counting how many of a named clue-set the journal contains before an
  "accuse"/"conclude" command succeeds.
- ~~**Escort quests**~~ **✅ Shipped — Sprint 68 (2026-07-09).** An NPC can now follow a player
  (`NPC.following_player_id`, DB-backed) via the `"start_escort"`/`"end_escort"` dialogue/quest
  side effects, moving along on `PLAYER_MOVED` the same way a player-follower does; losing
  co-location quietly ends the escort. `"npc_following"`/`"npc_present"` quest conditions gate
  stages on it. See `features/follow/service.py` + `features/follow/conditions.py`. Delayed/
  harmed (once combat ships) outcomes are still future work — v1 only covers "lost".
- **Cross-quest consequences 💚** — one quest's choices visibly reshape a later quest or NPC's
  dialogue (saved them → discount later; betrayed a faction → locked questline). This is a
  **content discipline**, not a new mechanism: quest B's stage conditions read the
  flags/NPC-memory keys quest A's side effects already wrote. Worth calling out explicitly as a
  pattern to author toward, since the primitives (flags, `npc_remembers`, side effects) already
  exist but aren't yet used *across* quests, only within one.

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

#### Combat/PvP historical notes (updated 2026-07-15)

NPC-first combat has moved back onto the active roadmap and now follows
[`combat_design.md`](combat_design.md): Scheduled Intent actions, health/stamina, stances,
guarding, bounded reactions, status effects, simple ranged attacks, qualitative threat, and
party assistance metadata. The older tick-based combat sketch remains archived for context only.

Still deferred:

- Opt-in PvP consent, duel stakes, and player-vs-player simulation coverage.
- Player formations, persistent near/far bands, grappling/flanking/screening, and other
  multi-player tactical-position systems.
- Mounted/siege combat as a content-specific layer for future mounts, vehicles, artillery, or
  siege zones. Do not build a generic formation/range subsystem for this until content demands it.
- Harsher wound penalties and death consequences beyond the current inspection-only wounds,
  downed/defeated policy, and soft player death loop.

Keep these deferred until NPC combat has enough playtest feedback to show which extra layers are
actually useful.

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

- **World-placed shrines / altars 🤔** — discoverable stations offering a set of _mutually
  exclusive_ boons, one active per station, bought with a token currency; multiple stations
  stack. An exploration reward + light respec-able customization + currency sink in one. The
  mutex-per-station rule keeps it from becoming a flat power-stack.

#### Systems & balance design notes

- **Soft caps / diminishing returns 💚 (content adoption, not new engine work)** — the modifier
  resolver already supports `clamp_min`/`clamp_max` (hard ceilings/floors); the open work is
  content actually *using* them — "no 100% resistance," tiered damage drop-off — so nothing
  goes degenerate as traits/skills/effects stack.
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
- **Categorized, searchable help / codex 💚** — help topics with categories + `help topics
  [search]` filtering already ship; the remaining work is a browser **codex panel/modal**
  (full-text search + clickable cross-links) merged with the journal/lore log.
- **Player-facing world graphs / stats 🤔** — Alteraeon-style `graph` command/page: aggregate
  world statistics players can browse (hourly/daily player load, economy/gold offsets), distinct
  from admin analytics — a *public* "what is the whole world doing" view. Reuses existing metric
  queries + the `dataviz` skill; could also be exposed as a narrow **public read-only REST
  endpoint** for community tooling (a companion page, a bot) rather than only an in-game panel.
- **Instanced minigames / scenarios 🤔** — themed self-contained challenge areas (Fractals of the
  Weave: Unseelie Court, caravan defense) that repop on a timer (every 60h, _unannounced_ — players
  learn the rhythm) and restore vitals at checkpoints. Good fit for the feature-registration pattern +
  scheduler; the caravan-defense one pairs with the trade-route idea. Defer, but a strong "special
  content" mould. (The simplest *non-instanced* slice already shipped as scavenger hunt events.)

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

[Sprint 28](roadmap.md#sprint-28--trading--economy). Designed in [`trade_economy.md`](archive/trade_economy.md): currency (carried `coins` +
`BankAccount`) → NPC shops → regional pricing → banks → player-to-player trade.
_Deferred:_ auctions, dynamic global market — until there's real trading volume.

### PvP 🤔 (set aside from the roadmap — 2026-07-05)

Consent-based (challenge/accept) reusing the combat system. **Design choice pending:** soft
opt-in PvP (most modern MUDs, Aardwolf's "99% harmless") vs. anything more punishing. Lean
soft unless Lorecraft wants a darker RP tone.

### Bounty / target marks 🤔 (2026-07-08, PK-oriented — needs the PvP consent decision first)

A player or NPC can be **marked** for assassination or hunting; other players who kill (or
capture/subdue) the marked target collect a reward. Common in PK-oriented MUDs — genuinely
interesting, but it inherits the same open question as PvP above (soft vs. punishing) since a
bounty is only meaningful if killing the target is actually possible.

- **Issuing a mark** — an NPC (a "bounty board" or specific quest-giver) or, later, a player
  posts a bounty: target id, reward (coins from the existing ledger, or an item), optional
  expiry. Reuses the currency/ledger primitive for the reward escrow and the flag/reputation
  system to record "is marked" state on the target.
- **NPC bounties first, player bounties later** — mirrors the existing "NPC combat before PvP"
  sequencing decision: a hunted NPC (a fugitive, a monster with a price on its head) is much
  lower-stakes to design and test than a marked *player*, and reuses quest/combat primitives
  directly (kill-quest with a bulletin-board presentation instead of a quest-giver dialogue).
  Nothing new here beyond how the reward is discovered.
- **Marked-player variant (needs PvP first)** — requires the PvP consent model to exist and
  resolve: is being marked itself a form of consent to be attacked, or does the attacker still
  need the target to accept a challenge? (If the latter, a mark just adds a reward on top of
  ordinary consensual PvP, which is far simpler than a non-consensual bounty-hunting system.)
- **Avoidance-first, per the pillars** — a marked player/NPC can go into hiding (leave the
  marked area, change disguise if that ever exists), buy the mark off (pay to clear it,
  economy sink), or seek protection (a safe-zone flag, guard NPCs) — killing on sight isn't the
  only resolution, consistent with the "combat is optional" stance elsewhere in this doc.
- **Reward payout & proof-of-kill** — on the marked target's death/defeat, a side effect (same
  registry `death_resurrection.md` already uses) pays the escrowed reward to whoever landed the
  killing blow (or subdued them, if non-lethal outcomes count) and clears the mark flag.
- **Overlaps existing ideas** — shares its whole risk/reward shape with
  [*Robbers & highway risk*](#robbers--highway-risk--ties-money-travel--death) (carried wealth
  and marked status both make you a target) and with the *Reputation / standing* system (a
  faction could auto-mark anyone whose standing drops low enough — a "wanted by the guard"
  bounty with no player involved at all).

**When to act:** after the PvP consent design question above resolves, and after NPC
combat is real (bounty-on-an-NPC is the natural first slice — a "wanted poster" quest
board is mostly presentation on top of existing kill-quest + reward plumbing).

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

### Dynamic area behaviors & spawn policies 💚 (2026-07-08)

Respawn, ecology, and events should be content decisions, not engine constants: one forest
respawns gradually, a siege zone spawns in waves, a depleted ruin stays depleted. Put area/spawn
controllers behind the feature-registration pattern (swappable per area) rather than a single
hardcoded respawn timer — the scheduler + `SCHEDULED_JOB_DUE` primitive already generalizes to
this, it just isn't parameterized per-area yet.

---

## Client UI, layout & presentation 💚 (from Aardwolf/MUSHclient screenshots, 2026-07-03)

Three classic MUSHclient/Aardwolf multi-pane layouts were reviewed for pane/layout/style ideas.
Lorecraft is browser-based, so most of these map onto HTMX panels it already has (room, inventory,
minimap, players-online, quest tracker, world-clock bar) — the value is in _what deserves its own
pane_ and _how information is separated_.

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
- **Two map zoom levels 🤔** — the full-screen pan/zoom map modal already shipped (Sprint 26.1);
  the still-open nuance is whether a _local_ minimap and a _zoomed-out region/area map_ (tiled
  grid, colour-coded rooms) should ever show **together**, or stay local-inline + region-modal
  as today (screen budget favors the latter — low priority, revisit only if it's felt as a gap).
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

### Admin monitoring and operations ideas 🤔 (triaged 2026-07-16)

The actionable, ordered queue for Admin UI and tooling now lives in
[`roadmap.md`](roadmap.md#admin-ui--tooling-triage-2026-07-16). This wishlist keeps the larger or
less-proven ideas that are worth preserving but should not become sprint work until the smaller
admin backlog proves the need.

Already covered or actively in-flight elsewhere:

- ~~Category-based admin navigation with contextual sub-tabs~~ — `admin-ui` branch.
- ~~Live tuning for Clock, Weather, Combat, Progression, and Economy~~ — shipped or `admin-ui`
  branch depending on the tab.
- ~~Crash reports, trace lookup, analytics, audit, and graceful restart controls~~ — shipped or
  `admin-ui` branch.
- ~~Player record editing from the player list~~ — `admin-ui` branch.
- ~~Issues, News, Help, Accounts, World room editing, and Changesets~~ — existing admin tooling.

Wishlist-only items, ordered by how soon they might become useful:

- **Interactive snoop / force-command mode** — let an admin execute commands as a player with a
  mandatory audit reason. Do not build until the read-only Live Session Viewer in the roadmap has
  shipped and its safety model is proven.
- **Audit replay sandbox** — select an audit window or incident and replay it in an isolated
  instance. High debugging value, but requires stronger structured audit coverage and sandbox
  lifecycle tooling first.
- **Full visual Behavior Tree editor** — node editor that serializes to YAML, side-by-side with raw
  YAML. Valuable only after basic schema validation, diff preview, and read-only NPC/AI inspection
  exist.
- **Behavior Tree step debugger** — pause on conditions/actions, inspect blackboard per tick, and
  force branches in a test instance. Keep behind the visual/editor work; it is a specialist tool.
- **Admin break-glass workflows** — elevated snoop/force/edit mode that notifies other admins and
  records heavier audit. Useful for production operations, not needed for solo/dev playtesting.
- **Builder collaboration suite** — area locks, comments, review queues, and ownership. Worth it
  only once more than one active builder is editing the same content at the same time.
- **Behavior variant A/B testing** — compare NPC tree variants or balance configs across test
  cohorts. Requires analytics maturity and enough player volume to matter.
- **External notifications and integrations** — Discord/email/webhooks for alerts. Start with
  in-dashboard toasts first; external integrations wait on async event/webhook demand.
- **Public/community stats API** — read-only non-admin world stats and dashboards. Keep separate
  from admin APIs and privacy-sensitive player monitoring.

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

### Content preview / diff view + world versioning 🤔 (2026-07-08)

- **Content preview / diff view** — before publishing a web-builder YAML edit, show a diff of
  what will change. The existing exporter + `lorecraft.tools.validators` already produce a
  canonical serialized form and a lint pass; this is running both against pre/post-edit state
  and rendering a unified diff in the admin UI — no new content model.
- **World versioning & rollback** — restore world state (prices, descriptions, quest defs) to
  an earlier point ("revert market prices to two days ago"). The audit log is already the
  canonical, replayable history; the gap is purely a UI layer exposing it for restore, not new
  persistence.

### Networking & protocols 🤔 (multi-client support, low priority)

Lorecraft is deliberately WebSocket/browser-only today — no Telnet, no GMCP/MSDP/MXP. That's
the right call while the audience is a browser-first community, but worth naming as an
explicit option rather than an accident:

- **GMCP/MSDP structured OOB** — would let traditional MUD clients (Mudlet, CMUD, Tintin++)
  consume vitals/map/event data the way the WebSocket JSON payloads already do for the browser
  client. Revisit only if a retro-client community actually forms.
- **External integrations** — Discord relay, RSS/news bridging (news RSS already ships),
  cross-game chat. Would sit at the composition layer, behind the same permission checks as
  in-game commands. Nice-to-have, not requested yet.
- **Public read-only REST API** — a narrow, non-admin API surface (room/item/NPC lookups,
  aggregate world stats) for community tooling — distinct from the existing admin-only REST
  API. Natural first consumer: the player-facing world-graphs/stats idea above.

### AI-assisted content & procedural generation 🤔 (2026-07-08, edge-only)

- **AI/LLM-assisted NPCs & content** — a lore tutor, barkeep, or codex assistant answering in
  character; builder-assistance and localization drafts. Keep strictly **async and
  non-authoritative** — never the source of truth for game rules, quest outcomes, or combat
  math. Cost, moderation, and determinism are the real risks; scope any first attempt to pure
  flavor dialogue with a hard fallback to static text.
- **Procedural generation with authorial constraints** — randomized quest objects, shuffled
  clues, parameterized dungeon layouts generated from bounded templates + seed values, never
  freeform randomness. Strong for variation, weak as a substitute for hand-authored content —
  Lorecraft's narrative-quality bar means this stays a minor accent, not a content pipeline.

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

## Social & meta layers

### Guilds / clans 🚫 (leaning non-goal)

Genre-standard (Aardwolf clans own recall rooms, treasuries, morgues; SMAUG councils). **The
user is not sure Lorecraft wants these.** Heavy social meta-layer that assumes a large,
competitive playerbase. Parking as _probably not_ unless the game grows a community that
actually forms groups and asks for shared identity/spaces. Revisit only then.

### Player-built world / housing / vehicles-as-property 🤔 (Tier 3, low priority)

EmpireMUD-style player-modified geography (roads, outposts, territorial claims), Discworld/
Materia-style housing and civic identity, and vehicles-as-owned-property (beyond the
already-shipped passenger transit) are all genuine differentiators in the wider MUD landscape,
but bigger commitments than Lorecraft's current scope:

- **Housing / player shops** — a social anchor (storage, customization, a place friends visit)
  and a natural extension of the shop system already built for NPCs. Defer until a social
  community exists that would use it — pairs naturally with player groups/parties below.
- **Player-modified geography** — claim parcels, structure templates, upkeep, reversible deltas.
  Large design surface (griefing, persistence cost); not pursued unless Lorecraft's scope
  shifts toward a sandbox-building game, which isn't the current direction.
- **Vehicles as ownable property** — beyond the ferry/rail/balloon transit lines already
  shipped, a player-owned boat/wagon. Interesting but low priority; the moving-room/
  `MobileRouteService` primitive would carry it if ever pursued.

### Player-run economy at scale 🚫

Auctions, player shops, clan banks, dynamic markets. Presupposes a busy economy Lorecraft
doesn't have. Not now; maybe never, depending on scale.

### Player groups / parties 🤔

Lighter-weight than guilds: temporary parties for shared travel or content. Could pair well
with the transit theme (board the ferry together). Worth considering _if_ co-op content
appears, without committing to the full guild apparatus. The lightest slice — a **`follow`
command** — was promoted to roadmap
[Sprint 47](roadmap.md#sprint-47--follow-command-social-movement) (2026-07-05).

### `report player <name>` moderation branch 🤔

The guided `report` wizard (category → title → detail) already shipped. The only remaining
piece: a **`report player <name>`** branch that asks what's being reported about that player and
records the *target* alongside the *filer* — needs a new `target_player_id` field (or companion
table) on `Issue`, plus a design decision on whether moderation reports need different
admin-visibility handling than ordinary bug/feedback reports. Small scope: one wizard branch +
one field + admin visibility.

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
| How deep is survival (fatigue/sleep/hunger)?            | Character-condition scope                                                          | Light/flavor, per-world toggle                                                                            |
| Skills: use-based vs. XP-based improvement?             | Progression feel                                                                   | Use-based (fits exploration)                                                                              |
| Attributes: minimal spread or none?                     | Character system                                                                   | Minimal, non-combat-framed                                                                                |
| PvP: soft opt-in vs. anything more punishing?           | Combat feel, gates the *Bounty / target marks* idea                                | Lean soft unless Lorecraft wants a darker RP tone                                                          |
| Scripting layer: Python / Lua / YAML-only?              | Builder extensibility                                                              | Hold; decide during combat                                                                                |
| Guilds/clans: in or out?                                | Social scope                                                                       | Leaning out                                                                                               |
| Engine/game-data split: when to act?                    | Repo structure, scripting design                                                   | Plan for it now; execute once scripting is decided or a 2nd world is wanted                               |
| Tutorial/character-creation: engine feature or content? | Onboarding design                                                                  | Content (scripted, per-world) — reuses dialogue/quest primitives, not new engine mechanism                |
| Currency model: single int or keyed quantity map?       | Trade ([Sprint 28](roadmap.md#sprint-28--trading--economy))                        | Keyed map — cheap now, expensive to retrofit                                                              |
| Player settings/preferences: engine feature?            | Accessibility, UX                                                                  | Yes — thread through the render layer early                                                               |

---

_Created 2026-07-03 from an architecture + MUD-comparison planning session. Update as ideas
are chosen (move to [`roadmap.md`](roadmap.md)) or explicitly dropped._
