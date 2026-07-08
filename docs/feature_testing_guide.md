---
kindle_doc_weaver: ignore
---

# Lorecraft Feature Testing Guide

**Purpose:** Comprehensive reference for testing all implemented gameplay features. Each feature includes:
- **What it is** — brief description and design purpose
- **What gameplay it enables** — player-facing impact
- **Manual testing** — step-by-step walkthroughs to verify behavior
- **Automated testing** — pytest patterns, test locations, golden-path scenarios
- **Edge cases** — corner cases and known gotchas to watch for
- **Verification checklist** — what to look for in each test

> **Last updated:** 2026-07-07, v0.46.2 (all features through Sprint 55)
> **Scope:** Tier 1 engine primitives + Tier 2 features (Sprints 1–55)
> **Coverage:** Foundation (Sprints 1–34), Performance & scaling (35–37), Content & UX (39–55)

---

## Table of Contents

1. [Foundation: Authentication & Session](#foundation-authentication--session)
2. [Foundation: Movement & Exploration](#foundation-movement--exploration)
3. [Foundation: Inventory & Equipment](#foundation-inventory--equipment)
4. [Foundation: Character Progression](#foundation-character-progression)
5. [Pillar 1: Exploration Features](#pillar-1-exploration-features)
6. [Pillar 2: Trading & Economy](#pillar-2-trading--economy)
7. [Pillar 3: Transit & Travel](#pillar-3-transit--travel)
8. [Pillar 4: NPCs, Dialogue & Quests](#pillar-4-npcs-dialogue--quests)
9. [Pillar 5: Social & Multiplayer](#pillar-5-social--multiplayer)
10. [World Events & Content](#world-events--content)
11. [Admin & Observability](#admin--observability)

---

## Foundation: Authentication & Session

### Feature: Player Authentication (Sprint 4)

**What it is:**
Password-based account creation and login with JWT token flow. Supports character creation, login verification, and session tokens for WebSocket connections.

**Gameplay it enables:**
- Persistent character ownership
- Private accounts (only you can enter your character)
- Multi-character support (one player, many characters)
- Session persistence (closing/reopening browser keeps you logged in)

**Manual Testing:**

1. **Create new character:**
   - Navigate to `/lobby`
   - Enter a character name (3–30 chars: letters, numbers, `-`, `_`)
   - Enter a password (any string)
   - Click "Create New Character"
   - **Expected:** Character created, dropped into village_square

2. **Login with correct password:**
   - At `/lobby`, click "Log In" tab
   - Enter exact character name and password
   - **Expected:** Logged in successfully, game page loads

3. **Login with wrong password:**
   - At `/lobby`, click "Log In" tab
   - Enter correct name, wrong password
   - **Expected:** Error message displayed, stays on lobby (400 error, NOT a redirect)

4. **Session persistence:**
   - Log in as a character
   - Refresh the page (`F5`)
   - **Expected:** Still logged in as same character, no re-login needed

5. **Logout and reconnect:**
   - Type `quit` in game
   - **Expected:** Returns to `/lobby`, session cleared
   - Log back in with same credentials
   - **Expected:** Resume in same location as before quit

**Automated Testing:**
- **Location:** `tests/e2e/test_auth_flows.py` (5 tests)
- **Test patterns:**
  - `test_create_character()` — create → game page
  - `test_login_correct_password()` — login → game page
  - `test_login_wrong_password()` — login error → 400, stay on lobby
  - `test_session_persists_on_reload()` — reload → same character
  - `test_unauthenticated_blocks_game_page()` — no auth → 401 on `/game`

- **Golden path scenario:**
  - `tests/simulation/scenarios/golden_path.json` — includes login as player-1

**Edge Cases:**
- Character name is case-sensitive (or case-insensitive? — verify current behavior)
- Password with special characters / spaces
- Very long names or passwords
- Multiple rapid login attempts
- Concurrent logins from two browsers (should both work; same player in two places)

**Verification Checklist:**
- [ ] JWT tokens issued correctly
- [ ] WebSocket tickets are single-use
- [ ] Session cookies persist across page reloads
- [ ] Wrong password rejects immediately (no partial state created)
- [ ] Concurrent sessions allowed (same player online in two rooms)

---

### Feature: Disconnect Handling (Sprint 13)

**What it is:**
Graceful handling of broken connections. Players stay "in-game" for a grace period (60s default) and can reconnect without losing position. Full reconnection resyncs the client state.

**Gameplay it enables:**
- Tolerance for brief network hiccups
- No harsh penalties for accidental disconnects
- Live updates resume immediately on reconnect

**Manual Testing:**

1. **Brief disconnect (within grace period):**
   - Log in as player-1
   - Close browser tab abruptly (or kill the network)
   - Within 30 seconds, reopen the server URL
   - Log back in as same character
   - **Expected:** Resume in exact same room, inventory unchanged, no state loss

2. **Slow reconnect (beyond grace period):**
   - Log in as player-1, move to a unique room
   - Wait 65+ seconds without sending commands
   - Reconnect by refreshing the page
   - **Expected:** Treated as a fresh login; may end up in the default spawn room or last saved location (verify current behavior)

3. **WebSocket reconnect:** (requires client dev tools or explicit socket drop)
   - Log in as player-1
   - Open browser dev console → `window.Lorecraft.debugDropSocket()`
   - **Expected:** Socket closes, auto-reconnects within 1–2 seconds
   - Verify status dot shows "connected" again
   - Send a command → works normally

**Automated Testing:**
- **Location:** `tests/e2e/test_reconnect.py` (WS reconnect flow)
- **Test patterns:**
  - Socket auto-reconnects after drop
  - Chat/state updates resume on reconnect
  - Multiple rapid reconnects stable

- **Integration tests:** `tests/integration/test_disconnect.py`
  - Grace-period expiry
  - Double-connect (same player logs in twice)

**Edge Cases:**
- Client sends command during reconnect window (should queue or retry)
- Graceful shutdown (server stops) during grace period
- Connection drops and reconnects repeatedly (flaky network)
- Grace period exact boundary (59s vs. 61s)

**Verification Checklist:**
- [ ] Player invisible to others during grace period
- [ ] Reconnect within grace period resumes exact state
- [ ] Reconnect after grace period treats as fresh login
- [ ] Pending deliveries (WS pushes) queued during downtime, flushed on reconnect
- [ ] `reconnect_sync` fires with `feed?since=` to backfill narrative

---

## Foundation: Movement & Exploration

### Feature: Navigation & Room Movement (Sprint 2)

**What it is:**
Player movement between rooms using directional commands (`go north`, `n`, etc.). Enforces exit-existence, locked-door checks, and hidden-exit discovery.

**Gameplay it enables:**
- Exploration of the world
- Navigation puzzles (locked doors, hidden exits)
- Transit between areas for trading/questing

**Manual Testing:**

1. **Basic movement (Ashmoore demo world):**
   - Start in village_square
   - Type `go east` → market_stalls
   - Type `west` → back to village_square
   - Type `north` → wandering_crow_inn
   - **Expected:** Each move succeeds, current location panel updates

2. **Invalid direction:**
   - In village_square, type `go northwest`
   - **Expected:** Error: "You can't go that way." (no exit in that direction)

3. **Locked door:**
   - From village_square, go `north` → `north` → `east` (Vault Hall)
   - Try `go east` without a key
   - **Expected:** Error: "The exit is locked; you need a key."
   - Take the "Good Key" from the vault
   - Type `unlock east`
   - Type `go east` → Inner Vault
   - **Expected:** Unlock succeeds, movement allowed

4. **Direction abbreviations:**
   - Test `n`, `s`, `e`, `w`, `ne`, `se`, `nw`, `sw`, `u`, `d`
   - **Expected:** All work as aliases for full directions

**Automated Testing:**
- **Location:** `tests/integration/test_movement.py`
- **Test patterns:**
  - Basic move between adjacent rooms
  - Invalid direction rejected
  - Locked/unlocked door checks
  - Hidden exit discovery (see below)
  - Terrain skill gating

- **Golden path:** `scenarios/golden_path.json` includes `go east` (market), `go west` (inn)

**Edge Cases:**
- Moving to a room that's deleted (in a live-reloading world)
- Chained movement in rapid succession (shouldn't overflow queue)
- Movement into a room with an event (puzzle, effect) occurring at same time
- Movement while encumbered (should add stamina cost but not block)

**Verification Checklist:**
- [ ] Movement in all 8 directions works
- [ ] Abbreviations (`n`, `ne`, etc.) work
- [ ] Locked door blocks movement until unlocked
- [ ] Wrong key doesn't unlock
- [ ] Exiting a room notifies others ("X leaves east.")
- [ ] Entering a room notifies others ("X arrives from the west.")

---

### Feature: Item Examination & Interaction (Sprint 5)

**What it is:**
Examine items in the room or inventory to read descriptions. Some items have verbs (`read altar`, `pull lever`) that trigger special actions.

**Gameplay it enables:**
- Reading item flavor text and learning item properties
- Discovering item purposes (what's it for?)
- Triggering context-specific actions (puzzle interaction, lore revelation)

**Manual Testing:**

1. **Examine a room item:**
   - In village_square, type `examine coin`
   - **Expected:** Displays full item description and value
   - Type `x coin` (shorter alias)
   - **Expected:** Same result

2. **Examine carried item:**
   - Take an item with `take coin`
   - Type `examine coin` (from inventory)
   - **Expected:** Shows description, carried status

3. **Context verb (read altar):**
   - From village_square, go `south` (past the creek) → Ruined Chapel
   - Type `read altar`
   - **Expected:** Displays altar inscription/lore (specific to the altar object)

4. **Examine armor:**
   - Go to Forge (`north` from inn)
   - Type `take helmet` then `examine helmet`
   - **Expected:** Shows slot, wearability, bonuses ("Equippable on head slot; worn")

**Automated Testing:**
- **Location:** `tests/integration/test_examine.py`
- **Test patterns:**
  - Examine room item by name
  - Examine carried item by name
  - Examine with disambiguation (multiple items with same name)
  - Examine non-existent item (error)
  - Context verbs fire correctly

**Edge Cases:**
- Item name with multiple words (`examine red apple`)
- Ambiguous item name (two items both called "key") → should show numbered list
- Examine while in dialogue (should be blocked or show context)
- Examine an item that just despawned

**Verification Checklist:**
- [ ] Item descriptions display correctly
- [ ] Item stats (value, weight, durability) shown
- [ ] Context verbs appear only when item is present
- [ ] Disambiguation prompt when name matches multiple items
- [ ] Error message clear when item not found

---

### Feature: Search & Hidden Exits (Sprint 25)

**What it is:**
Skill check (`perception`) to discover hidden exits that aren't shown in the room description. Once found, they stay visible to that player.

**Gameplay it enables:**
- Reward for high perception skill
- Discovery-based exploration (not just following written exits)
- Shortcuts and secrets in the world

**Manual Testing:**

1. **Search in a room with hidden exits:**
   - Go to a room known to have hidden exits (verify in world.yaml)
   - Type `search`
   - **Expected:** Roll perception check; if successful, discover hidden exit(es)
   - Type `look` → description now includes the newly-found exit
   - Move through it
   - **Expected:** Movement succeeds, new room visible

2. **Failed search:**
   - Search in a room with hidden exits but low perception skill
   - **Expected:** "You don't find anything hidden here this time."
   - Try again later (skill improves with use)

3. **Persistent discovery:**
   - Search and find a hidden exit in room A
   - Move away and return to room A
   - **Expected:** Exit still visible (not re-hidden)

**Automated Testing:**
- **Location:** `tests/integration/test_search.py`
- **Test patterns:**
  - Search roll succeeds/fails by perception vs. difficulty
  - Discovered exit becomes visible in room description
  - Discovered exit persists in player state
  - Movement through hidden exit works

**Edge Cases:**
- Multiple hidden exits in one room (should discover one per successful roll? or all at once?)
- Searching a room with no hidden exits (should give "found nothing" message)
- Fatigue affecting the perception check
- Searching a dark room (without light — can't see anything?)

**Verification Checklist:**
- [ ] Search uses player's perception skill
- [ ] Success rate increases with skill level
- [ ] Discovered exits added to player's room-state cache
- [ ] Exits remain visible on repeat visits
- [ ] Movement through hidden exit counts as normal movement (triggers movement events, fatigue, etc.)

---

### Feature: Celestial Cycles & Tides (Sprint 54)

**What it is:**
A persistent world clock with lunar cycles and tides that affect gameplay. Moon phase and tide display in the status bar; some areas/doors only accessible at specific lunar phases.

**Gameplay it enables:**
- Time-gated exploration (return at the right moon phase to progress)
- World immersion (clock/calendar visible to players)
- Asynchronous coordination (quest hints mention "wait for the full moon")

**Manual Testing:**

1. **Check current time:**
   - In any room, look at the status bar (top-right)
   - **Expected:** Shows current game hour/minute, moon phase, tide

2. **Moon-gated area (if available in Ashmoore):**
   - Find a room with a moon-gated exit (e.g., "Only accessible at full moon")
   - Try to move through it at wrong moon phase
   - **Expected:** Blocked with message: "You sense a barrier. Perhaps the time is not right."
   - Wait for (or skip to) the full moon via admin tools
   - Try again
   - **Expected:** Exit opens, movement allowed

3. **Tide-gated area:**
   - Find a causeway or similar room that's submerged at high tide
   - Check the tide status
   - At high tide, movement blocked; at low tide, allowed
   - **Expected:** Appropriate blocking message based on tide

4. **Time advancement:**
   - Type `sleep` in a bed/camp
   - Check status bar before and after
   - **Expected:** Hour advances, moon phase may cycle, tide changes

**Automated Testing:**
- **Location:** `tests/integration/test_celestial.py`
- **Test patterns:**
  - WorldClock advances time correctly
  - Moon phases cycle (new → waxing → full → waning → new)
  - Tide cycles (high → low → high)
  - Moon-gated exits block/open correctly
  - Tide-gated areas block/open correctly

- **Integration:** `tests/integration/test_worldclock.py`

**Edge Cases:**
- Crossing a moon-phase boundary during sleep
- Moving between rooms with different phase requirements (should check on entry)
- Jumping time forward via admin commands (should recalculate all phase-gated content)
- Interaction with weather (weather also uses the clock)

**Verification Checklist:**
- [ ] Moon phase displays in status bar
- [ ] Tide displays in status bar
- [ ] Moon-gated exits show barrier message
- [ ] Tide-gated areas show appropriate message
- [ ] Time advances after `sleep` command
- [ ] Phase checks use the correct timestamp (not stale)

---

## Foundation: Inventory & Equipment

### Feature: Item Management (Sprints 5, 16, 22–23)

**What it is:**
Core inventory system: taking/dropping items, carrying weight limits, and item durability. Items are stored as stacks with configurable carry capacity, encumbrance bands, and overload thresholds.

**Gameplay it enables:**
- Resource management (can't carry everything)
- Weight-based progression (heavier armor requires strength)
- Loss-on-death stakes (carried items dropped as loot)

**Manual Testing:**

1. **Take and drop items:**
   - Start in village_square
   - Type `take coin`
   - **Expected:** Item added to inventory
   - Type `inventory` → coin listed
   - Type `drop coin`
   - **Expected:** Item back in room, removed from inventory

2. **Take all:**
   - In a room with multiple items
   - Type `take all`
   - **Expected:** All takeable items added to inventory

3. **Quantity:**
   - Type `take 2 coin` (take 2 copies)
   - **Expected:** Stack of 2 coins in inventory, room still has coins (if unlimited)

4. **Encumbrance:**
   - Inventory panel shows "WEIGHT X / Y" (current / max)
   - Pick up heavier items until near capacity
   - **Expected:** Weight bar colors: green (light), amber (moderate), red (full)
   - Try to pick up another heavy item past overload
   - **Expected:** Error: "You can't carry any more weight."

5. **Burdened state:**
   - Fill inventory to > 75% capacity (burdened)
   - Type `go <direction>` repeatedly
   - **Expected:** Movement costs more stamina, messages show "You're weighed down."
   - Drop some items to lighten load
   - **Expected:** Movement stamina cost returns to normal

**Automated Testing:**
- **Location:** `tests/integration/test_inventory.py`
- **Test patterns:**
  - Take/drop operations update stacks
  - Overload gate on take
  - Encumbrance band calculation
  - Fatigue drain by weight band
  - Item instances track state correctly

**Edge Cases:**
- Item weight = 0 (should not affect encumbrance)
- Dropping items while overloaded (should always succeed, reducing weight)
- Picking up very heavy single item (heavier than max capacity) — should fail with clear message
- Taking items from a container (see Container feature)
- Picking up a bound item (see Bound Items below)

**Verification Checklist:**
- [ ] Weight UI shows current/max correctly
- [ ] Encumbrance band color changes with weight percentage
- [ ] Overload blocks `take` with clear message
- [ ] Movement fatigue increases with weight
- [ ] Drop always succeeds (even when overloaded)
- [ ] Weight persists after logout/login

---

### Feature: Equipment & Slots (Sprint 23)

**What it is:**
Wearing and wielding items: armor goes in slots (head, chest, legs, etc.), weapons in hand(s), light sources in hands. Equipped items grant passive bonuses and occupy slots.

**Gameplay it enables:**
- Character customization (which armor/weapons to equip?)
- Stat progression (better gear = stronger character)
- Light source management (need light to see in dark rooms)

**Manual Testing:**

1. **Wear armor:**
   - Go to Forge (`north` from inn)
   - Take the helmet: `take helmet`
   - Type `equipment` → helmet not listed yet
   - Type `wear helmet`
   - **Expected:** Helmet moved from inventory to "worn" list
   - Type `equipment` → helmet listed as worn on head
   - Check inventory → helmet no longer in loose inventory

2. **Equipment bonuses:**
   - Type `traits` before wearing
   - Wear the helmet
   - Type `traits` again
   - **Expected:** New trait visible if helmet grants one (e.g., "Armored")

3. **Remove armor:**
   - Type `remove helmet`
   - **Expected:** Helmet back in inventory, no longer worn
   - Type `equipment` → helmet gone from worn list

4. **Multiple slots:**
   - If available in world, take body armor + helmet
   - Wear both
   - **Expected:** Both occupy their respective slots, both show in `equipment`

5. **Duplicate slots (e.g., two hand slots):**
   - Take two weapons/tools
   - Wield both
   - Type `equipment` → both listed as wielded
   - **Expected:** Dual-wielding possible (or second item fails with "hand slot full")

**Automated Testing:**
- **Location:** `tests/e2e/test_panel_rendering.py` (P4.2 equipment test)
- **Test patterns:**
  - Wear/remove changes equipment panel
  - Wield/unwield works for weapons/tools
  - Slot conflicts rejected ("can't wear two helmets")
  - Equipping item grants its bonuses
  - Unequipping removes bonuses

- **Integration tests:** `tests/integration/test_equipment.py`

**Edge Cases:**
- Wearing/wielding items while encumbered (should still work — equipment slots are separate from carry capacity)
- Wearing an item that grants a trait, then removing it (trait should disappear unless from another source)
- Item that fits multiple slots (rare; verify slot-assignment logic)
- Picking up an item while a slot is full (should go to inventory if inventory room exists, else fail)

**Verification Checklist:**
- [ ] Wear/remove commands work on wearable items
- [ ] Wield/unwield commands work on wielded items
- [ ] Equipment panel shows all equipped items
- [ ] Equipped items grant their bonuses (traits, stat mods)
- [ ] Slot conflicts prevented (can't wear two helmets)
- [ ] Equipment persists after logout/login
- [ ] Removing equipment removes its bonuses

---

### Feature: Containers & Item Nesting (Sprint 23.3)

**What it is:**
Items can be containers holding other items. `open <container>`, `put <item> in <container>`, `take <item> from <container>`.

**Gameplay it enables:**
- Nested item organization (bag within bag)
- Quest stashes (find items hidden in a chest)
- Encumbrance puzzles (pack light items in a heavy container, vs. carrying them loose)

**Manual Testing:**

1. **Open and close container:**
   - Find a container (e.g., a chest or sack)
   - Type `open chest`
   - **Expected:** Container opens; `look` shows contents if visible
   - Type `close chest`
   - **Expected:** Container closes

2. **Put item in container:**
   - Have an item in inventory
   - Open a container
   - Type `put coin in chest`
   - **Expected:** Item moved from inventory to container
   - Type `inventory` → coin gone

3. **Take item from container:**
   - Type `take coin from chest`
   - **Expected:** Item moved from container to inventory
   - Type `inventory` → coin listed

4. **Container capacity:**
   - Open a container with limited capacity (e.g., 100 weight units)
   - Try to put very heavy items in it
   - **Expected:** Can fill up to capacity limit; excess rejected with "can't fit"

**Automated Testing:**
- **Location:** `tests/integration/test_containers.py`
- **Test patterns:**
  - Open/close container state changes
  - Put/take from container moves items
  - Container capacity enforced
  - Closing container removes contents from view
  - Nested containers (containers within containers) — if supported

**Edge Cases:**
- Taking from a closed container (should give error: "It's closed.")
- Putting an item in a full container (should fail gracefully)
- Container that's locked (bonus: treat same as locked door/chest)
- Taking all from a container: `take all from chest`
- Carrying a closed container (contents still consume weight? verify design)

**Verification Checklist:**
- [ ] Open/close toggle container state
- [ ] Put item into container moves it from inventory
- [ ] Take item from container moves it to inventory
- [ ] Container capacity is enforced
- [ ] Closed container blocks put/take operations
- [ ] Nesting works (container in container)

---

### Feature: Light Sources & Durability (Sprint 23.3)

**What it is:**
Light sources (lanterns, torches) emit light when equipped and lit. They have durability that decays over time. Dark rooms require lit light sources to see anything.

**Gameplay it enables:**
- Resource management (keep spare light sources)
- Exploration risk (deeper caves need fuel management)
- Atmosphere (dark areas feel dangerous/mysterious)

**Manual Testing:**

1. **Dark room without light:**
   - Find a dark room (verify `light_level=0` in world.yaml)
   - Try `look`
   - **Expected:** Error: "It's too dark to see." (or "You need light to see.")
   - Can't `take`, `examine`, etc. either

2. **Equip and light a source:**
   - Take a lantern/torch
   - Type `wield lantern` or `light lantern`
   - **Expected:** Lantern now equipped and lit
   - Go to a dark room
   - Type `look`
   - **Expected:** Room is visible, description shown

3. **Light source burning:**
   - Equip a lit lantern and check its durability
   - Wait several ticks (or verify in audit log)
   - Check durability again
   - **Expected:** Durability decreased slightly

4. **Light source fuel depletion:**
   - Check lantern durability (e.g., "3 / 10 fuel remaining")
   - Wait for fuel to reach 0
   - **Expected:** Light extinguishes automatically; dark room becomes dark again

5. **Extinguish and relight:**
   - Type `extinguish lantern`
   - **Expected:** Light goes out, lantern still in equipment but not lit
   - Type `light lantern` again
   - **Expected:** Light comes back on, durability continues burning

**Automated Testing:**
- **Location:** `tests/integration/test_light.py`
- **Test patterns:**
  - Dark room blocks look/examine without light
  - Lit light source allows sight in dark room
  - Light durability decays over time
  - Durability = 0 extinguishes light
  - Extinguish/light toggles lit state

**Edge Cases:**
- Multiple light sources (take maximum light, ignore others? — verify design)
- Light source that grants light but isn't in hand slot (e.g., "glowing gem" worn on belt) — should it still light the room?
- Light source goes out during a command (e.g., durability hits 0 mid-movement) — does movement still complete?
- Re-equipping a partially-burned light source (durability should remain)

**Verification Checklist:**
- [ ] Dark room blocks look without light source
- [ ] Lit light source allows sight in dark room
- [ ] Light durability decreases with activity
- [ ] Durability = 0 extinguishes light
- [ ] Extinguish removes light without destroying durability
- [ ] Re-light costs no durability
- [ ] Multiple light sources: only nearest/best counts (or all stack?)

---

## Foundation: Character Progression

### Feature: Skills & Leveling (Sprint 24)

**What it is:**
Character skills improve with practice. Skills include perception, survival, cartography, appraisal, bartering, lockpicking, and more. Each successful use increments skill XP, with an XP-to-level threshold.

**Gameplay it enables:**
- "Learn by doing" progression (no trainers, no quest trees)
- Skill-gated content (difficult terrain needs high survival, etc.)
- Long-term character development

**Manual Testing:**

1. **View current skills:**
   - Type `skills`
   - **Expected:** List of all skills with current level and XP progress
   - Example: "Perception 3 (45 XP toward level 4)"

2. **Perception check:**
   - Type `search` in a room with hidden exits
   - **Expected:** Check uses current perception level; higher level = better success rate
   - Repeat several times and monitor skill level
   - **Expected:** After several successful checks, perception XP increases

3. **Cartography skill:**
   - Open the minimap
   - **Expected:** Zoom shows rooms around you based on cartography level
   - Higher cartography reveals more distant rooms
   - Navigate around and check minimap
   - **Expected:** Cartography skill increases with exploration

4. **Bartering skill:**
   - Talk to a shop NPC and `buy` / `sell`
   - Check skills before/after
   - **Expected:** Bartering skill increases
   - Check final price
   - **Expected:** As bartering rises, discounts increase (prices improve)

5. **Lockpicking skill:**
   - Try unlocking a difficult lock (`unlock <direction>`)
   - **Expected:** Difficult locks might fail; as skill improves, success rate goes up
   - Repeat and monitor lockpicking skill XP

**Automated Testing:**
- **Location:** `tests/integration/test_skills.py`
- **Test patterns:**
  - Skill XP increments on successful skill checks
  - XP accumulates toward next level
  - Level threshold triggers promotion
  - Skill affects check DC (harder with low skill)
  - Skill persists after logout/login

**Edge Cases:**
- Skill cap (is there a max level? verify design)
- Skill XP overflow (what happens at next level after promotion?)
- Multiple sources of same skill bonus (trait + equipment + aura) — should they stack?
- Skill decay (do unused skills decrease? — probably not in current design)

**Verification Checklist:**
- [ ] `skills` command lists all skills with XP/level
- [ ] Skill checks succeed more often with higher skill
- [ ] Successful skill use increments XP
- [ ] XP accumulates and triggers level-up
- [ ] Skills persist across sessions
- [ ] Skill bonuses from equipment stack correctly

---

### Feature: Traits & Status Effects (Sprint 19)

**What it is:**
Passive bonuses and penalties applied to the character. Traits come from equipment, temporary effects, or background. Status effects (burdened, cold, etc.) indicate character condition.

**Gameplay it enables:**
- Visible character state (players know what bonuses they have)
- Condition-based gameplay (can't do X while exhausted)
- Equipment-driven identity (wearing certain gear gives certain traits)

**Manual Testing:**

1. **View active traits:**
   - Type `traits`
   - **Expected:** List of all active traits and their sources
   - Example: "Armored (from Iron Helmet), Cautious (from trait), Weary (temporary, 2 min remaining)"

2. **Equipment grants trait:**
   - Wear a piece of armor that grants a trait (e.g., helmet grants "Armored")
   - Type `traits`
   - **Expected:** Trait appears with source "Iron Helmet"
   - Remove the armor
   - **Expected:** Trait disappears

3. **Status effects:**
   - Get to low stamina (use `search` repeatedly without rest)
   - Type `traits`
   - **Expected:** "Weary" or "Exhausted" appears as a trait
   - Rest or sleep
   - **Expected:** Status effect disappears, stamina recovers

4. **Marks grant traits:**
   - Earn a mark that grants a boon/trait (e.g., "Mark of the Far Strider grants +5 carry capacity")
   - Type `traits`
   - **Expected:** See the trait in the list

5. **Multiple trait sources:**
   - Wear equipment + earn a mark + get a status effect
   - Type `traits`
   - **Expected:** All traits listed with their sources
   - Modifiers should stack correctly

**Automated Testing:**
- **Location:** `tests/integration/test_traits.py`
- **Test patterns:**
  - Equipment grants/removes traits on wear/remove
  - Active effects add traits
  - Traits expire when effects expire
  - `traits` command lists all with sources
  - Trait modifiers stack correctly

**Edge Cases:**
- Duplicate traits from multiple sources (should stack or merge? — verify design)
- Trait that conflicts with another (e.g., "Warm" + "Cold" — how does engine handle?)
- Temporary effect expires mid-command (e.g., "Haste" wears off while moving)
- Trait from a mark that you lose (mark unearned somehow? — probably doesn't happen)

**Verification Checklist:**
- [ ] `traits` command displays all active traits
- [ ] Each trait shows its source (equipment, effect, mark, etc.)
- [ ] Equipment traits grant/revoke on wear/remove
- [ ] Effect traits show duration remaining (if temporary)
- [ ] Trait modifiers correctly affect stats/skills
- [ ] Traits persist across session boundaries

---

### Feature: Reputation & Standing (Sprint 24)

**What it is:**
Relationship system with NPCs and factions. Standing affects prices, dialogue options, and quest availability.

**Gameplay it enables:**
- NPC relationships that evolve over time
- Better prices from liked NPCs
- Locked dialogue/quests behind reputation thresholds

**Manual Testing:**

1. **Check reputation:**
   - Type `reputation`
   - **Expected:** List of NPCs/factions and standing (e.g., "Mira (Neutral)", "Merchant's Guild (Friendly)")

2. **Improve standing:**
   - Complete a quest for an NPC (or accept a favor)
   - Type `reputation`
   - **Expected:** Standing with that NPC improved (e.g., "Friendly" → "Trusted")
   - Repeat with different NPCs

3. **Better prices from allies:**
   - Note the price of an item from a shop NPC
   - Do something to improve standing with them
   - Check the price again
   - **Expected:** Price is lower (or higher if reputation went down)

4. **Unlock dialogue:**
   - Talk to an NPC with low reputation
   - Certain dialogue options might be missing
   - Improve standing with that NPC
   - Talk again
   - **Expected:** New dialogue options appear (e.g., "What do you know about X?")

**Automated Testing:**
- **Location:** `tests/integration/test_reputation.py`
- **Test patterns:**
  - Standing starts at neutral
  - Completing quests/tasks improves standing
  - Standing affects shop prices
  - Standing gates dialogue options
  - Standing persists across sessions

**Edge Cases:**
- Standing that goes negative (hostile, enemy status) — what happens? (attacks? trading blocked?)
- Multiple characters with different standing with same NPC (possible; they're separate)
- Reputation that can't be improved (e.g., starting at max)
- Faction reputation vs. individual NPC reputation (do they interact?)

**Verification Checklist:**
- [ ] `reputation` command shows standing with all NPCs/factions
- [ ] Standing changes with quest completion
- [ ] Shop prices adjust based on standing
- [ ] Dialogue gates based on standing
- [ ] Standing persists across sessions
- [ ] Hostile standing prevents/penalizes trading

---

## Pillar 1: Exploration Features

### Feature: Journal & Discoveries (Sprint 25)

**What it is:**
Persistent log of places visited, NPCs met, items discovered, and active quests. Doubles as the game's in-world encyclopedia.

**Gameplay it enables:**
- Track which NPCs you've encountered
- Remember quest goals without reading them again
- See what items you've found (discovery journal)
- Read lore hints about encountered NPCs/items

**Manual Testing:**

1. **View journal:**
   - Type `journal`
   - **Expected:** Shows visited rooms, met NPCs, discovered items, active quests, learned lore

2. **Record visit:**
   - Move to a new room
   - Type `journal`
   - **Expected:** That room now listed under "Places Visited" with a brief description

3. **Record NPC met:**
   - Talk to an NPC (any dialogue option)
   - Type `journal`
   - **Expected:** NPC listed under "People Met" with optional lore snippet

4. **Record item discovered:**
   - Pick up or examine a new item
   - Type `journal`
   - **Expected:** Item listed under "Items Discovered"

5. **Quests in journal:**
   - Accept a quest from an NPC
   - Type `journal`
   - **Expected:** Active quest listed with current step description
   - Complete a step
   - **Expected:** Journal updates with new step

**Automated Testing:**
- **Location:** `tests/integration/test_journal.py`
- **Test patterns:**
  - Visiting a room records it in journal
  - Talking to NPC records in journal
  - Examining/taking item records discovery
  - Quest progress updates journal
  - Journal persists across sessions
  - Journal is read-only (can't edit entries)

- **Integration test:** `tests/integration/test_discovery.py`

**Edge Cases:**
- Visiting same room multiple times (should record once, or update last-visited date?)
- Journal reaches max entries (pagination needed?)
- Lore that's locked behind quest progress (show spoilers or hide?)
- Re-encountering an NPC (should journal show multiple meetings? or update single entry?)

**Verification Checklist:**
- [ ] `journal` command displays all sections (places, people, items, quests, lore)
- [ ] Visiting a new room adds to journal
- [ ] Talking to NPC adds to journal
- [ ] Taking/examining item adds to discoveries
- [ ] Quest progress updates journal
- [ ] Journal entry updates on re-visit (last-visited date changes?)
- [ ] Journal persists across logout/login

---

### Feature: Marks / Attunements (Sprint 53)

**What it is:**
Named badges earned by discovery (visiting places, meeting NPCs, finding items, learning lore). Some marks grant passive boons. Some are hidden until earned.

**Gameplay it enables:**
- Achievement system (discoverable goals)
- Passive progression track (marks instead of combat XP)
- Exploration incentive (find the hidden marks)
- Character identity (which marks have you earned?)

**Manual Testing:**

1. **Earn a mark:**
   - Fulfill a mark's criteria (e.g., visit 10 rooms, meet 5 NPCs, find 5 items)
   - **Expected:** Message: "You have earned Mark of the [Title]!"
   - Type `marks`
   - **Expected:** Earned mark listed with description

2. **Mark with boon:**
   - Earn a mark that grants a boon (e.g., "+5 carry capacity")
   - Type `traits`
   - **Expected:** The boon appears in traits, source shows mark name
   - Type `marks`
   - **Expected:** Mark shows the boon description

3. **Hidden mark:**
   - Type `marks`
   - **Expected:** Shows earned marks + "??? — undiscovered" lines (count of hidden marks, not details)
   - Earn the hidden mark by fulfilling its criteria
   - **Expected:** Mark reveals with name and description

4. **Mark hints:**
   - Type `help marks` (if there's help text)
   - **Expected:** General info about marks and how to earn them

**Automated Testing:**
- **Location:** `tests/integration/test_marks.py`
- **Test patterns:**
  - Mark awarded when criteria met
  - Mark state persists (earned marks don't reset)
  - Mark boons appear in traits
  - Hidden marks show as "???" until earned
  - Multiple marks can be earned
  - Mark criteria evaluated on journal events (moved, talked, took item, etc.)

- **Ashmoore content:** `world_content/marks.yaml` has example marks

**Edge Cases:**
- Mark criteria that can't be met anymore (deleted room/NPC)
- Earning a mark while offline (should award on next login)
- Mark criteria with time constraints (e.g., "earned at full moon only") — how often are criteria checked?
- Overlapping criteria (two marks with similar goals; can earn both?)

**Verification Checklist:**
- [ ] `marks` command shows earned + hidden marks
- [ ] Mark awarded when criteria met
- [ ] Mark boon appears in traits
- [ ] Mark description shows in `marks` command
- [ ] Hidden marks display as "???" until earned
- [ ] Marks persist across sessions
- [ ] Multiple marks can be earned simultaneously

---

### Feature: Scavenger Hunts (Sprint 48)

**What it is:**
Timed world events where a set of themed items is scattered across rooms. Players hunt them for a reward (coins, a collectible mark, lore).

**Gameplay it enables:**
- Recurring exploration events (exploration incentive)
- Coordination opportunity (multiple players can collaborate)
- Reward loop (find all → claim prize)

**Manual Testing:**

1. **Check active hunts:**
   - Type `hunts`
   - **Expected:** Lists active hunts with: hunt name, count of items found, count of items total
   - Example: "Harvest Trinket Hunt: 0 / 3 found"

2. **Hunt an item:**
   - In `hunts` output, see that a hunt is active
   - Navigate to rooms where hunt items spawn (noted in world.yaml or hunt definition)
   - Type `look` and search for hunt items
   - Type `take <hunt-item>`
   - **Expected:** Item picked up, hunt progress increments
   - Type `hunts`
   - **Expected:** Count updated (e.g., "1 / 3")

3. **Complete hunt:**
   - Take all items in the hunt
   - **Expected:** Final item triggers completion
   - Message: "You have completed the Harvest Trinket Hunt! Reward: [coins/mark/lore]"
   - Check inventory for coins, or marks for new mark
   - **Expected:** Reward claimed

4. **Scheduled hunt:**
   - Hunt runs on a schedule (e.g., every Monday)
   - Wait for hunt to close (or admin-trigger closure)
   - **Expected:** Hunt items despawn, hunt no longer active in `hunts`
   - Repeat on next scheduled date
   - **Expected:** Hunt opens again with fresh items

**Automated Testing:**
- **Location:** `tests/integration/test_hunts.py`
- **Test patterns:**
  - Hunt opens on schedule
  - Hunt items spawn in designated rooms
  - Taking hunt item increments progress
  - Completing hunt awards reward (coins/mark/lore)
  - Hunt closes and despawns items
  - Hunt can be completed by multiple players independently

- **Ashmoore content:** `world_content/hunts.yaml` has example hunt ("Harvest Trinket Hunt")

**Edge Cases:**
- Hunt item already taken by another player (inventory finite? — probably not; items respawn per room)
- Player completes hunt, then disconnects before reward awarded (race condition?)
- Hunt closes while player is in middle of completion (items despawn mid-hunt?)
- Player joins hunt late (can they still complete if some items already taken? — yes, items should respawn)

**Verification Checklist:**
- [ ] `hunts` command lists active hunts with progress
- [ ] Hunt items spawn in correct rooms
- [ ] Taking hunt item updates player progress
- [ ] Completion awards coins/mark/lore
- [ ] Hunt closes and items despawn on schedule
- [ ] Multiple players can complete same hunt independently
- [ ] Hunt can be triggered manually by admin

---

## Pillar 2: Trading & Economy

### Feature: Currency & Banking (Sprint 20, 28)

**What it is:**
Two separate money pools: carried coins (spent anywhere, at risk) and banked coins (safe, only accessible at bank branches).

**Gameplay it enables:**
- Strategic risk (how much to carry vs. bank for safety?)
- Death penalty (lose carried coins on death, keep banked coins)
- Trade routes (move money between banks safely)

**Manual Testing:**

1. **Carry coins:**
   - Pick up coins from the world or earn them from a quest
   - Type `balance`
   - **Expected:** Shows carried coins and banked balance
   - Example: "Carried: 50 coins · Banked: 0 coins"

2. **Deposit at bank:**
   - Find a bank NPC/room (if available in Ashmoore)
   - Type `deposit 30`
   - **Expected:** 30 coins moved from carried to banked
   - Type `balance`
   - **Expected:** Carried: 20, Banked: 30

3. **Withdraw from bank:**
   - Type `withdraw 20`
   - **Expected:** 20 coins moved from banked to carried
   - Type `balance`
   - **Expected:** Carried: 40, Banked: 10

4. **Insufficient balance:**
   - Type `deposit 100` with only 40 carried
   - **Expected:** Error: "You don't have that many coins."

5. **Carry safety:**
   - Die (or test via admin) and drop as corpse loot
   - **Expected:** Carried coins drop; banked coins are safe
   - Loot the corpse
   - **Expected:** Carried coins recovered; banked intact

**Automated Testing:**
- **Location:** `tests/integration/test_banking.py`
- **Test patterns:**
  - Deposit moves coins from carried to banked
  - Withdraw moves coins from banked to carried
  - Cannot deposit more than carried
  - Cannot withdraw more than banked
  - Coins persist across sessions
  - Death drops carried coins only (banked safe)

**Edge Cases:**
- Deposit/withdraw with 0 coins
- Try to deposit negative amount (exploit?)
- Rapid succession of deposits/withdraws (no race conditions?)
- Bank that runs out of cash (not a feature yet)
- Transferring coins between players (see Player-to-Player Trading)

**Verification Checklist:**
- [ ] `balance` command shows carried and banked
- [ ] `deposit` and `withdraw` move coins correctly
- [ ] Cannot over-withdraw or over-deposit
- [ ] Coins persist across sessions
- [ ] Banked coins are safe on death
- [ ] Carried coins are lost on death

---

### Feature: NPC Shops & Selling (Sprint 28)

**What it is:**
NPCs can run shops, buying and selling items at prices derived from base value × quality × region × skill modifiers. Shop stock is finite and restocks on a schedule.

**Gameplay it enables:**
- Economy participation (earn coins by selling items)
- Progression through trade (low-end items → better items → profit)
- Regional trade routes (buy cheap here, sell high there)

**Manual Testing:**

1. **View shop stock:**
   - Find an NPC with a shop (e.g., merchant in the market)
   - Type `list` or `shop`
   - **Expected:** Shows available items and buy prices
   - Example: "Shortbread (2 coins), Iron Pot (15 coins), Wool Cloak (40 coins)"

2. **Buy an item:**
   - Type `buy shortbread`
   - **Expected:** Coins deducted from balance, item added to inventory
   - Check balance before and after
   - **Expected:** Coins decreased by purchase price

3. **Sell an item:**
   - Carry an item the shop will buy
   - Type `sell <item>`
   - **Expected:** Coins added, item removed from inventory
   - Example: "The merchant offers 8 coins. [Accept/Decline]"
   - Accept
   - **Expected:** Coins received, item gone

4. **Shop stock finite:**
   - Buy an item multiple times
   - **Expected:** After enough purchases, stock runs out ("Out of stock")
   - Wait for restock timer (or advance game clock)
   - **Expected:** Item back in stock

5. **Bartering discount:**
   - Check an item price with low bartering skill
   - Improve bartering skill (buy/sell more)
   - Check same item price
   - **Expected:** Price is slightly better (lower for buying, higher for selling)

6. **Reputation discount:**
   - Note item price with neutral reputation
   - Improve reputation with shop NPC
   - Check price again
   - **Expected:** Price improves

**Automated Testing:**
- **Location:** `tests/integration/test_shops.py`
- **Test patterns:**
  - `list` command shows shop stock with prices
  - `buy` deducts coins and adds item
  - `sell` adds coins and removes item
  - Shop stock decrements on sale
  - Shop won't buy non-tradeable items
  - Bartering skill affects price (negotiation discount)
  - Reputation affects price
  - Stock restocks on schedule

- **Integration test:** `tests/integration/test_economy.py` (pricing formulas)

**Edge Cases:**
- Buying item with insufficient coins (should fail with "You can't afford that.")
- Selling bound item (should fail: "That item is bound to you.")
- Selling item shop doesn't buy (should fail: "I don't buy that kind of thing.")
- Shop runs out of cash (inventory design not yet done; shops may have unlimited cash for v1)
- Buying/selling while encumbered (weight gates take, not buy)
- Quality modifiers on items (common vs. legendary same item should have different prices)

**Verification Checklist:**
- [ ] `list`/`shop` command shows current stock with prices
- [ ] `buy` transaction deducts coins, adds item
- [ ] `sell` transaction adds coins, removes item
- [ ] Shop won't buy soulbound/bound items
- [ ] Shop won't buy items outside its category list
- [ ] Shop stock is finite and restocks
- [ ] Bartering skill provides discount
- [ ] Reputation provides discount

---

### Feature: Player-to-Player Trading (Sprint 28)

**What it is:**
Two players can exchange items and coins peer-to-peer. Both sides pledge their goods, and either side can accept to finalize the trade. Trade validates at accept time, so no race conditions (item dropped, coins spent mid-trade).

**Gameplay it enables:**
- Direct player economy (not just shops)
- Cooperation mechanic (trading favors, splitting loot)
- Risk management (examine what you're getting before accepting)

**Manual Testing:**

1. **Initiate trade:**
   - Two players in same room
   - Player A: `offer sword to Bob`
   - **Expected:** Bob sees notification: "[Alice] offers you a sword."

2. **Accept pledge:**
   - Bob: `accept` (or he can counter-offer first)
   - **Expected:** Trade accepted, items exchanged
   - Alice: check inventory → sword gone, any reciprocal items gained
   - Bob: check inventory → sword gained

3. **Counter-offer:**
   - Alice: `offer sword to Bob`
   - Bob: `offer coins to Alice` (without accepting yet)
   - Alice: sees Bob's counter, can accept or counter again
   - **Expected:** Both sides can keep offering until satisfied

4. **Decline trade:**
   - Alice: `offer sword to Bob`
   - Bob: `decline`
   - **Expected:** Trade cancelled, offers reset
   - Alice: `offer sword to Bob` again to restart

5. **Trade validation:**
   - Alice: `offer sword to Bob`
   - Bob: accepts
   - Meanwhile, Alice drops the sword accidentally
   - **Expected:** Trade revalidates at accept time; Alice doesn't have sword anymore
   - Trade fails: "You no longer have a sword."

**Automated Testing:**
- **Location:** `tests/integration/test_player_trading.py`
- **Test patterns:**
  - Two players exchange items successfully
  - Counter-offers work
  - Trade revalidates at accept time
  - Missing item/coins at accept time cancels trade
   - Soulbound items can't be traded
  - Both sides see confirmation

- **E2E test:** `tests/e2e/test_gameplay_flows.py` could include player-trade scenario

**Edge Cases:**
- Trade between player and NPC (not supported — NPCs use `buy`/`sell`)
- Trading soulbound item (should fail: "You can't trade that item.")
- One player leaves room mid-trade (trade cancelled?)
- One player logs out mid-trade (trade cancelled?)
- Offering same item twice in one trade (should work; player has two)
- Concurrent trades with same player (multiple pending trades?)

**Verification Checklist:**
- [ ] `offer` command pledges item/coins
- [ ] Both sides see pending trade
- [ ] `accept` finalizes trade
- [ ] `decline` cancels trade
- [ ] Counter-offers work
- [ ] Trade revalidates at accept (catches race conditions)
- [ ] Soulbound items can't be traded
- [ ] Both sides receive their items

---

## Pillar 3: Transit & Travel

### Feature: Transit Routes & Boarding (Sprint 29)

**What it is:**
Vehicles (ferries, trains, balloons) move on schedules between fixed stops. Players board at stations, ride inside the vehicle room, and disembark at stops.

**Gameplay it enables:**
- Networked world (moving between distant areas costs time/money)
- Schedule-based gameplay (miss a departure, wait for next one)
- Social travel (other players visible while traveling)
- Trade network foundation (ferries connect commerce hubs)

**Manual Testing:**

1. **Check schedule:**
   - Find a transit stop (e.g., ferry dock)
   - Type `schedule` or `timetable`
   - **Expected:** Lists vehicle name, route stops, current position
   - Example: "Coastal Ferry: Village Dock → Market Wharf → Lighthouse Rock → back. Currently at Village Dock. Next departure in 5 minutes."

2. **Board vehicle:**
   - Type `board`
   - **Expected:** Enters vehicle room (internal space), can see other passengers
   - Type `look`
   - **Expected:** Shows vehicle interior description and passenger list

3. **Vehicle departure:**
   - Board the ferry
   - Wait for departure
   - **Expected:** Message: "The ferry begins moving..." Room shifts to show in-transit state
   - Can still move within the vehicle room (? or locked during transit?)

4. **Arrival at next stop:**
   - Vehicle reaches a stop
   - **Expected:** Message: "The ferry arrives at Market Wharf." Status bar updates

5. **Disembark:**
   - Type `disembark` or `leave`
   - **Expected:** Exits vehicle, now in the stop room
   - Type `look`
   - **Expected:** Shows stop room (not inside vehicle anymore)

6. **Miss a departure:**
   - Check `schedule`, see ferry is leaving soon
   - Don't board in time
   - **Expected:** Vehicle leaves without you
   - Next departure appears on schedule

7. **Ticket requirement:**
   - If ferry requires tickets: board without ticket
   - **Expected:** Error: "You need a ticket to board."
   - Acquire a ticket (buy from shop, find in world, etc.)
   - Board again
   - **Expected:** Boarding succeeds

**Automated Testing:**
- **Location:** `tests/integration/test_transit.py`
- **Test patterns:**
  - `schedule` shows current vehicle position and next departure
  - `board` enters vehicle room
  - Vehicle moves on schedule
  - `disembark` exits to stop room
  - Ticket requirement enforced
  - Vehicle room contains current passengers
  - Missing a departure updates schedule

- **Simulation test:** `tests/simulation/test_load.py` includes transit boarding

**Edge Cases:**
- Boarding while vehicle is mid-route (should fail: "The ferry is not at a station.")
- Disembarking while in-transit (should fail: "The ferry is moving; you can't leave now.")
- Ticket is consumed on boarding (one-time use)
- Ticket is a pass (reusable for many trips)
- Staying on vehicle through a full loop (multiple round-trips)
- Other player leaves room while you're boarding (should see them in vehicle)

**Verification Checklist:**
- [ ] `schedule` shows route, stops, and current position
- [ ] `board` only works when vehicle is docked
- [ ] Vehicle room is accessible while aboard
- [ ] Vehicle departs on schedule
- [ ] `disembark` only works when docked
- [ ] Passengers remain in vehicle room during transit
- [ ] Ticket requirement enforced
- [ ] Other players visible while traveling together

---

### Feature: Weather Effects on Transit (Sprint 44, 29)

**What it is:**
Harsh weather (storms, blizzards, fog) can ground or delay vehicles. Some vehicles are immune to weather.

**Gameplay it enables:**
- Weather-driven consequences (plan travel around weather)
- Character survival mechanics (weather is a hazard, not just flavor)

**Manual Testing:**

1. **Check weather:**
   - Type `weather` (if available) or check status bar
   - **Expected:** Current weather (clear, rainy, stormy, etc.)

2. **Weather-sensitive vehicle:**
   - Check schedule for ferry (marked as weather-sensitive)
   - **Expected:** If clear weather, normal schedule
   - Advance game clock to storm
   - Check schedule again
   - **Expected:** Ferry delayed or grounded ("Ferry delayed by heavy storms. Next departure: in 20 minutes.")

3. **Weather-immune vehicle:**
   - Check rail line schedule (usually immune)
   - **Expected:** Operates on time regardless of weather

4. **Boarding during delay:**
   - Wait for delayed departure
   - Attempt to board
   - **Expected:** If vehicle is grounded, can't board ("The ferry won't depart in this weather.")

**Automated Testing:**
- **Location:** `tests/integration/test_weather_transit.py`
- **Test patterns:**
  - Harsh weather triggers vehicle delay
  - Delay extends departure time
  - Grounded vehicles can't be boarded
  - Weather-immune vehicles unaffected
  - Weather clears, vehicle resumes schedule

**Edge Cases:**
- Weather changes mid-transit (vehicle in route when storm starts) — what happens? (completes route as-is, next departure affected?)
- Ticket expires during weather delay (holder can't board later? — probably not a real issue)
- Multiple vehicles at same stop; one grounded, one immune (can board the immune one)

**Verification Checklist:**
- [ ] Weather status visible in schedule
- [ ] Weather-sensitive vehicles delay in harsh weather
- [ ] Weather-immune vehicles run on schedule
- [ ] Boarding blocked for grounded vehicles
- [ ] Schedule updates reflect weather status

---

## Pillar 4: NPCs, Dialogue & Quests

### Feature: NPC Dialogue Trees (Sprint 10, 30)

**What it is:**
NPCs have dialogue trees with multiple choice branches. Dialogue can have conditions (reputation, quest state, flags) that gate certain options. Dialogue triggers side-effects (quest start, reputation change, item give).

**Gameplay it enables:**
- Character discovery (learn about the world from NPCs)
- Narrative branching (choices matter)
- Quest hooks (accept quests via dialogue)
- Social progression (dialogue unlocks with reputation)

**Manual Testing:**

1. **Start conversation:**
   - Talk to an NPC: `talk mira`
   - **Expected:** Dialogue overlay appears with NPC's opening line and numbered choices

2. **Choose response:**
   - Dialogue shows: "What would you like to know?"
   - Options: "(1) Tell me about yourself (2) Any news? (3) Goodbye"
   - Type `1` or click button
   - **Expected:** NPC responds, new choices appear

3. **Dialogue branching:**
   - Follow dialogue tree, making different choices
   - **Expected:** Each choice leads to different NPC response and new options
   - Choose different paths and see different outcomes

4. **Dialogue side-effect (quest start):**
   - During dialogue, choose "Any news around town?"
   - **Expected:** Quest starts, message: "New quest: Investigate the Lights"
   - Check `quests` panel
   - **Expected:** Quest listed with current step

5. **Conditional dialogue:**
   - Talk to an NPC with low reputation
   - Certain options might be missing (greyed out or absent)
   - Improve reputation with that NPC
   - Talk again
   - **Expected:** New options available (e.g., "Tell me a secret")

6. **Exit conversation:**
   - Type `bye` or `goodbye`
   - **Expected:** Dialogue closes, back to normal game

7. **Dialogue with flags:**
   - Accept a quest that sets a flag ("lights_investigated = true")
   - Complete the objective
   - Talk to the quest-giver again
   - **Expected:** Different dialogue path (quest-complete path) available

**Automated Testing:**
- **Location:** `tests/e2e/test_gameplay_flows.py` (P3.2 dialogue traversal)
- **Test patterns:**
  - Dialogue starts and displays NPC line + choices
  - Choosing an option triggers next dialogue step
  - Dialogue side-effects execute (quest start, reputation change)
  - Conditional dialogue branches correctly
  - Dialogue persists across room movement? (probably closes)

- **Integration tests:** `tests/integration/test_dialogue.py`

**Edge Cases:**
- Dialogue that doesn't end (infinite loop) — should warn
- Dialogue choice that's impossible (condition was true, now false) — skip or error?
- NPC who only has dialogue under conditions (can talk to them, but no options) — show "They have nothing to say."
- Dialogue that gives an item, but inventory is full (item queued? or given on quest-complete?)
- Rapid-fire dialogue choices (shouldn't be possible with current UI, but check)

**Verification Checklist:**
- [ ] NPC dialogue displays and shows choices
- [ ] Each choice triggers correct response
- [ ] Dialogue branches lead to different outcomes
- [ ] Dialogue side-effects execute (quest/reputation/flags)
- [ ] Conditional dialogue gates correctly
- [ ] `bye` closes dialogue overlay
- [ ] Other players don't see your dialogue (private)

---

### Feature: Quests & Quest Progress (Sprint 10, 30)

**What it is:**
Named tasks with multiple steps. Quests track progress, update on key events, and can have multiple endings (success/failure). Quest state persists in player flags and a quest-progress table.

**Gameplay it enables:**
- Main story hooks (multi-step objectives)
- Repeatable activities (daily/weekly quests?)
- Non-linear progression (choose which quests to do)

**Manual Testing:**

1. **Accept quest:**
   - Talk to Mira in the Wandering Crow Inn
   - Choose "Any news around town?"
   - **Expected:** Quest accepted: "Investigate the Lights"
   - Quests panel shows quest with step 1 description

2. **Track progress:**
   - Follow quest steps as described in panel
   - (Varies by quest; "Investigate the Lights" has you visit specific rooms)
   - Check Quests panel frequently
   - **Expected:** As you complete steps, panel updates to show next step

3. **Complete quest:**
   - Complete final step
   - **Expected:** Quest completion message and reward (coins, items, reputation)
   - Quests panel removes completed quest
   - `journal` marks quest as "completed"

4. **Failed quest:**
   - If quest can fail (time limit, wrong choices): trigger failure condition
   - **Expected:** Quest marked failed, penalty applied (reputation loss, etc.)
   - Quests panel removes failed quest

5. **Multiple quests:**
   - Accept 2–3 quests from different NPCs
   - Quests panel shows all active quests
   - **Expected:** Can toggle between viewing different quest steps

6. **Quest with choice:**
   - If a quest has multiple solutions (e.g., peaceful vs. hostile path): choose one
   - **Expected:** Quest progresses along chosen path
   - Choose different path on replay with different character
   - **Expected:** Different outcome/reward

**Automated Testing:**
- **Location:** `tests/integration/test_quests.py`
- **Test patterns:**
  - Quest starts with first step
  - Quest updates on expected condition (visited room, talked to NPC, took item)
  - Quest completes and awards reward
  - Quest can fail on condition
  - Multiple quests tracked independently
  - Quest state persists across sessions
  - Quest with choices branches correctly

**Edge Cases:**
- Abandoning a quest (command to drop it? probably not implemented yet)
- Quest completion event triggers, but player misses the notification
- Quest that requires an item, but item was traded away (quest still resolvable? or soft-lock?)
- Repeatable quest (can do it again?) — probably not in v1
- Timed quest (must complete within X hours) — probably not in v1

**Verification Checklist:**
- [ ] `quests` panel shows all active quests
- [ ] Each quest shows current step description
- [ ] Conditions properly trigger quest progression
- [ ] Quest completion awards correct reward
- [ ] Quest failure marks quest as failed
- [ ] Multiple quests don't interfere with each other
- [ ] Quest state persists across sessions
- [ ] Choice-based quests branch correctly

---

## Pillar 5: Social & Multiplayer

### Feature: Chat & Messaging (Sprint 45, 52)

**What it is:**
Multiple chat channels with different scopes: `say` (room-local), `tell` (player-to-player), and topic channels (global, e.g., `newbie` for new players). Each channel is color-coded and can be muted individually.

**Gameplay it enables:**
- Social coordination (talk to group in-room)
- Private messages (one-on-one help)
- Community channels (newbie help, trading post, etc.)

**Manual Testing:**

1. **Room chat:**
   - Type `say hello everyone`
   - **Expected:** Message appears in your feed and everyone in the room's feed
   - Other players in room see: "[Your Name]: hello everyone"

2. **Private message:**
   - Type `tell Alice secret message`
   - **Expected:** Message sent to Alice only (not to room)
   - Alice receives: "[Your Name] (privately): secret message"
   - Alice replies: `tell You that's confidential`

3. **Global channel (newbie):**
   - Type `newbie I need help with the locked door!`
   - **Expected:** Message sent to all online players
   - All players see: "[Your Name] (Newbie): I need help with the locked door!" (colored tag)

4. **Mute channel:**
   - Open Settings page
   - Uncheck "Newbie" channel
   - **Expected:** Newbie messages stop appearing in your feed
   - Room chat and private tells still visible (can't mute those)

5. **Separate chat pane:**
   - Open Settings, enable "Separate chat pane"
   - **Expected:** Two feeds appear: narrative (room events) and chat (messages)
   - Say something
   - **Expected:** Appears in chat pane, not narrative pane
   - Move east
   - **Expected:** Movement narration in narrative pane, chat pane unchanged

**Automated Testing:**
- **Location:** `tests/e2e/test_multiplayer_realtime.py` (P1.1 say propagates)
- **Test patterns:**
  - `say` message reaches all players in room
  - `tell` reaches only target player
  - Global channel reaches all online players
  - Muted channels don't appear in feed
  - Chat messages tagged with channel name + color
  - Offline player can't receive `tell` (error: "That player is offline.")

- **E2E tests:** `tests/e2e/test_chat_feed_split.py`

**Edge Cases:**
- Telling a player who just went offline (race: message in flight while disconnect?)
- Chat spam / rate limiting (not implemented yet)
- Long message (word-wrapping, text cutoff?)
- Special characters in chat (emoji, color codes, HTML — probably sanitized)
- Tell to yourself (allowed? confusing?)
- Offline message history (no feature yet; `tell` only works online)

**Verification Checklist:**
- [ ] `say` reaches all players in room
- [ ] `tell` reaches only target
- [ ] Global channel reaches all online players
- [ ] Muting channel removes messages from feed
- [ ] Chat messages show sender name
- [ ] Channel tags are color-coded
- [ ] Offline players can't receive `tell`
- [ ] Separate chat pane toggles correctly

---

### Feature: Following & Group Movement (Sprint 47)

**What it is:**
`follow <player>` makes you move with another player automatically. When they move, you move too (if your path is clear). Chains work (A→B→C, all move together).

**Gameplay it enables:**
- Group travel (move together without coordinating each move)
- Escort mechanics (help a low-level player navigate)

**Manual Testing:**

1. **Follow a player:**
   - Two players in same room (Alice and Bob)
   - Bob: `follow Alice`
   - **Expected:** Bob's panel shows "Following: Alice"
   - Alice: sees notification "Bob is following you."

2. **Automatic movement:**
   - Alice: `go east`
   - **Expected:** Alice moves east
   - Bob: automatically moves east too (if path is clear)
   - Bob's panel updates to show new room

3. **Failed movement:**
   - Alice: `go north` to a locked door
   - Alice has key, but Bob doesn't
   - **Expected:** Alice moves through; Bob stays behind
   - Bob's panel shows: "You can't follow Alice east (exit is locked)."
   - Follow automatically broken

4. **Unfollow:**
   - Bob: `unfollow`
   - **Expected:** "You stop following Alice."
   - Alice: "Bob is no longer following you."
   - Bob no longer auto-moves with Alice

5. **Check follow status:**
   - Bob: `follow` (no argument)
   - **Expected:** Shows "You're following Alice. Followers: none."
   - Alice: `follow` (to check)
   - **Expected:** Shows "You're not following anyone. Followers: Bob."

6. **Chain following:**
   - Alice, Bob, Charlie in same room
   - Bob: `follow Alice`
   - Charlie: `follow Bob`
   - Alice: `go east` → Bob follows → Charlie follows Bob (cascade)
   - **Expected:** All three end up in the same room

7. **Cycle prevention:**
   - Alice: `follow Bob`
   - Bob: `follow Alice` (attempting a cycle)
   - **Expected:** Error: "You can't follow someone who's already following you."

**Automated Testing:**
- **Location:** `tests/integration/test_follow.py`
- **Test patterns:**
  - `follow <player>` sets follower state
  - Follower auto-moves on target's movement
  - Failed movement breaks follow
  - `unfollow` stops following
  - Chain following cascades correctly
  - Cycles rejected
  - Both sides see notifications

- **E2E test:** `tests/e2e/test_multiplayer_realtime.py` (integration with WS updates)

**Edge Cases:**
- Target player logs out (follow breaks?)
- Target player is in a different area (can't follow if too far?)
- Follower in a room, target in adjacent room (how does follow start?)
- Follower leaves room while target is moving (race condition?)
- Rapid movement by target (should follower queue up, or try to catch up one room at a time?)

**Verification Checklist:**
- [ ] `follow <player>` sets follow state
- [ ] Follower auto-moves with target
- [ ] Failed movement breaks follow with message
- [ ] `unfollow` stops following
- [ ] Both sides see notifications
- [ ] Chain following works (A→B→C)
- [ ] Cycles prevented
- [ ] `follow` (bare) shows current status

---

### Feature: Multiplayer Presence (Sprint 15, 50)

**What it is:**
Real-time visibility of other players: who's in your room, who's online, player list with live updates on join/leave.

**Gameplay it enables:**
- Social awareness (know who's around)
- Opportunity to group up for quests/travel
- World feels populated (see other players acting)

**Manual Testing:**

1. **Player list:**
   - Look at "Here Now" panel (top-right)
   - **Expected:** Lists all players currently in your room

2. **Player joins room:**
   - Player A is alone in village_square
   - Player B logs in and enters village_square
   - **Expected:** Player A's "Here Now" updates, "B" appears
   - Player A sees in feed: "[B] has arrived."

3. **Player leaves room:**
   - Player B: `go north`
   - **Expected:** Player A's "Here Now" updates, "B" disappears
   - Player A sees in feed: "[B] has left to the north."

4. **Player goes offline:**
   - Player B: `quit`
   - **Expected:** Player A's "Here Now" updates, "B" disappears
   - Player A sees in feed: "[B] has gone offline." (or similar)

5. **See other player's actions:**
   - Player A in room with Player B
   - Player B: `take coin`
   - **Expected:** Player A sees in feed: "[B] takes a coin."
   - Player A sees coin disappear from room view

**Automated Testing:**
- **Location:** `tests/e2e/test_multiplayer_realtime.py`
- **Test patterns:**
  - P1.2 `player_joined` increments "Here Now"
  - P1.3 `player_left` decrements "Here Now"
  - P1.4 Dropped item becomes visible to other players
  - P1.5 Third-person narration form shown to observers

**Edge Cases:**
- Player in room during WS disconnect (should disappear after grace period)
- Rapid join/leave (shouldn't spam feed)
- Multiple players joining simultaneously (all should appear)
- Player name containing special characters (display correctly?)

**Verification Checklist:**
- [ ] "Here Now" panel lists current room occupants
- [ ] Player join updates panel and feed
- [ ] Player leave updates panel and feed
- [ ] Other player's actions visible in feed
- [ ] Player disconnect shows offline message
- [ ] List updates in real-time (WS push)
- [ ] Player names display correctly

---

## World Events & Content

### Feature: Room Effects & Timed Events (Sprint 39)

**What it is:**
Time-limited effects applied to rooms: doors that open/close on timers, occupant auras that modify abilities, environmental hazards.

**Gameplay it enables:**
- Puzzle mechanics (timed gates)
- Environmental hazards (cold aura in winter room)
- Event-driven gameplay (doors unlock for a limited time)

**Manual Testing:**

1. **Timed gate:**
   - Find a room with a timed-open passage (verify in world.yaml)
   - Exit is blocked: "A stone barrier blocks the passage."
   - Wait for effect to apply (or trigger manually)
   - **Expected:** Barrier lifts ("A stone rumbles aside, opening the passage.")
   - Move through
   - **Expected:** Movement succeeds
   - Wait for timer to expire
   - **Expected:** Barrier re-closes ("A stone rumbles shut behind you.")

2. **Occupant aura:**
   - Enter a room with an aura effect (e.g., "cold aura")
   - Check traits
   - **Expected:** Aura effect appears as a trait (e.g., "Chilled")
   - Leave the room
   - **Expected:** Aura trait disappears

3. **Effect duration:**
   - Note the effect's remaining time (if visible)
   - Wait
   - Check remaining time
   - **Expected:** Time counts down

**Automated Testing:**
- **Location:** `tests/integration/test_room_effects.py`
- **Test patterns:**
  - Effect applies at correct time
  - Room-state effect (gate) transitions on apply/expire
  - Occupant aura adds trait to players in room
  - Effect expires and reverts
  - Effect timing is accurate

**Edge Cases:**
- Moving through a gate just as it closes (race condition?)
- Effect expires while player is in the room (trait should disappear)
- Multiple effects in same room (should all apply)
- Effect that has an error in its hook (should fail gracefully, not cascade)

**Verification Checklist:**
- [ ] Timed gate opens/closes on schedule
- [ ] Gate blocks movement when closed
- [ ] Occupant aura adds trait while in room
- [ ] Aura trait disappears on room exit
- [ ] Effect timing is accurate
- [ ] Multiple effects coexist

---

### Feature: Weather & Climate (Sprint 44)

**What it is:**
Global weather state (clear, rainy, stormy, snowy, etc.) tied to the world clock. Weather affects terrain movement, vehicle schedules, and skill checks.

**Gameplay it enables:**
- Environmental storytelling (weather affects mood)
- Challenge variation (same area harder in harsh weather)
- Strategic planning (avoid travel during storms)

**Manual Testing:**

1. **Check weather:**
   - Type `weather` (if available) or look at status bar
   - **Expected:** Current weather displayed

2. **Weather affects terrain:**
   - Check a skill-gated mountain pass requirement (e.g., "Survival 5 required")
   - In clear weather, you can pass (assume you have skill 5+)
   - Advance time to blizzard
   - **Expected:** Same pass now blocked ("Survival 7 required" due to weather penalty)

3. **Weather affects transit:**
   - Check ferry schedule in clear weather
   - Advance time to storm
   - **Expected:** Ferry schedule shows delay

**Automated Testing:**
- **Location:** `tests/integration/test_weather.py`
- **Test patterns:**
  - World clock advances weather through cycles
  - Weather modifiers apply to skill checks
  - Weather-sensitive vehicles delay in harsh weather
  - Weather affects terrain difficulty

**Edge Cases:**
- Transitioning between rooms with different weather effects (shouldn't happen; weather is global)
- Very rapid weather changes (simulation time acceleration)

**Verification Checklist:**
- [ ] Current weather visible in status/command output
- [ ] Weather cycles through states
- [ ] Harsh weather increases terrain difficulty
- [ ] Transit vehicles respond to weather
- [ ] Weather is consistent across world (global, not local)

---

## Admin & Observability

### Feature: Analytics & Performance Monitoring (Sprints 35, 49, 51)

**What it is:**
Admin dashboard showing performance metrics (p50/p95/p99 latency by operation), activity heatmaps (players by hour), NPC interaction stats, quest completion funnel, and operation timeline.

**Gameplay it enables:**
- Observability (admins know what's slow)
- Health monitoring (player activity patterns)
- Bug discovery (stat anomalies)

**Manual Testing (Admin Only):**

1. **Open Analytics tab:**
   - Log in as admin (if available)
   - Go to `/admin`
   - Click "Analytics" tab
   - **Expected:** Dashboard loads with multiple widgets

2. **Latency table:**
   - Shows p50/p95/p99 latency for each operation
   - Example: "take: p50=8ms, p95=12ms, p99=45ms"
   - **Expected:** Numbers make sense (< 100ms for simple ops)

3. **Activity heatmap:**
   - Shows player activity by hour (24 buckets)
   - Color intensity = number of players active
   - **Expected:** Matches your expected playtime (if testing during peak, expect darker colors)

4. **Top commands:**
   - Bar chart of most-executed commands
   - Example: "move: 150 times, look: 200 times, take: 80 times"
   - **Expected:** Matches your expected gameplay patterns

5. **NPC interactions:**
   - Stats on which NPCs players interact with most
   - Example: "Mira: 45 interactions, Innkeeper: 20 interactions"
   - **Expected:** Matches world usage

6. **Quest completion funnel:**
   - Shows quest-start, completion, failure rates
   - Example: "Investigate Lights: 10 started, 7 completed, 2 failed"
   - **Expected:** Completion rate > 0%

7. **Operation timeline:**
   - Recent operations with duration
   - Example: "move (8ms), look (2ms), say (3ms), move (7ms)"
   - **Expected:** Timeline is recent (last few ops)

**Automated Testing:**
- **Location:** `tests/integration/test_analytics.py`
- **Test patterns:**
  - `operation_latency_percentiles()` calculates p50/p95/p99
  - `activity_by_hour()` buckets players by hour
  - `top_commands()` ranks operations
  - `npc_interactions()` counts NPC interactions
  - `quest_completion_funnel()` calculates rates
  - `operation_timeline()` returns recent ops with duration

- **E2E test:** `tests/e2e/test_admin_analytics.py` (dashboard endpoint)

**Edge Cases:**
- No activity (all stats = 0)
- Spike in activity (one operation dominates)
- Very long-running operation (p99 is extreme outlier)
- Dashboard loads while activity is happening (data shouldn't change mid-request)

**Verification Checklist:**
- [ ] Analytics dashboard loads and displays
- [ ] Latency stats are accurate (validated against audit log)
- [ ] Activity heatmap reflects player distribution
- [ ] Top commands reflects actual command frequency
- [ ] NPC stats count interactions correctly
- [ ] Quest funnel shows realistic rates
- [ ] Operation timeline shows recent operations

---

### Feature: Issue Reporting & Tracking (Sprints 33, 40–42)

**What it is:**
In-game `report` command for players to file bugs/feedback. Reports go to admin issue tracker with categorization, priority, and filtering.

**Gameplay it enables:**
- Player feedback collection (without leaving game)
- Bug discovery (players report issues)
- Community engagement (admin responds to feedback)

**Manual Testing (Player):**

1. **File a report:**
   - Type `report There's a typo in the innkeeper's dialogue`
   - **Expected:** Message: "Thanks — logged as issue-abc123. The team will take a look."

2. **Report via guided wizard:**
   - Type `report` (no argument)
   - **Expected:** Dialogue-style form appears: "What would you like to report?"
   - Choose category (Bug / Suggestion / Typo / Other)
   - Enter title
   - Enter detailed description
   - Submit
   - **Expected:** Issue logged with all fields

**Manual Testing (Admin):**

1. **View issues:**
   - Go to `/admin` → "Issues" tab
   - **Expected:** List of all submitted issues with priority/status/date

2. **Filter issues:**
   - Filter by component, priority, status
   - **Expected:** Filtered list updates

3. **Sort issues:**
   - Click "Sort: Priority" vs. "Sort: Recently Updated"
   - **Expected:** List re-sorts

4. **Hide resolved:**
   - Check "Hide status: resolved"
   - **Expected:** Resolved issues disappear from list

5. **Edit issue:**
   - Click an issue
   - Edit priority / status / component
   - **Expected:** Changes save and list updates

6. **Live refresh:**
   - Player files a report while admin Issues tab is open
   - **Expected:** New issue appears in list automatically (no manual refresh)

**Automated Testing:**
- **Location:** `tests/integration/test_issues.py` (report command)
- **Test patterns:**
  - `report` command creates issue
  - Report via dialogue wizard works
  - Issue appears in admin issue list
  - Admin can edit issue
  - Filter/sort works
  - Live refresh on new report

- **E2E tests:** `tests/e2e/test_admin_issues.py`

**Edge Cases:**
- Report while in dialogue (should work; they're independent)
- Report with very long description (truncation? validation?)
- Player reports during grace period (disconnected before ACK)
- Admin deletes issue while player is viewing report success message

**Verification Checklist:**
- [ ] `report` command accepts input
- [ ] Report appears in admin Issues tab
- [ ] Issues can be filtered and sorted
- [ ] Admin can edit issue metadata
- [ ] Live-refresh works (new report auto-appears)
- [ ] Issue component is validated (known component required? or free-text?)
- [ ] Issue priority defaults to normal/unset

---

### Feature: Content Linting & Validation (Sprint 10.5, ongoing)

**What it is:**
Automated checks on world content (YAML) for consistency: missing item references, broken NPC links, invalid field values, etc. Run via admin CLI or on startup.

**Gameplay it enables:**
- Content quality gates (prevent obvious errors from reaching players)
- Content integrity (verify world is self-consistent)

**Manual Testing:**

1. **Lint on startup:**
   - Start the server with dev world
   - **Expected:** Lint output in logs, warnings for any issues
   - Example: "Warning: Room 'market_stalls' has item 'coin' but coin type is not defined"

2. **Manually lint:**
   - CLI: `python scripts/world_cli.py lint world_content/world.yaml`
   - **Expected:** Report of any validation errors

3. **Fix errors:**
   - If lint reports missing item, add it to world.yaml
   - Re-run lint
   - **Expected:** Error gone

**Automated Testing:**
- **Location:** `tests/unit/test_content_linting.py`
- **Test patterns:**
  - Missing item references detected
  - Broken NPC links detected
  - Invalid room IDs detected
  - Missing dialogue target detected
  - Duplicate item/NPC IDs detected

**Edge Cases:**
- World with no errors (should pass cleanly)
- World with multiple error types (all reported, not just first)
- Circular references (NPC A's quest refers to NPC B's quest, which refers to A)

**Verification Checklist:**
- [ ] Lint reports missing items/NPCs
- [ ] Lint validates field types
- [ ] Lint prevents invalid quest references
- [ ] Lint runs on startup
- [ ] Lint can be triggered manually
- [ ] Error output is clear and actionable

---

## Testing Strategy Overview

### Unit Tests
- **Location:** `tests/unit/`
- **Scope:** Individual services, commands, logic
- **Run:** `make test` (includes unit)
- **Examples:** Skill XP calculation, inventory stacking, ledger math

### Integration Tests
- **Location:** `tests/integration/`
- **Scope:** Multiple services interacting; database included
- **Run:** `make test` (includes integration)
- **Examples:** Quest progression (dialogue → quest → completion), economy (shop restock)

### E2E Tests
- **Location:** `tests/e2e/`
- **Scope:** Full game flow through browser; WS, HTMX, Alpine reactive
- **Run:** `make test-e2e` (serial)
- **Examples:** Multiplayer chat, auth session, equipment wear/remove

### Simulation Tests
- **Location:** `tests/simulation/`
- **Scope:** Headless multi-player load tests, scenario replay, audit regression
- **Run:** `make test-simulation` (serial)
- **Examples:** 10 players concurrently moving/trading, replay recorded session, audit-log golden

### Golden Path Scenario
- **File:** `tests/simulation/scenarios/golden_path.json`
- **Coverage:** Login → move → take → examine → quests → trade → transit
- **Audit trail:** `tests/simulation/scenarios/golden_path.audit.json` (deterministic baseline)
- **Use:** Catch regressions; replay under load; verify determinism

---

## Coverage Gaps & Future Work

### Not Yet Tested Comprehensively:
- Combat system (awaiting implementation — Sprint 61+)
- PvP mechanics (awaiting implementation)
- Multiplayer trade/transit test pass (deferred to wishlist)
- Death/resurrection mechanics (awaiting implementation)
- Offline message history (not implemented)
- Rate limiting on chat (not implemented)
- World versioning & builder mode (tested but integration could be deeper)

### Recommended Next Steps:
1. **Expand E2E coverage:** Every major feature should have an end-to-end test exercising the full flow
2. **Multiplayer scenarios:** Record and replay real multi-player sessions (group quest, trading chain, etc.)
3. **Stress testing:** Push system to 50+, 100+ concurrent players to find bottlenecks
4. **Edge-case scenarios:** Test rare combinations (max encumbrance + no light + low stamina, etc.)
5. **Browser compatibility:** Test on Safari, Firefox, mobile Chrome (current tests run Chromium)

---

## Verification Checklist Template

Use this checklist when testing a feature:

```
Feature: [Name]
Sprint: [#]
Tester: [Name]
Date: [YYYY-MM-DD]

[ ] Manual walkthrough completed (all main flows tested)
[ ] No console errors or warnings
[ ] UI renders correctly on mobile and desktop
[ ] Feature persists across logout/login
[ ] Integration tests pass (make test)
[ ] E2E tests pass (make test-e2e) — if applicable
[ ] Audit-regression unchanged (make test-simulation) — if applicable
[ ] Edge cases handled gracefully
[ ] Error messages are clear and helpful
[ ] Performance acceptable (< 100ms for most operations)
[ ] Feature doesn't break other features (smoke test other areas)

Issues found:
- [Issue 1]
- [Issue 2]

Notes:
[Any observations or recommendations]
```

---

**End of Feature Testing Guide**

> This guide is a living document. Update it as features are added or changed.
> Last updated: **2026-07-07** (Sprints 1–55 complete)
