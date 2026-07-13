# Lorecraft — Roadmap

**A concise list of *remaining* work.** Every **completed** sprint — 1–34 (foundation, the Tier 1
engine-core primitives, the Tier 2 pillar feature band, the tier-split follow-ons), the performance
& scaling band (35–37), and everything since (39–55) — lives in
[`roadmap_completed.md`](roadmap_completed.md) with full task-level detail. Per-version detail is in
[`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and the deferred
multiplayer test pass + concurrency/batching gates are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-13, v0.96.0 on main; Sprints 73, 74, 75 & 76 all merged)

**Everything through Sprint 76 is merged to main** (currently at v0.96.0, which ships Sprints 73,
74, 75, and 76 in sequence — see `../CHANGELOG.md`).
Foundation, the Tier 1 engine-core primitives, the full Tier 2 pillar band (exploration ·
trading · questing · puzzles · inventory/equipment · traits/skills · character condition ·
transit), the tier-split refactor, the performance/WAL band, the observability pair (56–57), the
client themes/layouts band (58–60, 62), multi-level map (66), the webui-theming skill (67), escort
quests (68), and the **Phase A scripting engine** (v0.57–0.70) plus its **Sprint 69** world-building
polish (weather-narration voice, indoor rooms, the world-building agent skill, zone-qualified
addressing, and the flag-condition canonicalization to `actor_has_flag`/`actor_lacks_flag`),
**Sprint 70** social emotes (`wave`, `point`) and the `quests` command, **Sprint 71** backlog
cleanup (admin Issues editable priority/description, Room schema zone/room_type split + admin World
filter, player map shape stability, help command styling), and **Sprint 72** backlog cleanup
(scripting catalog feature-enable, admin DB reseed, process supervisor + graceful restart, mobile chat
tab-collapse) have all shipped. Detail in
[`roadmap_completed.md`](roadmap_completed.md) and [`../CHANGELOG.md`](../CHANGELOG.md).

*(Out-of-band, v0.90.0: the `consumables` feature — `eat`/`drink`/`quaff` with one-shot
`heal`/`apply_effect` item descriptors — closed the "no consumption mechanic" gap that Phase 2.4
world content had been blocked on; see `roadmap_world.md` P2.4. Also out-of-band, v0.90.1–0.90.2:
a world-content polish pass — P4.1 descriptive-writing upgrade of six flat Cogsworth rooms plus an
NPC memorable detail, and the P4.2/P4.3/P4.4 thematic-consistency, lighting, and safe-rest audits,
all of which found the existing 104-room world already correct. See `roadmap_world.md` and
[`../CHANGELOG.md`](../CHANGELOG.md) for full detail.)*

**[Sprint 73 — Generalized rewards + XP/leveling core](#sprint-73--generalized-rewards--xpleveling-core)
is implementation-complete** — all of 73.1–73.10 shipped as commits on branch
`sprint-73-progression` (full task-level detail in that section's table above), plus a critical
fix found in review (new characters never got a `PlayerStats` row — see that section's callout
row). Delivers a real XP/leveling system split along the mechanism/policy (Tier 1/Tier 2) line:
**Tier 1** (`engine/game/leveling.py`) is the generic, data-driven leveling mechanism — detect
threshold crossings, apply an arbitrary reward payload to player properties — while **Tier 2**
(`features/progression/`) owns the opinionated, **admin-tunable** policy of what each level
rewards (coins + skill points), plus the unified quest/level-up reward interpreter. Resolves the
long-standing "does Lorecraft have leveling?" question (**yes**) and delivers Sprint 71.5 (quest
XP rewards) as Sprint 73.6. **Merged to main as v0.94.0.**

**[Sprint 75 — SQLite additive-column auto-migration + Sprint 71.2 PK-rename data migration](#sprint-75--sqlite-additive-column-auto-migration--sprint-712-pk-rename-data-migration)
is also implementation-complete** — all of 75.1–75.5 shipped as commits on branch
`sprint-75-db-migration` (full task-level detail in that section's table above), plus two
hardening fixes found in review. A generic reflection-based scanner replacing the ~14
hand-written `_ensure_sqlite_compat_columns` shims and covering the ~22 previously-unshimmed
additive columns, plus deliberate data migrations for the two Sprint 71.2 PK-adjacent renames
(`regionpricing.area_id`→`zone`, `room.area_id`→`zone`/`room_type`) that Sprint 71.2 itself never
built `db.py` handling for. Foundation-band infrastructure (data-integrity / startup-robustness),
not a feature. **Merged to main as v0.94.0.**

**[Sprint 74 — Skill tree & ability unlocks](#sprint-74--skill-tree--ability-unlocks)
is implementation-complete** — all of 74.1–74.8 shipped as commits on branch
`sprint-74-skill-tree` (full task-level detail in that section's table above), plus a
mid-review fix for an unconsumed `haggler` price modifier — see that section's callout rows.
Delivers the skill-point *sink* Sprint 73 set up: a data-driven `world_content/skill_tree.yaml`
tree, bought with skill points, unlocking abilities in all three flavors — active utility verbs
(`forage`/`sense`/`pick`), passive modifiers (`mule`/`sharp_eyes`/`haggler`), and an
interaction/dialogue unlock (`silver_tongue`, gating a persuasion option in the innkeeper Mira's
dialogue tree). **Merged to main as v0.95.0.**

**[Sprint 76 — Economy live-tuning admin UI](#sprint-76--economy-live-tuning-admin-ui)
is implementation-complete** — all of 76.1–76.7 shipped as commits on branch
`sprint-76-economy-live-tuning` (full task-level detail in that section's table above, including
commit hashes). Closes the `economy.regions` live-tunability gap (flagged in the Backlog table
below and in `AGENTS.md`'s "prefer live-tunable configuration" section) by adding the missing
**admin layer** — a repo read method plus an admin router/UI tab — over the `RegionPricing`
table, which is **already** DB-backed and live-read (since Sprint 71.2); **no schema change**, so
the Database Specialist gate was skipped. Delivers a new **Economy** admin tab: any admin role
can view every zone's `region_mult`/`bias`, and a superadmin can retune either live, with no
restart or reseed. Pure Tier 2 (`features/economy/`) + composition-layer (`webui/admin/`) work —
no `engine/` changes. Gate-clean (lint, typecheck, 1459 unit tests, 54 e2e tests, tier boundaries,
90.91% coverage; Code Reviewer found no blocking issues). **Merged to main as v0.96.0.**

Sprint 73's cleanup backlog (stale `PlayerStats` fallbacks, the first-access race investigation,
and the stale e2e seed workaround) is fully closed as of 2026-07-13 — see the struck-through
Backlog table entries below for the resolution detail on each.

**Set aside to [`wishlist.md`](wishlist.md):** combat & PvP (ready-to-restore specs — a supporting
system, not the centerpiece); the multiplayer trade/transit **test pass**; and the deferred
**scheduler-commit batching (37.1)** + **concurrency/threading gate (38)** — the measured wall was
fsync serialization on a single SQLite writer, which WAL (37.4) already removed, so threads wouldn't
help. Revisit the latter only if a *post-WAL* realistic-load test shows a hard single-process wall.

Design anchors: [`engine_core.md`](engine_core.md) (the Tier 1/2/3 boundary) and
[`wishlist.md`](wishlist.md) (design pillars + idea backlog).

---

## Recently completed (56–69)

Sprints **56–69** (observability pair, client themes/layouts, classic CRT mode, multi-level map, escort quests, and the Sprint 69 scripting-engine world-building polish) are complete and shipped through **v0.75.0**. Their full task-level detail was moved to [`roadmap_completed.md`](roadmap_completed.md) on 2026-07-10 to keep this file to *remaining* work.

---

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
| — | **Critical fix found in review (not a numbered task): new characters never got a `PlayerStats` row.** Discovered by the Frontend Specialist while building 73.4/73.9's UI: **no code path created `PlayerStats` for a new player** — not character creation, not save/load — across all four creation call sites (`webui/player/auth.py`, `rendering.py`, `frontend.py`, `world/bootstrap.py`). Every reward/XP grant to a genuinely new character silently no-op'd (`apply_rewards` reads `ctx.player_repo.stats(player_id)` and treats `None` as "can't hold XP," per its own docstring) — this would have shipped broken for any player who didn't happen to inherit a pre-seeded stats row. Fixed by making `PlayerRepo.stats()` get-or-create instead of get-or-`None`. | [x] Shipped as commit `c3b818a` on branch `sprint-73-progression`. Non-blocking follow-ups (stale defensive-fallback comments left at ~8 call sites, a low-probability first-access race, and a test that still seeds a stats row unnecessarily) are tracked in the Backlog table below. |

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

**Goal:** close the `economy.regions` live-tunability gap flagged in the Backlog table below and
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

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| ~~Player-facing bug reports~~ | **Done** — `report` one-liner (v0.12.0) + guided category→title→detail wizard (Sprint 33.1). Only the `report player <name>` moderation branch + an `Issue.target_player_id` field remain — see [`wishlist.md`](wishlist.md) → *Issue-report wizard*. |
| Database inspector / state editor | Admin tool for advanced troubleshooting |
| ~~Economy: make `economy.regions` pricing live-tunable~~ | Added 2026-07-12. **Done as [Sprint 76 — Economy live-tuning admin UI](#sprint-76--economy-live-tuning-admin-ui) (implementation-complete 2026-07-13, awaiting Integrator merge).** `RegionPricing` was already DB-backed and live-read (since Sprint 71.2) — the gap was purely the missing admin layer (repo read-all method + admin router/UI), not a schema change. |
| Multiplayer trade/transit test pass | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Multiplayer sim-test coverage* (was Sprint 65) |
| Combat & PvP | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Combat, reframed* (ready-to-restore specs) |
| ~~Sprint 73 cleanup: stale defensive `PlayerStats` fallbacks~~ | Added 2026-07-12. **Done 2026-07-13** (commit `70ffcab` on `sprint73-cleanup-backlog`). Removed the dead `is not None`/`or PlayerStats(...)` fallbacks at all real call sites (`webui/player/session.py`'s encumbrance-snapshot strength default and attributes-block fallback; `engine/services/save.py`'s `_apply_stats_snapshot`; six feature-service `record_use` guard sites). A follow-up (commit `92edad1`, after a Code Reviewer catch) restored the `.stats()` call's get-or-create *side effect* at those six sites — the truthiness check was dead, but the `.stats()` call itself was load-bearing for a brand-new character's first skill-use action — with a regression test added. |
| ~~Sprint 73: low-probability first-stats-access race~~ | Added 2026-07-12. **Investigated 2026-07-13, accepted risk — no code change.** Traced the commit flow (one `Session` per websocket command, committed centrally in `main.py`) with SQLite in WAL mode (serializes writers) and `PlayerStats.player_id` as PK: the outcome of the race is a clean PK `IntegrityError` at commit time (caught, logged as an in-game error, no corruption, no duplicate row, succeeds on retry), not data corruption. A correct fix would need `begin_nested()`/SAVEPOINT scoping (per the precedent in `engine/services/effects.py:115`) to avoid a naive flush+rollback discarding other pending changes in the same unit of work — judged disproportionate to the risk. Revisit only if the DB moves to a true multi-writer backend or an engine-wide busy-timeout/retry policy is added. |
| ~~Sprint 73: `test_progression_ui.py` still seeds `PlayerStats` directly~~ | Added 2026-07-12. **Done 2026-07-13** (commit `1a050de` on `sprint73-cleanup-backlog`). Removed the `_seed_player_stats()` workaround and both call sites; rewrote the module docstring's "known backend gap" paragraph into past-tense historical context pointing at the fixing commit `c3b818a`. Both tests now exercise the real `PlayerRepo.stats()` get-or-create path organically via `create_character()` + quest completion. |

*Already-implemented items previously listed here (bug/todo letterbox, encumbrance/wear slots, the
simulation CLI, the analytics dashboard) were promoted to shipped sprints — see
[`roadmap_completed.md`](roadmap_completed.md).*

---

## Sprint numbering (avoid duplicates)

- **Used (all complete):** 1–34 (incl. 10.5), 35–37 (performance band; 37.1 deferred to
  [`wishlist.md`](wishlist.md)), 39 (timed room effects), 40–42 (admin console live-refresh,
  registered issue components, Issues-tab filter/sort), 43–49 (session record/playback,
  weather-driven effects, chat/feed split, item discovery journal, follow command, scavenger hunts,
  encumbrance + analytics dashboard), 50 (e2e browser coverage), 51 (four more analytics widgets +
  the `target_id` audit fix), 52 (global channels & the channel framework), 53 (collectible marks),
  54 (celestial cycles), 55 (context-attached commands). Full detail in
  [`roadmap_completed.md`](roadmap_completed.md).
- **Deferred to [`wishlist.md`](wishlist.md):** 37.1 (scheduler-commit batching) and 38
  (concurrency/threading gate) — never developed; fsync, not CPU, was the wall.
- **Used (all complete):** 56 (structured output-type tagging), 57 (request tracing & crash
  reports), 58 (selectable client themes & layouts), 59 (classic old-MUD CRT mode, incl. 59.1–59.8),
  60 (per-mode typography + minimap de-boxing, 60.1–60.2), **62** (layout/scheme axis split,
  Standard+Dock rebuild, full Stats pane — shipped v0.54.0, backfilled to this ledger 2026-07-09;
  see its row under Sprint 59 above), 66 (multi-level map foundation — `map_z`), 67 (webui-theming
  agent skill + `MODE_DEFAULT_THEME` single-sourcing fix), 68 (escort quests).
- **Retired to [`wishlist.md`](wishlist.md):** 61, 63, 64 (combat core, combat commands/UI, combat
  testing, PvP consent — 62 was reclaimed for the unrelated axis-split work above since combat
  stayed shelved), 65 (multiplayer trade/transit tests). Don't reuse 61/63/64/65 for unrelated
  work — restore under fresh numbers if that work returns.
- **Used (all complete):** 69 (scripting-engine world-building polish — 69.1–69.8, v0.71.0–0.75.0:
  weather-narration voice, admin-teleport fix, indoor rooms, world-building skill, zone addressing,
  admin clock auto-refresh, admin World-by-zone, flag-condition rename). The Phase A scripting engine
  itself (v0.57–0.70, branch `scripting_engine`) predates this ledger; it is tracked in
  `docs/scripting_engine_design.md`.
- **Used (all complete):** 70 (social emotes & QoL commands — 70.1 emotes, 70.2 `quests` command, v0.78.0).
- **Used (all complete):** 71 (backlog cleanup: admin UI + player-facing bugs — 71.1–71.4 done, 71.5 blocked; v0.91.0: admin Issues editable priority/description, Room zone/room_type split, admin World filter, player map shape stability, help styling).
- **Used (all complete):** 72 (backlog cleanup: tooling tech-debt + admin ops + mobile polish —
  72.1 scripting-catalog feature-enable + `register_spec` migration, 72.2 admin DB wipe/reseed from
  `world.yaml`, 72.3 admin engine restart + process supervision, 72.4 mobile chat tab-collapse; v0.92.0).
- **Used (all complete, pending Integrator merge/version-bump):** 73 (Generalized rewards +
  XP/leveling core — **mechanism/policy split** per the 2026-07-12 correction: 73.1 Tier 1 generic
  leveling *mechanism* [data-driven `LevelCurve` + `award_xp` + `apply_stat_deltas`, no reward
  opinions], 73.2 `skill_points` field, 73.3 Tier 2 `ProgressionConfig` [YAML-seeded,
  admin-tunable], 73.4 **live admin-tune endpoint** [WorldClock pattern], 73.5 Tier 2 reward
  interpreter, 73.6 quest rewards rewired [delivers 71.5 / `issue-39d3fcb8`], 73.7 level-up payout
  from config, 73.8 exploration reroute, 73.9 level-up UX, 73.10 docs; plus a critical
  review-found fix (new characters never got a `PlayerStats` row, commit `c3b818a`). Branch
  `sprint-73-progression`, all tasks `[x]` — see the Sprint 73 section above for the full commit
  list.
- **In design: 74** (Skill tree & ability unlocks — the skill-point *sink*; 74.1 data-driven
  `skill_tree.yaml` + loader, 74.2 node persistence [`unlocked_nodes` + `ability.<id>` flag],
  74.3 `train` command, 74.4 passive modifier source, 74.5 active-verb gating pattern + `forage`,
  74.6 two more active verbs `sense`/`pick`, 74.7 interaction/dialogue unlock example, 74.8 UI/docs;
  **74-OI-1 RESOLVED 2026-07-12**: build all three ability flavors — active utility verbs [first-class],
  passive modifiers, interaction unlocks — data-driven; new **74-OI-5**: ability verbs live in their
  thematic feature, not `progression`).
- **Used (all complete, pending Integrator merge/version-bump):** 75 (SQLite additive-column
  auto-migration + Sprint 71.2 PK-rename data migration; 75.1 generic reflection additive-column
  scanner, 75.2 delete the 14 hand-written shims, 75.3 Room `area_id`→`zone`/`room_type` in-place
  migration, 75.4 RegionPricing `area_id`→`zone` PK table-rebuild migration, 75.5 full test matrix;
  foundation-band infra, not a feature; OPEN ITEMs A [tier-placement correction:
  composition-layer, not Tier 1 engine, with a bounded content-literal exception], B [force
  Ashmoore `region_mult` to 1.0], C [rebuild-with-fold over drop-empty for `regionpricing`] all
  resolved per their stated recommendations; two review-found hardening fixes, commits `8183be3`
  and `8b1795b`). Branch `sprint-75-db-migration`, all tasks `[x]` — see the Sprint 75 section
  above for the full commit list.
- **Used (all complete, pending Integrator merge/version-bump): 76** (Economy live-tuning admin
  UI — 76.1 `EconomyRepo.all_regions()`, 76.2 admin router GET/POST for `RegionPricing`, 76.3
  "Economy" admin tab, 76.4 backend unit tests, 76.5 frontend e2e tests, 76.6 Test & QA pass, 76.7
  docs; no schema change — `RegionPricing` already existed and was already live-read; pure Tier 2
  + composition-layer work, no `engine/` changes; Database Specialist gate skipped). Branch
  `sprint-76-economy-live-tuning`, all tasks `[x]` — see the Sprint 76 section above for the full
  commit list.
- **Next new sprint: 77.** Don't recycle a number that appears here or in
  [`roadmap_completed.md`](roadmap_completed.md).

---

## Playtesting (Ashmoore dev world)

`start.sh` copies `test_dbs/lorecraft-dev-game.db`, which is built from `world_content/world.yaml`.

Regenerate after world edits:

```bash
python scripts/import_world.py --fresh --db test_dbs/lorecraft-dev-game.db
```

**Starting room:** `village_square` as `player-1`

| Try | Command |
|-----|---------|
| Move east | `go east` → market stalls |
| Pick up coin | `take coin` |
| Talk to Mira | `go west` → Wandering Crow Inn, then `talk mira` |
| Quest hook | Choose "Any news around town?" in dialogue |
| Wear armor | `go north` → forge, `take helmet`, `wear helmet`, `remove helmet` |
| Locked door | `north`→`north`→`east` to Vault Hall; `take good key`, `unlock east`, `go east` → Inner Vault (the Bad Key won't work) |
| Context verb | `go south` past the creek to the Ruined Chapel; `read altar` (reveals lore) |

Empty databases import `world_content/world.yaml` on startup (configurable via `LORECRAFT_WORLD_YAML_PATH`). Integration tests use the same Ashmoore data — no parallel hardcoded world in production code.
