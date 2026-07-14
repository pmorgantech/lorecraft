# Lorecraft — Roadmap

**A concise list of *remaining* work.** Every **completed** sprint — 1–34 (foundation, the Tier 1
engine-core primitives, the Tier 2 pillar feature band, the tier-split follow-ons), the performance
& scaling band (35–37), and everything since (39–83) — lives in
[`roadmap_completed.md`](roadmap_completed.md) with full task-level detail. Per-version detail is in
[`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and the deferred
multiplayer test pass + concurrency/batching gates are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-14, v0.104.0 on develop; Sprints 1–84 all shipped)

**Everything through Sprint 84 is shipped on `develop`** (currently v0.104.0). `roadmap.md` now tracks
remaining work only; the full task-level history for completed Sprints 1–84 lives in
[`roadmap_completed.md`](roadmap_completed.md), with release-level detail in
[`../CHANGELOG.md`](../CHANGELOG.md).

The latest completed band is archived as Sprints 77–80: the Discipline/Ability replacement for the
old skills/skill-tree split, the Sprint 79 cleanup pass for its review follow-ups, and the Sprint
80 world-system pass for zone climate, data-driven spawns, room loot tables, ambient room flavor,
NPC route hooks, and admin multi-weather controls. Sprint 81 adds the Ashmoore graveyard, the
Brass Vaults steampunk zone, new mobile hazards, and local quest content using those world-system
surfaces. Sprint 82 adds fixed-location Ashmoore shops for potions, food/drink, general goods,
and armory basics using stationary NPC shopkeepers and the existing economy model. Sprint 83
expands Ashmoore's scavenger-hunt content pattern with spread placement for 3-7 item hunts and
speed-scaled coin reward tiers. Sprint 84 adds database query-span logging and an analyzer for
slow/frequent statements plus index candidates, so future schema/index work is evidence-driven.

Sprint 73's cleanup backlog and the 2026-07-13 UI-cohesion items are closed and preserved in
[`roadmap_completed.md`](roadmap_completed.md).

**Set aside to [`wishlist.md`](wishlist.md):** combat & PvP (ready-to-restore specs — a supporting
system, not the centerpiece); the multiplayer trade/transit **test pass**; and the deferred
**scheduler-commit batching (37.1)** + **concurrency/threading gate (38)** — the measured wall was
fsync serialization on a single SQLite writer, which WAL (37.4) already removed, so threads wouldn't
help. Revisit the latter only if a *post-WAL* realistic-load test shows a hard single-process wall.

Design anchors: [`engine_core.md`](engine_core.md) (the Tier 1/2/3 boundary) and
[`wishlist.md`](wishlist.md) (design pillars + idea backlog).

---

## Backlog

| Item | Notes |
|------|-------|
| Offline/IRL commands (`/system`, `@someone`) | Parser scope distinction; after core commands stable |
| Async event-bus support | When webhooks/external integrations need it (audit §3.2) |
| Sounds, GPT descriptions, online world-building | Wishlist |
| Database inspector / state editor | Admin tool for advanced troubleshooting |
| Multiplayer trade/transit test pass | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Multiplayer sim-test coverage* (was Sprint 65) |
| Combat & PvP | Set aside 2026-07-05 to [`wishlist.md`](wishlist.md) → *Combat, reframed* (ready-to-restore specs) |
| E2E coverage gap for the new discipline/ability command surface | Added 2026-07-13 (Sprint 78 Test & QA pass). `train`/`abilities`/`disciplines`/`forage`/`pick`/`sense` are unit-tested but not directly exercised by browser-driven e2e tests. Not a current defect — flagged as worth a follow-up e2e pass. |
| Ability tuning live-admin controls | Added 2026-07-14 (Sprint 79 triage). Per-ability `cost`, `cooldown_seconds`, resource costs, and proficiency-growth values (`improve_chance`/`max_rank`) remain static YAML by design. Build a DB-backed, admin-live-tunable config only if admins ask to retune these without restart/reseed; do not build it speculatively. |


---

## Sprint numbering (avoid duplicates)

- **Used (complete):** 1–84, except for deliberately skipped/deferred numbers below. Full task
  detail lives in [`roadmap_completed.md`](roadmap_completed.md).
- **Deferred to [`wishlist.md`](wishlist.md):** 37.1 (scheduler-commit batching), 38
  (concurrency/threading gate), 61/63/64 (combat/PvP work), and 65 (multiplayer trade/transit
  test pass).
- **Next genuinely free sprint number:** 85. Do not recycle a number that appears here, in
  [`roadmap_completed.md`](roadmap_completed.md), or in [`wishlist.md`](wishlist.md).

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
| Shop village | `go east`, `shop`; then `east` to Vale's General Store or `south` to Hearthloaf Bakery and `shop` again |
| Quest hook | Choose "Any news around town?" in dialogue |
| Wear armor | `go north` → forge, `take helmet`, `wear helmet`, `remove helmet` |
| Locked door | `north`→`north`→`east` to Vault Hall; `take good key`, `unlock east`, `go east` → Inner Vault (the Bad Key won't work) |
| Context verb | `go south` past the creek to the Ruined Chapel; `read altar` (reveals lore) |

Empty databases import `world_content/world.yaml` on startup (configurable via `LORECRAFT_WORLD_YAML_PATH`). Integration tests use the same Ashmoore data — no parallel hardcoded world in production code.
