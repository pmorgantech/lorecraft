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
| **Mini-map** (bottom-left) | Rooms you've visited, with fog of war over unexplored areas. |
| **The Chronicle** (center) | The live narrative feed — your actions, other players' actions, and room events, in order. |
| **Here Now** (top-right) | Players currently in your room / online. |
| **Quests** (bottom-right) | Your active quests and current stage description. |
| **Command bar** (bottom) | Type a command and press Enter or click **Send**. Press `/` anywhere to jump focus into it. |

When an NPC conversation is active, a dialogue overlay appears above the command bar with
the NPC's line and numbered reply buttons — see [Talking to NPCs](#talking-to-npcs--quests).

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
```

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
