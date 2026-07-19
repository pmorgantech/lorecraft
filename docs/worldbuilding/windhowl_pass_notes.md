# Windhowl Pass — Design Notes

Source material for the `windhowl_pass` zone (12 rooms, branching east off `ashmoore`'s
`ruined_chapel`). This is the original design brainstorm, annotated with what shipped as
world content (`world_content/world.yaml`) versus what's backlogged pending new engine
mechanics (tracked in `docs/wishlist.md`). Keep this doc as the reference for finishing the
backlogged pieces later — it has the full NPC/item/mechanic detail the terser wishlist
entry doesn't repeat.

## Lore hook

A narrow, high-altitude mountain route infamous for constant, shrieking wind that can strip
skin from exposed flesh in a violent gust. The dead are said to linger, their voices carried
on the wind, sometimes calling travelers by name. It's the shortest path between the
lowlands and the high valleys beyond — and has a reputation for claiming more lives than it
lets through. Some say the wind itself is alive, and hungry.

## Rooms — shipped

All 12 rooms below are live in `world_content/world.yaml` (zone `windhowl_pass`, map block
`x[12,16] y[3,7] z[-1,0]`, clear of every other zone's coordinate range):

- **Southern Approach** — entry point, west exit to `ruined_chapel` (ashmoore).
- **The Howling Narrows** — carved warning scenery item: "Do not speak your name aloud."
- **Stonewatch Ruins** — Elara Voss shelters here.
- **The Whispering Crevice** — dead-end, muted wind, wind-smoothed wall grooves.
- **High Ridge** — hub: narrows, summit approach, avalanche chute (down), cave entrance (east).
- **Summit Approach**
- **The Crown** — standing-stone scenery item; one-way risky drop down to Avalanche Chute.
- **Avalanche Chute** — reciprocal only with High Ridge (the Crown's drop is intentionally
  one-way, signposted in both rooms' text).
- **Eastern Wind Caves Entrance**
- **The Breathing Tunnels** — Old Man Gale lives here.
- **The Hollow Chamber** — the central pit is described but not enterable (see backlog).
- **Collapsed Gallery** — dead-end, unstable.

## NPCs — shipped

- **Elara Voss** (`elara_voss`, Stonewatch Ruins) — trapped caravan survivor, quest giver.
- **Old Man Gale** (`old_man_gale`, Breathing Tunnels) — wind-mad hermit, teaches "reading
  the wind."
- **The Listener** (`the_listener`, patrols Crown/Narrows/Hollow Chamber) — cryptic spirit,
  flavor-only dialogue (no quest tie — the "Name in the Wind" chain it was designed for is
  backlogged, see below).

## Quest — shipped (partial)

`windhowl_survivors_crossing` ("The Survivor's Crossing") ships **stages 1–2 only** of the
originally designed 4-stage chain:

1. ~~"A Voice in the Wind"~~ — folded into Elara's dialogue (`elara_plea_heard` flag +
   `start_quest`), not a separate stage.
2. **"Read the Wind"** (shipped as `learn_from_gale`) — talk to Old Man Gale, he teaches you
   and gives a `windworn_token` keepsake.
3. **"The High Crossing"** — **NOT SHIPPED.** Original design: escort Elara across High
   Ridge → Summit Approach → The Crown, with wind events forcing player choices
   (tie her down, shield her, use items). No escort/follow mechanic exists, and no
   wind-intensity event system exists to drive the choices. This is the main backlog item.
4. **"What She Carried"** — shipped in simplified form as `report_to_elara`: instead of
   surviving an escorted crossing, the player just needs to have learned from Gale and
   returns to tell Elara, who hands over the sealed letter directly. The original
   "success/failure changes what happens to Elara" branching is gone since there's no
   crossing event to succeed or fail at.

The sealed letter (`sealed_letter_for_northern_valleys`) is addressed to "someone in the
valleys beyond the mountains" — there is no delivery stage or destination room, since
Windhowl Pass doesn't yet lead anywhere (per the brief, it "should eventually lead to yet
another zone but for now can exist on its own"). When that zone is built, add a delivery
stage/NPC there and a `next_stage` off `report_to_elara`.

## Backlog — needs new mechanics (see `docs/wishlist.md` for the tracked summary)

### Wind-intensity system

The original design's whole point — wind strength varying by time of day/weather/event,
gusts that knock players down, blow items away, or gate certain paths — needs:

- A `WindIntensityUpdate`-style scheduler job (hourly, mirrors `WeatherFrontService`).
- An `EventBus` event (e.g. `WIND_INTENSITY_CHANGED`) other systems can react to.
- A "Dead Calm" rare event (1–2% chance/night) — total silence, voices stop, the Hollow
  Chamber's pit becomes accessible.
- Time/weather table from the original brief:

  | Time / condition | Wind strength | Effects | Scheduler hook |
  |---|---|---|---|
  | Dawn | Low | Easier movement, rare voices | Low chance of "Quiet Hour" |
  | Midday | Medium | Normal | Occasional strong gusts |
  | Dusk | Rising | Reduced visibility | Wind "wakes up" |
  | Night | High | Strong gusts, frequent voices | Nightly "Night Howl" event |
  | Storm/special event | Extreme | Knockback risk, movement penalty | Triggered by world events |
  | Rare "Dead Calm" | None | Voices stop, unsettling silence | ~1–2%/night |

### The Voices / Name Taboo

Wind carries fragments of speech, sometimes calling the player by name, sometimes repeating
a dead traveler's last words, occasionally trying to lure someone off the path. The carved
warning in the Narrows ("Do not speak your name aloud") is real lore but has no mechanical
consequence yet — speaking a true name in the pass doesn't do anything. Needs a "spoken name"
detection hook plus a wind-spirit reaction system.

### The Hollow Chamber pit

Described as inaccessible depths with faint flickering lights. Becomes enterable only during
Dead Calm per the original design — blocked on the Dead Calm event above.

### Quest Chain 2 — "The Name in the Wind" (not started)

Mystery chain: The Listener asks the player to find the true names of three people who died
in the pass; Old Man Gale knows one but demands a favor. Optional dark branch leads to the
Hollow Chamber pit revealing something has been "collecting" names and voices for a long
time. Needs: the name-taboo mechanic above, a `Name-Bound Cord` quest item (cord that
tightens when a true name is spoken nearby — needs the same detection hook), and the pit
being enterable.

### Quest Chain 3 — "What Sleeps Below" (not started)

Time-affected chain spanning multiple in-game days: something ancient sleeps at the bottom
of the pit; The Listener wants to wake it, Old Man Gale wants it to stay asleep. Needs Dead
Calm (recurring, not one-off) plus a multi-day quest-state mechanic beyond what
`timeout_ticks`/`on_timeout` currently offers (this is closer to a standing world-state flag
than a single quest timer).

### Items not built (all need the wind-intensity system, Dead Calm, or Chain 2/3 above)

| Item | Blocked on |
|---|---|
| Galecloak | Wind knockback/damage system |
| Windwhisper Charm | Voices mechanic |
| Howlstone | Wind-intensity events (early warning + throwable gust attack) |
| Echo of the Lost | Time-conditional item examine text (WorldClock-gated) |
| Breath of the Mountain | Dead Calm (collected only during it) |
| Name-Bound Cord | Name-taboo mechanic (Chain 2) |
| Stormheart Fragment | Wind-state combat damage modifier |
| Stillwind Vial | Dead Calm + a "suppress wind effects" mechanic |

`windworn_token` and `sealed_letter_for_northern_valleys` **are** built (flavor-only /
quest-handoff items, no missing mechanic required).
