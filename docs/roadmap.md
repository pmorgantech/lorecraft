# Lorecraft — Roadmap

**A concise list of *remaining* work.** Every **completed** sprint — 1–34 (foundation, the Tier 1
engine-core primitives, the Tier 2 pillar feature band, the tier-split follow-ons), the performance
& scaling band (35–37), and everything since (39–55) — lives in
[`roadmap_completed.md`](roadmap_completed.md) with full task-level detail. Per-version detail is in
[`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and the deferred
multiplayer test pass + concurrency/batching gates are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-11, v0.90.2)

**Everything through Sprint 70 is complete** and merged to main.
Foundation, the Tier 1 engine-core primitives, the full Tier 2 pillar band (exploration ·
trading · questing · puzzles · inventory/equipment · traits/skills · character condition ·
transit), the tier-split refactor, the performance/WAL band, the observability pair (56–57), the
client themes/layouts band (58–60, 62), multi-level map (66), the webui-theming skill (67), escort
quests (68), and the **Phase A scripting engine** (v0.57–0.70) plus its **Sprint 69** world-building
polish (weather-narration voice, indoor rooms, the world-building agent skill, zone-qualified
addressing, and the flag-condition canonicalization to `actor_has_flag`/`actor_lacks_flag`), and
**Sprint 70** social emotes (`wave`, `point`) and the `quests` command have all shipped. Detail in
[`roadmap_completed.md`](roadmap_completed.md) and [`../CHANGELOG.md`](../CHANGELOG.md).

*(Out-of-band, v0.90.0: the `consumables` feature — `eat`/`drink`/`quaff` with one-shot
`heal`/`apply_effect` item descriptors — closed the "no consumption mechanic" gap that Phase 2.4
world content had been blocked on; see `roadmap_world.md` P2.4. Also out-of-band, v0.90.1–0.90.2:
a world-content polish pass — P4.1 descriptive-writing upgrade of six flat Cogsworth rooms plus an
NPC memorable detail, and the P4.2/P4.3/P4.4 thematic-consistency, lighting, and safe-rest audits,
all of which found the existing 104-room world already correct. See `roadmap_world.md` and
[`../CHANGELOG.md`](../CHANGELOG.md) for full detail.)*

**Next: Sprint 71** — backlog cleanup: admin UI + player-facing bugs. See
[Sprint 71](#sprint-71--backlog-cleanup-admin-ui--player-facing-bugs) below.

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
| 71.1 | **Admin Issues panel: editable priority + description.** Backend PUT endpoint already accepts both fields; needs the admin SPA form/UI work. | [ ] not started — waiting on frontend design |
| 71.2 | **Admin World panel: zone + name filter.** Filter room list by zone dropdown (Cogsworth / Whisperwood / Port Veridian / Ashmoore) plus a dynamic name substring search as the admin types. | [ ] not started — frontend shaping the design; will flag if a new `/admin/world` query param is needed |
| 71.3 | **Player map rendering: z-level filtering + shape stability.** Isolate the fix to `rendering.py`; flag if it turns out the `Room` schema itself needs a change (would escalate scope). | [ ] not started — waiting on rendering.py investigation |
| 71.4 | **Help command: better formatting (bold/color).** Presentation-only improvement to the `help` command's output. | [ ] not started |
| 71.5 | **Quest XP rewards.** | [ ] **BLOCKED** — needs a product decision first: does Lorecraft have any leveling/XP progression system at all? If no, this may close as works-as-designed; if yes, it needs its own dedicated XP-system sprint before design work here can start. |

---

## Backlog

| Item | Notes |
|------|-------|
| Scripting catalog generator enables features (Phase A tech-debt #2) | `docs/scripting_api.md` is generated after `discover_features()` (import only), so feature-**enable**-time vocabulary (reputation's `actor_reputation_at_least`/`adjust_reputation`, escort, …) is missing from the doc. **Two parts** (found 2026-07-10): (a) the generator must *enable* features (invoke each `FeatureManifest.register_fn`) after discovery — which needs a stub/lightweight `AppState`, since `register_fn(state)` also wires services; and (b) those enable-time registrations currently use the registries' plain `register` (no catalog descriptor), so they must migrate to **`register_spec`** with a `VocabEntry` before they can appear in the catalog. Do both, or the catalog stays incomplete. Best done with a state-free `register_vocabulary()` split each feature exposes to both its `register_fn` and the generator. |
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| Mobile chat tab-collapse polish | Cosmetic leftover from Sprint 45.3 (finished by Sprint 52 otherwise) — on small screens the chat pane should collapse into a tab rather than stack. Purely responsive/CSS. |
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
- **Used:** 71 (backlog cleanup: admin UI + player-facing bugs — 71.1–71.5, in progress).
- **Next new sprint: 72.** Don't recycle a number that appears here or in
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
