# Tooling Infrastructure — Design & Implementation Plan

**Status:** Implemented (Sprint 10.5 complete)
**Last updated:** 2026-07-02

---

## Overview

Comprehensive tooling suite for engine development, data management, and operations. The system is built around three core principles:

1. **Data-driven** — Configuration stored in repo-tracked YAML files, synced bidirectionally with admin UI
2. **Admin-centric** — All tooling accessible through existing admin TUI and web panel
3. **Foundation-focused** — Designed to support development through combat/trading/PvP feature phases

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Admin UI Layer                             │
├─────────────────────────────────────────────────────────────┤
│  Web Panel (tabs)      │    Textual TUI (F-key screens)    │
│  • Issues              │    • Issues (F6)                   │
│  • News                │    • News (F7)                     │
│  • Analytics           │    • Analytics (F8)                │
│  • World Manager       │    • World Manager (F3, enhanced)  │
├─────────────────────────────────────────────────────────────┤
│                   API Layer                                  │
├─────────────────────────────────────────────────────────────┤
│  FastAPI Routers:                                            │
│  • /admin/issues       • /admin/news       • /admin/analytics
│  In-game commands:     • /news (RSS feed)                   │
│  • /news               • /report-bug (eventual)             │
├─────────────────────────────────────────────────────────────┤
│                   Data Layer                                 │
├─────────────────────────────────────────────────────────────┤
│  YAML Files (repo-tracked)    │   Database (SQLite)         │
│  • docs/issues.yaml           │   • Issue (table, optional) │
│  • docs/news.yaml             │   • News (table, optional)  │
│                               │   • Analytics data          │
├─────────────────────────────────────────────────────────────┤
│                   CLI Tools                                  │
├─────────────────────────────────────────────────────────────┤
│  python -m lorecraft.tools.world_cli ...                     │
│  python -m lorecraft.tools.fixtures ...                      │
│  python -m lorecraft.tools.analytics ...                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Issue Tracking System

**Purpose:** Repository-tracked bug and todo management, admin-facing with optional in-game player reporting (later).

**Data Format: `docs/issues.yaml`**

```yaml
format_version: "1.0"
issues:
  - id: issue-001
    type: bug
    title: "Movement validation race condition"
    description: |
      When two players move to same room simultaneously,
      one movement gets lost. Reproduction steps in #123.
    created_by: peter
    created_at: 2026-07-02T18:00:00Z
    updated_at: 2026-07-02T19:30:00Z
    status: open  # open | in-progress | resolved | deferred | duplicate
    priority: high  # low | normal | high | critical
    component: movement  # movement | inventory | dialogue | quest | npc | combat | etc
    tags: [threading, race-condition, critical-path]
    assigned_to: peter
    links:
      - type: "depends_on"
        id: issue-002
      - type: "duplicates"
        id: issue-042

  - id: issue-002
    type: todo
    title: "Sprint 10 extensibility seams"
    description: "Implement pluggable dialogue conditions and side effects"
    created_by: peter
    created_at: 2026-07-01T00:00:00Z
    status: in-progress
    priority: normal
    component: game
    assigned_to: peter
```

**Admin UI Features:**

- **TUI (F6 Issues screen):**
  - Sortable table: ID | Type | Title | Status | Priority | Component
  - Filter bar: `/status:open /priority:high /component:movement`
  - Actions: Open (detail view) | Edit status | Assign | Mark done
  - Detail view: Full description, links, history, related issues

- **Web Panel (Issues tab):**
  - Dashboard: open count by priority, burndown chart
  - Issue list with filters/search
  - Create new: form with title, description, component, priority
  - Edit modal: update status, priority, assignment, tags
  - Bulk actions: batch status change

**Auto-sync Behavior:**

- YAML → DB on server startup (one-way read, enables git tracking)
- UI changes → YAML file (bidirectional, commits on each change)
- Detects external edits (via git); merges on reload

**Related Game Features (future):**

- `/report-bug` command (player-facing) creates draft issues
- Moderation flag for inappropriate reports

---

### 2. News & Announcements System

**Purpose:** In-game announcements, lobby bulletin board, RSS feed for external integrations.

**Data Format: `docs/news.yaml`**

```yaml
format_version: "1.0"
announcements:
  - id: news-2026-07-02-welcome
    type: server  # server | event | bulletin | maintenance | patch
    title: "Welcome to Ashmoore"
    body: |
      A new quest line begins in the Wandering Crow Inn.
      Seek out Mira for an interesting proposal.
    author: "Game Master"
    published_at: 2026-07-02T12:00:00Z
    expires_at: 2026-08-02T12:00:00Z  # null = permanent
    priority: normal  # low | normal | high (high → banner, normal → feed)
    icon: "scroll"  # emoji or icon reference
    tags: [quest-content, ashmoore]

  - id: news-2026-07-01-maintenance
    type: maintenance
    title: "Server maintenance window"
    body: "Scheduled downtime 2026-07-03 02:00–02:30 UTC for database optimization."
    author: "System"
    published_at: 2026-07-01T18:00:00Z
    expires_at: 2026-07-03T03:00:00Z
    priority: high

seasonal_events:
  - id: seasonal-spring-2026
    type: seasonal_event
    title: "Spring Festival"
    description: "Flowers bloom, new quests unlock"
    start_date: 2026-03-20
    end_date: 2026-06-20
    active: true
    tags: [seasonal, event]
```

**In-Game Features:**

- `/news` command shows feed (dismissible per-player, marked as read)
- Lobby screen: news bulletin board (before entering game)
- News banner for `high` priority items (auto-dismiss after 30s or click)
- News icon in status bar (red dot if unread)

**Admin UI:**

- **TUI (F7 News screen):** Sortable list, edit, schedule publish/expire
- **Web Panel (News tab):** Calendar view, bulk schedule, preview

**External Integration:**

- `/api/news/feed` — RSS 2.0 feed (unauthenticated, cacheable)
- `/api/news?format=json` — JSON API for external bots/dashboards

**Auto-sync Behavior:**

- YAML → DB on startup
- Admin UI changes → YAML file
- Auto-expires old news based on `expires_at` timestamp

---

### 3. World Management CLI Suite

**Purpose:** Command-line tools for world content authoring, validation, and operations.

**Installed as:** `python -m lorecraft.tools.world_cli`

**Commands:**

```bash
# Import/export
python -m lorecraft.tools.world_cli import \
  --file world.yaml \
  --db game.db \
  --fresh  # wipe before import

python -m lorecraft.tools.world_cli export \
  --db game.db \
  --output world.yaml \
  --format yaml|json

# Validation
python -m lorecraft.tools.world_cli validate \
  --file world.yaml  # schema + referential integrity

# Diff / merge
python -m lorecraft.tools.world_cli diff \
  --from world.v1.yaml \
  --to world.v2.yaml \
  --output diff.yaml

python -m lorecraft.tools.world_cli merge \
  --base world.yaml \
  --theirs world.new.yaml \
  --output world.merged.yaml

# Statistics
python -m lorecraft.tools.world_cli stats \
  --db game.db  # rooms, items, NPCs, quests, dialogue trees
```

**Implementation Location:** `src/lorecraft/tools/world_cli.py`

**Output Example (validate):**

```
✓ Schema valid (323 rooms, 487 items, 42 NPCs, 18 quests)
✓ All item references exist
✓ All NPC dialogue trees reachable
⚠ Room 'old_basement' unreachable (no entry from village_square)
✗ NPC 'Aldric' dialogue node 'exit_2' links to nonexistent 'node_XYZ'
```

---

### 4. Analytics Foundations

**Purpose:** Metrics collection and dashboards fed by observability work (Sprint 13).

**Admin API Endpoints:**

- `GET /admin/analytics/metrics?metric=player-hours&range=7d&group-by=player`
- `GET /admin/analytics/commands?top=20&range=24h`
- `GET /admin/analytics/npcs?metric=interactions&npc=mira`
- `GET /admin/analytics/export?range=7d&format=json|csv`

**In-Game Admin Commands:**

```
/admin/analytics player-hours --range=7d
/admin/analytics top-commands --range=24h --limit=20
/admin/analytics npc-interactions --npc=mira
```

**Metrics Collected (from Sprint 13 instrumentation):**

- Command latency (p50/p95/p99)
- Event bus depth and handler timing
- Player session duration
- NPC interaction counts
- Quest completion rates
- Item flow (pickup/drop/use counts)

**Dashboard Features (Web Panel):**

- Timeline chart: command latency over time
- Heatmap: player activity by hour/day
- Top commands bar chart
- NPC interaction stats
- Quest completion funnel

---

### 5. Simulation Runner Enhancements

**Purpose:** Load world, spawn bots, run scripted scenarios (Sprint 12 work + tooling).

**CLI Interface:**

```bash
python -m lorecraft.tools.simulation run \
  --world world.yaml \
  --bots 10 \
  --script scenario.json \
  --duration 300s \
  --output results.json
```

**Scenario Format: `scenarios/test-movement.json`**

```json
{
  "name": "Movement load test",
  "bots": 10,
  "duration_seconds": 60,
  "actions": [
    {
      "at": 0,
      "bot": "all",
      "action": "move",
      "direction": "east"
    },
    {
      "at": 5,
      "bot": [0, 1, 2],
      "action": "take",
      "item": "coin"
    }
  ]
}
```

**Reports:**

- Latency distribution (p50/p95/p99)
- Error counts by type
- Throughput (commands/sec)
- Database query counts
- State consistency checks

---

### 6. Fixture Generator

**Purpose:** Template-based scaffold for new content (NPCs, quests, items).

**CLI Interface:**

```bash
python -m lorecraft.tools.fixtures gen-quest \
  --name "Dragon Slayer's Gambit" \
  --npc aldric \
  --stages 3 \
  --output quest-dragon.yaml

python -m lorecraft.tools.fixtures gen-npc \
  --name "Aldric the Blacksmith" \
  --personality gruff \
  --location smithy \
  --dialogue-branches 4 \
  --output npc-aldric.yaml

python -m lorecraft.tools.fixtures gen-item \
  --name "Iron Sword" \
  --type weapon \
  --value 500 \
  --aliases sword,iron-blade \
  --output item-sword.yaml
```

**Output:** Validated YAML boilerplate with sane defaults, ready to customize.

---

### 7. Content Validation & Linting

**Purpose:** Catch world authoring mistakes before they reach the DB.

**Checks:**

- YAML schema validation (already have via pydantic)
- Dead item references (items in dialogue but not in rooms)
- Dead NPC references (NPCs mentioned but not defined)
- Unreachable rooms (no exit path from start)
- Unreachable dialogue nodes (dialogue links to nonexistent nodes)
- Circular quest dependencies (Quest A → Quest B → Quest A)
- Duplicate item names in same room (confusing for players)
- Item quantity warnings (e.g., "100 coins in one item" → suggest quantity model)

**CLI Invocation:**

```bash
python -m lorecraft.tools.world_cli validate --strict  # fail on warnings
```

---

## Sprint Integration

### Sprint 10.5 — Tooling Infrastructure (Proposed)

**Goal:** Foundation for admin/dev tooling. Repo-tracked issues and news enable operations; CLI suite enables world authoring.

| # | Task | Scope |
|---|------|-------|
| 10.5.1 | Issues system: YAML format, file sync, CRUD routes, admin UI (TUI F6, web tab) | 2 days |
| 10.5.2 | News system: YAML format, in-game `/news`, RSS feed, admin UI (TUI F7, web tab) | 2 days |
| 10.5.3 | World CLI suite: import/export/validate/diff/stats; call from admin world manager | 2 days |
| 10.5.4 | Analytics foundation: metric collection setup (queries + API endpoints, no dashboard yet) | 1 day |
| 10.5.5 | Content validation & linting rules (called by world CLI validate) | 1 day |

**Unblocks:**

- Sprint 11 browser E2E harness (can log issues from test failures)
- Sprint 12 simulation harness (can record metrics)
- Sprint 13 observability (has analytics queries ready)

---

## File Structure

```
src/lorecraft/
├── tools/                          # NEW
│   ├── __init__.py
│   ├── world_cli.py               # import/export/validate/diff/stats
│   ├── fixtures.py                # gen-quest/gen-npc/gen-item
│   ├── analytics.py               # metric collection + queries
│   ├── simulation.py              # bot runner
│   └── validators.py              # content validation rules
│
├── admin/
│   ├── routers/
│   │   ├── issues.py              # NEW: /admin/issues CRUD
│   │   ├── news.py                # NEW: /admin/news CRUD
│   │   ├── analytics.py           # NEW: /admin/analytics queries
│   │   ├── players.py             # (existing)
│   │   ├── audit.py               # (existing)
│   │   ├── world.py               # (existing, enhanced with CLI calls)
│   │   ├── clock.py               # (existing)
│   │   └── accounts.py            # (existing)
│   ├── tui/
│   │   └── app.py                 # Add F6 (issues), F7 (news), F8 (analytics)
│   └── (existing: auth.py, websocket.py)
│
├── models/
│   └── (add Issue and News tables if DB storage desired; optional)
│
├── repos/
│   ├── issue_repo.py              # NEW (optional, if DB-backed)
│   ├── news_repo.py               # NEW (optional, if DB-backed)
│   └── (existing repos)
│
├── web/admin/
│   └── index.html                 # Add Issues, News, Analytics tabs
│
├── (existing modules: game, services, commands, npc, clock, etc)
│
└── __main__.py                     # Entry point for CLI tools

docs/
├── issues.yaml                     # NEW: issue tracking (repo-tracked)
├── news.yaml                       # NEW: announcements (repo-tracked)
├── tooling_infrastructure.md       # NEW: this doc
├── roadmap.md                      # (update: insert Sprint 10.5)
├── status.md                       # (update: add tooling phase)
└── (existing: architecture.md, etc)

tests/
└── tools/                          # NEW
    ├── test_world_cli.py
    ├── test_fixtures.py
    └── test_validators.py
```

---

## Glossary

| Term | Definition |
|------|-----------|
| Issue | Bug, todo, or feature request tracked in `docs/issues.yaml` |
| News | Announcement or event shown in-game and in lobby |
| Changeset | World versioning construct; separate from issues (already implemented in Sprint 6) |
| YAML sync | Bidirectional: YAML ↔ admin UI (via auto-commit) |
| World CLI | Command-line tools for import/export/validate world content |
| Analytics | Metrics from command latency, event bus, NPC interactions, etc. |

---

## Design Decisions

### Why YAML for Issues & News?

- **Versioned:** Git tracks all changes, blame shows who changed what and when
- **Mergeable:** Easy to resolve conflicts (unlike DB rows)
- **Reviewable:** Pull requests show what changed
- **Offline-friendly:** Can edit locally without server
- **Simple:** No migration burden, human-readable

### Why Optional DB Storage?

- Issues/News can live in YAML only (start here)
- If full-text search / complex queries needed later, add DB table
- Sync keeps YAML and DB in sync via `AppState` loader

### Why Repo-Tracked Issues?

- Keeps context with code (issues live alongside architecture/roadmap docs)
- Enables automation (CI can close issues on PR merge)
- No third-party dependency (GitHub, Linear, Jira)
- Single source of truth (dev knows to check `docs/issues.yaml`)

### Analytics Foundation (Not Dashboard Yet)

- Sprint 13 adds instrumentation (logging, timing)
- Sprint 10.5 adds query API
- Sprint 14+ can build dashboards as needed
- Avoids scope creep; focuses on data collection first

---

## Future Expansions

- **DB Inspector:** Table viewer, query builder, state editing (from admin panel)
- **Event Replay:** Correlation ID → full transaction trace, pause/resume
- **Profiler HUD:** FPS, event queue depth, hotspots (in-game dev mode)
- **Hotloading:** Edit NPC dialogue/quests, reload without restart
- **Player Impersonation:** Admin joins as player, sees their view
- **Rollback Tools:** Restore player to point-in-time from audit trail
- **Feature Registry Dashboard:** Visualize pluggable dialogue/command hooks
- **Metrics Export:** Prometheus scrape endpoint for external monitoring

---

## Success Criteria

- ✅ Issues tracked in `docs/issues.yaml`, synced to admin UI
- ✅ News in `docs/news.yaml`, shown in-game and in lobby
- ✅ `/news` command and RSS feed working
- ✅ World CLI tools (import/export/validate) fully functional
- ✅ Admin UI displays issues and news (TUI F6/F7, web tabs)
- ✅ Analytics queries available via API (no dashboard yet, but data collected)
- ✅ All 336+ tests passing; new tools have unit tests
- ✅ Roadmap and status docs updated; foundation band visibility improved

---

*Last updated: 2026-07-02 — Sprint 10.5 implemented. Deviations from this design doc:*
- *Analytics endpoints are grounded in data the engine already records (the audit log, `PlayerSession`) rather than new instrumentation — see `lorecraft.analytics`. Command latency/event-bus-depth metrics wait on Sprint 13 instrumentation, as this doc's own "Analytics Foundation" section anticipated.*
- *Issues/News auto-sync is one-way YAML→DB on startup (only when the DB has no rows yet) plus DB→YAML export on every admin mutation. Git-based external-edit detection/merge was not implemented — out of scope for this sprint.*
- *Circular quest dependency checking was not implemented: `QuestStageData` has no quest-to-quest dependency field in the schema today, so there's nothing to scan for a cycle in.*
- *Seasonal events (`docs/news.yaml`'s `seasonal_events` section) and TUI/web dashboards for analytics were left out of scope, matching "no dashboard yet" in this doc's Analytics section.*
