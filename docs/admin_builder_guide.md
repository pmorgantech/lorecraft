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

Nine tabs, each backed by REST endpoints under `/admin/*`:

| Tab | What you can do | Key endpoints |
|-----|------------------|----------------|
| **Dashboard** | Live player table, auto-refreshed over `/admin/ws` | `GET /admin/players` |
| **Audit** | Paginated, filterable audit log; row-expand payload; correlation-ID session replay. **Live-updates** as players act (each executed command pushes over `/admin/ws`) — toggle with the **Live** checkbox, or use the **↻ Refresh** button to reload on demand. Command summaries show the full command as typed (e.g. `Command executed: go east`, not just the verb) | `GET /admin/audit`, `GET /admin/audit/session/{correlation_id}` |
| **World** | Room search + inline editor (optimistic locking), item/NPC sub-tabs, NPC spawn/despawn | `GET/PUT/POST /admin/world/rooms`, `GET /admin/world/items`, `GET /admin/world/npcs`, `POST /admin/npcs/{id}/spawn` |
| **Changesets** | Draft → scan → promote workflow; conflict list | `POST /admin/changesets`, `POST /admin/changesets/{id}/scan`, `POST /admin/changesets/{id}/promote` |
| **Clock** | Live world-clock readout; pause/resume, time-ratio, weather override | `GET/POST /admin/clock`, `/admin/clock/pause`, `/admin/clock/resume`, `/admin/clock/time-ratio`, `/admin/clock/weather` |
| **Issues** | Repo-tracked issue tracker CRUD. **Resolved/deferred are hidden by default** — a "Hide status" checkbox group toggles any status in/out of view; plus a **priority** filter and a **sort** selector (Priority / Recently updated / Recently created). Filter+sort run client-side (hide/sort choices persist per browser); a header count shows `N shown · M hidden`. `component` is a **registered dropdown** (create + filter), served from `GET /admin/issues/components` and validated on write. Table shows opened-by + created/updated dates (🕑 toggles absolute dates ↔ relative ages); rows expand (click) to description, tags, links, assignee, timestamps. Live-refreshes on any change — admin edits **and** in-game player `report`s | `GET/POST/PUT /admin/issues`, `GET /admin/issues/components` |
| **News** | Announcements CRUD (also feeds the in-game `news` command and `/api/news/feed` RSS) | `GET/POST/PUT/DELETE /admin/news` |
| **Help** | Help-article CRUD (the topics players read via `help topics`/`help <id>`); create form + row-expand inline editor (body/title/category/keywords) + name/title search; every change re-exports `docs/help_topics.yaml` | `GET/POST/PUT/DELETE /admin/help` |
| **Accounts** | Create/revoke admin accounts, assign roles (superadmin only) | `GET/POST /admin/accounts`, `DELETE /admin/accounts/{username}` |

Player moderation actions (teleport, flag edit, freeze/unfreeze, message) live under the
player detail view reached from the Dashboard — see
[Moderating Players](#moderating-players).

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

3. **Dialogue conditions** — put the key directly on a choice, like `required_flags`:

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
        # requires: flag_set:some_flag   # optional extra gate
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

Full lifecycle (DRAFT → SCANNING → CONFLICTS/READY → LIVE → ROLLED_BACK), builder-mode
DB clones, and ghost sessions are documented in
**[world_versioning_changesets.md](world_versioning_changesets.md)**.

## Moderating Players

From the Dashboard (web) or Players screen (TUI, `F1`), select a player to:

- **Teleport** — move them to a different room
- **Freeze / unfreeze** — block their commands without disconnecting them
- **Edit flags** — set/clear quest or state flags directly
- **Message** — send them a system message

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

## Related Docs

| Doc | Covers |
|-----|--------|
| [world_building.md](world_building.md) | Room/exit/item YAML schema |
| [dialogue_npcs_quests.md](dialogue_npcs_quests.md) | NPC, dialogue tree, and quest YAML schema |
| [world_versioning_changesets.md](world_versioning_changesets.md) | Changeset lifecycle, builder mode, optimistic locking |
| [tooling_infrastructure.md](tooling_infrastructure.md) | Design rationale for issues/news/CLI/analytics/linting |
| [observability.md](observability.md) | Structured logging, correlation IDs, latency instrumentation, and (Sprint 57) request tracing + crash reports |
| [player_authentication.md](player_authentication.md) | Player session/auth design (JWT cookie, planned full account system) |
| [disconnect_handling.md](disconnect_handling.md) | Grace period, reconnect, and scheduler integration details |
| [architecture.md](architecture.md) | Full system architecture reference |
| [tier_split_refactor.md](tier_split_refactor.md) | Engine/feature/web-host layout + the `presentation.py` feature-UI design (§1c) |
| [architecture_tiers.md](architecture_tiers.md) | Tier 1/2/3 model, feature manifests, enabling/disabling features |
| [roadmap.md](roadmap.md) | Sprint-by-sprint build order and current status |
| [user_guide.md](user_guide.md) | Player-facing command reference |
