# Lorecraft — Roadmap

**A concise list of *remaining* work.** Every **completed** sprint — 1–34 (foundation, the Tier 1
engine-core primitives, the Tier 2 pillar feature band, the tier-split follow-ons), the performance
& scaling band (35–37), and everything since (39–55) — lives in
[`roadmap_completed.md`](roadmap_completed.md) with full task-level detail. Per-version detail is in
[`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and the deferred
multiplayer test pass + concurrency/batching gates are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-12, v0.92.0)

**Everything through Sprint 72 is complete** and merged to main.
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

**Next: Sprints 73–74** — **progression** (design complete). The 2026-07-11 scope expansion (classic DikuMUD-style earn→level→train→abilities, deliberately scoped down for *now*) splits across two sprints: **[Sprint 73 — Generalized rewards + XP/leveling core](#sprint-73--generalized-rewards--xpleveling-core)** (a mechanism/policy split per the 2026-07-12 correction: **Tier 1** provides the generic, data-driven leveling mechanism — detect threshold crossings, apply an arbitrary reward payload to player properties — while **Tier 2 `features/progression/`** owns the opinionated, **admin-tunable** policy of what each level rewards [coins + skill points], plus the unified quest/level-up reward interpreter), then **[Sprint 74 — Skill tree & ability unlocks](#sprint-74--skill-tree--ability-unlocks)** (the genuinely-new design surface: spending skill points on a data-driven tree that unlocks abilities in **all three flavors** — active utility verbs like `forage`/`sense`/`pick`, passive modifiers, and interaction/dialogue unlocks; ability-scope fork resolved 2026-07-12). Resolves the long-standing "does Lorecraft have leveling?" question (**yes**, 2026-07-12) and delivers Sprint 71.5 (quest XP rewards) as **Sprint 73.4**.

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
| 71.5 | **Quest XP rewards.** | [ ] **UNBLOCKED → scoped into Sprint 73.** Product decision (2026-07-12): Lorecraft **does** have XP/leveling progression, so this is no longer blocked. The dedicated design now exists — see [Sprint 73 — Generalized rewards + XP/leveling core](#sprint-73--generalized-rewards--xpleveling-core) below; implementation is **Sprint 73.4** (rewire `_award_rewards` onto the new generalized reward path so quest `rewards.xp` — and now `coins`/`skill_points` — actually apply). Closes when 73.4 ships. |

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
YAML edit + reseed (or Sprint 72.2's `POST /admin/world/reseed`). See the admin-tunable OPEN ITEM below.

| # | Task | Status |
|---|------|--------|
| 73.1 | **Tier 1 generic leveling *mechanism* (data-driven, policy-free).** New `src/lorecraft/engine/game/leveling.py`, pure like `engine/game/checks.py::skill_check`. It provides "the ability to do things," not opinions: (a) a **data-driven curve value object** `LevelCurve` — holds the threshold data (`base`, `step`, or an explicit `thresholds` list), **passed in as data**, not hardcoded module constants; `xp_for_level(curve, level) -> int`. (b) `award_xp(stats: PlayerStats, amount: int, curve: LevelCurve) -> LevelUpResult(leveled_up, old_level, new_level, levels_gained)` — adds XP, rolls `level` across **one or more** thresholds per the passed curve, updates `xp_to_next`, and returns how many levels crossed. It grants **nothing** beyond xp/level and **does not know** coins/skill-points exist — the caller decides per-level rewards. (c) a generic property applier `apply_stat_deltas(stats, deltas: Mapping[str, int])` — the "update an array of player properties" mechanism: validate each key is a known numeric `PlayerStats` field (whitelist: `xp`, `skill_points`, future stat points) and apply the int delta; reject unknown keys. **Pure: no session/IO/`ctx`, no coins (ledger) / items.** Unit tests: single/multi-level rollover, exact-threshold boundary, zero/negative guard, unknown-property rejection, curve driven by passed data. | [ ] |
| 73.2 | **`PlayerStats.skill_points` field (the earn-side currency).** Add `skill_points: int = 0` to `PlayerStats`. Earned this sprint (quests + level-ups), **spent** in Sprint 74's tree — banks until then. Include in the `stats_snapshot` save/load path and admin reseed. Success: fresh player has `skill_points=0`; round-trips through save/load. | [ ] |
| 73.3 | **Tier 2 progression *config* (data-driven **and** admin-tunable).** New `features/progression/` package: a DB-backed `ProgressionConfig` **singleton row** (mirroring the `WorldClock` pattern) holding **both** the curve params (`base`, `step`) **and** the per-level reward *policy* (`coins_per_level`, `skill_points_per_level`). **Seeded from a `progression:` section in `world.yaml`** at import (mirror `_import_economy`, and add it to `export_world_document` so live edits round-trip back to YAML) — data-driven defaults, authorable. Tier 2 reads this row and constructs the Tier 1 `LevelCurve` from its params. This is the "malleable opinionated bit." Success: config seeds from YAML; changing `coins_per_level` there + reseed changes level-up payouts with no code edit. | [ ] |
| 73.4 | **Admin-tunable endpoint (live, no restart) — the "tunable by an admin" ask.** `GET`/`POST /admin/progression/config` mirroring `POST /admin/clock/time-ratio` (`webui/admin/routers/clock.py`): read + edit the 73.3 `ProgressionConfig` row live, commit, and (if any value is cached in the runtime) push it — no reseed, no restart. Admin `index.html` form hook + an e2e/integration test. **This is the piece the correction flagged as most at-risk of under-design; it is now a first-class task, not folded away.** See the admin-tunable OPEN ITEM for the phase-1 fallback. | [ ] |
| 73.5 | **Tier 2 reward *interpreter* (policy → Tier 1 mechanism dispatch).** In `features/progression/`, `apply_rewards(ctx, rewards: JsonObject) -> RewardOutcome` interprets the reward **vocabulary** (`items`/`xp`/`coins`/`skill_points`) and dispatches each to a Tier 1 mechanism: `items` → `ctx.item_location.spawn`; `coins` → `ctx.ledger.credit`; `xp` → `leveling.award_xp` with the curve built from 73.3 config; `skill_points` (and future numeric props) → `leveling.apply_stat_deltas`. **The vocabulary lives here (Tier 2), not in Tier 1** — "which keys count as rewards" is a policy/content choice (see design note). Canonical key **`coins`** (matches `CoinBalance`; `money` tolerated as alias). Returns `RewardOutcome` (amounts granted + any `LevelUpResult`) so callers narrate without re-deriving. Unit tests per key + a combined bundle. | [ ] |
| 73.6 | **Rewire quest rewards onto the interpreter (delivers Sprint 71.5 / `issue-39d3fcb8`).** Replace `features/quests/service.py::_award_rewards` (L195–203) with a single `apply_rewards(ctx, rewards)` call, then narrate (73.9). Quests just *supply the payload* (the authored reward dict); it owns no reward mechanism. Because `_complete_quest` calls `_award_rewards` **per stage**, multi-stage quests award incrementally for free. Success: `world.yaml`'s 605 quest XP goes live; `rewards.coins`/`rewards.skill_points` now function. Closes Sprint 71.5. | [ ] |
| 73.7 | **Level-up rewards = pure Tier 2 policy read (no hardcoded amounts).** When 73.1's `award_xp` reports `levels_gained > 0`, `features/progression/` reads the 73.3 config's `coins_per_level`/`skill_points_per_level`, builds `{"coins": coins_per_level·levels_gained, "skill_points": skill_points_per_level·levels_gained}`, and applies it via the 73.5 interpreter. **No magic constants in code** — the numbers come from the admin-tunable config. Success: crossing a threshold credits coins + skill points at the *configured* rate; changing the rate via 73.4 changes payouts live. | [ ] |
| 73.8 | **Route discovery XP through the mechanism.** `features/exploration/service.py` L62–64's inline `stats.xp += DISCOVERY_XP` bypasses level-up. Replace with `apply_rewards(ctx, {"xp": DISCOVERY_XP})` (or `award_xp` with the config curve) so a threshold-crossing discovery also triggers 73.7's payout. No duplicated threshold math. | [ ] |
| 73.9 | **Level-up feedback (feed message + event + live stats).** On `leveled_up`, the Tier 2 caller emits a feed line (add `MessageType.LEVEL` + `.msg-level` CSS, mirroring Sprint 71.4's `MessageType.HELP`, or reuse `SYSTEM`), `ctx.push_update`s the Stats pane (extend `partials/stats_panel.html` / `webui/player/session.py` to show `skill_points`), and queues a new `GameEvent.PLAYER_LEVELED_UP` (mirror `SKILL_IMPROVED`). Presentation stays in Tier 2 so Tier 1's `leveling.py` stays IO-free. | [ ] |
| 73.10 | **Docs.** `docs/user_guide.md` (how XP is earned; levels pay coins + skill points). `docs/admin_builder_guide.md` (quest `rewards` supports `xp`/`coins`/`items`/`skill_points`; the `world.yaml` `progression:` section; **how to live-tune per-level rewards + the curve from the admin console** [73.4]). No `scripting_api.md` regen (no new `register_spec`). | [ ] |

### Sprint 73 design — the mechanism/policy (Tier 1/Tier 2) split, admin-tunability & naming

> **Provenance.** Research + design 2026-07-12 (branch `sprint-73-leveling-design`, based on
> `2b3253b`/v0.92.1), **revised for the 2026-07-12 mechanism/policy architectural correction**.
> Design-only. Facts verified against the live tree. Forks surfaced with a recommendation, not
> silently decided.

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

**FINDING + OPEN ITEM — what "admin-tunable" means here, and how far to build it in Sprint 73.** The
correction asked whether a *live* admin-editable balance value exists. It does — **two** precedents:

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
**Phasing sub-decision (the real OPEN ITEM):** if 73.4's live endpoint+UI must be cut for scope, the
**minimum honest fallback** is "config in `world.yaml`, tuned via reseed" (pattern 2 only) — still
data-driven, just not live. → **Recommend keeping 73.4 in-sprint** (the `WorldClock` precedent makes the
endpoint cheap and the user asked for it explicitly); drop to the reseed-only fallback only if 73.4
proves heavier than the clock precedent suggests. **Flagged, not silently decided.**

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
| 74.1 | **Data-driven tree definitions + loader.** `world_content/skill_tree.yaml` → a `SkillTreeRegistry` (mirror `features/skills/definitions.py::SkillRegistry` + the `world.yaml` import path). Node schema: `id`/`name`/`description`/`cost`/`prerequisites`/`unlock` (`flags`, optional `modifier`, optional `enables_verb`). Validation: no prerequisite cycles, prereqs exist, `cost >= 1`. **No hardcoded node IDs in `src/`.** Lives under `features/progression/`. Unit tests: load, cycle rejection, missing-prereq rejection. | [ ] |
| 74.2 | **Node persistence (`unlocked_nodes` + `ability.<id>` flag — both now mandatory).** New `PlayerStats.unlocked_nodes: list[str]` (JSON, mirrors `traits`) for query/UI, **and** — because flavors A and C gate on `actor_has_flag` — each purchase also sets `Player.flags["ability.<id>"] = True`. The flag is now load-bearing (the active-verbs decision promoted it from convenience), so this dual-write is a design requirement, not an optimization. Save/load round-trip for both. | [ ] |
| 74.3 | **`train`/`learn` command — spend skill points on a node.** Lists available nodes (prereqs met, affordable) and buys one: check `stats.skill_points >= cost` + prereqs, decrement `skill_points`, record the node in `unlocked_nodes`, set the `ability.<id>` flag, and register any passive `modifier` (74.4). Lives in `features/progression/commands.py`. Refuse with a clear reason on insufficient points / unmet prereqs / already-owned. | [ ] |
| 74.4 | **Passive modifier source (flavor B).** A modifier collection source registered with `engine/game/modifiers.py` that, for each unlocked node carrying a `modifier`, contributes it to the resolver (e.g. `carry_capacity +2`, `skill.perception mult 1.1`, `price.buy mult 0.95`). Proves passive abilities with **zero new verbs**; applies retroactively and free (resolver recomputes per use — see 74-OI-4). Unit test: an unlocked node changes `resolve_carry_capacity`. | [ ] |
| 74.5 | **Active-verb gating pattern + reference verb `forage` (flavor A).** Establish the pattern: a verb registers with `conditions=[..., "actor_has_flag:ability.<id>"]` so it is available (and `help`-listed) only once unlocked. Ship the reference implementation: **`forage`** — in an outdoor room (`Room.indoor == False`), roll `skill_check(survival)` (`game/checks.py`, the `survival` STANDARD_SKILL already exists) to yield a foraged consumable (the `consumables` feature already handles `eat`/`drink`), gated on `ability.forage`. Lives in the thematically-appropriate feature, not `progression` (see 74-OI-5). Unit tests: verb hidden without the flag, succeeds/fails on the skill roll with the flag. | [ ] |
| 74.6 | **Two more active verbs — `sense` + `pick` (flavor A, ≥3 example verbs total).** **`sense`** (aka `perceive`): an enhanced `search` that rolls `skill_check(perception)` to reveal hidden items *and* concealed NPCs in the room, gated on `ability.keen_senses`. **`pick`**: attempt a locked exit *without* a key via `skill_check(lockpicking)` — the world already ships locked doors (Vault Hall) and a key/`unlock` flow, so this is the no-key path — gated on `ability.pick_locks`. Each in its thematic feature (exploration / movement-or-lockpicking), each with hidden-without-flag + skill-roll tests. These three (survival/perception/lockpicking) map onto three existing `STANDARD_SKILLS`, so no invented content. | [ ] |
| 74.7 | **Interaction/dialogue unlock example (flavor C).** Author example `world_content` proving the pure-data path: a `skill_tree.yaml` node whose `unlock.flags` sets `ability.<id>`, plus a `world.yaml` dialogue/context branch gated on `actor_has_flag:ability.<id>` (e.g. a `persuasion`-flavored dialogue option that only appears once an ability is trained). Zero engine work — validates that builders can add interaction abilities without code. | [ ] |
| 74.8 | **UI + docs.** Surface unlocked abilities + spendable skill points (extend `score`/Stats pane or a small `abilities` view listing owned nodes and available buys). `docs/user_guide.md` (earning/spending skill points; that abilities come in active-verb, passive-bonus, and interaction flavors; the starter verbs `forage`/`sense`/`pick`). `docs/admin_builder_guide.md` (authoring `skill_tree.yaml` nodes; the `unlock` block; gating content on `actor_has_flag:ability.<id>`). Regenerate `docs/scripting_api.md` via `make scripting-docs` **only if** an optional `actor_has_ability` alias is added (74-OI-5b) — otherwise no new `register_spec`. | [ ] |

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
- **74-OI-6 — NEW, from the Sprint 73 mechanism/policy correction — is `skill_tree.yaml` "admin-tunable" enough?** The tree (node costs/rewards) is YAML-seeded → DB at import, matching the `economy.regions` precedent: data-driven but **not live** (a cost change needs a reseed). This mirrors the Sprint 73 admin-tunable finding. → **Recommend YAML+reseed for v1** — node costs/prereqs are *structural* content, not a hot balance dial like per-level coin rewards, so the reseed cadence is acceptable; revisit migrating node costs onto the same live `ProgressionConfig`-style mechanism (73.4) only if admins ask to retune tree costs without a reseed. Keeps Sprint 74 consistent with 73's split (Tier 1 reads data; Tier 2/config owns the opinionated, potentially-live values).
- **74-OI-4 — retroactive passives / respec (recommendation stands):** passives apply immediately
  (resolver recomputes per use — free); **no respec** in v1 (defer).

Package placement (`features/progression/`), reward-key (`coins`), and the Sprint 73 forks are settled
in the Sprint 73 design section above; none are changed by the active-verbs decision.

---

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
- **Used (all complete):** 72 (backlog cleanup: tooling tech-debt + admin ops + mobile polish —
  72.1 scripting-catalog feature-enable + `register_spec` migration, 72.2 admin DB wipe/reseed from
  `world.yaml`, 72.3 admin engine restart + process supervision, 72.4 mobile chat tab-collapse; v0.92.0).
- **In design: 73** (Generalized rewards + XP/leveling core — **mechanism/policy split** per the
  2026-07-12 correction: 73.1 Tier 1 generic leveling *mechanism* [data-driven `LevelCurve` +
  `award_xp` + `apply_stat_deltas`, no reward opinions], 73.2 `skill_points` field, 73.3 Tier 2
  `ProgressionConfig` [YAML-seeded, admin-tunable], 73.4 **live admin-tune endpoint** [WorldClock
  pattern], 73.5 Tier 2 reward interpreter, 73.6 quest rewards rewired [delivers 71.5 /
  `issue-39d3fcb8`], 73.7 level-up payout from config, 73.8 exploration reroute, 73.9 level-up UX,
  73.10 docs; OPEN ITEMs: admin-tunable phasing [rec. live endpoint in-sprint, reseed-only fallback],
  package placement [`features/progression/`], `coins` vs `money`, perk-beyond-rewards [rec. rewards-only]).
- **In design: 74** (Skill tree & ability unlocks — the skill-point *sink*; 74.1 data-driven
  `skill_tree.yaml` + loader, 74.2 node persistence [`unlocked_nodes` + `ability.<id>` flag],
  74.3 `train` command, 74.4 passive modifier source, 74.5 active-verb gating pattern + `forage`,
  74.6 two more active verbs `sense`/`pick`, 74.7 interaction/dialogue unlock example, 74.8 UI/docs;
  **74-OI-1 RESOLVED 2026-07-12**: build all three ability flavors — active utility verbs [first-class],
  passive modifiers, interaction unlocks — data-driven; new **74-OI-5**: ability verbs live in their
  thematic feature, not `progression`).
- **Next new sprint: 75.** Don't recycle a number that appears here or in
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
