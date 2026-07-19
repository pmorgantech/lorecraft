# Scavenger hunt events — design (Sprint 48)

**Goal:** a scheduled, time-boxed world event — a themed set of clue items is placed across a
pool of rooms, and players hunt them down for a reward (coins, lore). The simplest *non-instanced*
slice of the wishlist's *Instanced minigames / scenarios* idea: pure content on existing
primitives (scheduler, item spawns, flags/journal, news), **no new engine mechanism**.

Roadmap: [Sprint 48](../project/roadmap.md#sprint-48--scavenger-hunt-events-design-first).

## What it reuses (nothing new in Tier 1)

| Need | Existing primitive |
|---|---|
| *When* a hunt opens/closes | `SchedulerService.schedule(job_type, at_game_epoch, payload)` → `SCHEDULED_JOB_DUE`, or a manual/admin call |
| Placing clue items | `ItemLocationService.spawn(item_id, Location("room", room_id))` |
| Detecting a find | the `ITEM_TAKEN` event (already fired by every `take` path) |
| Per-player progress | **player flags** (`hunt:<id>:found:<item>`, `hunt:<id>:done`) — persist through save/load, surface in the journal, no new table |
| Reward | `LedgerService` (coins) + a lore/flag set |
| Announcement | a **news item** (persistent, synchronous DB write) — not a live broadcast, which sidesteps the async-from-scheduler problem entirely |
| Seedable placement | `GameRng` (deterministic room choice for audit-regression) |

## Why news, not a live broadcast

Opening/closing is driven by the scheduler, whose `SCHEDULED_JOB_DUE` handler runs **synchronously**
(the event bus is sync) and has no async event loop to `await manager.broadcast_*`. Rather than
thread a deferred-delivery seam through the scheduler, hunt announcements are **news items**: a
synchronous DB write players see via the existing `news` command / news panel. Completion is
announced the same way. A live "a hunt has begun!" feed ping is a deliberate non-goal for v1
(add later via the Sprint 47 `pending_deliveries` seam if wanted).

## Hunt definition (YAML)

Loaded from `world_content/hunts.yaml` (env-overridable, like the world/news/help mirrors) into an
in-memory registry at startup — the weather/terrain-def pattern. Pydantic-validated.

```yaml
version: 1
hunts:
  - id: harvest_trinkets
    name: "The Harvest Trinket Hunt"
    description: "Five lost trinkets are scattered about Ashmoore. Find them all."
    clue_items: [trinket_acorn, trinket_bell, trinket_feather]   # Item ids to find
    spawn_rooms: [village_square, market_stalls, wandering_crow_inn]  # room-id pool
    spread_items: true              # avoid reusing rooms while rooms remain
    reward:
      coins: 50                     # fallback when no speed tier matches
      lore: harvest_trinkets            # sets flag lore:harvest_trinkets (journal-visible)
      tiers:
        - max_elapsed_seconds: 60
          coins: 2000
        - max_elapsed_seconds: 120
          coins: 250
        - max_elapsed_seconds: 300
          coins: 100
    duration_ticks: 240                 # closes this many game-ticks after opening
```

- **Placement:** on open, each `clue_items` entry is spawned into a room chosen from `spawn_rooms`
  by the seeded `GameRng` (deterministic). Fewer rooms than items → items share rooms; more rooms →
  a random subset is used. Set `spread_items: true` to choose without replacement while unused
  rooms remain, which is useful for authored 3-7 item hunts that should be distributed between
  rooms.
- **Completion rule (v1):** find *all* `clue_items`. (A `find_count: N` variant is a trivial later
  extension — the progress check already counts found flags.)
- **Timed rewards:** `reward.tiers` is optional. The timer starts when a player finds their first
  clue item for that hunt and uses game-clock seconds. The first tier where
  `elapsed < max_elapsed_seconds` wins; otherwise `reward.coins` is paid as the fallback.

## Lifecycle

1. **Open** — `HuntService.open(hunt_id, session, rng)`: spawn the clue items, set world flag
   `hunt:<id>:open` (on `WorldMeta`-style state / a small in-memory active-set + a scheduled close
   job), write an "opened" news item, and schedule the close job at `now + duration_ticks`.
2. **Hunt** — `ITEM_TAKEN` handler: if the taken item is a clue of an *open* hunt, set
   `player.flags["hunt:<id>:started_epoch"]` on the first clue and
   `player.flags["hunt:<id>:found:<item>"]` on every clue. If the player now holds all clue flags
   and isn't already `hunt:<id>:done`, choose the timed coin tier, grant the reward (coins + lore
   flag), set `hunt:<id>:done`, and `ctx.say` the payoff to the finder.
3. **Close** — `HuntService.close(hunt_id, session)`: despawn any un-taken clue stacks still in the
   pool rooms, clear the open flag, write a "closed" news item. Player `done`/`found` flags remain
   (a record of participation; the journal can surface completed hunts later).

## Storage decision: flags, not a table

Per-player progress is **player flags**, not a new `HuntProgress` table:
- Flags already persist through `SaveSlot` and are journal-visible — zero new persistence code.
- A hunt has a handful of clue items; the flag set per player is tiny.
- The only global state is "which hunts are open" + each open hunt's close job — held in a small
  in-memory active-set on the `HuntService` (rebuilt from pending scheduler jobs isn't needed for
  v1; a server restart mid-hunt simply ends it, acceptable for a time-boxed event).

## Content-lint (48.2)

A validator (in `tools/validators.py` / the hunts loader) checks each hunt:
- every `clue_items` id resolves to a real `Item`;
- every `spawn_rooms` id resolves to a real `Room`;
- `reward.coins >= 0`; reward-tier `coins >= 0`; tier thresholds are positive;
  `duration_ticks > 0`; ids unique.

Wired into the world-content lint path so a bad hunt file fails fast, like room/item content.

## Feature package (Tier 2, auto-discovered)

`features/hunts/`:
- `__init__.py` — `FeatureManifest(key="hunts")` + `register_feature`.
- `models.py` — Pydantic `HuntDef` / `HuntsDocument` + loader/validator.
- `service.py` — `HuntService`: registry, `open`/`close`, `ITEM_TAKEN` handler, reward grant.
- `commands.py` — (optional) a read-only `hunts` verb listing open hunts + your progress.

## Non-goals (v1)

- No instancing / private copies (that's the larger wishlist idea this is the simple slice of).
- No live feed broadcast on open (news item only).
- No admin-console authoring UI (YAML-authored; an admin *trigger* to open on demand is fine).
- Completion rule is "find all" only (count/target variants are later, trivial extensions).
