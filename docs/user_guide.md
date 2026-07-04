# Lorecraft Player Guide

A guide to playing Lorecraft in the browser: creating a character, moving around, talking
to NPCs, and the full command list.

## Table of Contents

1. [Getting Started](#getting-started)
2. [The Game Screen](#the-game-screen)
3. [Movement](#movement)
4. [Looking, Taking, and Using Items](#looking-taking-and-using-items)
5. [Talking to NPCs & Quests](#talking-to-npcs--quests)
6. [Chat & Social](#chat--social)
7. [Saving, Quitting, and Reconnecting](#saving-quitting-and-reconnecting)
8. [News](#news)
9. [Full Command Reference](#full-command-reference)
10. [Tips & Troubleshooting](#tips--troubleshooting)

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
use the **Room** / **Feed** / **Players** tabs at the bottom to switch between them.

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

If an exit is locked, `unlock <direction>` works if you're carrying the right key, and
`lock <direction>` locks it back up.

```
unlock north
go north
```

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
light lantern             — light a light source
extinguish lantern        — put out a lit light source
```

Worn/wielded gear can grant passive bonuses (stat/skill boosts, extra carry capacity,
traits) while equipped — check an item's description or `examine` it to see what it does.
Carrying too much weight makes you **burdened** (travel costs more) or, past a hard
threshold, **overloaded** (you can't pick up anything else until you drop or stow something).
A room with no ambient light needs an equipped, lit light source (like a lit lantern) or
you can't see to look around, take items, or read descriptions — a lit source slowly burns
through its fuel (durability) over time, so keep spares.

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
journal         — review places visited, people met, lore learned, and active quests
```

Not every exit shows up in a room's description — `search` rolls your perception skill
(better with practice, traits, and equipment) to find hidden passages. Once you've found
one, it stays visible to you from then on. Some exits also need a specific flag (a key
event, an NPC's trust, a quest step) before they'll let you through, whether or not you've
found them. Rooms can also have terrain (forest, mountain, swamp, water...) that requires
a minimum survival skill to enter safely.

## Stamina: Rest, Sleep, and Camp

```
rest            — catch your breath and recover a little stamina
camp            — make camp and recover a good deal of stamina
sleep           — sleep deeply and recover all your stamina
```

Traveling drains your stamina — more so if you're carrying a lot of weight. Running low
saps your skill checks (perception, lockpicking, and the rest), so it pays to top up
before attempting something that matters. `rest` is quick and available almost anywhere;
`camp` restores more but takes longer; `sleep` restores you fully and advances the clock.

Sleeping in an inn or a marked camp is always reliable. Anywhere else it's a gamble — a
survival check, harder in cold weather unless you're dressed for it (a warm cloak or
similar helps). If it goes badly your rest is interrupted: shorter, and only a partial
recovery. A good night's sleep sometimes comes with a dream — occasionally a hint tied to
something you've already discovered.

## Character: Traits, Skills, and Reputation

```
traits          — list your active traits (from equipment, effects, and background)
skills          — list your skills and their current levels
reputation      — list your standing with NPCs and factions (also: rep)
```

Traits are passive bonuses or penalties — some come from what you wear, some from timed
effects, and some are permanent (background or earned through play). Skills improve the
more you use them ("learn by doing") — there's no way to train them directly. Reputation
with an NPC or faction can unlock better prices, new dialogue, or additional quests.

## Trading

```
list            — show a room's shop stock and prices (also: shop)
buy sack        — purchase 1 (or: buy 3 sack — purchase 3)
sell mug        — sell a carried item to the shop here
appraise gem    — estimate what an item is worth in coins
```

Some NPCs run a shop — `list` in their room to see what's for sale. Shops only buy
certain kinds of goods, won't take anything soulbound, and have real (finite) cash — sell
too much in one place and they'll run dry. The `bartering` skill and your standing with
the vendor both shave a little off the price over time. Prices also vary by place —
the same goods can cost more or less depending on where you are, so it pays to know the
routes.

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

## Talking to NPCs & Quests

```
talk mira        — start a conversation (also: speak)
1                 — pick reply #1 (or: choice 1, choose 1)
bye               — end the conversation (also: farewell, goodbye)
```

The dialogue overlay shows the NPC's current line and numbered choices — click a choice
button or type its number. Some choices start or advance quests; check the **Quests**
panel in the right sidebar to see what you're currently tracking and what to do next.

## Chat & Social

```
say hello         — speak aloud; everyone in the room sees it
```

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
```

Announcements are also available outside the game as an RSS feed at `/api/news/feed`,
if you want to follow them in a feed reader.

## Full Command Reference

This list is generated from the same `help` text the game shows you in-session — type
`help` any time for the live, context-aware version (it hides commands that don't apply
right now, e.g. dialogue-only commands when you're not in a conversation).

| Command | Aliases | What it does |
|---------|---------|----------------|
| `go <direction>` | `north`/`south`/`east`/`west` (bare) | Move to an adjacent room |
| `unlock <direction>` | | Unlock an exit if you carry its key |
| `lock <direction>` | | Lock an exit if you carry its key |
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
| `unwield <item>` | | Unequip a wielded item |
| `equipment` | `eq` | List what you're wearing and wielding |
| `light <item>` | | Light a light source |
| `extinguish <item>` | | Put out a lit light source |
| `traits` | | List your active traits |
| `skills` | | List your skills and their levels |
| `reputation` | `rep` | List your standing with NPCs and factions |
| `search` | | Look for hidden exits and secrets in the room |
| `journal` | | Review places visited, people met, lore learned, and active quests |
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
| `news` | | Show current announcements |
| `save [slot]` | | Save your progress |
| `load [slot]` | | Load a saved game |
| `help` | `?` | Show the command list (context-aware) |
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
