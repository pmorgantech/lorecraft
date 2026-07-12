# Lorecraft — Roadmap

**A concise list of *remaining* work.** Every **completed** sprint — 1–34 (foundation, the Tier 1
engine-core primitives, the Tier 2 pillar feature band, the tier-split follow-ons), the performance
& scaling band (35–37), and everything since (39–55) — lives in
[`roadmap_completed.md`](roadmap_completed.md) with full task-level detail. Per-version detail is in
[`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and the deferred
multiplayer test pass + concurrency/batching gates are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-11, v0.91.0)

**Everything through Sprint 71 is complete** and merged to main.
Foundation, the Tier 1 engine-core primitives, the full Tier 2 pillar band (exploration ·
trading · questing · puzzles · inventory/equipment · traits/skills · character condition ·
transit), the tier-split refactor, the performance/WAL band, the observability pair (56–57), the
client themes/layouts band (58–60, 62), multi-level map (66), the webui-theming skill (67), escort
quests (68), and the **Phase A scripting engine** (v0.57–0.70) plus its **Sprint 69** world-building
polish (weather-narration voice, indoor rooms, the world-building agent skill, zone-qualified
addressing, and the flag-condition canonicalization to `actor_has_flag`/`actor_lacks_flag`),
**Sprint 70** social emotes (`wave`, `point`) and the `quests` command, and **Sprint 71** backlog
cleanup (admin Issues editable priority/description, Room schema zone/room_type split + admin World
filter, player map shape stability, help command styling) have all shipped. Detail in
[`roadmap_completed.md`](roadmap_completed.md) and [`../CHANGELOG.md`](../CHANGELOG.md).

*(Out-of-band, v0.90.0: the `consumables` feature — `eat`/`drink`/`quaff` with one-shot
`heal`/`apply_effect` item descriptors — closed the "no consumption mechanic" gap that Phase 2.4
world content had been blocked on; see `roadmap_world.md` P2.4. Also out-of-band, v0.90.1–0.90.2:
a world-content polish pass — P4.1 descriptive-writing upgrade of six flat Cogsworth rooms plus an
NPC memorable detail, and the P4.2/P4.3/P4.4 thematic-consistency, lighting, and safe-rest audits,
all of which found the existing 104-room world already correct. See `roadmap_world.md` and
[`../CHANGELOG.md`](../CHANGELOG.md) for full detail.)*

**Next: Sprint 72** — backlog cleanup: tooling tech-debt + admin ops + mobile polish. See
[Sprint 72](#sprint-72--backlog-cleanup-tooling-tech-debt--admin-ops--mobile-polish) below.

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
| 71.5 | **Quest XP rewards.** | [ ] **BLOCKED** — needs a product decision first: does Lorecraft have any leveling/XP progression system at all? If no, this may close as works-as-designed; if yes, it needs its own dedicated XP-system sprint before design work here can start. |

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
| 72.1 | **Scripting catalog generator enables features (Phase A tech-debt #2).** `docs/scripting_api.md` is generated by `_load_scripting_vocabulary()` in `src/lorecraft/tools/world_cli.py` (~L211–226), which calls `discover_features()` (import-only — fires module-level `@register_spec` decorators) but never *enables* any feature, so enable-time vocabulary is missing from the doc. Proof: `features/reputation/conditions.py::register()` (L81–100) runs only via the reputation feature's `register_fn` at enable-time, and it uses the registries' plain `.register(name, fn)` rather than `register_spec(name, fn, VocabEntry(...))` — so `actor_reputation_at_least`/`adjust_reputation` never reach the catalog even if features *were* enabled. **Two-part fix:** (a) the generator enables every discovered feature via a lightweight stub `AppState` (note `register_fn(state)` also wires real services — see `features/loader.py::wire_features`; reputation's `_wire` already ignores `state`); (b) affected features migrate their enable-time registrations from plain `register()` to `register_spec()` with a `VocabEntry`. Suggested shape: each feature exposes a state-free `register_vocabulary()` that both its `register_fn` and the generator call. Composition-layer only — no engine→feature tier violation (`world_cli.py` already imports features). Regenerate + re-check via `make scripting-docs`. | [ ] not started |
| 72.2 | **Admin: DB wipe + reseed from `world.yaml` (lower-risk half of the "restart + reload" ask).** Admin-triggered action that wipes and reseeds the game DB from `world_content/world.yaml`, reusing the existing `scripts/import_world.py --fresh` path (the same one `start.sh` uses to build the seed DB). Data-driven — reseeds from the YAML, no hardcoded content. Shippable independently of the engine restart (72.3). Motivation: test updates pushed to `main` end-to-end from the browser without shelling in. | [ ] not started |
| 72.3 | **Admin: restart the running engine process (riskier half — needs a supervisor).** `start.sh` launches `uvicorn lorecraft.main:app` directly with **no supervising process**, so a naive in-process exit would just kill the server handling the request. Scope the supervision mechanism *first* (a wrapper/supervisor process, or an exec-replace pattern) before adding any admin button; escalate if it needs launch-script changes beyond an additive hook. | [ ] not started — blocked on a restart-mechanism design decision |
| 72.4 | **Mobile chat tab-collapse polish.** Leftover from Sprint 45.3: on small screens the chat pane should collapse into a tab rather than stack. Purely responsive/CSS in the player webui — low risk, no engine touch. | [ ] not started |

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| ~~Player-facing bug reports~~ | **Done** — `report` one-liner (v0.12.0) + guided category→title→detail wizard (Sprint 33.1). Only the `report player <name>` moderation branch + an `Issue.target_player_id` field remain — see [`wishlist.md`](wishlist.md) → *Issue-report wizard*. |
| Database inspector / state editor | Admin tool for advanced troubleshooting |
| Multiplayer trade/transit test pass | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Multiplayer sim-test coverage* (was Sprint 65) |
| Combat & PvP | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Combat, reframed* (ready-to-restore specs) |

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
- **Planned (not yet shipped):** 72 (backlog cleanup: tooling tech-debt + admin ops + mobile polish —
  72.1 scripting-catalog feature-enable + `register_spec` migration, 72.2 admin DB wipe/reseed from
  `world.yaml`, 72.3 admin engine restart [needs a supervisor design], 72.4 mobile chat tab-collapse).
- **Next new sprint: 73.** Don't recycle a number that appears here or in
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
