# Lorecraft — Roadmap

**A concise list of *remaining* work.** Every **completed** sprint — 1–34 (foundation, the Tier 1
engine-core primitives, the Tier 2 pillar feature band, the tier-split follow-ons), the performance
& scaling band (35–37), and everything since (39–83) — lives in
[`roadmap_completed.md`](roadmap_completed.md) with full task-level detail. Per-version detail is in
[`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and the deferred
multiplayer test pass + concurrency/batching gates are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-16, v0.135.1; Sprints 1–87 and 89 implemented; Sprint 88 deferred pending playtesting)

`roadmap.md` now tracks remaining work only. The full task-level history for completed Sprints
1–87 and the 2026-07-16 admin/tooling tranche lives in
[`roadmap_completed.md`](roadmap_completed.md), and release-level detail is in
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

**Set aside to [`wishlist.md`](wishlist.md):** the multiplayer trade/transit **test pass**; and the
deferred **scheduler-commit batching (37.1)** + **concurrency/threading gate (38)** — the measured
wall was fsync serialization on a single SQLite writer, which WAL (37.4) already removed, so threads
wouldn't help. Revisit the latter only if a *post-WAL* realistic-load test shows a hard
single-process wall.

**Activated (2026-07-14):** Combat & PvP (Sprints 86–88, see below) — the Scheduled Intent design
from [`combat_design.md`](combat_design.md). Combat is a **supporting** system (Exploration >
Trading > Questing > Puzzles) — it serves stories; stealth/persuasion/bribery/flee are first-class
alternatives. It ships as `features/combat/` with no Tier 1 edits needed.

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
| E2E coverage gap for the new discipline/ability command surface | Added 2026-07-13 (Sprint 78 Test & QA pass). `train`/`abilities`/`disciplines`/`forage`/`pick`/`sense` are unit-tested but not directly exercised by browser-driven e2e tests. Not a current defect — flagged as worth a follow-up e2e pass. |
| Ability tuning live-admin controls | Added 2026-07-14 (Sprint 79 triage). Per-ability `cost`, `cooldown_seconds`, resource costs, and proficiency-growth values (`improve_chance`/`max_rank`) remain static YAML by design. Build a DB-backed, admin-live-tunable config only if admins ask to retune these without restart/reseed; do not build it speculatively. |

### Admin UI & tooling triage (2026-07-16)

This section folds the Admin & Monitoring brainstorm into the active queue. Order is based on
usefulness to current development, player/debugging payoff, and implementation effort. Completed
or already-in-flight surfaces are struck through so they stay visible as context without becoming
new work.

**Already covered / do not re-scope:**

- ~~Category-based admin shell with contextual sub-tabs~~ — present on the `admin-ui` branch:
  Overview, Tuning, World, Content, Moderation, System.
- ~~Live tuning tabs for Clock, Weather, Combat, Progression, and Economy~~ — existing or
  `admin-ui` branch surfaces backed by DB/admin endpoints where those live dials exist.
- ~~System controls for graceful restart, crash reports, trace lookup, analytics, audit~~ —
  restart/crashes/analytics/audit already exist; trace lookup is present on the `admin-ui` branch.
- ~~Player record editing from the player list~~ — present on the `admin-ui` branch for username,
  respawn room, PvP consent, ghost state, and flags JSON.
- ~~Issues, News, Help, Accounts, World room editing, and Changesets~~ — already implemented admin
  tooling; keep improving ergonomics only when specific friction appears.

**Backlog candidates, ordered:**

| Priority | Item | Usefulness / payoff | Effort | Notes |
|----------|------|---------------------|--------|-------|
| P1 | Observation routing for live session viewer | Converts Observe from a useful snapshot into true live support/debug tooling | L | Active Sprint 90 on `admin-ui`. Scope: sanitized player output stream, command-history/event stream, and no execute-as-player mode. |
| P1 | Audit trace/crash drill-down links | Speeds incident debugging from one audit row to related trace/crash context | M | Build on `/admin/audit`, `/admin/observability/traces/{id}`, and crash report endpoints. |
| P2 | Builder Studio validation and diff preview | High builder payoff after the shell exists | L | Add YAML validation and read-only diff preview before any visual editor. Live publish/hot-reload stays behind explicit review. |
| P2 | Weather-front and WorldClock forecast timeline | Makes live tuning safer by showing expected world impact | M | Extend the existing scheduler timeline rather than creating a separate dashboard. |
| P3 | Admin command console execution | Useful but risky; lower priority than purpose-built controls | M | Requires allowlist, RBAC, confirmation gates, and mandatory audit reason before enabling. |
| P3 | Alerts/notifications evaluator | Nice ops payoff after metrics are real | M | Rule storage/evaluator first; external webhooks remain wishlist until local alerts prove useful. |

**Keep in [`wishlist.md`](wishlist.md) until demand or design evidence appears:**

- Interactive snoop / force-command mode, break-glass workflows, and replay-as-player.
- Full visual Behavior Tree editor and Behavior Tree step debugger.
- Sandbox/replay instances for historical audit windows.
- Area locking, collaborative review queues, comments, and A/B testing for behavior variants.
- Public/community stats APIs and external monitoring integrations.

---

## Sprint numbering (avoid duplicates)

- **Used (complete):** 1–87 and 89, except for deliberately skipped/deferred numbers below. Full task
  detail lives in [`roadmap_completed.md`](roadmap_completed.md).
- **Deferred to [`wishlist.md`](wishlist.md):** 37.1 (scheduler-commit batching), 38
  (concurrency/threading gate), and 65 (multiplayer trade/transit test pass).
- **Deferred pending playtesting evidence:** 88 (Combat Phase 4 advanced-depth bucket).
- **Completed and archived (2026-07-16):** 89 (Admin NPC/AI read-only runtime endpoint).
- **Newly active (2026-07-16):** 90 (Admin observation routing for live session viewer).
- **Newly active (2026-07-16):** 91 (Body equipment and condition view).
- **Next genuinely free sprint number:** 92. Do not recycle a number that appears here, in
  [`roadmap_completed.md`](roadmap_completed.md), or in [`wishlist.md`](wishlist.md).

---

## Combat (Scheduled Intent)

Sprints 85–87 are complete and archived in
[`roadmap_completed.md`](roadmap_completed.md#sprints-8587--scheduled-intent-combat-foundation-tactics-and-content-power).
Combat remains built as `features/combat/`, with opinion/data in Tier 2. Sprint 88 is now being
handled one narrow layer at a time; speculative control-heavy depth remains deferred.

### Sprint 88 — Combat Phase 4: Advanced

**Goal:** Narrow depth layers gated behind demonstrated need. Do not build speculatively. Formation
mechanics, near/far tactical bands, grappling, flanking, screening, and full PvP duel rules are
explicitly out of the active roadmap.

**Depends on:** Sprints 85–87 + playtesting/balance evidence.

**Tier:** Tier 2 (all features/combat/). Each item independently deferrable.

- [x] 88.1 Wounds + body locations — persist after health recovery. v0.136.0 records active
  `CombatWound` rows for positive combat damage and includes wound metadata in resolution/audit
  payloads; no stat penalties yet.
- [ ] 88.2 Terrain & cover as narrow defense modifiers — only if authored encounters need it
- [ ] 88.3 Combo systems — only if data-authored actions need follow-up hooks
- [ ] 88.4 Simultaneous-planning encounter mode (optional, arena/boss) — alternate combat_mode
- [ ] 88.5 Mounted / siege combat — content-specific, not general-purpose formations

---

## Sprint 91 — Body Equipment & Condition View

**Goal:** give players and admins a body-centric view that shows all wear/wield slots, what is
equipped or empty, and current body-part condition from persistent combat wounds.

**Tier split:** Tier 1 remains unchanged. Tier 2 equipment defines body/slot presentation policy;
Tier 2 combat contributes wound condition rows; web/admin hosts render the composed view.

- [x] 91.1 Body schema/view model — canonical body parts and equipment slot grouping.
- [x] 91.2 Equipment body view — populate every slot with equipped/worn/wielded item state.
- [x] 91.3 Condition body view — group `CombatWound` rows by body part/severity/status.
- [x] 91.4 Player UI + command — add browser body panel plus `body` / `condition` command.
- [ ] 91.5 Admin/player observe integration — show body/equipment/condition in admin Observe.
- [ ] 91.6 Tests/docs — focused coverage and player/admin documentation.

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
