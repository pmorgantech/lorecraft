---
kindle_doc_weaver: ignore
---

# Lorecraft Player Guide

A guide to playing Lorecraft in the browser: creating a character, moving around, talking
to NPCs, and the full command list.

## Table of Contents

1. [Getting Started](#getting-started)
2. [The Game Screen](#the-game-screen)
3. [Themes & Display](#themes--display)
4. [Movement](#movement)
5. [Looking, Taking, and Using Items](#looking-taking-and-using-items)
6. [Talking to NPCs & Quests](#talking-to-npcs--quests)
7. [Chat & Social](#chat--social)
8. [Saving, Quitting, and Reconnecting](#saving-quitting-and-reconnecting)
9. [News](#news)
10. [Reporting Bugs](#reporting-bugs)
11. [Full Command Reference](#full-command-reference)
12. [Tips & Troubleshooting](#tips--troubleshooting)

---

## Getting Started

Open the server's URL in a browser (e.g. `http://localhost:8000`) — it redirects to
`/lobby`.

- **Create New Character** tab — pick a name (3–30 characters: letters, numbers, `-` or
  `_`) and a password. This creates your character and drops you straight into the game.
- **Log In** tab — enter the name and password of a character that already exists on the
  server.

Both tabs are password-protected: only someone who knows a character's password can enter
as them. Logging in with the same name and password again later returns you to the same
character; a wrong password is rejected.

Your session is a signed cookie, so refreshing the page or closing the tab and coming
back keeps you logged in as the same character.

## The Game Screen

| Panel | What it shows |
|-------|----------------|
| **Current Location** (top-left) | Room name, description, visible NPCs, and visible items. Click **⟳** to refresh it manually. |
| **Inventory** (left, below room) | What you're carrying. Hover an item for **use**/**drop** quick-action buttons. |
| **Mini-map** (bottom-left) | Rooms you've visited, with fog of war over unexplored areas. Click **⛶** to open a full-screen map you can drag to pan and scroll (or use the +/−/⟲ buttons) to zoom — improving your cartography skill also reveals nearby rooms you haven't visited yet, dimmed until you get there. |
| **The Chronicle** (center) | The live narrative feed — your actions, other players' actions, and room events, in order. |
| **Here Now** (top-right) | Players currently in your room / online. |
| **Quests** (bottom-right) | Your active quests and current stage description. |
| **Command bar** (bottom) | Type a command and press Enter or click **Send**. Press `/` anywhere to jump focus into it. |

When an NPC conversation is active, a dialogue overlay appears above the command bar with
the NPC's line and numbered reply buttons — see [Talking to NPCs](#talking-to-npcs--quests).

On a narrow (phone-width) screen, the three panel columns collapse into one at a time —
use the **Room** / **Feed** / **Panel** tabs at the bottom to switch between them.

## Themes & Display

Open **Settings** (top-right of the game screen) to change how the client looks. Choices are
saved to your account, so they follow you to any device you log in from.

A **Theme** is the combination of a **Layout** and a **Color scheme** — the two dropdowns.

**Layout** is the main choice — it sets the panel arrangement **and** the typography (font faces,
sizes, spacing): Standard, E-reader, Dock, Immersive, or Classic (see the table further down).
Each layout brings its own tuned colours too, so most players only ever pick a Layout.

**Color scheme** is optional and changes **colours only** — it never reflows the text. Leave it on
**Auto** to use the layout's own scheme, or pick one to override it — e.g. the Mono Green CRT look
under any layout:

| Scheme | Look |
|--------|------|
| **Terminal** *(default for Standard)* | A green-tinted terminal — spring-green accent on near-black. |
| **Slate** | A modern dark app scheme with a cyan accent. |
| **Immersive** | A cinematic, low-glare dark scheme lit in warm amber. |
| **Parchment** | A warm, light "old book" scheme. |
| **Mono Green** *(default for Classic)* | A phosphor-green CRT — scanlines and a soft glow, like an old text game. |
| **Mono Amber** | The same CRT, in amber phosphor. |

The **Layouts** — each pairs panel arrangement with its own typesetting (the scheme override
recolours it without changing the type):

| Layout | Arrangement |
|--------|-------------|
| **Standard** *(default)* | Three columns: the Current Location (with an **Also Here** list) + map on the left, chronicle in the centre with its command prompt, and one full-height right pane **tabbed between Inv / Body / Quests / Stats**. |
| **E-reader** | A warm "illuminated manuscript" book: the location on a left ledger, a wide **serif chronicle** in the centre with an *Inscribe* prompt, and a slim right rail of vertical tabs (Here / Quests / Pack / Stats). Pairs best with the Parchment scheme. |
| **Dock** | A modern dark "app": three columns of floating, rounded **cards** — the Location (with an **Also Here** list) + Minimap on the left, the Chronicle (with a **Send** button) in the centre, and one right card with **window-shade sections Inv / Quests / Stats** (click a shade's title to open it; the others collapse to their headers). Inv lists your inventory with each item's name **coloured by type** (weapon/armor/utility/coin) plus a small type tag and its weight (click a row to examine it). Pairs with the Slate scheme. |
| **Immersive** | A focused, cinematic view: a slim **icon rail** on the far left (glyph shortcuts for Look / Inventory / Journal / Score), a **full-bleed chronicle** filling the screen, and a **floating minimap** and **command bar** hovering over it. Chat folds into the chronicle — no side panels at all. Pairs with the amber-lit **Immersive** scheme. |
| **Classic** | An old-MUD terminal: the chronicle (with a vitals line + command prompt) fills the left; a minimap and a chat channel are stacked on the right. Chat is display-only — send messages with `say …` on the main command line. Chronicle-only like Immersive; defaults to the **Mono Green** CRT scheme but works under any. |

Each Layout is also **typeset** to suit its feel: Standard uses JetBrains Mono and Classic IBM
Plex Mono, E-reader sets its chronicle as serif book prose (spoken lines in *italics*), and Dock
and Immersive use a clean sans. Numbers line up (tabular figures) and descriptions are held to a
comfortable reading width in every Layout. Switching the color scheme never changes any of this.

In **Standard**, the right pane holds **Inv, Body, Quests, and Stats as tabs** in a single card; Dock
holds Inv, Quests, and Stats as **window shades**. The **Stats** pane is a full character readout — vitals
as meter bars plus coins, attributes and level, trait chips, earned marks, your reputation with
each faction (Friendly / Neutral / Wary), and any active effects. Who's here lives in the **Also
Here** section of the Location card in both. (E-reader reaches everything from its tab rail.)
Immersive drops the room, inventory, players and quest panels entirely to keep the focus on the
chronicle — see below for how it makes that information up.

**Immersive and Classic read like an old-school MUD.** With no side panels, the chronicle itself
narrates what they'd normally show: entering a new room (or a bare `look`) prints a styled room
readout — name, description, NPCs, items, exits, and anyone else present — flush in the chronicle.
Lines have no colour bar or timestamp here — just scrolling text, telnet-style.

**Your own chat is right-aligned, with the colour bar on the right** — wherever it appears as its
own message (the separate chat pane, or the classic layout's chat channel) — so your lines read as
"sent by me" against everyone else's left-aligned messages. (In Immersive your chat simply folds
into the chronicle inline, MUD-style.)

Layout and scheme **preview live** as you change the dropdowns — click **Save** to keep them (you
go straight back to the game), or **Cancel** to discard and return with your last-saved look.

There are also quick **Layout** and **Color scheme** dropdowns in the top bar (next to your name)
that take effect immediately, if you'd rather not open Settings.

Other display options on the same page:

- **Minimap style** — *Graph* (the map of rooms you've discovered) or *Compass* (an exit-star
  rose: a lit spoke means an exit that way — click it to go). Every layout's map pane also has a
  small **⇄ toggle** that flips between the two on the spot.
- **Display density** — *Comfortable* or *Compact* (tighter spacing to fit more on screen).
- **Text size**, **High-contrast theme**, and **Reduce motion** for readability and accessibility.
- **Feed verbosity**, **timestamp format**, and how many feed entries to load.
- **Hidden panels** — hide the mini-map, inventory, players, or quest panels you don't want.

> Prefer keyboard-friendly, low-distraction play? Pair **High-contrast** or **Reduce motion**
> with any theme — those toggles stack on top of your chosen palette.

## Movement

Move with `go <direction>`, or just type the direction on its own:

```
go north
north
n
```

Recognized directions (full word or the listed abbreviation): `north`/`n`,
`south`/`s`, `east`/`e`, `west`/`w`, `up`/`u`, `down`/`d`, `northeast`/`ne`,
`northwest`/`nw`, `southeast`/`se`, `southwest`/`sw`.

Use `where <room>` to ask for the shortest known path from your current room:

```
where south gate
Path to South Gate: s, s, e, s
```

If an exit is locked, `unlock <direction>` works if you're carrying the right key, and
`lock <direction>` locks it back up.

```
unlock north
go north
```

### Following another player

`follow <player>` makes you move with someone when they move — handy for travelling together
(and boarding transit as a group). It's overt: they see that you're following, and both of
you see the movement. `unfollow` stops. A bare `follow` shows who you're following and who's
following you.

```
follow Aldric        — travel with Aldric when they move
follow               — show your current follow status
unfollow             — stop following
```

If a door you can't pass (a locked exit, terrain you lack the skill for) blocks you when your
leader moves through it, your follow simply breaks and you're both told. Chains work
(A follows B follows C, and the whole line moves together).

## Looking, Taking, and Using Items

```
look                    — describe your surroundings again
examine key             — read an item's description (also: inspect, x)
take coin                — pick up an item
take 2 coin               — pick up a specific quantity
take all                 — pick up everything takeable in the room
drop sword                — put down a carried item
inventory                — list what you're carrying
use torch                — use a carried item
use key on chest          — use one item on another
give bread to Mira        — hand a carried item to an NPC
open chest                — open a container
close chest               — close a container
put coin in chest         — place a carried item into an open container
take coin from chest      — take an item out of a container
wear helm                 — equip a worn item (armor, clothing)
remove helm               — unequip a worn item
wield sword               — equip a wielded item (weapon, tool, light)
unwield sword             — unequip a wielded item
equipment                 — list what you're wearing and wielding (also: eq)
body                      — show every wear slot plus current body condition (also: condition)
light lantern             — light a light source
extinguish lantern        — put out a lit light source
turn dial                — cycle a lever or dial to its next position (also: pull, activate)
```

Worn/wielded gear can grant passive bonuses (stat/skill boosts, extra carry capacity,
traits) while equipped — check an item's description or `examine` it to see what it does.
Use the **Body** tab, or type `body` / `condition`, to see every wear/wield slot grouped by
body part. Empty slots are shown explicitly, equipped items appear in their slot, and active
combat wounds are listed on the affected body part as a damage assessment.
Carrying too much weight makes you **burdened** (travel costs more) or, past a hard
threshold, **overloaded** (you can't pick up anything else until you drop or stow something).
A room with no ambient light needs an equipped, lit light source (like a lit lantern) or
you can't see to look around, take items, or read descriptions — a lit source slowly burns
through its fuel (durability) over time, so keep spares.

For the Ashmoore caves, take the `Dented Oil Lantern` at the cave mouth, then:

```
wield lantern
light lantern
```

The Brass Vaults also seed an `Aether Lantern` near their entrance for their darker
maintenance rooms.

**Disambiguation:** if your item name matches more than one thing, Lorecraft prompts you
with a numbered list:

```
> take key
Which do you mean? (1) Iron Key, (2) Rusty Iron Key, (3) Steel Key
> 2
```

Just type the number. Being more specific (`take rusty iron key`) also works and skips
the prompt.

Rooms need light to look around and to take/examine items — `light_level` in the room
data controls this. If a room is dark, bring a light source.

## Exploration

```
search          — look for hidden exits and secrets in the room
journal         — review places visited, people met, items discovered, lore learned, and active quests
hunts           — list any scavenger hunts running now and your progress
marks           — list the marks you have earned by discovery
```

Every so often a **scavenger hunt** runs: a themed set of items is scattered across a handful
of rooms, and finding all of them earns a reward. `hunts` shows what's active and how many
you've found; just `take` the hunt items you come across — the last one completes the hunt.
Some hunts pay speed bonuses, timed from the first hunt item you find.

**Marks** are badges earned by discovery — visiting places, meeting people, finding items,
learning lore. They award themselves the moment you complete one's criteria ("You have earned
Mark of the Village Wanderer!"), and some carry a small passive boon (a lighter pack, a keener
map hand). `marks` lists what you've earned; a `??? — undiscovered` line hints at marks still
out there. A few are entirely hidden until the moment you earn them.

Not every exit shows up in a room's description — `search` rolls your perception skill
(better with practice, traits, and equipment) to find hidden passages. Once you've found
one, it stays visible to you from then on. Some exits also need a specific flag (a key
event, an NPC's trust, a quest step) before they'll let you through, whether or not you've
found them. Rooms can also have terrain (forest, mountain, swamp, water...) that requires
a minimum survival skill to enter safely.

Some **objects carry their own verbs**. An altar might let you `read` its inscription, a
lever might `pull`, an innkeeper might accept a `tip` — but only while that object is with
you (in the room, or in your pack). These verbs show up in `help` only when they're usable,
so if you're stuck, `look` around and try the obvious action on what you see.

The world also keeps **celestial time**: the status bar shows the current **moon phase**
and **tide** beside the clock. Some paths only open when the water is low (a drowned
causeway, say), and some things — a dialogue option, a ritual, a door — answer only to a
particular moon. If a way is shut, the heavens may simply not be right yet; note the moon
and tide and come back.

## Stamina: Rest, Sleep, and Camp

```
rest            — enter rest mode and recover movement points over time
stand           — leave rest mode
camp            — make camp and recover a good deal of stamina
sleep <hours>   — sleep deeply and recover movement points faster
```

Traveling spends movement points from your stamina meter. The cost depends on the
terrain you're entering, the weather if you're exposed, and how much weight you're
carrying. If you don't have enough movement points, you can't move. Running low also
saps your skill checks (perception, lockpicking, and the rest), so it pays to top up
before attempting something that matters.

`rest` toggles a rest mode: you recover slowly over time, but you must `stand` before
you can move or use things. `sleep <hours>` recovers faster and clears rest mode, but
you are unavailable until enough world time passes and room events won't appear in
your feed while you're asleep. Sleeping in an inn or a marked camp is reliable;
anywhere else still risks an interrupted, exposed sleep, especially in cold weather
without warm gear.

## Character: Traits, Disciplines, and Reputation

```
traits          — list your active traits (from equipment, effects, and background)
disciplines     — list your disciplines and your rank in each (also: skills)
reputation      — list your standing with NPCs and factions (also: rep)
```

Traits are passive bonuses or penalties — some come from what you wear, some from timed
effects, and some are permanent (background or earned through play).

Your capabilities are organized into five **disciplines**, each a themed body of practice:

| Discipline | Covers |
|------------|--------|
| Survival | Foraging, tracking, cartography, and weathering the wild |
| Subterfuge | Lockpicking, perception, and moving unseen |
| Commerce | Bartering and driving a fair deal |
| Rhetoric | Persuasion and social craft |
| Fortitude | Physical resilience |

Each discipline has its own **rank**, and every check that leans on a discipline (a
survival check to forage, a lockpicking check to `pick`, a perception check to `sense` or
`search`, a bartering check when you `sell`, a persuasion check in dialogue) rolls against
that discipline's rank. Ranks grow the more you use the checks they govern ("learn by
doing") — there's no way to train a rank directly. Run `disciplines` (its alias `skills`
is the same read-only command, not a separate system) to see your current rank in each.
Reputation with an NPC or faction can unlock better prices, new dialogue, or additional
quests.

## Experience & Leveling

```
score           — your progress: level/xp, quests, wealth, reputation, discoveries
```

You earn **experience (XP)** two ways: completing a quest stage (its reward is applied the
moment the stage completes) and **discovery** — a successful `search` that turns up a hidden
passage awards a little XP for the find, alongside revealing the passage. XP accumulates
toward your current level's threshold; the cost curve (how much XP each level takes) is set
by the server admin rather than fixed in the game, so it can differ from server to server.

Crossing a threshold **levels you up** — the chronicle prints a "You reach level N!" line in
its own distinct color, and you're paid coins and skill points on the spot. Those amounts are
also admin-configured rather than a fixed rate, so don't assume one server's payout matches
another's.

**Skill points** are the currency you spend on abilities — see
[Abilities](#abilities) below for how to spend them.

`score` (or the **Stats** pane) shows your current level and XP progress (`X/Y XP` toward the
next level) at a glance.

## Abilities

```
train [ability]     — spend skill points to train an ability (no arg lists what's trainable) (also: learn)
abilities            — list the abilities you know and what you can currently train (also: abils)
```

The skill points you earn from [leveling up](#experience--leveling) are spent on
**abilities** — one-time, permanent unlocks, each filed under one of the five
[disciplines](#character-traits-disciplines-and-reputation) above. Each ability costs a
number of skill points and may require another ability first (a prerequisite), and some
also require a minimum rank in their discipline or a minimum character level; once
trained, an ability is yours for good — there's no respec.

Abilities come in three flavors, and a given ability is always exactly one of them:

- **Active-verb abilities** unlock a new command you can use once trained. Attempting the verb
  before you've trained it behaves as if the command doesn't exist — it won't even show up in
  `help` — so if you want to `forage`, `sense`, or `pick` a lock, train the matching ability
  first.
- **Passive-bonus abilities** apply automatically the moment you train them — no verb to run,
  just a standing bonus (for example, carrying more before you're overloaded, or paying less
  at a shop).
- **Interaction/dialogue abilities** don't change what you can *do* so much as what people will
  *tell* you — they unlock extra conversation options with NPCs who respond differently once
  they know you have a certain knack (a silver tongue, say).

Run `train` with no argument to see what's ready to buy right now versus what's still locked
(and why — not enough points, or a prerequisite you haven't trained yet). `train <ability>` (or
`learn <ability>`) spends the points on a specific ability by its name; you'll get a clear
reason if it fails — not enough skill points, a missing prerequisite, or you already know it.
`abilities` (or `abils`) is the read-only counterpart: it lists what you already know alongside
what you're currently able to train, without spending anything.

The three starter active-verb abilities:

| Ability | Verb | What it does |
|---------|------|----------------|
| Forage | `forage` | Outdoors only. Rolls a survival check; on success, turns up a consumable item you can `eat`/`drink` later. |
| Keen Senses | `sense` (also: `perceive`) | An enhanced search: rolls a perception check to reveal any hidden exits in the room, plus who and what else is present. |
| Pick Locks | `pick <direction>` | Attempts a locked exit without its key via a lockpicking check — the alternative to `unlock` when you don't have the right key. |

## Trading

```
list            — show a room's shop stock and prices (also: shop)
buy sack        — purchase 1 (or: buy 3 sack — purchase 3)
sell mug        — sell a carried item to the shop here
appraise gem    — estimate what an item is worth in coins
```

Some NPCs run a shop — `list` in their room to see what's for sale. In Ashmoore,
try the inn, forge, apothecary, general store, and bakery around the village market.
Shops only buy certain kinds of goods, won't take anything soulbound, and have real
(finite) cash — sell too much in one place and they'll run dry. The `bartering`
skill and your standing with the vendor both shave a little off the price over time.
Prices also vary by place — the same goods can cost more or less depending on where
you are, so it pays to know the routes. Newly created characters start with 100
carried coins.

## Banking

```
deposit 50      — deposit carried coins at a bank branch
withdraw 20     — withdraw banked coins at a bank branch
balance         — show coins carried and banked (works anywhere)
```

Banked coins are safe — they're a separate account from what you're carrying, so they
survive things that carried coins don't. Deposit at one branch, withdraw at another;
it's the same account everywhere.

## Trading with Other Players

```
offer sword to Bob       — pledge a carried item to a trade with Bob
offer 40 coins to Bob    — pledge coins instead
accept                   — finalize the pending trade
decline                  — call it off
```

Either of you can keep adding pledges with `offer` — items, coins, or both — until
you're both happy, then either side can `accept` to make the swap. Nothing moves until
someone accepts, and the trade is checked one more time at that moment, so it can't go
wrong if something changed since you offered (an item got dropped, coins got spent).

## Travel

```
board            — board a transit vehicle docked at this station
board ferry      — board a specific line, if more than one serves this station
disembark        — leave the vehicle at its current stop (also: leave)
schedule         — show a line's stops and where it is right now (also: timetable)
```

Some routes (a ferry, a rail line, a balloon) run on their own schedule between fixed
stops, whether or not anyone's riding. `board` only works while the vehicle is docked at
your station — miss it and you'll need to wait for the next stop, or catch it further
down the line. Some lines need a ticket to board; check `schedule` to see the route and
whether the vehicle is currently there.

## Living World

Some zones have their own climate patterns in addition to the world's general weather:
Whisperwood is often misty or rainy, while Cogsworth more often sits under clear or
overcast skies. Rooms may also produce occasional ambient details as time passes, and
some hidden places can turn up randomized treasure the first time you discover them.

NPCs can move on their own. Some wander, some patrol a simple loop, and some follow a
fixed route with visible departures and arrivals.

Two newer explorable areas branch from Ashmoore: from `south_gate`, go `east` to reach
the Old Hill Graveyard; from `inner_vault`, go `up` to reach the steampunk Brass Vaults.
The graveyard has tombstones with local commands such as `read tombstone`, while Forewoman
Cassia in the Brass Vaults offers ten local repair and survey quests.

## Talking to NPCs & Quests

```
talk mira        — start a conversation (also: speak)
1                 — pick reply #1 (or: choice 1, choose 1)
bye               — end the conversation (also: farewell, goodbye)
quests            — list your quests, their status, and current objective (also: quest)
```

The dialogue overlay shows the NPC's current line and numbered choices — click a choice
button or type its number. Some choices start or advance quests; check the **Quests**
panel in the right sidebar — or type `quests` — to see what you're currently tracking and
what to do next. For a multi-stage quest, `quests` shows which stage you're on (`stage 2/3`)
and that stage's objective; finished quests are marked completed (or failed).

## Chat & Social

```
say hello           — speak aloud; everyone in the room sees it
tell <player> <msg> — private message to an online player (alias: whisper)
newbie <msg>        — speak on the world-wide Newbie channel
who                 — list players online across the whole game
wave                — wave to the room; `wave at <someone>` to wave at a target
point at <target>   — point at a person, creature, or thing (e.g. `point at sign`)
```

`who` is global: it lists connected players anywhere in the game. Use `look` or the
location panel for who is present in your current room.

Chat travels on **channels** with different reach: `say` stays in your room, `tell` goes
to exactly one online player (offline players can't receive tells — there's no in-game
mail yet), and topic channels like **Newbie** reach everyone online. Each channel gets its
own color in the feed, and topic messages carry a `(Newbie)`-style prefix.

You can tune out topic channels on the **Settings** page ("Chat channels") — untick one
and its chatter stops reaching you entirely. Room talk and private tells always reach you;
they can't be muted. Pair this with the *separate chat pane* setting to keep all
conversation out of your narrative feed.

## Saving, Quitting, and Reconnecting

```
save            — same as `save auto`
save slot1      — save to a named slot (auto, slot1, slot2, slot3)
load slot1      — restore from a slot
quit            — leave the game and return to the lobby
```

Your position, inventory, flags, and stats persist automatically as you play — `save`
is for keeping named checkpoints you can `load` back to later, not for basic persistence.

If your connection drops without `quit` (closed laptop, lost WiFi), the server holds your
character in place for a grace period (60 seconds by default) before treating you as
disconnected. Reconnecting within that window resumes exactly where you left off; other
players nearby see you flicker rather than vanish.

## News

```
news            — show current server announcements
/news           — same thing
```

Announcements are also available outside the game as an RSS feed at `/api/news/feed`,
if you want to follow them in a feed reader.

## Reporting Bugs

```
report <description>    — report a bug or issue to the developers
/report <description>   — same thing
```

Found something broken? `report` sends a short description straight to the developers'
issue tracker — no need to leave the game or dig up a contact form. It works anywhere,
even mid-conversation with an NPC. Try to be specific about what you did and what you
expected to happen instead:

```
> report get all left the keys visible in the room panel even after taking them
Thanks — logged as issue-a1b2c3d4. The team will take a look.
```

## Combat

Combat uses scheduled intent: your command commits an action, then the world resolves it after
a short wind-up and recovery window. For a step-by-step introduction, see
[`combat_tutorial.md`](combat_tutorial.md). The first implemented PvE commands are:

```
attack <target>    — start or continue an encounter with a nearby NPC
shoot <target>     — start or continue a ranged attack against a nearby NPC
consider <target>  — appraise a nearby opponent before starting or continuing combat
defend             — brace with your next primary action
guard [ally]       — defend yourself or intercept attacks against an ally
assist <player>    — join a nearby player's active encounter on their side
flee               — look for an opening to leave the encounter
stance <stance>    — switch to balanced, aggressive, defensive, or mobile
reaction <policy>  — choose defensive, conserve, or never for auto-reactions
```

Ashmoore now has a combat training academy west of South Gate. Talk to Armsmaster Seren Vale in
the drill hall, take practice gear from the pegs, and spar with Tobin in the yard to try the combat
flow without looking for a wilderness fight.

Builders can tune the core action timing and broad ranged/melee semantics in
`world_content/combat_actions.yaml`; players do not need to know those numbers while playing.

During recovery you can queue one replacement primary action; the newer choice replaces the
older pending one. Combat uses health plus your existing stamina meter. The browser combat feed shows each
opponent's approximate health band plus current HP after combat updates. At 0 HP, player characters
die and immediately respawn at their respawn point with a fraction of max HP restored, while NPCs
are defeated. Death leaves a corpse in the death room holding 20% of carried coins and loose,
unbound carried items; equipped and bound items remain with the player, and a temporary weakened
effect is applied. Dead, defeated, or escaped participants leave active combat and any queued combat
action for them is cancelled. Stances persist for the
encounter and trade offense, defense, damage, and escape stamina cost. Once combat starts,
active participants keep queuing basic attacks automatically every few game seconds until the
encounter ends, but you can still replace your next queued primary action with an explicit command.
Guarding can redirect
incoming melee attacks, while ranged shots record their range without using guard interception.
Reaction policy controls whether the character automatically spends a bounded defensive reaction
when attacked. If a character becomes unable to act before a committed wind-up resolves, that
action is interrupted instead of taking effect. Some strong hits can apply short-lived combat
status effects that expire on game time. NPC attention is tracked as broad cues, so enemies may
keep pressure on the participant who has drawn the most notice. Assisting another player joins
their active encounter and marks you as a participant for later rewards and audit history.
Room terrain and authored cover can also help the defender: dense forest, mountain paths, swampy
ground, or explicit cover in a room can raise the target's defense score. This is ambient and
automatic; you do not choose cover positions or manage range bands.

Some authored actions can also set up or spend a combo follow-up. For example, one move might
create an opening and another move might consume that opening for a temporary accuracy or damage
bonus. This is action behavior, not a separate command you have to maintain.

Special arena or boss encounters may use simultaneous-planning mode. In those fights, the NPC
commits a response as soon as you commit your action, and both actions share the same resolve
time. You still use the same combat commands; the mode changes encounter pacing, not controls.

In the browser, combat appears as prose in the feed plus structured state updates used to keep
participants, statuses, stances, attention cues, and recent outcomes current. A committed action
may appear before it resolves; that delay is the wind-up/recovery model working as intended.
Downed, defeated, or escaped participants can remain visible in combat state so the outcome is
clear instead of disappearing from the encounter record.

## Getting Help In-Game

The `help` command is your in-game reference:

- **`help`** — a short list of the most common commands to get you started, plus
  pointers to the fuller help below. (During a conversation or combat it instead shows
  the commands that apply right now.)
- **`help commands`** — every command available to you, grouped by category (Movement,
  Social, Items & Inventory, Trade, …) and alphabetized within each group.
- **`help <command>`** — detail on one command: its usage, aliases, category, and scope
  (e.g. `help go`, `help buy`).
- **`help topics`** — browse the help **articles**: longer explanations of systems like
  movement, trading, quests, and rest. Each is listed as `[id] name — Title`.
- **`help topics <word>`** — search the articles by name, title, or keyword
  (e.g. `help topics money`).
- **`help <id>` or `help <name>`** — read a specific article, by its number or its name
  (e.g. `help 6` or `help trading`).

## Full Command Reference

This list is generated from the same `help` text the game shows you in-session — type
`help commands` any time for the live, context-aware version (it hides commands that don't
apply right now, e.g. dialogue-only commands when you're not in a conversation).

| Command | Aliases | What it does |
|---------|---------|----------------|
| `go <direction>` | `north`/`south`/`east`/`west` (bare) | Move to an adjacent room |
| `where <room>` | | Show the shortest known path to a room |
| `unlock <direction>` | | Unlock an exit if you carry its key |
| `lock <direction>` | | Lock an exit if you carry its key |
| `pick <direction>` | | Pick a locked exit without its key (requires the Pick Locks ability) |
| `follow <player>` | | Move with a player when they move (bare `follow` shows status) |
| `unfollow` | | Stop following |
| `look` | | Describe your surroundings |
| `examine <item>` | `inspect`, `x` | Read an item's description |
| `take <item>` | | Pick up an item (`2 <item>`, `all <item>` also work) |
| `drop <item>` | | Put down a carried item |
| `inventory` | | List what you're carrying |
| `use <item> [on/with <other>]` | | Use an item, optionally combined with another |
| `give <item> to <name>` | | Hand a carried item to an NPC |
| `open <container>` | | Open a container |
| `close <container>` | | Close a container |
| `put <item> in <container>` | | Place a carried item into an open container |
| `take <item> from <container>` | | Take an item out of a container |
| `wear <item>` | | Equip a worn item (armor, clothing) |
| `remove <item>` | | Unequip a worn item |
| `wield <item>` | | Equip a wielded item (weapon, tool, light) |
| `attack <target>` | `fight` | Commit to a scheduled attack against a nearby NPC |
| `shoot <target>` | `fire` | Commit to a scheduled ranged attack against a nearby NPC |
| `consider <target>` | `con` | Appraise a nearby opponent before a fight |
| `defend` | `guard` | Spend your next combat action bracing against attacks |
| `assist <player>` | | Join a nearby player's active encounter on their side |
| `flee` | | Commit to an escape attempt from the current encounter |
| `unwield <item>` | | Unequip a wielded item |
| `equipment` | `eq` | List what you're wearing and wielding |
| `body` | `condition` | Show every wear slot and active body-part wounds |
| `light <item>` | | Light a light source |
| `extinguish <item>` | | Put out a lit light source |
| `turn <item>` | `pull`, `activate` | Cycle a lever or dial to its next state |
| `traits` | | List your active traits |
| `disciplines` | `skills` | List your disciplines and your rank in each |
| `reputation` | `rep` | List your standing with NPCs and factions |
| `score` | | Your progress: level/xp, quests, wealth, reputation, discoveries |
| `search` | | Look for hidden exits and secrets in the room |
| `journal` | | Review places visited, people met, items discovered, lore learned, and active quests |
| `marks` | | List the marks you have earned by discovery |
| `train [ability]` | `learn` | Spend skill points to unlock an ability (no arg lists what's trainable) |
| `abilities` | `abils` | List the abilities you know and what you can currently train |
| `forage` | | Search the wild outdoors for something edible (requires the Forage ability) |
| `sense` | `perceive` | A keen perception sweep of the room (requires the Keen Senses ability) |
| `rest` | | Catch your breath and recover a little stamina |
| `camp` | | Make camp and recover a good deal of stamina |
| `sleep` | | Sleep deeply and recover all your stamina |
| `list` | `shop` | Show a room's shop stock and prices |
| `buy <item> [qty]` | | Purchase an item from a room's shop |
| `sell <item> [qty]` | | Sell a carried item to a room's shop |
| `appraise <item>` | | Estimate an item's coin value |
| `deposit <amount>` | | Deposit carried coins at a bank branch |
| `withdraw <amount>` | | Withdraw banked coins at a bank branch |
| `balance` | | Show coins carried and banked |
| `offer <item\|N coins> to <player>` | | Pledge something to a pending trade |
| `accept` | | Finalize your pending trade |
| `decline` | | Call off your pending trade |
| `board [line]` | | Board a transit vehicle docked at this station |
| `disembark` | `leave` | Leave a transit vehicle at its current stop |
| `schedule [line]` | `timetable` | Show a transit line's stops and current status |
| `talk <name>` | `speak` | Start a conversation with an NPC |
| `choice <number>` | `choose` | Pick a dialogue reply |
| `bye` | `farewell`, `goodbye` | End the current conversation |
| `say <message>` | | Speak aloud to the room |
| `tell <player> <message>` | `whisper` | Private message to an online player |
| `newbie <message>` | | Speak on the world-wide Newbie channel |
| `who` | | List players online across the whole game |
| `news` | `/news` | Show current announcements |
| `report <description>` | `/report <description>` | Report a bug or issue to the developers |
| `save [slot]` | | Save your progress |
| `load [slot]` | | Load a saved game |
| `help [command\|commands]` | `?` | Common commands, the full grouped list, or detail on one |
| `help topics [search]` | | Browse/search help articles; `help <id\|name>` reads one |
| `quit` | | Return to the lobby |

## Tips & Troubleshooting

- **"Go where?" / "Take what?"** — you left off the argument; the command needs an
  object (`go north`, not just `go`).
- **"There is no X here."** — check the room description or `look` again; the item/NPC
  might have been taken by someone else or isn't actually in this room.
- **Numbered disambiguation prompt** — just reply with the number, or repeat the command
  with a more specific name.
- **Command bar not focused?** — press `/` anywhere on the page, or click into the input.
- **Combat, trading, and player-vs-player** are not implemented yet — commands related to
  them don't exist in the current build. See `docs/roadmap.md` for what's coming.
