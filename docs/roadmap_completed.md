# Roadmap — completed sprint history

> **Historical record (last extended 2026-07-16, through v0.145.1).** The active, forward-looking
> roadmap is [`roadmap.md`](roadmap.md) — a concise list of *remaining* work. This file preserves
> the full detail of **completed** sprints (first archived 2026-07-05 so the active roadmap stays
> readable). Per-version detail also lives in [`../CHANGELOG.md`](../CHANGELOG.md).
>
> Covers **every completed sprint: 1–34** (foundation hardening, Tier 1 engine-core primitives, the
> Tier 2 pillar feature band, tier-split follow-ons) **+ the Foundation exit criteria, 35–37** (the
> performance & scaling band), **39–55** (timed room effects; admin-console + analytics work;
> the wishlist-promoted content/UX band — chat/feed split → global channels, marks, celestial
> cycles, context-attached commands), **56–69**, **70–84**, **85–88 combat**, and the
> **2026-07-16 admin UI/tooling/body-view tranche**. Layout note: recent completions are
> grouped near the top (below), the deep 1–34 archive follows under a second `# Lorecraft — Roadmap`
> header.
>
> **Not here:** 37.1 (scheduler-commit batching) + 38 (concurrency gate) were deferred to
> [`wishlist.md`](wishlist.md), not completed; Combat/PvP (former 61–64) likewise set aside there.
> Do not plan against this file; append newly-completed sprints here as they close.

---

## Sprint 88 — Combat Phase 4: Advanced

**Goal:** add only narrow combat depth layers with demonstrated utility. General-purpose
formations, persistent near/far tactical bands, grappling, flanking, screening, full PvP duel
rules, and generic mounted/siege systems remain out of scope.

**Tier split:** Tier 1 remains unchanged. Tier 2 `features/combat/` owns wounds, environment
modifiers, authored combo hooks, and opt-in encounter modes. Web/admin hosts consume the resulting
resolution traces and wound rows.

| # | Task | Status |
|---|------|--------|
| 88.1 | Wounds + body locations — persist after health recovery. | [x] v0.136.0 — Positive combat damage records active `CombatWound` rows with body location, severity, damage, and HP transition metadata. Wounds are inspection-only and do not apply stat penalties yet. |
| 88.2 | Terrain & cover as narrow defense modifiers. | [x] v0.143.0 — Room terrain and authored cover flags add target defense-score bonuses at resolution time, with terrain/cover/environment contributions recorded in combat traces. |
| 88.3 | Combo systems — only if data-authored actions need follow-up hooks. | [x] v0.144.0 — Authored opposed-attack actions can grant or consume encounter-scoped combo keys for temporary accuracy/damage bonuses, with before/after state recorded in traces. |
| 88.4 | Simultaneous-planning encounter mode (optional, arena/boss). | [x] v0.145.0 — NPCs can opt into `ai.combat_mode: simultaneous_planning`; their response queues immediately at the player's shared resolve time, and that encounter mode disables the normal auto-continue loop. |
| 88.5 | Mounted / siege combat. | Deferred to [`wishlist.md`](wishlist.md#combatpvp-historical-notes-updated-2026-07-15) — keep this content-specific until world content needs mounts, vehicles, artillery, or siege zones. Do not build a general-purpose formation/range subsystem speculatively. |

---

## Sprint 91 — Body Equipment & Condition View

**Goal:** give players and admins a body-centric view that shows all wear/wield slots, what is
equipped or empty, and current body-part condition from persistent combat wounds.

**Tier split:** Tier 1 remains unchanged. Tier 2 equipment defines body/slot presentation policy;
Tier 2 combat contributes wound condition rows; web/admin hosts render the composed view.

| # | Task | Status |
|---|------|--------|
| 91.1 | Body schema/view model — canonical body parts and equipment slot grouping. | [x] v0.137.0 — Added `features/equipment/body.py` with body-part definitions, full equipment-slot coverage, empty body views, and validation coverage. |
| 91.2 | Equipment body view — populate every slot with equipped/worn/wielded item state. | [x] v0.138.0 — `body_equipment_view()` renders every canonical slot as empty or populated with equipped item metadata. |
| 91.3 | Condition body view — group `CombatWound` rows by body part/severity/status. | [x] v0.139.0 — Active combat wounds now attach to the matching body part for condition inspection. |
| 91.4 | Player UI + command — add browser body panel plus `body` / `condition` command. | [x] v0.140.0 — Added player `body`/`condition` commands, the Standard layout Body tab, a shared body partial, and OOB body-panel refreshes. |
| 91.5 | Admin/player observe integration — show body/equipment/condition in admin Observe. | [x] v0.141.0 — Admin player state and observe snapshots include grouped body, equipment, and wound data; the admin editor and Observe panel render it. |
| 91.6 | Tests/docs — focused coverage and player/admin documentation. | [x] v0.142.0 — Added focused body/equipment/admin API coverage and documented player/admin body inspection. |

---

## Sprints 85–87 — Scheduled Intent Combat foundation, tactics, and content power

**Goal:** restore combat from the wishlist into active development as a supporting system, built
inside `features/combat/` with Scheduled Intent rather than tick-spam combat. These sprints stop
before speculative advanced depth; Sprint 88 remains deferred pending playtesting evidence.

| # | Task | Status |
|---|------|--------|
| 85 | **Combat Phase 1: Foundation.** Encounter aggregate, participant relationships, action submission/resolution pipeline, primary-channel queued action, attack/defend/flee, HP/stamina meters, immutable resolution records, audit-ready events, browser combat state, and NPC counter-intent stub. | [x] v0.109.0 — Scheduled Intent combat foundation shipped with `features/combat/`, scheduler-backed resolution, `CombatResolutionRecord` traces, defeat/downed policy, active-combat cleanup, and structured browser state updates. |
| 86 | **Combat Phase 2: Tactical Depth.** Stances, guarding, bounded reactions, wind-up interruption, combat status effects, ranged semantics, threat cues, NPC roles, and party assistance metadata. | [x] v0.117.0 — Tactical layer shipped without formations or persistent distance bands; `assist <player>` joins local encounters on the same side and records participation metadata. |
| 87 | **Combat Phase 3: Content Power.** Data-authored actions, equipment combat descriptors, effect hooks, boss phase resolvers, faction/reputation consequences, resolver/ruleset versioning, simulation reports, live-tunable rulesets, and player-facing combat help/tutorial docs. | [x] v0.126.0 — Combat content and tuning surfaces shipped, including `world_content/combat_actions.yaml`, `python -m lorecraft.tools.combat_balance`, admin combat ruleset tuning, and expanded `help combat` / tutorial docs. |

---

## Admin UI/tooling tranche — monitoring, observability, audit export, and NPC/AI runtime dashboard

**Goal:** promote the admin UI from a flat console into a category-based operations surface with
safe player editing, richer monitoring, and the first read-only world/runtime inspection panels.

| # | Task | Status |
|---|------|--------|
| Admin UI shell | Category title bar plus contextual sub-tabs for Overview, Tuning, World, Content, Moderation, and System. | [x] v0.131.0 — `webui/admin/index.html` now groups existing admin workflows into categories with nested sub-tabs. |
| Player monitoring/edit basics | Search/filter players, inspect session/activity state, and edit player records safely. | [x] v0.131.0 — Dashboard search/status filters, player edit panel, read-only Observe snapshot, mandatory admin reasons, and structured `admin_action` audit rows for edits/teleport/freeze/flags. |
| Live tuning/admin operations shell | Surface Clock, Weather, Combat, Progression, Economy, restart, backups, crashes, observability, analytics, audit, console, and alerts destinations. | [x] v0.131.0 — Existing endpoints are wired where available; high-risk/future controls remain disabled shells. |
| Audit and system health basics | Improve audit search and expose system health/scheduler state. | [x] v0.131.0 — Severity/source filters, audit facets, WebSocket/session/scheduler/audit/crash counters, and scheduler timeline. |
| EventBus metrics | Make event flow visible to System Health. | [x] v0.132.0 — EventBus tracks emitted counts and handler count/error/latency summaries; System Health displays emitted-event totals. |
| Audit export | Export filtered audit data for incident/debugging workflows. | [x] v0.133.0 — `/admin/audit/export` supports JSON/CSV using the same filters as the Audit tab; the UI downloads CSV with admin auth. |
| Sprint 89 — NPC/AI read-only runtime dashboard | Turn the NPC/AI shell into a useful read-only runtime inspection panel before adding controls. | [x] v0.134.0 — `/admin/world/npcs` now returns room, behavior, HP, AI config, schedule, hooks, context commands, escort, and loot metadata; the NPC/AI tab renders the dashboard. |

---

## Sprints 70–84 — QoL, admin/world cleanup, progression, disciplines, zone climate, Ashmoore shops, hunts, and database observability (v0.78.0–v0.104.0, archived 2026-07-14)

> Moved here from the active roadmap on 2026-07-14 once Sprint 80 closed. Full task
> detail preserved below; per-version notes in [`../CHANGELOG.md`](../CHANGELOG.md).

## Sprint 84 — Database query observability tooling

**Goal:** make future database optimization evidence-driven by recording query timing/frequency to
non-DB logs and adding an offline analyzer before adding schema/index changes.

| # | Task | Status |
|---|------|--------|
| 84.1 | Add SQLAlchemy cursor timing hooks for game and audit engines. | [x] v0.104.0 — `db.configure_query_logging()` writes one compact JSONL record per cursor statement to `logs/sql_queries.log` by default, with duration, statement fingerprint, rowcount, and parameter counts but not parameter values. |
| 84.2 | Keep query logging tunable and outside the measured DB workload. | [x] v0.104.0 — Added `LORECRAFT_DB_QUERY_LOG_ENABLED`, `LORECRAFT_DB_QUERY_LOG_PATH`, and `LORECRAFT_DB_QUERY_SLOW_MS`; `start.sh` enables the dev runtime log at `logs/sql_queries.log`; generated `*.log` files remain ignored. |
| 84.3 | Add an analysis tool for slowest, most frequent, and missing-index candidates. | [x] v0.104.0 — `python scripts/analyze_query_log.py --log logs/sql_queries.log --database game.db` summarizes slow statements, frequent fingerprints, and `WHERE` / `JOIN` / `ORDER BY` index candidates, marking primary-key/index-covered SQLite columns when a DB path is supplied. |
| 84.4 | Document operator workflow and focused tests. | [x] v0.104.0 — Updated observability/admin docs and added focused tests for JSONL query logging, analyzer grouping, and SQLite index detection. |

## Sprint 83 — Scavenger-hunt quest content

**Goal:** promote scavenger hunts from a minimal three-item demo event into a repeatable
content pattern for 3-7 themed items scattered through a zone, with optional speed-scaled
coin rewards.

| # | Task | Status |
|---|------|--------|
| 83.1 | Add a generic spread-placement option for authored hunts. | [x] v0.103.0 — `spread_items: true` now chooses spawn rooms without replacement while unused rooms remain, preserving seeded deterministic placement. |
| 83.2 | Add elapsed-time reward scaling without new Tier 1 policy. | [x] v0.103.0 — Hunt reward tiers are data-driven (`reward.tiers[].max_elapsed_seconds` + `coins`) and measured from the player's first clue item using the existing world-clock epoch and ledger coin primitive. |
| 83.3 | Ship a seven-item Ashmoore hunt. | [x] v0.103.0 — Expanded the Harvest Trinket Hunt to seven clue item definitions, spread across seven Ashmoore rooms, with coin rewards of 2000/250/100 for under 1/2/5 minutes. |
| 83.4 | Update docs and focused tests. | [x] v0.103.0 — Updated player/builder/scavenger-hunt docs and added unit coverage for spread placement, timed reward tiers, and shipped-content lint. |

## Sprint 82 — Ashmoore fixed-location shop village

**Goal:** make Ashmoore's village services feel like a real town market while staying inside the
existing economy model: fixed-location shops are represented by stationary NPC shopkeepers with
`shop:` blocks. Roving shops remain possible by moving an NPC, but this sprint intentionally avoids
new first-class shop-hours or room-owned-shop engine work.

| # | Task | Status |
|---|------|--------|
| 82.1 | Add a compact, coherent Ashmoore shop cluster connected to the existing market. | [x] v0.102.0 — Added `ashmoore_general_store` and `ashmoore_bakery` off `market_stalls`, both indoor town rooms with reciprocal exits and feature-dense descriptions. |
| 82.2 | Add dedicated fixed-location services for potions, food/drink, armory basics, and general goods. | [x] v0.102.0 — Added stationary shopkeepers Pella Wren, Harl Venn, Cora Vale, and Lysa Hearthloaf; expanded Mira's Wandering Crow counter into a real food/drink/bar shop. |
| 82.3 | Use existing economy surfaces for pricing, finite cash, finite stock, and restocking. | [x] v0.102.0 — Shops use focused `buys_categories`, `sell_ratio`, `region_mult`, `starting_coins`, finite quantities, unlimited staples, and `restock_to`/`restock_every_ticks` where appropriate. |
| 82.4 | Prefer existing stock and add only missing Ashmoore-local goods. | [x] v0.102.0 — Reused existing potions, food, drink, light sources, containers, and tools; added four local armory items (`ashmoore_hunting_knife`, `ashmoore_militia_spear`, `ashmoore_padded_jack`, `ashmoore_kettle_helm`). |
| 82.5 | Validate world content and focused economy/world tests. | [x] v0.102.0 — `world_cli validate --file world_content/world.yaml` clean; `tests/tools/test_world_content_reachability.py` and `tests/unit/test_economy.py` passed (`26 passed`). |

## Sprint 70 — Social emotes & quality-of-life commands

**Goal:** small player-facing conveniences requested during play. `equip`/`unequip` already exist
as **`wear`/`wield`** (equip) and **`remove`/`unwield`** (unequip) — no new work needed there.

| # | Task | Status |
|---|------|--------|
| 70.1 | **Social emotes `wave` / `point`.** `wave [at <target>]` and `point at <target>` broadcast to the room; targets resolve to a co-located NPC or player by name, otherwise the raw text (so `point at sign` / `wave at the sky` work). SOCIAL-scoped. | [x] v0.78.0 — `commands/social.py`, `tests/unit/test_social_emotes_and_quests_command.py`. |
| 70.2 | **Player `quests` command.** `quests` (alias `quest`) lists the player's quests with status; a multi-stage quest shows `stage N/M` and the current stage's objective; completed/failed are marked. Read-only (progression stays event-driven). | [x] v0.78.0 — `features/quests/commands.py` wired via `register_all_commands` (gated on the quests feature). |

---

## Sprint 71 — Backlog cleanup: admin UI + player-facing bugs

**Goal:** small backlog items surfaced from admin console and player-facing use, mostly UI/presentation
work, with one item blocked on a product decision.

| # | Task | Status |
|---|------|--------|
| 71.1 | **Admin Issues panel: editable priority + description.** Backend PUT endpoint already accepts both fields; needs the admin SPA form/UI work. | [x] v0.91.0 — `webui/admin/index.html` (per-row priority `<select>` mirroring the status select; description `<textarea>` + Save in the detail row), `tests/e2e/test_admin_issues.py` (2 new e2e cases, commit `853425e`). |
| 71.2 | **Admin World panel: zone + name filter** (+ prerequisite `Room` schema split). Client-side zone dropdown + live name-substring search over the existing `GET /admin/world/rooms` response. Gated on first splitting the conflated `Room.area_id` into orthogonal `zone` + `room_type` fields. **Full design: [Sprint 71.2 design](#sprint-712-design--room-zoneroom_type-split--admin-world-filter) below.** | [x] v0.91.0 — All 71.2a-f complete (schema split `zone`/`room_type`, economy re-keyed, weather dedup guard, admin filter UI, test updates; branch `sprint-71-2-zone-room-type-split`, commits `2e9f466`, `7e90bf4`). |
| 71.3 | **Player map rendering: z-level filtering + shape stability.** Isolate the fix to `rendering.py`; flag if it turns out the `Room` schema itself needs a change (would escalate scope). | [x] v0.91.0 — z-level filtering verified correct (regression test added `test_frontend_map.py`); fixed shape-stability bug where tie-break was non-deterministic (now sorts by distance + room_id), commit `2e9f466`. |
| 71.4 | **Help command: better formatting (bold/color).** Presentation-only improvement to the `help` command's output. | [x] v0.91.0 — Backend `MessageType.HELP` tag (`c29fea1`) + frontend `.msg-help` CSS styling with `--lc-accent` token + e2e regression test (`357c533`, branch `sprint-71-4-help-formatting`). |
| 71.5 | **Quest XP rewards.** | [x] **Closed by Sprint 73.6.** Product decision (2026-07-12): Lorecraft **does** have XP/leveling progression, unblocking this item. Implemented as commit `5bf8fa5` on branch `sprint-73-progression` — `features/quests/service.py::_award_rewards` now calls the Sprint 73 reward interpreter (`apply_rewards`), so quest `rewards.xp` (and `coins`/`skill_points`) genuinely apply instead of being discarded. See [Sprint 73 — Generalized rewards + XP/leveling core](#sprint-73--generalized-rewards--xpleveling-core) below. |

---

### Sprint 71.2 design — Room `zone`/`room_type` split + admin World filter

> **Provenance — THREE same-day correction passes (2026-07-11). This is the FINAL, implementable version.**
> (1) **Lost-design reconstruction fix.** Originally drafted in another worktree session and *lost* before it
> reached this file (confirmed gone — not in any worktree, stash, or history). Reconstructed from memory
> 2026-07-11, then corrected against live code.
> (2) **User product decision (same day)**: weather fronts key off `zone` not `room_type`; `room_type` is a
> small *universal* room-kind taxonomy, not a byte-for-byte rename of `area_id`.
> (3) **User final decisions (same day)** resolving the two open items: **`room_type` values are
> `{cave, wilderness, town}`** (user "keep wilderness" — reverses the informal "forest"; open-ended, expect
> more, e.g. a future `road` kind), scope confirmed **universal** across all ~104 rooms; **economy keys off
> `zone` alone** (option (i)); **weather uses a runtime dedup-adjacent guard** (not YAML path shortening).
> All open items are now resolved and this section is **ready for backend implementation.** One number — the
> collapsed `ashmoore` economy multiplier — carries a *recommended* value (1.0) pending a rubber-stamp; it is
> explicitly **non-blocking** (71.2b may proceed).

**Problem.** `Room.area_id: str | None` (`src/lorecraft/engine/models/world.py`) conflates two independent
meanings. `world_content/world.yaml` uses **9 distinct values**, not 4:

- *Ashmoore-era rooms* encode a **kind**: `town` (x11), `wilderness` (x8), `cave` (x6). (Geographically in
  Ashmoore — e.g. `village_square` is "The Village Square of Ashmoore" — but `ashmoore` never appears as an
  `area_id` value.)
- *Sprint 69 rooms* encode a **geographic zone**: `cogsworth` (x27), `whisperwood` (x30), `port_veridian` (x25).
- *Connector rooms* each carry a **singleton**: `trade_road`, `forest_road`, `coast_road` (`old_trade_road`,
  `forest_road`, `river_bend`).

**The split (two orthogonal fields on `Room`):**

- `zone: str | None = None` — **geographic/thematic, user-facing.** Exactly **4** values:
  `ashmoore`, `cogsworth`, `whisperwood`, `port_veridian`. Powers `RoomRepo.resolve_ref` zone-qualified
  teleport addressing, `rooms_in_area`, the admin World grouping+filter, `features/npc_ai/service.py` wander
  bounds, `features/npc/side_effects.py` zone-targeted effects, **weather fronts, and economy region pricing.**
- `room_type: str | None = None` — **universal room-kind taxonomy.** Small, open-ended set
  `{cave, wilderness, town}` "for now" (expect more, e.g. a future `road` kind for connector rooms).
  Describes *what kind of room* it is, applied across **all** zones — NOT each zone as its own value. This is a
  genuine per-room reclassification (content authoring), not a mechanical rename.

**`zone` mapping — the 4-value geographic fold** (every current `area_id` value → `zone`):

| current `area_id` | rooms | → `zone` |
|---|---|---|
| `town` | Ashmoore starter (x11) | `ashmoore` |
| `wilderness` | Ashmoore (x8) | `ashmoore` |
| `cave` | Ashmoore (x6) | `ashmoore` |
| `cogsworth` | Cogsworth (x27) | `cogsworth` |
| `whisperwood` | Whisperwood (x30) | `whisperwood` |
| `port_veridian` | Port Veridian (x25) | `port_veridian` |
| `trade_road` (`old_trade_road`) | connector | `cogsworth` |
| `forest_road` (`forest_road`) | connector | `whisperwood` |
| `coast_road` (`river_bend`) | connector | `port_veridian` |

**Connector target zones confirmed correct** (each road assigned to the zone it leads *toward* travelling
outward from Ashmoore).

**`room_type` — universal kind taxonomy `{cave, wilderness, town}` (growing).** Applied to all ~104 rooms
across all 4 zones (scope confirmed by the user). cogsworth/whisperwood/port_veridian rooms are NOT
`room_type=<zone-name>`; each gets a kind (a Cogsworth street = `town`; a Whisperwood glade = `wilderness`; a
Port Veridian dock = `town`; a cave chamber = `cave`).
- Ashmoore maps mechanically from today's `area_id`: `town`→`town`, `wilderness`→`wilderness`, `cave`→`cave`.
- **The other 3 zones + connectors need fresh per-room kind authoring** — a *content* task across the world,
  not a mechanical rename. Connector roads fit none of `{cave, wilderness, town}`; a future `road` kind is the
  likely home for them (consistent with the open-ended set). For 71.2 they may take the nearest existing kind
  (e.g. `wilderness`) or be left `None` until `road` lands — author's discretion, since nothing keys off a
  connector's `room_type` once economy moves to `zone` (below).

---

**RESOLVED — OPEN ITEM A → weather: `zone` keying + runtime dedup-adjacent guard.**
Verified in `src/lorecraft/features/weather/fronts.py`: `_activate()` copies the YAML `path:` verbatim, no
dedup (L116); `_advance_fronts()` advances `zone_index` every `travel_ticks` with no consecutive-equal guard
(L150). **Decision:** weather fronts key off `zone`; `weather_fronts.yaml`'s `path:` lists get a
**straightforward mechanical value-swap** from old area_id values to zone values — **leaving adjacent
duplicates literal in the YAML** (no hand shortening, no extending to new zones), and a **small runtime
dedup-adjacent guard** in `fronts.py` collapses consecutive-equal entries at run time so no redundant
`_leave_zone`→`_enter_zone` narration fires. Concretely:
- `spring_squall` `[town, wilderness]` → `[ashmoore, ashmoore]` (kept as a literal 2-entry list).
- `coastal_squall` `[port_veridian, coast_road, whisperwood]` → `[port_veridian, port_veridian, whisperwood]`
  (kept as a literal 3-entry list).
The guard (collapse consecutive-equal `front.path` entries — cleanest in `_activate()` after the value-swap
load, so `zone_index` stepping in `_advance_fronts()` never lands on an adjacent duplicate) is the only new
engineering. No content decision about single-zone-vs-travel — the paths are a pure value-swap.

**RESOLVED — OPEN ITEM B → economy keys off `zone` alone (option (i)).**
Verified: `RegionPricing.area_id` PK (`features/economy/models.py`), `EconomyRepo.region_for_area`,
`service.py`'s `ctx.room.area_id` lookup; `economy.regions` today prices 6 area_id values. **Decision:**
economy region pricing keys off `zone` (4 zones); the composite and dedicated-field options are **off the
table**. Consequences:
- cogsworth/whisperwood/port_veridian keep their existing multipliers unchanged (1.1 / 1.05 / 0.95) — those
  were already zone-level.
- Ashmoore's three area_id rows (`town` 1.0, `wilderness` 1.15, `cave` 1.25) **collapse into one
  `ashmoore` row.** The within-Ashmoore gradient is dropped, as intended.
- **Recommended `ashmoore` region_mult = `1.0` (pending rubber-stamp; NON-BLOCKING — 71.2b may proceed).**
  Rationale, data-grounded: Ashmoore has exactly **one** shop — the innkeeper at `wandering_crow_inn`, an
  `area_id: town` room priced 1.0 today. No shop sits in any `wilderness` or `cave` room, so those two
  multipliers (1.15 / 1.25) are **inert** — they never apply to a transaction. Setting `ashmoore = 1.0`
  therefore preserves *actual player-facing prices with zero change*, and keeps the starter zone at the clean
  baseline. (If the intent were to preserve an average regional *price level* rather than shop-location
  fidelity, the room-count-weighted mean would be ~1.108 — but that would *raise* the innkeeper's prices, so
  it is not recommended.)
- `world/validator.py`'s economy check (L504-508) must validate region keys against the set of room `zone`
  values (4) instead of `area_id`.

---

**`area_id` disposition — removed outright (clean replace, no back-compat alias).** Pre-1.0, single world
file, no Alembic (the world DB is derived state reseeded from `world.yaml` via `world/loader.py`); a lingering
half-renamed field is the half-done seam AGENTS.md warns against. Migration: change the model, change
loader/validator, reseed from `world.yaml`.

**Admin filter — client-side, no new query param.** `GET /admin/world/rooms`
(`webui/admin/routers/world.py`) already returns the full room list unpaginated; add `zone` (and `room_type`)
to each room dict. The zone dropdown + live name-substring search are pure client-side JS over that response
(`webui/admin/index.html` ~L1002-1015 already groups by `area_id` — repoint to `zone`).

**Call sites to update in lockstep** (grepped 2026-07-11): `engine/models/world.py` (field split),
`engine/repos/room_repo.py` (`resolve_ref`, `rooms_in_area` — geographic + weather + economy now all key
`zone`), `features/weather/fronts.py` + `world_content/weather_fronts.yaml` (value-swap paths to `zone` +
runtime dedup guard), `features/economy/{models,repo,service}.py` + `economy.regions` in world.yaml (zone
keying; RegionPricing PK renamed to `zone`), `features/npc_ai/service.py` (L167 — **no** world content sets
`ai.area` today, so zero content impact), `features/npc/side_effects.py` (L185-189 — verify no content relies
on the old town/wilderness default), `webui/admin/routers/world.py` (GET/PUT/POST bodies+response),
`webui/admin/index.html` (grouping + filter UI), `world/validator.py` (`RoomData` fields + economy check vs
`zone`), `world/loader.py` (round-trip), `world_content/world.yaml` (room `zone`+`room_type` + economy
regions). Tests: `tests/unit/test_world_loader.py`, `test_economy.py`, `test_npc_ai.py`,
`test_weather_fronts.py`, `test_room_ref_resolution.py`, `test_spawns.py`, `test_phase_a_acceptance.py`.

**Proposed tasks:**

- [x] 71.2a — Schema split: add `zone` + `room_type` on `Room`; remove `area_id`. Apply the `zone` fold
  (table above) and the Ashmoore `room_type` mapping (`town`/`wilderness`/`cave` unchanged); reseed.
  *Success: `world.yaml` rooms carry 4 `zone` values; loader round-trips clean.*
- [x] 71.2b — Author `room_type` `{cave, wilderness, town}` for cogsworth/whisperwood/port_veridian (and
  connectors — nearest kind or `None`); re-key economy pricing to `zone` (RegionPricing PK → `zone`;
  `region_for_area`/`service.py` lookups → `ctx.room.zone`); collapse Ashmoore to one `ashmoore` row at
  `region_mult 1.0` (recommended); update `world/validator.py` economy check to validate against `zone`.
  *Success: every room has a `room_type`; economy prices resolve via `zone`; cogsworth/whisperwood/
  port_veridian prices unchanged; `test_economy.py` green.*
- [x] 71.2c — Repoint weather fronts to `zone`; value-swap `weather_fronts.yaml` paths to zone values
  (adjacent duplicates left literal); add the runtime dedup-adjacent guard in `fronts.py`. *Success:
  `spring_squall`/`coastal_squall` fire with no duplicate leave/re-enter narration; `test_weather_fronts.py`
  green.*
- [x] 71.2d — Repoint remaining geographic consumers to `zone` (`resolve_ref`, admin grouping, `npc_ai`,
  `npc/side_effects`). *Success: teleport `ashmoore.<room>` resolves; npc/side-effect tests green.*
- [x] 71.2e — Admin World panel: add `zone` (+`room_type`) to `GET /admin/world/rooms`; client-side zone
  dropdown + live name-substring filter, usable together. *Success: dropdown lists the 4 zones; typing
  narrows live; no new query param.* Done — `webui/admin/index.html`: `#w-filter-zone` select (all zones +
  the 4 named zones, `onchange`) and `#w-search` input (`oninput`, cached `allRooms` + `renderRooms()`,
  mirroring the Help tab's `h-search`/`renderHelp()` idiom) filter together before the existing zone-grouped
  render; `#w-count` mirrors the Issues tab's `#i-count` "N shown · M hidden" convention. No e2e coverage
  existed or was added for the admin World panel (gap, flagged for 71.2f/follow-up).
- [ ] 71.2f — Update the 7 test files; add a zone-qualified `ashmoore.<room>` `resolve_ref` case.
  *Success: `make test` green.*

**Remaining flagged item (non-blocking rubber-stamp):**

- The collapsed **`ashmoore` economy `region_mult`** is *recommended* at **1.0** (rationale above: Ashmoore's
  sole shop is a `town`/1.0 room; the `wilderness`/`cave` multipliers were inert). Awaiting a rubber-stamp or
  override — 71.2b proceeds with 1.0 unless the user says otherwise. Everything else in OPEN ITEMS A and B is
  finally decided.

---

## Sprint 72 — Backlog cleanup: tooling tech-debt + admin ops + mobile polish

**Goal:** the next tranche of small, well-understood backlog items — one scripting-tooling
tech-debt fix, two admin-operations conveniences (split by risk), and one leftover responsive-CSS
polish. Deliberately *not* an XP/leveling system: that product decision (does Lorecraft have any
leveling progression at all?) is still open and unrelated to this cleanup pass (see Sprint 71.5).

| # | Task | Status |
|---|------|--------|
| 72.1 | **Scripting catalog generator enables features (Phase A tech-debt #2).** `docs/scripting_api.md` is generated by `_load_scripting_vocabulary()` in `src/lorecraft/tools/world_cli.py` (~L211–226), which calls `discover_features()` (import-only — fires module-level `@register_spec` decorators) but never *enables* any feature, so enable-time vocabulary is missing from the doc. Proof: `features/reputation/conditions.py::register()` (L81–100) runs only via the reputation feature's `register_fn` at enable-time, and it uses the registries' plain `.register(name, fn)` rather than `register_spec(name, fn, VocabEntry(...))` — so `actor_reputation_at_least`/`adjust_reputation` never reach the catalog even if features *were* enabled. **Two-part fix:** (a) the generator enables every discovered feature via a lightweight stub `AppState` (note `register_fn(state)` also wires real services — see `features/loader.py::wire_features`; reputation's `_wire` already ignores `state`); (b) affected features migrate their enable-time registrations from plain `register()` to `register_spec()` with a `VocabEntry`. Suggested shape: each feature exposes a state-free `register_vocabulary()` that both its `register_fn` and the generator call. Composition-layer only — no engine→feature tier violation (`world_cli.py` already imports features). Regenerate + re-check via `make scripting-docs`. | [x] v0.92.0 — (a) `_load_scripting_vocabulary()` now wires every discovered feature via a minimal doc-gen `AppState` stand-in (`_DocGenState` holding a populated `ServiceContainer` — the only surface enable-time `register_fn`s read); (b) `features/reputation/conditions.py::register()` migrated to `register_spec(...)` so `actor_reputation_at_least` (command+dialogue) and `adjust_reputation` (side effect) now appear in `docs/scripting_api.md` (18 entries, no capability overlaps). New generator tests in `tests/unit/test_scripting_api_doc.py`. |
| 72.2 | **Admin: DB wipe + reseed from `world.yaml` (lower-risk half of the "restart + reload" ask).** Admin-triggered action that wipes and reseeds the game DB from `world_content/world.yaml`, reusing the existing `scripts/import_world.py --fresh` path (the same one `start.sh` uses to build the seed DB). Data-driven — reseeds from the YAML, no hardcoded content. Shippable independently of the engine restart (72.3). Motivation: test updates pushed to `main` end-to-end from the browser without shelling in. | [x] v0.92.0 — `POST /admin/world/reseed` endpoint (superadmin-gated, audit-logged, validates before deletion); admin Web panel adds "Danger zone" button in World tab (confirm-gated); players in deleted rooms relocated to seed start room. Tests: `test_world_reseed.py`, `test_admin_world_reseed.py`, `test_admin_world_reseed_ui.py`. |
| 72.3 | **Admin: restart the running engine process (riskier half — needs a supervisor).** `start.sh` launches `uvicorn lorecraft.main:app` directly with **no supervising process**, so a naive in-process exit would just kill the server handling the request. **Full design: [Sprint 72.3 design](#sprint-723-design--admin-engine-restart--process-supervision) below** — investigation done; the admin-facing half (an endpoint that *requests* a restart) is now scopeable, but the *performer* half carries a genuine product/ops fork (real supervisor vs. in-process exec-replace) surfaced there for a decision. | [x] v0.92.0 — Option A supervisor built: `scripts/supervisor.py` launches uvicorn as child, watches for restart sentinel, performs graceful SIGTERM → wait → relaunch (no reseed); admin `/ops/restart` endpoint + System tab button (superadmin, confirm-gated, audit-logged); armed indicator via heartbeat; crash-recovery guard; regression test proves restart preserves live DB. |
| 72.4 | **Mobile chat tab-collapse polish.** Leftover from Sprint 45.3: on small screens the chat pane should collapse into a tab rather than stack. Purely responsive/CSS in the player webui — low risk, no engine touch. | [x] v0.92.0 — Chat pane collapses into own "Chat" tab on small screens; Standard layout tab bar now isolates Chat from Feed. |

### Sprint 72.3 design — Admin engine restart + process supervision

> **Provenance.** Investigation + design write-up 2026-07-12 (branch `sprint-72-3-restart-design`, based on
> `376e610`). Design-only per scope: no admin endpoint, no `start.sh` change, no exit code shipped here. The
> deployment/process-model findings below are verified against the live tree; the recommendation ends on a
> **genuine unresolved fork** (real supervisor vs. in-process exec-replace) that is a product/ops preference,
> not a technical-correctness question — laid out with tradeoffs rather than silently decided.

**Problem.** An admin action "restart the running engine" faces the self-immolation problem: the process
handling the HTTP request *is* the process that must die and come back. A naive `os._exit()`/`sys.exit()` from
inside a request handler kills the server with nothing to bring it back up — every connection dropped, server
down permanently. The current process model gives us **nothing to catch that fall.**

**Verified deployment / process model (2026-07-12).**

- **No supervisor of any kind exists.** No `Procfile`, no `Dockerfile`/`docker-compose`, no systemd `.service`
  or `.socket`, no gunicorn/supervisor config anywhere in the repo (searched). The *only* launcher is the
  bespoke, dev-oriented `start.sh`. There is no production deployment story to conform to — the restart
  performer is greenfield either way.
- **`start.sh` is a dev launcher, not a supervisor.** Its final line runs `uvicorn lorecraft.main:app` as a
  plain **foreground child** (not bash's `exec` — bash stays as parent PID but does nothing: no `trap`, no
  `while` relaunch loop, no signal forwarding). Under `set -euo pipefail`, when uvicorn exits, bash exits with
  it. So today **if uvicorn crashes it stays down** — the restart performer is also the missing
  crash-recovery piece. (The `exec`-vs-fork distinction is immaterial to the design: either way nothing
  relaunches the child.)
- **uvicorn runs single-process, single-worker** (no `--workers`, no `--reload`). One process, one event loop,
  one listening socket on `:8000`. uvicorn *bundles* a `supervisors/` package (its own `--reload`/`--workers`
  machinery) but neither mode is enabled here.
- **`start.sh` reseeds the runtime DB on every launch — the critical footgun.** `reset_runtime_db` copies
  `test_dbs/lorecraft-dev-*.db` → `/tmp/lorecraft-dev-*.db` (deleting stale WAL/SHM) *before* launching. So
  **re-running `start.sh`'s body wipes all live runtime state** (player positions, sessions, world mutations)
  back to seed. That is exactly what 72.2 (wipe+reseed) wants, and exactly what "restart but keep players where
  they are" must **avoid.** Any restart performer must run the *relaunch* without re-running the reseed.

**What disruption is already tolerated — the reconnect-grace cushion (verified).** This determines how
seamless a restart can be:

- **Client** (`webui/player/static/js/app.js`): auto-reconnect with exponential backoff — up to **10 attempts**,
  delay `min(1000 · 1.5ⁿ, 15000)` ms (cumulative ≈ 75–80 s before giving up). A server outage of roughly a
  minute is survived automatically: the browser just keeps retrying and re-attaches when the port rebinds.
- **Server** (`main.py` WS handler + `engine/services/save.py` `SessionSafetyService`): on an involuntary WS
  drop, `begin_grace_period` sets the session `status="grace"` in the **game DB** with
  `disconnect_grace_seconds` (default **60 s**, `config.py`). On reconnect within grace,
  `start_or_resume_session` flips grace→active, returns `reconnected=True`, and pushes a `reconnect_sync`
  payload that restores the UI seamlessly ("Reconnecting…" → back in place).
- **Crucial property:** grace/session state is **DB-persisted, not in-memory** — it survives a process restart
  **iff the DB file survives** (i.e. the reseed is skipped). And grace-begin runs only in the WS handler's
  `except WebSocketDisconnect` path, which fires only on a **graceful** socket close (SIGTERM → uvicorn
  lifespan shutdown → close frames). On an **abrupt kill / `execv`** (no close frame, no lifespan shutdown)
  grace-begin never runs: the session is left `status="online"`, and on reconnect `boot_active_session` boots
  the stale session and `start_or_resume_session` starts a *fresh* one (`reconnected=False`, no
  `reconnect_sync`). The player still gets back in — their position lives on the `Player` row, not the session —
  but the reconnect is a cold "new login," not the seamless cushion.

  **So a restart is seamless only if BOTH hold: (a) graceful shutdown (SIGTERM, sockets closed cleanly so
  grace-begin runs) AND (b) the runtime DB is preserved (reseed skipped).** This is the fact that decides the
  fork below.

**Options considered.**

- **Option A — Wrapper/supervisor process (parent watches child, relaunches on request).** A small supervisor
  (a new `scripts/` entry point, or `start.sh` restructured into "cold-boot prep" + "run loop") launches
  uvicorn as a child and `wait`s on it; on a designated restart exit code (or an observed sentinel file/signal)
  it relaunches — *without* re-running the DB reseed. The admin endpoint requests a restart by touching a
  sentinel / sending a signal; the supervisor performs it by **SIGTERM → wait for graceful lifespan shutdown →
  relaunch.**
  - *Pros:* the only option that reloads **code** (new Python interpreter — picks up a deploy) AND does a
    **graceful** restart (SIGTERM lets the WS handler run grace-begin and lets uvicorn close sockets), so the
    reconnect-grace cushion actually fires. It is *also* the missing general crash-recovery piece (today a
    crash = permanent downtime), so it pays double. Composes cleanly with a real process manager later
    (systemd `Restart=`, container restart policy) by mapping the same exit code.
  - *Cons:* requires restructuring `start.sh` (or a new entry point) — more than an "additive hook." Must
    carefully split cold-boot prep (venv/seed/**reseed once**) from the relaunch loop (**no reseed**) so a
    restart doesn't wipe live state via the footgun above. A bash supervisor loop is fiddly (signal forwarding,
    exit-code plumbing, restart-storm guard); a small Python supervisor is cleaner but is one more process.

- **Option B — In-process exec-replace (`os.execv`).** The admin handler calls `os.execv(sys.executable,
  [...uvicorn argv...])`, replacing the process image in place: PID persists, code + interpreter fully reloaded,
  no new process, no `start.sh` change (works today from inside the app).
  - *uvicorn compatibility (investigated):* uvicorn's own `--reload` uses `execv`-style restarts under the
    hood, so exec-replace is a known-workable pattern for it — **but** uvicorn does it from a *reloader parent*
    that pre-binds and hands down the listening socket, not from inside a request handler on the serving
    process. Calling `execv` from within the event loop tears down the running loop, every live WS, and the
    listening socket **instantly**, running **no** Python cleanup — no `atexit`, no `finally`, no FastAPI
    lifespan shutdown. Consequences: the lifespan shutdown never runs (no clean world-clock stop / DB
    checkpoint); every WS is severed **abruptly with no close frame** → identical to SIGKILL for grace purposes
    (**grace-begin skipped**, players reconnect cold, no `reconnect_sync`); the `:8000` listening socket is
    closed on exec, leaving a brief (typically sub-second) unbound window until the re-exec'd uvicorn rebinds —
    clients mid-backoff simply retry and succeed. It re-runs the lifespan **startup** (`ensure_world_bootstrapped`,
    `_ensure_admin_seed`, issues/news/help bootstrap), all idempotent against the existing DB, and — because it
    does **not** run `start.sh` — it happens to **preserve** the runtime DB (avoids the reseed footgun *by
    accident*, which is fragile: a future coupling could reintroduce it).
  - *Verdict:* technically works (PID persists, port comes back, state preserved) but is **always the abrupt
    path** — it cannot do the "graceful SIGTERM, drain, *then* relaunch" that A can, because `execv` *is* the
    shutdown. Reconnect is functional but never seamless. Cheapest possible (no infra, no `start.sh` change).

- **Option C — External restart-signal only (split the scope; no lifecycle code in the request path).** Make
  72.3's structure explicit: the endpoint only *requests* a restart (writes a sentinel file, e.g.
  `/tmp/lorecraft-restart.request`, or sends a signal) with an audit-log entry + confirmation gate; the *thing
  that listens and performs* the restart is a separate deliverable (a supervisor per A, or a signal handler
  that triggers a graceful self-restart). This is not a third *performer* — it is the **framing** that lets the
  small, safe half ship independently of the risky half, exactly mirroring how 72.2 (wipe+reseed) was already
  split from 72.3 by risk.
  - *Pros:* de-risks the admin-facing half; the endpoint can land while the performer design settles; clean
    audit/confirm story.
  - *Cons:* an admin clicking "restart" with no performer wired does nothing — needs explicit "not yet armed"
    UX/gating so it never looks silently broken.

**Recommendation (structure) + the open fork (performer).**

The **structure is not in doubt**: adopt Option C's split — a small, safe **72.3a "request a restart"** endpoint
(sentinel/signal + audit + confirm + "armed?" gating), shippable independently, cleanly mirroring the 72.2/72.3
risk split. That half has no real design risk and no tier concern (it lives in `webui/admin/`, composition
layer, touching only a sentinel file or a signal — no engine→feature violation, no hardcoded world IDs).

The **performer half (72.3b) is a genuine product/ops fork, surfaced here rather than decided:**

- **If the goal is a real running story** (survive crashes, graceful reloads that keep players seamlessly
  attached, a path toward systemd/containers) → **Option A (supervisor).** It is the only option that gives a
  graceful restart *and* code reload *and* crash recovery, and it forces the healthy cold-boot-vs-relaunch
  split around the reseed footgun. Cost: real work on `start.sh`/a new entry point.
- **If the goal is only dev convenience** ("let an admin reload code without shelling in," abrupt drops
  acceptable, no new infra) → **Option B (exec-replace)** alone is defensible: it works today, needs no
  `start.sh` change, preserves runtime state, and the client backoff + fresh-login reconnect is a tolerable UX
  for a dev tool. Its ceiling is low (never seamless, no crash recovery) and its state-preservation is
  incidental rather than designed.

**This is a product/ops preference, not a correctness question — it should be decided by the user before 72.3b
is built.** My assessment: **Option A is the better default** — the app has *no* supervisor and *no* deployment
story, so the performer must be built regardless, and A is simultaneously the crash-recovery fix the process
model is missing today; B's appeal is real but only if 72.3 is scoped as a throwaway dev affordance. Either way,
72.3a (request-only endpoint) can proceed now.

**Call-sites / files affected (for whichever performer is chosen).**

- `start.sh` (Option A only) — restructure into cold-boot prep (venv install, seed-DB init, **`reset_runtime_db`
  once**) vs. a relaunch loop that re-runs uvicorn **without** reseeding; add restart-exit-code handling and a
  restart-storm guard. **No change under Option B.**
- New `scripts/supervisor.py` or `scripts/run.sh` (Option A) — the watch/relaunch loop, if kept out of
  `start.sh` itself.
- `webui/admin/` (both options) — the admin endpoint + button that *requests* the restart (sentinel/signal for
  A; the in-process `execv` call for B), behind admin auth, audit-logged, with a confirm gate and, for A, an
  "armed?" indicator (is a supervisor actually watching?).
- `main.py` lifespan (context, both options) — the graceful-shutdown path (SIGTERM under A) is what lets the WS
  handler's `begin_grace_period` fire and the reconnect cushion work; `execv` under B bypasses it entirely
  (documented limitation, not a change).
- `config.py` — no change required; note `disconnect_grace_seconds` (60 s) vs. the client's ~75–80 s backoff
  window already bound how long a restart can take before players fall out of grace.

**Proposed sub-tasks.**

- [x] 72.3a — **Admin "request restart" endpoint (safe half, shippable now).** Done. `GET/POST /admin/ops/restart`
  (`webui/admin/routers/ops.py`) writes a restart sentinel via `lorecraft.ops.RestartControl`, superadmin-gated
  with a `confirm` flag, audit-logged (`GameEvent.ENGINE_RESTART_REQUESTED`), and gated on an "armed?" indicator
  read from the supervisor's heartbeat — an unarmed instance returns 409, never a silent no-op. A "System" tab
  button in the admin console drives it. No process-lifecycle code in the request path; no engine/tier touch.
- [x] 72.3b — **Performer — Option A supervisor (product decision made).** Done. `start.sh` split into a
  one-time cold-boot prep section (venv, seed init, `lorecraft.ops.coldboot` reseed **once**) and a run loop that
  `exec`s `scripts/supervisor.py`. The supervisor launches uvicorn as a child, publishes a heartbeat, and on a
  sentinel trigger does **SIGTERM → wait for graceful lifespan shutdown → relaunch** (no reseed); it also
  relaunches on an unexpected crash. A restart-storm guard (max launches per window + unhealthy-exit backoff)
  covers both paths. `LORECRAFT_NO_SUPERVISOR=1` bypasses it for bare-uvicorn dev.
- [x] 72.3c — **Regression guard for the reseed footgun.** Done. `tests/integration/test_supervisor.py` spawns
  the real supervisor against a stub child + throwaway runtime DB: cold-boots via the real `reset_runtime_db`
  (seed applied), mutates the runtime DB, triggers a real sentinel restart, and asserts the mutation **survives**
  the relaunch (no reseed); a subsequent genuine cold boot still reseeds. A static AST guard also asserts the
  supervisor never imports/calls the reseed.

---

## Sprint 73 — Generalized rewards + XP/leveling core

**Goal:** turn the inert `Player.level`/`xp` fields into a real progression system, split cleanly along
a **mechanism/policy (Tier 1/Tier 2) line** per the 2026-07-12 architectural correction. **Tier 1
provides the generic, data-driven *mechanism*** — detect XP-threshold crossings and apply an arbitrary
reward payload to a player's properties — and **knows nothing about *what* leveling rewards**. **Tier 2
(`features/progression/`) supplies the *policy*** — the opinionated, **admin-tunable** answer to "what
does each level grant" — and hands the Tier 1 mechanism concrete payloads. This delivers Sprint 71.5's
quest-XP ask (`issue-39d3fcb8`) as a side effect. Combat stays shelved, so this builds progression
*without* combat stat-scaling. This sprint introduces the **skill-point currency (earn side)**;
*spending* it on a skill tree is Sprint 74.

**The mechanism/policy split in one line (user's words, 2026-07-12):** *"tier1 should provide ability to
do things (level up updates an array of player properties) and be data-driven; tier2 is the malleable
opinionated bit where we tell the tier1 leveler what to reward for leveling, tunable by an admin."*

**Scope guard.** Build the reward/level/skill-point plumbing; **defer** the skill tree/abilities to
Sprint 74 and free **stat points** (STR/DEX-style point-buy allocation) to *later* — the six
`PlayerStats` attributes already exist as real fields, so "stat points later" is about an allocation
UI, not adding the stats. No stat-allocation work here.

**Verified starting state (2026-07-12).** `PlayerStats` (`engine/models/player.py` L36–53) carries
`level=1`, `xp=0`, `xp_to_next=100`, the six stat fields, and a `skills` JSON blob — but **no
`skill_points` field**. XP accrues in exactly **one** place — `features/exploration/service.py` L62–64
does `stats.xp += DISCOVERY_XP` (=5) — and **no level-up logic exists**. Quest `_award_rewards`
(`features/quests/service.py` L195–203) handles `rewards["items"]` but its `rewards["xp"]` branch only
narrates cosmetically (never mutates `stats.xp`), and there is **no `coins`/`skill_points` branch**.
World content authors **605 XP** across 12 quest stage rewards, currently discarded. **Coin-grant reuse
path (confirmed):** `LedgerService.credit(session, "player", player_id, amount)`
(`engine/services/ledger.py` L59–66) is the documented money-creation API ("world import, admin,
**loot** … the ONLY way coins enter play"); `ctx.ledger` is on `GameContext`. **Admin-tunable
precedent (confirmed):** the DB-backed `WorldClock` singleton (`engine/models/world.py` L119) is
**live-editable** by admins via `POST /admin/clock/time-ratio` (`webui/admin/routers/clock.py` L74–89) —
commit to DB + push to the running engine, **no restart**. The YAML-seeded alternative is
`economy.regions` → `RegionPricing` rows via `import_world._import_economy`, changeable only by
YAML edit + reseed (or Sprint 72.2's `POST /admin/world/reseed`). See the admin-tunable finding below.

| # | Task | Status |
|---|------|--------|
| 73.1 | **Tier 1 generic leveling *mechanism* (data-driven, policy-free).** New `src/lorecraft/engine/game/leveling.py`, pure like `engine/game/checks.py::skill_check`. It provides "the ability to do things," not opinions: (a) a **data-driven curve value object** `LevelCurve` — holds the threshold data (`base`, `step`, or an explicit `thresholds` list), **passed in as data**, not hardcoded module constants; `xp_for_level(curve, level) -> int`. (b) `award_xp(stats: PlayerStats, amount: int, curve: LevelCurve) -> LevelUpResult(leveled_up, old_level, new_level, levels_gained)` — adds XP, rolls `level` across **one or more** thresholds per the passed curve, updates `xp_to_next`, and returns how many levels crossed. It grants **nothing** beyond xp/level and **does not know** coins/skill-points exist — the caller decides per-level rewards. (c) a generic property applier `apply_stat_deltas(stats, deltas: Mapping[str, int])` — the "update an array of player properties" mechanism: validate each key is a known numeric `PlayerStats` field (whitelist: `xp`, `skill_points`, future stat points) and apply the int delta; reject unknown keys. **Pure: no session/IO/`ctx`, no coins (ledger) / items.** Unit tests: single/multi-level rollover, exact-threshold boundary, zero/negative guard, unknown-property rejection, curve driven by passed data. | [x] Shipped as commit `aa20e38` on branch `sprint-73-progression`. |
| 73.2 | **`PlayerStats.skill_points` field (the earn-side currency).** Add `skill_points: int = 0` to `PlayerStats`. Earned this sprint (quests + level-ups), **spent** in Sprint 74's tree — banks until then. Include in the `stats_snapshot` save/load path and admin reseed. Success: fresh player has `skill_points=0`; round-trips through save/load. | [x] Shipped as commit `70ed9f4` on branch `sprint-73-progression`. A hand-written sqlite-compat column shim for the new field followed as commit `99d3ef9` — **since superseded** by Sprint 75's generic reflection-based scanner (75.1/75.2 deleted this shim along with the other 13 hand-written ones; see [Sprint 75](#sprint-75--sqlite-additive-column-auto-migration--sprint-712-pk-rename-data-migration) below). |
| 73.3 | **Tier 2 progression *config* (data-driven **and** admin-tunable).** New `features/progression/` package: a DB-backed `ProgressionConfig` **singleton row** (mirroring the `WorldClock` pattern) holding **both** the curve params (`base`, `step`) **and** the per-level reward *policy* (`coins_per_level`, `skill_points_per_level`). **Seeded from a `progression:` section in `world.yaml`** at import (mirror `_import_economy`, and add it to `export_world_document` so live edits round-trip back to YAML) — data-driven defaults, authorable. Tier 2 reads this row and constructs the Tier 1 `LevelCurve` from its params. This is the "malleable opinionated bit." Success: config seeds from YAML; changing `coins_per_level` there + reseed changes level-up payouts with no code edit. | [x] Shipped as commit `eeb6226` on branch `sprint-73-progression`. Import-time bounds validation (`base > 0`, rest `>= 0`) added separately in commit `565b77b`. |
| 73.4 | **Admin-tunable endpoint (live, no restart) — the "tunable by an admin" ask.** `GET`/`POST /admin/progression/config` mirroring `POST /admin/clock/time-ratio` (`webui/admin/routers/clock.py`): read + edit the 73.3 `ProgressionConfig` row live, commit, and (if any value is cached in the runtime) push it — no reseed, no restart. Admin `index.html` form hook + an e2e/integration test. **Confirmed in-sprint (user, 2026-07-12)** — not a stretch goal. | [x] Backend shipped as commit `64db1d4`, admin console form shipped as commit `8857515`, both on branch `sprint-73-progression`. |
| 73.5 | **Tier 2 reward *interpreter* (policy → Tier 1 mechanism dispatch).** In `features/progression/`, `apply_rewards(ctx, rewards: JsonObject) -> RewardOutcome` interprets the reward **vocabulary** (`items`/`xp`/`coins`/`skill_points`) and dispatches each to a Tier 1 mechanism: `items` → `ctx.item_location.spawn`; `coins` → `ctx.ledger.credit`; `xp` → `leveling.award_xp` with the curve built from 73.3 config; `skill_points` (and future numeric props) → `leveling.apply_stat_deltas`. **The vocabulary lives here (Tier 2), not in Tier 1** — "which keys count as rewards" is a policy/content choice (see design note). Canonical key **`coins`** (matches `CoinBalance`; `money` tolerated as alias). Returns `RewardOutcome` (amounts granted + any `LevelUpResult`) so callers narrate without re-deriving. Unit tests per key + a combined bundle. | [x] Shipped as commit `9fabd64` on branch `sprint-73-progression` (bundled with 73.7's level-up payout). A malformed non-list `items` reward value now warns instead of silently no-op'ing (commit `236c05d`). |
| 73.6 | **Rewire quest rewards onto the interpreter (delivers Sprint 71.5 / `issue-39d3fcb8`).** Replace `features/quests/service.py::_award_rewards` (L195–203) with a single `apply_rewards(ctx, rewards)` call, then narrate (73.9). Quests just *supply the payload* (the authored reward dict); it owns no reward mechanism. Because `_complete_quest` calls `_award_rewards` **per stage**, multi-stage quests award incrementally for free. Success: `world.yaml`'s 605 quest XP goes live; `rewards.coins`/`rewards.skill_points` now function. Closes Sprint 71.5. | [x] Shipped as commit `5bf8fa5` on branch `sprint-73-progression`. Closes Sprint 71.5 / `issue-39d3fcb8` — see the 71.5 row above. |
| 73.7 | **Level-up rewards = pure Tier 2 policy read (no hardcoded amounts).** When 73.1's `award_xp` reports `levels_gained > 0`, `features/progression/` reads the 73.3 config's `coins_per_level`/`skill_points_per_level`, builds `{"coins": coins_per_level·levels_gained, "skill_points": skill_points_per_level·levels_gained}`, and applies it via the 73.5 interpreter. **No magic constants in code** — the numbers come from the admin-tunable config. Success: crossing a threshold credits coins + skill points at the *configured* rate; changing the rate via 73.4 changes payouts live. | [x] Shipped as commit `9fabd64` on branch `sprint-73-progression` (bundled with 73.5's reward interpreter — the level-up payout is the interpreter recursively applying its own `{coins, skill_points}` payload). |
| 73.8 | **Route discovery XP through the mechanism.** `features/exploration/service.py` L62–64's inline `stats.xp += DISCOVERY_XP` bypasses level-up. Replace with `apply_rewards(ctx, {"xp": DISCOVERY_XP})` (or `award_xp` with the config curve) so a threshold-crossing discovery also triggers 73.7's payout. No duplicated threshold math. | [x] Shipped as commit `2dd499b` on branch `sprint-73-progression`. |
| 73.9 | **Level-up feedback (feed message + event + live stats).** On `leveled_up`, the Tier 2 caller emits a feed line (add `MessageType.LEVEL` + `.msg-level` CSS, mirroring Sprint 71.4's `MessageType.HELP`, or reuse `SYSTEM`), `ctx.push_update`s the Stats pane (extend `partials/stats_panel.html` / `webui/player/session.py` to show `skill_points`), and queues a new `GameEvent.PLAYER_LEVELED_UP` (mirror `SKILL_IMPROVED`). Presentation stays in Tier 2 so Tier 1's `leveling.py` stays IO-free. | [x] Backend feedback plumbing shipped as commit `d038f01`; frontend Stats-pane live-render + level-up re-render shipped as commit `ea48c25`; distinct `.msg-level` feed styling shipped as commit `172ca71` — all on branch `sprint-73-progression`. |
| 73.10 | **Docs.** `docs/user_guide.md` (how XP is earned; levels pay coins + skill points). `docs/admin_builder_guide.md` (quest `rewards` supports `xp`/`coins`/`items`/`skill_points`; the `world.yaml` `progression:` section; **how to live-tune per-level rewards + the curve from the admin console** [73.4]). No `scripting_api.md` regen (no new `register_spec`). | [x] Shipped as commit `e094f2e` (this worktree, docs-only). `docs/user_guide.md` gained an "Experience & Leveling" section + `score` command entry; `docs/admin_builder_guide.md` gained a "Quest rewards and the progression system" subsection (reward vocabulary, `progression:` YAML, live-tuning via the new Progression admin tab) plus a Panel Tour row; `docs/dialogue_npcs_quests.md`'s stale `rewards` examples (an unsupported `reputation` key, dead since Sprint 73.6 made the interpreter strict) corrected to the real vocabulary. |
| — | **Critical fix found in review (not a numbered task): new characters never got a `PlayerStats` row.** Discovered by the Frontend Specialist while building 73.4/73.9's UI: **no code path created `PlayerStats` for a new player** — not character creation, not save/load — across all four creation call sites (`webui/player/auth.py`, `rendering.py`, `frontend.py`, `world/bootstrap.py`). Every reward/XP grant to a genuinely new character silently no-op'd (`apply_rewards` reads `ctx.player_repo.stats(player_id)` and treats `None` as "can't hold XP," per its own docstring) — this would have shipped broken for any player who didn't happen to inherit a pre-seeded stats row. Fixed by making `PlayerRepo.stats()` get-or-create instead of get-or-`None`. | [x] Shipped as commit `c3b818a` on branch `sprint-73-progression`. The non-blocking follow-ups (stale defensive fallbacks, the first-access race investigation, and the obsolete e2e seed workaround) were later closed in the Sprint 73 cleanup backlog. |

### Sprint 73 design — the mechanism/policy (Tier 1/Tier 2) split, admin-tunability & naming

> **Provenance.** Research + design 2026-07-12 (branch `sprint-73-leveling-design`, based on
> `2b3253b`/v0.92.1), **revised for the 2026-07-12 mechanism/policy architectural correction**.
> Design-only at the time of writing. Facts verified against the live tree. Forks surfaced with a
> recommendation, not silently decided. **Since implemented in full** — see the Sprint 73 task
> table above for shipped commits; the "not yet built" / `[ ]` language throughout this design
> section reflects the state *at design time* and is kept as historical record, not current status.

**The Tier 1/Tier 2 boundary (resolved per the correction) — concrete signatures.** The old draft
conflated mechanism and policy (it hardcoded "level-up pays coins + skill points" and a `BASE=100/STEP=50`
curve as Python constants inside the leveling module). Corrected split:

- **Tier 1 = generic mechanism, data-driven, opinion-free** (`engine/game/leveling.py`):
  - `LevelCurve` — a value object holding the threshold **data** (`base`/`step` or explicit `thresholds`),
    *constructed by the caller from config*, never a hardcoded module constant. `xp_for_level(curve, level)`.
  - `award_xp(stats, amount, curve) -> LevelUpResult` — rolls levels across the passed curve; returns
    `levels_gained`. Grants nothing else; has no concept of coins or skill points.
  - `apply_stat_deltas(stats, deltas: Mapping[str, int])` — the "update an array of player properties"
    primitive; whitelisted numeric `PlayerStats` fields only.
  - Coins and items are applied through the **existing Tier 1 services** (`LedgerService.credit`,
    `ItemLocationService.spawn`) — already generic mechanisms.
- **Tier 2 = opinionated policy, admin-tunable** (`features/progression/`):
  - `ProgressionConfig` (DB singleton, YAML-seeded, admin-editable) — the curve params **and**
    per-level reward policy.
  - `apply_rewards(ctx, rewards)` — the reward-**vocabulary interpreter**; owns "which keys are rewards"
    and dispatches to the Tier 1 mechanisms. **Deliberately Tier 2:** the reward vocabulary is a
    policy/content concern (adding a future reward type is a policy change, and world.yaml authors write
    these keys), so it does not belong in Tier 1's opinion-free mechanism layer. Tier 1 stays the pure
    "doer"; Tier 2 decides *what* and *how much*.

This is precisely the user's model: Tier 1 "provides the ability to do things"; Tier 2 is "where we tell
the tier1 leveler what to reward." Follows the existing precedent that a Tier 2 feature mutates Tier 1
`PlayerStats` directly. **No new tier boundary, no engine→feature import** — the
`tests/unit/test_tier_boundaries.py` guard holds.

**FINDING + DESIGN DECISION RESOLVED (planning only — nothing here is built yet; 73.3/73.4 are both
still `[ ]` not started).** What "admin-tunable" should mean for the *new* `ProgressionConfig`, and how
far to build it in Sprint 73. The correction asked whether a *live* admin-editable balance value
exists **anywhere in the codebase already** — not for progression (nothing exists there yet, that's
this sprint's job) but as prior art to model the new config on. It does — **two** existing precedents:

1. **Live, DB-backed, no-restart (the `WorldClock` pattern).** `WorldClock` is a DB singleton whose
   fields (`time_ratio`, `weather`, `paused`) are edited live via admin `POST` endpoints
   (`clock.py`): mutate the row → `session.commit()` → push to the runtime (`state.clock_runner.time_ratio = …`).
   This is genuine live admin tuning; nothing reseeds or restarts.
2. **YAML-seeded, reseed-to-change (the `economy.regions` pattern).** Config lives in `world.yaml`,
   imported to DB rows (`RegionPricing`) at world-import; changing it needs a YAML edit + reseed
   (or `POST /admin/world/reseed`). Data-driven, **not** live.

→ **Recommendation:** model `ProgressionConfig` on **pattern 1** — a DB singleton **seeded from
`world.yaml`** (so it is data-driven *and* authorable, gaining pattern 2's round-trip via
`export_world_document`) **and** exposed through a live admin endpoint (73.4), so an admin can retune
per-level coins/skill-points and the curve **without a restart**, exactly as they already retune the
clock. This invents no new structural pattern — it composes the two that exist.
**Phasing sub-decision — SCOPE RESOLVED (user, 2026-07-12): keep 73.4 in the sprint plan.** This
resolves *whether to build it*, not building it — 73.4 (the live admin endpoint) is still `[ ]` not
started, same as every other task in this sprint; nothing has been implemented yet. The minimum
fallback, had the user cut it for scope, would have been "config in `world.yaml`, tuned via reseed"
(pattern 2 only, still data-driven, just not live) — but they confirmed it stays as a first-class task,
not a stretch goal. No fallback needed; implementation starts fresh from this plan.

**OPEN ITEM — package placement.** `features/progression/` (own manifest, auto-discovered) vs. folding
into `features/quests/` vs. a `services/` helper. → **Recommend `features/progression/`** — the only
option avoiding a spurious quests→everything coupling; it also owns the Tier 2 config and pre-stages
Sprint 74. (Unchanged by the correction; if anything the correction *reinforces* it, since the
config/policy layer needs a clear Tier 2 home distinct from Tier 1 `engine/game/leveling.py`.)

**OPEN ITEM — reward-key naming (`coins` vs `money`).** Engine vocabulary is **coins** (`CoinBalance`,
`LedgerService`). → **Recommend** canonical `coins`; optionally accept `money` as an author alias.

**OPEN ITEM — level-up beyond rewards.** The scope already answers this: level-up grants configured
coins + skill points, so a level isn't a bare number. A residual mechanical perk (e.g. per-level
`carry_capacity` modifier) is **largely redundant** with Sprint 74 (a carry node can just *be* a passive
tree node). → **Recommend rewards-only**; let Sprint 74's tree be where levels are mechanically felt;
reject content-gating-by-level as a scope explosion.

**Follow-on XP sources (out of scope — flagged, not built).** First-time zone discovery, puzzle solves,
escort completion are natural additional `apply_rewards` callers later. Quests + the existing discovery
source suffice for v1.

---

## Sprint 74 — Skill tree & ability unlocks

**Goal:** give the skill points earned in Sprint 73 a **sink** — a data-driven skill tree whose nodes,
bought with skill points, **unlock abilities**. This is the genuinely-new design surface flagged in the
2026-07-11 expansion ("a skill tree that enables abilities"). The central fork — what an "ability" *is*
in a combat-less, spell-less MUD — is now **RESOLVED (2026-07-12, user decision)**: build **all three
flavors**, with **active utility verbs as a first-class, non-optional part of the design**, not the
minimal B+C-only scope the research pass had recommended.

**RESOLVED — 74-OI-1: an ability is one of three things (all three ship in Sprint 74).** Grounded in the
engine's *actual* per-player extension points (grep-confirmed 2026-07-12):

- **(A) Active utility ability = a new command verb, gated by `actor_has_flag:ability.<id>`.** The
  command registry already takes `conditions=[...]` per verb (`registry.py::register`, e.g.
  `search` registers with `conditions=[REQUIRES_LIGHT, NOT_IN_COMBAT]`), and `actor_has_flag`
  (`command_conditions.py`) already gates verbs per-player off `Player.flags` and hides them from
  `help`. So an active ability is a verb that appears only once its `ability.<id>` flag is set — **no
  new condition mechanism required**, exactly per the user's "gated by actor_has_flag". With no
  combat/spellcasting, these are **utility** verbs (see 74.5/74.6 for the concrete set).
- **(B) Passive ability = a modifier source** feeding the existing `engine/game/modifiers.py` resolver
  (which `encumbrance/rules.py::resolve_carry_capacity` already composes) — an always-on bonus
  (carry capacity, +skill%, better prices) with no new verb.
- **(C) Interaction/dialogue ability = a `set_flags` unlock + `actor_has_flag` gate in world content.**
  Both are shipped vocabulary (`set_flags` `do:` effect in `features/npc/side_effects.py`;
  `actor_has_flag` registered on the dialogue surface too), so builders gate `world.yaml`
  dialogue/context branches on `ability.<id>` with zero engine work.

The through-line: **all three flavors converge on the same `ability.<id>` player flag** — a node
purchase sets it (flavor C's `set_flags` path), active verbs gate on it (A), and passive nodes
additionally register a modifier (B). This makes the `ability.<id>` flag **load-bearing and mandatory**
(it was "convenience" under the old B+C recommendation — the active-verbs decision promotes it), which
is why 74.2 keeps *both* an `unlocked_nodes` list (for UI/query) and the flag (for gating).

**Definition source (unchanged, per the data-driven principle):** the tree — nodes, costs, prereqs,
unlock effects — lives in **`world_content/skill_tree.yaml`**, loaded into a registry mirroring
`features/skills/definitions.py` + the `world.yaml` import. **No hardcoded node IDs in `src/`.** Each
node: `id`, `name`, `description`, `cost` (skill points), `prerequisites` (node ids), and an `unlock`
block that may combine `flags` (always — the `ability.<id>` flag), a `modifier` (flavor B), and an
`enables_verb` marker (flavor A, documentation only — the verb itself is code, gated on the flag).

| # | Task | Status |
|---|------|--------|
| 74.1 | **Data-driven tree definitions + loader.** `world_content/skill_tree.yaml` → a `SkillTreeRegistry` (mirror `features/skills/definitions.py::SkillRegistry` + the `world.yaml` import path). Node schema: `id`/`name`/`description`/`cost`/`prerequisites`/`unlock` (`flags`, optional `modifier`, optional `enables_verb`). Validation: no prerequisite cycles, prereqs exist, `cost >= 1`. **No hardcoded node IDs in `src/`.** Lives under `features/progression/`. Unit tests: load, cycle rejection, missing-prereq rejection. | [x] |
| 74.2 | **Node persistence (`unlocked_nodes` + `ability.<id>` flag — both now mandatory).** New `PlayerStats.unlocked_nodes: list[str]` (JSON, mirrors `traits`) for query/UI, **and** — because flavors A and C gate on `actor_has_flag` — each purchase also sets `Player.flags["ability.<id>"] = True`. The flag is now load-bearing (the active-verbs decision promoted it from convenience), so this dual-write is a design requirement, not an optimization. Save/load round-trip for both. | [x] |
| 74.3 | **`train`/`learn` command — spend skill points on a node.** Lists available nodes (prereqs met, affordable) and buys one: check `stats.skill_points >= cost` + prereqs, decrement `skill_points`, record the node in `unlocked_nodes`, set the `ability.<id>` flag, and register any passive `modifier` (74.4). Lives in `features/progression/commands.py`. Refuse with a clear reason on insufficient points / unmet prereqs / already-owned. | [x] |
| 74.4 | **Passive modifier source (flavor B).** A modifier collection source registered with `engine/game/modifiers.py` that, for each unlocked node carrying a `modifier`, contributes it to the resolver (e.g. `carry_capacity +2`, `skill.perception mult 1.1`, `price.buy mult 0.95`). Proves passive abilities with **zero new verbs**; applies retroactively and free (resolver recomputes per use — see 74-OI-4). Unit test: an unlocked node changes `resolve_carry_capacity`. | [x] |
| 74.5 | **Active-verb gating pattern + reference verb `forage` (flavor A).** Establish the pattern: a verb registers with `conditions=[..., "actor_has_flag:ability.<id>"]` so it is available (and `help`-listed) only once unlocked. Ship the reference implementation: **`forage`** — in an outdoor room (`Room.indoor == False`), roll `skill_check(survival)` (`game/checks.py`, the `survival` STANDARD_SKILL already exists) to yield a foraged consumable (the `consumables` feature already handles `eat`/`drink`), gated on `ability.forage`. Lives in the thematically-appropriate feature, not `progression` (see 74-OI-5). Unit tests: verb hidden without the flag, succeeds/fails on the skill roll with the flag. | [x] |
| 74.6 | **Two more active verbs — `sense` + `pick` (flavor A, ≥3 example verbs total).** **`sense`** (aka `perceive`): an enhanced `search` that rolls `skill_check(perception)` to reveal hidden items *and* concealed NPCs in the room, gated on `ability.keen_senses`. **`pick`**: attempt a locked exit *without* a key via `skill_check(lockpicking)` — the world already ships locked doors (Vault Hall) and a key/`unlock` flow, so this is the no-key path — gated on `ability.pick_locks`. Each in its thematic feature (exploration / movement-or-lockpicking), each with hidden-without-flag + skill-roll tests. These three (survival/perception/lockpicking) map onto three existing `STANDARD_SKILLS`, so no invented content. | [x] |
| 74.7 | **Interaction/dialogue unlock example (flavor C).** Author example `world_content` proving the pure-data path: a `skill_tree.yaml` node whose `unlock.flags` sets `ability.<id>`, plus a `world.yaml` dialogue/context branch gated on `actor_has_flag:ability.<id>` (e.g. a `persuasion`-flavored dialogue option that only appears once an ability is trained). Zero engine work — validates that builders can add interaction abilities without code. | [x] |
| 74.8 | **UI + docs.** Surface unlocked abilities + spendable skill points (extend `score`/Stats pane or a small `abilities` view listing owned nodes and available buys). `docs/user_guide.md` (earning/spending skill points; that abilities come in active-verb, passive-bonus, and interaction flavors; the starter verbs `forage`/`sense`/`pick`). `docs/admin_builder_guide.md` (authoring `skill_tree.yaml` nodes; the `unlock` block; gating content on `actor_has_flag:ability.<id>`). Regenerate `docs/scripting_api.md` via `make scripting-docs` **only if** an optional `actor_has_ability` alias is added (74-OI-5b) — otherwise no new `register_spec`. | [x] |

> **74.8 status ([x] complete):** the UI slice shipped with 74.3 as the read-only `abilities`
> query command (`features/progression/commands.py`, alongside `train`/`learn`) — a text-command
> surface, the same shape as `quests`/`journal`, rather than a dedicated Stats-pane widget; no
> webui/frontend files were touched anywhere in the Sprint 74 diff. The docs half
> (`docs/user_guide.md` + `docs/admin_builder_guide.md`) shipped separately by the Docs Writer,
> completing the task. No `register_spec` calls were touched anywhere in the Sprint 74 diff
> (verified by grep across `features/progression`/`exploration`/`movement`), so
> `make scripting-docs` was correctly skipped — 74-OI-5b (the `actor_has_ability` alias) was
> deferred as recommended, not built. A dedicated Stats-pane/webui surfacing of abilities remains
> a possible follow-up if a future sprint wants it, but is not required by this task.

**Two flagged deviations from the design above, for the historical record:**

- **`pick` grammar alias removed.** Before Sprint 74, bare `pick` was a `take` alias
  (`grammar.py`); 74.6 removed it to free the `pick` verb for lockpicking (`pick <direction>`).
  `take`/`get`/`grab` remain synonyms, and `pick up <item>` still means take via the phrasal-verb
  table — only the bare `pick <noun>` form changed meaning. Documented, reversible, and no test
  relied on the old alias.
- **`sense`/`perceive` reveals what the engine can actually conceal, not a literal "hidden
  items/concealed NPCs" system.** The engine has no per-item or per-NPC concealment field, so
  `sense` (74.6) reveals the one real concealment mechanism that exists — hidden exits
  (`Exit.hidden`, the same mechanism `search` reveals) — and additionally narrates every NPC and
  item actually present in the room as a perception-sweep readout. This satisfies the ability's
  intent (a perception check that tells you more than a blind look) without inventing new
  schema. Flagged as a candidate follow-up if true per-entity concealment (an item or NPC that is
  present but normally unlisted until "sensed") is ever wanted — it would need a new field on
  `Item`/`NPC`, not just a doc change.

**Mid-review fix (haggler skill node):** the `haggler` passive node shipped in 74.6 with an
`unlock.modifier` of `price.buy mult 0.95`, but nothing in `features/economy/service.py` resolved
`price.buy` yet — a Code Reviewer blocking finding, since the modifier was contributed to the
resolver but silently had no effect. Fixed in `a3644ea`: `EconomyService.buy_price` now resolves
`price.buy` via `resolve_for(..., base=1.0)` — the same read-through pattern
`resolve_carry_capacity` uses — and folds it into the existing barter/reputation discount
product.

### Sprint 74 open items (summary)

- **74-OI-1 — RESOLVED (2026-07-12, user):** an ability spans **all three flavors** — (A) active utility
  verbs gated by `actor_has_flag`, (B) passive modifiers, (C) interaction/dialogue `set_flags` unlocks —
  with active verbs **first-class** (74.5–74.6: `forage`/`sense`/`pick`), not the minimal B+C the research
  pass recommended. Tree is data-driven `world_content/skill_tree.yaml`.
- **74-OI-2 — node persistence (recommendation stands, now *reinforced*):** keep **both** an
  `unlocked_nodes` list **and** the `ability.<id>` flag. The active-verbs decision makes the flag
  **mandatory** (flavors A and C gate on `actor_has_flag`), not merely convenient — flagged per the
  coordinator's ask to surface where the decision changes a smaller item.
- **74-OI-5 — NEW, raised by the active-verbs decision — where do the ability *verbs* live?** The
  gating flag/tree is `features/progression/`, but the verbs (`forage`/`sense`/`pick`) are thematically
  exploration/utility. **(a)** put them in their thematic feature (forage/sense → `exploration`; pick →
  the movement/lockpicking feature) with `progression` owning only the tree/train/persistence/modifier
  source; **(b)** put all ability verbs in `progression`. → **Recommend (a)** — keeps `progression` from
  becoming a grab-bag of unrelated verbs and keeps each verb near the skill/service it uses. Sub-item
  **74-OI-5b:** whether to add an optional `actor_has_ability:<id>` condition as a readability alias over
  `actor_has_flag:ability.<id>` — **recommend deferring it** (the user specified `actor_has_flag`; the
  alias is sugar and would add a `register_spec` + `scripting_api.md` regen for no new capability).
- **74-OI-3 — tree shape/economy (recommendation stands):** shallow first tree (flat tiers, few
  prereqs); tune skill-point costs against the ~1-point-per-level earn rate from 73.5 once both exist.
  The active-verbs decision suggests seeding the tree with at least the three verb-unlock nodes
  (`forage`/`keen_senses`/`pick_locks`) plus 2–3 passive nodes.
- **74-OI-6 — NEW, from the Sprint 73 mechanism/policy correction — is `skill_tree.yaml` "admin-tunable" enough?** The tree (node costs/rewards) is YAML-seeded, matching the `economy.regions` precedent: data-driven but **not live** (a cost change needs a restart to take effect). This mirrors the Sprint 73 admin-tunable finding. → **Recommend YAML+restart for v1** — node costs/prereqs are *structural* content, not a hot balance dial like per-level coin rewards, so the restart cadence is acceptable; revisit migrating node costs onto the same live `ProgressionConfig`-style mechanism (73.4) only if admins ask to retune tree costs without a restart. Keeps Sprint 74 consistent with 73's split (Tier 1 reads data; Tier 2/config owns the opinionated, potentially-live values). **As shipped:** `skill_tree.yaml` is read directly into an in-memory `SkillTreeRegistry` at server startup (`main.py::_load_skill_tree_definitions`) — the `marks.yaml`/`hunts.yaml` pattern, not the `world.yaml`-DB-import pattern `ProgressionConfig` uses. So the accurate framing is **YAML + engine restart**, not "YAML + DB reseed" — there is no DB row to reseed at all; a plain process restart is enough to pick up an edited tree.
- **74-OI-4 — retroactive passives / respec (recommendation stands):** passives apply immediately
  (resolver recomputes per use — free); **no respec** in v1 (defer).

Package placement (`features/progression/`), reward-key (`coins`), and the Sprint 73 forks are settled
in the Sprint 73 design section above; none are changed by the active-verbs decision.

---

## Sprint 75 — SQLite additive-column auto-migration + Sprint 71.2 PK-rename data migration

**Goal (shipped — design complete 2026-07-12, built and merged on branch `sprint-75-db-migration`).**
Replace the ~14 hand-written per-column `_ensure_sqlite_compat_columns` shims in `db.py` with a
generic reflection-based additive-column auto-migration scanner covering the ~22
currently-unshimmed additive columns, and add deliberate data migrations for the two Sprint 71.2
PK-adjacent renames (`regionpricing.area_id`→`zone`, `room.area_id`→`zone`/`room_type`) that
Sprint 71.2 itself never touched `db.py` for. This is foundation-band infrastructure hardening
(data-integrity / startup-robustness) — **not a feature** — squarely inside the "foundation before
features" mandate. *(At design time this section read "design complete, not yet built" — a design
decision being finalized is not the same as it being built. That distinction has since resolved:
every task below is now `[x]`, shipped as the commits listed in its row.)*

| # | Task | Status |
|---|------|--------|
| 75.1 | **Generic reflection additive-column scanner in `db.py`.** New `_ensure_additive_columns(engine)` replacing the body of `_ensure_sqlite_compat_columns`: for each model in `GAME_TABLE_MODELS`, diff `model.__table__.columns` against live reflected columns; for each column missing from the live table, `ALTER TABLE … ADD COLUMN` with a type derived from `col.type.compile(dialect=…)` and a **`DEFAULT` derived from the actual pydantic field default** (`model.model_fields[name].default` / `.default_factory`, not a naive type-zero table — this is load-bearing, see design section); **skip + WARNING-log** any missing column that is part of the primary key (SQLite can't `ADD` a PK column via `ALTER` — this is exactly `regionpricing.zone`, handed off to 75.4); for any DB-only column absent from the model, **WARN, never drop/alter** (strictly additive contract; DB-only columns are the rename/drop signal handled deliberately in 75.3/75.4). **Tier 1 in character, composition-layer in placement** (see OPEN ITEM A below). *Success: a legacy DB missing any of the ~22 unshimmed additive columns upgrades cleanly on startup; test-matrix items 1 + 4 + 6 (75.5) green.* — tunable: N/A (schema infra, no game-balance dial). | [x] Shipped, together with 75.2, as commit `683abd7` on branch `sprint-75-db-migration`. |
| 75.2 | **Delete the 14 hand-written per-column shim blocks** (including the just-landed Sprint 73 `skill_points` shim), subsumed by 75.1 by construction (recommended: subsume, don't run-alongside — two sources of truth for the same fact is the exact "someone forgot to add a shim" bug that motivated this sprint). Retain a regression test asserting the previously-hand-shimmed columns still get added after the hand code is deleted, so the deletion can't silently regress. **Tier 1 in character, composition-layer in placement.** *Success: `db.py`'s compat body is the generic scanner only; previously-shimmed columns still added.* — tunable: N/A. | [x] Shipped, together with 75.1, as commit `683abd7` on branch `sprint-75-db-migration` — includes deleting the Sprint 73 `skill_points` shim (`99d3ef9`). |
| 75.3 | **Room `area_id`→`zone`/`room_type` in-place data migration.** Runs after 75.1 (which will already have added `room.zone`/`room.room_type` as nullable columns, orphaned from `area_id`). `_migrate_room_area_id(engine)`: if the legacy `area_id` column is still present, `UPDATE room SET zone = …` applying the §71.2 fold table **verbatim** (town/wilderness/cave→`ashmoore`; cogsworth/whisperwood/port_veridian→themselves; `old_trade_road`→`cogsworth`, `forest_road`→`whisperwood`, `river_bend`→`port_veridian`); `room_type` is mechanically derivable **only** for the three Ashmoore kinds (`UPDATE room SET room_type = area_id WHERE area_id IN ('town','wilderness','cave') AND room_type IS NULL`) — the other zones' `room_type` was per-room authoring in 71.2b, not derivable, and stays NULL, matching §71.2's stance exactly. **Warranted even though rooms are reseed-derived**, because admin can `POST`/`PUT` rooms (`webui/admin/routers/world.py`), so a legacy DB can hold admin-authored rooms not in `world.yaml` that a reseed will never fix. **Recommend DROP `area_id` after copy** (SQLite 3.45 supports `DROP COLUMN` on this non-PK, non-indexed column) — a lingering half-renamed column is the "half-done seam" AGENTS.md warns against, and leaving it means the 75.1 scanner's DB-only-column WARNING fires on every startup forever; dropping it makes the migration self-clearing and idempotent. Guard the DROP on the column's presence. **Tier 1 in character, composition-layer in placement, with the bounded content-literal caveat (OPEN ITEM A).** *Success: test-matrix item 2 (75.5) green; migration idempotent.* — tunable: N/A. | [x] Shipped as commit `399aaae` on branch `sprint-75-db-migration`. |
| 75.4 | **RegionPricing `area_id`→`zone` PK table-rebuild migration.** `zone` is the PRIMARY KEY, so neither `ADD COLUMN … PRIMARY KEY` nor `DROP COLUMN area_id` is possible in SQLite — requires the classic rebuild, guarded on "does the live `regionpricing` table still have an `area_id` column": (1) `CREATE TABLE regionpricing_new (zone VARCHAR PRIMARY KEY, region_mult FLOAT NOT NULL DEFAULT 1.0, bias JSON NOT NULL DEFAULT '{}')`; (2) `INSERT … SELECT <fold(area_id)>, region_mult, bias FROM regionpricing GROUP BY <fold(area_id)>` — the `GROUP BY` on the folded value is **mandatory** (the fold collapses Ashmoore's three source rows into one `ashmoore` PK and would otherwise raise a PK collision); (3) `DROP TABLE regionpricing; ALTER TABLE regionpricing_new RENAME TO regionpricing`. Resolves **OPEN ITEM B** (force `ashmoore`'s `region_mult` to `1.0` explicitly in the fold, rather than relying on `GROUP BY`'s arbitrary row-pick which could otherwise grab the wilderness/cave multiplier) and **OPEN ITEM C** (rebuild-with-fold vs. drop-and-recreate-empty — recommend rebuild-with-fold; see design section for the full fork). **Tier 1 in character, composition-layer in placement.** *Success: test-matrix item 3 (75.5) green; OPEN ITEMs B and C resolved per the stated recommendations.* — tunable: N/A. | [x] Shipped as commit `f623889` on branch `sprint-75-db-migration`. A missed-cleanup crash-loop guard (drop a stray `regionpricing_new` before rebuilding) followed in commit `8183be3`; a non-deterministic tie-break in the non-Ashmoore fold was made deterministic in commit `8b1795b`. |
| 75.5 | **`tests/unit/test_db_migrations.py` — full test matrix.** Against a temp-file SQLite engine (not `:memory:`, so `ALTER`/rebuild round-trips through real reflection): (1) parametrized additive-column upgrade with an explicit hardcoded-default subset (`item.quality → 'common'`, `room.terrain → 'normal'`, JSON `'[]'`/`'{}'` factories, a nullable `NULL` case) to catch the type-zero-vs-field-default bug that pure reflection parity would tautologically hide; (2) Room data round-trip parametrized over the full §71.2 fold table + `area_id` dropped afterward; (3) RegionPricing rebuild round-trip (six legacy rows → four zone-keyed rows, Ashmoore collapsed to `1.0`, `zone` reported as PK by reflection); (4) warn-but-don't-drop for a DB-only column (`caplog`); (5) idempotency (second run issues no `ALTER`/rebuild); (6) non-SQLite dialect early-return guard (preserve existing behavior). **Test.** *Success: `make test` green; the previously-untested `_ensure_*` path is now covered.* — tunable: N/A. | [x] Shipped as commit `5900096` on branch `sprint-75-db-migration`. |

### Sprint 75 design — additive-column scanner, PK-rename migrations & tier placement

> **Provenance.** Research + design 2026-07-12, verified against the `sprint-73-progression` worktree
> tip (`2dd499b`) in its own venv (SQLAlchemy `2.0.51`, SQLite `3.45.1`). Design-only — nothing in
> this section is built. Open items are surfaced with a recommendation, not silently decided.

**Precedent.** `src/lorecraft/db.py`'s `_ensure_sqlite_compat_columns` is the existing hand-maintained
pattern — 14 per-column `if "x" not in cols: ALTER TABLE … ADD COLUMN` blocks. Most recent hand
example: the Sprint 73 `skill_points` shim (commit `99d3ef9`). Sprint 71.2 (`docs/roadmap.md` §71.2)
is the canonical `area_id`→`zone` fold table and the Ashmoore economy-collapse rule — but **the
71.2 commits (`2e9f466`/`7e90bf4`) did not touch `db.py` at all**; 71.2 relied entirely on
reseed-from-`world.yaml`, shipping **zero** compat/migration handling for that rename. So the (b)
migrations below are net-new; there is no partial handling to build on or dedup against.

**Fit to roadmap.** Sprint 75 was confirmed free (70–74 all claimed). This is pure foundation-band
infrastructure hardening (data-integrity / startup-robustness), squarely inside the "foundation
before features" mandate — not a feature jump-ahead.

**Environment facts (verified in the sprint-73-progression tree's venv).** SQLAlchemy `2.0.51`,
SQLite `3.45.1`. SQLite 3.45 **supports `ALTER TABLE … DROP COLUMN`** (added in 3.35.0) for plain
non-PK, non-indexed columns — relevant to the `area_id` disposition in 75.3. It still **cannot**
`ADD` a PRIMARY KEY column via `ALTER`, nor `DROP` a PK column — relevant to `regionpricing` (75.4).

**Risks.**
- **Tier-placement framing needed correction** — see OPEN ITEM A below. `db.py` is **not** `engine/`;
  it lives at `src/lorecraft/db.py` and **already imports `lorecraft.features.*`** (bank, economy,
  npc, quests, trading, reputation, transit, npc_memory in `GAME_TABLE_MODELS`). It is a
  **composition-layer** module, not Tier 1 engine infra, so `tests/unit/test_tier_boundaries.py`
  does not gate it the way it gates `engine/`.
- **Content values leaking into infra.** The two fold-maps encode world-content-specific literals
  (`ashmoore`, `cogsworth`, `old_trade_road`, …) inside `db.py`. As a one-shot historical migration
  constant this is defensible, but it is **not** "no feature-specific opinion" — flagged, not
  silently accepted (see OPEN ITEM A).
- **`regionpricing.zone` is a PRIMARY KEY** — the generic scanner cannot and must not touch it; it
  requires a full table-rebuild migration (75.4), the single hardest piece of this sprint.
- **Coverage gap.** There is essentially no test coverage for `_ensure_sqlite_compat_columns` today
  (it grew 14 blocks with no dedicated legacy-DB upgrade test). This sprint closes that gap as a
  first-class deliverable (75.5), not an afterthought.

**(a) The reflection-based additive-column scanner (75.1–75.2).** Mechanism
(`_ensure_additive_columns(engine)`): early-return on non-SQLite; for each model in
`GAME_TABLE_MODELS`, skip tables not yet reflected (brand-new DBs already got the full schema);
diff `model.__table__.columns` (authoritative names + type + nullable + PK membership) against
live reflected columns. **`model − live` → ADD**, skipping and WARNING-logging any PK-member column
(the clean seam handed to 75.4). **Default derivation is load-bearing — derive from the actual
pydantic field default, not a type-zero table.** Read `model.model_fields[name]`: if `field.default`
is set, use it; elif `field.default_factory` is not `None`, call it and `json.dumps` (correctly
distinguishing `'[]'` list factories from `'{}'` dict factories rather than guessing by name); else,
for a `NOT NULL` column with no declared default, fall back to type-zero. Why it matters:
`quality: str = "common"` and `terrain: str = "normal"` must emit `DEFAULT 'common'`/`DEFAULT
'normal'`, not `''` — a naive str→`''` table would silently corrupt these two on every legacy
upgrade. **`live − model` → WARN, never drop/alter** — the strictly-additive contract; a DB-only
column is the rename/drop signal (exactly `room.area_id` and legacy `regionpricing.area_id`), out
of scope for the generic scanner and handled deliberately in 75.3/75.4.

**Decision — subsume, don't run-alongside (recommended, 75.2).** Delete all 14 hand-written blocks
and let the generic scanner cover them by construction: every current hand entry is a plain
additive column the scanner expresses exactly, and keeping both is two sources of truth for the same
fact — the exact recurring "someone forgot to add a shim" bug that spawned this sprint. Retain a
regression test asserting the previously-hand-shimmed columns still get added after deletion. The
one thing the scanner must **not** subsume is `regionpricing.zone` (PK) — it never appeared in the
hand code and belongs to 75.4.

**(b) The two PK-rename data migrations (75.3–75.4).** These run **after** `_ensure_additive_columns`
(which will already have added `room.zone`/`room.room_type` as nullable columns, leaving them NULL
and `area_id` orphaned — the gap these deliberate steps close).

*Room (`area_id` → `zone` + `room_type`, 75.3) — in-place, no rebuild needed.* `area_id` is nullable,
non-PK, non-indexed; `zone`/`room_type` are nullable non-PK. `_migrate_room_area_id(engine)` folds
`area_id` into `zone` verbatim per §71.2, derives `room_type` only for the three Ashmoore kinds
(the other zones' `room_type` was per-room authoring, not derivable), and drops `area_id` after copy
once SQLite 3.45's `DROP COLUMN` support is confirmed available. Warranted despite rooms being
reseed-derived because admin `POST`/`PUT` on rooms (`webui/admin/routers/world.py`) can produce
admin-authored rows not in `world.yaml` that a reseed will never fix.

*RegionPricing (`area_id` PK → `zone` PK, 75.4) — full table rebuild.* `zone` is the PK, so neither
`ADD COLUMN … PRIMARY KEY` nor `DROP COLUMN area_id` is possible; use the classic SQLite rebuild
(new table → folded+grouped `INSERT` → drop old → rename new), guarded on the live table still
having an `area_id` column. The `GROUP BY` on the folded value is mandatory to avoid a PK collision
from Ashmoore's three source rows collapsing to one `ashmoore` row.

**OPEN ITEM A — tier-placement correction.** The originating request framed this work as "belongs
in `db.py`, which is Tier 1 engine infra." **That framing is inaccurate and should not be committed
as written.** `db.py` lives at `src/lorecraft/db.py` (top-level), not under `engine/`, and it
**already imports `lorecraft.features.*`** across `GAME_TABLE_MODELS` — making it a
**composition-layer** module (allowed to import both engine and features), not a Tier 1 engine
module; `tests/unit/test_tier_boundaries.py` does not apply to it the way it applies to `engine/`.
→ **Recommendation:** state it accurately — **the scanner mechanism is Tier-1 *in character***
(opinion-free reflection; knows *how* to diff+ALTER, encodes no feature's opinion about *what* a
column means) and introduces no new feature import, so it adds zero coupling. **The two fold-maps
are the caveat** — they embed world-content literals directly in `db.py`, which is not "no
feature-specific opinion." Accept this as a **bounded, one-shot historical migration constant**
(it transforms *past* data to a *known* target state; it is not runtime branching on room IDs,
which the design principles forbid), but document it as a **deliberate, self-clearing exception**,
not as clean Tier 1 — once `area_id` is dropped (room, 75.3) and the table rebuilt
(regionpricing, 75.4), both fold-maps become dead code removable in a later cleanup.

**OPEN ITEM B — the Ashmoore-collapse `region_mult` value.** The rebuild's `GROUP BY` picks *one*
row's `region_mult` for the collapsed `ashmoore` row. §71.2 rubber-stamped `ashmoore = 1.0` (the
`town` row's value, and the only Ashmoore room with a shop). → **Recommend forcing `ashmoore` to
`1.0` explicitly** in the fold rather than relying on `GROUP BY`'s arbitrary row-pick (which could
grab the 1.15 `wilderness` or 1.25 `cave` mult). Today all three Ashmoore rows would fold identically
in player-facing terms because no shop sits in a wilderness/cave room, but forcing `1.0` matches
§71.2's documented decision and is collision-proof regardless of row order.

**OPEN ITEM C — rebuild-with-fold vs. drop-and-recreate-empty for `regionpricing`.** Unlike `room`,
`regionpricing` has **no admin-authoring path** (verified: `region_for_zone` is a pure `session.get`;
pricing is YAML-seeded from `economy.regions`, reseed-only). So its rows are always reproducible by
a reseed, and a simpler migration would be: drop the old-schema table and let `_create_model_tables`
recreate it empty with the `zone` PK, deferring repopulation to the next economy reseed. →
**Recommend rebuild-with-fold (the 75.4 steps) anyway**, because the startup `SELECT zone` crash
happens *before* any reseed is guaranteed to run, and rebuild-with-fold is the only option that
keeps economy prices correct on a legacy DB upgraded **in place without a reseed** — the entire
justification for building real data migration rather than "just ADD COLUMN and orphan the data."
Drop-empty would leave every zone at the model default `1.0` until someone remembers to reseed.

**(d) Test matrix.** See task 75.5 above for the full six-item matrix (parametrized additive-column
upgrade with hardcoded-default assertions, Room fold round-trip, RegionPricing rebuild round-trip,
warn-but-don't-drop, idempotency, non-SQLite guard).

**Sequencing note (for the eventual Backend Engineer).** Build this on a branch based off
`sprint-73-progression`'s current tip (`2dd499b`), not off `main`. Both Sprint 73 and Sprint 75 edit
`_ensure_sqlite_compat_columns` in `db.py`; basing off the sprint-73 tip means Sprint 75's "delete
the hand shims" change sits cleanly on top of Sprint 73's `skill_points` shim commit (`99d3ef9`)
instead of conflicting with it during a later rebase/merge. Sprint 75 is scope-separate from
Sprint 73 (progression) — do not fold it into the Sprint 73 branch's own work.

**Tunability note.** None of Sprint 75's tasks are game-balance dials — this is schema/migration
infrastructure, with no reward amount, price, or curve to tune. Every task's tunable classification
is "N/A — schema infra"; there is no live-tunable knob to invent here.

**Files referenced (design analysis, sprint-73-progression worktree — implementation base once
picked up; do not confuse with this session's own worktree):**
- `src/lorecraft/db.py` (scanner target; current hand-shim body)
- `src/lorecraft/engine/models/world.py` (Room/Item/NPC additive fields)
- `src/lorecraft/engine/models/player.py` (Player/PlayerStats/SaveSlot additive fields)
- `src/lorecraft/features/economy/models.py` (`RegionPricing`, `zone` PK)
- `src/lorecraft/features/economy/repo.py` (`region_for_zone` — no admin-authoring path)
- `src/lorecraft/webui/admin/routers/world.py` (admin room POST/PUT — why 75.3 is warranted)
- `docs/roadmap.md` §71.2 (fold table + Ashmoore collapse) and §73 design (format model for this
  section)

---

## Sprint 76 — Economy live-tuning admin UI

**Goal:** close the `economy.regions` live-tunability gap flagged in the active backlog and
in `AGENTS.md`'s "Prefer live-tunable configuration where sensible" section. `RegionPricing`
(`src/lorecraft/features/economy/models.py`) is **already** a DB-backed table — `zone` (PK) →
`region_mult` + a per-item `bias` JSON map — YAML-seeded from `world_content/world.yaml`'s
`economy.regions:` list at import time, and already read **live** from the DB on every
transaction (`features/economy/service.py`). **This is not a schema/model change** — `RegionPricing`
already exists exactly as needed; what's missing is the admin layer to retune it without a reseed,
mirroring the `WorldClock` (`webui/admin/routers/clock.py`) and Sprint 73.4 `ProgressionConfig`
precedents. Because there is no schema change, **the Database Specialist gate stage is skipped**
for this sprint's implementation gate.

**Tier boundary:** this is pure **Tier 2 + composition-layer** work — a new read method on
`features/economy/repo.py` (Tier 2 feature repo) plus a new router/UI under `webui/admin/`
(composition layer, may import both engine and features). **No `engine/` changes.**

| # | Task | Status |
|---|------|--------|
| 76.1 | **`EconomyRepo.all_regions()`.** New read method on `src/lorecraft/features/economy/repo.py` returning every `RegionPricing` row (today there is only `region_for_zone(zone)`, a single-row lookup — the admin list view needs all rows). Mechanism-only, Tier 2 feature-repo addition, no schema change. | [x] Shipped as commit `8a3db06` on branch `sprint-76-economy-live-tuning`. |
| 76.2 | **Admin router `webui/admin/routers/economy.py`.** GET (list all regions, `Observer`-gated) and POST (edit one region's `region_mult`/`bias`, `Superadmin`-gated) endpoints, mirroring `webui/admin/routers/progression.py`'s exact pattern (Sprint 73.4: read the row(s) fresh from the DB each call, mutate + commit in the POST handler — no runtime cache to push to, since nothing caches `RegionPricing` in memory). Register in `webui/admin/api.py` (import + `admin_router.include_router(economy_router)` alongside the other routers there). | [x] Shipped, together with 76.1, as commit `8a3db06`. |
| 76.3 | **"Economy" admin tab in `webui/admin/index.html`.** Mirror the existing "Progression" tab's structure (the `tab-progression` panel and its `loadProgressionConfig`/`saveProgressionConfig`/`updateProgressionEditUI` JS, ~line 1350–1420) but for a *list* of regions (one row per zone) rather than a single config object — each row shows zone, `region_mult` (editable number input), `bias` (editable, likely a simple JSON textarea given it's a sparse `item_id`→mult map), and a per-row Save button. Superadmin-gated editing exactly like Progression's tab (disabled inputs + tooltip for lesser roles, `state.role === "superadmin"`). | [x] Shipped as commit `6c5bf93`; a follow-up fix for a save-status/reload race plus zone-encoding and inline-`onclick` XSS hardening landed as commit `57c1ba3`. |
| 76.4 | **Backend unit tests.** Coverage for `EconomyRepo.all_regions()` and the new admin router's GET/POST endpoints (auth-gating, validation, persistence round-trip) — written inline by Backend Engineer as part of 76.1/76.2, not a separate Pytest Writer task. | [x] Landed with 76.1/76.2 in commit `8a3db06` (`tests/unit/test_economy_repo_regions.py`, `tests/integration/test_admin_api.py`); a bias type-confusion rejection case was pinned separately in commit `18a7a94`. |
| 76.5 | **Frontend e2e tests.** Coverage for the new Economy admin tab, written inline by Frontend Specialist as part of 76.3, following the existing e2e admin-tab test pattern (e.g. `tests/e2e/test_admin_issues.py`, or the Progression tab's e2e test if one exists — check `tests/e2e/` for a progression admin test to mirror). | [x] Landed with 76.3 in commit `6c5bf93` (`tests/e2e/test_admin_economy.py`: seeded rows render, an edit persists across reload, save controls are role-gated, invalid bias JSON is rejected without firing a request); hardened alongside the 76.3 fix in commit `57c1ba3`. |
| 76.6 | **Full Test & QA pass** (lint + typecheck + test, e2e for the new admin UI) before merge. | [x] Gate-clean: lint, typecheck, 1459 unit tests, 54 e2e tests, tier boundaries all pass; coverage 90.91%; Code Reviewer found no blocking issues (3 advisories, all since closed). |
| 76.7 | **Docs.** This roadmap section, plus an update to `docs/admin_builder_guide.md` documenting the new Economy admin tab/endpoints, in the same style as that guide's existing Clock/Progression admin-control sections. | [x] Docs — this commit. `docs/admin_builder_guide.md` gained a "Region pricing (Sprint 76)" subsection plus an Admin Web Panel Tour row and a `trade_economy.md` Related Docs entry; `docs/world_building.md` and `docs/trade_economy.md`'s stale `economy.regions` YAML examples (`area_id`, dead since the Sprint 71.2/75 `zone` rename) corrected in passing. |

---

## Sprint 77 — Discipline/Ability system: Tier 1 mechanism (Phases A–B.1)

**Used (all complete, merged as v0.97.0).** Implemented on branch
`sprint-77-abilities-tier1` — 7 implementation commits (`9eedd5d` 77.1 `AbilityDef`, `a21ca79`
77.2 `check_acquisition`, `23103d9` 77.3 `check_usage`, `21db8b3` 77.4 `resolve_proficiency`,
`39d59b0` 77.5 cooldown/resource primitives, `6f4cfb5` 77.6 unit tests, `da19c72` 77.7
`features/disciplines/` package skeleton), plus the earlier design-finalization commit
(`1188f99`) already on the branch. **No schema/DB changes this sprint** — pure new Tier 1 module
plus a manifest-only Tier 2 package stub; `PlayerStats` migration is Sprint 78's job (78.3).
Full design in [`discipline_ability_system.md`](discipline_ability_system.md)
(added 2026-07-13, user-driven; Research/Planning audit pass completed 2026-07-13 with four
cautions, all folded into the design — the `resolve_proficiency` parameterization note (§2),
the new Live-tunability subsection (§3), the seed-discipline mapping-table fix (§7), and the
content-migration modifier-key-remap note (§6.1)). Origin: the user found Lorecraft's current
skills-vs-abilities split
genuinely confusing (two separate systems both called "skill" — a flat numeric `SkillRegistry`
catalog vs. the Sprint 74 skill-tree's `ability.<id>` nodes — that don't share storage or
vocabulary) and provided a detailed Discipline → Ability design brief to replace both with one
coherent, fully data-driven model.

**Scope: Phase A (Tier 1 mechanism) plus the start of Phase B (Tier 2 scaffolding), stopping
short of content/migration/commands** — those are Sprint 78. Mirrors the Sprint 73/74
mechanism-then-policy split precedent.

| # | Task | Status |
|---|------|--------|
| 77.1 | **`engine/game/abilities.py` — `AbilityDef`.** New Tier 1 value object (mirrors `engine/game/leveling.py`'s shape): id, discipline id, tier, `ability_type`, `activation_type`, prerequisites, cost, usage-requirement descriptors. Pure data, no hardcoded ability IDs (`discipline_ability_system.md` §2). | [x] |
| 77.2 | **`check_acquisition(player_state, ability, discipline_rank) -> AcquisitionResult`.** Generic "can this player learn this ability" mechanism — cost affordable, prerequisites held, discipline rank + level met. Knows nothing about what an ability unlocks (§2). | [x] |
| 77.3 | **`check_usage(actor_state, ability, target_state, world_state) -> UsageResult`.** Generic "can this ability be performed right now" mechanism — character/target-state match via existing `Player.flags`/`ActiveEffect`, cooldown/resource affordability. **Genuinely new capability** — today's verbs hardcode their own gating in Python; this is the single biggest structural addition (§2, §5.3). | [x] |
| 77.4 | **`resolve_proficiency(rng, base_level, modifiers, improve_chance, max_rank) -> float`.** Thin wrapper composing the existing `modifiers.py::resolve()` and `checks.py::skill_check()` Tier 1 primitives. **Parameterized, not hardcoded**: `improve_chance` and `max_rank` are supplied by the Tier 2 caller (from YAML/config), not baked in as module constants the way `features/skills/service.py`'s `IMPROVE_CHANCE`/`MAX_LEVEL` are today — that would leak policy into the mechanism layer (§2). Shipped signature leads with `rng: GameRng` (not in the original illustrative sketch) since the roll composes `skill_check`, which requires it and is never called with bare `random`; it therefore also inherits `skill_check`'s 5%/95% floor/ceil clamping — see `discipline_ability_system.md` §2 for the full accepted-deviation note. | [x] |
| 77.5 | **Cooldown/resource primitives.** A small, generic `ResourceLedger`-style affordability check (stamina is the only resource Lorecraft has today — no speculative multi-resource system) plus a cooldown-timestamp check, both keyed off existing `ActiveEffect`/meter primitives. No new resource-type registry (§2). | [x] |
| 77.6 | **Unit tests for 77.1–77.5.** Pure Tier 1 module, no content yet — cover acquisition/usage/proficiency/cooldown edge cases with synthetic `AbilityDef`s, not real disciplines (those arrive in Sprint 78). | [x] |
| 77.7 | **Phase B.1 — `features/disciplines/` package skeleton.** New Tier 2 package (manifest-only stub at this stage) that will host the registries Sprint 78 builds out; establishes the package location and import boundaries (may import `engine.*`, never a web host) ahead of the registry/schema work. | [x] |
| 77.8 | **Docs.** This roadmap section plus confirmation that `discipline_ability_system.md` accurately reflects the shipped Tier 1 module's actual signatures (update if implementation deviates from the design in any parameter name/shape). | [x] |

**Tier boundary:** 77.1–77.6 are pure **Tier 1** (`engine/game/abilities.py`) — no discipline
identities, ability content, or policy values hardcoded anywhere in this sprint. 77.7 opens the
**Tier 2** package location only (no registries/schema yet — those are Sprint 78).

---

## Sprint 78 — Discipline/Ability system: Tier 2 policy & content (Phases B.2–F)

**Used (all complete, merged to main as v0.98.0).** Implemented on branch
`sprint-78-abilities-tier2` — 8 implementation commits (`c4e4c34` 78.1 `DisciplineDef`/
`DisciplineRegistry`, `d6fb469` 78.2 `AbilityRecord`/`AbilityRegistry`, `bc3174e` 78.3
`PlayerStats.skills`→`discipline_ranks` migration, `7df0e59` 78.4 `disciplines.yaml`/
`abilities.yaml` content, `413243f` 78.6 code migration — delete the flat skills catalog + wire
services, `c225a84` 78.7 relocate `train`/`abilities` verbs to the `disciplines` feature,
`3d33431` 78.8 retrofit `forage` onto data-driven `check_usage`, `4557266` 78.9
`AbilityService`/command/modifier-source test coverage), plus the earlier design-correction
commit (`779d48f`) already on the branch. Builds the opinionated, data-driven policy layer on
top of Sprint 77's mechanism: registries, YAML content, the `PlayerStats` schema migration,
content migration, and the command rework. Full detail in
[`discipline_ability_system.md`](discipline_ability_system.md) §4–§9. **Design correction
(2026-07-13):** the design doc originally directed a `sharp_eyes` modifier-key remap (78.5,
below) as part of content migration; that premise was found false and the remap is dropped —
see §6.1's Option A and 78.5's row for the corrected reasoning.

| # | Task | Status |
|---|------|--------|
| 78.1 | **`DisciplineDef`/`DisciplineRegistry`.** Loaded from `world_content/disciplines.yaml`, mirroring the existing `SkillTreeRegistry` load pattern (marks-def, `discover_features()`-compatible). Static YAML only — discipline structure is not a live-tunable dial (§3). | [x] |
| 78.2 | **`AbilityRegistry`.** Loaded from `world_content/abilities.yaml` (split from `disciplines.yaml` per §5.4's rationale — disciplines change rarely, abilities change often), each entry validated into the Tier 1 `AbilityDef` shape plus Tier-2-only display fields. | [x] |
| 78.3 | **`PlayerStats` schema migration (Database Specialist gate).** `skills: JsonObject` → `discipline_ranks: JsonObject` (same dict shape, different keys); `unlocked_nodes` kept as-is (a "node" is an "ability" now, vocabulary-only). Follow the Sprint 75 generic reflection-scanner pattern, not a hand-written shim (§4, §6.2). | [x] |
| 78.4 | **Content migration — 5-discipline non-combat seed set.** Survival, Subterfuge, Commerce, Rhetoric, Fortitude, absorbing all 7 existing skill-tree nodes (`forage`, `keen_senses`, `pick_locks`, `mule`, `sharp_eyes`, `haggler`, `silver_tongue`) and all 6 flat skills, zero new combat content (§7). | [x] |
| 78.5 | ~~`sharp_eyes` modifier-key remap.~~ **Dropped, superseded 2026-07-13 by the Option A namespace-retention decision — see [`discipline_ability_system.md`](discipline_ability_system.md) §6.1.** The original premise (that `skill.perception` was the *only* reference to the flat namespace, and had to be remapped to `discipline_ranks.subterfuge`) was false — a fuller audit found six live `skill.<name>` references across `traits/standard.py`, `consumables/buffs.py`, `items/effects.py`, `marks.yaml`, and `webui/player/frontend.py`, not just `sharp_eyes`. Research/Planning's resolved direction: `skill.<name>` is retained **permanently** as the check/modifier-key namespace (it's orthogonal to the `features/skills/` package's existence, not a back-compat alias); only the flat `SkillRegistry` catalog and `PlayerStats.skills` storage are deleted, with each check's base value re-sourced from `discipline_ranks.<discipline>` instead. No remap needed anywhere — this task is moot. | [ ] dropped |
| 78.6 | **Code migration.** Delete `features/skills/definitions.py` (no back-compat alias, matches the `area_id` disposition precedent); `features/progression/skill_tree.py` → `features/disciplines/abilities.py` (renamed/extended); `engine/game/checks.py::skill_check()` and `engine/game/modifiers.py` unchanged (§6.3). | [x] |
| 78.7 | **Command rework — `train`/`learn`/`abilities`/`skills` → unified discipline/ability commands.** Driven by the generalized `check_acquisition`, folding in the already-flagged "one `ctx.say()` per command" fix for these commands' listings while their underlying data model changes shape anyway. | [x] |
| 78.8 | **Retrofit existing verbs onto `check_usage`.** `features/exploration/forage.py`, `sense.py`, movement/lockpicking's `pick` — replace hardcoded Python conditions (e.g. `Room.indoor == False`) with data-driven `usage:` YAML read through `check_usage`, proving the new mechanism actually replaces the old gating, not just duplicates it (§6.3). | [x] |
| 78.9 | **Backend + Frontend unit/e2e tests.** Registry loading, acquisition/usage flows end-to-end through the real content, command output, schema migration round-trip. | [x] |
| 78.10 | **Full Test & QA pass** (lint + typecheck + test, e2e) before merge. | [x] |
| 78.11 | **Docs.** `docs/user_guide.md` (disciplines/abilities/proficiency explained to players), `docs/admin_builder_guide.md` (authoring new abilities/disciplines), this roadmap section. | [x] |

**Gate results (78.10):** Database Specialist, Code Reviewer, and both Test & QA lanes (unit +
e2e) all reported clean. Four small non-blocking follow-ups were surfaced and moved to the
follow-up backlog rather than blocking merge: a dead `PlayerStats.skills` column left
un-dropped (startup warning), two stale `required_skill`/`required_skill_min` comments in
`features/weather/modifiers.py`, a cosmetic help-category mismatch for `train`/`learn`/
`abilities`, and an e2e coverage gap for the new command surface. Sprint 79 closed the first
three; the e2e command-surface gap remains in the active roadmap backlog.

**OPEN ITEM carried from the design audit — not resolved here, flagged for a future sprint if
demand appears:** per-ability `cost`, `cooldown_seconds`, resource costs, and proficiency-growth
tuning (`improve_chance`/`max_rank`) are shipped as **static YAML** in this sprint, matching
`skill_tree.yaml`'s existing precedent. They are *candidates* for a live-tunable DB-singleton
admin control (the `WorldClock`/Sprint 76 economy pattern) — worth building only if admins
actually ask to retune these without a reseed. Don't build it speculatively ahead of that
demand (`discipline_ability_system.md` §3).

**Tier boundary:** all of 78.1–78.8 are **Tier 2** (`features/disciplines/`) + content
(`world_content/*.yaml`) + composition-layer command wiring. **No further `engine/` changes**
beyond what Sprint 77 already shipped.

---

---

## Sprint 79 — Discipline migration/help cleanup

**Goal:** close the concrete non-blocking Sprint 78 review findings without expanding the
Discipline/Ability feature surface. This is cleanup/patch work: a dedicated SQLite migration,
comment drift, help taxonomy, and roadmap triage for a future live-tuning idea.

| # | Task | Status |
|---|------|--------|
| 79.1 | **Drop stale `PlayerStats.skills` DB column.** Add a dedicated, idempotent SQLite migration (`_migrate_playerstats_skills`) after the additive scanner: `discipline_ranks` is added by the scanner, then the legacy pre-78 `skills` column is dropped so DB-only-column startup warnings self-clear. No data fold is attempted because the keyspace changed from flat skills to disciplines. | [x] v0.98.2 — implemented in `db.py` with focused migration tests. |
| 79.2 | **Fix stale `required_skill` comment terminology.** Update `features/weather/modifiers.py` comments/docstring to refer to `required_discipline` / `required_discipline_min`; code already used the renamed fields. | [x] v0.98.2 — comment-only cleanup. |
| 79.3 | **Move discipline command help category.** Register `train`/`learn`/`abilities`/`disciplines` under the `"disciplines"` help category instead of `"progression"` and add a `Disciplines` label/order entry in `commands/meta.py`. | [x] v0.98.2 — cosmetic help grouping fix with unit coverage. |
| 79.4 | **Live-tuning decision for ability costs/cooldowns/proficiency growth.** Keep per-ability `cost`, `cooldown_seconds`, resource costs, `improve_chance`, and `max_rank` static YAML for now. Add the live-admin UI/config migration to the Backlog only if admins ask to retune these without restart/reseed. | [x] v0.98.2 — documented as deferred demand-driven scope; no implementation. |

## Sprint 80 — Zone climate, loot, ambience, spawns, and NPC routes

**Goal:** close the active world-system gaps that were still listed as blocked/partial in
`docs/roadmap_world.md`: zone-specific climate bias, data-driven random NPC spawns, randomized
room treasure, timed ambient room flavor, and visible fixed-route NPC movement.

| # | Task | Status |
|---|------|--------|
| 80.1 | **Tier 2 zone climate support.** Add `ZoneClimateService` under `features/weather/`, loading a `climates:` block from `world_content/weather_fronts.yaml`, rolling per-zone weather on `DAY_CHANGED`, and narrating only to occupied outdoor rooms in that zone. Whisperwood is weighted rainy/misty; Cogsworth is weighted clear/overcast. | [x] v0.99.0 — `features/weather/climate.py`, `world_content/weather_fronts.yaml`, `tests/unit/test_zone_climate.py`. |
| 80.2 | **Spawn/respawn templates for random NPC spawns.** Exercise the existing `features/spawns` controller with `world_content/spawns.yaml`, topping Whisperwood wisps and Cogsworth sewer vagrants from template NPCs. | [x] v0.99.0 — `world_content/spawns.yaml`; existing `tests/unit/test_spawns.py` covers controller behavior. |
| 80.3 | **Randomized room treasure/loot tables.** Add `Room.loot_table` YAML/DB round-trip and a Tier 2 `RoomLootService` that rolls once per player-room visit and materializes rewards through `ItemLocationService.spawn`. | [x] v0.99.0 — `features/exploration/loot.py`, loader/validator/model support, `hollow_oak_cache` content, tests. |
| 80.4 | **Ambient/timed room flavor events.** Add `Room.ambient_events` YAML/DB round-trip and a Tier 2 `RoomAmbientService` that emits authored room lines on world ticks for occupied rooms. | [x] v0.99.0 — `features/exploration/ambient.py`, Whisperwood/Cogsworth content, tests. |
| 80.5 | **NPC-specific route hooks + broader autonomous NPC behavior.** Preserve the existing `wander`/`patrol` tick loop and add `NpcRouteLoader` for NPC `ai.mode: route`, wiring NPC-specific `RouteHooks` over the generic `MobileRouteService` to broadcast departure/arrival and update `NPC.current_room_id`. Convert Scout Wren to a looped route patrol. | [x] v0.99.0 — `features/npc_ai/routes.py`, `main.py` wiring, `world_content/world.yaml`, tests. |
| 80.6 | **Admin UI support for multiple weather states.** Extend the Clock admin API/UI so admins can see the global weather plus each configured zone climate, and set a zone's local weather live. | [x] v0.99.0 — `/admin/clock` now returns `zone_weather`, `/admin/clock/zone-weather` updates one zone, and the web Clock tab renders per-zone selectors. |

## Sprint 81 — Ashmoore graveyard and Brass Vaults content

**Goal:** expand authored world content using the existing Phase A world-building surfaces:
rooms, items, context-attached object commands, dialogue-started quests, NPC AI, and spawn
controllers.

| # | Task | Status |
|---|------|--------|
| 81.1 | **Ashmoore graveyard.** Add the Old Hill Graveyard off South Gate with interactive tombstones, dark crypt/ossuary rooms, graveyard relics and wearables, Grave-Warden Elsbet, and undead templates. | [x] v0.100.0 — `world_content/world.yaml`; validated with `world_cli validate`. |
| 81.2 | **Tombstone undead spawns.** Add spawn controllers for tombstone skeletons, bell ghosts, and a crypt wight, all confined to `ashmoore_graveyard`. | [x] v0.100.0 — `world_content/spawns.yaml`; spawn refs checked against authored zones/templates. |
| 81.3 | **Brass Vaults steampunk zone.** Add a steampunk zone reached by `up` from `inner_vault`, with descriptive rooms, steampunk items/wearables, dark maintenance rooms, Forewoman Cassia, patrolling/wandering mechanical hazards, and ten local quests. | [x] v0.100.0 — `world_content/world.yaml`; validated/import-checked. |
| 81.4 | **Working cave light sources.** Make the Dented Oil Lantern and Brass Oil Lantern actual `light: 1` sources and document the `wield` + `light` player flow. | [x] v0.100.0 — `world_content/world.yaml`, `docs/user_guide.md`. |

---

## Sprints 56–69 — observability, client themes/layouts, multi-level map, escort quests, scripting world-building (v0.47.0–v0.75.0, archived 2026-07-10)

> Moved here from the active roadmap on 2026-07-10 once Sprint 69 closed. Full task
> detail preserved below; per-version notes in [`../CHANGELOG.md`](../CHANGELOG.md).

## Sprint 56 — Structured output-type tagging

**Goal:** tag every engine-emitted message with a semantic type (`room_event`, `chat`, `tell`,
`combat`, `quest`, `warning`, `hint`, `system`) at the point of emission, instead of the flat
untyped strings `GameContext.say()` produces today. **Why now:** the direct-response channel
(`ctx.messages`) carries zero type information at all; the room-broadcast channel
(`engine/game/broadcast.py`) only has an ad hoc binary `message_type: "chat" | "room_event"`. This
is a single call-site change today (`ctx.say`) — leaving it untyped through the trading/quest band
was fine, but combat (when it returns) and further quest/social output will multiply call sites
fast, and retrofitting a type onto every existing `ctx.say(...)` later is far more expensive than
adding one now. No new commands or player-visible behavior — this is invisible infrastructure that
unlocks output filtering/routing (mute-by-type prefs, accessible/screen-reader-friendly rendering,
future non-web clients) without further engine work.

| # | Task | Status |
|---|------|--------|
| 56.1 | Define the starter taxonomy (`room_event`, `chat`, `tell`, `combat`, `quest`, `warning`, `hint`, `system`) in one small module. Keep it short and resist one-off types per feature — same "small, named taxonomy" discipline as the `EventBus` event names. | [x] `engine/game/message_types.py` — `MessageType(str, Enum)`. |
| 56.2 | Extend `GameContext.say()` to accept an optional message type (default `"system"`); thread it through `ctx.messages` (currently `list[str]` → a small `(type, text)` pair or frozen dataclass) without changing every call site's required arguments. | [x] `Message(str)` subclass carrying `.type` (`message_types.py`) — `ctx.messages` stays behaviorally `list[str]` (equality/`.startswith`/`in`/JSON serialization all degrade to plain text), so none of the ~280 existing `ctx.say(text)` call sites or their test assertions needed to change. |
| 56.3 | Reuse the same taxonomy on the room-broadcast payload (`broadcast.py`'s `feed_append` messages) in place of the current `"chat"`/`"room_event"` binary, so the direct-response and broadcast channels share one vocabulary. | [x] `broadcast.py`, plus the two duplicate disconnect-narration broadcasts in `main.py`/`frontend.py`, now source `"message_type"` from `MessageType.*.value` instead of separate literal strings. |
| 56.4 | `webui/player/frontend.py`: apply a CSS class per type when rendering the feed (`.msg-combat`, `.msg-warning`, …) — the first real consumer, and the seed for a future per-type mute/filter preference (no new engine work needed later). | [x] Feed messages carry a new `msg_type` field; `feed_item.html`/`feed_items.html` add an additive `msg-<type>` class (new CSS only for types actually in use — `quest`/`warning`/`tell`/`combat`/`hint` — so untouched call sites' current look is unchanged). |
| 56.5 | Sweep existing `ctx.say(...)` call sites in `engine/` and `features/`; assign a type where the intent is clear from context, leave genuinely ambiguous ones on the `"system"` default rather than guessing. | [x] Full sweep of all 28 files with `ctx.say()` calls (283 call sites total): 171 retyped (162 `WARNING`, 7 `QUEST`, 1 `TELL`, 1 `HINT` — first use of `HINT`, decided together for `exploration/service.py`'s hidden-passage discovery message), 112 deliberately left on `SYSTEM`. `WARNING` = precondition failures, disambiguation prompts, exception-message passthroughs, and the core parser/dispatch errors in `engine/game/engine.py` (all 8 of that file). `QUEST` = quest/hunt/mark progression and reward narration. Left on `SYSTEM`: successful-action confirmations ("You take the sword.") across every file; whole read-only report/display commands (`character/service.py` traits/skills/reputation/score, `exploration/journal.py`, `marks/commands.py`, `hunts/commands.py` listings — none of their calls, including empty-states, are warnings); `fatigue/service.py` (sampled, no clean fit); `context_commands/commands.py`'s `binding.say` (arbitrary world-content-authored text, no single type could fit); `follow/service.py`'s `_show_status` (a status check, not an error, despite sharing exact text with `unfollow`'s genuine failure case — caught and reverted after an initial blanket `replace_all` mistake). `follow/service.py`'s `_notify()` helper gained its own `msg_type` passthrough param so `_break_follow`'s two involuntary-disconnect notifications could be tagged `WARNING` without affecting its other (voluntary-action) callers. |

## Sprint 57 — Request tracing & crash reports

**Goal:** extend Sprint 13's structured logging (correlation/transaction IDs) and command latency
percentiles with two admin-facing debugging tools that don't exist today: a per-command trace of
what actually happened (conditions checked, events fired, DB commits) and a saved, browsable record
of unhandled exceptions. Today an admin diagnosing a bad command has only raw log grep by
`transaction_id` — no structured "what ran" view and nothing captured for an exception beyond
whatever hits stdout.

| # | Task | Status |
|---|------|--------|
| 57.1 | Trace buffer: within `bind_transaction_context()`'s scope, collect an ordered list of trace spans (condition evaluations, event dispatches, DB commits — reusing `time_operation`'s existing timing) keyed by `transaction_id`. In-memory ring buffer over the last N commands — not persisted, matching the "measure, don't over-build" caution already applied to the deferred concurrency work. | [x] `observability.py`'s `TraceSpan`/`record_span`/`get_trace` + a 200-entry `OrderedDict` ring buffer; `time_operation()` records automatically, `EventBus.emit()` and the command-handler dispatch call `record_span()` directly since they already compute their own timing. |
| 57.2 | `GET /admin/trace/<transaction_id>` — returns the captured spans for one recent command (404 once it's aged out of the ring buffer). | [x] `webui/admin/routers/observability.py`. |
| 57.3 | Crash capture: a handler at both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`) that, on an unhandled exception, persists a `CrashReport` row (transaction_id, correlation_id, player_id, command text, stack trace, timestamp) to the audit DB and returns a friendly in-game error instead of a raw disconnect/500. | [x] New `CrashReport` model (`engine/models/audit.py`) + `engine/services/crash_reports.record_crash()` (rolls back both sessions first so a crash report never smuggles in unrelated pending writes); both entry points wrap their command-processing body in try/except. |
| 57.4 | `GET /admin/crashes` (list) + `GET /admin/crashes/<id>` (detail) endpoints and a Crash Reports tab in the admin console, reusing the Audit tab's table/detail pattern. | [x] Endpoints in `observability.py`; admin console gets a list-table + detail-panel layout (mirrors the World tab's room-list/room-editor split) wired into `TAB_LOADERS`. |
| 57.5 | Document both features (usage, endpoints, retention) in [`observability.md`](observability.md) and cross-link from the admin guide's Troubleshooting section. | [x] |

---

## Sprint 58 — Selectable client themes & layouts

**Goal:** turn the four client design directions in [`Lorecraft Client.dc.html`](Lorecraft%20Client.dc.html)
— **terminal** (1a), **parchment** (1b), **slate** (1c), **immersive** (1d) — into player-selectable
**themes** *and* **layouts**, persisted through the same `PlayerPreferences` blob as every other
display setting. **Why now:** the foundation gate is green and the display-preference seam
(Sprints 32.2/32.3 — density, font scale, high-contrast, hidden panels) already exists; both are a
natural extension of it, not new engine surface.

**Two orthogonal axes, sequenced.** *Phase 1 (58.1–58.4)* delivers **theme** = palette + typography
on today's three-column layout — small, low-risk, and independently shippable. *Phase 2 (58.5–58.8)*
adds **layout** as a *second, independent preference* (`standard` / `ledger` / `dock` / `immersive`),
so a player can pair any palette with any arrangement — matching the mockups' own "combine 1c layout
with 1d's chronicle" framing. Phase 1 lands first and stands alone; Phase 2 builds on it.

### Phase 1 — Themes (palette + typography)

| # | Task | Status |
|---|------|--------|
| 58.1 | **Theme token layer + preference.** Add a semantic CSS-variable token layer (`--lc-bg`, `--lc-panel`, `--lc-accent`, `--lc-text`, `--lc-text-muted`, `--lc-border`, `--lc-font-body`, `--lc-font-head`, …) to `static/css/custom.css`, defaulting to today's zinc/emerald terminal values (**zero visual change**). Point `base.html`'s Tailwind config semantic colours (`panel`/`accent`/`text`/`text-muted`/`feed-bg`/`border`) at those vars. Add a `theme` enum to `PlayerPreferences` (`THEMES = ("terminal","parchment","slate","immersive")`, default `terminal`), emit `theme-<name>` on `<body>` via `body_classes`, and add the theme `<select>` to the settings form. Unit tests for the pref round-trip/validation + the body-class output. | [x] `theme` field on `PlayerPreferences` (default `terminal`, leads `body_classes`); Tailwind semantic colours resolve to `--lc-*`; settings selector; `TestTheme` unit + `test_game_screen_applies_theme_body_class`/`test_settings_renders_and_persists_theme` integration tests. |
| 58.2 | **Slate & Immersive (dark) themes.** Define the `slate` (1c: `#0a0d15`/`#43c7d8`, Plex Sans) and `immersive` (1d: `#0a0807`/`#e8a13c`, Plex Sans) token sets + the override layer that remaps the raw `zinc-*`/`emerald-*` literals still in the partials (same mechanism as the existing high-contrast block) so both repaint the whole screen. Load the required web fonts. | [x] Shared **`body:not(.theme-terminal)` remap** (one block, specificity 0,2,x — no `!important`) routes every raw literal through the tokens; each theme is just a token block. IBM Plex Sans/Mono + Spectral loaded in `base.html`. |
| 58.3 | **Parchment (light) theme.** The one light theme (1b: `#e3d7bd`/`#8c3b2e`, Spectral serif body + Plex Mono commands) — inverts background/text, needs its own override set and a WCAG-AA contrast pass. | [x] `body.theme-parchment` token block + serif body / mono commands + softened error-red + lifted feed-hover for the light ground. |
| 58.4 | **Theme docs & regression tests.** Document the theme picker in [`user_guide.md`](user_guide.md); changelog; a settings test that a chosen theme persists and re-renders selected; a render assertion that `<body>` carries the right `theme-*` class. | [x] Regression tests landed with 58.1; user-guide "Themes" section + CHANGELOG. |

### Phase 2 — Layouts (panel arrangement)

| # | Task | Status |
|---|------|--------|
| 58.5 | **Layout preference + collapsible-panel mechanism.** Add a `layout` enum to `PlayerPreferences` (`LAYOUTS = ("standard","ledger","dock","immersive")`, default `standard`), emit `layout-<name>` on `<body>` (independent of `theme-*`), and build the shared building block the other three need: an Alpine-driven **collapsible panel rail** (icon-collapsed ↔ expanded), CSS-only where possible. `standard` reproduces today's three-column grid (**zero visual change**). Settings gets a layout `<select>`; unit tests mirror 58.1. | [x] `layout` field (default `standard`) as a second body-class axis; settings picker; `TestLayout` unit + `test_game_screen_applies_layout_body_class` integration tests. Collapsible rail deferred to 58.8, the only layout that needs it. |
| 58.6 | **Ledger layout (1b) + shared right-rail Inventory/Quests.** Left column = Location + Map; Chronicle runs wide in the centre; secondary panels collapse into a slim right rail. | [x] Narrow left (Location + Map) + **wide full-width chronicle** (the 72ch cap that starved it was removed after review). **Inventory now moves into the right rail for *every* layout** (per review), paired with Quests as a **mutually-exclusive** pane (both stay in the DOM so `#inventory`/`#quest-tracker` OOB updates fire while hidden). Two UI patterns to compare: **standard = toggle button** (one titlebar, a button flips Inventory⇄Quests); **dock + ledger = window-shade accordion** (stacked titlebars). `test_inventory_and_quests_share_right_rail`. |
| 58.7 | **Dock layout (1c).** A visible control bar (theme · density · layout · panel toggles surfaced from `/settings` inline) above card-style panels, plus the rarity-coloured **icon-grid inventory** variant. Drag-to-reorder panels is a **stretch** (behind a flag) — the reviewable core is the toolbar + card treatment + icon-grid. | [x] Superseded by the **bespoke Dock rebuild in 59.7** — card shell, rarity **icon-grid** Pack, and Party/Quests are all delivered there; the base-nav Mode/Palette pickers act as the control bar. (Drag-to-reorder remains the deferred stretch.) |
| 58.8 | **Immersive layout (1d) + docs.** Near-full-bleed Chronicle with a soft vignette; everything else collapses to a slim icon rail (58.5) that expands on demand; floating minimap + floating command bar. Document both axes in [`user_guide.md`](user_guide.md); changelog; render tests asserting the `layout-*` body class and that hidden-by-default rail panels are still reachable. | [x] **Reworked to a focused 2-column view** (per review): a slim left column with **Chat on top + Minimap below** and a dominant Chronicle taking the rest; Room/Inventory/Players/Quests dropped; larger type + soft vignette. Chat routes into the left pane (its `#chat-feed` is what the client keys on); the centre pane is suppressed there to keep the id unique. `test_immersive_layout_puts_chat_in_left_column`. |
| 58.9 | **Live theme/layout preview.** The Settings **Theme**/**Layout** dropdowns preview immediately (Alpine swaps the `theme-*`/`layout-*` body classes on change); **Save** persists via the existing POST, **Cancel** returns to `/game` and reloads the last-saved prefs (natural revert). | [x] `settings.html` Alpine `applyPreview()`. |
| 58.10 | **Settings Save→game + [Save][Cancel].** Per review: **Save** uses Post/Redirect/Get to return straight to `/game` (the new look applies immediately, no second click); the button row is just **[Save] [Cancel]** — the top back-to-game link, the saved-banner, and the hint text are removed. | [x] `POST /settings` → 303 `/game`; `settings.html` trimmed; three POST tests updated for the redirect. |
| 58.11 | **Top-bar quick appearance pickers (experimental, flag-gated).** Small **Theme** + **Layout** dropdowns in the nav (left of the player name/Settings) that take effect immediately — Theme swaps the body class client-side, Layout persists + reloads — via a dedicated `POST /settings/appearance` that updates *only* the posted field(s), merged over current prefs. Gated by `APPEARANCE_TOPBAR` + a self-contained partial so it can be peeled back after testing. The settings page keeps its own pickers. | [x] `partials/topbar_appearance.html`, `lcApplyTheme()`, `/settings/appearance` route, `APPEARANCE_TOPBAR` flag; render + partial-update tests. |
| 58.12 | **Own chat routes into the chat pane too, styled as a "sent by me" bubble.** Per review: the actor's own `say`/`tell`/topic-channel echo only ever showed in the main chronicle, never in a chat pane (a latent gap — only *other* players' chat, via WS, ever reached `#chat-feed`). Now routed there via an HTMX OOB append whenever a chat pane exists (`separate_chat`, or always in immersive), and styled distinctly: the colour bar moves to the **right** and the line **right-justifies**, mirroring everyone else's left-barred/left-aligned lines — scoped to `#chat-feed` only, so the plain narrative feed is unaffected. | [x] `route_chat_oob` computed in `handle_command()`; `feed_items.html` marks `type=='chat'` items `mine` + `hx-swap-oob="beforeend:#chat-feed"` (safe unconditionally — a rendered chat item is *always* the actor's own echo; others' chat only ever arrives client-side via WS); `#chat-feed .msg.chat.mine` CSS. `test_immersive_own_chat_routes_to_chat_pane`. |
| 58.13 | **Immersive chronicle reads like an old-school MUD; the right column is gone outright.** Per review: (a) drop the per-line colour gutter and timestamp in immersive's `#feed` — plain scrolling text, telnet-MUD style; (b) narrate the **full room** (name/description/NPCs/items/exits) as chronicle text when entering a new room — movement never narrated any of this before (that was the panel's job, and immersive has no panel); `look` already narrates name/description/exits via the engine's existing output, so only the **players-here** line is added there; (c) the right column (Here Now / Inventory / Quests) is dropped from the DOM entirely for immersive, not just hidden — including its mobile tab. | [x] `mud_room_block()`/`mud_players_here_line()` (`rendering.py`) reuse the same `room_panel`/`players_here()` data the panels render, so they can't drift; wired into both `/game`'s initial load and `handle_command()` (keyed off `room_changed` vs. the `look`/`l` verb, tagged `msg_type=room_event` — no ordinary `ctx.say()` produces that tag, so it's an unambiguous test signal). `game.html`'s right sidebar + its mobile tab are now `{% if prefs.layout != 'immersive' %}`-gated. Tests: `test_immersive_movement_appends_old_school_mud_room_block`, `test_immersive_look_appends_players_here_line_only`, extended `test_immersive_layout_puts_chat_in_left_column`, new `test_standard_layout_keeps_players_column_and_tab`. |

---

## Sprint 59 — Classic mode (old-MUD CRT terminal)

**Goal:** integrate the new **"Classic" mode** (design source: the `Lorecraft Client (standalone).html`
canvas + the `lorecraft-export/classic/` reference, kept local — see the design-export note below) —
a pure old-MUD phosphor-CRT terminal. Added
**alongside** the existing themes/layouts (per review — nothing removed), so it slots onto the same
two orthogonal axes: a **theme** (CRT palette) and a **layout** (MUD arrangement). Reuses the
chronicle-narration machinery from Sprint 58.13 (immersive), which classic also needs.

| # | Task | Status |
|---|------|--------|
| 59.1 | **Classic CRT themes.** Add `classic` (phosphor green) + `classic-amber` to `THEMES`: token overrides from the `lorecraft-export/classic` palette, a text-shadow **phosphor glow**, and a fixed **scanline overlay** (`::after`, `z-index:40` under the modals; suppressed under `reduced-motion`). Caught by the shared `:not(.theme-terminal)` remap like every other theme. | [x] `body.theme-classic{,-amber}` token blocks + glow + CRT overlay in `custom.css`. |
| 59.2 | **Classic layout.** Add `classic` to `LAYOUTS`: a purpose-built shell (`partials/game_classic.html`) — chronicle (`#feed`) + vitals prompt + command input on the left, a ~420px **minimap-over-chat** column on the right (chat has its own input that rewrites `command`→`say …` via `htmx:configRequest`). Chronicle-only, so it drops room/inventory/players/quests and reuses the MUD room-narration (`MUD_CHRONICLE_LAYOUTS = ("immersive","classic")`) + own-chat→pane routing (`route_chat_oob`). `game.html` branches `#main-content`, the mobile tab bar, and the full-width command bar on `layout == 'classic'`. | [x] `game_classic.html`; `game.html` three-way branch; shared `#feed`/`#chat-feed`/`#minimap`/`#command-input` ids preserved so WS/OOB/hotkeys keep working. |
| 59.3 | **Vitals prompt + polish + tests + docs.** A real **vitals line** in the prompt (`session.vitals_snapshot`: fatigue meter as stamina + carried coins via the ledger — Lorecraft has no HP/MP/MV, so surface real meters; OOB-refreshed each command). Nicer picker labels (`classic-amber` → "Classic Amber"). Render + command tests; user guide + changelog. | [x] `partials/vitals.html`; `#vitals` OOB refresh in `handle_command`; `test_classic_layout_renders_mud_terminal`, `test_classic_layout_command_refreshes_vitals_and_routes_chat`; existing parametrized `TestTheme`/`TestLayout` auto-cover the new enum values. |
| 59.6 | **Couple layout + palette into tuned "Modes" (+ optional override).** Per the 2026-07-09 UI direction: the **layout is the primary "Mode"**, and each mode has a tuned default palette (`MODE_DEFAULT_THEME`: standard→terminal, e-reader→parchment, dock→slate, immersive→immersive, classic→classic). The theme pref gains an **`auto`** default (the new zero-config default) that resolves to the mode's palette, and otherwise acts as an **optional override**. Settings/top-bar relabelled (Mode · Palette override); live preview + `lcApplyTheme` resolve `auto` client-side from the current mode. Coupled but reversible — the two prefs still exist underneath. | [x] `resolved_theme`/`MODE_DEFAULT_THEME` in `preferences.py`; `theme` default `auto`; settings + topbar relabel; `TestTheme` auto-resolution tests. **Next:** bespoke **immersive** (slim icon rail + floating minimap/command) rebuild to match `lorecraft-export/` — **dock done in 59.7**. |
| 59.7 | **Bespoke Dock rebuild (closer emulation round 2).** Replace the CSS-only "card treatment over the grid" (58.7 first cut) with a purpose-built shell (`partials/game_dock.html`) matching `lorecraft-export/dock`: three columns of floating **`.dock-card`** panels (gradient bg, rounded, drop shadow, a drag **grip**, uppercase titles) — LEFT Location + Minimap, CENTRE Chronicle (`#feed` + a gradient **Send** button), RIGHT Party + a **Pack** card with the **rarity icon-grid** inventory (4-wide tiles, dashed empty slots, click-to-examine) and a **Quests footer** (replacing the window-shade accordion). `inventory.html` renders both grid + list; CSS reveals the grid only under `body.layout-dock` so `#inventory` stays a single OOB target. Slate palette gains a violet `--lc-accent-2` for the Send gradient. | [x] `game_dock.html`; `game.html` `elif dock` branch + toggle-pane collapsed to standard-only; `.dock-card`/`.dock-send`/`.grip`/`.dock-quests-foot`/`.inv-grid`/`.inv-slot` CSS (old `body.layout-dock .game-col` rules removed); `test_dock_layout_renders_card_shell`, updated right-rail test. **Next:** bespoke **immersive** rebuild (59.8). |
| 59.8 | **Bespoke Immersive rebuild (closer emulation round 3).** Replace the 2-column immersive (chat-in-left-column) with a purpose-built cinematic shell (`partials/game_immersive.html`) matching `lorecraft-export/immersive`: a slim left **icon rail** (glyph buttons that run look/inventory/journal/score into `#feed`), a **full-bleed chronicle**, and a **floating minimap card** + **floating command bar** (amber glass) over it. Chat now **folds into the chronicle** (no separate pane) — `route_chat_oob` drops immersive, so the actor's echo stays in `#feed` and other players' WS chat degrades into it via `appendToChat`. The grid `game.html` branch is simplified to Standard-only (all the `!= immersive` guards and the left chat-pane removed). Still chronicle-only + MUD-narrated (`MUD_CHRONICLE_LAYOUTS`). | [x] `game_immersive.html`; `game.html` `elif immersive` branch + grid de-immersived + command-bar guard; `.immersive-rail`/`.immersive-ico`/`.immersive-map`/`.immersive-cmd` CSS; `route_chat_oob` narrowed to `separate_chat or classic`. Tests: `test_immersive_layout_renders_full_bleed_shell`, `test_immersive_own_chat_folds_into_chronicle` (rewritten from the old chat-pane tests); MUD-narration tests unchanged. **All five modes now have bespoke shells.** |
| 60.1 | **Per-mode typography pass.** Give each Mode a tuned type treatment, scoped by its palette class (the palette carries the mode's typographic identity in the coupled design): Standard → JetBrains Mono, code-literal (`calt` off), 13px/1.7 chronicle; E-reader → Spectral serif 15px/1.8 with oldstyle figures (`onum`) + `text-wrap:pretty` + italic spoken lines; Dock → IBM Plex Sans weight hierarchy + timestamp chips; Immersive → IBM Plex Sans 15px/1.7, 26px room name with amber candlelight glow; Classic → IBM Plex Mono 13.5px/1.62, `calt` off + slashed `zero`. Shared: capped prose measure (`--lc-measure` ~60–66ch) + `tabular-nums` on aligned numbers. The chronicle stops hardcoding `font-serif` so it inherits the Mode font; JetBrains Mono added to the font load. | [x] `base.html` font load + JetBrains Mono; `game.html` `#feed`/`#chat-feed` drop `font-serif`; e-reader layout rule → Spectral-first family; per-mode typography section in `custom.css`. Test: `test_typography_fonts_loaded_and_feed_inherits_mode_font`. **Follow-ups:** self-host fonts (FOUT on parchment/CRT); density axis via a single `--lc-fs` rem base. |
| 60.2 | **Minimap de-boxing + Dock's textual inventory (closer emulation round 4).** Refreshed `lorecraft-export/` reference confirmed a pattern true across all five mockups: `#minimap`/`#inventory` are always bare content — the card border/rounding/title lives in the SURROUNDING template, never inside the swapped partial — so a mode that already wraps the include in its own card (dock, e-reader, immersive) was double-boxing. (a) `partials/minimap.html` now renders bare content only (no border/rounded/header); each mode's own wrapper supplies the title + refresh/full-screen-map buttons in its own idiom (Standard's card head, Dock's `dock-card__head`, E-reader's "THE KNOWN WAYS" kicker, Immersive's new `.immersive-map__head`, Classic's plain "── MINIMAP ──" text) — `mm-graph`/`mm-compass` gained a shared radial-gradient backdrop since they no longer inherit one from a card. (b) Dock's inventory switched from the rarity icon-grid to the reference's **textual row** — item name coloured by type + a small uppercase type tag (weapon/armor/item/coin) + weight, no icon glyph; `_item_icon` gained a `type` field reusing the existing data-driven classification. | [x] `minimap.html` stripped to bare content; `game.html`/`game_dock.html`/`game_ereader.html`/`game_immersive.html`/`game_classic.html` each own their minimap card chrome now; `.mm-graph`/`.mm-compass` radial-gradient backdrop; `.classic-map-box`/`.immersive-map__head`/`.mm-body-dock` CSS; `inventory.html` `.invlist`/`.invlist__row` (replacing `.inv-grid`/`.inv-slot`); `_item_icon` `type` field. Tests: `test_minimap_is_bare_content_no_double_box`, updated dock/right-rail tests for `invlist`. |
| 62 | **Layout/scheme axis split, Standard+Dock rebuild, full Stats pane (v0.54.0, backfilled to this ledger 2026-07-09 — shipped without a roadmap entry).** Per-mode typography (font faces, sizes, leading, features, measure, glow, timestamp chips) moved off the `theme-*` palette classes onto the `layout-*` classes, so picking a colour scheme repaints without reflowing text — a **Theme** is now Layout + Colour scheme. Colour schemes renamed/retuned to the design exports (Classic/Classic Amber → Mono Green/Mono Amber, usable under any layout; Terminal retuned to a green-tinted palette; per-scheme character colours match each export). Standard layout rebuilt to the export design (compact exits readout + ALSO HERE in the Location card, prompt+SEND moved into the chronicle card, one tabbed Inv/Quests/Stats right-hand card). Dock's right column now mirrors Standard's panes as a window-shade accordion. Every layout's map pane gained a `⇄` graph/compass toggle persisted via `/settings/appearance`. The Stats pane became the full "Score" readout (vitals meter bars, attributes, level/xp, trait chips, marks, reputation band, active effects) in both Standard and Dock. | [x] `preferences.py`, `custom.css` token/typography split, `game.html` (Standard) / `partials/game_dock.html`, `partials/stats_panel.html`; CI e2e fixes for the resulting DOM changes shipped separately as v0.55.3 (see the "Sprint 62-era" note in `CHANGELOG.md`). |
| 67 | **`webui-theming` agent skill + `MODE_DEFAULT_THEME` single-sourcing.** Added `.agents/skills/webui-theming/SKILL.md` (mirrored to `.claude/`/`.grok/`/`.codex/` per the repo's multi-platform skill convention) baking in the Layout × Color-scheme architecture so future agents don't have to re-derive it from a full-webui code dive. Writing it surfaced a real bug: `MODE_DEFAULT_THEME` (layout → default scheme) was hand-copied into two client-side JS literals (`base.html`'s `lcApplyTheme()`, `settings.html`'s `applyPreview()`) alongside the authoritative Python dict in `preferences.py`, with nothing keeping the three in sync — editing only the Python dict left both live-preview paths silently showing the *old* default scheme's colours. Fixed by injecting the dict once as JSON (`frontend.py` sets `templates.env.globals["MODE_DEFAULT_THEME_JSON"]`; `base.html` assigns it to `window.LC_MODE_DEFAULT_THEME`) and pointing both JS call sites at that global instead of their own literals — one source of truth, zero JS copies left to drift. | [x] `frontend.py` `MODE_DEFAULT_THEME_JSON` global; `base.html`/`settings.html` read `window.LC_MODE_DEFAULT_THEME`; skill docs updated to match. Test: `test_mode_default_theme_injected_as_single_source_for_client_js`. |
| 66 | **Multi-level map foundation (`map_z`).** Rooms gain `map_z: int = 0` (floor/level; additive column, defaults to ground floor — no migration risk). `build_map_data()` gains a `level: int | None` param (`None` = every floor, matching prior behavior; an int hard-filters candidates to that floor) so a floor that reuses the same `(map_x, map_y)` footprint as another floor no longer overlaps on the minimap/full-map plot. All player-facing call sites (sidebar minimap, post-command refresh, `/partials/minimap`, `/partials/map-full`, the transit minimap panel) now pass `level=current_room.map_z`. Threaded through the whole authoring path too: `RoomData` (validator), `import_world`/`export_world_document` (loader), changeset `create` (versioning), and the admin room editor (REST API, SPA form, TUI table column) all read/write `map_z`. `up`/`down` exits are unaffected — `map_z` only changes what's *drawn*, not traversal. | [x] `engine/models/world.py` `Room.map_z`; `db.py` sqlite compat-column migration; `world/validator.py`/`loader.py`/`versioning.py`; `rendering.py` `build_map_data(level=...)`; 5 call sites (`frontend.py` ×4, `transit/presentation.py`); admin `routers/world.py`/`routers/players.py`/`index.html`/`tui/app.py`; `main.py` `_room_snapshot` WS payload. Tests: `test_level_filters_out_rooms_on_a_different_floor_at_the_same_xy`, loader round-trip, changeset-create, admin API map_z coverage. **Deferred:** full-map level selector / dashed inter-level connection lines (`level=None` is already wired for whenever that UI lands); `world_content/world.yaml` still single-floor (content, not engine). |
| 59.5 | **Closer emulation round 1: E-reader layout, rarity inventory, compass sizing.** From the `lorecraft-export/` reference set: (a) a bespoke **E-reader layout** (renamed from `ledger`) — `partials/game_ereader.html`: left ledger (location + compass) · centre serif folio (chronicle + *Inscribe* prompt) · right **vertical tab rail** (Here/Quests/Pack/Stats → run look/journal/inventory/score); serif forced via `body.layout-e-reader`. (b) **Rarity-chip inventory** — `inventory_snapshot` adds a data-driven type chip (weapon ◆ / armour ▲ / misc ● / coin ¤) + stack weight; the panel becomes `.inv__row` icon rows with an "N items · wt/cap" header. (c) Fix the **compass ballooning on room change** — the minimap OOB now marks the partial's own sized root instead of nesting it in a bare `<div id="minimap">`. | [x] `game_ereader.html`; `game.html` four-way branch; `.ereader*`/`.inv__*` CSS; `_item_icon`; `mark_oob_swap` for the minimap OOB. Tests: `test_ereader_layout_renders_ledger_folio_rail`, updated inventory-rail + snapshot + layout-body-class tests. |
| 59.4 | **Review round: drop the extra chat input, fix chat wrapping, add the switchable compass exit-star.** From the `lorecraft-export/` design references (kept local, gitignored) feedback: (a) the classic chat pane's separate input is removed — chat is sent with `say …` on the main command line (the pane is display-only); (b) fix chat lines running together — HTMX positional OOB appends the OOB element's *child nodes*, so putting `hx-swap-oob` on the `.msg` dropped its block wrapper; now wrapped in an OOB *carrier* div so each line lands as a block; (c) a new **`minimap_style`** preference (`graph` default / `compass`) — the minimap partial renders both a discovered-rooms node-map and the phosphor **exit-star compass** (lit spoke = available exit, clickable to move; theme-token colours), toggled by a `minimap-<style>` body class. | [x] `feed_items.html` OOB carrier + shared `msg_body` macro; `game_classic.html` input removed; `minimap.html` dual view + `.mm-graph`/`.mm-compass` CSS toggle; `MINIMAP_STYLES` pref + settings select; `TestMinimapStyle`, `test_minimap_style_toggles_graph_vs_compass`, strengthened chat-carrier assertion. **Still open (larger follow-up):** closer palette/markup emulation of the `standard`/`dock`/`e-reader`/`immersive` reference front-ends. |

---

## Sprint 68 — Escort quests

**Goal:** let a quest/dialogue send an NPC along with the player instead of only ever standing
still, so a story can task the player with "guide me home" content. Reuses the shipped `follow`
command's movement cascade (Sprint 47) rather than building a second one, and reuses the
pluggable quest-condition/side-effect registries (Sprint 30.1) rather than adding a new mechanism
— per [`wishlist.md`](wishlist.md) → *Quests & puzzles*, dated 2026-07-08.

| # | Task | Status |
|---|------|--------|
| 68.1 | `NPC.following_player_id: str \| None` (additive column, default `None`, no migration risk — same pattern as Sprint 66's `Room.map_z`). DB-backed rather than `FollowService`'s in-memory player-follow dict, so the new quest condition can read it via `ctx.npc_repo` alone with no shared service reference in reach. `NpcRepo.escorting(player_id)` query. | [x] `engine/models/world.py`, `db.py` sqlite compat-column migration, `engine/repos/npc_repo.py`. |
| 68.2 | `FollowService.start_escort`/`end_escort` (co-located + not-already-escorting checks, narration) and the `PLAYER_MOVED` cascade extended to also advance any NPC escorting the mover: moves along if still co-located, otherwise quietly ends the escort with a "you've lost track of them" narration — no movement-gate re-run (NPCs don't have their own move command to re-run against), unlike player-to-player follow. First real emitter of the long-declared, previously-unused `GameEvent.NPC_MOVED`. | [x] `features/follow/service.py`. |
| 68.3 | `"start_escort"`/`"end_escort"` dialogue/quest side effects (npc_id string) on the shared `npc/side_effects.py` registry — the same registry quest-stage `branches[].side_effects` already use (Sprint 30.1), so escort start/stop can be authored identically from a dialogue choice or a quest branch. `"npc_following"`/`"npc_present"` quest condition types (explicit `npc_id`) on `quests/conditions.py`'s registry, mirroring the `npc_present` *command* condition's logic (`engine/game/command_conditions.py`) for quest stages. | [x] New `features/follow/conditions.py`, wired via the `follow` feature manifest's `register_fn` (mirrors the `npc_memory` package's registration pattern). |
| 68.4 | Unit tests: escort start/end (including the co-located and already-escorting rejections), the movement cascade (moves along; quietly ends when co-location is lost), both side effects via the shared registry, both quest conditions. | [x] `tests/unit/test_escort_quests.py` — 12 tests. **Deferred:** `world_content/world.yaml` has no escort-quest content yet (a "guide me home" dialogue/quest using Mira or a new NPC) — the mechanism ships without a playtestable in-game example, same content-vs-engine split as Sprint 66's `map_z`. |

---

## Sprint 69 — Scripting-engine world-building polish

**Goal:** make the Phase A scripting engine (weather fronts, triggers, spawns — branch
`scripting_engine`, v0.57–0.70) usable and consistent from a builder's chair, and fix the
correctness gaps found while play-validating it. Small, reviewable changes; each row is its own
commit + version bump.

| # | Task | Status |
|---|------|--------|
| 69.1 | **Ambient weather narration voice.** `WEATHER_CHANGED` announces the transition to players' feeds ("A light rain begins to fall."); the admin `POST /admin/clock/weather` endpoint now emits `WEATHER_CHANGED` (previously silent). | [x] v0.71.0 — `features/weather/handlers.py`, `webui/admin/routers/clock.py`, `tests/unit/test_weather_narration.py`. |
| 69.2 | **Admin teleport fires room enter/exit behaviour.** Teleport routed through a real `GameContext` + `PLAYER_MOVED` + `broadcast_command_effects`, so encounter triggers, quest/mark progression, `follow`, and the admin dashboard's live location fire instead of a silent field swap. | [x] v0.71.1 — `webui/admin/routers/players.py`, `tests/integration/test_admin_api.py`. |
| 69.3 | **Indoor vs. outdoor rooms.** `Room.indoor` flag (additive migration); ambient weather voice and storm fronts skip sheltered interiors; demo world marks 11 interiors indoor. | [x] v0.72.0 — `engine/models/world.py`, `db.py`, `world/{validator,loader}.py`, `features/weather/{handlers,fronts}.py`, `connection_manager.occupied_rooms()`. |
| 69.4 | **World-building agent skill.** `.agents/skills/worldbuilding/` (+ `.claude/` pointer): authoritative guide to rooms/NPCs/triggers/dialogue/weather/spawns and the generated `docs/scripting_api.md` vocabulary, so any "create an NPC / scripted event" prompt consults how scripting actually works. | [x] |
| 69.5 | **Zone-qualified teleport addressing.** Teleport accepts a bare room id/name **or** `zone.room` (e.g. `town.inner_vault`), resolving ambiguous names by `area_id`. No schema change (uses existing `area_id`); integer room IDs intentionally **not** pursued. | [x] v0.73.0 — `RoomRepo.resolve_ref`, `webui/admin/routers/players.py`, `tests/unit/test_room_ref_resolution.py`. |
| 69.6 | **Admin world-clock auto-refresh.** The admin dashboard's clock panel refreshes periodically so time/weather update without a manual reload. | [x] v0.74.0 — `webui/admin/index.html` (5s poll of the Clock tab). |
| 69.7 | **Admin World panel grouped by zone.** Room list in the admin World tab grouped by `area_id` instead of a flat list. | [x] v0.74.0 — `webui/admin/index.html` + `indoor` in `GET /admin/world/rooms`. |
| 69.8 | **Flag-family rename (Phase A tech-debt #1).** Collapse the `when:`-condition drift `flag_set`/`required_flags` + `flag_not_set`/`forbidden_flags` to the one §8.4 canonical name per capability — `actor_has_flag`/`actor_lacks_flag` — registered on both command and dialogue surfaces. Catalog overlap report now empty. Zero `world_content/` uses (code+test+docs only); validator-guarded. Left as-is: `set_flags`/`clear_flags` effects (no duplicate) and the separate quest-stage `{type: flag_set}` registry. | [x] `command_conditions.py`, `registry.py` enum, `dialogue_conditions.py`, `dialogue.py`, `world/validator.py`; regenerated `docs/scripting_api.md`; updated worldbuilding skill + dialogue docs. |

---

## Sprint 40 — Admin console live-refresh (done, v0.37.0, 2026-07-05)

**Goal:** Content tabs in the admin console (Issues, News, Help) should update on their own when the underlying data changes, instead of going stale until a manual Search/Refresh. Born from admin-console issue *"Admin UI does not auto-update"*.

**Approach — reuse the existing push channel, add nothing new.** The console already opens `/admin/ws` and fans out via `AdminBroadcaster`; it was only wired for `player_*`/`changeset_scan_done`. Content mutations now push a generic `{"type": "content_changed", "resource": "<tab>"}`.

| # | Task | Status |
|---|------|--------|
| 40.1 | Shared helper `webui/admin/routers/_common.notify_content_changed(state, resource)`; called after every issue/news/help create/update/delete (each mutation already funnels through the router's `_sync_yaml`). | [x] |
| 40.2 | Frontend: lift the tab-loader map to module scope (`TAB_LOADERS`), add `refreshIfActive(name)`, and handle `content_changed` in the WS `onmessage` — reload the named tab **only when it's the active one**. | [x] |
| 40.3 | Integration test: a subscribed broadcaster queue receives `content_changed`/`issues` after `POST /admin/issues`. | [x] |

## Sprint 41 — Registered issue components (done, v0.37.0, 2026-07-05)

**Goal:** Replace the free-text issue `component` field with a **registered, strict closed set** surfaced as a dropdown, so components are consistent and filterable. Born from admin-console issue *"Issues components should be a list."*

**Design:** coarse, structural taxonomy (not per-feature) — `engine`, `webui/player`, `webui/admin`, `admin-tui`, `features`, `docs`, `infra`. Single source of truth in `lorecraft/content/components.py`; the empty value ("unassigned") is always allowed.

| # | Task | Status |
|---|------|--------|
| 41.1 | `content/components.py`: `ISSUE_COMPONENTS` + `is_valid_component()`. | [x] |
| 41.2 | API: `GET /admin/issues/components` (serves the list to the dropdown, registered before `/issues/{issue_id}` so the literal path wins); validate `component` on `POST`/`PUT /admin/issues` (unknown → 400). | [x] |
| 41.3 | Frontend: create-form and filter `component` inputs → `<select>`s populated once from the endpoint (cached). | [x] |
| 41.4 | Tests: endpoint returns the set; unknown component rejected; unit tests for `is_valid_component`. | [x] |

> **Interaction with in-game reports:** the `report` command keeps `component="player-report"` (and the matching tag). It uses the content path, which is deliberately *not* API-validated, so player reports are unaffected; those issues store and display their component unchanged. `player-report` is intentionally **not** in the registered structural set — filter such issues by their tag.

## Sprint 42 — Issues tab filter/sort + player-report live-refresh (done, v0.38.0, 2026-07-05)

**Goal:** Make the admin Issues tab usable at volume and truly live. Two dogfooding asks: (1) hide resolved/deferred by default with a way to choose what's filtered out, and sort by priority or date; (2) fix that player-filed reports didn't live-update the tab.

**Filter/sort (client-side).** The tracker is low-volume, so the tab fetches the full list and filters + sorts in the browser for one coherent model: default-hide `resolved`+`deferred` via a **"Hide status" checkbox group** (any status toggleable), a **priority** filter dropdown, and a **sort** selector — *Priority* (priority-first, newest-updated tiebreak), *Recently updated*, *Recently created* (date-first, priority tiebreak). Header shows `N shown · M hidden`; hide/sort prefs persist in `localStorage`. Replaced the old free-text status/priority filter inputs.

**Live-refresh for player reports.** The `report` command created issues via the content path (no `content_changed` push), so an open Issues tab stayed stale. Added `GameEvent.ISSUE_FILED`, emitted by the command; `main.py` forwards it to the admin broadcaster as the same `content_changed`/`issues` message the admin routers send. Now player reports (and any bus-emitting issue source) live-refresh like admin edits.

| # | Task | Status |
|---|------|--------|
| 42.1 | Client-side default filter (hide resolved/deferred), "Hide status" checkbox group, priority filter, sort selector (priority / recently-updated / recently-created); count + `localStorage` persistence. | [x] |
| 42.2 | `GameEvent.ISSUE_FILED` emitted by `report` (one-liner + wizard paths); `main.py` forwards to the admin broadcaster as `content_changed`/`issues`. | [x] |
| 42.3 | Tests: report emits `ISSUE_FILED` (unit); admin **Issues** browser e2e (`tests/e2e/test_admin_issues.py`) for default-hide, sort, and out-of-band live update; shared admin e2e fixture/login helper moved to `tests/e2e/conftest.py` with content-YAML isolation. | [x] |

## Sprint 43 — Session record & playback (advanced testing) — ✅ complete

**Goal:** record real/scripted player command streams and replay them — one scenario across **N
simulated players**, or a mix concurrently — for regression (golden audit-trail diff), load
(p50/p95/p99), and soak/fuzz. Mostly a **consolidation** of pieces that already exist: the audit
log (recording), the `VirtualPlayer`/`SimulationServer` harness (playback), `test_load.py` (N-player
fan-out + metrics), and the seeded-`GameRng` audit-regression determinism. **Full plan:
[`session_replay.md`](archive/session_replay.md).** Supersedes the Backlog `lorecraft.tools.simulation` note.

| # | Task | Status |
|---|------|--------|
| 43.1 | **Phase 1** — `record` from the audit log → scenario JSON; single-actor `replay` via one `VirtualPlayer`; assert the normalised audit trail against a golden (data-drives `test_audit_regression.py`). | [x] `lorecraft.tools.session_replay`: versioned scenario JSON (logical actors, `{t, actor, raw}`, `world_yaml`/`rng_seed` stamps), `record_scenario()` + `record` CLI off any audit DB, shared `normalize_events()`. Replay: `tests/simulation/replay.py` (fresh `VirtualPlayer`, fast timing); `test_audit_regression.py` now data-driven off checked-in `scenarios/golden_path.json` with a **checked-in golden trail** (`golden_path.audit.json`; regen via `LORECRAFT_UPDATE_GOLDENS=1`). Sim-server factory takes `rng_seed`. Unit + sim suites green. (v0.39.4) |
| 43.2 | **Phase 2** — N-player fan-out (`--players N`) reusing the load-test percentile report; replace the fixed `test_load.py` script with recorded traffic. | [x] `fan_out_scenario()` in `tests/simulation/replay.py` maps a single-actor scenario onto N fresh concurrent `VirtualPlayer`s; report assembly (`percentile`/`latency_report`) moved to `lorecraft.tools.session_replay` (unit-tested, CLI-reusable). `test_load.py` now replays `scenarios/load_default.json` (the old read-heavy loop) and `LORECRAFT_LOAD_TEST_SCENARIO` points it at any recorded session — verified with `golden_path.json` @5 players. Same report shape/knobs (`_PLAYERS`/`_JITTER_MS`/`_JSON`); numbers match the post-WAL baseline (p50 ~56 ms @10). (v0.39.6) |
| 43.3 | **Phase 3** — mixed concurrent scenarios (`--mix`), longer soak runs, and an opt-in `simulation`-marked CI job. | [x] `mix_scenarios(server, scenarios, repeats=…)` replays distinct recorded sessions concurrently, each looped for soak, over a shared `_run_concurrent` runner (fan-out is now the same-script case); report = shared `percentile_summary()` + mix context. New `test_soak.py` mixes golden-path + load-default (quick 2-repeat default; `LORECRAFT_SOAK_REPEATS` for real soaks — verified @25 = 325 commands, p99 ~30 ms). CI's existing `simulation` job gains a `workflow_dispatch` `soak_repeats` input for opt-in longer runs. (v0.40.0) |

## Sprint 44 — Weather-driven world effects — ✅ complete

**Goal:** the weather/season state machine mostly flavored descriptions — make it drive a real
mechanic. From [`wishlist.md`](wishlist.md) → *Weather-driven world events*.

**Design note (corrected during build):** weather is **global clock state affecting rooms by terrain**,
a natural fit for the **§3.5 modifier resolver** (read-through, like room auras / terrain gating) —
*not* the Sprint 39 timed-room-effect primitive (that is for *localized, TTL* effects, and would mean
materializing a redundant effect row per outdoor room on every weather change). Each behavior keeps one
owner: the clock owns weather, terrain defs own terrain, the resolver composes them.

| # | Task | Status |
|---|------|--------|
| 44.1 | `WeatherTerrainModifierSource` (`features/weather/modifiers.py`): harsh weather (`COLD_WEATHERS` + thunderstorm/heavy_rain) subtracts a penalty from a skill-gated terrain's `required_skill`, read through `resolve_for`. So a **blizzard can push a marginal traveller below a mountain pass's survival requirement** via the *existing* movement terrain gate — no new movement code, no materialized room effects. Registered at module import; unit-tested (penalty in harsh weather on skill-gated terrain, none in clear weather or on sheltered terrain). | [x] |

## Sprint 46 — Item discovery journal — ✅ complete

**Goal:** the Sprint 25.3 `journal` records places visited, people met, lore learned, and active
quests — but **not items**. Add discovered-item tracking so finding a distinct item is a recorded
exploration payoff (pillar #1).

| # | Task | Status |
|---|------|--------|
| 46.1 | Track first discovery per item *definition* (not per instance): `Player.discovered_items`, set on first `take`/`examine` — same pattern as `met_npcs` (set on first `talk`). | [x] `Player.discovered_items` + `SaveSlot.discovered_items` (save/load parity); `_record_item_discovery()` in `inventory/service.py`, hooked from `_emit_item_taken` (all take paths) and `examine` — per-definition (`item.id`), idempotent. Additive sqlite migrations for both tables. (v0.40.5) |
| 46.2 | `journal` gains an "Items discovered" section (names, matching the journal's existing read-only style); unit tests for first-discovery tracking + journal output. | [x] `JournalService._show_items` between people-met and lore, same read-only style ("Items discovered: …" / "none yet."). 4 new unit tests (take-once idempotent, examine-without-take, journal shows names, empty state). |

## Sprint 47 — Follow command (social movement) — ✅ complete

**Goal:** `follow <player>` — when the target moves, followers move with them; `unfollow` stops.
Overt, not stealthy: both sides see narration. The lightweight slice of the wishlist's *Player
groups / parties* idea, and a natural pairing with transit (board the ferry together) without
building parties.

| # | Task | Status |
|---|------|--------|
| 47.1 | Follow state + movement hook: follower auto-moves on the target's movement event, re-running the standard movement gates (terrain/skill/hidden/locked exits) — a failed gate breaks the follow with a message to both sides. Chains allowed (A→B→C), cycles rejected. | [x] New Tier 2 `follow` feature: `FollowService` holds an **in-memory** follow graph and subscribes to `PLAYER_MOVED`; co-located connected followers are re-moved through the standard `MovementService.move` gates via a `dataclasses.replace` sub-context. Gate failure (detected by not reaching the target's room) breaks the follow and notifies both sides; chains cascade because each auto-move emits its own `PLAYER_MOVED`; cycles rejected at follow-time. Needed a generic engine seam — `GameContext.pending_deliveries` (deferred async WS pushes drained by `broadcast_command_effects`), since the event bus is synchronous but followers need live pushes. (v0.40.6) |
| 47.2 | `follow <player>`/`unfollow` commands (movement feature `commands.py`); narration both sides ("X begins following you."); bare `follow` shows current status; tests incl. a multi-room chain and a gate-failure break. | [x] `follow`/`unfollow` verbs (movement category); both-sides narration on follow/unfollow (target push); bare `follow` shows who you follow + who follows you. 5 unit tests (follower moves, A→B→C chain cascade, self/absent reject, cycle reject, gate-failure break) + a **live two-player WS check** (follower's socket gets "You follow X east." + panel refresh). |

## Sprint 48 — Scavenger hunt events (design-first) — ✅ complete

**Goal:** a scheduled, time-boxed world event: a themed set of items/clues is placed across rooms
and players hunt them for a reward (coins, a collectible mark, lore). Exploration-pillar event
content on existing primitives (scheduler + world clock for the window, item spawns, flags/journal
for progress, news/feed for announcement). The simplest, *non-instanced* slice of the wishlist's
*Instanced minigames / scenarios* idea.

| # | Task | Status |
|---|------|--------|
| 48.1 | **Design spec first** — YAML event definition (item/clue set, spawn room pools, cadence or admin trigger, duration, completion rule, reward), announcement surface (news + feed), and per-player progress storage (flags vs. a small table). No implementation until reviewed. | [x] Spec: [`scavenger_hunt.md`](archive/scavenger_hunt.md). Decisions: **flags** for per-player progress (persist via SaveSlot, journal-visible, no new table); **news items** for announcements (synchronous DB — sidesteps the async-from-scheduler broadcast problem, no live feed ping in v1); YAML defs loaded into an in-memory registry (weather/terrain pattern); completion = "find all" (count variant deferred); reuses scheduler / `ItemLocationService.spawn` / `ITEM_TAKEN` / `LedgerService` / `GameRng` — no new Tier 1 mechanism. (v0.40.7) |
| 48.2 | Implement as a Tier 2 feature package (`features/…` + manifest, auto-discovered) per the spec; content-lint for event YAML references (item keys, room pools). | [x] `features/hunts/` (auto-discovered): `models.py` (Pydantic `HuntDef`/`HuntsDocument`, registry, `lint_hunts`), `service.py` (`open`/`close`/`ITEM_TAKEN` find + reward/`SCHEDULED_JOB_DUE` open-close), `commands.py` (read-only `hunts` verb). Progress in player flags, announcements as news items, coins via ledger. `LORECRAFT_HUNTS_YAML_PATH` config; loaded into the registry at startup. Wired into `ServiceContainer`/`register_all_commands`/`main`. (v0.40.8) |
| 48.3 | Ashmoore example hunt + tests: event opens/closes on schedule, item found → progress → reward, audit-regression stays stable. | [x] `world_content/hunts.yaml` — the Harvest Trinket Hunt (3 trinket items added to `world.yaml` as definitions only) across village_square/market/inn. 10 unit tests (open spawns clues, find→progress→reward+lore, no double-reward, close despawns, scheduled open/close, content-lint clean/dirty, dup-id + negative-coin validation, shipped-content lints against the real world). Audit-regression golden **unchanged** (definitions aren't placed by default). |

## Sprint 49 — Encumbrance & analytics dashboard (Tier 2 + observability) — ✅ complete

**Goal:** Ship inventory encumbrance (weight capacity, gating) as a Tier 2 feature, and build an admin analytics dashboard surfacing p50/p95/p99 operation latency (Sprint 35.3 data) with player activity heatmaps and an operation timeline. Together: player progression friction + ops visibility.

**Reconciled (2026-07-06):** the **encumbrance model already existed** as the `encumbrance` feature (`Item.weight`, `resolve_carry_capacity`/`total_carried_weight`/`encumbrance_band` composing the §3.5 modifier resolver, strength-scaled base) with `take` already gated on overload ("You can't carry any more weight.") and fatigue draining by band — so 49.1 was largely done. The design also gates **carrying** (can't pick up more than you can haul), which is kept over the roadmap's speculative "too heavy to *move*" (movement-weight gating would be punishing and duplicate the take gate). This sprint therefore delivered the genuinely-missing pieces: the **weight UI** and the **analytics dashboard**.

| # | Task | Status |
|---|------|--------|
| 49.1 | **Encumbrance model** — weight, carry capacity, bands, overload gate. | [x] **Already shipped** as the `encumbrance` feature (`rules.py`) + `Item.weight`; `take` gates on overload; fatigue drains by band. No change needed beyond the snapshot helper below. |
| 49.2 | **Weight UI** — player sees current/max carried weight + band on the inventory panel. | [x] `encumbrance_snapshot()` (current/capacity/band) + `encumbrance_snapshot_for()` wired into all three inventory renders (game page, HTMX command OOB swap, `/partials/inventory`); weight line in `inventory.html`, colored by band (amber/red). Verified live ("WEIGHT 0.0 / 80.0"). *(The roadmap's "too heavy to move" movement gate was dropped in favour of the existing take-gate — see reconciliation note.)* |
| 49.3 | **Analytics dashboard** (`/admin/analytics/dashboard` + admin console tab): p50/p95/p99 latency by operation, operation timeline (recent ops w/ duration), player-activity-by-hour heatmap. | [x] New `operation_timeline()` + `activity_by_hour()` analytics queries; `/admin/analytics/dashboard` one-call endpoint (Observer auth, `range`/`timeline_limit`); new **Analytics tab** in the admin console (latency table, CSS-bar heatmap, recent-ops table — no charting lib). |
| 49.4 | Tests. | [x] Timeline (order/limit) + heatmap (24-bucket density) analytics unit tests; dashboard endpoint schema + auth integration tests; `encumbrance_snapshot` unit test; audit-regression golden unchanged. (v0.40.9) |

> **Rationale:** Encumbrance ties inventory to character progression; the analytics dashboard keeps ops/player-health visible post-launch. Both low-risk over stable foundations (inventory, traits, audit).

## Sprint 50 — E2E browser test coverage (multiplayer & UX layers) (done, v0.40.13–v0.41.1, 2026-07-06)

**Goal:** Expand `tests/e2e/` coverage from single-player smoke tests to **multiplayer/WebSocket paths**,
**auth flows**, and **interaction seams** (Alpine/HTMX). Existing e2e tests cover the happy path
(create→move→take) and basic UI (map modal, mobile tab bar). The gaps: **zero coverage of the WS
multiplayer layer** (`broadcast_to_room`, `feed_append`, `player_joined`/`player_left`, cross-client
state updates) and **auth edge cases** (wrong password, unknown username, session reload). These are
high-risk, expensive to verify manually, and only testable end-to-end.

**Guiding principle:** a test belongs in e2e *only if* it depends on real **DOM / HTMX swaps**, **Alpine
reactive state**, or **WebSocket-driven cross-client updates**. Pure command→response correctness
(economy math, parser edge cases) stays in `tests/integration/` — e2e is expensive (real Chromium +
real uvicorn socket, serial). **Full plan: [`e2e_test_plan.md`](e2e_test_plan.md).**

Rollout order: harness prerequisites first (H1–H3), then Priority 1 (multiplayer, the marquee gap),
then P2 (auth), then P3–P4 (interaction + panels), finally P5 (flaky reconnect tests, last with
generous timeouts).

**Status: complete (v0.41.0 → v0.41.5).** Harness (H1–H3) + **15 new e2e tests** shipped: P1 (5,
multiplayer/WS), P2 (5, auth), P3 (4, interaction), P4 (3, panels), P5 (1, reconnect). The three
subtasks first deferred for missing world content / harness capability were then **addressed for
real** (v0.41.5) rather than fabricated around:
- **P3.3** (locked door → key): added a **Vault Hall → Inner Vault** locked-exit area off the
  locksmith gallery, with a matching **Good Key** and non-matching **Bad Key** (obvious names) — real
  world content demonstrating the exit lock/unlock mechanic.
- **P4.2** (equipment): added an **Equippable Helmet** (`slot: head`, `wearable`) in the blacksmith
  forge — closing the "demo world can't exercise equipment" gap; the wear/remove flow moves it out of
  and back into the inventory panel.
- **P5.1** (reconnect): confirmed `set_offline(True)` doesn't sever an open WebSocket, so added a
  clearly-named client debug hook (`window.Lorecraft.debugDropSocket()`) to force a real drop, and
  test that the socket **auto-reconnects and resumes live delivery**. Backfilling messages *missed
  during* an outage is intentionally out of scope — `say`/room narration are transient (not audited to
  the room feed), so replaying them would need durable chatter persistence, a separate design decision.
All new content placed off the audit-regression golden path (golden unchanged); full suite 980 +
e2e 36 green.

| # | Task | Status |
|---|------|--------|
| 50.1 | **Harness H1: two-player fixture & shared helpers.** New `second_page` fixture yielding an independent browser context in the same live server; extract duplicated `_create_character` / `_send_command` helpers from the three existing e2e test files into a centralized `tests/e2e/_helpers.py` (precondition: rotten duplication will diverge otherwise). | [x] Shared helpers centralized in `tests/e2e/_helpers.py` (`create_character`, `send_command`, `send_command_via_enter`, `enable_separate_chat`, `navigate_to_locksmiths_gallery`); `second_page` fixture added to conftest; all existing e2e test files updated to use shared helpers; existing e2e tests verified passing. (v0.41.0) |
| 50.2 | **Harness H2: WS-settled signal.** Document and implement a pattern for multiplayer assertions: `page.wait_for_function(...)` on the receiver's DOM, never synchronous asserts after a cross-client action (WS pushes are async; the next event loop turn is when B's panel updates after A acts). Candidate signal: status dot gaining `bg-emerald-500` in `ws.onopen`, or `page.wait_for_function` on `window`-exposed WS state. | [x] The status dot is server-rendered already carrying `bg-emerald-500`, so it can't signal connection — instead added a minimal `window.Lorecraft.isConnected()` accessor (real WS flag set in `ws.onopen`/`onclose`, also useful for console debugging). `wait_for_ws_connected()` polls it; multiplayer pattern documented in _helpers.py module docstring. (v0.41.0) |
| 50.3 | **Harness H3: offline toggle** (only for P5.1 reconnect test). Playwright `context.set_offline(True/False)` to exercise `app.js` reconnect + `reconnect_sync` backfill. Kept separate because it is timing-sensitive. | [x] `set_offline(page, offline)` added, but **`set_offline(True)` does not sever an already-open WebSocket in this Chromium** (`window.Lorecraft.isConnected()` stays `true` for the whole offline window). Superseded for reconnect testing by `drop_ws()` + the `debugDropSocket()` client hook, which forces a real drop (v0.41.5). See P5 (50.8). |
| 50.4 | **Priority 1 — Multiplayer / WebSocket (`test_multiplayer_realtime.py`):** P1.1 `say` propagates to another player; P1.2 `player_joined` increments "Here Now"; P1.3 `player_left` decrements; P1.4 dropped item becomes visible; P1.5 observer sees third-person narration form (closes the 2026-07-04 actor-only test's other half). | [x] All 5 tests passing. Uses `wait_for_ws_connected()` so the receiver is connected before the actor broadcasts, then asserts on the receiver's DOM. Assertions are username-based on `#players-online` (P1.2/P1.3) rather than `#player-count` — the count is server-rendered and not WS-refreshed, and `village_square` always holds the unconditional `player-2` seed body. (v0.41.0) |
| 50.5 | **Priority 2 — Auth & session lifecycle (`test_auth_flows.py`):** P2.1 log in via the Log In tab (existing char); P2.2 wrong password rejected (401); P2.3 unknown username doesn't silently create an account (404); P2.4 session persists across reload (cookie); P2.5 unauthenticated `/game` redirects to `/lobby`. | [x] All 5 passing (v0.41.1). Reconciled to actual server behavior: the browser login form re-renders the lobby with an inline error + **400** (not 401/404 — those are the JSON `/auth/*` codes), and unauthenticated `/game` returns **401** (not a `/lobby` redirect; `allow_query_player_id` defaults off). Tests assert the security property (stays on lobby / never reaches `/game`). Added `login_character` helper + `new_page` cookie-isolated context factory fixture. |
| 50.6 | **Priority 3 — Interaction flows (extend `test_gameplay_flows.py`):** P3.1 command history ArrowUp/ArrowDown multi-entry + index reset; P3.2 full dialogue traversal + dismiss; P3.3 locked door → key golden path (multi-step regression anchor); P3.4 invalid command robustness. | [x] All 4 passing. P3.1/P3.2/P3.4 (v0.41.2); **P3.3 (v0.41.5)** now backed by real content — a **Vault Hall** (off the locksmith gallery, east) with a locked east exit (`key_item_id: good_key`) to the **Inner Vault**, holding a matching **Good Key** and non-matching **Bad Key**. Test drives the full mechanic: locked with no key → Bad Key rejected → Good Key unlocks → pass through. |
| 50.7 | **Priority 4 — Panel rendering (`test_panel_rendering.py`):** P4.1 minimap current-room highlight moves on movement; P4.2 equipment/wield/wear/unwield flow; P4.3 feed autoscroll + top/bottom controls. | [x] All 3 passing. P4.1/P4.3 (v0.41.3); **P4.2 (v0.41.5)** now backed by a real **Equippable Helmet** (`slot: head`, `wearable`) in the blacksmith forge. Test: `take` → helmet in inventory; `wear` → leaves the loose inventory panel; `remove` → returns. Closes the "demo world can't exercise equipment" gap. |
| 50.8 | **Priority 5 — High-value but flaky (P5.1 reconnect test).** WS reconnect / resync backfill: A and B connected; set B offline; A acts (missed); set B online; `app.js` reconnect + `reconnect_sync` / `feed?since=` should backfill. Assert (with generous polling) B's feed eventually contains the missed line. Implement last with long `wait_for_function` timeouts. | [x] **Reframed & passing (v0.41.5).** `context.set_offline(True)` doesn't sever an open WebSocket here (verified — `isConnected()` stays true, so a "missed" message is a false positive), so the test forces a genuine drop via a clearly-named client debug hook `window.Lorecraft.debugDropSocket()` and asserts the socket **auto-reconnects and resumes live delivery** (`test_reconnect.py`, stable over repeated runs). **Backfill of messages missed *during* the outage is intentionally out of scope:** `say`/room narration are transient — not written to the room audit feed (verified: a reload doesn't show a room-mate's `say`), so neither a reload nor `reconnect_sync` can replay them. Durable chatter replay would be a separate design decision (persist room broadcasts), not a bug this test asserts. |

## Sprint 51 — Four more analytics widgets (observability) (done, v0.42.0, 2026-07-06)

**Goal:** Round out the Sprint 49 Analytics tab with the four widgets requested but not yet built: a timeline chart, a top-commands bar chart, NPC interaction stats, and a quest completion funnel. Built on a `webui`-scoped branch, architected so any one widget can be dropped later without touching the others.

**Discovery mid-sprint:** two of the four requested widgets sit on analytics functions (`npc_interaction_counts`, `quest_completion_counts`) whose backing data was **never actually populated** — `AuditEvent.target_id` was never set on any audit record, and quest lifecycle events (`QUEST_UPDATED`/`COMPLETED`/`FAILED`) are only ever queued on the in-process event bus, never persisted as audit rows. Their existing unit tests only ever exercised fabricated `AuditEvent` rows, masking the gap.

| # | Task | Status |
|---|------|--------|
| 51.1 | **Timeline chart** — SVG scatter/line of command handler latency over time. | [x] `renderTimelineChartWidget`, built from the existing `operation_timeline()` feed (already real data; no backend change). |
| 51.2 | **Top commands bar chart.** | [x] `renderTopCommandsWidget`, wired to the existing (already real, previously unused by the dashboard) `top_commands()` — folded into `/admin/analytics/dashboard` as `top_commands`. |
| 51.3 | **NPC interaction stats** — required fixing the `target_id` gap first. | [x] `CommandEngine` now resolves the parsed command's target/object/recipient id against `NpcRepo` and threads it into `COMMAND_EXECUTED`/`BLOCKED`/`FAILED` audit records (only when it names a real NPC). `renderNpcInteractionsWidget` + `npc_interactions` dashboard key. Verified live: `talk mira` in the Ashmoore dev world → `npc_interactions: [{"npc_id": "innkeeper", ...}]`. |
| 51.4 | **Quest completion funnel** — the audit-log path (`quest_completion_counts`) is a dead end (see discovery above); sourced from live game state instead. | [x] New `analytics.quest_completion_funnel()` reads `PlayerQuestProgress` rows (started/completed/failed/in-progress per quest) directly from the game DB. `renderQuestFunnelWidget` + `quest_funnel` dashboard key + standalone `GET /admin/analytics/quest-funnel`. Verified live (`investigate_lights` funnel populated after a real quest-start dialogue choice). |
| 51.5 | Tests + architecture for removability. | [x] Each of the 4 widgets is a self-contained `{id, render(data)}` entry in `ANALYTICS_WIDGETS`, delimited by `<!-- WIDGET --> ... <!-- /WIDGET -->` HTML comments — delete a widget's block + render function + registry line to drop it without touching the others. Unit tests: engine `target_id` resolution (NPC vs. non-NPC target), `quest_completion_funnel`. Integration test: dashboard payload schema. Full suite + simulation (audit-regression golden) unaffected. |

> **Rationale:** The `target_id` fix is a genuine, narrowly-scoped bug fix (foundation/observability, not new feature surface) uncovered by trying to build the NPC widget honestly rather than against dead data. The quest-audit gap (`quest_completion_counts`) is intentionally left unfixed — tracked here as a known gap rather than expanded into this sprint's scope. Merged after the Sprint 50 e2e work (rebased for version/changelog).

---

# Performance & scaling band (Sprints 35–38) — ✅ 35–37 complete; 37.1 + 38 deferred to wishlist

**Goal:** Establish performance telemetry, capture a baseline before any optimization, then implement high-ROI single-process optimizations. Measure-first paid off twice: **Sprint 36** (parser entity-resolution, 9.3×) and the **fsync/WAL finding**. The dominant cost across every path was fsync-per-commit on the single SQLite writer; **SQLite WAL mode (37.4)** fixed it broadly — `scheduler_tick@50jobs` **1410 → 48 ms (~29×)**, load-test p50 **254 → 58 ms**. Consequently **37.1 (scheduler-commit batching)** and **all of Sprint 38 (concurrency/threading gate)** were **deferred to [`wishlist.md`](wishlist.md)** — the wall was fsync serialization, not CPU, so threads wouldn't help and WAL already removed most of the commit cost. Revisit only if a *post-WAL* realistic-load test shows a hard single-process wall.

## Sprint 35 — Performance telemetry & baseline — ✅ complete

| # | Task | Status |
|---|------|--------|
| 35.1 | Baseline micro-benchmark harness `scripts/perf_baseline.py` (p50/p95/p99 per operation vs. the Ashmoore world). | [x] Revealed parser entity-resolution was O(visible entities): `examine` parse 0.7 ms → 4.8 ms @25 items → 17 ms @100 items. |
| 35.2 | Structured perf logging: `time_operation(name)` ctx-manager; instrument parse/condition/commit/scheduler/broadcast (warn >50 ms). | [x] `time_operation(name, *, warn_ms=50.0)` in `observability.py`; all five sites instrumented. |
| 35.3 | Analytics API `/admin/analytics/performance` — p50/p95/p99 by operation from audit `duration_ms` payloads. | [x] `CommandEngine` stamps a per-operation `perf` breakdown on each `COMMAND_EXECUTED`; `analytics.operation_latency_percentiles` + endpoint, unit + e2e tested. |

## Sprint 36 — Parser entity-resolution scaling — ✅ complete

**Outcome:** `parse:examine@100items` **16.92 → 1.82 ms p50 (9.3×)**, p99 tail gone, flat in inventory size. Profiling drove the fix: DB round-trips (36.1) then full-`Item` ORM materialization (36.2), not the matcher scan — so 36.2 became a column projection and 36.3's memoization gate came back negative.

| # | Task | Status |
|---|------|--------|
| 36.1 | Eliminate per-item DB round-trips in `GameContext.get_inventory()` (batch-load rows). | [x] `ItemRepo.get_many(ids)`; `@25items` 4.79 → 1.47 ms, `@100items` 16.92 → 3.01 ms. |
| 36.2 | ~~Index visible entities by name+alias~~ → **column projection** (full-`Item` materialization was ~72% of parse). | [x] `ItemRepo.name_index(ids)` = `select(Item.id, Item.name, Item.aliases)`; `@100items` 3.01 → 1.82 ms, p99 tail collapsed ~22 → ~1.9 ms. |
| 36.3 | Re-measure; add LRU memoization only if still material. | [x] At ~1.8 ms p50 / ~1.9 ms p99, resolution no longer material — **no memoization added**. |

## Sprint 37 — Pool tuning, load test & the WAL win — ✅ complete (37.1 → wishlist)

| # | Task | Status |
|---|------|--------|
| 37.2 | Connection-pool tuning knobs (`pool_size`/`pool_recycle`) — networked backends only. | [x] `db_pool_size`/`db_pool_recycle` + env vars; documented, unit-tested. |
| 37.3 | Load test (`tests/simulation/test_load.py`): N concurrent `VirtualPlayer`s, p95/p99 before/after. | [x] Lockstep baseline p50 254 → 58 ms after WAL; p99 475 → 83 ms. Fixed a pre-existing sim-harness break. |
| 37.4 | **SQLite WAL mode** (`journal_mode=WAL` + tunable `synchronous`). | [x] `db.configure_sqlite_engine`; `scheduler_tick@50jobs` 1410 → 48 ms (~29×). Documented, unit-tested. |
| ~~37.1~~ | ~~Batch scheduler execution into one commit/tick~~ → **[`wishlist.md`](wishlist.md)** | Marginal after WAL (50 jobs/tick ≈ 48 ms). |

---

## Sprint 39 — Timed room effects (Tier 1 engine primitive) — ✅ complete

**Goal:** A general, content-agnostic primitive for applying a **time-limited effect to a room** — puzzle timers, occupant auras, weather hazards. **Design decided: reuse the Sprint 19 `ActiveEffect`/`EffectService` timed-effect primitive** (`entity_type="room"`, `entity_id=<room_id>`) — no new model/table/scheduler. Two mechanics: room-state effects write the one authoritative `Exit` state (movement unchanged); occupant auras via a new `RoomAuraModifierSource` (§3.5).

| # | Task | Status |
|---|------|--------|
| 39.1 | **Design spec** — room-effect hook interface (`on_apply`/`on_expire` for room-state; auras as a room-scoped `ModifierRegistry` source), written into [`engine_core.md`](engine_core.md) §3.9. | [x] §3.9 spec: room-state effects write the authoritative `Exit` (undo in `payload`, no read-through fork); auras are `RoomAuraModifierSource`; engine gains no exit awareness — "open the gate" is a Tier 2 `EffectDef` hook. Each behavior keeps one owner; no new model/table/scheduler. |
| 39.2 | Room-effect application + expiry on the existing primitive; `on_expire` reverses room-state. | [x] `on_apply`/`on_expire` hooks on `EffectDef`; `apply()` fires `on_apply` after flush; expiry sweep fires `on_expire` before delete, each isolated in a savepoint (failing hook rolls back only itself, row kept for retry). Unit-tested. |
| 39.3 | Read/gate points: modifier resolution consults `active_for("room", room_id)`; a plate/mechanism applying a timed gate is the first content example. | [x] `RoomAuraModifierSource` (shares `_effect_modifiers`) auto-picks-up a player's room auras; movement unchanged (effect writes the `Exit`). Content: `features/exploration/room_effects.py` `passage_open` EffectDef + `open_timed_passage` mechanism side-effect. Integration-tested. |
| 39.4 | Tests: expiry closes a gate; aura modifies a resolved value; audit-regression stable; content-lint of room-effect keys + directions. | [x] Gate open→relock, aura modify+lift, `on_expire` savepoint isolation, `on_apply`-raise rollback covered; audit-regression stable; `world/validator._validate_open_timed_passage` shape-lint + tests. |

---

## Sprint 45 — Split the social/chat feed from the narrative feed (opt-in) — ✅ complete

**Goal:** the single biggest client-UX takeaway — chatter must never scroll room/quest/action output out of view. Split narrative feed from social/channel feed into two panes, as a toggleable player option. **Full plan: [`chat_feed_split.md`](archive/chat_feed_split.md).**

| # | Task | Status |
|---|------|--------|
| 45.1 | **Phase 1 (headless)** — GameContext chat channel (`say_chat`/`tell_room_chat`); `command_result.chat_messages` + broadcast `message_type:"chat"`; `separate_chat` preference. | [x] v0.40.3 — default UX unchanged (both render paths degrade the new type into the single feed until Phase 2). 7 unit tests. |
| 45.2 | **Phase 2 (browser)** — `app.js` dual-pane routing, `game.html` pane, styling, settings toggle; two-player e2e. | [x] v0.40.4 — `#chat-pane`/`#chat-feed` (rendered only when `separate_chat` is on); WS + HTMX routing; two-player e2e (`test_chat_feed_split.py`). |
| 45.3 | **Phase 3** — global channels (shout/tell); colored/prefixed per-channel tags; per-channel mute; mobile tab-collapse. | [x] **Completed by Sprint 52 (v0.45.0):** `tell` P2P + the `newbie` P2ALL channel (a distinct `shout` folded into named P2ALL channels by design); colored/prefixed tags (52.7); the interim v0.40.10 blanket `mute_chat` superseded by real per-channel subscriptions with a server-side drop (52.5/52.8). *Cosmetic mobile tab-collapse polish left as a standalone backlog item.* |

---

## Sprint 52 — Global channels & the channel framework — ✅ complete (v0.45.0)

**Goal:** Add the global chat channels the Sprint 45 split was built to carry; finish chat Phase 3. **Design:** two orthogonal axes — a fixed `ChatScope` enum (`P2P`/`P2ROOM`/`P2ALL`, mapping onto the three `ConnectionManager` sends) × named channels in a `ChannelRegistry` (engine owns the mechanism; `newbie` seeds capacity). Decisions: offline `tell` rejected; channels code-registered for now (world-YAML defs a follow-on); per-channel subscription generalizes `mute_chat`; verb-per-channel; rate-limiting deferred.

| # | Task | Status |
|---|------|--------|
| 52.1 | `ChatScope` + `Channel` + `ChannelRegistry` (engine mechanism); built-in `say`/`tell` + seed `newbie`. | [x] v0.44.1 — muteable-only-P2ALL enforced; `say`/`tell` at module load, `newbie` from composition. |
| 52.2 | Channel-aware chat outbox on `GameContext`, replacing the Sprint 45 lists. | [x] v0.44.2 — `chat_echoes` + `chat_outbox`; unknown channels fall back to P2ROOM (never accidentally global). |
| 52.3 | `broadcast.py` routes each outbox entry by scope; stamps `channel`. | [x] v0.44.2 — P2ALL iterates `connected_player_ids()` per-recipient (server-side subscription drop); WS `chat_messages` entries became `{text, channel}`. |
| 52.4 | `tell <player>` (P2P, offline-reject); registry auto-registers a verb per named channel. | [x] v0.44.3 — `tell`/`whisper`; topic verbs with `(Tag)` prefix baked into server text. |
| 52.5 | Per-channel subscription in prefs (generalize `mute_chat`); server-side drop. | [x] v0.44.4 — `channel_subscriptions` map; `mute_chat` retired (say/tell not muteable); client-side gate removed. |
| 52.6 | Unit tests: routing, offline-tell, verb dispatch, subscription drop, channel tag. | [x] 24 new unit tests across `test_channels`/`test_chat_broadcast`/`test_chat_verbs`/preferences. |
| 52.7 | Colored/prefixed per-channel tags on both render paths. | [x] v0.44.5 — `chat-<channel>` class; say cyan / tell violet / newbie amber. |
| 52.8 | Settings UI: per-channel toggle list replacing the mute checkbox. | [x] v0.44.5 — one subscribe checkbox per muteable topic channel, via `apply_updates`. |
| 52.9 | Two-player e2e: newbie subscribed/muted; tell reaches only target; say room-scoped. | [x] v0.45.0 — three-context e2e; Sprint 45 say-routing e2e still passes. |

**Deferred to a follow-on:** data-driven channel defs in world YAML; a distinct `shout` verb; channel scrollback/history; mobile tab-collapse polish; rate-limiting.

---

## Sprint 53 — Collectible marks / attunements — ✅ complete (v0.43.0)

**Goal:** Named passive badges earned by *discovering* things — a progression track fed by exploration, not combat. **Design:** the hunts feature (Sprint 48) is the template — `world_content/marks.yaml` defs, earned state a `mark:<id>` flag, criteria over existing `Player` journal state, boons via a `MarkModifierSource`. No new table.

| # | Task | Status |
|---|------|--------|
| 53.1 | `features/marks/` package + `marks.yaml` loader + fail-fast validation + content-lint + registry. | [x] v0.42.6 — hunts-def template; `MarkBoon.kind` typed as the engine `ModifierKind` literal. |
| 53.2 | `MarkService`: criteria eval over journal state; idempotent award = flag + announcement; `register(bus)`. | [x] v0.42.7 — rides `PLAYER_MOVED`/`ITEM_TAKEN`/`QUEST_COMPLETED` (queued pre-commit so award writes land in the txn); fixpoint loop chains mark-on-mark criteria. |
| 53.3 | Boons (`MarkModifierSource`) + `marks` command. | [x] v0.42.8 — traits `sources.py` pattern; `marks` verb lists earned + "???" teasers (hidden omitted). |
| 53.4 | Ashmoore marks content + unit/integration tests + docs. | [x] v0.43.0 — 4 marks (village_wanderer; friend_of_the_crow; far_strider +5 carry; hidden deep_delver +5 cartography); integration walk-test; shipped-content lint. |

---

## Sprint 54 — Celestial cycles: moons & tides — ✅ complete (v0.44.0)

**Goal:** Lunar phase and tide as world state derived from the world clock, gating content across pillars. **Design:** pure derivation, no new persisted state, no new scheduler — `moon_phase_for_day`/`tide_for_hour` beside `season_for_day`; change detection rides `HOUR_CHANGED`/`DAY_CHANGED`; content gates via condition registry + a tide-written authoritative `Exit`.

| # | Task | Status |
|---|------|--------|
| 54.1 | Tier 1 calendar functions + `MOON_PHASE_CHANGED`/`TIDE_CHANGED` events. | [x] v0.43.1 — `engine/clock/celestial.py`: 8-phase 16-day lunar month (drifts against the 30-day season), semi-diurnal tide. |
| 54.2 | `features/celestial/`: transition handlers; `moon_phase_is`/`tide_is` gates (command + dialogue); status-bar surfacing. | [x] v0.43.2 — handlers compare event endpoints; gates fail closed with in-fiction reasons; moon/tide in `time_update` + status bar. |
| 54.3 | Ashmoore tide-gated causeway + moon-gated dialogue beat; content-lint; integration tests; docs. | [x] v0.44.0 — data-driven `celestial.yaml` `tide_gates` drives `creek_crossing → tidal_islet` (authoritative-`Exit` writes; ungated return so the tide never strands). Required aligning the validator with the dialogue engine's open-keyed choice contract (`DialogueChoiceData` now `extra="allow"`). |

---

## Sprint 55 — Context-attached commands (object-scoped verbs) — ✅ complete (v0.46.0)

**Goal:** let world content give an **item or NPC its own verbs** that appear and work only when that object is present. Adopt Evennia's object-scoped-verb concept; **skip** its cmdset merge algebra. **Key finding:** Lorecraft already had most of the machinery — the help filter auto-hides out-of-context verbs, the shared side-effect registry provides the actions, `CommandRegistry` already supports per-command conditions. New parts: a presence gate, a content schema, a loader/dispatcher.

| # | Task | Status |
|---|------|--------|
| 55.1 | `object_present:<id>` / `npc_present:<id>` command-condition gates. | [x] v0.45.4 — join the built-in conditions; the help filter then lists a context verb only when its object is present. |
| 55.2 | `context_commands` schema on items/NPCs (validator) + content-lint + registry + loader. | [x] v0.45.5 — `ContextCommandData`, `context_commands` JSON columns (+ SQLite migrations), YAML round-trip, `features/context_commands` registry + `load_from_session` + `lint_context_commands`. |
| 55.3 | Dispatcher: one gated command per verb; resolve the present declaring object; fire side-effects; collision-warning. | [x] v0.45.6 — `context_verb:<verb>` availability condition; noun disambiguates shared verbs; verb/alias shadowing a built-in is skipped with a warning. |
| 55.4 | Ashmoore content + integration/help tests + docs. | [x] v0.46.0 — altar `read`/`study` (→ `lore:chapel_wheel`) in the Ruined Chapel + Mira's `tip` (→ `tipped_mira`); gated to their room, hidden from `help` out of context, shipped content lints clean. |

**Deferred to a follow-on:** Evennia's cmdset merge algebra; optional-prefix matching (`@look`) and per-command permission locks.

---

# Lorecraft — Roadmap

**This is the single source of truth for implementation progress** — what's done and what's next. (`docs/status.md` was retired 2026-07-04 and archived to `docs/.archive/status.md`; its Phase-based tracking had drifted out of sync with this roadmap.)

Working roadmap derived from `docs/architecture.md`, `CODE_AUDIT.md`, and recent 0.2.0 development (HTMX migration + parser v1).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started

Sprints are scoped small (1–2 tasks, one subsystem) on purpose, so each sprint/task can be picked up with minimal context.

---

## Guiding principle (2026-07-01)

**Foundation before features.** The core engine must be very well designed, well tooled, well tested, and internally consistent *before* we expand commands or introduce combat, trading, or PvP. No skimping on code design and quality. Concretely:

- The findings in `CODE_AUDIT.md` are the work queue, not background reading. Foundation sprints below map directly to them.
- New features are gated behind the **Foundation exit criteria** (see below). Combat and trading do not start until the gate is green.
- Every change during the foundation phase should *raise* consistency: one error-handling style, one context-construction path, one event-wiring style, one module-layout convention.
- Partially-finished subsystems get finished or removed — no half-done seams left behind.

---

## Current position

Phases **1–6** are implemented (command dispatch, world/time, inventory, NPCs/quests, save/disconnect, admin tools). Version **0.2.0** added parser v1, quantity inventory, and the HTMX primary UI.

[Sprints 1–3](#sprint-1--htmx-parity-playtesting-unblock-) closed out HTMX parity, command-depth gaps, and the scheduler foundation. A full code audit (`CODE_AUDIT.md`, 2026-07-01, revalidated against source) identified the engineering debt to clear next.

**Current:** Foundation ([Sprints 4–15](#sprint-4--player-authentication-production-hardening-)) and the **entire pillar-driven feature band ([Sprints 16–30](#sprint-16--item-locationownership--instance-state))** are complete — Tier 1 engine primitives (16–21), item components & equipment (22–23), traits/skills & exploration + UI (24–26), condition/trade/transit (27–29), quests & puzzles (30). **Foundation gate is green.**

Since then, the **Tier 1/Tier 2/web split** shipped as a large refactor (v0.15.0–0.31.1, tracked in [`tier_split_refactor.md`](tier_split_refactor.md), off this roadmap): Tier 1 now lives in `src/lorecraft/engine/` (import-pure — it depends on nothing under `features/` or web, enforced by `tests/unit/test_tier_boundaries.py`), the 24 Tier 2 features each own a package under `src/lorecraft/features/`, and the web hosts moved to `src/lorecraft/webui/{player,admin}/`. Player username/password validation also shipped (v0.31.0).

**Current (2026-07-05):** the post-tier-split band (Sprints 31–34) is essentially done — **Sprint 31** (tier split fully complete, v0.31.4–0.32.3), **Sprint 32.2/32.3** (account preferences + accessibility, v0.33.0–0.34.0), **Sprint 33** (guided `/report` + page-length quick-win, v0.35.0), and **Sprint 34** (`help <command>` + `score`, v0.34.0 — both open player reports resolved). **Open roadmap items:** [Sprint 32.1](#sprint-32--player-onboarding--account-ux) (in-game intro walkthrough, deferred pending a product decision on its trigger UX), [Sprint 65](#sprint-65--multiplayer-trade--transit-tests) (multiplayer trade/transit simulation tests), and the new [Performance & scaling band (Sprints 66–69)](#performance--scaling-band-sprints-6669--measure-then-optimize-no-threading-yet). **Combat and PvP are set aside to [`wishlist.md`](wishlist.md)** (2026-07-05) — they kept forcing roadmap renumbering; ready-to-restore specs live there. See [`engine_core.md`](engine_core.md) for the Tier boundary and [`wishlist.md`](wishlist.md) for the pillars and mechanics menu.

---

## Sprint 1 — HTMX parity (playtesting unblock) ✅

**Goal:** Commands execute through `POST /command`, social gameplay is visible, and WebSocket push works for multi-player panel refresh.

| # | Task | Status |
|---|------|--------|
| 1.1 | Call `CommandEngine.handle_command()` in `frontend.py` `POST /command` | [x] |
| 1.2 | Disambiguation: bare-number replies via `AppState.pending_disambig` | [x] |
| 1.3 | Dialogue overlay partial + OOB swaps from `ctx.updates["dialogue"]` | [x] |
| 1.4 | Quest tracker partial + active quests on SSR + OOB on `quest_update` | [x] |
| 1.5 | Fix WebSocket URL (`/ws?player_id=…`), handle `feed_append` / `room_event` | [x] |
| 1.6 | `players_here` from `ConnectionManager` when WS connected | [x] |
| 1.7 | Integration tests: move, take, talk via `POST /command` | [x] |

---

## Sprint 2 — Command depth ✅

**Goal:** Close gameplay gaps (item aliases, disambiguation, help, use/give/lock) before combat.

| # | Task | Status |
|---|------|--------|
| 2.1 | Item `aliases` in YAML/model; wire through `GameContext.get_visible_entities()` | [x] |
| 2.2 | Finish inventory disambiguation bug | [x] |
| 2.3 | Context-aware `help` (dialogue, combat, per-room disabled commands) | [x] |
| 2.4 | `use` command + `InventoryService.use_item()` | [x] |
| 2.5 | 2–3 more parser patterns (`give`, `open`, containers) | [~] `give` + `lock`/`unlock` (on the existing `Exit.locked`/`key_item_id` fields) shipped; `open`/container-holding items deferred — needs new Item/state modeling |

---

## Sprint 3 — Scheduler foundation ✅

**Goal:** Phase 8 per `architecture.md` §28 — the scheduling primitive combat will run on.

| # | Task | Status |
|---|------|--------|
| 3.1 | `services/scheduler.py` — DB-backed jobs on `TIME_ADVANCED` | [x] |

---

## Sprint 4 — Player authentication (production hardening) ✅

**Goal:** Phase 7 per `architecture.md` §21 — full account system with password auth, JWT tokens, and signed WebSocket handshake. Foundation for all production deployments.

**See:** [`player_authentication.md`](player_authentication.md) for detailed workflows and code examples.

| # | Task | Status |
|---|------|--------|
| 4.1 | `POST /auth/login` — account creation on first login, password hashing (bcrypt/argon2) | [x] Uses the existing PBKDF2-HMAC-SHA256 primitives in `admin/auth.py` (`hash_password`/`verify_password`) rather than adding bcrypt/argon2 as a new dependency — same security properties, one hashing convention for the whole codebase. New `PlayerAuth` table (provider-agnostic: `provider`/`provider_subject`, ready for OAuth later). `login_or_register()` in `web/auth.py` also *claims* pre-existing passwordless players (e.g. dev-seeded `player-1`) on first authenticated login rather than erroring. |
| 4.2 | JWT access tokens (15min lifetime) + refresh token rotation (8hr lifetime) | [x] Reuses `admin/auth.py`'s `create_token`/`decode_token`, signed with `Settings.player_session_secret` (distinct token `type` from the browser's `lorecraft_session` cookie — can never be replayed as each other). Fixed a latent bug found along the way: tokens only had second-precision `iat`, so two issued in the same second were byte-identical (rotation was a no-op if called twice quickly) — added a `jti` claim, fixing both the new player refresh endpoint and the pre-existing admin one. |
| 4.3 | `POST /auth/ws-ticket` — single-use, 60-second WebSocket ticket exchange | [x] Accepts either `Authorization: Bearer <access_token>` (API clients) or the signed `lorecraft_session` cookie (the browser, which can't easily attach custom headers to a same-origin fetch but sends cookies automatically). Ticket storage is an in-memory dict on `AppState` (`ws_tickets`), matching the existing `pending_disambig` pattern — fine for this engine's single-process deployment target. |
| 4.4 | WebSocket handshake: validate ticket, map to player_id, attach to ConnectionManager | [x] `main.py`'s `_resolve_ws_player_id()`: a `?ticket=` param is authoritative — invalid/expired/reused rejects the connection outright (1008) rather than silently falling back to `?player_id=`, which would defeat the point of tickets. |
| 4.5 | `/auth/refresh` endpoint for refresh token rotation | [x] Also verifies the player still exists (guards against refreshing into a deleted account), mirroring `admin/auth.py`'s `/admin/auth/refresh`. |
| 4.6 | Retire legacy `?player_id=` query param fallback (was gated by `LORECRAFT_ALLOW_QUERY_PLAYER_ID`) | [x] `Settings.allow_query_player_id` now defaults to `False`. Not deleted outright — kept as an explicit opt-in for test fixtures that intentionally exercise the wire protocol directly (`tests/simulation/`'s `VirtualPlayer`, several state-resolution integration tests), since removing it would break the [Sprint 11](#sprint-11--browser-e2e-harness-)/12 harnesses for no real security benefit (trusted local test processes, not real clients). Surfaced and fixed a chicken-and-egg bug: `GET /lobby` depended on `get_current_player`, which now 401s with no session — meaning a brand-new visitor couldn't reach the page that lets them log in. New `get_current_player_optional()` fixes this for `/lobby` only; every other route correctly keeps requiring a session. |
| 4.7 | OAuth extensibility hooks (Google OIDC callback stubs for future LAN-party deployments) | [x] `POST /auth/oauth/{provider}/callback` stub — `PlayerAuth.provider`/`provider_subject` already generalize to non-local providers with no schema change needed. Returns 501 rather than pretending to implement OAuth (needs a registered client id/secret/redirect URI this engine doesn't have configured); not wired into any client. |
| 4.8 | Integration tests: login, token refresh, WS ticket validation, expired token rejection | [x] `tests/integration/test_player_authentication.py` (15 tests) + `tests/unit/test_player_login.py` (9 tests) + updated `tests/integration/test_player_session.py` for the new password-protected lobby. Covers account creation/verification/wrong-password, refresh rotation + expired/garbage/wrong-type rejection, ws-ticket issuance (bearer + cookie) + single-use + TTL expiry + expired-access-token rejection, and the OAuth stub. Full suite (unit/integration/e2e/simulation) green throughout — the e2e run caught the `/lobby` chicken-and-egg bug above before it could ship. |

**Also done, beyond the numbered checklist:** the browser lobby (`/lobby/enter`, `/lobby/create`) is now password-protected — previously `/lobby`'s "Join a World" tab was a one-click player picker with *zero* authentication (anyone could enter as any existing character), which the numbered tasks above don't explicitly cover but would have left the real player-facing surface unprotected even with the API-level auth in place. `login_or_register()` gained `allow_create: bool` so `/lobby/enter` ("Log In") 404s on a genuinely unknown username instead of silently creating one, while `/lobby/create` keeps create-or-claim semantics. `app.js`'s `connectWebSocket()` now fetches a ws-ticket before connecting instead of using a raw `?player_id=`.

---

# Foundation band (Sprints 5–15)

Work queue derived from `CODE_AUDIT.md`. Ordering is deliberate: error/type groundwork first, then **characterization tests before the big refactors**, then structure, then tooling.

**Current progress:** [Sprints 5–15](#sprint-5--error-handling--exception-hierarchy-) complete (error handling, type safety, characterization tests, module decomposition, service consistency/wiring, extensibility seams, tooling infrastructure, browser E2E harness, simulation harness MVP, observability & CI quality gates, unified command lifecycle, core UX completion). Foundation band done — see exit criteria below.

## Sprint 5 — Error handling & exception hierarchy ✅

**Goal:** One error-handling style everywhere. Audit §2.1.

| # | Task | Status |
|---|------|--------|
| 5.1 | `lorecraft/errors.py` — `GameError`, `ValidationError`, `NotFoundError`, `PermissionError`, `ConflictError` (with machine-readable `code`) | [x] |
| 5.2 | Eliminate the 22 silent `except Exception` blocks: catch specific exceptions, log all of them (`web/frontend.py` ×12, `web/player_auth.py`, `admin/websocket.py` ×3, `admin/auth.py` ×2) | [x] |
| 5.3 | Services raise typed errors; command handlers translate to `ctx.say()` in one shared wrapper | [~] prepared via errors.py; integration in [Sprint 9](#sprint-9--service-consistency--wiring-) |
| 5.4 | Guard quantity underflow in `ItemRepo.remove_from_room` (raise/log instead of silent delete) | [x] |
| 5.5 | Unit tests for error paths (every custom exception exercised) | [x] |

## Sprint 6 — Type safety ✅

**Goal:** basedpyright verifies real invariants. Audit §2.2.

| # | Task | Status |
|---|------|--------|
| 6.1 | Type `CommandHandler` as `Callable[[str | None, GameContext], None]` (Protocol in `types.py` or `TYPE_CHECKING` import); delete all 18 `cast(GameContext, ctx)` | [x] |
| 6.2 | Replace `cast(Any, ctx)` + `getattr(..., default)` condition evaluation in `game/registry.py` with typed access — conditions must fail closed, not open | [x] |
| 6.3 | Single `build_game_context()` factory used by all entry points; make `quest_repo`/`dialogue_repo`/`audit` required and delete their None-guards | [x] |
| 6.4 | `TypedDict` schemas for WS payloads and HTMX/JSON responses | [x] |
| 6.5 | Raise basedpyright to `standard` mode on `src/` and hold it there | [x] |

## Sprint 7 — Web & admin characterization tests ✅

**Goal:** Lock in current behavior *before* the [Sprint 8–9](#sprint-8--module-decomposition-) refactors. Audit §2.3.

| # | Task | Status |
|---|------|--------|
| 7.1 | Characterization tests for `web/frontend.py`: state resolution, session reconnect edge cases, feed pagination, error rendering | [x] |
| 7.2 | Admin API endpoint tests (target ~80% of `admin/api.py` routes) | [x] |
| 7.3 | Admin WebSocket integration tests | [x] |
| 7.4 | Event-flow integration tests: command → event → service reaction → client update; handler-ordering assertions | [x] |

## Sprint 8 — Module decomposition ✅

**Goal:** No module over ~400 lines with mixed concerns. Audit §2.6.

| # | Task | Status |
|---|------|--------|
| 8.1 | Split `web/frontend.py` (1,306→780 lines) → `session.py` (380), `rendering.py` (180); replaced `getattr`-chain state access with explicit dependency injection functions | [x] |
| 8.2 | Extract `game/grammar.py` (322 lines) and `game/diagnostics.py` (119 lines) from `game/parser.py` (774→407 lines); re-exports for backwards compatibility | [x] |
| 8.3 | Split `admin/api.py` (817→20 lines) into per-resource routers under `admin/routers/`: `players.py` (191), `audit.py` (93), `world.py` (357, incl. items/NPCs/changesets), `clock.py` (125), `accounts.py` (93); `admin_router` now just mounts them, same route paths and status codes | [x] |

## Sprint 9 — Service consistency & wiring ✅

**Goal:** One way to construct, wire, and use services. Audit §3.1.

| # | Task | Status |
|---|------|--------|
| 9.1 | Service container/registry in `AppState`; remove ad-hoc `Service()` instantiation from the four command modules | [x] |
| 9.2 | One event-wiring convention: every service exposes `register(bus)`; replace the inline `bus.on()` quest wiring in `main.py` | [x] |
| 9.3 | DRY the six near-identical take/drop methods in `services/inventory.py` (shared find→disambiguate→act helper) | [x] |
| 9.4 | Consolidate item-matching logic in `repos/item_repo.py` into one matcher | [x] |

## Sprint 10 — Extensibility seams ✅

**Goal:** New mechanics hook in via data/registration, not core edits. Audit §3.3.

| # | Task | Status |
|---|------|--------|
| 10.1 | Pluggable dialogue side effects (handler registry replacing the hardcoded `set_flags`/`give_item`/`start_quest` branches in `npc/dialogue.py`) | [x] |
| 10.2 | Pluggable dialogue/exit conditions (predicate types beyond flags: level, item, quest state) | [x] |
| 10.3 | Pluggable command conditions (registry instead of the hardcoded `_evaluate_condition` chain) | [x] |
| 10.4 | Decide + document the feature-registration pattern (models/commands/events/rules per feature) — combat will be its first consumer | [x] |

## Sprint 10.5 — Tooling Infrastructure ✅

**Goal:** Admin/dev tooling foundation: repo-tracked issues & news, world CLI suite, analytics API, content validation. Unblocks [Sprint 11](#sprint-11--browser-e2e-harness-)+ (can log failures, record metrics, validate content).

| # | Task | Status |
|---|------|--------|
| 10.5.1 | Issues system: `docs/issues.yaml`, CRUD routes, admin TUI (F6) + web panel tabs | [x] |
| 10.5.2 | News & announcements: `docs/news.yaml`, in-game `/news`, RSS feed, admin UI (TUI F7) | [x] |
| 10.5.3 | World management CLI: import/export/validate/diff/stats commands; call from admin world manager | [x] |
| 10.5.4 | Analytics API foundation: metric queries ready (no dashboard yet, driven by [Sprint 13](#sprint-13--observability--ci-quality-gates-) instrumentation) | [x] |
| 10.5.5 | Content validation & linting: dead references, unreachable rooms, circular quests, etc. | [x] |

**See:** [`tooling_infrastructure.md`](tooling_infrastructure.md) for full architecture and design details. Circular quest dependency checking was scoped out — `QuestStageData` has no quest-to-quest dependency field in the schema today.

## Sprint 11 — Browser E2E harness ✅

**Goal:** Catch UI-specific regressions (HTMX swaps, OOB updates, Alpine state) that ASGI-transport integration tests can't see.

| # | Task | Status |
|---|------|--------|
| 11.1 | Browser end-to-end test harness for HTMX UI | [x] `tests/e2e/` — Playwright-driven tests against a real live uvicorn server (background thread, disposable per-test sqlite DB, real world YAML bootstrap). Optional `e2e` extra (`pip install -e ".[e2e]"` + `playwright install chromium`); excluded from the default `pytest`/`make test` run via `-m "not e2e"`; run explicitly with `make test-e2e`. Covers character creation, movement + room/inventory panel updates, and dialogue → quest-start via the Ashmoore dev world golden path. |

## Sprint 12 — Simulation harness MVP ✅

**Goal:** Real-protocol, multi-player scripted scenarios per `architecture.md` §25 — a third test transport alongside ASGI-transport integration tests and the [Sprint 11](#sprint-11--browser-e2e-harness-) browser E2E harness.

| # | Task | Status |
|---|------|--------|
| 12.1 | Simulation harness MVP (`tests/simulation/`) | [x] `virtual_player.py` — `VirtualPlayer` wraps a real `websockets` client against `/ws` (not an ASGI shortcut); `send_command()`/`run_script()` with optional timing jitter, `wait_for_broadcast()` for pushed (non-reply) messages. `conftest.py` — `simulation_server`/`simulation_server_factory` fixtures boot the real app under `uvicorn` on a background thread against a disposable per-test sqlite DB and the real `world_content/world.yaml` (same pattern as [Sprint 11](#sprint-11--browser-e2e-harness-)'s `live_server`, no synthetic world content). `test_multiplayer_scenarios.py` — two real connections: `player_joined` broadcast fan-out on connect, and concurrent `take` of a single-quantity item (no duplication/loss). `test_audit_regression.py` — runs a fixed script against two independent fresh servers and diffs the normalized audit trail, per the "capture, diff after changes" pattern in `architecture.md` §25. New `simulation` pytest marker, excluded from `make test`/plain `pytest` like `e2e` (`make test-simulation`); no new install required (`websockets`/`httpx` were already transitive via `fastapi[standard]`, now declared explicitly in the `dev` extra). Noted but intentionally not fixed here: the raw `/ws` command loop didn't yet re-broadcast `room_messages` to other occupants the way `POST /command` does — fixed by Sprint 14.1. |

## Sprint 13 — Observability & CI quality gates ✅

**Goal:** Regressions can't land silently. Audit §4.2, §5.2.

| # | Task | Status |
|---|------|--------|
| 13.1 | Structured logging (stdlib `logging` with correlation/transaction IDs from `TransactionContext`) | [x] `observability.py` — `configure_logging()` attaches a correlation-aware formatter/filter to the root logger (idempotent, level from new `Settings.log_level`/`LORECRAFT_LOG_LEVEL`); `bind_transaction_context()` publishes a `TransactionContext`'s `transaction_id`/`correlation_id` to a `contextvars.ContextVar` for the duration of one command, so every `log.*` call anywhere in that call stack (services, event handlers, repos) picks the IDs up automatically — no signature threading needed. Wired into both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`) and `create_app()`. |
| 13.2 | Command latency + event-handler timing instrumentation | [x] `CommandEngine._execute_parsed` times each command handler call and stamps `duration_ms` onto the `COMMAND_EXECUTED` audit event payload (`game/engine.py`); `EventBus.emit()` times each handler dispatch, records it on `HandlerResult.duration_ms`, and logs `event=... handler=... duration_ms=... depth=<handlers registered>` at DEBUG (`game/events.py`). New `analytics.command_latency_percentiles()` (p50/p95/p99 from `duration_ms`) + `GET /admin/analytics/latency`. |
| 13.3 | CI: pytest + coverage threshold + basedpyright + ruff as required checks | [x] `.github/workflows/ci.yml` — three required jobs on push/PR to `main`: `quality` (`make lint` + `make typecheck` + `make test-cov`), `simulation` (`make test-simulation`), `e2e` (Playwright + `pytest tests/e2e`). `make test` / `make test-cov` run the default suite with `pytest-cov` + `pytest-xdist` (`-n auto --dist=loadfile`) and `[tool.coverage.report] fail_under = 80` in `pyproject.toml` (current baseline ~82%). New `make lint`/`make typecheck` targets. Fixed a latent bug found while wiring this up: `tests/simulation/*.py`'s `from tests.simulation.conftest import ...` only worked under `python -m pytest` (which prepends cwd to `sys.path`), not bare `pytest` (what `make test-simulation` and CI actually run) — `pythonpath` in `pyproject.toml` now includes `"."` alongside `"src"`. |

## Sprint 14 — Unify command lifecycle ✅

**Goal:** One 13-step transaction/event/audit lifecycle shared by `/ws` and `/command` paths (long-standing `[~]` STATUS item). Easier after [Sprint 8](#sprint-8--module-decomposition-) decomposition.

| # | Task | Status |
|---|------|--------|
| 14.1 | Extract shared lifecycle; both entry points call it; add rollback-on-error semantics | [x] **Rollback-on-error** — `CommandEngine._execute_parsed` (`game/engine.py`) now catches exceptions from the command handler instead of letting them propagate uncaught. On a crash: `GameContext.rollback_state_changes()` (new `rollback_state` callable, wired at both entry points to the DB session's `.rollback`) undoes any half-applied state; `ctx.messages`/`room_messages`/`updates`/`pending_events` are cleared so no partial narration leaks out (architecture.md §26's golden rule: never tell clients something happened until the DB says it happened); a generic error message replaces it; a new `GameEvent.COMMAND_FAILED` audit event (severity ERROR) records the crash. **Broadcast unification** — new `game/broadcast.py`'s `broadcast_command_effects()` is the one place step 12 (room broadcast) now lives; both `main.py`'s `/ws` command loop (now `async`) and `web/frontend.py`'s `POST /command` call it after `CommandEngine.handle_command()` returns, closing the gap [Sprint 12](#sprint-12--simulation-harness-mvp-)'s simulation tests surfaced (the raw `/ws` path never re-broadcast `ctx.room_messages`/`state_change` to other room occupants the way `POST /command` did). Verified with a new simulation test exercising the previously-broken path over a real socket, plus the full existing suite (unit/integration/e2e/simulation) unchanged. **Construction unification (follow-up)** — `game/context.py`'s `build_game_context()` factory (added Sprint 6.3, meant to be "the" `GameContext` construction path) turned out to be unused by both real entry points. Extended it to accept `audit_session` (a separate `Session`, matching real usage — replacing the old same-session `create_audit_repo` bool) and `rollback_state`, and to pass `clock` straight through rather than synthesizing a fallback `WorldClock` (a fabricated clock would be silently wrong data, not a safe default). `main.py` and `web/frontend.py` now both call it instead of constructing `GameContext` inline. |

## Sprint 15 — Core UX completion ✅

**Goal:** Finish the partially-shipped core UX so nothing is left half-done.

| # | Task | Status |
|---|------|--------|
| 15.1 | World clock / weather status bar push via WS | [x] `ConnectionManager.broadcast_global()` + a `TIME_ADVANCED` handler in `main.py` push `time_update` (hour/minute/day/season/weather) to every connected player, not just on connect/reconnect SSR. |
| 15.2 | Multi-player live lists finished (`[~]` STATUS item) | [x] `game/broadcast.py`'s `broadcast_command_effects()` now sends a second `state_change` (`players-online` panel) to the room a player *left*, not just the room they entered — previously occupants of the old room only saw the departure narration text, not a live players-list refresh. |

---

## Foundation exit criteria (gate for Sprints 16+)

All must be true before combat/trading work starts:

- [x] Zero silent `except Exception` blocks in `src/` ([Sprint 5](#sprint-5--error-handling--exception-hierarchy-))
- [x] Zero `cast(GameContext, ctx)` / `cast(Any, ctx)` in `src/`; basedpyright `standard` mode clean ([Sprint 6](#sprint-6--type-safety-))
- [x] One `GameContext` construction path; no optional repo fields — **fixed (2026-07-02):** `build_game_context()` now accepts `audit_session` (a separate `Session`, matching real usage) instead of the old same-session `create_audit_repo` bool, `rollback_state`, and passes `clock` straight through instead of synthesizing a fallback `WorldClock`. Both `main.py`'s `/ws` loop and `web/frontend.py`'s `POST /command` call it instead of constructing `GameContext` inline.
- [x] No module >~500 lines with mixed concerns ([Sprint 8](#sprint-8--module-decomposition-))
- [x] One service wiring convention; no inline `bus.on()` in `main.py` (Sprint 9.2)
- [x] Web + admin layers have integration coverage; CI enforces coverage, types, and lint ([Sprint 7](#sprint-7--web--admin-characterization-tests-) + Sprint 13.3)
- [x] Feature-registration pattern documented and demonstrated (10.4)
- [x] All `[~]` STATUS partials either finished or explicitly retired — [Sprint 14](#sprint-14--unify-command-lifecycle-) closed the `/ws`/`/command` broadcast-lifecycle gap; [Sprint 15](#sprint-15--core-ux-completion-) closed world clock/weather WS push (15.1) and the multi-player live-lists refresh gap on room-leave (15.2)

---

# Engine core band (Tier 1 primitives) — Sprints 16–21

**Engine-first (2026-07-03).** The eight cross-cutting Tier 1 primitives from
[`engine_core.md`](engine_core.md) are built here, **before** the Tier 2 feature modules that
consume them ([Sprints 22](#sprint-22--standard-item-components--definition-fields)+). Rationale: several feature sprints share these primitives; building
them per-sprint yields N opinionated implementations and blurs the framework/game boundary. Order
follows dependency + leverage ([`engine_core.md`](engine_core.md) §6) — the two most expensive to
retrofit (unified item location/ownership, and a seedable `ctx.rng` the audit-regression harness
depends on) go first. These primitives are **content-agnostic**: no named skills, slots, factions,
or damage formulas live here.

## Sprint 16 — Item location/ownership & instance state ✅

**Goal:** One way to say where an item lives and to move it atomically; per-instance state via
registered components. Highest-leverage primitives — they underpin equipment, containers, shop
stock, corpses, and trade escrow. **See [`engine_core.md`](engine_core.md) §3.1–3.2, §4a/§4f.**

| # | Task | Status |
|---|------|--------|
| 16.1 | `ItemStack` + `(owner_type, owner_id, slot?)` location + holder registry; one atomic `ItemLocationService.move()` (rollback-safe); **replace** `Player.inventory`/`RoomItem` outright (column/table deleted — full blast-radius table in [`engine_core.md`](engine_core.md) §3.2) | [x] |
| 16.2 | `ItemInstance` carrier + pluggable component registry (durability/openable/lit/container register like dialogue side-effects); `bound`/soulbound flag | [x] `ComponentRegistry` (`game/components.py`) ships with zero registered components (Tier 1 registers none, per spec); `Item.bound` field added (enforcement deferred to Tier 2). |

**Delivered beyond the two checklist items:** full blast-radius migration (17 files) onto the new
primitive — `services/inventory.py`, `repos/item_repo.py`, `game/context.py`,
`game/command_conditions.py`, `services/movement.py`, `services/quest.py`,
`npc/side_effects.py`, `services/save.py` (v1-save-compatible load), `world/loader.py`,
`world/versioning.py`, `tools/world_cli.py`, `scripts/import_world.py`,
`admin/routers/players.py`, `main.py`, `web/session.py`, `web/frontend.py`. 23 new invariant
unit tests (`tests/unit/test_item_location_service.py`); full existing suite (431 unit/
integration + 3 e2e + 5 simulation, including the audit-regression diff and the
concurrent-take-no-duplication guarantee) green unchanged. See `CHANGELOG.md` for the full
list of bugs caught along the way (typed-error argument order, a missing `StackRepo` flush,
a pydantic recursion bug in `list[JsonValue]` SQLModel fields). Schema migration for
*existing* production DBs (`scripts/migrate_schema_v2.py`, `WorldMeta.schema_version` 1→2) is
scoped out for now — no production deployment exists yet; the dev flow
(`scripts/import_world.py --fresh`) regenerates disposable DBs from YAML instead.

## Sprint 17 — Determinism: seedable RNG & skill-check ✅

**Goal:** All random resolution reproducible so the [Sprint 12](#sprint-12--simulation-harness-mvp-) audit-regression harness can cover
combat/skills/trade. **See [`engine_core.md`](engine_core.md) §3.6, §4b.**

| # | Task | Status |
|---|------|--------|
| 17.1 | Seedable `ctx.rng` service threaded through `GameContext` (per-run seed); lint-ban module-level `random` in feature code | [x] `game/rng.py`'s `GameRng`; one app-wide instance on `AppState` from `Settings.rng_seed`; required `GameContext.rng`/`build_game_context(rng=...)`; `SchedulerEventContext.rng`; `clock/weather.py` converted off `random.choice`. Ruff `TID251` banned-api rule on `random`, scoped to `src/` (test-harness timing jitter exempted). |
| 17.2 | `skill_check(rng, base, difficulty, modifiers) → CheckResult` helper (roll-under d100, 5/95 bounds — one check path for perception/lockpicking/barter/combat) | [x] `game/checks.py`; resolves `effective` via Sprint 18's modifier resolver, clamps target to `[5, 95]`. Landed after Sprint 18 since it needs the `Modifier` type. |

## Sprint 18 — Modifier resolution ✅

**Goal:** One runtime resolver for bonuses from many sources, with a defined stacking order and
caps. Generalizes the doc's `EquipmentEffects.resolve()`. **See [`engine_core.md`](engine_core.md) §3.5, §4d.**

| # | Task | Status |
|---|------|--------|
| 18.1 | Modifier resolver: buckets **flat add → multiplier → clamp/cap**; collects from equipment `effects`, traits, active effects, region; never stored (recompute on change / lazily) | [x] `game/modifiers.py`: `Modifier`/`resolve()` (pure, bucket-ordered) + `ModifierSource`/`ModifierRegistry`/`resolve_for()` (collection). Tier 1 registers no sources — landed ahead of its listed order (18 has no dependencies, per the doc's own build-order table) specifically to unblock Sprint 17.2's `skill_check()`. |

## Sprint 19 — Meters & timed effects ✅

**Goal:** Named bounded clock-tickable resources, and expiring buffs/debuffs — one primitive each,
not one column per resource. **See [`engine_core.md`](engine_core.md) §3.3–3.4.**

| # | Task | Status |
|---|------|--------|
| 19.1 | `Meter` primitive (bounded, optional regen, scheduler tick, `METER_DEPLETED`); migrate `current_hp` (player + NPC) onto it as the proof — `max_hp` stays as the definitional base | [x] `models/meters.py`'s `Meter` + `game/meters.py`'s `MeterDef`/registry + `services/meters.py`'s `MeterService`. "hp" `MeterDef` registered as bootstrap in `main.py`'s lifespan; `PlayerStats.current_hp`/`NPC.current_hp` deleted outright (not deprecated). |
| 19.2 | `ActiveEffect` (clock-driven expiry, swept by scheduler) + trait registry (named boon/bane modifier-bundles) feeding the resolver | [x] `models/meters.py`'s `ActiveEffect` + `game/effects.py`'s `EffectDef`/registry + `services/effects.py`'s `EffectService`; `game/traits.py`'s `TraitDef`/`TraitSource`/registry. Tier 1 registers one `TraitSource` (active effects' `grants_traits`) and two `ModifierSource`s (active-effect, trait) with Sprint 18's resolver — the §3.5 promise fulfilled. |

**Delivered beyond the two checklist items:** full HP-migration blast radius (`world/loader.py`,
`admin/routers/world.py`, `services/save.py` — v1/v2 save-snapshot compat); `GameContext` gained
required `session`/`meters`/`effects` fields (`build_game_context()` factory pattern held); 25 new
invariant tests caught two real bugs (both `_on_time_advanced` sweeps read ORM attributes after
`session.commit()`'s default `expire_on_commit` invalidated them — fixed by capturing plain values
before the session closes). See `CHANGELOG.md` for the full list.

## Sprint 20 — Ledger & atomic transfer ✅

**Goal:** A coin balance on any holder + one atomic multi-party transfer for coins *and* items.
**See [`engine_core.md`](engine_core.md) §3.7, §4c/§4g.**

| # | Task | Status |
|---|------|--------|
| 20.1 | `CoinBalance` on any registered holder (player/bank/corpse/shop); atomic multi-leg `execute_exchange(legs)` — validate all, then apply all (escrow = accept-time revalidation), reusing the [Sprint 14](#sprint-14--unify-command-lifecycle-) rollback; integrity gates via `RuleEngine` (fail-closed), not conditions | [x] `models/ledger.py`'s `CoinBalance` + `services/ledger.py`'s `LedgerService` (stateless-per-call, no engine/rng held). `execute_exchange(legs)` validates every leg first, then applies all mutations — no partial exchange ever lands. `GameContext` gained a required `ledger` field. 14 new tests, all green first run. |

## Sprint 21 — Scheduled moving entity ("moving room") ✅

**Goal:** The moving-room carrier transit rides on; also serves wandering NPCs/patrols later.
**See [`engine_core.md`](engine_core.md) §3.8.**

| # | Task | Status |
|---|------|--------|
| 21.1 | Scheduled moving-room carrier + position-interpolation state machine (`at_stop → in_transit → arrive`, reverse/loop) + position push; line semantics (express/local, tickets, weather) stay Tier 2 ([Sprint 29](#sprint-29--transit--travel-systems)) | [x] `models/mobile.py`'s `MobileRouteState` (only the runtime state is persisted) + `services/mobile_route.py`'s `Waypoint`/`RouteSpec`/`RouteHooks`/`MobileRouteService` (engine-holding schedulable, exactly the `SchedulerService` shape — reuses it for all timing via `job_type="mobile_route"`). Ping-pong reversal and circular looping both covered; a route whose spec disappears on restart halts instead of crashing. 15 new tests, all green first run. |

---

# Feature band (Sprints 22+) — Tier 2 modules & content, gated on foundation exit criteria

**Re-sequenced 2026-07-03** to reflect Lorecraft's design pillars — **Exploration > Trading >
Questing > Puzzle-solving, with combat as a *supporting* system, not the centerpiece** (see
[`wishlist.md`](wishlist.md) → *Design pillars*). The old sequence front-loaded combat
(Sprints 18–20 of the previous plan); the new sequence front-loads the systems those pillars
depend on — item state, inventory/equipment, exploration, traits/skills — and moves combat
below trading/transit/quests as a fallback resolution path rather than the main loop.

Ordering follows dependencies: item state → equipment → traits/skills/exploration → condition
→ trade → transit → quests/puzzles → combat → PvP. UI polish (map, mobile) sits alongside
exploration, which it serves.

> **Engine-first (2026-07-03):** the feature band decomposes into **Tier 1 engine primitives →
> Tier 2 standard modules → Tier 3 content** per [`engine_core.md`](engine_core.md) — the anchor
> doc for the framework/game boundary. Directive: **design Tier 1 now, implement most of Tier 1
> before Tier 2.** Eight cross-cutting primitives (item location/ownership, component state,
> meters, timed effects, modifier resolver, seedable RNG + skill-check, ledger/atomic transfer,
> moving-entity) sit underneath [Sprints 22–35](#sprint-22--standard-item-components--definition-fields); building them per-sprint would yield N opinionated
> implementations and blur the boundary. The two most expensive to retrofit — the unified item
> location/ownership model and a seedable `ctx.rng` (audit-regression-critical) — go first. See
> [`engine_core.md`](engine_core.md) §3 (primitives), §4 (cross-doc surprises caught), §6 (build
> order). The Tier 1 work is now sequenced as **[Sprints 16–21](#sprint-16--item-locationownership--instance-state)** (the Engine core band below); the
> Tier 2 feature band shifts to **[Sprints 22–35](#sprint-22--standard-item-components--definition-fields)**.

> **Design docs:** [`engine_core.md`](engine_core.md) (Tier boundary + Tier 1 primitives — read first),
> [`inventory_equipment.md`](archive/inventory_equipment.md) ([Sprints 22–23](#sprint-22--standard-item-components--definition-fields)),
> [`combat_system.md`](combat_system.md) (stat/skill model + combat sprints),
> [`death_resurrection.md`](death_resurrection.md) (death penalty; combat set aside to [`wishlist.md`](wishlist.md)),
> [`dialogue_npcs_quests.md`](dialogue_npcs_quests.md) and
> [`feature-registration.md`](feature-registration.md) (quests/puzzles, pluggable
> registries), [`transit_systems.md`](archive/transit_systems.md) ([Sprint 29](#sprint-29--transit--travel-systems)), and
> [`trade_economy.md`](archive/trade_economy.md) ([Sprint 28](#sprint-28--trading--economy)). The signature systems now all have
> design docs.

## Sprint 22 — Standard item components & definition fields ✅

**Goal:** *Tier 2 realization* of item content on the [Sprint 16](#sprint-16--item-locationownership--instance-state) engine model — the deferred
Sprint 2.5 `open`/container/state prerequisite. The per-instance carrier, item-location model, and
component registry are **Tier 1 ([Sprint 16](#sprint-16--item-locationownership--instance-state))**; this sprint adds the Layer A `Item` definition
fields and the *standard components* (durability, light, container, openable) on top, so items can
be worn, burned, opened, and puzzle-wired. **See [`engine_core.md`](engine_core.md) §3.1–3.2 and
[`inventory_equipment.md`](archive/inventory_equipment.md) §7.**

| # | Task | Status |
|---|------|--------|
| 22.1 | Layer A item fields (`slot`, `weight`, `wearable`, `quality`, `max_durability`, `light`, `capacity`, `effects`, `bound`) on `Item`; YAML loader + validators | [x] |
| 22.2 | Register durability/`is_open`/`lit`/container as **standard components** on the [Sprint 16](#sprint-16--item-locationownership--instance-state) `ItemInstance`/component model; `open` + state verbs (stateless stackables stay as ID stacks) | [x] |

## Sprint 23 — Inventory & equipment ✅

**Goal:** Wear/wield slots, encumbrance, containers. Equipment grants **non-combat** effects
(light, warmth, carry, skill/trait bonuses) resolved at runtime. **See [`inventory_equipment.md`](archive/inventory_equipment.md) §3–6, §9.**

| # | Task | Status |
|---|------|--------|
| 23.1 | `wear`/`remove`/`wield`/`unwield`/`equipment` commands via `InventoryService`; `ITEM_EQUIPPED`/`ITEM_UNEQUIPPED` events | [x] Equipped-ness is a location (slot on the player's own `ItemStack`), not a `Player.equipment` column — supersedes that earlier draft, per `inventory_equipment.md`'s binding "decided" storage spec |
| 23.2 | Encumbrance bands from weight + `carry_bonus`; equipment effects resolved at runtime (never stored) | [x] `game/equipment_source.py` + `game/encumbrance.py` |
| 23.3 | Containers: `put in` / `take from`, nesting, worn-container capacity; light/darkness gate (`Room.light_level` + lit source) | [x] |

## Sprint 24 — Traits & skills ✅

**Goal:** Character identity that gates exploration and social play. Use-based skills, a trait
registry (boons/banes), reputation/NPC-standing. Builds on existing `PlayerStats` (attributes
+ `skills` dict). **See [`combat_system.md`](combat_system.md) stat model + [`wishlist.md`](wishlist.md).**

| # | Task | Status |
|---|------|--------|
| 24.1 | Trait registry (pluggable, like dialogue side-effects); traits from equipment/background/earned; boon+bane modifiers | [x] `game/standard_traits.py`'s `InnateTraitSource` + 5 illustrative traits; `services/traits.py` grant/revoke |
| 24.2 | Use-based skill improvement (perception, lockpicking, bartering, cartography, survival, persuasion); skill-check helper | [x] `game/skills.py` (identity) + `services/skills.py` (improvement); `skill_check()` itself shipped Sprint 17-18 |
| 24.3 | Reputation/standing per NPC + faction; unlocks dialogue/prices/quests (extends flags + NPC memory) | [x] `models/reputation.py` + `game/reputation_conditions.py` |

## Sprint 25 — Exploration depth ✅

**Goal:** Make discovery a first-class reward (the top pillar). Search-gated secrets, terrain,
journal, cartography. Builds on existing minimap fog and `Exit.hidden`/`condition_flags`.

| # | Task | Status |
|---|------|--------|
| 25.1 | `search` command + hidden-exit/secret-room reveal gated on perception skill + traits + light; discovery rewards (knowledge flags, progression tick) | [x] Also fixed: hidden exits were unconditionally blocked and `condition_flags` was never enforced — both pre-existing bugs |
| 25.2 | Terrain types on rooms/exits affecting travel time, fatigue cost, and required skill/gear; environmental `examine` layering | [x] `Room.terrain` + `game/terrain.py`; required-skill gate + `look` description suffix. Travel-time/fatigue-cost hooks deferred to Sprint 27 (fatigue doesn't exist yet) |
| 25.3 | Journal / auto-log panel (discovered places, met NPCs, learned lore, active clues); player cartography reveal | [x] `journal` command. Cartography map-reveal payoff deferred to Sprint 26 (owns the map UI it reveals onto) |

## Sprint 26 — Map & mobile UI ✅

**Goal:** UI polish that serves exploration (was Sprints 16–17 of the previous plan).

| # | Task | Status |
|---|------|--------|
| 26.1 | Full-screen map modal (pan/zoom), integrated with cartography reveal | [x] `partials/map_modal.html`; drag-to-pan/scroll-to-zoom via Alpine; cartography-gated reveal of known-but-unvisited rooms in `build_map_data()` |
| 26.2 | Responsive mobile tab layout | [x] Bottom tab bar (Room/Feed/Players) below `lg`; verified in a real headless-Chromium browser |

## Sprint 27 — Character condition (fatigue / sleep) ✅

**Goal:** Light survival texture that rewards planning; per-world toggle, not punishing. Runs
on `SchedulerService` + `TIME_ADVANCED`. **See [`wishlist.md`](wishlist.md) → Character condition.**

| # | Task | Status |
|---|------|--------|
| 27.1 | Fatigue/stamina drained by travel/encumbrance/actions; low fatigue penalizes skill checks; `rest`/`sleep`/`camp` | [x] `game/fatigue_source.py`'s "fatigue" `MeterDef` (stamina, scales with fortitude) + `FatigueModifierSource` (flat `mult` penalty on every registered skill once stamina drops below 50%/20% thresholds); `services/fatigue.py`'s `FatigueService` drains on `PLAYER_MOVED` (more when burdened/overloaded per Sprint 23.2 encumbrance bands) and backs `rest`/`camp`/`sleep` (`commands/condition.py`) |
| 27.2 | Sleep advances time + restores fatigue + dream/lore hook; safe vs. unsafe sleep; warmth/exposure via weather + worn clothing | [x] New `Room.safe_rest` field: `sleep` there always succeeds (full restore, 8h clock-advance, dream); elsewhere it's a `survival` `skill_check` (harder in cold weather — `clock/weather.py`'s `COLD_WEATHERS` — offset by resolved `warmth`), failing into a shorter, partial, dreamless "interrupted" rest. `game/warmth.py` + a new `warmth_bonus` item effect (`game/item_effects.py`) give worn clothing a non-combat purpose. Dream flavor references a random `lore:`-flagged discovery (Sprint 25.3) when the player has one. |

## Sprint 28 — Trading & economy ✅

**Goal:** A living economy where *where* you buy/sell matters (pillar #2). Currency → NPC shops
→ regional pricing → banks. **Signature pairing:** the transit network ([Sprint 29](#sprint-29--transit--travel-systems)) is the trade
network. **See [`trade_economy.md`](archive/trade_economy.md).**

| # | Task | Status |
|---|------|--------|
| 28.1 | Currency model (carried `coins`); item `value` × `quality` pricing; NPC vendor shops (`buy`/`sell`/`list`), bartering skill + reputation flex price | [x] New `Shop`/`ShopStock` tables (`models/economy.py`) attached to an NPC via world YAML `shop:` block; a shop's cash is `CoinBalance("shop", shop.id)` (new "shop" holder type, `game/economy_holders.py`), seeded once at import (idempotent re-import guard) via `LedgerService.credit`. `services/economy.py`'s `EconomyService` derives `buy_price = value × quality_mult × region_mult × (1 - barter_discount) × (1 - rep_discount)` and `sell_price = buy_price × sell_ratio` at runtime (never stored); every coin/item movement is one `LedgerService.execute_exchange` call (sold items are `destroy()`ed, not held as physical shop stock — `ShopStock.quantity` is listing state only). `list`/`shop`, `buy`, `sell`, `appraise` commands (`commands/economy.py`). Mira the innkeeper is a working shop in `world_content/world.yaml`. 15 new unit tests + a world-loader round-trip test. |
| 28.2 | Regional price differences + per-good bias + finite stock restocking on the world clock (buy-low/sell-high loop) | [x] New `RegionPricing` table (world YAML `economy.regions`) contributes an area-wide `region_mult` + per-item `bias` on top of a shop's own `region_mult`; `EconomyService._demand_mult()` reads current stock against `restock_to` (depleted costs more, flooded costs less, bounded to [0.5, 1.5]). `services/restock.py`'s `RestockService` (scheduler-driven, same shape as `LightFuelService`) counts `TIME_ADVANCED` ticks per `ShopStock` row and jumps `quantity` to `restock_to` once `restock_every_ticks` elapses. 12 new unit tests + a world-loader region round-trip test. |
| 28.3 | Banks: `BankAccount`, `deposit`/`withdraw`/`balance` at branches, one account/many branches (safe from death & robbery) | [x] New `Bank` (an NPC marker, like `Shop`) + `BankAccount` (identity only — balance is `CoinBalance("bank_account", account.id)`, new holder type). `deposit`/`withdraw` require standing in a branch's room (an `execute_exchange` leg each way); `balance` (carried + banked) works anywhere. One account, many branches — `services/bank.py`'s `BankRepo.get_or_create_account()` lazily creates the single account on first use. Mira's inn also runs a strongbox in `world_content/world.yaml`. 8 new unit tests + a world-loader round-trip test. |
| 28.4 | Player-to-player `offer`/`accept` trade handshake (atomic escrow swap; multi-player transaction safety) | [x] Finished the pre-existing `TradeOffer` placeholder table (never wired to any code — extended with coin fields + `[stack_id, quantity]` pledge lists per side) rather than adding a parallel one. `offer <item\|N coins> to <player>` records a pledge (creates or reuses one open `TradeOffer` between the pair) and moves nothing; `accept` composes exactly one `LedgerService.execute_exchange` with every pledge as a leg — that call's own validation *is* the escrow revalidation (a pledge that's gone since offered raises and nothing moves). Room-presence, `tradeable`/`bound`, and TTL are all re-checked at accept time, not just offer time. Also finished the pre-existing unused `GameEvent.TRADE_COMPLETED`. New `offer`/`accept`/`decline` commands (`commands/trade.py`); added `"offer"` to the parser's `OBJECT_VERBS` (grammar.py) so `offer X to Y` splits roles the same way `give X to Y` does. 7 new unit tests. |

## Sprint 29 — Transit & travel systems ✅

**Goal:** The signature Materia-Magica-inspired feature — multiple travel modes between areas
(ferry, rail, balloon, caravan) that are slow or fast, run end-to-end (express) or make multiple
stops (local), and animate on the minimap. Built on scheduler + world clock + weather + WS push.
**See [`transit_systems.md`](archive/transit_systems.md).**

| # | Task | Status |
|---|------|--------|
| 29.1 | Data model (`TransitLine`/`TransitStop`/`TransitVehicleState`) + YAML `transit:` section + validators; data-driven modes/speeds/stopping patterns | [x] `TransitLine`/`TransitStop` tables (`models/transit.py`) — no `TransitVehicleState` table (superseded per `transit_systems.md` §4: runtime position is the Sprint 21 `MobileRouteState`, keyed `route_id=f"transit:{line_id}"`, wired in Sprint 29.2). World YAML `transit.lines` + validators: stop `room_id`/`ticket_item_id` resolve, `vehicle_room_id` exists with no static exits, sequences contiguous from 0, express lines have ≥2 boarding stops, `blocking_weather` values are real weather states. 12 new unit tests (import/export/reimport round-trip + 5 validator-rejection tests). |
| 29.2 | Scheduler-driven vehicle state machine (at_stop→in_transit→arrive, reverse/loop); moving-room `board`/`disembark`/`schedule`; ticket-item gating | [x] `services/transit.py`'s `TransitService` builds a Sprint 21 `RouteSpec`/`RouteHooks` per `TransitLine` at app lifespan (`load_lines()`) and starts it — no new state machine, entirely the Tier 1 route runner. `may_depart` grounds weather-sensitive lines when `WorldClock.weather` is in `blocking_weather`; `on_depart`/`on_arrive` narrate to both the station and the vehicle room. New `board [line]`/`disembark` (`leave`)/`schedule` (`timetable`) commands (`commands/transit.py`) gate on live vehicle status + stop position, validate/consume tickets, and move the player between the station room and the vehicle room. `register_all_commands` gained an optional `transit=` kwarg (`TransitService` needs the game engine + `ConnectionManager` at construction, so it can't live in the no-arg `ServiceContainer`) — every existing call site is unaffected. 10 new unit tests. |
| 29.3 | `transit_update` WS message + minimap marker animation (interpolated between stop coords); weather grounding/delay (balloon/ferry) | [x] Backend: `TransitService._build_hooks()` implements `on_tick` hook that emits `transit_update` messages with interpolated position, progress, ETA, and mode. `_build_spec()` sets `tick_pushes=5` for lines with `animate_minimap: true`. Weather grounding already works via `may_depart` hook checking `WorldClock.weather`. Frontend: `app.js` adds a `transit_update` handler that receives position/progress data, interpolates between stop coords, and renders a mode-specific emoji icon (⛴/🚂/🎈/🐎) on the minimap SVG using the existing coordinate-scaling system. 9 new unit tests verify message format, hook execution, and tick_pushes configuration. |

## Sprint 30 — Quests & puzzles depth ✅

**Goal:** Branching, consequence-bearing quests and environmental/lore puzzles (pillars #3–4).
Extends the stage/flag quest system with branch conditions and mechanism puzzles.

| # | Task | Status |
|---|------|--------|
| 30.1 | Branch conditions + consequence side-effects on quests (world-state/standing changes); NPC memory of past interactions | [x] Stage `branches` (conditions + `next_stage` + `side_effects`) evaluated once a stage's own `conditions` pass; first branch whose extra conditions pass wins, applying its `side_effects` via the existing `npc/side_effects.py` registry and advancing to `next_stage` (`null` completes the quest). Legacy linear stages (no `branches`) unchanged — full backward compat. New `terminal: true` stage flag completes regardless of array position (a branch target isn't necessarily last in `stages`). Quest conditions moved off a hardcoded if/elif chain onto a new pluggable `game/quest_conditions.py` registry (mirrors `npc/dialogue_conditions.py`). New `NpcMemory` table/repo (`models/npc_memory.py`) + `remember` dialogue side effect + `npc_remembers` dialogue/quest condition: a memory key is scoped per-(player, NPC), so the same key ("helped") means something different for each NPC without pre-naming a flag per pair. `game/reputation_conditions.py` gained `adjust_reputation` (the consequence counterpart to its existing `min_reputation` gate). 16 new unit tests. |
| 30.2 | Mechanism & item-combination puzzles on `ItemInstance.state` (levers, dials, sequences) via pluggable conditions/side-effects; timed clock-driven quest events | [x] New `"mechanism"` standard component (`game/standard_components.py`): `Item.mechanism_states` (ordered list) + `mechanism_side_effects` (keyed by state name, fired once on transition-into via the shared side-effects registry — typically `set_flags`, which `Exit.condition_flags`/dialogue/quest gates already consume, so solving is a one-way trigger). New `turn`/`pull`/`activate` commands cycle state. `Item.combination_side_effects` (checked both directions) makes a successful `use X with Y` apply a real consequence, not just flavor text. New `services/quest_timer.py`'s `QuestTimerService` (engine-holding schedulable, `RestockService`'s shape) sweeps active quest progress on `TIME_ADVANCED`: `timeout_ticks`/`on_timeout` (fallback `next_stage`/`message`/`set_flags`) branches or fails a quest if the player doesn't act in time — data-driven, no per-quest code. New `PlayerQuestProgress.stage_started_epoch` (game-epoch) backs the math; a new `/partials/quest-tracker` route + per-player `state_change` push live-refreshes the one affected player's tracker (quest state is private, not room-broadcast). 26 new unit tests total (mechanism, timer, item-combination, world-schema round-trip/validation). |

## Post-tier-split band (Sprints 31–33) — next up

> **Sequencing note (2026-07-05).** The Tier 1/Tier 2/web split shipped in v0.15.0–0.31.1
> (engine/ is import-pure; 24 feature packages under `features/`; `webui/player` + `webui/admin`;
> the boundary is enforced by `tests/unit/test_tier_boundaries.py`). These three sprints capture
> the remaining tier-split follow-ons plus the highest-value UX/wishlist gaps surfaced along the
> way. **Combat and PvP are set aside to [`wishlist.md`](wishlist.md)** (2026-07-05) — they kept
> forcing roadmap renumbering; ready-to-restore specs live there. See
> [`tier_split_refactor.md`](tier_split_refactor.md).

## Sprint 31 — Finish the tier split: feature-UI seam, toggling & doc refresh ✅

**Goal:** Close out the deliberately-deferred, additive pieces of the tier split and make
feature toggling real. Everything here is non-breaking (the app ships and passes today).
**Complete (v0.31.4–0.32.0)** — the tier split is now fully done (all steps 0–13, see
[`tier_split_refactor.md`](tier_split_refactor.md)).

| # | Task | Status |
|---|------|--------|
| 31.1 | `WebHost` abstraction (tier split step 10c): multi-directory Jinja `ChoiceLoader` + a panel/slot registry, so a feature can contribute templates/panels instead of the single hard-coded template dir | [x] `WebHost` + `Panel` classes; `add_template_dir`/`add_panel`/`add_static`/`add_script` + `build_jinja_environment()`. 9 unit tests. |
| 31.2 | Optional `presentation.py` feature-UI seam (tier split §1c / step 11); prove it by re-homing the existing transit minimap (Sprint 29.3) onto the seam — loads only when the feature *and* the web host are enabled | [x] Feature manifests gain optional `presentation` field (dotted path to module with `register(web_host)`). `webui/player.__init__` loads presentations via `create_web_host()` + `load_feature_presentations()`. Wired into main.py lifespan. Transit feature has `presentation.py` registering minimap panel as proof. Tier boundary test updated to allow web imports in presentation.py. |
| 31.3 | Make Tier 2 feature **services** manifest-gated (today only `economy`/`bank`/`fatigue` are; the rest are built unconditionally in `main.py`/`ServiceContainer`), then add feature enable/disable integration tests (tier split step 12b) | [x] All Tier 2 services now gated (`movement`/`inventory`/`dialogue`/`quest`/`character_info`/`exploration`/`journal`/`trade` + main.py's `light_fuel`/`restock`/`quest_timer`/`transit`); only Tier 1 `save` is unconditional. `register_all_commands` + `main.py` guard every feature. 4 new `test_feature_toggling.py` integration tests. |
| 31.4 | Rewrite the tier-split-stale structure docs beyond the current banners — `architecture.md` §4 tree, `tier_modules.md` tables, `architecture_tiers.md` body → engine/features/webui; graduate §1c "adding feature UI" into `admin_builder_guide.md` (step 13b) | [x] `architecture.md` §4 tree + `tier_modules.md` + `architecture_tiers.md` body rewritten to the shipped layout; new "Extending the UI: Feature Panels" chapter in `admin_builder_guide.md` (+ `LORECRAFT_FEATURES` config row). Tier split fully complete. |

## Sprint 32 — Player onboarding & account UX

**Goal:** Make first contact a real arrival and give players an account-level home for
preferences. From [`wishlist.md`](wishlist.md) (Player Creation / Preferences / Accessibility).
Username + password validation already shipped (v0.31.0); this builds on it.
**Status:** 32.2 (preferences) + 32.3 (accessibility) shipped (v0.33.0–0.34.0); **32.1 deferred**
(2026-07-05, user decision — intro-trigger UX to be revisited).

| # | Task | Status |
|---|------|--------|
| 32.1 | In-game character-creation / intro walkthrough — authored like dialogue/quests (YAML + the dialogue & side-effect registries), **skippable and repeatable**, runs once after first spawn (no in-engine special-casing) | [ ] **Deferred** (2026-07-05): trigger UX (opt-in `tutorial` vs. auto-open-once) is a product choice to settle first; needs a guide NPC + onboarding dialogue tree authored in `world.yaml` + a config-driven first-spawn hook. |
| 32.2 | Per-account **preferences layer** — one settings blob on the account (display density, feed verbosity, panel visibility, timestamp format, reduced-motion for transit/map animation) that the render layer reads in exactly one place | [x] Opaque `Player.preferences` blob (engine-stored, webui-interpreted); `webui/player/preferences.py` owns schema/defaults/validation; `resolve_preferences()` read in one place (`/game` SSR context → `prefs`); `/settings` page to view/update; `hidden_panels` gates game.html panels; `.density-compact`/`.reduced-motion` CSS. 24 tests. |
| 32.3 | **Accessibility mode** — semantic HTML/ARIA, high-contrast / screen-reader-friendly, colourblind-safe palette, real font scaling (a genuine browser-client differentiator; cheap now, costly to retrofit) | [ ] |

## Sprint 33 — Reporting & content-tooling polish ✅

**Goal:** Small, self-contained, combat-independent wins surfaced during the split + wishlist.
**Complete** — guided `/report` (33.1) shipped; the page-length wishlist quick-win (33.2) shipped
(further stretch quick-wins remain optional under 33.2).

| # | Task | Status |
|---|------|--------|
| 33.1 | Guided, multi-turn `/report` flow (category → title → detail) replacing the current one-line note; keep the existing Sprint 10.5 issues pipeline underneath | [x] Bare `report` opens a flag-driven wizard (category→title→detail, `cancel` aborts); web input routes to it via `resolve_command_text` (like dialogue). `report <text>` one-liner unchanged. Same `create_issue()` pipeline underneath. 13 tests. |
| 33.2 | (stretch) Prioritized wishlist quick-wins pulled as scoped — e.g. clickable-link and page-length preferences (feed into the Sprint 32.2 blob), lore/journal surfacing | [x] Page-length quick-win: `feed_page_length` preference (20/40/80) added to the 32.2 blob and driving the `/game` feed load limit + settings select. Further quick-wins (clickable links, lore surfacing) remain open under this stretch item. |

## Sprint 34 — Player-reported command polish ✅

**Goal:** Close the two open player reports in `docs/issues.yaml` — small, self-contained
command wins that improve day-to-day play. Both came in via the in-game `/report` pipeline.
**Complete** — both player reports resolved; no open issues remain.

| # | Task | Status |
|---|------|--------|
| 34.1 | `help <command>` shows detailed help for one command (usage, aliases, scope) instead of always dumping the full list; bare `help` unchanged ([`issue-7502f412`](issues.yaml)) | [x] `help <verb>` shows that command's help text, aliases, and scope; unknown verb reports not-found; bare `help` unchanged. issue-7502f412 resolved. 3 tests. |
| 34.2 | `score` command — a player progress report (level/xp, quest completion, coins/net worth, reputation, discoveries) reading existing stats/quest/economy state; no new persistent schema ([`issue-257c6643`](issues.yaml)) | [x] `score` in the character feature aggregates level/xp, quests (completed/active), wealth (carried + banked), reputation count, discoveries (rooms/NPCs). Reads existing tables only; degrades to zeros. issue-257c6643 resolved. 4 tests. |

---

*Updated 2026-07-07 — archived the **performance & scaling band (35–37)**, **Sprint 39** (timed room effects), **Sprint 45** (chat/feed split; its cosmetic mobile tab-collapse leftover kept as a standalone backlog item), and **Sprints 52–55** (global channels, marks, celestial cycles, context-attached commands) here, clearing the active roadmap. 37.1 + Sprint 38 (scheduler batching / concurrency gate) were deferred to [`wishlist.md`](wishlist.md), not completed.*

*Last updated: 2026-07-05 — **Combat & PvP set aside to [`wishlist.md`](wishlist.md)** (former Sprints 61–64 + the PvP-consent portion of 65) to stop them forcing roadmap renumbering; ready-to-restore specs preserved there. Added the **Performance & scaling band (66–69)** and the `scripts/perf_baseline.py` baseline harness (v0.36.3–0.36.4). Earlier (2026-07-04) — **[Sprint 30](#sprint-30--quests--puzzles-depth-) complete**, closing out every non-combat/PvP Tier 2 sprint (22–30). Branching quests (stage `branches`: conditions + `next_stage` + `side_effects`, backward-compatible with pre-existing linear quests), NPC memory (`models/npc_memory.py`, scoped per-player-per-NPC), a new pluggable `game/quest_conditions.py` registry, mechanism items (levers/dials via a new `"mechanism"` standard component + `turn`/`pull`/`activate` commands), item-combination consequences (`Item.combination_side_effects`), and `services/quest_timer.py`'s `QuestTimerService` (timed clock-driven quest stage deadlines, `RestockService`'s scheduler shape). 26 new tests; full suite (739 unit/integration + 10 e2e + 5 simulation) green. Version bumped to 0.14.0. Sprints 31–35 (combat core, combat commands/UI, combat testing, PvP consent, multiplayer trade/PvP/transit tests) remain — deliberately out of scope for this pass.

Earlier — **[Sprints 20](#sprint-20--ledger--atomic-transfer-) and [21](#sprint-21--scheduled-moving-entity-moving-room-) complete**, closing out the Tier 1 engine-core band. `models/ledger.py`'s `CoinBalance` + `services/ledger.py`'s `LedgerService` add coin balances on any registered holder and one atomic multi-leg `execute_exchange()` for coins and items together (validate-all-then-apply-all, no partial exchange). `models/mobile.py`'s `MobileRouteState` + `services/mobile_route.py`'s `MobileRouteService` add the generic scheduled route runner (ping-pong or circular waypoint cycling, position interpolation, pluggable `RouteHooks`) that transit will ride on — reuses `SchedulerService` for all timing, no second timing mechanism. 29 new tests, all green first run; full suite (538 unit/integration + 3 e2e + 5 simulation) green. Version bumped to 0.3.0. Tier 2 feature band now open, starting at [Sprint 22](#sprint-22--standard-item-components--definition-fields).

Earlier — **[Sprint 19](#sprint-19--meters--timed-effects-) complete**: `models/meters.py`'s `Meter`/`ActiveEffect` + `game/meters.py`/`game/effects.py`/`game/traits.py` registries + `services/meters.py`/`services/effects.py` are the meter, timed-effect, and trait primitives — the "hp" `MeterDef` migration deletes `PlayerStats.current_hp`/`NPC.current_hp` outright as the proof, and Tier 1 registers its promised active-effect/trait `ModifierSource`s + `TraitSource` with Sprint 18's resolver. `GameContext` gained required `session`/`meters`/`effects` fields. 25 new tests caught two real bugs (both scheduler sweeps read expired ORM attributes after `session.commit()`). Full suite (509 unit/integration + 3 e2e + 5 simulation) green.

Earlier same day — **[Sprints 17](#sprint-17--determinism-seedable-rng--skill-check-) and [18](#sprint-18--modifier-resolution-) complete**: `game/rng.py`'s `GameRng` is now the one sanctioned randomness source (ruff `TID251` bans bare `random` in `src/`), threaded through `GameContext`/`build_game_context()`/`SchedulerEventContext`/`clock/weather.py`; `game/modifiers.py`'s `resolve()` is the one stacked-bonus resolver (fixed add→mult→clamp bucket order); `game/checks.py`'s `skill_check()` composes both into the one roll-under-d100 helper every future skill/combat/barter check will share. 18 landed ahead of its listed position (it has no dependencies) specifically to unblock 17.2, which needs the `Modifier` type. 21 new unit tests; full suite green.

Earlier same day — **[Sprint 16](#sprint-16--item-locationownership--instance-state) complete**: `ItemStack`/`ItemInstance` unified item location/ownership model + `ItemLocationService` (spawn/destroy/materialize/move) ships, replacing `Player.inventory`/`RoomItem` outright across the full 17-file blast radius (see `engine_core.md` §3.2's table). `ComponentRegistry`/`HolderRegistry` scaffolded per spec (Tier 1 registers no components, three built-in holder types). 23 new invariant tests; full unit/integration/e2e/simulation suite green unchanged (no audit-event schema drift).

Earlier same day — **Design docs are now implementation-ready** (deep-dive revision for handoff): [`engine_core.md`](engine_core.md) §3 carries full Tier 1 specs (schemas, APIs, invariants, migration blast-radius tables, per-sprint tests); [`combat_system.md`](combat_system.md) rewritten off the pre-Tier-1 code (seeded rng, hp meter, slot-based weapon, real event names); [`inventory_equipment.md`](archive/inventory_equipment.md), [`trade_economy.md`](archive/trade_economy.md), [`transit_systems.md`](archive/transit_systems.md), and [`death_resurrection.md`](death_resurrection.md) aligned to the primitives (superseded drafts called out inline; engine_core §4 lists every resolution). Earlier same day: inserted an engine-first **Tier 1 primitives band ([Sprints 16–21](#sprint-16--item-locationownership--instance-state))** ahead of the feature modules per [`engine_core.md`](engine_core.md), and **renumbered the feature band +6 to [Sprints 22–35](#sprint-22--standard-item-components--definition-fields)** (item components 22, equipment 23, traits/skills 24, exploration 25, map/mobile 26, condition 27, trade 28, transit 29, quests/puzzles 30, combat 31–33, PvP 34, multiplayer tests 35). Sprint refs in the feature design docs + `wishlist.md` were updated to match. Earlier same day: added `engine_core.md` (Tier 1/2/3 boundary); re-sequenced the feature band around design pillars (Exploration > Trading > Questing > Puzzles; combat supporting). [Sprints 4–15](#sprint-4--player-authentication-production-hardening-) complete; foundation gate green.*
