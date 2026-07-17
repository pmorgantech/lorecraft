---
kindle_doc_weaver: ignore
---

# Lorecraft Admin & Builder Guide

An operational guide for running a Lorecraft server, moderating players, and building
world content. This is the entry point — it links out to the deeper implementation docs
for each subsystem rather than duplicating them.

## Table of Contents

1. [Audiences](#audiences)
2. [Running the Server](#running-the-server)
3. [Configuration Reference](#configuration-reference)
4. [Admin Access](#admin-access)
5. [Admin Web Panel Tour](#admin-web-panel-tour)
6. [Admin TUI](#admin-tui)
7. [Building World Content](#building-world-content)
8. [The World CLI](#the-world-cli)
9. [Publishing World Changes Safely (Changesets)](#publishing-world-changes-safely-changesets)
10. [Moderating Players](#moderating-players)
11. [Issues & News](#issues--news)
12. [Analytics](#analytics)
13. [Extending the UI: Feature Panels](#extending-the-ui-feature-panels)
14. [Troubleshooting](#troubleshooting)
15. [Related Docs](#related-docs)

---

## Audiences

- **Server operator** — runs the process, manages env vars/secrets, applies DB
  migrations, watches logs.
- **World builder** — writes/edits `world_content/world.yaml` (rooms, items, NPCs,
  dialogue, quests), validates and imports it.
- **Moderator** — uses the admin web panel or TUI to watch players, teleport/freeze,
  and read the audit log.

One person often wears all three hats on a small deployment.

## Running the Server

Dev quick start:

```bash
./start.sh
```

This bootstraps a `.venv`, installs Lorecraft editably (with the admin TUI extra), copies
the repo-tracked seed DBs (`test_dbs/lorecraft-dev-game.db`,
`test_dbs/lorecraft-dev-audit.db`) into `/tmp`, and runs `uvicorn` on `127.0.0.1:8000`.

If the seed DBs don't exist yet (fresh checkout, or you deleted them), bootstrap them
first:

```bash
./start.sh --init-dbs-if-missing   # create missing seed DBs, then launch
./start.sh --init-dbs-only         # create missing seed DBs, then exit (no launch)
```

Useful flags:

| Flag | Purpose |
|------|---------|
| `--init-dbs-if-missing` | Create the seed game/audit DBs if they don't exist yet |
| `--init-dbs-only` | Same, but exit instead of launching the server |
| `--world-dir PATH` / `--world PATH` | Import from a different world YAML directory/file (default: `world_content/`) |
| `--game-db PATH` | Override the seed game DB path (default: `test_dbs/lorecraft-dev-game.db`) |
| `--audit-db PATH` | Override the seed audit DB path (default: `test_dbs/lorecraft-dev-audit.db`) |

For a from-scratch import without `start.sh` (e.g. into a real deployment DB), see
[The World CLI](#the-world-cli).

## Configuration Reference

All settings are environment variables (loaded via `.env` in the repo root if present),
defined in `src/lorecraft/config.py`.

| Variable | Default | Notes |
|----------|---------|-------|
| `LORECRAFT_DB_PATH` | `game.db` | Game database path |
| `LORECRAFT_AUDIT_DB_PATH` | `audit.db` | Audit log database path |
| `LORECRAFT_DB_POOL_SIZE` | `5` | SQLAlchemy connection-pool size. **Applies only to a networked backend** (Postgres/MySQL) — ignored for SQLite (single-writer). Raise for many concurrent players. |
| `LORECRAFT_DB_POOL_RECYCLE` | `1800` (30 min) | Recycle pooled connections older than this many seconds (avoids stale server-side connections); `-1` disables. Networked backends only. |
| `LORECRAFT_DB_SQLITE_WAL` | `true` | Enable SQLite **WAL** journal mode — makes every commit cheap (append + periodic checkpoint) instead of a full fsync per commit (~20–29× faster scheduler ticks, ~4–6× faster commands under load). SQLite only. Turn off only for network filesystems, which don't support WAL. |
| `LORECRAFT_DB_SQLITE_SYNCHRONOUS` | `NORMAL` | SQLite `synchronous` pragma (`OFF`/`NORMAL`/`FULL`/`EXTRA`). `NORMAL` under WAL is safe against app crashes and can lose only the last transaction(s) on OS crash / power loss. Set `FULL` for full durability (still faster than the old default). SQLite only. |
| `LORECRAFT_DB_QUERY_LOG_ENABLED` | `true` | Write SQLAlchemy cursor timing spans to a non-DB JSONL log for query tuning. |
| `LORECRAFT_DB_QUERY_LOG_PATH` | `logs/sql_queries.log` | Query-span log path. Generated `*.log` files are ignored by git. |
| `LORECRAFT_DB_QUERY_SLOW_MS` | `50.0` | Slow-query threshold stamped on query-span records. |
| `LORECRAFT_WORLD_TIME_RATIO` | `60.0` | In-game seconds per real second |
| `LORECRAFT_WEBSOCKET_PATH` | `/ws` | Player WebSocket endpoint |
| `LORECRAFT_DISCONNECT_GRACE_SECONDS` | `60.0` | Grace period before a dropped connection is treated as a real disconnect |
| `LORECRAFT_ADMIN_JWT_SECRET` | *(unset)* | **Set this in production.** If unset, an ephemeral random secret is generated per process — admin tokens won't survive a restart, and a warning is logged. |
| `LORECRAFT_ADMIN_JWT_ACCESS_TTL` | `900` (15 min) | Admin access token lifetime, seconds |
| `LORECRAFT_ADMIN_JWT_REFRESH_TTL` | `28800` (8 hr) | Admin refresh token lifetime, seconds |
| `LORECRAFT_ADMIN_SEED_USERNAME` | `admin` | Seed admin account created on first startup if both seed vars are set |
| `LORECRAFT_ADMIN_SEED_PASSWORD` | `admin` | **Change this before exposing the server.** The default is `admin`/`admin`. |
| `LORECRAFT_ADMIN_SEED_ROLE` | `superadmin` | Role for the seed account |
| `LORECRAFT_WORLD_YAML_PATH` | `world_content/world.yaml` | World file imported into an empty game DB on startup |
| `LORECRAFT_ISSUES_YAML_PATH` | `docs/issues.yaml` | Repo-tracked issue list, synced to DB |
| `LORECRAFT_NEWS_YAML_PATH` | `docs/news.yaml` | Repo-tracked announcements, synced to DB |
| `LORECRAFT_HELP_YAML_PATH` | `docs/help_topics.yaml` | Repo-tracked in-game help articles, imported into the DB on first startup |
| `LORECRAFT_SEED_PLAYER_ID` / `_USERNAME` / `_START_ROOM` | `player-1` / `player-1` / `village_square` | Optional dev player auto-created on startup |
| `LORECRAFT_PLAYER_SESSION_SECRET` | *(unset)* | Signs player session cookies (and player access/refresh JWTs); auto-generated and persisted to `.env` on first real server startup if unset |
| `LORECRAFT_PLAYER_SESSION_TTL_SECONDS` | `604800` (7 days) | Player session cookie lifetime |
| `LORECRAFT_PLAYER_ACCESS_TTL` | `900` (15 min) | Player API access token lifetime, seconds (`POST /auth/login`/`/auth/refresh`) |
| `LORECRAFT_PLAYER_REFRESH_TTL` | `28800` (8 hr) | Player API refresh token lifetime, seconds |
| `LORECRAFT_PLAYER_WS_TICKET_TTL_SECONDS` | `60.0` | Single-use `POST /auth/ws-ticket` ticket lifetime before the `/ws` handshake must consume it |
| `LORECRAFT_ALLOW_QUERY_PLAYER_ID` | `false` (Sprint 4) | Dev/test fallback: trusts `?player_id=` (HTTP) and `/ws?player_id=` (WebSocket) without a signed session or ws-ticket. Off by default since Sprint 4 shipped real password login + WS tickets — only turn on for local dev/test convenience, never on a public server. |
| `LORECRAFT_FEATURES` | *(unset → all on)* | Comma-separated Tier 2 feature keys to enable (e.g. `movement,inventory,npc,quests`). Unset means every discovered feature is on (the shipped default). A whitelist — to *disable* one feature, list all the others. Declared dependencies (`equipment`→`traits`, `containers`→`item_components`) must be included or startup fails. See [Extending the UI](#extending-the-ui-feature-panels) and `docs/architecture_tiers.md` §5. |

**Before exposing a server publicly:** set `LORECRAFT_ADMIN_JWT_SECRET` and
`LORECRAFT_PLAYER_SESSION_SECRET` to real secrets, change `LORECRAFT_ADMIN_SEED_PASSWORD`
from the `admin` default, and leave `LORECRAFT_ALLOW_QUERY_PLAYER_ID` at its `false`
default (only ever set it `true` for local dev).

## Admin Access

There are two admin clients: a web panel and a terminal (TUI) client. Both authenticate
against the same JWT-based admin API (`POST /admin/auth/token` with `{username,
password}`, returning access + refresh tokens).

- **Web panel:** `http://<host>:8000/admin`. Log in with the seed admin credentials
  (or an account created later via the Accounts tab). The JWT is kept in
  `sessionStorage` — closing the tab logs you out.
- **TUI:** see [Admin TUI](#admin-tui) below.

## Admin Web Panel Tour

The web panel is organized as title-bar categories with contextual sub-tabs:
**Overview**, **Tuning**, **World**, **Content**, **Moderation**, and **System**. Most
sub-tabs are backed by REST endpoints under `/admin/*`:

| Tab | What you can do | Key endpoints |
|-----|------------------|----------------|
| **Dashboard** | Live player table, auto-refreshed over `/admin/ws`; search/status filters; player record editing; body/equipment snapshots; support actions for healing, revitalizing, timed buffs, and bestowing coins/items; read-only Observe panel with player snapshot, recent player audit events, and a live outbound message stream. Player-affecting edits require an admin reason and write structured `admin_action` audit rows. | `GET /admin/players`, `GET /admin/players/{id}/state`, `GET /admin/players/{id}/observe`, `PATCH /admin/players/{id}`, `POST /admin/players/{id}/heal`, `/revitalize`, `/buff`, `/bestow`, `/admin/ws` |
| **Audit** | Paginated, filterable audit log; row-expand payload; correlation-ID session replay. **Live-updates** as players act (each executed command pushes over `/admin/ws`) — toggle with the **Live** checkbox, or use the **↻ Refresh** button to reload on demand. Command summaries show the full command as typed (e.g. `Command executed: go east`, not just the verb). Severity/source facets are loaded from the audit DB. | `GET /admin/audit`, `GET /admin/audit/facets`, `GET /admin/audit/session/{correlation_id}` |
| **World** | Room search + inline editor (optimistic locking), item definition list/create/edit form, read-only NPC data, NPC spawn/despawn | `GET/PUT/POST /admin/world/rooms`, `GET/POST/PUT /admin/world/items`, `GET /admin/world/npcs`, `POST /admin/npcs/{id}/spawn` |
| **NPC/AI** | Read-only NPC runtime dashboard: current room, behavior, HP, autonomous AI config, schedule count, triggers, context commands, and escort state. Control actions remain intentionally absent until safety/audit gates exist. | `GET /admin/world/npcs` |
| **Changesets** | Draft → scan → promote workflow; conflict list | `POST /admin/changesets`, `POST /admin/changesets/{id}/scan`, `POST /admin/changesets/{id}/promote` |
| **Clock** | Live world-clock readout; pause/resume, time-ratio, weather override. A weather override **announces the change to every player's feed** (e.g. "A light rain begins to fall."); re-setting the current weather is silent | `GET/POST /admin/clock`, `/admin/clock/pause`, `/admin/clock/resume`, `/admin/clock/time-ratio`, `/admin/clock/weather` |
| **Combat** | Live-tune combat rulesets. Ruleset editing requires superadmin. Combat damage is tracked as HP loss, not body-part wound records. | `GET /admin/combat/rulesets`, `POST /admin/combat/rulesets/{id}` |
| **Progression** | Live-tune the XP curve (`base`/`step`) and per-level rewards (`coins_per_level`/`skill_points_per_level`) — no restart or reseed. See [Live-tuning progression from the admin console](#live-tuning-progression-from-the-admin-console) | `GET/POST /admin/progression/config` |
| **Economy** | Live-tune each zone's price multiplier (`region_mult`) and per-item price bias — no restart or reseed. Viewing is open to any admin role; editing requires superadmin. See [Region pricing (Sprint 76)](#region-pricing-sprint-76) | `GET /admin/economy/regions`, `POST /admin/economy/regions/{zone}` |
| **Issues** | Repo-tracked issue tracker CRUD. **Resolved/deferred are hidden by default** — a "Hide status" checkbox group toggles any status in/out of view; plus a **priority** filter and a **sort** selector (Priority / Recently updated / Recently created). Filter+sort run client-side (hide/sort choices persist per browser); a header count shows `N shown · M hidden`. `component` is a **registered dropdown** (create + filter), served from `GET /admin/issues/components` and validated on write. Table shows opened-by + created/updated dates (🕑 toggles absolute dates ↔ relative ages); rows expand (click) to description, tags, links, assignee, timestamps. Live-refreshes on any change — admin edits **and** in-game player `report`s | `GET/POST/PUT /admin/issues`, `GET /admin/issues/components` |
| **News** | Announcements CRUD (also feeds the in-game `news` command and `/api/news/feed` RSS) | `GET/POST/PUT/DELETE /admin/news` |
| **Help** | Help-article CRUD (the topics players read via `help topics`/`help <id>`); create form + row-expand inline editor (body/title/category/keywords) + name/title search; every change re-exports `docs/help_topics.yaml` | `GET/POST/PUT/DELETE /admin/help` |
| **Accounts** | Create/revoke admin accounts, assign roles (superadmin only) | `GET/POST /admin/accounts`, `DELETE /admin/accounts/{username}` |
| **System** | Request a graceful engine restart (superadmin only, confirm-gated). An **armed?** badge reflects whether the process supervisor is actually watching this instance; if not armed the request is refused (409) rather than silently dropped. The System panel also shows basic health counters and a pending scheduler timeline. See [Restarting the Engine](#restarting-the-engine) | `GET/POST /admin/ops/restart`, `GET /admin/system/health`, `GET /admin/system/scheduler` |
| **Builder Studio / Console / Alerts** | Scoped destinations for the Admin UI/tooling backlog. These panels are intentionally disabled or link to existing tools until their backend endpoints exist. | See [`roadmap.md`](roadmap.md#admin-ui--tooling-triage-2026-07-16) |

Player moderation actions (teleport, flag edit, freeze/unfreeze, message) live under the
player detail view reached from the Dashboard — see
[Moderating Players](#moderating-players).

The Dashboard's player editor and Observe panel include a **Body / Equipment** section. It
groups every canonical wear/wield slot by body part and shows equipped items or empty slots.
Use this for support/debugging when a player's inventory says they own an item but the slot
state needs inspection.

**Live refresh:** the console keeps an `/admin/ws` push connection open (WS indicator, top-right).
Beyond the Dashboard's live player table, the **Issues**, **News**, and **Help** tabs auto-reload
when their content changes — including edits made by *another* admin, an out-of-band change, or an
in-game player `report` filing a new issue — but only for whichever tab you're currently viewing.
The **Audit** tab likewise live-appends as players run commands (each `command_executed` audit row
pushes an `audit_appended` nudge; the tab re-queries with your current filters, debounced so a burst
of commands coalesces into one refetch). Turn this off with the tab's **Live** checkbox, and reload
by hand with **↻ Refresh**. No manual Search/Refresh needed to see a fresh issue, announcement, help
topic, or player command.

**Session expiry:** access tokens are short-lived (`LORECRAFT_ADMIN_JWT_ACCESS_TTL`, default 900 s / 15 min) and the
console holds no refresh token. When the token expires, the next authenticated action (or the admin
WebSocket reconnecting) is rejected and the console **automatically logs you out** back to the login
screen with a "session expired" notice — clearing the stale token and WS rather than leaving a dead
session on screen. A `403` (valid session, insufficient role) does *not* log you out; it just reports
the missing permission. Log back in to continue.

## Restarting the Engine

The **System** tab can request a graceful restart of the running engine without shelling in.
This only *requests* a restart — the actual work is done by a small **supervisor process**
(`scripts/supervisor.py`) that must be running the server for the button to do anything.

- **How it works.** `start.sh` does a one-time cold-boot (venv, seed DBs, and a runtime-DB
  reseed) and then launches the supervisor, which runs `uvicorn` as a child. Clicking
  **Request Restart** (superadmin, with a confirm prompt) writes a sentinel file to the control
  directory (`LORECRAFT_CONTROL_DIR`, default `/tmp/lorecraft-control`) and audit-logs an
  `engine_restart_requested` event. The supervisor sees the sentinel, sends the child `SIGTERM`,
  waits for uvicorn's graceful lifespan shutdown (so players enter the reconnect **grace period**
  and re-attach seamlessly), then relaunches uvicorn — **without** re-running the reseed, so live
  runtime state (player positions, sessions, world mutations) survives.
- **Armed indicator.** The supervisor publishes a heartbeat; the System tab reads it and shows
  **armed** / **not armed**. If nothing is listening (e.g. you launched bare uvicorn with
  `LORECRAFT_NO_SUPERVISOR=1`), a restart request is refused with a clear 409 rather than silently
  doing nothing.
- **Crash recovery.** Because the supervisor also relaunches on an *unexpected* child exit, a crash
  no longer means permanent downtime. A restart-storm guard caps how many relaunches can happen in a
  short window so a stuck trigger or crash loop can't spin forever.

## Admin TUI

A terminal client (Textual) mirroring most of the web panel, useful over SSH or for
keyboard-driven workflows.

```bash
pip install -e ".[admin-tui]"     # start.sh already does this for you
python -m lorecraft.admin.tui.app
```

On first run it prompts for a server URL + credentials, then stores the token at
`~/.config/lorecraft-admin/credentials.json` (mode `0600`) for silent reuse. Set
`LORECRAFT_ADMIN_URL` to point it at a non-default host. If the saved token expires
or was signed by a previous ephemeral server secret, the next protected request clears
that saved token and returns you to the login screen.

| Key | Screen |
|-----|--------|
| `F1` | Players — live table; teleport, freeze, message |
| `F2` | Audit — tailing log, `/` to filter, `r` to replay a session |
| `F3` | World — room list + field editor, `Ctrl+S` to save |
| `F4` | Changesets — create, scan, promote |
| `F5` | Clock — pause/resume, time-ratio, weather override |
| `F6` | Issues |
| `F7` | News |
| `F8` | Help — help topics (read-only; create/edit via the web panel) |
| `q` | Quit |

## Building World Content

World content lives in YAML (`world_content/world.yaml` by default) and is imported into
the game DB. Two dedicated guides cover authoring in depth — this section is just the
workflow:

1. Edit `world_content/world.yaml` (rooms/exits/items — see
   **[world_building.md](world_building.md)**) and/or add NPCs, dialogue trees, and
   quests (see **[dialogue_npcs_quests.md](dialogue_npcs_quests.md)**).
2. Validate before importing anywhere:
   ```bash
   python -m lorecraft.tools.world_cli validate --file world_content/world.yaml \
     --start-room village_square --strict
   ```
   Catches dangling dialogue references, unreachable rooms, dead item references,
   duplicate item names per room, and oversized item stacks.
3. Import into a database (fresh or incremental):
   ```bash
   python scripts/import_world.py --fresh --db test_dbs/lorecraft-dev-game.db
   ```
   or the equivalent `world_cli import` subcommand (below).
4. Playtest against the imported DB (`./start.sh`, then the golden path in
   `docs/roadmap.md`'s Playtesting section) or run the E2E harness (`make test-e2e`,
   see the Sprint 11 entry in `docs/roadmap.md`).

### Room loot, ambience, climate, spawns, and NPC routes

Rooms can declare one-shot randomized treasure and timed feed flavor directly in
`world_content/world.yaml`:

```yaml
rooms:
  - id: hollow_oak_cache
    loot_table:
      chance: 1.0
      message: A hidden shelf gives up a small cache.
      entries:
        - {item_id: copper_coin, weight: 5, quantity: {min: 1, max: 4}}
        - {item_id: faewrought_token, weight: 1, quantity: 1}
    ambient_events:
      - text: Mist curls low across the moss.
        every_ticks: 4
        chance: 0.65
```

Zone climate lives beside traveling storm fronts in `world_content/weather_fronts.yaml`.
Each seasonal list is weighted by repetition; narration is scoped to occupied outdoor
rooms in that zone:

```yaml
climates:
  whisperwood:
    spring: [fog, light_rain, light_rain, overcast, clear]
    narration:
      fog: Mist gathers between the trunks.
```

Admins can override the live state from the Clock panel: the global weather selector still
sets `WorldClock.weather`, and the Zone climates section sets each configured zone's local
weather without a restart or reseed.

Random NPC population controllers live in `world_content/spawns.yaml`:

```yaml
spawns:
  whisperwood_wisps:
    area: whisperwood
    template: fey_wisp
    max_count: 3
    every_ticks: 6
```

For visible fixed patrols, use NPC `ai.mode: route`; for simpler autonomous movement,
`ai.mode: wander` and `ai.mode: patrol` remain available:

```yaml
npcs:
  - id: forest_scout_wren
    ai:
      mode: route
      route: [whispering_clearing, old_oak_grove, wildflower_glade]
      dwell_ticks: 4
      travel_ticks: 3
      reverses: false
      loop: true
```

For non-movement autonomy, add `ai.actions`. Each action has its own cadence, optional
chance roll, and a room-visible output type:

```yaml
npcs:
  - id: vault_forewoman_cassia
    ai:
      actions:
        - type: say             # say | emote | narrate
          every_ticks: 5
          chance: 0.6
          lines:
            - "No one signs off on a valve repair until the whistle holds pitch."
        - type: emote
          every_ticks: 8
          text: checks a brass clipboard against the nearest pressure dial.
```

NPC `schedule` entries run on `HOUR_CHANGED`. A row may relocate the NPC, change its
`behavior`, replace its autonomous `ai` config, or do any combination of those changes. Use
`ai: {}` to stop a simple autonomous `wander`/`patrol` loop during off hours. Scheduled room
changes are instant state changes, not visible walked routes.

```yaml
npcs:
  - id: night_watch_holt
    behavior: defensive
    schedule:
      - game_hour: 8
        target_room_id: grand_plaza
        behavior: defensive
        ai: {}
      - game_hour: 20
        target_room_id: smithy_district
        behavior: alert
        ai:
          mode: patrol
          move_every: 2
          route: [smithy_district, grand_plaza]
```

### Authoring scavenger hunts (`world_content/hunts.yaml`)

Scavenger hunts are timed world events defined in their own content file, loaded into an
in-memory registry at startup (`LORECRAFT_HUNTS_YAML_PATH` overrides the path). A hunt
spawns clue item definitions into authored rooms only while the hunt is open; players
complete it by taking every clue item.

```yaml
version: 1
hunts:
  - id: harvest_trinkets
    name: The Harvest Trinket Hunt
    description: Seven festival trinkets have gone missing about Ashmoore.
    clue_items:
      - trinket_acorn
      - trinket_bell
    spawn_rooms:
      - village_square
      - market_stalls
    spread_items: true          # choose without replacement while rooms remain
    reward:
      coins: 0                  # fallback if no speed tier matches
      lore: harvest_trinkets    # sets lore:harvest_trinkets
      tiers:
        - max_elapsed_seconds: 60
          coins: 2000
        - max_elapsed_seconds: 120
          coins: 250
        - max_elapsed_seconds: 300
          coins: 100
    duration_ticks: 240
```

Each `clue_items` id must be an item definition in `world_content/world.yaml`, but
those items do not need `room_items` entries. `spawn_rooms` must reference real rooms.
`spread_items: true` is the usual choice for authored 3-7 item hunts; if there are
fewer rooms than clues, later clues fall back to normal seeded random placement.
Timed reward tiers use game-clock seconds from the first clue item a player finds;
the first `elapsed < max_elapsed_seconds` tier wins, otherwise `reward.coins` is
paid.

### Authoring marks (`world_content/marks.yaml`)

Marks (Sprint 53) are discovery badges defined in their own content file, loaded into an
in-memory registry at startup (`LORECRAFT_MARKS_YAML_PATH` overrides the path — the
`hunts.yaml` pattern). Each mark declares **criteria** over the player's journal state
(all populated criteria must hold) and optional **boons** (modest §3.5 modifiers,
active once earned):

```yaml
version: 1
marks:
  - id: far_strider
    name: Mark of the Far Strider
    description: Twelve places known; the road knows you now.
    criteria:              # any of: rooms_visited, rooms_visited_count,
      rooms_visited_count: 12    # npcs_met, items_discovered, flags_set
    boons:                 # optional; key/kind/amount per engine modifier
      - {key: carry_capacity, kind: add, amount: 5}
    # hidden: true         # omit from "???" teasers until earned
```

- Earned state is the `mark:<id>` player flag — no separate table; awards announce in
  the feed and are idempotent. A mark's `flags_set` may reference another mark's
  `mark:<id>` flag to build chains.
- Content-lint (`lint_marks`, enforced by
  `tests/unit/test_marks_models.py::test_shipped_ashmoore_marks_lint_clean_against_world`)
  requires every referenced room/NPC/item to exist in `world.yaml`; flags are free-form.
- Keep boons small and flat (soft-cap principle); useful keys today:
  `carry_capacity`, `skill.<name>`, `warmth`, `meter.<key>.max`.

### Authoring celestial content (`world_content/celestial.yaml`)

Celestial cycles (Sprint 54) derive **moon phase** (8 phases, 16-day month) and **tide**
(low/high, two cycles a day) from the world clock — no new state to author. Content hooks
onto them three ways:

1. **Tide-gated exits** — declare them in `world_content/celestial.yaml`
   (`LORECRAFT_CELESTIAL_YAML_PATH` overrides). The feature locks/unlocks the named exit
   as the tide turns; author the exit's `locked:` in `world.yaml` to match the tide at
   `START_HOUR` (8 → high water):

   ```yaml
   version: 1
   tide_gates:
     - room: creek_crossing
       direction: south
       open_at: low     # exit is unlocked only at this tide
   ```

   Content-lint (`lint_celestial`) requires the room/direction pair to be a real exit.
   Make the *return* exit ungated so a turning tide can't strand a player.

2. **Command conditions** — gate any verb with `conditions: ["moon_phase_is:full"]` or
   `["tide_is:low"]` (fails closed, with an in-fiction reason).

3. **Dialogue conditions** — put the key directly on a choice, like `actor_has_flag`:

   ```yaml
   - label: The moon is full tonight. Does the creek change with it?
     moon_phase_is: full
     next_node: moon_lore
   ```

   Valid phases: `new`, `waxing_crescent`, `first_quarter`, `waxing_gibbous`, `full`,
   `waning_gibbous`, `last_quarter`, `waning_crescent`. Tides: `low`, `high`.

### Chat channels (Sprint 52 — code-registered for now)

Chat travels on **channels** with a delivery scope: `say` (room), `tell` (one player), and
P2ALL **topic channels** like `newbie` that reach everyone online, auto-register a speaking
verb named after the channel, get their own feed color, and appear as subscribe toggles on
the player settings page (unless `default_subscribed` opts them out). Adding a channel is
currently a one-line `Channel(...)` registration in `commands/social.py` (see
`NEWBIE_CHANNEL`); world-YAML channel definitions are a planned additive follow-on — the
engine's `ChannelRegistry` is the seam.

### Context-attached commands (object-scoped verbs, Sprint 55)

Give an **item or NPC its own verbs** that appear and work only when that object is present
(held, or in the room) — a `pull` lever, a `read` inscription, `pet` the dog. Declare a
`context_commands` map on the item or NPC in `world.yaml`:

```yaml
# on an item (available where the item is; use takeable:false for a room fixture)
  - id: chapel_altar
    takeable: false
    context_commands:
      read:                       # the verb players type
        aliases: [study]
        help: read the altar's worn inscription
        say: You trace the worn relief and piece out the eroded words...
        side_effects:             # any handler on the shared side-effect registry
          set_flags: [lore:chapel_wheel]
        # requires: actor_has_flag:some_flag   # optional extra gate
```

- Verbs on an **item** are gated `object_present:<id>` (room or inventory); on an **NPC**,
  `npc_present:<id>`. Availability rides the help filter, so the verb is *listed* only in
  context.
- The action reuses the **shared side-effect registry** (`set_flags`, `clear_flags`,
  `give_item`, `start_quest`, …) — the same effects dialogue and mechanisms use. A command
  must set `say` and/or `side_effects` (a no-op verb is rejected at load).
- Several objects may share a verb (`pull` on two levers); the player's noun disambiguates
  (`pull rusty`). Content-lint (`lint_context_commands`, enforced by
  `tests/integration/test_context_commands_integration.py::test_shipped_context_commands_lint_clean`)
  requires every `side_effects` key to resolve to a registered handler.
- A context verb that would **shadow a built-in** verb/alias (e.g. `look`, `take`) is skipped
  with a startup warning — pick a name that isn't already a command.

### Quest rewards and the progression system (Sprint 73)

A quest stage's `rewards:` block is a small vocabulary, interpreted by
`features/progression/rewards.py`'s `apply_rewards` the moment the stage completes:

```yaml
stages:
  - id: deliver_supplies
    description: Bring the supplies to the outpost.
    conditions:
      - type: in_room
        room_id: outpost
    rewards:
      items: [travel_ration]     # spawned on the player (skips ids already carried)
      xp: 50                     # banked toward the level curve, below
      coins: 25                  # canonical key (`money` is a tolerated alias)
      skill_points: 1            # banked; spent on abilities, below
```

All four keys are optional and additive — grant any subset. `coins`/`money` is the only
sanctioned way for a quest to create coins (it goes through `LedgerService.credit`, same as
every other coin faucet). An `xp` grant that crosses a level threshold pays out that level's
configured `coins_per_level`/`skill_points_per_level` *on top of* whatever the stage itself
grants — see the `progression:` section below for where that rate comes from. Any other
numeric `PlayerStats` field name is also accepted as a reward key and applied as a plain
delta (validated against a whitelist — a typo'd key is rejected at grant time, not silently
dropped); it is **not** the place to grant `reputation` — use the dialogue/quest
`side_effects: adjust_reputation` mechanism for that instead (see
[dialogue_npcs_quests.md](dialogue_npcs_quests.md)).

#### The `progression:` section (`world_content/world.yaml`)

The XP curve and per-level rewards are seeded at import from a top-level `progression:` block:

```yaml
progression:
  base: 100                 # XP to go from level 1 -> 2
  step: 50                  # extra XP required per level after that
                             # (level N -> N+1 costs base + step*(N-1))
  coins_per_level: 25       # coins paid out on every level crossed
  skill_points_per_level: 1 # skill points paid out on every level crossed
```

All four fields are required. `base` must be positive; `step`/`coins_per_level`/
`skill_points_per_level` must be zero or positive — enforced at `world_cli validate`/import
time, so a `base: 0` or negative value fails the import instead of blowing up later at the
first reward grant. Importing seeds (or updates) a singleton `ProgressionConfig` DB row,
mirroring the `WorldClock` pattern used elsewhere in this guide, that the reward interpreter
reads on every `xp` grant.

#### Live-tuning progression from the admin console

Like the world clock's time-ratio, per-level rewards and the XP curve are editable **live,
with no restart or reseed**, from the admin console's **Progression** tab:

- **XP Curve** — `base`/`step`, editable independently.
- **Per-Level Rewards** — `coins_per_level`/`skill_points_per_level`.

Backed by `GET`/`POST /admin/progression/config`. `POST` accepts any subset of the four
fields (an admin retunes one dial — say, `coins_per_level` — without restating the others);
each field is validated with the same bounds as the `world.yaml` import (`base` positive,
the rest non-negative) and rejected with `422` otherwise. Unlike the clock's `time_ratio`
(which a running background task caches in memory and must be pushed a fresh value), nothing
currently caches progression config in runtime state — the reward interpreter reads
`ProgressionConfig` fresh from the DB on every grant — so a plain commit is enough; the very
next reward uses the new numbers.

### Region pricing (Sprint 76)

Regional price multipliers and per-item bias (`RegionPricing` —
`src/lorecraft/features/economy/models.py`, keyed on `Room.zone`) are authored in
`world_content/world.yaml`'s `economy.regions:` list and YAML-seeded at import — see
[world_building.md § Regional pricing](world_building.md#regional-pricing) for the full
authoring format and [trade_economy.md § 5](archive/trade_economy.md#5-regional-pricing-the-transittrade-pairing)
for how `region_mult`/`bias` feed the buy/sell price formula. Since Sprint 71.2 that table has
always been read **live** from the DB on every transaction (`features/economy/service.py`); what
Sprint 76 adds is the missing admin layer to retune it without a reseed, mirroring the
`WorldClock` and Sprint 73.4 `ProgressionConfig` live-tune precedents.

From the admin console's **Economy** tab:

- **Viewing** the region table (zone, region multiplier, bias) is available to any
  authenticated admin role (`GET /admin/economy/regions`, observer-gated — the lowest role).
- **Editing** a zone's `region_mult` and/or `bias` requires the **superadmin** role
  (`POST /admin/economy/regions/{zone}`); inputs are disabled with a "Requires superadmin
  role" tooltip for lesser roles, the same pattern as the Progression tab.

The UI is a table with one row per zone (not a single config object like Progression) — each
row has a `region_mult` number input and a `bias` field edited as a **JSON textarea**
(`{"item_id": multiplier, ...}`), with a per-row **Save** button. Two semantics to know before
editing:

- **`region_mult` must be positive** (`> 0`) — zero or negative is rejected client-side and
  with a `422` server-side.
- **`bias` is a full replacement, not a merge.** Whatever JSON object you save becomes the
  entire bias map for that zone; omitting a previously-set item id clears its bias rather than
  leaving it untouched. The POST body treats `region_mult` and `bias` as independently optional
  (an admin can retune just one without restating the other), but when `bias` **is** included it
  wholesale-replaces the stored map. The textarea is pre-filled with the zone's current bias on
  load, so retuning one item's multiplier means editing that one key in place rather than typing
  the whole map from scratch.

Like Progression, nothing caches `RegionPricing` in runtime state — `features/economy/service.py`
reads the row fresh from the DB on every transaction — so a save takes effect on the very next
buy/sell, no restart required.

The seeded world currently includes economy rows for `ashmoore`, `ashmoore_graveyard`,
`brass_vaults`, `cogsworth`, `whisperwood`, and `port_veridian`. When adding a new authored
zone with shops or intended pricing differences, add a matching `economy.regions` row before
importing so the admin Economy tab can tune it live afterward.

### Disciplines & abilities (Sprint 78)

The skill points a player earns from leveling (above) are spent on **abilities**, each filed
under one of five **disciplines**. This replaced two earlier, separately-vocabularied systems
(a flat `SkillRegistry` catalog and the Sprint 74 skill tree's `ability.<id>` nodes) with one
coherent, fully data-driven model — see
[`discipline_ability_system.md`](discipline_ability_system.md) for the full design. Content
lives in two files, both loaded into in-memory registries at server startup — the same pattern
as `marks.yaml`/`hunts.yaml`, not the `world.yaml`/DB-import path `ProgressionConfig` uses.
**No discipline or ability ids are hardcoded in `src/`.**

#### `world_content/disciplines.yaml` — themed bodies of practice

```yaml
version: 1
disciplines:
  - id: survival
    name: Survival
    description: >-
      Reading the wild — foraging, tracking, pathfinding, and weathering exposure.
    governing_stat: fortitude   # mirrors the old SkillDef.governing_stat
    improve_chance: 0.1         # per-use growth-roll chance; defaults to 0.1
    max_rank: 100                # rank ceiling; defaults to 100
    check_keys: [skill.survival, skill.cartography]
```

Fields (`DisciplineDef`, `features/disciplines/abilities.py`):

- `id`/`name`/`description` — identity and display text.
- `governing_stat` — the base attribute the discipline is themed around (non-empty).
- `improve_chance`/`max_rank` — the two proficiency-growth dials the Tier 1
  `resolve_proficiency` mechanism takes as parameters (not engine constants): `improve_chance`
  must be in `[0, 1]`, `max_rank` must be `>= 1`. Both default to `0.1`/`100` (the same values
  the old flat-skill system used), but are authored explicitly per discipline so one can be
  retuned (a faster-learning or deeper-mastery discipline) without touching another.
- `check_keys` — the list of `skill.<name>` resolver-key namespaces this discipline governs
  (e.g. Survival governs `skill.survival` and `skill.cartography`; Subterfuge governs
  `skill.perception` and `skill.lockpicking`). This is *not* decorative: the `fatigue` feature's
  low-stamina penalty (`features/fatigue/source.py::FatigueModifierSource`) enumerates every
  discipline's `check_keys` to know which checks to penalize when a player is Weary/Exhausted —
  there is no other registry of "every live skill check" to iterate, so a discipline that omits
  a check key it should govern silently escapes the fatigue penalty on that check.

The five shipped disciplines (Survival, Subterfuge, Commerce, Rhetoric, Fortitude) are the seed
non-combat set; adding a sixth is a pure content change — a new list entry, no code.

#### `world_content/abilities.yaml` — one concrete thing within a discipline

```yaml
version: 1
abilities:
  - id: forage                    # unique id; also the argument to `train <id>`
    name: Forage                  # display name shown in `train`/`abilities`
    description: >-
      Learn to read the wild for food. Enables the `forage` verb in outdoor
      rooms, where a survival check turns up something edible.
    discipline: survival          # which DisciplineDef this ability belongs to
    ability_type: active          # open string: active | passive | interaction | …
    activation_type: instant      # open string: instant | maintained | triggered | …
    cost: 1                       # skill points required; must be >= 1
    prerequisites: []             # ability ids that must already be trained
    required_discipline_rank: 0   # minimum discipline rank to learn it; must be >= 0
    proficiency_model: success_only  # none | success_only | success_and_magnitude
    usage:
      terrain: [outdoor]           # see "The usage: block" below
    unlock:
      enables_verb: forage        # (A) active-verb marker — documentation only,
                                   #     the verb itself is code (see below)

  - id: mule
    name: Mule
    description: A trained back and better packing — you carry more before slowing.
    discipline: fortitude
    ability_type: passive
    cost: 1
    prerequisites: []
    proficiency_model: none
    unlock:
      modifier:                   # (B) passive-bonus ability
        key: carry_capacity       # namespaced modifier key (see engine/game/modifiers.py)
        kind: add                 # "add" or "mult"
        amount: 20

  - id: silver_tongue
    name: Silver Tongue
    description: A persuasive turn of phrase opens conversations that stay shut to others.
    discipline: rhetoric
    ability_type: interaction
    cost: 1
    prerequisites: []
    proficiency_model: none
    unlock:
      enables_verb: null           # (C) interaction/dialogue ability — flag only, no
                                    #     modifier or enables_verb
```

Full `AbilityRecord` fields (`features/disciplines/abilities.py`): `id`, `name`, `description`,
`flavor`, `discipline` (required), `branch` (optional sub-grouping), `tier` (>= 1, default 1),
`ability_type`/`activation_type` (open strings — deliberately not closed enums, so combat can
add `stance`/`spell`/… later as content, not an engine change), `cost` (>= 1),
`prerequisites`, `required_discipline_rank` (>= 0), `required_level`, `usage` (see below),
`unlock`, `proficiency_model` (closed enum: `none` | `success_only` | `success_and_magnitude`),
`mutually_exclusive_group`, `tags`.

Every ability's `unlock.flags` always includes `ability.<id>` — it's injected automatically if
omitted, so authors don't have to repeat it. That flag is what training an ability actually sets
on the player and is the single gate all three ability flavors converge on:

- **(A) Active-verb abilities** — `unlock.enables_verb` is a documentation-only marker naming
  the verb the ability unlocks; the verb itself is real code (e.g.
  `features/exploration/forage.py`, `features/exploration/sense.py`,
  `features/movement/service.py::pick`) whose command registration gates on
  `conditions=["actor_has_flag:ability.<id>", ...]`. Adding a new active-verb ability therefore
  always needs a matching code change — the YAML alone can't create a new verb.
- **(B) Passive-bonus abilities** — `unlock.modifier` is a `{key, kind, amount}` block matching
  the Tier 1 `engine.game.modifiers.Modifier` shape (`kind` is `add` or `mult`; namespaced
  `key`s like `carry_capacity`, `skill.perception`, `price.buy`). Every unlocked ability
  carrying a `modifier` is fed to the modifier resolver by `AbilityModifierSource`
  (`features/disciplines/modifier_source.py`) — no engine-code change needed to add a new
  passive as long as its `key` is one an existing resolver already reads (see the worked
  `haggler` example below for what happens when it isn't).
- **(C) Interaction/dialogue abilities** — `unlock` carries only the flag (no `modifier`, no
  usable `enables_verb`). Gate a `world.yaml` dialogue choice or NPC context on
  `actor_has_flag: [ability.<id>]` and the option appears only once the ability is trained —
  zero engine code. Worked example: the innkeeper Mira's dialogue tree
  (`dialogue_trees: innkeeper_dialogue`) has a persuasion-flavored choice gated on
  `actor_has_flag: [ability.silver_tongue]`, unlocked by the `silver_tongue` ability above.

#### The `usage:` block — data-driven performance gating

`usage:` (`UsageSpec`, projected to the Tier 1 `UsageRequirements` via
`AbilityRecord.to_ability_def`) describes what must hold to *perform* an already-trained
ability — distinct from what's needed to *learn* it. All fields default to "no requirement", so
an ability with no `usage:` block is always performable once trained:

- `character_states` / `target_states` — state names the actor (or, for target-directed
  abilities, the target) must currently hold: a durable `state.<name>` flag or a transient
  `ActiveEffect` key.
- `terrain` — terrain tags, any one of which satisfies the requirement.
- `resource` — `{type, cost}`, a resource the actor spends to perform it (today Lorecraft has
  exactly one resource type, `stamina`, via the `fatigue` feature's meter; `cost: 0` means
  "declared but free").
- `cooldown_seconds` — real-time cooldown between uses; `0` means no cooldown.

This is the retrofit target for verbs that used to hardcode their gating in Python. `forage`'s
old `Room.indoor == False` check is now `usage.terrain: [outdoor]`, enforced by the Tier 1
`check_usage` mechanism (`engine/game/abilities.py::check_usage`, called via
`features/disciplines/usage.py`'s `evaluate_usage` helper) instead of the ability's own code
inspecting the room. Adding a new usage requirement to an existing active-verb ability is
therefore a YAML-only change; the verb's Python only needs to call `evaluate_usage` and act on
the result, not hardcode a new condition.

#### Validation rules

Enforced by `DisciplineDocument`/`AbilityDocument` (`features/disciplines/abilities.py`) at
load time — a malformed document logs a warning and the registry stays empty rather than
crashing boot:

- Discipline `id`/`governing_stat` must be non-empty; `improve_chance` in `[0, 1]`; `max_rank`
  `>= 1`; discipline ids unique within the document.
- Ability `cost` must be `>= 1`; `tier` `>= 1`; `required_discipline_rank` `>= 0`;
  `proficiency_model` must be one of `none`/`success_only`/`success_and_magnitude`.
- Every ability `prerequisites` entry must name an ability id that exists elsewhere in the same
  document (no dangling prerequisites), and an ability may not list itself as its own
  prerequisite.
- No prerequisite cycles — the whole prerequisite graph must be a DAG (detected via a standard
  grey/black DFS walk).
- Ability ids must be unique and non-empty within the document.

#### A passive ability needs its `modifier.key` to be actually read somewhere

A passive ability's `modifier` only has an effect if some resolver in the codebase actually
calls `resolve_for(...)`/`resolve(...)` with that same `key` — the modifier source is a generic
pump, not a guarantee the value is consumed. This bit the `haggler` ability during the original
Sprint 74 review (carried forward unchanged in the Sprint 78 migration): it ships with
`key: price.buy, kind: mult, amount: 0.95`, and relies on `EconomyService.buy_price`'s
`_skill_price_mult` step (`features/economy/service.py`), which calls
`resolve_for(ctx.session, "player", ctx.player.id, "price.buy", base=1.0)` — the same
read-through pattern `encumbrance/rules.py::resolve_carry_capacity` uses for `carry_capacity` —
and folds it into the existing barter/reputation discount product. If you add a passive ability
with a new `modifier.key`, verify some Tier 1/Tier 2 code actually resolves that key before
shipping it; an unconsumed modifier fails silently, not loudly.

#### Not live-tunable — YAML + restart, not YAML + reseed

Unlike `ProgressionConfig` (live-editable from the admin console's Progression tab, no restart)
and unlike `world.yaml` content (imported into the DB via the World CLI, so a change needs a
`world_cli import`, i.e. a reseed), `disciplines.yaml` and `abilities.yaml` are read directly
into in-memory registries once at **server startup**
(`main.py::_load_discipline_definitions`/`_load_ability_definitions`, paths configured via
`Settings.disciplines_yaml_path`/`abilities_yaml_path`) — editing either file takes effect on
the **next process restart**, not a DB reseed and not live. This is a deliberate scope decision
(carried over from the Sprint 74 skill tree, roadmap 74-OI-6), not a gap: ability costs,
prerequisites, and discipline dials are structural content shape, not a hot balance lever an
admin needs to retune mid-session the way per-level coin rewards are. Revisit moving these onto
a `ProgressionConfig`-style live-tunable DB row only if admins actually ask to retune them
without a restart.

## The World CLI

`python -m lorecraft.tools.world_cli {import,export,validate,diff,merge,stats}` — the
single tool for moving world content between YAML and a database.

```bash
# Import (--fresh wipes existing world content first)
python -m lorecraft.tools.world_cli import --file world_content/world.yaml --db game.db --fresh

# See what's in a database
python -m lorecraft.tools.world_cli stats --db game.db

# Validate a YAML file without touching a database
python -m lorecraft.tools.world_cli validate --file world_content/world.yaml --start-room village_square --strict

# Round-trip a DB back to YAML/JSON
python -m lorecraft.tools.world_cli export --db game.db --output exported.yaml --format yaml

# Compare two world files by entity id (added/removed/changed)
python -m lorecraft.tools.world_cli diff --from world_content/world.yaml --to exported.yaml

# Merge two world files ("theirs" wins on id collision)
python -m lorecraft.tools.world_cli merge --base world_content/world.yaml --theirs branch_edits.yaml --output merged.yaml
```

Automated coverage: `pytest tests/tools/test_world_cli.py -v`. Full design rationale:
**[tooling_infrastructure.md](tooling_infrastructure.md)**.

## Publishing World Changes Safely (Changesets)

Editing the live world DB directly (via the admin World tab) is fine for solo dev
servers. For anything with players connected, use **changesets**: draft your room/item
edits, scan them for conflicts (broken exits, displaced players), and promote atomically
only when the scan is clean. Rollback is supported.

The World tab's **Items** editor changes canonical `Item` definitions: name,
description, flags such as takeable/tradeable/bound, equipment/economy fields, and the
advanced JSON fields used by effects, mechanisms, combinations, loot tables, and
context commands. Item IDs are immutable once created because rooms, scripts,
inventories, and world YAML references point at them. The editor does not place item
instances into rooms or inventories; use world content/changesets for placement, or the
Dashboard **Bestow** action for support grants to a specific player.

Full lifecycle (DRAFT → SCANNING → CONFLICTS/READY → LIVE → ROLLED_BACK), builder-mode
DB clones, and ghost sessions are documented in
**[world_versioning_changesets.md](world_versioning_changesets.md)**.

## Moderating Players

From the Dashboard (web) or Players screen (TUI, `F1`), select a player to:

- **Teleport** — move them to a different room
- **Freeze / unfreeze** — block their commands without disconnecting them
- **Edit flags** — set/clear quest or state flags directly
- **Heal / revitalize** — restore HP, or restore HP plus the fatigue feature's stamina meter
- **Buff** — apply a registered timed `ActiveEffect` such as `fortified` or `keen_minded`
- **Bestow** — grant coins through the ledger faucet, spawn item stacks into the player's loose inventory, or both
- **Message** — send them a system message

To bestow coins in the web admin panel: open **Dashboard**, click **Edit** on the
player, enter an **Admin reason**, type the amount in **Bestow -> coins**, and press
**Bestow**. To grant an item at the same time, enter the canonical item ID and
quantity in the adjacent fields. The backend endpoint is
`POST /admin/players/{player_id}/bestow`.

Every action is written to the audit log (Audit tab / `F2`), searchable by player,
command, or correlation ID (for full session replay).

## Issues & News

Both are YAML-first (git-blame-able, reviewable in PRs) and synced into the DB on
startup and on every admin mutation:

- **Issues** (`docs/issues.yaml`) — bug/task tracker. Manage via the Issues tab, `F6`,
  or `GET/POST/PUT /admin/issues`. The `component` field is a **registered, closed set**
  (a dropdown in the create form and the filter bar), served from `GET /admin/issues/components`
  and validated on write — the source of truth is `lorecraft/content/components.py`
  (`ISSUE_COMPONENTS`: coarse structural areas — `engine`, `webui/player`, `webui/admin`,
  `admin-tui`, `features`, `docs`, `infra`); the empty value means "unassigned". To add a
  component, edit that tuple. Players can also file an issue directly from in-game with
  `report <description>` — these keep the legacy `component="player-report"` (also a tag) and
  are **not** validated against the registered set (they use the content path, not the admin
  API); filter them by the `player-report` tag rather than the component dropdown. A report
  lands in the DB immediately (visible right away in the Issues tab/API), but the git-tracked
  YAML mirror only picks it up the next time an admin mutates *any* issue (same as any other
  DB-only write), not the instant it's filed.
- **News** (`docs/news.yaml`) — in-game announcements. Manage via the News tab, `F7`,
  or `GET/POST/PUT/DELETE /admin/news`. Also exposed unauthenticated at `/api/news`
  (JSON) and `/api/news/feed` (RSS 2.0), and in-game via the `news` command.
- **Help topics** (`docs/help_topics.yaml`) — the in-game help *articles* players read via
  `help topics` / `help <id>` / `help <name>`. Each topic has a numeric `id`, a unique
  slug `name`, a `title`, a `category` (used to group the listing), a `body`, and optional
  `keywords` (extra search terms). Authored in YAML and imported into the DB on first
  startup; ids and names must be unique and names must be slugs. (Command help — `help`,
  `help commands`, `help <command>` — is separate and comes from each command's own
  registered help text, not this file.)

Design rationale (why YAML, why repo-tracked): **[tooling_infrastructure.md](tooling_infrastructure.md#design-decisions)**.

## Analytics

The **Analytics tab** (Sprint 49, expanded Sprint 51) surfaces the ops picture at a glance:
p50/p95/p99 latency by operation, a player-activity-by-hour heatmap, a recent-operations timeline
(+ **timeline chart**), a **top commands** bar chart, **NPC interaction stats**, and a **quest
completion funnel**. It's backed by a one-call endpoint; the underlying query endpoints are also
available directly:

```
GET /admin/analytics/dashboard      — combined: latency_by_operation + timeline + heatmap +
                                      top_commands + npc_interactions + quest_funnel
GET /admin/analytics/commands       — most-used commands
GET /admin/analytics/npcs           — NPC interaction counts
GET /admin/analytics/quests         — quest completion counts (audit-log based — see note below)
GET /admin/analytics/quest-funnel   — per-quest started/completed/failed/in-progress (game-state based)
GET /admin/analytics/player-hours   — playtime from PlayerSession records
GET /admin/analytics/latency        — command-handler p50/p95/p99 (ms)
GET /admin/analytics/performance    — p50/p95/p99 by operation (command_parse,
                                      condition_evaluate, db_commit, command_handler)
```

All accept a `range` query param (`24h`, `7d`, `2w`, `30m`; default varies per endpoint);
`/dashboard` also takes `timeline_limit` (default 100, capped at 500) and `commands_limit` (default
10, capped at 50). `/performance` (Sprint 35.3) breaks latency down per operation from the `perf`
field the engine stamps on each `COMMAND_EXECUTED` audit event, so you can see whether time is
going to parsing, condition checks, or the DB commit. `scheduler_tick`/`broadcast_send` are timed
in the structured logs (WARNING over 50 ms) but sit outside the per-command audit path.

For the logging/correlation-ID side of this (grepping one command's full log trail by
`transaction_id`, the slow-operation WARNING threshold, and the upcoming per-command trace +
crash-report tools), see [`observability.md`](observability.md).

**`/quests` vs. `/quest-funnel`:** `quest_completion_counts` (backing `/quests`) reads the audit
log for `QUEST_COMPLETED` events — but those are only ever queued on the in-process event bus, never
persisted as audit rows, so this endpoint is always empty against real data (a pre-existing gap,
not fixed as part of Sprint 51). `quest_completion_funnel` (backing `/quest-funnel`, and the
dashboard's `quest_funnel` key) sidesteps this by reading live `PlayerQuestProgress` rows from the
game DB instead — use this one.

**NPC interactions require a resolved target.** `npc_interaction_counts` reads `AuditEvent.target_id`,
which `CommandEngine` sets (Sprint 51) only when the parsed command's target/object/recipient
role resolves to a real NPC (via `NpcRepo`) — so `talk mira`, `attack goblin`, etc. count, but
`take sword` never pollutes the NPC count.

## Combat Implementation Notes

Combat is implemented as the Tier 2 `combat` feature. Its first Scheduled Intent slice stores
encounters, participants, hostile relationships, and pending/resolved actions in feature-owned
tables, then resolves actions through durable `combat.resolve_action` scheduler jobs.

Combat damage applies directly to the target's HP meter. The previous persistent body-part
wound records and qualitative health-status layer were removed to keep combat state simple:
resolution and audit payloads retain numeric damage, traces, effects, consequences, and HP
participant snapshots.

Sprint 88.2 adds narrow terrain/cover defense modifiers. The combat resolver reads the encounter
room at resolution time, adds a small target defense bonus for `forest`, `mountain`, or `swamp`
terrain, and records the applied values in `random_trace` (`terrain_defense_bonus`,
`cover_defense_bonus`, `environment_defense_bonus`). Builders can opt a room into explicit cover
with `flags.combat_cover: light|partial|heavy`, or use `flags.combat_cover_defense_bonus` for a
numeric override. This is intentionally not a positioning system: no range bands, formations, or
cover actions are added.

Sprint 88.3 adds opt-in combo hooks for data-authored opposed-attack actions. An action can
`grants` a short encounter-scoped combo key after selected outcomes, and another action can
`consumes` that key for temporary accuracy and damage bonuses. The active key is stored on the
actor's combat participant contribution as `combo_ready`, so it ends with the encounter and stays
out of permanent player state. Resolution traces include `combo_ready_before`, `combo_consumed`,
`combo_granted`, `combo_accuracy_bonus`, `combo_damage_multiplier`, and `combo_ready_after`.

```yaml
version: 1
actions:
  - id: setup_slash
    action_range: engaged
    calculator: opposed_attack
    resolver: opposed_attack
    timing: { windup: 0.25, recovery: 2.0 }
    combo:
      grants: opening
      grant_outcomes: [hit, strong_hit]
  - id: finishing_thrust
    action_range: engaged
    calculator: opposed_attack
    resolver: opposed_attack
    timing: { windup: 0.35, recovery: 2.4 }
    combo:
      consumes: opening
      accuracy_bonus: 5.0
      damage_multiplier: 1.5
```

Sprint 88.4 uses the existing `CombatEncounter.combat_mode` column for an opt-in
simultaneous-planning mode. An NPC can declare `ai.combat_mode: simultaneous_planning`; when a
player starts that encounter, the NPC response is queued immediately and shares the player's
resolve time. Normal scheduled-intent encounters remain the default, and simultaneous-planning
encounters do not auto-continue attacks after each resolution. This mode is intended for authored
arena/boss beats, not as the default world-combat loop.

```yaml
npcs:
  - id: duel_champion
    name: Duel Champion
    ai:
      combat_mode: simultaneous_planning
```

The initial player-facing commands are `attack <npc>`, `shoot <npc>`, `defend`, and `flee`.
They use the primary action channel only; during recovery a player may queue one replacement
primary action. Health and stamina are ordinary MeterService meters (`hp`, and the fatigue
feature's `fatigue` meter rendered as stamina), and NPC
counter-attacks are created as scheduled intents through the same pipeline as player actions.

Core combat actions are authored in `world_content/combat_actions.yaml`. Each entry defines an
action id, primary-channel timing, broad action range (`self`, `engaged`, or `ranged`), optional
stamina delta, tags, a `ruleset_id`, and registered calculator/resolver ids. The shipped registered
resolvers are `opposed_attack`, `defend`, and `flee`; YAML references identifiers only and never
embeds combat scripts. `resolver_version` should change whenever a resolver's behavior or balance
contract changes in a way that matters to reports. If the file is missing or malformed, startup
falls back to the built-in core actions so `attack`, `shoot`, `defend`, and `flee` remain
available, and logs a warning. `world_cli validate` also checks the combat action file: missing
content is a warning, malformed content or unknown calculator/resolver ids are errors.

The current damage layer reads existing equipment effect descriptors rather than a new combat-only
item table. Equipped items may define `weapon_profile` descriptors (`base_damage`,
`accuracy_bonus`, `penetration`, `tags`) or `armor_profile` descriptors (`block`,
`resistance_factor`, `tags`). Items without those descriptors still fall back to the legacy
`category`/`slot`/`weight`/`quality` heuristic, so older content remains usable while builders can
tune important gear explicitly. Each resolved action persists a compact resolution record with
random and damage traces, state changes, position changes, weapon/armor descriptor sources, and the
record id used by structured combat events. Resolution records, action outcomes, random traces, and
audit payloads also include the action's `ruleset_id` and `resolver_version`, allowing admin reports
to compare outcomes across balance revisions. When scheduled combat is running with an audit engine,
the same resolution writes an `AuditEvent` row that points back to the feature-owned resolution
record.

Scheduled combat resolutions also broadcast to browsers as two messages: combat prose in the
normal feed and a structured `combat_update` payload with a per-encounter sequence number. The
current browser stores that ordered state for future panel/resync work. The structured state keeps
dead, defeated, and escaped participants visible with explicit `engaged`/`unengaged` positions;
builders do not need to author anything special for this first pass.

The first tactical-depth layer adds persistent encounter stances: `balanced`, `aggressive`,
`defensive`, and `mobile`. Stance policy is centralized in `features/combat/policy.py`, feeds
immutable resolver snapshots, and appears in resolution random/damage traces so later explanation
or audit UI can show which tactical trade-off affected a result.

Guarding uses the existing relationship-edge model: `guard <ally>` writes a supportive `guarding`
edge from guardian to protected participant, queues a defensive primary action, and lets the
guardian become the effective target when intercepting an attack. Resolution traces keep both the
original target and interceptor ids.

Ranged combat is intentionally lightweight. `shoot`/`fire` creates a `ranged_attack` scheduled
intent and carries `action_range: "ranged"` through action payloads, resolution records, damage
traces, and random traces. Ranged attacks do not use guarding interception. There is no persistent
near/far band or party formation state in this slice; authored tower guards, bows, and sniper-like
content can build on the range trace without forcing all player combat into a formation model.

Threat is qualitative. When a participant takes damage, its combat `threat.attention` map records
the source participant, a decaying score, and an `aware`/`watching`/`focused` cue. Resolution
payloads include `threat_changes`, and `combat_update` includes each participant's current threat
summary. NPC combat role text comes from `NPC.ai.combat_role` if present, otherwise the existing
`NPC.behavior`; the role is a cue for builders and UI, not a separate planner.

Party assistance is explicit participation. `assist <player>` joins the named player's active
encounter on the same side, writes a supportive relationship to the sponsored participant, mirrors
hostile edges against the opposing side, and stores a `party_assist` `combat_contract` in the
assister's contribution payload. This is the current "duel contract" boundary: structured metadata
for participation/reward/audit policy, not opt-in PvP consent or duel stakes.

Bounded reactions are participant policy, not nested actions. `reaction <defensive|conserve|never>`
sets the stored reaction policy; an incoming basic attack may consume one auto-brace window and
then advances `reaction_ready_at`. The trace records whether the reaction fired, so later audit UI
can explain the defense bonus without replaying hidden behavior.

Wind-up interruption is also explicit: if an actor is no longer active when a pending action
resolves, the action state becomes `interrupted` and a resolution record is still written with an
interrupt reason trace. Builders and admin tools can distinguish interruption from replacement or
manual cancellation.

Combat continuation is automatic once an encounter is active. After each resolved attack, active
participants with a hostile target and no pending primary action queue a basic attack for their
next available primary window. Player commands still replace the queued primary action, so a player
can switch from the default attack loop to `defend`, `flee`, or a different target without waiting
for the loop to stop.

Player HP depletion is the first death/resurrection slice. A player who reaches 0 HP is marked
`dead` for the combat participant record, clears active combat and queued actions, leaves a corpse
container in the death room, moves 20% of carried coins plus loose unbound carried items into that
corpse, moves to `Player.respawn_room_id`, restores HP to 25% of maximum, and receives the temporary
`weakened` effect. Corpse decay, lost-and-found recovery, and PvP-specific corpse rules remain later
work from `docs/death_resurrection.md`.

Combat status effects reuse the engine `ActiveEffect` lifecycle. The first status, `combat.off_balance`,
is applied by strong hits with game-time expiry and source metadata in payload, contributes a
combat defense modifier while active, appears in structured `active_effects`, and expires through
the existing `EffectService` sweep.

Combat effects may also register narrow Python hooks by effect key through
`features/combat/effect_hooks.py`: `on_action_admission`, `on_damage_received`, and `on_movement`.
These hooks are for combat-local reactions such as recording a ward trigger or a retaliatory trait;
they are not inline YAML scripts. Hook payloads are preserved in action `random_trace` or resolution
`effect_changes` so admin/audit tooling can see that the hook fired.

Boss-style NPCs can opt into a registered Python phase resolver by setting
`ai.combat_phase_resolver` on the NPC definition. Resolvers live in
`features/combat/boss_phases.py` and run only when that NPC is about to schedule a counter-intent;
they can choose the response action, target, and phase trace payload. This is meant for authored
boss encounters and does not replace normal NPC behavior or add a general planner.

NPCs can also opt into combat consequence obligations through `ai.combat_consequences`. The first
supported trigger is `on_damage_received`, and the first supported obligation is
`adjust_reputation`:

```yaml
ai:
  combat_consequences:
    on_damage_received:
      - type: adjust_reputation
        target_type: faction
        target_id: city_watch
        delta: -5
        reason: assault
```

That example means player damage against the NPC reduces the player's standing with the
`city_watch` faction by 5 and records the applied consequence in the combat resolution payload.
This is the current boundary for crime/faction fallout: content-authored obligations into the
existing reputation system, not a separate law, bounty, or arrest engine.

NPCs can also opt into content-authored combat rewards through `ai.combat_rewards`. The first
supported trigger is `on_defeat`, and the first supported reward is carried coins:

```yaml
ai:
  combat_rewards:
    on_defeat:
      - type: coins
        amount: 25
        message: "The instructor pays you 25 coins for a clean spar."
```

That reward credits the victorious player through the ledger service and records the reward in the
combat resolution payload so the browser feed can narrate it with the final defeat message.

For balance checks, run the headless report CLI instead of hand-testing in the browser:

```bash
python -m lorecraft.tools.combat_balance --trials 1000 --seed 7 -o combat-report.json
```

The report repeats the pure combat resolver with deterministic RNG and returns outcome counts,
damage min/max/average, hit rate, one-shot defeat rate, and the action's `ruleset_id` and
`resolver_version`. Use it to compare candidate weapon, armor, or action timing values before
shipping content. It does not boot a server, create combat actors in the database, or simulate a
party encounter.

Live ruleset tuning is DB-backed. The combat admin API exposes
`GET /admin/combat/rulesets` and `POST /admin/combat/rulesets/{ruleset_id}` with two positive
multipliers: `damage_multiplier` and `stamina_cost_multiplier`. Scheduled combat reads the row
fresh for each resolving action, so a superadmin update affects the next resolution without restart
or reseed. The applied multipliers are recorded in random/damage traces. Keep these dials coarse:
use action YAML and equipment descriptors for authored content, and use the live row for emergency
or playtest balance changes.

Balance details are intentionally still shallow in this slice: PvP consent and richer browser
resync remain later combat work tracked in `docs/roadmap.md`.

**Removing a Sprint 51 widget.** Each of the four new widgets is a self-contained
`{id, render(data)}` entry in the admin console's `ANALYTICS_WIDGETS` array
(`src/lorecraft/webui/admin/index.html`), delimited by `<!-- WIDGET: ... --> ... <!-- /WIDGET -->`
HTML comments. To drop one: delete its HTML block, its `render...Widget()` function, and its one
line in `ANALYTICS_WIDGETS` — none of them reference each other or share helpers.

## Extending the UI: Feature Panels

A Tier 2 **feature** can contribute its own UI to the player web client — a schedule
board, an inventory panel, the transit minimap — without touching the engine or the base
web templates. This is the `presentation.py` seam (shipped in Sprint 31). It loads **only**
when both that feature and the web host are running, so a headless run (tests, simulation,
world CLI) never touches UI code.

### The update loop it builds on

A "panel" in the player UI is a convention with three parts:

1. A DOM element with a stable id, e.g. `<div id="transit-minimap">`, sitting in a named
   **slot** in the page shell (`left-rail`, `right-rail`, `hud`, `feed`).
2. A route `GET /partials/<id>` that renders the panel's template.
3. The engine *naming* that panel when it changes: a command/event handler adds the panel
   id to `ctx.updates`, and the web layer pushes `{"type": "state_change",
   "affected_panels": ["transit-minimap", ...]}`. The browser re-fetches
   `/partials/<id>` and swaps the returned HTML. The client never needs to know what the
   panel *means* — that indirection is the whole extension seam.

### What a feature ships

Add a `presentation.py` to the feature package and point the manifest at it:

```python
# features/<feature>/__init__.py
manifest = FeatureManifest(
    key="transit",
    name="Transit",
    presentation="lorecraft.features.transit.presentation",  # optional dotted path
)
```

```python
# features/<feature>/presentation.py
from lorecraft.webui.player.host import WebHost, Panel

def build_minimap_context(player, db) -> dict:
    ...                              # (player, session) -> template context

def register(web: WebHost) -> None:
    web.add_template_dir(Path(__file__).parent / "templates")  # add to Jinja search path
    web.add_panel(Panel(
        id="transit-minimap",        # unique; prefix with the feature key
        slot="right-rail",           # a named shell slot
        partial="partials/transit_minimap.html",
        context=build_minimap_context,
    ))
    web.add_static("/features/transit", Path(__file__).parent / "static")  # optional
    web.add_script("/features/transit/minimap.js", module=True)            # optional (interactive only)
```

The web host (`webui/player/__init__.py`) loads every enabled feature's `presentation.py`
during startup and calls its `register(web)`. A broken `presentation.py` degrades to
"no panel" with a logged error — it never crashes the page.

### Contracts to know

- **Panel ids are global and stable** — they are the URL (`/partials/<id>`), the DOM id,
  and the `affected_panels` token. Prefix with the feature key (`transit-minimap`, not
  `minimap`) to stay unique across features.
- **Slots are a fixed contract** (`left-rail`, `right-rail`, `hud`, `feed`); an unknown
  slot name drops the panel with a warning. Two panels in the same slot stack in feature
  load order.
- **Most panels need zero JavaScript** — a server-rendered partial that re-fetches on
  `state_change` is enough. Only genuinely interactive panels (e.g. an animated minimap)
  ship a JS module, and that module reads the DOM / a host-provided `lorecraft:ws`
  event — it never opens its own socket or imports engine code.
- **The engine drives visibility** — a feature refreshes its panel by adding the panel id
  to `ctx.updates`/`affected_panels` from its own handlers, exactly like core panels.

See `docs/tier_split_refactor.md` §1c for the full design and `features/transit/` for a
working example.

## Troubleshooting

- **"Using an ephemeral random secret" warning at startup** — `LORECRAFT_ADMIN_JWT_SECRET`
  isn't set; admin tokens won't survive a restart. Set it for anything long-running.
  Same idea applies to `LORECRAFT_PLAYER_SESSION_SECRET`, except that one self-persists
  to `.env` automatically the first time a real server starts.
  See `config.ensure_persisted_secret()`.
- **Can't log into `/admin`** — confirm `LORECRAFT_ADMIN_SEED_USERNAME`/`_PASSWORD` were
  set (or unset, meaning the `admin`/`admin` default) the *first* time the server started
  against this DB — the seed account is only created once, on an empty `AdminUser` table.
- **Player teleport/edit fails with a conflict** — someone else edited that room
  concurrently; the World tab and changeset scans use optimistic locking. Reload and
  retry.
- **World import aborts on existing rooms** — `import_world.py`/`world_cli import`
  refuse to import into a non-empty DB unless you pass `--fresh` (which wipes existing
  world content first — player accounts are untouched).
- **Where's the audit trail?** — the Audit tab / `F2` / `GET /admin/audit`, backed by
  `LORECRAFT_AUDIT_DB_PATH`, separate from the game DB.
- **A player hit "something went wrong processing that command"** — the command pipeline threw
  an unhandled exception (Sprint 57.3); check the **Crashes tab** (or `GET /admin/crashes`) for a
  row with that player/timestamp — it has the full stack trace. For non-crashing slowness, pull
  the `transaction_id` from a crash row or a structured log line and check
  `GET /admin/trace/<transaction_id>` for the per-operation timing breakdown. Full detail in
  [`observability.md`](observability.md) (Request tracing / Crash reports sections).
- **Database work feels slow** — inspect the query-span log before adding indexes:
  `python scripts/analyze_query_log.py --log logs/sql_queries.log --database game.db`.
  The report shows slowest statements, most frequent fingerprints, and index candidates from
  observed `WHERE` / `JOIN` / `ORDER BY` clauses. Full detail is in
  [`observability.md`](observability.md#sql-query-span-logging).

## Related Docs

| Doc | Covers |
|-----|--------|
| [world_building.md](world_building.md) | Room/exit/item YAML schema |
| [dialogue_npcs_quests.md](dialogue_npcs_quests.md) | NPC, dialogue tree, and quest YAML schema |
| [trade_economy.md](archive/trade_economy.md) | Currency, pricing formula, regional pricing, shops, bartering |
| [world_versioning_changesets.md](world_versioning_changesets.md) | Changeset lifecycle, builder mode, optimistic locking |
| [tooling_infrastructure.md](tooling_infrastructure.md) | Design rationale for issues/news/CLI/analytics/linting |
| [observability.md](observability.md) | Structured logging, correlation IDs, latency instrumentation, request tracing, crash reports, and SQL query-span logs |
| [player_authentication.md](player_authentication.md) | Player session/auth design (JWT cookie, planned full account system) |
| [disconnect_handling.md](disconnect_handling.md) | Grace period, reconnect, and scheduler integration details |
| [architecture.md](architecture.md) | Full system architecture reference |
| [tier_split_refactor.md](tier_split_refactor.md) | Engine/feature/web-host layout + the `presentation.py` feature-UI design (§1c) |
| [architecture_tiers.md](architecture_tiers.md) | Tier 1/2/3 model, feature manifests, enabling/disabling features |
| [roadmap.md](roadmap.md) | Sprint-by-sprint build order and current status |
| [user_guide.md](user_guide.md) | Player-facing command reference |
