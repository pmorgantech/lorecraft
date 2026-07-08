# Lorecraft — Roadmap

**A concise list of *remaining* work.** Every **completed** sprint — 1–34 (foundation, the Tier 1
engine-core primitives, the Tier 2 pillar feature band, the tier-split follow-ons), the performance
& scaling band (35–37), and everything since (39–55) — lives in
[`roadmap_completed.md`](roadmap_completed.md) with full task-level detail. Per-version detail is in
[`../CHANGELOG.md`](../CHANGELOG.md); the idea backlog, set-aside combat/PvP specs, and the deferred
multiplayer test pass + concurrency/batching gates are in [`wishlist.md`](wishlist.md).

Legend: `[x]` done · `[~]` in progress · `[ ]` not started.

---

## Where things stand (2026-07-08, v0.46.3)

**Sprint 56 (56.1–56.4 done, 56.5 partial) is implemented; Sprint 57 is drafted, not started.**
Everything through **Sprint 55** is complete and merged to local `main`. Foundation, the Tier 1
engine-core primitives, the full Tier 2 pillar feature band (exploration · trading · questing ·
puzzles, plus inventory/equipment, traits/skills, character condition, transit), the tier-split
refactor, the performance/WAL band, and the recent content/UX band (timed room effects, chat/feed
split → global channels, marks, celestial cycles, context-attached commands) have all shipped. See
[`roadmap_completed.md`](roadmap_completed.md).

**Sprint 56** (structured output-type tagging) and **Sprint 57** (request tracing & crash reports)
are scoped below — an observability/output-infra pair identified 2026-07-08 comparing Lorecraft
against a modern-MUD-engine research pass ([`wishlist.md`](wishlist.md) "Engine architecture" +
"Operations, security & deployment" sections). Both are cheap now and expensive to retrofit once
combat/quests are emitting output at volume, so they're queued ahead of the backlog below.

**Candidate work** also lives in the *Backlog* table below and in [`wishlist.md`](wishlist.md)
(audited against the code 2026-07-07 — bullets that were already shipped are annotated there). The
nearest small, well-scoped backlog item is the **`report player <name>` moderation branch** of the
issue-report wizard (the guided flow itself already shipped in Sprint 33.1). **Next new sprint after
56–57: 58.**

**Set aside to [`wishlist.md`](wishlist.md):** combat & PvP (ready-to-restore specs — a supporting
system, not the centerpiece); the multiplayer trade/transit **test pass**; and the deferred
**scheduler-commit batching (37.1)** + **concurrency/threading gate (38)** — the measured wall was
fsync serialization on a single SQLite writer, which WAL (37.4) already removed, so threads wouldn't
help. Revisit the latter only if a *post-WAL* realistic-load test shows a hard single-process wall.

Design anchors: [`engine_core.md`](engine_core.md) (the Tier 1/2/3 boundary) and
[`wishlist.md`](wishlist.md) (design pillars + idea backlog).

---

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
| 56.5 | Sweep existing `ctx.say(...)` call sites in `engine/` and `features/`; assign a type where the intent is clear from context, leave genuinely ambiguous ones on the `"system"` default rather than guessing. | [~] Retyped the ~20 call sites with unambiguous, content-verified intent: `quests/service.py` + `hunts/service.py` + `marks/service.py` → `QUEST`; `commands/social.py` + `npc/dialogue.py`'s precondition failures → `WARNING`; `npc/dialogue.py`'s actual NPC speech line → `TELL`. Sampled other candidate files (`fatigue/service.py`) and found no clean fit — left on `SYSTEM` rather than force a stretch mapping. ~260 call sites across the remaining 22 files are still on the `SYSTEM` default; a full sweep is a follow-on, not blocking. |

## Sprint 57 — Request tracing & crash reports

**Goal:** extend Sprint 13's structured logging (correlation/transaction IDs) and command latency
percentiles with two admin-facing debugging tools that don't exist today: a per-command trace of
what actually happened (conditions checked, events fired, DB commits) and a saved, browsable record
of unhandled exceptions. Today an admin diagnosing a bad command has only raw log grep by
`transaction_id` — no structured "what ran" view and nothing captured for an exception beyond
whatever hits stdout.

| # | Task | Status |
|---|------|--------|
| 57.1 | Trace buffer: within `bind_transaction_context()`'s scope, collect an ordered list of trace spans (condition evaluations, event dispatches, DB commits — reusing `time_operation`'s existing timing) keyed by `transaction_id`. In-memory ring buffer over the last N commands — not persisted, matching the "measure, don't over-build" caution already applied to the deferred concurrency work. | [ ] |
| 57.2 | `GET /admin/trace/<transaction_id>` — returns the captured spans for one recent command (404 once it's aged out of the ring buffer). | [ ] |
| 57.3 | Crash capture: a handler at both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`) that, on an unhandled exception, persists a `CrashReport` row (transaction_id, correlation_id, player_id, command text, stack trace, timestamp) to the audit DB and returns a friendly in-game error instead of a raw disconnect/500. | [ ] |
| 57.4 | `GET /admin/crashes` (list) + `GET /admin/crashes/<id>` (detail) endpoints and a Crash Reports tab in the admin console, reusing the Audit tab's table/detail pattern. | [ ] |
| 57.5 | Document both features (usage, endpoints, retention) in [`observability.md`](observability.md) and cross-link from the admin guide's Troubleshooting section. | [ ] |

---

## Backlog

| Item | Notes |
|------|-------|
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
- **Drafted, not started:** 56 (structured output-type tagging), 57 (request tracing & crash
  reports) — scoped above 2026-07-08 from the same gap in the numbering left by the earlier
  combat renumber.
- **Reserved but never used:** 58–60 (remainder of the gap from an earlier combat renumber).
- **Retired to [`wishlist.md`](wishlist.md):** 61–64 (combat core, combat commands/UI, combat
  testing, PvP consent), 65 (multiplayer trade/transit tests). Don't reuse these numbers for
  unrelated work — restore under fresh numbers if that work returns.
- **Next new sprint after 56–57: 58.** Don't recycle a number that appears here or in
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
