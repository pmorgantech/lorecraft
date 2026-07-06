# Changelog

All notable changes to Lorecraft will be documented in this file.

## [0.40.3] - 2026-07-05

### Added

- **Sprint 45.1 — chat channel threaded end to end (Phase 1 of the chat/feed split,** [`chat_feed_split.md`](docs/chat_feed_split.md)**).** Chat and room narration used to share one channel with no signal to tell them apart; there is now a `chat` category at every seam. `GameContext` gains `say_chat()`/`tell_room_chat()` backed by new `chat_messages`/`room_chat_messages` lists (mirroring `messages`/`room_messages`); `say` speaks through them (the "Say what?" prompt stays narrative); `broadcast_command_effects` emits room chat as `feed_append` with `message_type:"chat"`; the WS `command_result` carries a `chat_messages` field; the HTMX command path renders the actor's echo as `type:"chat"` feed items; and `PlayerPreferences.separate_chat` (default **off**) is stored/resolved/round-tripped ready for the Phase 2 dual-pane UI. **Default UX is unchanged** — both render paths degrade the new type into today's single feed until Phase 2 routes by the preference. Movement/action narration (`tell_room`) is untouched and stays narrative. 7 new unit tests (say routing, broadcast tagging + speaker exclusion, preference round-trip); default + simulation suites green.

## [0.40.2] - 2026-07-05

### Fixed

- **Unhandled `WebSocketDisconnect` noise on every disconnect-during-broadcast.** Two-part fix for the "Exception in ASGI application" traceback the CI logs surfaced: (1) the disconnect handler now deregisters the leaving socket **before** the `player_left` broadcast — that broadcast has no `exclude`, so it used to try to send to the just-closed socket; (2) `ConnectionManager.send_to_player` treats **any** send failure as a dead connection (logged with traceback, connection dropped) instead of catching only `RuntimeError` — the concrete exception is host-framework-specific (starlette raises `WebSocketDisconnect` when a broadcast races a closing socket), and one dead socket must never break a broadcast to everyone else. Unit-tested (send failure drops the connection without raising; a broadcast survives one dead socket and still reaches the rest).

## [0.40.1] - 2026-07-05

### Fixed

- **Flaky golden audit diff on CI (Sprint 43.1 follow-up).** `replay_scenario` read the audit trail *after* closing the player's WebSocket, racing the server's `player_disconnected` lifecycle event — on the CI runner the disconnect landed first and the golden diff failed with one extra event. The trail is now captured **before** the socket closes (every command's audit writes are committed before its `command_result` is sent, so the capture is stable after the last reply), keeping the golden exactly the gameplay the scenario drove, never transport teardown. Verified stable across repeated local runs; no golden regeneration needed.

## [0.40.0] - 2026-07-05

### Added

- **Sprint 43 complete — session record & playback (43.3: mixed-scenario soak + CI knob)** ([`session_replay.md`](docs/session_replay.md) Phase 3). New `mix_scenarios(server, scenarios, repeats=…, jitter_ms=…)` in `tests/simulation/replay.py` replays **distinct recorded sessions concurrently** — each scenario gets its own fresh player driving its own command stream, looped `repeats` times — so different behaviors (quest dialogue, movement, item contention) interleave over shared world state, the pattern that surfaces crashes a lockstep script can't. Fan-out and mix now share one `_run_concurrent` runner, and the report core (`percentile_summary()`) moved beside `latency_report()` in `lorecraft.tools.session_replay`. New `tests/simulation/test_soak.py` mixes the golden-path + load-default recordings: a quick 2-repeat default keeps push/PR CI fast, `LORECRAFT_SOAK_REPEATS` scales it into a real soak (verified @25 repeats = 325 commands, p50 ~11 ms / p99 ~30 ms), `LORECRAFT_SOAK_JSON` exports the report. The CI `simulation` job gained a `workflow_dispatch` `soak_repeats` input for opt-in longer soaks without touching the push/PR path. With 43.1 (record + golden audit diff) and 43.2 (N-player fan-out), the wishlist's `lorecraft.tools.simulation` idea is fully superseded: record real play once, then regress it, load-test it, and soak it.

## [0.39.6] - 2026-07-05

### Added

- **Sprint 43.2 — N-player scenario fan-out; the load test now replays recorded traffic** (Phase 2 of [`session_replay.md`](docs/session_replay.md)). New `fan_out_scenario(server, scenario, players=N, jitter_ms=…)` in `tests/simulation/replay.py` maps a single-actor scenario onto N freshly created concurrent `VirtualPlayer`s and returns the Sprint 37.3 percentile report — whose assembly (`percentile()`/`latency_report()`) moved into `lorecraft.tools.session_replay` so the report shape is unit-tested and reusable by the future replay CLI. `test_load.py` no longer hard-codes its command script: the read-heavy loop became the checked-in `tests/simulation/scenarios/load_default.json`, and `LORECRAFT_LOAD_TEST_SCENARIO=<path>` points the same harness at **any recorded session** (verified by fanning the golden-path recording out to 5 players — including 5-way contention over one coin). Report shape and knobs (`LORECRAFT_LOAD_TEST_PLAYERS`/`_JITTER_MS`/`_JSON`) unchanged, JSON now also stamps the scenario name; numbers match the post-WAL baseline (p50 ~56 ms @10 players lockstep). Default + simulation suites green.

## [0.39.5] - 2026-07-05

### Added

- **Docs: Sprint 49 plan — encumbrance + analytics dashboard.** Promoted two backlog items into a scheduled sprint: **inventory encumbrance** (item weight trait, character weight capacity, `can_carry` inventory gating, movement gate + player weight UI) and an **admin analytics dashboard** (live p50/p95/p99 latency by operation off the Sprint 35.3 `/admin/analytics/performance` endpoint, command-execution timeline, player-activity heatmap). Both are low-risk Tier 2 additions over stable foundations (inventory, traits, audit telemetry). Sprint-numbering guard updated (used 1–49; next new = 50).

## [0.39.4] - 2026-07-05

### Added

- **Sprint 43.1 — session record & single-actor replay with a golden audit diff** (Phase 1 of [`session_replay.md`](docs/session_replay.md)). New `lorecraft.tools.session_replay` module: a versioned **scenario JSON format** (logical actors + `{t, actor, raw}` command stream + `world_yaml`/`rng_seed` stamps), `record_scenario()` + a `record` CLI (`python -m lorecraft.tools.session_replay record --audit-db … --actor … -o scenario.json`) that projects one actor's `command_executed`/`_blocked`/`_failed` events out of any audit DB into a replayable scenario, and the shared `normalize_events()` audit-trail normaliser. Playback side: `tests/simulation/replay.py` `replay_scenario()` drives a scenario through a fresh `VirtualPlayer` against a live server; `test_audit_regression.py` is now **data-driven** — the old hard-coded script became the checked-in `tests/simulation/scenarios/golden_path.json`, replayed for both the run-vs-run determinism guard and a new **checked-in golden diff** (`golden_path.audit.json`, regenerate intentionally with `LORECRAFT_UPDATE_GOLDENS=1 make test-simulation`). The simulation-server factory now accepts an `rng_seed` so replays pin the scenario's recorded seed. Unit-tested (record filtering/ordering/`t` deltas, JSON round-trip, version guard, normaliser, CLI); full default + simulation suites green.

## [0.39.3] - 2026-07-05

### Added

- **Docs: reconciled the unrecorded 2026-07-03 planning list into the roadmap/wishlist.** Five planned items (follow, channel colors + mute, contextual hints, item discovery journal, scavenger hunt events) had never been written into the repo. Three are now scheduled: **Sprint 46 — item discovery journal** (extend the Sprint 25.3 `journal` with first-discovery item tracking, `Player.discovered_items` on the `met_npcs` pattern), **Sprint 47 — `follow` command** (follower auto-moves on the target's movement, re-running the standard movement gates; chains allowed, cycles rejected), and **Sprint 48 — scavenger hunt events** (design-first: a scheduled, time-boxed exploration event on existing scheduler/news/flags primitives — the non-instanced slice of the wishlist's instanced-minigames idea). **Per-channel mute** folded into Sprint 45 Phase 3 alongside the colored/prefixed channel tags (`chat_feed_split.md` updated — same rendering/preferences surface). **Contextual hints** parked in the wishlist pending a design pass (trigger rules, frequency caps, preferences off switch). Sprint-numbering guard updated (used 1–48; next new = 49).

## [0.39.2] - 2026-07-05

### Added

- **Docs: engine / game-data separation deep-dive (`engine_content_separation.md`).** Deepened the wishlist "plan for it, don't do it yet" note into a concrete plan for splitting the engine from game data ("one engine, many worlds"). Covers what's already in our favor (tier split done, all content paths env-externalized, validator + versioning/changeset plumbing + `WorldMeta.schema_version`/`engine_version` exist, one load seam), a **content inventory decision** (rooms/items/NPCs/dialogue/quests/help = world content → content repo; news = operational; issues = engine-dev artifact stays behind), the **content contract** (layout + schema version + validation-as-gate + scripting entry points), the **hard part** (a future scripting layer is *game data* and must load through the external boundary — don't add it via an engine-internal import path), and a phased migration (consolidate + contract → externalize the reference world → decouple tests → scripting-if-it-lands). Linked from `wishlist.md`. Planning-only; unscheduled until a scripting decision or a second world creates the pressure.

## [0.39.1] - 2026-07-05

### Added

- **Docs: chat/feed split plan (`chat_feed_split.md`) for Sprint 45.** Planned the opt-in split of the social/chat feed from the narrative feed. Key finding: chat (only `say` today; shout/whisper/tell are still Backlog) and ordinary room narration ("X leaves north.") share **one channel end to end** (`tell_room` → `feed_append`/`room_event`), so there's no chat-vs-narrative signal — the split threads a new `chat` category through GameContext (`say_chat`/`tell_room_chat` + `chat_messages`) → the broadcast protocol (`message_type:"chat"`) → `command_result` → `app.js` dual-pane, gated by a `separate_chat` player preference (default off = today's single feed). Phased so Phase 1 (server channel + preference) is headless-testable and **Phase 2 (client dual-pane) needs a real browser to verify** — hence deferred to a focused follow-up. Linked into the roadmap Sprint 45 (43-plan → 44-built → 45-planned).

## [0.39.0] - 2026-07-05

### Added

- **Sprint 44 — weather-driven world effects.** Weather now *does* something beyond flavoring room text: a new `WeatherTerrainModifierSource` (`features/weather/modifiers.py`) means **harsh weather makes skill-gated wilderness terrain harder to cross**. During harsh weather (`COLD_WEATHERS` snow/blizzard/fog + thunderstorm/heavy_rain), a player standing on a terrain that has a `required_skill` (mountain/swamp/water need `survival`) gets a flat penalty subtracted from that skill, read through the **§3.5 modifier resolver** — the same one movement's terrain gate already uses. So a blizzard can push a marginal traveller below a mountain pass's survival requirement and block the crossing, with **no new movement code and no materialized per-room effects**. Design note: weather is *global clock state affecting rooms by terrain*, so it's a read-through modifier source (like room auras / terrain gating), **not** the Sprint 39 timed-room-effect primitive (which is for localized, TTL effects) — keeping one owner per behavior (clock → weather, terrain defs → terrain, resolver → composition). Unit-tested (penalty applies in harsh weather on skill-gated terrain; none in clear weather or on sheltered terrain).

## [0.38.17] - 2026-07-05

### Added

- **Docs: session record & playback plan (`session_replay.md`) + wishlist items promoted to the roadmap.** New design doc for **Sprint 43 — session record & playback**: record real/scripted player command streams (from the audit log) and replay them across **N simulated players** for regression (golden audit-trail diff), load (p50/p95/p99), and soak/fuzz — a consolidation of pieces that already exist (audit log, the `VirtualPlayer`/`SimulationServer` harness, the Sprint 37.3 load test, and the seeded-`GameRng` audit-regression determinism). Promoted three wishlist items to the active roadmap: **43** (session record/playback, plan above; supersedes the Backlog `lorecraft.tools.simulation` note), **44** (weather-driven world effects on the Sprint 39 timed-room-effect primitive), and **45** (split the social/chat feed from the narrative feed, opt-in). Sprint-numbering guard updated (used 1–45; next new = 46).

## [0.38.16] - 2026-07-05

### Added

- **Sprint 39.4 — timed-room-effects content-lint + test closeout (Sprint 39 complete).** Added `world/validator._validate_open_timed_passage`: a plate/lever's `open_timed_passage` mechanism side effect is shape-checked (non-empty `direction`, positive numeric `ticks`) so a malformed timed-gate trigger fails world validation instead of silently no-op'ing at runtime (the direction→exit resolution stays a runtime concern — an item's room isn't known statically). With the tests already added in 39.2/39.3 (gate open→relock, normally-open exit unchanged, aura modify+lift, `on_expire` savepoint isolation, `on_apply`-raise rollback) and confirmed audit-regression stability, **Sprint 39 (timed room effects) is complete** — and with the performance band closed out, **the active roadmap is now empty** (remaining work lives in `wishlist.md` + the roadmap Backlog).

## [0.38.15] - 2026-07-05

### Added

- **Sprint 39.3 — occupant auras + the `passage_open` timed-gate content example (engine_core.md §3.9).** Added the Tier 1 `RoomAuraModifierSource`: resolving a **player**'s modifiers now also pulls in their `current_room_id`'s active room effects, so occupant auras (a slow/chill zone) flow through the one §3.5 resolver with no call-site change and lift the instant the player leaves — no per-player state, no per-tick sweep. It shares an `_effect_modifiers` helper with `ActiveEffectModifierSource` so the ActiveEffect→Modifier translation isn't duplicated. Added the first content example in `features/exploration/room_effects.py`: a `passage_open` room `EffectDef` whose `on_apply` opens an exit (stashing its prior `locked` state) and whose `on_expire` restores it, plus an `open_timed_passage` mechanism side-effect handler so a Sprint 30 plate/lever can open a timed gate straight from world YAML (`{open_timed_passage: {direction: north, ticks: 30}}`); wired via the exploration feature's new `register_fn`. Movement is unchanged (it keeps reading the authoritative `Exit`). Integration-tested: gate opens on apply and the expiry sweep re-locks it (and leaves a normally-open exit open); an aura debuffs an in-room player's resolved skill and lifts on leave.

## [0.38.14] - 2026-07-05

### Fixed

- **CI e2e: player-flow browser tests no longer time out at character creation.** The lobby create form gained a **confirm-password field** and a **password policy** (mixed case + a number, ≥8 chars) back in v0.31.0, but the three e2e helpers still filled only the username + a policy-violating `"e2e-test-password"` and never the confirm field — so `formOk` stayed false, the "Create & Enter" button stayed `disabled`, and `test_gameplay_flows` / `test_map_and_mobile_ui` / `test_ui_refresh_on_item_actions` all timed out (10 failures). Consolidated the three byte-identical `_create_character` copies into one shared `create_character()` in `tests/e2e/conftest.py` that uses a compliant password and fills both password inputs. All 16 e2e tests pass.

## [0.38.13] - 2026-07-05

### Added

- **Sprint 39.2 — `on_apply`/`on_expire` hooks on the timed-effect primitive (engine_core.md §3.9).** `EffectDef` gains two optional hooks. `EffectService.apply()` fires `on_apply(session, effect)` after the row is flushed, in the caller's transaction — so a room-state effect's authoritative write (e.g. opening a gate via `RoomRepo`) and any raise from it both belong to the triggering action. The `TIME_ADVANCED` expiry sweep fires `on_expire(session, effect)` before deleting the row (to restore what `on_apply` changed), each isolated in a **`begin_nested()` savepoint**: a failing hook rolls back only its own writes, is logged, and its row is **kept for retry next tick** (no `EFFECT_EXPIRED` emitted for it) so one bad hook can't strand the rest of the tick's expirations. Backward-compatible — existing effects leave both hooks `None`. Unit-tested (fire timing, on_apply-raise rollback, on_expire failure isolation). No new model, table, or scheduler.

## [0.38.12] - 2026-07-05

### Fixed

- **CI: `tests/unit/test_admin_tui_auth.py` no longer errors when the `admin-tui` extra is absent.** The module imported the Textual-based admin TUI at import time, so the default CI `quality` job (which installs only `.[dev]`, not `.[admin-tui]`) failed collection with `ModuleNotFoundError: No module named 'textual'`. Added `pytest.importorskip("textual")` before the TUI import so the module **skips** cleanly without the extra (mirroring how the e2e suite guards Playwright) and still runs in full where Textual is installed. Verified both paths: 3 passed with Textual present, 1 skipped when absent.

## [0.38.11] - 2026-07-05

### Changed

- **Sprint 39.1 spec revised after a single-owner (one-system-per-behavior) audit.** The audit found the room-*state* mechanic's "read-through" design (movement consulting active room effects via `EffectDef.opens_exits`/`seals_exits`) was a soft violation: it forked *exit passability* into **two stores** (the `Exit` row *and* the effect rows), a second system answering the same question. Reworked in `engine_core.md` §3.9 so a timed gate instead **writes the one authoritative `Exit` state** via `on_apply`/`on_expire` (stashing the prior state in `payload` for an exact restore) — the effect is just another *timed writer* of the state `lock`/`unlock` already write, so **movement is unchanged, `opens_exits`/`seals_exits` are gone, and the engine gains no exit awareness** ("open the gate" is a Tier 2 `EffectDef` hook over `RoomRepo`). The occupant-*aura* mechanic was already correct — it extends the §3.5 multi-source modifier resolver (which stays the single owner of "effective value") rather than adding a parallel one. Net: each behavior keeps exactly one owner — `Exit`/movement → passability, the §3.4 sweep → timing, §3.5 → modifiers. Still design-only; 39.2 awaits sign-off.

## [0.38.10] - 2026-07-05

### Changed

- **Sprint 39.1 design review — hardened `engine_core.md` §3.9 against the code.** Reviewed the timed-room-effects spec and folded the findings back in. **De-risked:** `MovementService.move()` has a single exit-check block (so the read-through gate composes cleanly) and player modifier resolution already flows through `resolve_for(..., "player", …)` (so `RoomAuraModifierSource` needs no per-call-site change). **Strengthened Decision #1:** since `Exit.locked` already exists, mutate-and-reverse would have to *remember and restore* prior exit state (force-locking on expiry would wrongly lock a normally-open exit) — which reinforces read-through. **Added:** the aura-timing rule during a move (auras resolve against the departure room, before `current_room_id` updates), initial player-only occupant scope, `on_apply`/`on_expire` session-only discipline (no pre-commit client I/O, per §26) with per-effect `try/except` isolation in the sweep, and a clarified 39.4 lint (validate world-content *references* to room-effect keys, not the code `EffectDef`). Still design-only; 39.2 implementation awaits sign-off.

## [0.38.9] - 2026-07-05

### Added

- **Sprint 39.1 — timed room effects design spec (`engine_core.md` §3.9).** Wrote the design-first spec (implementation 39.2+ gated on review). A room effect reuses the Sprint 19 `ActiveEffect`/`EffectService` primitive with `entity_type="room"` — **no new model, table, or scheduler**. Decisions settled: **room-state effects** (gate opened / exit sealed) are **read-through** — movement consults `active_for("room", room_id)` plus new `EffectDef.opens_exits`/`seals_exits`, and expiry is the *existing* sweep deleting the row (no mutate-and-reverse, so state can't drift); **occupant auras** (fatigue drain / slow travel) are a new **`RoomAuraModifierSource`** (§3.5) keyed on the player's `current_room_id`, so they apply/lift on enter/leave with no per-tick occupant sweep and no stored per-player state; **`on_apply`/`on_expire`** are optional side-effect hooks (narration/spawn), not the mechanism. First content example (39.3) is a pressure-plate mechanism applying a timed `passage_open` room effect.

## [0.38.8] - 2026-07-05

### Changed

- **Docs: assessed PostgreSQL migration and recorded the finding in `wishlist.md`.** Concluded it would **not** improve performance at the current single-process design (the measured wall was fsync-per-commit on a single writer, already fixed by WAL; Postgres fsyncs per commit too, plus per-query network/IPC, and its concurrent-writer advantage can't be used by a single-threaded engine) — so it's deferred and tied to the concurrency gate (was Sprint 38.1). Captured the migration effort (code is largely DB-agnostic; the real work is adding Alembic + a data-migration path, since there's no migration tooling today) so the analysis isn't lost.

## [0.38.7] - 2026-07-05

### Added

- **Sprint 37.4 — SQLite WAL mode (the fsync fix the benchmarks pointed to).** New `db.configure_sqlite_engine` attaches a connect-listener that sets `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=<level>` on **SQLite engines only** (no-op for other backends and for `:memory:`), wired into `create_game_engine`/`create_audit_engine`. Configurable via `db_sqlite_wal` (default on) and `db_sqlite_synchronous` (default `NORMAL`) / `LORECRAFT_DB_SQLITE_WAL` / `LORECRAFT_DB_SQLITE_SYNCHRONOUS`. WAL makes each commit an append to the `-wal` file with fsync deferred to periodic checkpoints, instead of a full fsync per commit — the dominant cost the Sprint 37 benchmarks surfaced. **Measured win, reproduced in `perf_baseline.py` and the load test:** `scheduler_tick@50jobs` **1410 → 48 ms (~29×)**; multi-player load test p50 **254 → 58 ms**, p99 **475 → 83 ms**. `synchronous=NORMAL` under WAL is safe against application crashes and can lose only the last transaction(s) on OS crash / power loss; set `FULL` for full durability (still faster than the old `DELETE` journal). Documented in `admin_builder_guide.md`; unit-tested; full + simulation suites green.

### Changed

- **Performance & scaling band (Sprints 35–38) closed out; 37.1 and 38.1 deferred to `wishlist.md`.** The measure-first evidence showed the wall was fsync-per-commit on the single SQLite writer, and WAL (37.4) removed most of it broadly. So **scheduler-commit batching (37.1)** — marginal after WAL (~48 ms @ 50 jobs/tick) — and the **concurrency/threading gate (38.1)** — the wrong fix, since threads can't parallelize a single SQLite writer — both move to the wishlist with their evidence and re-trigger conditions. The remaining active roadmap is Sprint 39 (timed room effects, design-first).

## [0.38.6] - 2026-07-05

### Added

- **Scheduler-tick + jittered-load benchmarks (evidence for the Sprint 37.1 / 38.1 decisions).** Two additions to gather the missing measurements before committing to either the scheduler-batching (37.1) or concurrency (38.1) work:
  - `scripts/perf_baseline.py` now measures `scheduler_tick@{1,10,50}jobs` — the cost of one scheduler tick that dispatches N due `mobile_route` jobs, each handled with its own session + commit (the current design).
  - `tests/simulation/test_load.py` gained a `LORECRAFT_LOAD_TEST_JITTER_MS` knob so the load test can spread command arrivals (realistic think-time) instead of only the lockstep worst case.
- **Finding — fsync-per-commit is the dominant cost, and SQLite WAL mode fixes it broadly.** The scheduler tick scales ~linearly at **~28 ms/job** (1 job ≈ 40 ms, 10 ≈ 209 ms, 50 ≈ **1068 ms**) under the default `DELETE` journal; a throwaway `PRAGMA journal_mode=WAL; synchronous=NORMAL` comparison cut those **~20–29×** (50 jobs **1068 → 47 ms**). The load test shows the same root cause on the command path (10 players, 200 ms jitter → p50 100 ms; lockstep → p50 254 ms), since every command commits ~twice. **Implication:** the bottleneck is commit fsync on the single SQLite writer, not CPU — so (a) WAL/pragma tuning is a far higher-value, broader fix than scheduler-specific batching, and (b) adding threads (38.1) would not help a single fsync-bound writer. The 37.1/38.1 disposition follows this evidence (see `docs/roadmap.md` Sprint 37/38).

## [0.38.5] - 2026-07-05

### Added

- **Sprint 37.3 — multi-player load test (`tests/simulation/test_load.py`).** A `simulation`-marked test spins up N concurrent `VirtualPlayer`s (default 10, override with `LORECRAFT_LOAD_TEST_PLAYERS`) that each run a fixed command script over real WebSockets against a live server, then reports **p50/p95/p99/max command latency** (also as JSON via `LORECRAFT_LOAD_TEST_JSON` for scripted before/after diffs). The server is single-process/single-threaded, so this measures how latency degrades as concurrent commands queue on one event loop — the evidence the Sprint 38 concurrency gate needs. **First baseline (10 players × 6 commands): p50 ≈ 254 ms, p95/p99 ≈ 475 ms**, i.e. latency ≈ queue-position × per-command cost under a lockstep herd. Documented in `docs/roadmap.md` Sprint 37.

### Fixed

- **Simulation harness `create_player` was silently broken.** `tests/simulation/conftest.py`'s `/lobby/create` call omitted the now-required `password_confirm` field and used a password that fails the default complexity policy, so **every `simulation`-marked test 400'd at character creation** (unnoticed because the suite is excluded from the default `make test`). Now sends a matching `password_confirm` and a policy-compliant password; the full simulation suite passes again.

## [0.38.4] - 2026-07-05

### Added

- **Sprint 37.2 — connection-pool tuning knobs.** Added `db_pool_size` (default 5) and `db_pool_recycle` (default 1800 s) to `Settings`, configurable via `LORECRAFT_DB_POOL_SIZE` / `LORECRAFT_DB_POOL_RECYCLE`. A new `db._pool_kwargs` passes them to `create_engine` **only for a networked backend** (Postgres/MySQL — the many-concurrent-players deployment target); SQLite is skipped because it is single-writer and its dialect uses a thread-local/static pool that these `QueuePool` knobs don't apply to (and `pool_size` errors on the in-memory `StaticPool`). Documented in the `admin_builder_guide.md` configuration reference; unit-tested (sqlite → no kwargs, Postgres → tuned, env parsing). No behavior change for the default SQLite dev/test setup.

### Changed

- **Sprint 37 sequenced measure-first.** Reordered to **37.2 → 37.3 → 37.1**: the 35.1 baseline never measured `scheduler_tick`, so 37.1 (batching each `SCHEDULED_JOB_DUE` handler's per-job commit into one commit/tick) is an unmeasured change to the event/session contract — it's now gated on the 37.3 load test producing real p95/p99 evidence that scheduler-commit cost matters, per the band's "measure first" rule and the Sprint 36 precedent.

## [0.38.3] - 2026-07-05

### Added

- **Sprint 35.3 — per-operation latency analytics (`GET /admin/analytics/performance`).** Completes the Sprint 35 telemetry stack. `time_operation` now yields an `OperationTiming` whose `duration_ms` is readable after the block, and `CommandEngine` stamps a per-operation **`perf` breakdown** (`command_parse` / `condition_evaluate` / `db_commit`) onto every `COMMAND_EXECUTED` audit payload. A new `analytics.operation_latency_percentiles` groups those durations — plus the existing top-level handler time, surfaced as the `command_handler` operation — into **p50/p95/p99 + count per operation**, exposed at `GET /admin/analytics/performance` (`Observer` auth, `range` param like the other analytics endpoints). This extends `command_latency_percentiles` from a single aggregate to a per-operation view, so an admin can see whether real-traffic latency is going to parsing, condition checks, or the DB commit. Events predating this change (no `perf` field) still contribute their `command_handler` timing. `scheduler_tick`/`broadcast_send` remain timed in the structured logs (35.2) but sit outside the per-command audit path, so they don't appear here. Documented in `admin_builder_guide.md`.

## [0.38.2] - 2026-07-05

### Changed

- **Docs: `AGENTS.md` now documents the git-worktree testing footgun.** Added a "Running tests from a git worktree" subsection to the Testing guide: the `.venv` lives only in the primary working tree and its editable install resolves `import lorecraft` to the *primary* tree's `src`, so a bare `python -m pytest`/`make test` from a `.claude/worktrees/<name>` checkout silently tests the wrong source. Documents the fix — activate the primary venv and prepend `PYTHONPATH="$PWD/src"` — with a copy-paste, path-agnostic recipe (`MAIN=$(dirname "$(git rev-parse --git-common-dir)")`), a one-line "am I testing the right tree?" check, the `make`-from-worktree form, the worktree-local-venv alternative, and the e2e content-YAML `tmp_path` isolation note.

## [0.38.1] - 2026-07-05

### Fixed

- **Admin TUI now invalidates stale saved bearer tokens on 401.** The TUI persisted only its access token, so after the API restarted with a different ephemeral `LORECRAFT_ADMIN_JWT_SECRET` it would silently reuse an unverifiable token and every protected screen (`Players`, `Issues`, `Audit`, `World`, `Changesets`, `Clock`) returned 401 with `admin_token_decode_failed: Signature verification failed`. A protected-endpoint 401 now clears the in-memory token, removes `access_token` from `~/.config/lorecraft-admin/credentials.json`, and sends the TUI back to the login screen with a session-expired message. Login failures still stay as normal login failures, and malformed credential JSON now fails closed instead of crashing startup.

## [0.38.0] - 2026-07-05

### Added

- **Sprint 42 — Issues tab: default filter, configurable status hiding, and selectable sort.** The admin Issues tab now **hides resolved and deferred issues by default** so the list shows actionable work, with a **"Hide status" checkbox group** to toggle any status (open · in-progress · resolved · deferred · duplicate) in/out of view. Added a **priority filter** dropdown and a **sort selector** — *Priority* (priority first, newest-updated tiebreak), *Recently updated*, or *Recently created* (date first, priority tiebreak) — so you can prefer priority or recency. Filtering and sorting run client-side over the full list (the tracker is low-volume), a header count shows `N shown · M hidden`, and the hide/sort choices persist across reloads in `localStorage`. The free-text status/priority filter inputs were replaced by these controls.

### Fixed

- **In-game player reports now live-refresh the admin Issues tab.** Filing a report via the `report` command created the issue through the content path (not the admin API), so it never triggered the `content_changed` push and an open Issues tab stayed stale until reload. The command now emits a new `GameEvent.ISSUE_FILED`, which `main.py` forwards to the admin broadcaster as the same `content_changed`/`issues` message the admin routers already send — so player-filed reports (and any bus-emitting issue source) appear live, matching admin-initiated changes. First admin **Issues** browser e2e coverage added (`tests/e2e/test_admin_issues.py`) for the default filter, sort, and live-update paths; the admin live-server fixture + login helper were lifted into `tests/e2e/conftest.py` and now isolate the content YAML mirrors to a temp dir.

## [0.37.2] - 2026-07-05

### Fixed

- **Admin console now auto-logs-out on a stale/invalid session instead of flashing a toast.** Previously an authenticated request that came back `401` (expired/invalid access token) only showed a transient "Session expired — please log in again." error bar while leaving the dead token in place — the console stayed on-screen and every subsequent request kept failing, and an idle tab's admin WebSocket would reconnect-loop forever with the expired token. Now a `401` on any authenticated request (but **not** a `403`, which is a valid session lacking a role, nor the login call itself) triggers a full logout: the access token and WS are cleared and the user is returned to the login screen with a "Your session expired" notice (`sessionExpired()` in `webui/admin/index.html`, idempotent under concurrent 401s). This also fixes a latent bug where a failed login flashed the same "session expired" toast.
- **Admin WebSocket now delivers close code 1008 to the browser on token rejection.** `admin_ws_endpoint` previously `close()`d the socket *before* `accept()`, so a rejected handshake surfaced to the browser as an ambiguous `1006` (indistinguishable from a network blip) — the client couldn't tell a stale session from a transient drop. It now accepts first, then closes with `1008` on an invalid/expired token, so the admin UI can force a logout (rather than reconnect-loop) specifically on auth rejection while still auto-reconnecting on genuine network drops. First **admin browser e2e coverage** added (`tests/e2e/test_admin_session.py`) exercising both the HTTP-401 and WS-1008 logout paths.

## [0.37.1] - 2026-07-05

### Added

- **Sprint 35.2 — structured per-operation perf logging (`time_operation`).** Added `time_operation(name, *, warn_ms=50.0)` to `observability.py`: a context manager that times a block and emits one structured `perf_operation name=… duration_ms=…` log line — DEBUG normally, escalating to **WARNING when the block exceeds the 50 ms "slow" budget** the perf baseline flagged. It never swallows exceptions (the elapsed time is still logged when the block raises), and the transaction/correlation IDs bound per command are attached automatically by the existing root log filter, so every timing is traceable to the command that produced it. Instrumented all five hot operations from the roadmap: `command_parse`, `condition_evaluate`, and `db_commit` (in `CommandEngine`), `scheduler_tick` (in `SchedulerService._on_time_advanced`), and `broadcast_send` (both `ConnectionManager.broadcast_to_room`/`broadcast_global`). Logging-only — no behavior change. Call sites are placed so Sprint 35.3 can layer per-operation persistence into `time_operation` without moving them. (Engine-tier modules import `lorecraft.observability`, a stdlib-only leaf module, consistent with the existing `lorecraft.errors` dependency; the tier-boundary test stays green.)

## [0.37.0] - 2026-07-05

### Added

- **Sprint 40 — admin console live-refresh on content changes.** The admin console already opened an `/admin/ws` push channel (`AdminBroadcaster`) but only used it for player/changeset events; content tabs (Issues, News, Help) went stale until you hit Search/Refresh. Content mutations now push a generic `{"type": "content_changed", "resource": "<tab>"}` event (new shared helper `webui/admin/routers/_common.notify_content_changed`), and the frontend reloads that tab **only when it's the one currently open** (`refreshIfActive`). So a second admin — or your own session after an out-of-band edit — sees new/edited issues, news, and help topics without a manual refresh. No new infrastructure; reuses the existing broadcaster + WS.
- **Sprint 41 — registered issue components (dropdown, closed set).** The issue `component` field was free-text; it is now a **strict, registered set** exposed as a dropdown in the admin console's create and filter controls. The single source of truth is `lorecraft/content/components.py` (`ISSUE_COMPONENTS`): a coarse, structural taxonomy — `engine`, `webui/player`, `webui/admin`, `admin-tui`, `features`, `docs`, `infra` — served to the UI via `GET /admin/issues/components` and validated on `POST`/`PUT /admin/issues` (unknown component → HTTP 400; empty = "unassigned" is always allowed). In-game player reports keep their legacy `component="player-report"` (they use the content path, which is not API-validated, and are also tagged `player-report`); they store and display unchanged.

## [0.36.10] - 2026-07-05

### Changed

- **Sprint 36.2 — parser resolution now projects `(id, name, aliases)` instead of materializing full `Item` rows; Sprint 36.3 re-measure closes the parser-scaling work.** Profiling the 36.1 result showed the residual parse cost at large inventory sizes was **SQLAlchemy materializing full `Item` ORM objects** (each decoding four JSON columns) — ~72% of parse time — not the matcher scan (~6%) that 36.2 was originally scoped to index. So `GameContext.get_visible_entities()` / `get_inventory()` now use a new **column projection** `ItemRepo.name_index(ids)` that selects only the three fields noun-matching needs (skips ORM instance creation and decoding the unused `usable_with`/`loot_table`/`effects` columns). Semantics-preserving (ordering, item-id dedup, per-stack room entries unchanged). Re-running `scripts/perf_baseline.py`, cumulative vs. the original 35.1 baseline: `parse:examine@25items` **4.79 → 1.13 ms p50 (4.2×)** and `@100items` **16.92 → 1.82 ms p50 (9.3×)**, with the @100 **p99 tail collapsing from ~18–23 ms to ~1.9 ms** (full-row population, not the `IN` clause, was the tail). Parse cost is now roughly flat in inventory size. Per Sprint 36.3's gate — *add LRU memoization only if resolution is still material after 36.1–36.2* — resolution is no longer material (~1.8 ms p50 / ~1.9 ms p99 at 100 items, well under the 50 ms "slow" line), so **no result memoization is added**; a cross-command immutable-`Item` cache remains available as a future lever but isn't justified by the numbers.

## [0.36.9] - 2026-07-05

### Changed

- **Sprint 36.1 — eliminated the parser's per-item N+1 DB round-trips.** `GameContext.get_inventory()` and `ItemRepo._pair_with_items()` (which backs `items_in_room` → `get_visible_entities`, the room-contents path) previously called `item_repo.get()` once per stack, so noun resolution issued one query per visible/carried item. Both now batch-load their Item rows in a single query via a new `ItemRepo.get_many(ids)`, keyed by id (dedupes ids, skips missing rows, short-circuits on empty input). Semantics-preserving — ordering and item-id dedup are unchanged. Re-running `scripts/perf_baseline.py` on the same machine: `parse:examine` at 25 inventory items drops **4.79 ms → 1.47 ms p50 (3.3×)** and at 100 items **16.92 ms → 3.01 ms p50 (5.6×)**; the residual ~3 ms at 100 items is the matcher's O(entities) name scan, which is Sprint 36.2's target. (A thin p99 tail (~22 ms) remains at 100 items from the large `IN`-clause query — noted for the 36.2 re-measure; the p50/p95 distribution improved decisively.)

## [0.36.8] - 2026-07-05

### Fixed

- **WebSocket broadcast to closed connections no longer crashes.** When `broadcast_global()` attempted to send clock updates to a disconnected player whose WebSocket had already closed (e.g., page navigation), it raised `RuntimeError: Unexpected ASGI message 'websocket.send' after sending 'websocket.close'`. Now `send_to_player()` catches the error, cleans up the dead connection (including room tracking), and allows the broadcast to continue without crashing.

## [0.36.7] - 2026-07-05

### Added

- **Roadmap Sprint 39 — timed room effects (Tier 1 engine primitive, design-first).** Promoted the wishlist "Timed room effects / auras" idea to a scoped roadmap sprint. The design decision is recorded up front: **reuse the Sprint 19 `ActiveEffect`/`EffectService` timed-effect primitive** (already generic over `entity_type`, so a room is just `entity_type="room"`) rather than adding a parallel `RoomEffect` model (which would duplicate the scheduler expiry sweep) or a component carrier (wrong shape). The spec calls out that "room effect" bundles two mechanics — room-state effects (a plate opens a gate for 30s) vs. occupant auras (drain fatigue / slow travel) — and gates all implementation (39.2–39.4) behind a reviewed design task (39.1) written into `engine_core.md`. Roadmap "what's left", the numbering guard (used 1–39; next new = 40), and the wishlist entry updated to cross-reference.

## [0.36.6] - 2026-07-05

### Changed

- **Sprint 65 (multiplayer trade/transit tests) moved to `wishlist.md`; performance band renumbered 66–69 → 35–38.** The multiplayer trade/transit simulation-test pass was coverage-hardening of already-complete, stable subsystems, so it moved to the wishlist (under *Multiplayer sim-test coverage*) rather than sitting in the active roadmap. With it gone, the performance & scaling band is the only remaining roadmap work and was renumbered to fill the reserved 35–38 gap (35 telemetry/baseline, 36 parser scaling, 37 batching/pool/load, 38 concurrency gate); all cross-references, the sprint-numbering guard (used 1–38; next new = 39), and the "recommended next step" note updated. `docs/roadmap_completed.md` trimmed to completed history only (the open perf band and Sprint 65 no longer appear there as if active; the dated historical narrative is preserved).

## [0.36.5] - 2026-07-05

### Changed

- **Roadmap slimmed to remaining work only; completed history split out.** `docs/roadmap.md` went from ~660 lines to a concise list of what's *left* — Sprint 65 (multiplayer trade/transit tests) and the Performance & scaling band (66–69) — plus backlog, a sprint-numbering guard (used 1–34/65–69; 61–64 retired to wishlist; next new = 70), a playtesting quickstart, and an assessment recommending the perf band be sequenced ahead of Sprint 65. The full detail of the completed sprints (1–34, foundation + Tier 1 engine-core + Tier 2 pillar band + tier-split follow-ons) and the Foundation exit criteria moved verbatim to a new tracked file, **`docs/roadmap_completed.md`**.
- **Sprint 32.1 (in-game intro walkthrough) moved to `wishlist.md`.** It was the last open piece of Sprint 32 (32.2 preferences + 32.3 accessibility already shipped) and was deferred pending a product decision on its trigger UX; its spec now lives under *Onboarding & first-time experience* in the wishlist. Sprint 32 therefore has no remaining roadmap work.

## [0.36.4] - 2026-07-05

### Changed

- **Combat & PvP set aside to `wishlist.md`.** Roadmap Sprints 61–64 (combat core services, combat commands/UI, combat testing, PvP consent) — plus the PvP-consent portion of Sprint 65 — moved out of the active roadmap into `wishlist.md` as ready-to-restore, roadmap-grade specs. They kept forcing sprint renumbering and aren't worth the churn right now; nothing is lost. Sprint 65 is retained and retitled **"Multiplayer trade & transit tests"** (its trade/transit portions are independent of combat and stay live). Roadmap cross-references (current position, design-docs index, post-tier-split note, build-order reference, footer) updated to match; the open roadmap items are now Sprint 32.1, Sprint 65, and the Performance & scaling band (66–69).

## [0.36.3] - 2026-07-05

### Added

- **Performance baseline harness (`scripts/perf_baseline.py`).** A reproducible micro-benchmark that drives the real parse / condition-eval / command-dispatch / commit paths against the Ashmoore world in a disposable DB and reports p50/p95/p99 per operation — the checked-in "before" picture for the new Performance & scaling band (roadmap Sprints 66–69). First run shows parser entity-resolution is **O(visible entities)**: `examine` parse is ~0.7 ms baseline but ~4.8 ms at 25 inventory items and ~17 ms at 100 (p99 ~36 ms), while condition eval is ~0.002 ms and a no-op game-state commit ~0.015 ms — so the band prioritizes fixing the parser's linear resolution (Sprint 67) over speculative caching, and defers all threading/multiprocessing behind a data-gated decision (Sprint 69).

### Changed

- **Roadmap: added the Performance & scaling band (Sprints 66–69).** Telemetry-first plan — measure, fix the evidenced bottleneck (parser resolution), then a load test, with any concurrency work gated on real telemetry rather than added speculatively.
- **Test parallelism: split three multi-class test monoliths into one file per class** so pytest-xdist's `--dist=loadfile` can spread them across workers: `test_transit.py` (6 classes), `test_traits_skills_reputation.py` (3), and `test_trade.py` (2) → 11 focused files. No test logic changed; all 39 cases still pass, counts unchanged.

## [0.36.2] - 2026-07-05

### Added

- **Admin TUI: Help topics screen (F8).** The terminal admin client gains a read-only **Help Topics** screen (F8) listing id/name/title/category/keywords from `GET /admin/help`, with `r` to refresh — parity with the web console's Help tab (create/edit stays in the web panel, same as the TUI's News screen). Verified with a Textual pilot.

## [0.36.1] - 2026-07-05

### Added

- **Admin console: Help topics tab.** A new **Help** tab manages the help articles players read via `help topics` / `help <id>` / `help <name>`. Create topics (numeric id auto-assigned, or set explicitly), edit them inline (row-expand to a body textarea + title/category/keywords), delete them, and filter by name/title. Backed by `GET/POST/PUT/DELETE /admin/help` (read = Observer, mutations = Moderator); duplicate names/ids are rejected (409), non-slug names rejected (400), and every mutation re-exports `docs/help_topics.yaml` — same YAML-mirror pattern as News/Issues. Verified end-to-end in a headless browser (seed load, create/search/delete, YAML sync). 1 admin-API integration test; full suite 886 passing.

## [0.36.0] - 2026-07-05

### Added

- **Help system overhaul: command categories, curated help, and authored help topics.**
  - **`help` (bare)** now shows a short curated set of the most critical commands plus pointers, instead of dumping everything (in dialogue/combat it still shows the context-scoped list).
  - **`help commands`** lists every available command **grouped by category** (Movement, Social, Items & Inventory, Trade, …) and **alphabetized within each group**. Categories are assigned in one place (`register_all_commands` wraps each module's registration in a `registry.category(...)` block); a new `CommandDefinition.category` + `CommandRegistry.category()` context manager back this.
  - **`help <command>`** unchanged detail, now also prints the command's category.
  - **Help topics (articles):** a new DB/YAML-backed `HelpTopic` (numeric `id` + unique slug `name`, `title`, `body`, `category`, `keywords`), authored in `docs/help_topics.yaml` (8 seed topics) and imported on first startup (`LORECRAFT_HELP_YAML_PATH`, mirrors the news/issues pattern). `help topics` lists them as `[id] name — Title` grouped by category; `help topics <word>` searches name/title/keywords; `help <id>` or `help <name>` reads one. A command whose name matches a topic gets a "See also help topic [id]" pointer.
  - New `models/help.py`, `content/help.py` (validate/import/export/bootstrap), `repos/help_repo.py` (by-reference / search). 30 tests across the three parts; full suite 885 passing. Verified the live in-game output (curated help, grouped `help commands`, `help topics`, `help 6`, `help topics trade`).

## [0.35.3] - 2026-07-05

### Added

- **Admin Issues tab — date/age toggle.** A 🕑 button next to the Issues search flips the Created/Updated columns between absolute dates (`7/5/2026`) and relative ages (`2 hours ago`). The button label reflects the current mode (Dates/Ages); toggling re-renders the visible date cells in place (no refetch, expanded detail rows stay open), and the hover tooltip always shows the full timestamp. Verified end-to-end in a headless browser (toggle flips the cell text and back, no console errors).

## [0.35.2] - 2026-07-05

### Changed

- **Admin UI — richer Issues tab.** The Issues tab hid most of the data the `/admin/issues` API already returned. It now shows **Opened by**, **Created**, and **Updated** columns, and each row is **clickable to expand a detail panel** with the full description, opened-by / assigned-to, full created/updated timestamps, tags, and links (rendered as anchors). A caret (▸/▾) shows expand state; the inline status dropdown still works without toggling the row. Pure frontend change (`webui/admin/index.html`) — verified end-to-end in a headless browser (admin login → Issues tab renders the new columns and the detail row expands, no console errors).

## [0.35.1] - 2026-07-05

### Changed

- **Roadmap — post-tier-split band status updated; Sprint 32.1 marked deferred.** "Current position" now reflects that Sprints 31, 32.2/32.3, 33, and 34 have shipped, leaving only Sprint 32.1 (in-game intro walkthrough), deliberately deferred pending a product decision on its trigger UX (opt-in `tutorial` vs. auto-open-once). Docs-only.

## [0.35.0] - 2026-07-05

### Added

- **Sprint 33.1: guided multi-turn `/report` flow.** Bare `report` now opens a short modal wizard — pick a category (bug/feedback/idea), give a title, then a detail (or `skip`); `cancel` aborts at any step. State lives in `player.flags` (like the dialogue system), and the web layer routes free-text input to the wizard via `resolve_command_text` while it's active, so no command prefix is needed. `report <description>` remains a one-liner fast path, and both land in the same Sprint 10.5 `create_issue()` pipeline (the category maps onto the tracker's `type` and is added as a tag).
- **Sprint 33.2: page-length preference (wishlist quick-win).** A `feed_page_length` preference (20/40/80) added to the Sprint 32.2 account-preferences blob now drives how many feed entries the game screen loads, with a matching select on the settings page. Feeds through the same single-point resolver; invalid/legacy values fall back to 40.

### Marks Sprint 33 complete

- With 33.1 + 33.2 shipped, the post-tier-split "next up" band (Sprints 31–34) is done except the deferred Sprint 32.1 (in-game intro walkthrough). Both open player-reported issues were closed in Sprint 34.

## [0.34.0] - 2026-07-05

### Added

- **Sprint 32.3: accessibility mode.** The account settings page gains a **high-contrast theme** (black/white with brighter accent + borders, a visible keyboard focus ring, WCAG-AA contrast) and **real text scaling** (normal/large/xlarge, via root font-size). Both ride on the 32.2 preferences layer (`high_contrast` + `font_scale`, resolved into a combined `body_classes` string). Templates gained real accessibility structure: a "Skip to main content" link, `role="banner"`/`role="main"` landmarks, and a `role="log"` + `aria-live="polite"` narrative feed for screen readers, plus a robust `.sr-only` utility. Honours the OS `prefers-reduced-motion` setting too.
- **Sprint 34.1: `help <command>` shows per-command detail (issue-7502f412).** `help <verb>` now prints that command's help text, its other aliases, and its scope instead of always dumping the full list; an unknown verb reports not-found and points back to bare `help`. Bare `help` is unchanged. Closes the open player report.
- **Sprint 34.2: `score` command (issue-257c6643).** A single progress report aggregating existing state — level/XP, quests completed/in-progress, wealth (carried + banked coins), reputation count, and discoveries (rooms visited / NPCs met). No new persistent schema; each section reads its own feature's tables and degrades to zero when empty. Closes the open player report. **Both player-reported issues are now resolved; none remain open.**

## [0.33.0] - 2026-07-05

### Added

- **Sprint 32.2: per-account presentation preferences.** Players get an account-level settings page (`GET/POST /settings`, linked from the top nav) to control **display density** (comfortable/compact), **feed verbosity**, **timestamp format**, **reduced motion**, and **panel visibility** (hide minimap / inventory / players-online / quest-tracker). The engine stores an opaque `Player.preferences` JSON blob and never interprets it; `webui/player/preferences.py` is the single place that gives it meaning (schema, defaults, validation). The render layer resolves preferences in exactly one place (`resolve_preferences(player.preferences).to_context()` in the `/game` SSR context) and exposes them to templates as `prefs`; `base.html` applies `density-compact`/`reduced-motion` body classes (backed by new `custom.css` rules + a `prefers-reduced-motion` media query), and `game.html` gates the four toggleable panels on `prefs.hidden_panels`. Invalid, partial, or legacy blobs always resolve to valid defaults, and every settings POST is re-validated through `apply_updates` so an invalid value can never be stored (only non-defaults are persisted). 24 tests (18 unit + 6 integration). The accessible form markup (fieldsets/legends/labels) also seeds Sprint 32.3.

## [0.32.3] - 2026-07-05

### Changed

- **Sprint 31.4: structure docs rewritten to the shipped tier layout (tier-split step 13); Sprint 31 complete.** Went beyond the earlier staleness banners and rewrote the actual content: `architecture.md` §4 now shows the `engine/`/`features/`/`webui/` three-axis tree (was the pre-split flat `game/`/`models/`/`services/` tree); `tier_modules.md` is reorganized into per-axis tables (engine subtables, the 24 feature packages, webui hosts, composition root) with the manifest/`discover_features` model replacing the old side-effect-import section; `architecture_tiers.md` §2/§3/§4/§5/§6/§8 rewritten from "the split is NOT yet reflected / register via side-effect imports / disable by removing imports" to the shipped manifest + config-driven (`enabled_features` / `LORECRAFT_FEATURES`) reality. Graduated the `tier_split_refactor.md` §1c "adding feature UI" design into `admin_builder_guide.md` as a new **"Extending the UI: Feature Panels"** chapter, plus a `LORECRAFT_FEATURES` row in the config reference. `tier_split_refactor.md` marked **complete** (all steps 0–13). Docs-only.
- **Roadmap: folded the two open player reports into a new Sprint 34** (Player-reported command polish): 34.1 `help <command>` per-command help (issue-7502f412), 34.2 `score` progress command (issue-257c6643). Synced `docs/issues.yaml` from the runtime DB (issue-257c6643 was DB-only). Combat/PvP renumbered 40–44 → 61–65 to reserve 34–60.

## [0.32.2] - 2026-07-05

### Changed

- **Kindle doc weaver — Paperwhite table tuning.** EPUB output now embeds a small Kindle stylesheet and defaults to `--epub-table-mode lists`, converting Markdown pipe tables into stacked key/value bullet lists for small e-ink screens while preserving normal tables for PDF output. This keeps roadmap/status tables readable on a 7-inch Paperwhite without forcing tiny columns.

## [0.32.1] - 2026-07-05

### Added

- **Agent skill: Kindle doc weaver.** Added a portable `.agents/skills/kindle-doc-weaver` skill with a stdlib Python script that weaves master `docs/*.md` into a cross-linked Markdown/EPUB/PDF artifact and can email the output through Gmail SMTP to `smartattack_GW@kindle.com` using a runtime-provided app password. EPUB output is the Paperwhite default, splits at level-2 headings for shorter internal Kindle chunks, auto-names outputs as the next `lorecraft_YYYYMMDD<letter>` suffix in `build/kindle-docs/`, and skips Markdown docs tagged with `kindle_doc_weaver: ignore` frontmatter (`user_guide.md`, `admin_builder_guide.md`, `world_building.md`). Added lightweight `.claude/skills/`, `.codex/skills/`, and `.grok/skills/` adapters that point at the canonical repo skill.

## [0.32.0] - 2026-07-05

### Changed

- **Sprint 31.3: all Tier 2 feature services are now manifest-gated (tier-split step 12b).** Previously only `economy`/`bank`/`fatigue` were gated; `movement`, `inventory`, `dialogue` (npc), `quest`, `character_info`, `exploration`, `journal`, `trade` were built unconditionally, as were the `main.py`-level `light_fuel`/`restock`/`quest_timer`/`transit` schedulable services. Now every Tier 2 service is constructed only when its owning feature is enabled; only the Tier 1 `save` service is unconditional. `ServiceContainer._FEATURE_GATED_SERVICES` maps `container_field -> (feature_key, service_cls)` (handling the `dialogue`→`npc` and `journal`→`exploration` field/key mismatches); `register_all_commands` and `main.py` guard every feature's command registration and event wiring on its service being present. `main.py` resolves the enabled feature set before constructing feature-owned services.

### Added

- **`tests/integration/test_feature_toggling.py` — feature enable/disable coverage.** Four integration tests boot a real app with a reduced feature set and assert the gating takes effect end to end: disabling `economy`/`transit` drops their services + verbs while the app still serves `/health`; all-on registers the gated verbs; an empty feature set keeps only the Tier 1 shell verbs (`help`/`save`/`load`/`quit`).

### Roadmap

- **Folded the two open player reports in `docs/issues.yaml` into a new Sprint 34** (Player-reported command polish): 34.1 `help <command>` per-command help (issue-7502f412), 34.2 `score` progress command (issue-257c6643). Synced `issues.yaml` from the runtime DB (issue-257c6643 was DB-only).

## [0.31.5] - 2026-07-05

### Fixed

- **`scripts/import_world.py` — stale pre-tier-split imports broke `./start.sh --init-dbs-if-missing`.** The world-import script still imported from the old flat module layout (`lorecraft.models.dialogue`, `lorecraft.models.items`, `lorecraft.models.player`, `lorecraft.models.quest`, `lorecraft.models.world`, `lorecraft.repos.stack_repo`), all of which moved during the tier split — so a fresh DB init crashed with `ModuleNotFoundError: No module named 'lorecraft.models.dialogue'`. Repointed to the post-split homes (`lorecraft.features.npc.models`, `lorecraft.engine.models.*`, `lorecraft.features.quests.models`, `lorecraft.engine.repos.stack_repo`). Scripts aren't covered by the test suite, so this regression slipped through the split. Verified: `import_world.py --fresh` imports the Ashmoore world (19 rooms, 35 items, 1 NPC, 1 quest, seed players) and `create_audit_db.py` both run clean.

## [0.31.4] - 2026-07-05

### Changed

- **Sprint 31: Finish tier split — WebHost abstraction (31.1) + presentation.py seam (31.2).** Tier-split refactor step 10c + §1c: `WebHost` class (webui/player/host.py) provides multi-directory Jinja `ChoiceLoader` and panel/slot registry; features with optional `presentation.py` can now contribute UI panels via `register(web_host)`. Transit feature gained `presentation.py` as proof, registering its minimap panel (id="minimap", slot="right-rail"). Loading only runs in web hosts (never headless), tier boundary enforced by test; `presentation.py` files explicitly allowed to import web modules. New `create_web_host()` + `load_feature_presentations()` in `webui/player/__init__.py`; `FeatureManifest` gains optional `presentation` field; `AppState` gains optional `web_host`. 9 WebHost unit tests + 818 suite passed.

## [0.31.3] - 2026-07-05

### Changed

- **Roadmap — reserve 34–60 for future sprints; move combat/PvP to 61–65.** Combat (61–63) and PvP/multiplayer tests (64–65) renumbered from 40–44 to open up the 34–60 range for additional foundation and feature sprints. This aligns with the strategy of front-loading exploration/trading/questing/puzzles (pillars 1–4) and deferring combat (supporting system). No code changes. Docs-only.

## [0.31.2] - 2026-07-05

### Changed

- **Roadmap — post-tier-split next-steps written in; combat/PvP deferred to last.** Corrected the status of the already-complete feature sprints (**22, 27, 28, 29** were done but missing their `✅` header mark — added). Wrote the gaps surfaced during the tier split + wishlist review into `roadmap.md` as a new **"next up" band (Sprints 31–33)**: (31) finish the tier split — `WebHost`/`presentation.py` feature-UI seam, manifest-gated feature services + enable/disable tests, and the remaining structure-doc rewrites; (32) player onboarding & account UX — in-game character creation/intro flow, per-account preferences layer, accessibility mode; (33) reporting/tooling polish — guided multi-turn `/report`, prioritized wishlist quick-wins. **Combat (31–35 previously) was renumbered to 40–44** so numeric order matches execution order, and is explicitly deferred to last. Updated "Current position" and the build-order reference accordingly. Docs-only.

## [0.31.1] - 2026-07-05

### Changed

- **Docs — `architecture.md` §4 marked superseded by the tier split.** Added a banner noting the flat `game/`/`models/`/`services/` tree predates the tier split and pointing to `architecture_tiers.md` §0 (current layout) + `tier_split_refactor.md`; the tree is retained as the conceptual module map. Docs-only.

## [0.31.0] - 2026-07-05

### Added

- **Player creation: username feedback + configurable password policy (docs/wishlist.md).** The lobby "Create New Character" form now gives real validation feedback and enforces a password policy:
  - **Username** — the create field validates live against `^[A-Za-z0-9_-]{3,30}$` (border turns red/green as you type; the valid example is `Ashen_Wanderer`, not the old invalid "Ashen Wanderer"), with the server as backstop.
  - **Password** — a second **confirm-password** field with a live "passwords match" indicator and a per-requirement checklist; submit is disabled until valid. Enforced server-side by the new `PasswordPolicy` / `validate_password` (`webui/player/password_policy.py`) on both the HTMX create route and the JSON `POST /auth/login` — only when a _new_ credential is set, never on ordinary login.
  - **Configurable with defaults** (`LORECRAFT_PASSWORD_*`): `min_length=8`, `max_length=32`, `require_mixed_case=true`, `require_number=true`, `require_symbol=false`.
  - Validation failures now **re-render the lobby with an inline error** (HTTP 400) instead of a raw error page (both the Create and Log In tabs).
  - `main.py`'s brittle field-by-field `Settings` rebuild was replaced with `dataclasses.replace`, so new settings fields are forwarded automatically (this is also what makes the password env vars take effect). New tests: `test_password_policy.py` (12) + create-flow integration tests (confirm-mismatch, weak-password). Full suite 809 passed, lint + typecheck clean; verified end-to-end against a live server (weak → 400 inline, valid → 303).

## [0.30.1] - 2026-07-05

### Changed

- **Tier split — docs mark the structural refactor complete (branch `tier_split`).** `tier_split_refactor.md`'s "Current status" now states the split is structurally done (engine fully import-pure, 24 feature packages, `webui/` web hosts, boundary-enforced) and reframes the remaining `WebHost`/`presentation.py` seam (steps 10c/11) as _additive framework deliberately deferred until a feature needs feature-owned UI_ (per `AGENTS.md` and §1b), with feature enable/disable tests (12b) as a follow-on. `AGENTS.md`'s structure section updated for the `webui/` move and feature-owned command verbs. Docs-only.

## [0.30.0] - 2026-07-05

### Changed

- **Tier split — web hosts extracted into `webui/` (step 10b, branch `tier_split`).** The player web UI moved `src/lorecraft/web/` → `src/lorecraft/webui/player/`, and the admin console moved `src/lorecraft/admin/` → `src/lorecraft/webui/admin/` (with `web/admin/index.html` → `webui/admin/index.html`). All `lorecraft.web.*` → `lorecraft.webui.player.*` and `lorecraft.admin.*` → `lorecraft.webui.admin.*` imports rewritten; hardcoded Jinja template dirs, `main.py`'s `WEB_DIR`/`ADMIN_WEB_DIR`, the `pyproject.toml` `package-data`, and the basedpyright `exclude` all updated. Web is now the "third axis" (`webui/`, audience-named `player`/`admin`) that composes engine + features, as the design intended — separate from Tier 1 `engine/` and Tier 2 `features/`. Verified: full suite 796 passed, lint + typecheck clean, and a live `uvicorn` boot serves `/health`, `/lobby` (Jinja templates), `/admin` (HTML shell), and `/static/*` from the new paths. **Still open:** the `WebHost` abstraction (multi-dir Jinja `ChoiceLoader` + panel/slot registry, step 10c) and the `presentation.py` feature-UI seam (step 11) — additive framework with no current consumer.

## [0.29.0] - 2026-07-05

### Changed

- **Tier split — `connection_manager`/`broadcast` → engine; `game/` package deleted; engine is now fully import-pure (step 10a, branch `tier_split`).** `game/connection_manager.py` and `game/broadcast.py` were the last two modules in the legacy `game/` package. `ConnectionManager` depends only on `lorecraft.types.JsonWebSocket` (a Protocol) — transport-agnostic, genuinely Tier 1 — so both moved to `engine/game/`, and the empty `src/lorecraft/game/` package was removed. This turned `GameContext`'s `manager` import into engine→engine. Separately, `GameContext.news_repo` (the last non-engine import in the engine, `repos.news_repo`) was removed; the `/news` command builds `NewsRepo(ctx.session)` itself. **Result: every module under `src/lorecraft/engine/` now imports only `engine.*` and `lorecraft.types`** — no `features/`, no web, no `services`/`models`/`repos`/`commands`/`content`. Full suite 796 passed, lint + typecheck clean.

## [0.28.0] - 2026-07-05

### Changed

- **Tier split — feature verbs co-located with their features (step 9, branch `tier_split`).** The nine single-feature command modules moved from the shared `commands/` bucket into their owning feature packages as `features/<feature>/commands.py`: `movement`, `inventory`, `character`, `exploration`, `condition`→`fatigue`, `economy`, `bank`, `trade`→`trading`, `transit`. What remains in `commands/` is the shell/out-of-character layer — `meta` (help/quit/save/load), `social` (say/talk/choice/bye), `news`, `report` — which span concerns (say/talk touch the `npc` feature; `/news` and `/report` touch content) rather than belonging to one feature, plus `register_all_commands`, now documented as the **composition root** that wires the shell verbs together with every feature's verbs. This keeps the engine boundary intact (the engine owns the `CommandRegistry` mechanism but provides no verbs; `commands/` is a composition layer that may import features, which the engine may not). Full suite 796 passed, lint + typecheck clean. Deviation from the plan's "delete `register_all_commands`, each feature self-registers via its manifest" ideal is intentional and documented — the dispatcher is retained as a low-churn composition point (it is called by ~30 tests and `main.py`); converting to fully manifest-driven command registration is a follow-on.

## [0.27.1] - 2026-07-05

### Changed

- **Tier split — docs brought current with the shipped layout (step 13a, branch `tier_split`).** `architecture_tiers.md` gains a status banner + an "Implemented Layout" section and no longer claims the split is "not yet reflected"/"planned"; `tier_modules.md` gains an old-path→new-home translation map and notes the tier re-classifications (ledger + item-component-state accessor → Tier 1; movement → Tier 2); `AGENTS.md` gains a "Codebase structure (tier split)" section stating the engine⇏features rule and where new engine/feature code goes; `tier_split_refactor.md` gains a "Current status" section and updated tracker (steps 7, 8 ✅; 12, 13 🚧). Docs-only.

## [0.27.0] - 2026-07-05

### Added

- **Tier split — import-direction boundary enforcement (step 12, part 1, branch `tier_split`).** New `tests/unit/test_tier_boundaries.py` parses every module's imports with `ast` (catching lazy in-function imports, not just top-level) and fails with the exact `file -> module` pairs if the tier boundary is crossed: `engine/` may not import `features/` or a web host (`lorecraft.web`/`lorecraft.webui`), and `features/` may not import a web host. Both tests pass — the boundary the refactor built is now a regression guard that runs in `make test` (and therefore CI). The remaining part of step 12 (feature enable/disable integration tests) is still open.

## [0.26.0] - 2026-07-05

### Changed

- **Tier split — `GameContext` purged of Tier 2 repos; engine is now import-clean of `features/` (branch `tier_split`).** The Tier 1 `GameContext` carried `quest_repo: QuestRepo | None` and `dialogue_repo: DialogueRepo | None`, forcing `engine/game/context.py` to import `features.quests.repo` and `features.npc.repo` — the last engine→features leak. Those two fields are removed; the features that need them now build `QuestRepo(ctx.session)` / `DialogueRepo(ctx.session)` locally (quests service, exploration journal, npc side effects, npc dialogue). `build_game_context()` no longer constructs them. Result: **nothing under `src/lorecraft/engine/` imports `lorecraft.features` anymore** — the Tier 1/Tier 2 boundary holds in the one direction that matters. Full suite 794 passed, lint + typecheck clean. (`context.py` still references `game.connection_manager` and `repos.news_repo`, which are web-plumbing/content, not features — addressed by the web/content steps.)

## [0.25.0] - 2026-07-05

### Changed

- **Tier split — movement + NPC subsystem co-located; step 8 feature migration complete (batch 8, branch `tier_split`).**
  - **movement feature** (new) — `services/movement.py` → `features/movement/service.py`. Classified Tier 2 (not an engine primitive) because `MovementService.move()` is terrain-gated and skill-checked, depending on the `terrain` and `skills` features.
  - **npc feature** (new) — the whole NPC/dialogue subsystem co-located: `npc/dialogue.py` → `dialogue.py`, `npc/dialogue_conditions.py`, `npc/side_effects.py`, `npc/scheduler.py`, `models/dialogue.py` → `models.py`, `repos/dialogue_repo.py` → `repo.py`. Kept out of `engine/` because the dialogue side effects reach into inventory/quests; a future refinement could lift the pure tree traversal into the engine behind a Tier 1 side-effect registry. The empty `src/lorecraft/npc/` package was removed.
  - `services/__init__.py` slimmed to just its docstring (the package now holds only the composition `ServiceContainer`).
    `discover_features()` now returns **24 features**. Full suite 794 passed, lint + typecheck clean.
  - **Step 8 status:** every Tier 2 game mechanic is now co-located under `features/<x>/`. What remains in the legacy dirs is not Tier 2 game code: `game/{broadcast,connection_manager}.py` (web plumbing → step 10 `webui/`), `services/container.py` (the composition hub), and `models/{admin,issue,news,combat,changeset}.py` + `repos/{issue,news}_repo.py` (admin console, `/report`+`/news` content, a combat stub, and world-versioning — addressed by later steps / their own homes).

## [0.24.0] - 2026-07-05

### Changed

- **Tier split — ledger corrected to Tier 1; items/character features + restock relocated (step 8, batch 7, branch `tier_split`).**
  - **ledger → engine (Tier 1 fix).** `LedgerService` is carried by the Tier 1 `GameContext` (`ctx.ledger`), so coin/currency movement is a core primitive, not a feature. `services/ledger.py` → `engine/services/ledger.py`, `models/ledger.py` → `engine/models/ledger.py`, `repos/ledger_repo.py` → `engine/repos/ledger_repo.py`. `CoinBalance` moved to the `engine/models/__init__.py` aggregator. This removes an engine→`services` import from `context.py`.
  - **items feature** (new) — `game/item_effects.py` → `features/items/effects.py`, `game/item_rules.py` → `features/items/rules.py`. Passive manifest (`register_item_rules` still called from `main.py`).
  - **character feature** (new) — `services/character_info.py` → `features/character/service.py`. Passive manifest.
  - **restock → economy** — `services/restock.py` → `features/economy/restock.py` (it only ever read the economy repo).
    `discover_features()` now returns 22 features. Full suite 794 passed, lint + typecheck clean.

## [0.23.0] - 2026-07-05

### Changed

- **Tier split — four larger features co-located (step 8, batch 6, branch `tier_split`).** New feature packages, each with service + tables + repo (+ conditions/timer):
  - **transit** — `services/transit.py` → `service.py`, `models/transit.py` → `models.py`, `repos/transit_repo.py` → `repo.py`.
  - **quests** — `services/quest.py` → `service.py`, `services/quest_timer.py` → `timer.py`, `models/quest.py` → `models.py`, `repos/quest_repo.py` → `repo.py`, `game/quest_conditions.py` → `conditions.py` (its standard predicates register on import; consumers `quests`/`npc_memory` import it via `import conditions as quest_conditions` to keep the binding name).
  - **trading** — `services/trade.py` → `service.py`, `models/interaction.py` → `models.py` (`TradeOffer` + `PvpConsent`), `repos/trade_repo.py` → `repo.py`.
  - **inventory** — `services/inventory.py` → `service.py`.
    All passive manifests (services stay wired via the `ServiceContainer`/`main.py`); `discover_features()` now returns 20 features. `Quest`/`PlayerQuestProgress`/`TradeOffer`/`PvpConsent` dropped out of the `models/__init__.py` aggregator. Command modules remain in `commands/` until step 9. Full suite 794 passed, lint + typecheck clean.

## [0.22.0] - 2026-07-05

### Changed

- **Tier split — five small features co-located (step 8, batch 5, branch `tier_split`).** New feature packages: `warmth` (`game/warmth.py` → `rules.py`), `terrain` (`game/terrain.py` → `definitions.py`), `weather` (`clock/weather.py` → `handlers.py`), `light` (`services/light_fuel.py` → `service.py`), `encumbrance` (`game/encumbrance.py` → `rules.py`), each with a passive manifest. `discover_features()` now returns 16 features. `weather`'s `register_weather_handlers` and `light`'s service stay wired from `main.py` (they need the live bus/engine/rng), so their manifests are passive for now — this also preserves exact bus-handler registration order. `clock/` is now empty of code. Full suite 794 passed, lint + typecheck clean.
  - _Fixed in-flight:_ the bare `from lorecraft.game import encumbrance` rewrite initially dropped the binding name (`encumbrance` → `rules`), silently breaking fatigue's travel-drain (the `NameError` was swallowed by the event bus); restored via `import rules as encumbrance`. A fatigue test caught it.

## [0.21.0] - 2026-07-05

### Changed

- **Tier split — five more features co-located (step 8, batch 4, branch `tier_split`).** `economy`, `bank`, `npc_memory`, `skills`, and `exploration` now own their code under `features/<x>/`:
  - **economy** — `economy_holders.py` → `holders.py`, `services/economy.py` → `service.py`, `models/economy.py` → `models.py`, `repos/economy_repo.py` → `repo.py`.
  - **bank** — `bank_holders.py` → `holders.py`, `services/bank.py` → `service.py`, `models/bank.py` → `models.py`, `repos/bank_repo.py` → `repo.py`.
  - **npc_memory** — `npc/npc_memory_conditions.py` → `conditions.py`, `models/npc_memory.py` → `models.py`, `repos/npc_memory_repo.py` → `repo.py`.
  - **skills** (new package) — `game/skills.py` → `definitions.py`, `services/skills.py` → `service.py`. Passive manifest (registers nothing on shared registries beyond the skill defs its consumers import directly; skill defs stay idempotently registered on import).
  - **exploration** (new package) — `game/exploration.py` → `rules.py`, `services/exploration.py` → `service.py`, `services/journal.py` → `journal.py`. Passive manifest.
    `discover_features()` now returns 11 features (adds `skills`, `exploration`). Command modules (`commands/economy.py`, `commands/bank.py`, `commands/exploration.py`) stay put until step 9's dispatcher dissolution; their imports were rewritten. Full suite 794 passed, lint + typecheck clean.

## [0.20.0] - 2026-07-05

### Changed

- **Tier split — five features co-located into their packages (step 8, batch 3, branch `tier_split`).** `traits`, `equipment`, `fatigue`, `item_components`, and `containers` now own their code under `features/<x>/` instead of pointing back at `game/`/`services/`:
  - **traits** — `game/traits.py` **split** along its natural seam: the Tier 1 registry primitives (`TraitDef`, `TraitSource`, `TraitRegistry`, `get_registry`) stay in the engine at `engine/game/traits.py`, while the Tier 2 sources (`ActiveEffectTraitSource`, `TraitModifierSource`, `register()`) move to `features/traits/sources.py`. `standard_traits.py` → `standard.py`, `services/traits.py` → `service.py`.
  - **equipment** — `equipment_slots/source/validators.py` → `features/equipment/{slots,sources,validators}.py`.
  - **fatigue** — `fatigue_source.py` → `source.py`, `services/fatigue.py` → `service.py`.
  - **item_components** — `standard_components.py` → `components.py`. Separately, `services/item_components.py` was recognized as **Tier 1** (a generic per-instance component-state accessor depending only on `engine.models.items`, and already imported by Tier 1 `engine/game/command_conditions.py`) and moved to `engine/services/item_components.py`, fixing a latent engine→feature import.
  - **containers** — `container_validators.py` → `features/containers/validators.py`.
    Imports rewritten across `src/` and `tests/`; feature manifests and docstrings updated to reflect co-location. Full suite 794 passed, lint + typecheck clean.

## [0.19.0] - 2026-07-05

### Changed

- **Tier split — reputation is now a self-contained feature package (step 8, batch 2, branch `tier_split`).** The reputation feature's four scattered files were pulled into `features/reputation/`: `game/reputation_conditions.py` → `conditions.py`, `services/reputation.py` → `service.py`, `models/reputation.py` → `models.py`, `repos/reputation_repo.py` → `repo.py` (history-preserving `git mv`, dropping the now-redundant `reputation_` prefixes). Imports rewritten across `src/` and `tests/`; `db.py` now imports the `Reputation` table from `features.reputation.models` (table registration unchanged), and the model dropped out of the `models/__init__.py` aggregator. This is the first end-to-end Tier 2 vertical slice proving the step-8 pattern (conditions + service + model + repo co-located, wired via the manifest). Full suite 794 passed, lint + typecheck clean.

## [0.18.0] - 2026-07-05

### Changed

- **Tier split — Tier 1 models moved into `engine/models/` (step 8, batch 1, branch `tier_split`).** Nine pure-Tier-1 model files (`world`, `player`, `player_auth`, `items`, `meters`, `scheduler`, `mobile`, `audit`, `session`) moved to `engine/models/` via history-preserving `git mv`; all `lorecraft.models.*` imports for them rewritten to `lorecraft.engine.models.*` across `src/` and `tests/` (including `db.py`, the SQLModel table-registration aggregator). The Tier 1 model classes are now re-exported from `engine/models/__init__.py`; `models/__init__.py` keeps only the remaining Tier 2 tables. Table creation is unaffected — `db.py` registers each table by class, independent of module location. No package-level `from lorecraft.models import X` usages existed, so the re-export split is purely cosmetic. Full suite 794 passed, lint + typecheck clean. The remaining Tier 2 model files move into their `features/` packages as each feature is migrated.

## [0.17.0] - 2026-07-05

### Changed

- **Tier split — world clock moved into `engine/clock/`; season calendar decoupled from weather (step 7, batch 3, branch `tier_split`).** `clock/world_clock.py` moved to `engine/clock/world_clock.py`. To keep the engine free of Tier 2 imports, the season calendar (`SEASONS`, `DAYS_PER_SEASON`, `season_for_day`) — a Tier 1 clock concern, since `WorldClock.current_season` is a core field — was **hoisted out of Tier 2 `clock/weather.py` into `world_clock.py`**, removing the engine→feature import it previously had. Tier 2 `weather.py` stays in `clock/` and keeps its self-contained `WEATHER_TABLE` (season-name literals), so it needs no back-import into the clock. Imports rewritten across `src/` and `tests/`. Full suite 794 passed, lint + typecheck clean.
- **Note on Tier 1 models.** The pure-Tier-1 model files (`world`, `player`, `items`, `meters`, `scheduler`, `mobile`, `audit`, `session`) remain in `models/` for now: the directory is a shared SQLModel registration aggregator (`models/__init__.py`) where Tier 1 and Tier 2 tables coexist, so its split is sequenced together with the Tier 2 model relocation in step 8 rather than half-split with compat shims.

## [0.16.0] - 2026-07-05

### Changed

- **Tier split — Tier 1 services and repos moved into `engine/` (step 7, batch 2, branch `tier_split`).** Seven Tier 1 services (`scheduler`, `item_location`, `meters`, `effects`, `save`, `mobile_route`, `audit`) moved to `engine/services/`, and nine Tier 1 repositories (`base`, `item_repo`, `player_repo`, `room_repo`, `stack_repo`, `scheduler_repo`, `meter_repo`, `audit_repo`, `npc_repo`) moved to `engine/repos/` (history-preserving `git mv`). Imports across `src/` and `tests/` rewritten to `lorecraft.engine.services.*` / `lorecraft.engine.repos.*`. The public repo re-exports (`AuditRepo`, `ItemRepo`, `NpcRepo`, `PlayerRepo`, `RoomRepo`) now live in `engine/repos/__init__.py`; the old `repos/`/`services/` package inits are trimmed to their remaining Tier 2 members. No behaviour change — full suite 794 passed, lint + typecheck clean. The moved code still imports `lorecraft.models.*` (Mixed; models core split is deferred).

## [0.15.0] - 2026-07-05

### Changed

- **Tier split — `engine/` package created; Tier 1 `game/` modules moved (step 7, batch 1, branch `tier_split`).** New `src/lorecraft/engine/` package now holds the pure-Tier-1 engine primitives. The 18 Tier 1 modules from `game/` — `registry`, `context`, `events`, `engine`, `parser`, `grammar`, `command_patterns`, `command_conditions`, `holders`, `modifiers`, `components`, `rng`, `checks`, `effects`, `meters`, `transaction`, `diagnostics`, `rules` — moved to `engine/game/` (history-preserving `git mv`), and every import across `src/` and `tests/` was rewritten to `lorecraft.engine.game.*`. No behaviour change and no code edits beyond import paths — full suite 794 passed, lint + typecheck clean. Tier 2 `game/` modules (traits, equipment, fatigue, economy/bank holders, etc.) stay put; they move into `features/` in step 8. `context.py`'s reference to `game.connection_manager` is unchanged (that module is web plumbing and moves to `webui/` in step 10).

## [0.14.10] - 2026-07-04

### Changed

- **Tier split — conditional service construction (step 6, branch `tier_split`).** `ServiceContainer.build()` now takes an `enabled` feature set: the migrated feature-services `economy`, `bank`, and `fatigue` are instantiated only when their feature is enabled (`None` otherwise), and `register_all_commands` skips a gated feature's verbs when its service is absent. `create_app` resolves the enabled set before building services and threads it through. Default is "all on", so a normal boot and every test (which call `ServiceContainer.build()` with no args) are unchanged — full suite 794 passed. The remaining always-on services stay unconditional until their features are migrated; the container becomes fully feature-driven in step 8. 5 new tests (`test_service_container.py`).

## [0.14.9] - 2026-07-04

### Changed

- **Tier split — traits/equipment/fatigue/components/containers migrated to feature manifests (step 5c, branch `tier_split`).** The last seven self-registering modules (`traits`, `standard_traits`, `fatigue_source`, `standard_components`, `equipment_source`, `equipment_validators`, `container_validators`) now expose `register()` instead of registering at import, wrapped by new feature packages: `traits` (traits + standard_traits), `equipment` (depends on `traits`), `fatigue`, `item_components`, and `containers` (depends on `item_components`). **`main.py` now has zero feature side-effect imports** — all Tier 2 registration flows through the manifest/discover/wire path. Six test files updated to call `register()` explicitly.
- **Idempotency guards for append-based registrations.** Because a `register()` can now run more than once per process (multiple test files + app startup sharing a worker), registrations that _append_ to a list — modifier sources, trait sources, holder move-validators — gained a module-level `_registered` guard to prevent double-application (a bug that doubled equipment stat bonuses before the fix). Name/key registries (holders, components, conditions, side effects) are naturally idempotent and need no guard. Documented as a migration note in `tier_split_refactor.md`. Full suite 789 passed.

## [0.14.8] - 2026-07-04

### Changed

- **Tier split — NPC memory migrated to a feature manifest (step 5b, branch `tier_split`).** `npc/npc_memory_conditions.py` now exposes `register()` instead of registering its `npc_remembers` dialogue/quest conditions and `remember` side effect at import; new `features/npc_memory/` package wraps it in a manifest. Side-effect import removed from `main.py`; `test_npc_memory.py` calls `register()` explicitly. `npc_memory` added to the parametrized migrated-features test. Full suite 774 passed.

## [0.14.7] - 2026-07-04

### Changed

- **Tier split — economy + bank holder types migrated to feature manifests (step 5a, branch `tier_split`).** `game/economy_holders.py` (the "shop" holder) and `game/bank_holders.py` (the "bank_account" holder) now expose `register()` instead of self-registering at import; new `features/economy/` and `features/bank/` packages wrap them in manifests. Their side-effect imports are gone from `main.py`; `test_economy.py`/`test_bank.py` call `register()` explicitly. The reputation-specific feature test was generalized into `test_migrated_features.py`, parametrized over the growing set of migrated keys (`reputation`, `economy`, `bank`). Full suite 765 passed.

## [0.14.6] - 2026-07-04

### Changed

- **Tier split — reputation migrated to a feature manifest (step 4, branch `tier_split`).** First real feature moved onto the config-driven path: `lorecraft.game.reputation_conditions` now exposes a `register()` function instead of registering its conditions/side effect as an import side effect, and a new `lorecraft/features/reputation/` package wraps it in a `FeatureManifest`. The `import lorecraft.game.reputation_conditions  # noqa` line is gone from `main.py`; reputation is now discovered, enabled by default (or via `LORECRAFT_FEATURES`), and genuinely disableable. Two tests that relied on the old import side effect now call `register()` explicitly. Full suite 765 passed. 4 new tests (`test_reputation_feature.py`) cover discovery, default-on, disable, and wiring.

## [0.14.5] - 2026-07-04

### Added

- **Tier split — feature wiring in `create_app` (step 3, branch `tier_split`).** `create_app` now discovers feature packages, resolves the enabled set, dependency-orders it, and calls each feature's `register_fn` at startup. Enablement precedence: explicit `enabled_features=` arg > `LORECRAFT_FEATURES` env var (comma-separated) > all discovered features. Two new loader helpers: `resolve_enabled_features` and `wire_features`. Because no feature has been migrated to a manifest yet, the registry is empty and this is a runtime no-op — the existing side-effect imports still do all wiring — so behaviour is unchanged (full suite: 761 passed). 7 unit tests (`test_feature_config.py`).

## [0.14.4] - 2026-07-04

### Added

- **Tier split — feature loader (step 2, branch `tier_split`).** New `lorecraft.features.loader`: `discover_features()` imports every feature subpackage so its manifest self-registers (auto-discovery, replacing a hand-maintained import list), and `load_features(enabled, registry)` validates the enabled set and returns it in dependency order — raising on an unknown feature key, a dependency that isn't enabled, or a dependency cycle. Still additive; nothing calls it yet. 8 unit tests (`test_feature_loader.py`) cover ordering, transitive deps, unknown/missing-dependency/cycle errors, and idempotent discovery.

## [0.14.3] - 2026-07-04

### Added

- **Tier split — feature manifest (step 1, branch `tier_split`).** New `lorecraft.features` package with `manifest.py`: a frozen `FeatureManifest` descriptor (`key`, `name`, `dependencies`, optional `register_fn` wiring hook, optional `presentation` dotted-path for web UI) plus a `FEATURE_REGISTRY` catalogue and `register_feature`/`get_feature` helpers. This is the additive backbone that will replace `main.py`'s brittle side-effect feature imports with config-driven loading. Purely additive — no existing behaviour changes, no code moved yet. 7 unit tests (`test_feature_manifest.py`).

## [0.14.2] - 2026-07-04

### Docs

- **Tier split refactor — planning + tracking (branch `tier_split`).** Added `docs/tier_split_refactor.md`: the plan to physically separate the engine (Tier 1), optional features (Tier 2), and web hosts into `engine/`, `features/`, and `webui/{player,admin}/`, replace brittle side-effect imports with a config-driven feature manifest/loader, and add a documented `presentation.py` seam for feature-contributed web UI (§1c — authoritative builder/admin guidance on how feature panels/partials/JS load into the player web host). Document carries its own progress tracker and stays off `roadmap.md`. Renamed from the initial all-caps filename to `tier_split_refactor.md`.

## [0.14.1] - 2026-07-04

### Fixed

- **Database schema migration for Sprint 30.2 fields** — Added missing columns to existing databases: `item.mechanism_states`, `item.mechanism_side_effects`, `item.combination_side_effects`, and `playerquestprogress.stage_started_epoch`. The schema migration logic runs automatically on startup for SQLite databases.

## [0.14.0] - 2026-07-04

### Added

- **Sprint 30: Quests & puzzles depth** — branching, consequence-bearing quests and environmental puzzles (pillars #3–4), closing out the Tier 2 feature band's non-combat sprints.
  - **30.1 — Branch conditions + consequences, NPC memory:** Quest stages gain an optional `branches` list (`docs/dialogue_npcs_quests.md`): once a stage's own `conditions` pass, the first branch whose _own_ extra `conditions` also pass wins, applying its `side_effects` (any handler on the existing `npc/side_effects.py` registry — `set_flags`, `give_item`, `remember`, the new `adjust_reputation`, ...) and moving to its `next_stage` (or completing the quest if `null`). Stages with no `branches` keep the pre-existing linear "advance to `stages[idx+1]`" behavior unchanged — full backward compatibility with quests authored before this sprint. A new `terminal: true` stage flag completes the quest as soon as that stage's conditions pass, regardless of its array position (needed because a branch-reached ending doesn't have to sit last in the list). Quest conditions moved from a hardcoded if/elif chain to a pluggable `game/quest_conditions.py` registry (mirroring `npc/dialogue_conditions.py`), so new condition types (like the new `npc_remembers`) register without touching `services/quest.py`. New `NpcMemory` table + `NpcMemoryRepo` (`models/npc_memory.py`, `repos/npc_memory_repo.py`) back a `remember` dialogue side effect and `npc_remembers` dialogue/quest condition — a memory key like `"helped"` is scoped per-(player, NPC), so the same key means something different for Thor than for Mira, without pre-naming one global flag per NPC pair. `game/reputation_conditions.py` gained the `adjust_reputation` side effect (the flip side of its existing `min_reputation`/`reputation_at_least` gates), making standing changes an authored _consequence_, not just a gate. 16 new unit tests (`test_quest_branching.py`, `test_npc_memory.py`).
  - **30.2 — Mechanism/item-combination puzzles + timed quest events:** New `"mechanism"` standard item component (`game/standard_components.py`) for levers/dials: `Item.mechanism_states` (an ordered list like `["off", "on"]` or `["0".."3"]`) plus `mechanism_side_effects` (keyed by state name, applied once when a mechanism transitions into that state — typically `set_flags`, which existing `Exit.condition_flags`/dialogue/quest gates already consume, making a lever "solving" a one-way trigger rather than a live "must currently be in state X" check). New `turn`/`pull`/`activate` commands (aliases, `commands/inventory.py`) cycle a mechanism's state. Item-combination puzzles: `Item.combination_side_effects` (keyed by the other item's id, checked in both authoring directions) lets a successful `use X with Y` apply a real consequence instead of just "It works!" flavor text. New `services/quest_timer.py`'s `QuestTimerService` (engine-holding schedulable, same shape as `RestockService`) sweeps every player's active quest progress on `TIME_ADVANCED`: a stage's `timeout_ticks`/`on_timeout` (fallback `next_stage`, `message`, `set_flags`) lets a quest branch to a consequence stage or fail outright if the player doesn't act in time — entirely data-driven, no per-quest special-casing. New `PlayerQuestProgress.stage_started_epoch` (game-epoch, not wall-clock) backs the timeout math. A new `/partials/quest-tracker` route + a per-player `state_change` push lets this scheduler-driven (no in-flight HTTP request) quest change still live-refresh the quest tracker panel for the one affected player, without broadcasting to their room (quest state is private). 18 new unit tests (`test_mechanism_command.py`, `test_quest_timer.py`, item-combination cases in `test_use_command.py`) + 8 world-loader/validator tests (`test_quest_puzzle_world_schema.py`) covering the new YAML authoring fields and their cross-reference validation.
  - Full suite (739 unit/integration + 10 e2e + 5 simulation) green; types clean; no regressions.

## [0.13.0] - 2026-07-04

### Added

- **Sprint 29.3: Transit minimap animation** — Vehicles now show animated markers on the minimap during transit (ferries, balloons, rail, caravans). `TransitService` implements an `on_tick` hook that emits `transit_update` WS messages with interpolated position (from/to coordinates), progress (0–1), ETA, and vehicle mode for icon selection. Backend sets `tick_pushes=5` per segment for lines with `animate_minimap: true`, triggering scheduler jobs that fire the hook during `in_transit`. Frontend handler in `app.js` receives `transit_update`, interpolates vehicle coordinates using the minimap scaling system, and renders a mode-specific emoji icon (⛴/🚂/🎈/🐎 etc.) on the SVG minimap. Weather grounding (balloon/ferry delayed or halted by weather) was already working via Sprint 29.2's `may_depart` hook. 9 new unit tests verify `tick_pushes` configuration, message format, and hook execution.

## [0.12.4] - 2026-07-04

### Added

- **`/news` and `/report` slash aliases** — registered as literal extra verb strings on the existing `news`/`report` commands (same mechanism as `bye`/`farewell`/`goodbye`), so out-of-character/system commands are reachable with the conventional `/` prefix players expect. No parser architecture change: `/news`/`/report` are just additional keys in the command registry pointing at the same handlers. `/report` was also added to `game/grammar.py`'s `FREE_TEXT_VERBS` so it gets the same verbatim free-text handling as `report` (no preposition-splitting). A generic, prefix-character-aware parser (`/` for system commands, `@`/`!` for others) was considered and deliberately deferred — the existing `CommandScope.GLOBAL` already encodes "always available regardless of context" in code, and the broader idea is already tracked in `roadmap.md`'s backlog ("Offline/IRL commands `/system`, `@someone`").

## [0.12.3] - 2026-07-04

### Changed

- **docs:** replaced the now-stale wishlist entry for a player-facing report command (shipped in 0.12.0) with a new one describing the requested upgrade — a guided, multi-turn issue-report wizard (`report issue` / `report player <name>`, follow-up prompts for title/description, a new "reported against" player link) instead of today's single free-text command. Deliberately deferred; no code change.

## [0.12.2] - 2026-07-04

### Fixed

- **WebUI: multi-line messages (e.g. `help`) rendered as one giant wrapped line** — `help`'s output (and any other multi-line message, like `journal`) is a single string joined with `\n` between lines, but the feed template's message `<span>` had no whitespace styling, so the browser collapsed every newline into a single space — all the command entries ran together in one unreadable paragraph. Added Tailwind's `whitespace-pre-line` utility (preserves line breaks, still wraps and collapses ordinary runs of spaces) to the message span in both `feed_item.html` and `feed_items.html`.

## [0.12.1] - 2026-07-04

### Fixed

- **WebUI: recalling a command with ↑ then pressing Enter didn't submit it** — `app.js`'s command-history handler set the input's raw DOM `.value` directly on ArrowUp/ArrowDown, which never fires a native "input" event, so Alpine's `x-model="localCommand"` binding on that field never saw the change. `localCommand` stayed stale (usually `""`), which kept the Send button's `:disabled="!localCommand.trim()"` true even though the field visibly showed the recalled text — and a disabled submit control blocks a browser's implicit submit-on-Enter for the form. New `setInputValue()` helper dispatches a real `input` event after every programmatic `.value` write, keeping Alpine's model in sync. New e2e regression test (`test_arrow_up_history_recall_then_enter_submits`) confirmed failing without the fix and passing with it. Also fixed a pre-existing e2e test file (`test_ui_refresh_on_item_actions.py`, added in the 0.11.3 work) that had never actually run — it used the async Playwright API against this project's sync fixtures and a made-up `ashmoore_player` fixture that doesn't exist, plus a wrong room-graph direction (`south` instead of `north`, `north`) to reach Locksmith's Gallery; rewritten to match the working conventions in `test_gameplay_flows.py`/`test_map_and_mobile_ui.py` and now passes for real.

## [0.12.0] - 2026-07-04

### Added

- **`report` command: player-facing bug/feedback reports wired to the issue tracker** — New `report <description>` command (`commands/report.py`, GLOBAL scope, always available including mid-dialogue) creates a real `Issue` row via a new shared `content/issues.py`'s `create_issue()` helper — the same construction path the admin `POST /admin/issues` endpoint now calls too (refactored to remove the duplicated construction logic), so reports show up immediately in the existing admin issues list/TUI panel. Tagged `component="player-report"`/`tags=["player-report"]` for easy filtering; `created_by` is the reporting player's username. Long reports are truncated at 1000 characters (noted in the confirmation message); the title is a shortened summary of the description.
- Fixed a real, previously-unnoticed parser bug found while building this: any free-text argument containing a preposition word ("in", "on", "at", "with", "from", ...) or certain adjective-like words got silently mangled — split at the preposition and/or stripped of articles ("the", "a", "some", "one") anywhere in the text, not just leading ones — because free-text commands were being routed through the same phrase-parsing rules built for matching item names (`take the red apple`). New `FREE_TEXT_VERBS` set (`game/grammar.py`) exempts `report` from all of that: its entire argument is joined verbatim into a `message` role. Scoped narrowly to `report` only — `say`/`whisper`/`shout`/`yell`/`scream`/`tell` keep their existing (tested, intentional) `to <recipient>` preposition-splitting behavior unchanged.

## [0.11.4] - 2026-07-04

### Fixed

- **World versioning: displaced players desynced `ConnectionManager` room-tracking** — Promoting a changeset that deactivates a room moves any occupants to its `fallback_room_id` in the DB, but never told `ConnectionManager` — the noted follow-up from the 0.11.3 player-visibility fix. `VersioningService.promote()`/`_apply_item()`/`_apply_room()` now take an optional `manager: ConnectionManager`, and the room-deactivation path calls `manager.move_player()` for each displaced player, matching every other room-change path (`services/movement.py`, `services/transit.py`, `admin/routers/players.py`). `admin/routers/world.py`'s `promote_changeset` endpoint passes `state.manager`. Without this fix, a connected player displaced by a changeset promotion would miss real-time broadcasts in their new room until their next `move()` call happened to self-heal the stale tracking. New integration test (`test_promote_deactivate_updates_connection_manager_tracking`).

## [0.11.3] - 2026-07-04

### Fixed

- **Player visibility: missing arrival narration & stale connection tracking** — Movement (`services/movement.py`) only ever narrated a _departure_ ("X leaves east.") to the room a player left; the room they arrived in got a silent panel-refresh nudge but no feed message at all, so "THE CHRONICLE" never showed arrivals. `GameContext` gains a second narration channel — `tell_arrival()`/`arrival_messages`, distinct from `tell_room()`/`room_messages` — and `broadcast_command_effects()` (`game/broadcast.py`) now sends it to the destination room ("X arrives from the west."), excluding the mover. Wired into `movement.py`'s `move()` (via a new `OPPOSITE_DIRECTIONS` map in `game/grammar.py`) and `transit.py`'s `board()`/`disembark()`. Also fixed `ConnectionManager.disconnect()` (`game/connection_manager.py`), which cleared the WS connection but never removed the player from its room-tracking dicts (`_player_rooms`/`_room_players`) — a stale-state leak that could misdirect `broadcast_to_room` targeting after a player disconnects. Updated the Sprint 12/14 multiplayer simulation test to assert the new arrival broadcast; 1 new/updated unit test assertion in `test_movement.py`.
- **WebUI: room-items panel not refreshing after in-place item actions** — "CURRENT LOCATION"'s "You notice: ..." list only re-rendered when the player changed rooms (`room_changed`), so `get all`/`drop`/`use` left stale items showing in the pane even though `look` and the inventory panel were correct. `web/frontend.py`'s `POST /command` now also refreshes it whenever `ctx.room_messages` is non-empty (i.e. something narratable happened in the room), not just on movement.
- **WebUI: actor saw both their own action message and the room's narration of it** — After e.g. `get all`, the feed showed both "You take X" (actor feedback) and "player_name takes X" (room narration meant for other players) to the same actor. Removed the loop in `POST /command` that appended `ctx.room_messages` to the actor's own feed response; `broadcast_command_effects()` already delivers that narration to _other_ room occupants with the actor excluded. New e2e regression test (`tests/e2e/test_ui_refresh_on_item_actions.py`).

## [0.11.2] - 2026-07-04

### Changed

- **Testing: parallel focused pytest runs** — Added `pytest-xdist` to the dev tooling and updated `make test` / `make test-cov` to run the default focused suite with `-n auto --dist=loadfile`, so local and CI coverage-gated test runs use available CPU cores while keeping each test file's cases on the same worker. The browser e2e and live simulation harness targets remain explicit serial runs. Make targets now invoke Python tools through `python -m ...` by default, so local shells use the selected venv instead of a stale PATH executable.

## [0.11.1] - 2026-07-04

### Added

- **Sprint 29.2: Transit vehicle state machine & commands** — `services/transit.py`'s `TransitService` builds a Sprint 21 `RouteSpec`/`RouteHooks` per `TransitLine` at app lifespan (`load_lines()`) and starts it, entirely on the existing route runner — no new state machine or timing mechanism. `may_depart` grounds weather-sensitive lines when `WorldClock.weather` is in the line's `blocking_weather`; `on_depart`/`on_arrive` narrate to both the station room and the vehicle room. New `board [line]` (validates stop position + ticket, consumes it if configured, moves the player into the vehicle room), `disembark`/`leave` (moves the player back out at the current stop), and `schedule [line]`/`timetable` (stop order + live status) commands (`commands/transit.py`). `register_all_commands` gained an optional `transit=` keyword argument — `TransitService` needs the game engine and `ConnectionManager` at construction (like `MeterService`/`MobileRouteService`), so it can't live in the no-argument `ServiceContainer`; every existing call site is unaffected by the addition. 10 new unit tests (`test_transit.py`).

## [0.11.0] - 2026-07-04

### Added

- **Sprint 29.1: Transit data model** — New `TransitLine`/`TransitStop` tables (`models/transit.py`) for ferry/rail/balloon/caravan lines — line _configuration_ only, per `docs/transit_systems.md` §4: there is deliberately no `TransitVehicleState` table, since runtime vehicle position reuses Sprint 21's `MobileRouteState` (`route_id=f"transit:{line_id}"`), wired up in Sprint 29.2. World YAML gains a top-level `transit.lines` section (mode, service type, vehicle room, ticket item, reverse/loop, weather sensitivity, ordered stops) plus content validators: every stop's `room_id` and a line's `ticket_item_id` must resolve, `vehicle_room_id` must exist and have no static exits (board/disembark only), stop sequences must be contiguous from 0, an `express` line needs at least 2 boarding stops, and `blocking_weather` values must be states `clock/weather.py`'s `WEATHER_TABLE` actually produces. 12 new unit tests (import/export/reimport round-trip in `test_world_loader.py` + 5 validator-rejection tests).

## [0.10.3] - 2026-07-04

### Summary

**Sprint 28.4 — Player-to-player trade.** Completes Sprint 28 (Trading & economy):
a safe `offer`/`accept`/`decline` handshake atop the Sprint 20 ledger's atomic
exchange. 676 focused tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 28.4: Player-to-player trade** — Finished two pre-existing half-done seams instead of adding parallel ones: the `TradeOffer` table (present since early on, never wired to any code) gained coin fields and `[stack_id, quantity]` pledge lists per side; the unused `GameEvent.TRADE_COMPLETED` now actually fires. `offer <item|N coins> to <player>` (`services/trade.py`) records a pledge onto an open trade between the two players (creating one if needed) and moves nothing; either side can keep pledging more. `accept` composes exactly one `LedgerService.execute_exchange` call with every pledge (both directions, coins and stacks) as legs — that call's own leg validation _is_ the escrow revalidation the design called for: if a pledged stack or coin balance is gone since it was offered, the whole exchange raises and nothing moves. Room-presence and `tradeable`/`bound` are re-checked at accept time too, not just at offer time, and offers expire after 5 minutes. New `offer`/`accept`/`decline` commands (`commands/trade.py`). Added `"offer"` to the parser's `OBJECT_VERBS` (`game/grammar.py`) so `offer X to Y` splits into object/recipient roles the same way `give X to Y` already does. 7 new unit tests (`test_trade.py`).

## [0.10.2] - 2026-07-04

### Added

- **Sprint 28.3: Banks** — New `Bank` model (an NPC marker, like `Shop`) and `BankAccount` (identity/ownership only — the balance lives on the ledger as `CoinBalance("bank_account", account.id)`, a new holder type registered in `game/bank_holders.py`). `services/bank.py`'s `BankService` backs three new commands (`commands/bank.py`): `deposit <amount>`/`withdraw <amount>` (each one `LedgerService.execute_exchange` leg, gated on standing in a bank branch's room) and `balance` (shows carried + banked, works anywhere — you always know your own money). `BankRepo.get_or_create_account()` lazily creates the single per-player account on first use; **one logical account, many branches** — deposit in one room's branch, withdraw in another's, since banking code only ever keys off the account id, never the room. Mira's inn now also runs a strongbox (`world_content/world.yaml`). Banked money is immune to death/robbery by construction: that code only ever touches the `("player", id)` holder, never `("bank_account", ...)`. 8 new unit tests (`test_bank.py`) + a world-loader round-trip test.

## [0.10.1] - 2026-07-04

### Added

- **Sprint 28.2: Regional pricing & restocking** — New `RegionPricing` table (world YAML top-level `economy.regions`) contributes an area-wide `region_mult` and a per-item `bias` multiplier on top of a shop's own `region_mult` — the same good costs different amounts in different places, and specific goods can be cheap/dear per area regardless of the area default. `EconomyService._demand_mult()` reads a `ShopStock` row's current quantity against its `restock_to` target: depleted stock costs more, flooded stock (e.g. from players selling heavily into one shop) costs less, bounded to `[0.5, 1.5]` so prices never run away. New `services/restock.py`'s `RestockService` (scheduler-driven, same engine-holding shape as `LightFuelService`) counts `TIME_ADVANCED` ticks per stock row and jumps `quantity` to `restock_to` once `restock_every_ticks` elapses, independent of anyone visiting the shop. `world_content/world.yaml` now prices goods higher in the `wilderness`/`cave` areas than in `town`. 12 new unit tests (`test_economy.py`) + a world-loader region import/export round-trip test + a validator-rejection test.

## [0.10.0] - 2026-07-04

### Summary

**Sprint 28.1 — Currency & vendor shops.** NPCs can now run a shop: `list`/`buy`/`sell`/
`appraise` against runtime-derived prices, backed by the Sprint 20 ledger's atomic
exchange. 650 focused tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 28.1: Currency & vendor shops** — New `Shop`/`ShopStock` tables (`models/economy.py`) attached to an NPC via a world YAML `shop:` block; a shop's cash is `CoinBalance("shop", shop.id)` (new `"shop"` ledger/item holder type, `game/economy_holders.py`), seeded once at world import via `LedgerService.credit` (idempotent — re-importing the same world file does not double-credit). New `Item.value`/`Item.category` fields. `services/economy.py`'s `EconomyService` derives `buy_price = value × quality_mult × region_mult × (1 - barter_discount) × (1 - rep_discount)` and `sell_price = buy_price × sell_ratio` at runtime, never stored — `bartering` skill and vendor reputation each shave a capped discount off the price. Every coin/item movement is one `LedgerService.execute_exchange` call (Sprint 20); sold items are `destroy()`ed rather than held as physical shop stock, since `ShopStock.quantity` is listing state only, materialized as a real `ItemStack` only on purchase. New commands (`commands/economy.py`): `list`/`shop` (stock + prices), `buy <item> [qty]`, `sell <item> [qty]` (gated on `tradeable`, not `bound`, and the shop's `buys_categories`), `appraise <item>` (not skill-gated in this cut — shows the derived value outright). Mira the innkeeper runs a working shop (`world_content/world.yaml`) selling mugs/candles/dried herbs. 15 new unit tests (`test_economy.py`) + a world-loader import/export/reimport round-trip test.

## [0.9.1] - 2026-07-04

### Added

- **Sprint 27.2: Sleep depth** — New `Room.safe_rest` field (YAML `safe_rest: true`, marked on the Wandering Crow Inn in `world_content/world.yaml`): `sleep` there always succeeds — full stamina restore, 8-hour clock-advance (`clock/world_clock.py`'s `apply_clock_fields`, plus a weather reroll via `apply_daily_weather` if the day rolls over), and a dream. Everywhere else, `sleep` is a `survival` `skill_check` gamble — harder in cold weather (`clock/weather.py`'s new `COLD_WEATHERS`: snow/blizzard/fog) unless the player has enough resolved warmth; failure interrupts the sleep into a shorter (3h), partial, dreamless rest. New `game/warmth.py` (`resolve_warmth()`, composing the Tier 1 modifier resolver) and a new `warmth_bonus` item effect descriptor (`game/item_effects.py`, `tools/validators.py`) give worn clothing a non-combat purpose — a cloak matters in a blizzard. Dreams reference a random discovered `lore:`-flagged fact (Sprint 25.3) when the player has one, otherwise a generic flavor line. 5 new unit tests (13 total in `test_fatigue.py`).

## [0.9.0] - 2026-07-04

### Summary

**Sprint 27.1 — Fatigue.** Light survival texture: traveling drains stamina (more when
encumbered), and running low saps skill checks. `rest`/`camp`/`sleep` commands restore it.

### Added

- **Sprint 27.1: Fatigue** — `game/fatigue_source.py` registers a "fatigue" `MeterDef` (remaining stamina, base scales with `PlayerStats.fortitude`) and a `FatigueModifierSource` applying a flat `mult` penalty to every registered skill (`game/skills.py`) once stamina drops below 50% (weary) or 20% (exhausted) of maximum — the "low fatigue penalizes skill checks" promise in `docs/wishlist.md`. `services/fatigue.py`'s `FatigueService` drains stamina on every `PLAYER_MOVED` event, scaled by the Sprint 23.2 encumbrance band (unburdened/burdened/overloaded), and backs three new commands (`commands/condition.py`): `rest` (quick, small restore), `camp` (slower, larger restore), and `sleep` (restores to full — clock-advance, safe/unsafe risk, and dream flavor are Sprint 27.2's job). Built on top of the [0.8.2](#082---2026-07-04) event-flush fix below (fatigue drain relies on the same post-command `PLAYER_MOVED` event handler pattern as quest progression). 8 new unit tests.

## [0.8.2] - 2026-07-04

### Fixed

- **Post-command event handler mutations were silently discarded** — `CommandEngine._execute_parsed` (`game/engine.py`) called `ctx.commit_state_changes()` _before_ `ctx.flush_events()`, so any state mutated by a queued-event handler (notably `QuestService.check_progression`, which advances quest stages and sets completion flags on `PLAYER_MOVED`/`ITEM_TAKEN`/`ITEM_DROPPED`) was applied to the in-memory session but never committed — lost as soon as that request's session closed. Existing unit tests never caught this because they assert against the same still-open session. Found while designing Sprint 27's fatigue drain-on-move (which needed the same event-driven pattern to actually persist). Fixed by flushing events before the single commit; `EventBus.emit()` already isolates handler exceptions into `HandlerResult.error` rather than raising, so this can't turn a failed handler into an unwanted rollback of the command's own effects. New regression test (`test_websocket_movement_persists_quest_progression` in `tests/integration/test_main.py`) seeds a room-visited-gated quest stage and asserts the stage advance and completion flag survive a fresh session read after a real `go east` over the websocket; confirmed it fails without the fix and passes with it.

## [0.8.1] - 2026-07-04

### Fixed

- **CI: basedpyright venv configuration** — Removed hardcoded `.venv` path that caused CI to fail with "venv .venv subdirectory not found"; basedpyright now auto-detects the Python interpreter, working in both local dev and CI environments.
- **CI: e2e test dependency** — Added `pytest` to the `e2e` optional dependency group so browser tests can run without manually installing dev extras.

## [0.8.0] - 2026-07-04

### Summary

**Sprint 26 Complete — Map & Mobile UI.** UI polish serving exploration: a full-screen, pan/zoomable map modal integrated with cartography's reveal payoff, and a responsive mobile tab layout. Verified in a real headless-Chromium browser (screenshots of desktop, the modal, and all three mobile tabs) in addition to 3 new e2e tests and 4 new unit tests. 539 focused tests + 6 e2e + 5 simulation tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 26.1: Full-screen map modal** — An expand button (⛶) on the sidebar minimap opens a modal (`partials/map_modal.html`) with a larger SVG map (up to 60 rooms vs. the sidebar's 7), drag-to-pan and scroll/button-to-zoom (vanilla Alpine.js state, no new JS dependency). `build_map_data()` (`web/rendering.py`) gained `full`/`cartography_level` parameters: once a player's `cartography` skill (Sprint 24.2) reaches `CARTOGRAPHY_REVEAL_THRESHOLD` (20), rooms one non-hidden exit away from anywhere visited are plotted too — dimmer, labeled "Unexplored" — the cartography payoff Sprint 25.3 deferred here. Hidden exits are never revealed by cartography (that stays `search`'s job, Sprint 25.1).
- **Sprint 26.2: Responsive mobile tab layout** — Below the `lg` breakpoint, the three-column desktop layout (Room/Inventory/Map, Feed, Players/Quests) collapses to one column at a time, switched via a bottom tab bar (`Room`/`Feed`/`Players`); `lg:!flex` keeps the desktop three-column view untouched above that breakpoint (Tailwind's important-modifier overriding the mobile-only `hidden` class Alpine toggles).
- Added `[x-cloak] { display: none !important; }` to `custom.css` (avoids a flash of the map modal before Alpine initializes).

## [0.7.0] - 2026-07-04

### Summary

**Sprint 25 Complete — Exploration Depth.** Discovery as a first-class reward: `search` reveals hidden exits gated on perception, terrain types gate/flavor movement, and a `journal` command surfaces what a player has discovered. Fixed two real pre-existing bugs in movement (hidden exits always blocked; `condition_flags` never enforced) found while building this. 535 focused tests (12 new) + 5 simulation tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 25.1: Search + hidden-exit discovery** — New `search` command (`services/exploration.py`) runs a perception `skill_check()` (Sprint 17-18's existing resolution helper, base skill from Sprint 24's `SkillService`, modifiers from every registered source — equipment/traits/effects); on success, reveals any of the room's hidden exits the player hasn't found yet. Discovery is per-player (`game/exploration.py`'s `is_exit_discovered`/`mark_exit_discovered`, stored in the existing `Player.flags` dict — already save/load-snapshotted, no new persistence path needed) — `look` now lists a hidden exit once _that player_ has discovered it, not room-globally. Finding something awards a flat XP tick (`PlayerStats.xp`) and rolls a `perception` use (Sprint 24.2's use-based improvement) regardless of outcome.
- **Sprint 25.2: Terrain** — New `Room.terrain: str` field (`game/terrain.py`'s `TerrainRegistry`, data-driven default set: normal/road/forest/mountain/swamp/water) with an optional `required_skill`/`required_skill_min` gate enforced in `MovementService.move()` and a `description_suffix` layered onto `look`. Content validator (`check_room_terrain`) flags unknown terrain names.
- **Sprint 25.3: Journal** — New `journal` command (`services/journal.py`) surfaces places visited (`Player.visited_rooms`, already tracked), people met (new `Player.met_npcs`, set on first `talk`), lore learned (any player flag an author prefixes `lore:` via existing dialogue `set_flags` side effects — no new authoring mechanism), and active quest titles (`QuestRepo.active_progress`). Cartography's map-reveal payoff is Sprint 26's job (the full-screen map modal task explicitly owns "integrated with cartography reveal") — this sprint only ships the skill identity and the journal's read-only view.
- New `traits`/`skills`/`reputation`-style visibility precedent extended: `journal` and `search` give players concrete, testable payoff for the trait/skill/reputation plumbing Sprint 24 shipped.

### Fixed

- **`MovementService.move()` always blocked hidden exits, contradicting the documented behavior** (`world_building.md`: "Exits can be hidden from descriptions but still usable... the player must try the command directly") — a hidden exit could never be traversed even by guessing the exact direction. Fixed: hidden only affects whether `look` lists the exit, never whether `go <direction>` works.
- **`Exit.condition_flags` was stored and round-tripped through YAML import/export but never enforced anywhere** — an exit authored with `condition_flags: ["blessed_by_priest"]` was, in practice, unconditional. Fixed: `move()` now blocks the exit unless every listed flag is set on the player.

## [0.6.0] - 2026-07-04

### Summary

**Sprint 24 Complete — Traits & Skills.** Character identity that gates exploration and social play: an innate trait source (background/earned traits, distinct from equipment/active-effect traits), use-based skill improvement, and NPC/faction reputation gating dialogue and commands. 523 focused tests (18 new) passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 24.1: Trait registry (innate/background/earned)** — `game/standard_traits.py` registers `InnateTraitSource` (reads `PlayerStats.traits`, populated by `services/traits.py`'s `TraitService.grant()`/`revoke()`) alongside 5 illustrative standard traits (2 boons: `keen_eyed`, `silver_tongued`, `sure_footed`; 2 banes: `clumsy`, `frail`) with real modifier effects — completing the three-source picture alongside Sprint 19's active-effect source and Sprint 23's equipment source. New `traits` command lists a player's currently active traits (from every source) with descriptions.
- **Sprint 24.2: Use-based skill improvement** — `game/skills.py`'s `SkillRegistry` defines skill _identity_ (perception, lockpicking, bartering, cartography, survival, persuasion) on top of Sprint 17-18's `skill_check()`, which already defined how a check resolves. `services/skills.py`'s `SkillService.record_use()` is the "learn by doing" mechanic: each use has a 10% chance to raise the skill's level (stored in the existing `PlayerStats.skills` dict) by 1, capped at 100. New `skills` command lists all standard skills and the player's current level in each. No command calls `record_use()` yet — Sprint 25's `search` (perception) is the first real consumer, same "ships the primitive, next feature wires it in" precedent as `skill_check()` itself.
- **Sprint 24.3: Reputation/standing** — New `models/reputation.py`'s `Reputation` table (one row per player × target_type × target_id, "npc" or "faction"). `services/reputation.py`'s `ReputationService` clamps standing to [-100, 100]. `game/reputation_conditions.py` registers a `reputation_at_least:<type>:<id>:<min>` command condition and a `min_reputation` dialogue condition (`{"target_type", "target_id", "min"}`) on the existing Sprint 10 pluggable-condition registries — no core edits, gating dialogue/prices/quests behind standing exactly as the roadmap specifies. New `reputation`/`rep` command lists a player's standings.
- New `services/character_info.py`'s `CharacterInfoService` backs the `traits`/`skills`/`reputation` commands (`commands/character.py`), wired into `ServiceContainer` alongside the other gameplay services.

## [0.5.0] - 2026-07-04

### Summary

**Sprint 23 Complete — Inventory & Equipment.** Wear/wield slots, encumbrance, containers, and light/darkness gating, all built only on Tier 1 primitives per `docs/inventory_equipment.md`. 505 focused tests (69 new) + 5 simulation tests passing; basedpyright 0 errors; ruff clean.

### Added

- **Sprint 23.1: Equipment** — Equipped-ness is a location, not a column (supersedes the roadmap's old `Player.equipment` draft): wearing a helm is `ItemLocationService.move()` to `Location("player", id, slot="head")`. `game/equipment_slots.py` ships the default slot set (14 slots: worn + wielded) as data, with a generic `"finger"` item-slot that the `wear` command resolves to whichever of `finger_l`/`finger_r` is free. `game/equipment_validators.py` registers a `player`-holder move validator (slot must be known, item must fit and match wearable/wieldable, slot must be empty). `InventoryService` gains `wear_item`/`remove_item`/`wield_item`/`unwield_item`/`list_equipment`, wired as `wear`/`remove`/`wield`/`unwield`/`equipment`/`eq` commands — extending the existing service rather than forking it. New `ITEM_EQUIPPED`/`ITEM_UNEQUIPPED` events. `game/item_rules.py` adds the bound-item policy veto (`Item.bound` items can't be `drop`/`give`) as a fail-closed `RuleEngine` rule at the command layer, not inside the primitive — caught a real ordering bug along the way: `ctx.parsed_command` isn't set until _after_ `rules.check()` runs (game/engine.py's lifecycle), so the rule reads the noun from the audit payload the engine already built instead.
- **Sprint 23.2: Encumbrance & equipment-derived modifiers** — `game/item_effects.py` compiles `Item.effects` descriptors into Tier 1 `Modifier`s (`stat_bonus`/`skill_bonus`/`carry_bonus`) or trait grants (`grant_trait`); `game/equipment_source.py` registers an `EquipmentModifierSource` and `EquipmentTraitSource` that walk a player's equipped stacks and feed Sprint 18's modifier resolver and Sprint 19's trait registry — equip/unequip changes what resolves immediately, nothing is cached. `game/encumbrance.py`: `carry_base(strength)`, `resolve_carry_capacity()` (resolved, never stored — a worn backpack's `carry_bonus` extends it live), `total_carried_weight()`, and `encumbrance_band()` (unburdened/burdened/overloaded at capacity/1.5×capacity). "Cannot pick up more" is enforced at the command layer (`InventoryService._would_overload`) rather than as a generic holder-registry validator — the validator signature has no visibility into the source location, so a naive implementation would double-count weight on `wear`/`remove` (same-owner slot changes, not new weight entering play); checking at the specific take/give-receipt call sites where weight genuinely increases avoids that bug.
- **Sprint 23.3: Containers & light/darkness** — `game/container_validators.py` registers a `container`-holder move validator: closed containers reject moves, moves exceeding declared `capacity` are rejected, and nesting past `MAX_NESTING_DEPTH=3` is rejected. `put <item> in <container>` / `take <item> from <container>` added to `InventoryService`, riding the parser's existing (previously unused) `ContainerRoles`/preposition-to-role machinery (`in`→destination, `from`→source). `light`/`extinguish` commands toggle the `lit` component; `services/light_fuel.py`'s `LightFuelService` is a `MeterService`-shaped scheduler sweep that drains one durability point per world-clock tick from every lit instance, auto-extinguishing at zero — creating the "demand for oil/torches" resource loop the design calls for. The `requires_light` command condition now also passes when the player has an _equipped_ item with `light > 0` and `lit.lit == true` (previously it only ever checked `Room.light_level`).
- **Bug fix (found while building 23.3): container-cycle detection compared item _type_, not instance** — `ItemLocationService._check_container_cycle()` (Sprint 16) compared the moved item's `item_id` against the destination container's `item_id`, so nesting one chest inside a _different_ chest instance of the same item definition falsely raised "cannot place a container inside itself" — any two same-type containers could never nest. Fixed to walk the destination's actual ancestry by `ItemInstance.id`, correctly rejecting only genuine cycles (including transitive ones: A inside B inside A), which the original single-hop check also missed entirely. 2 new regression tests in `test_item_location_service.py`.
- **Bug fix (found while testing 23.3): equipped items were invisible to open/close/light/extinguish** — `InventoryService._find_carried_or_visible_stacks()` used `ItemRepo.player_stacks_matching()`, which only returns _loose_ (`slot=None`) stacks; a wielded lantern could never be found to light it. Fixed to search all of a player's stacks regardless of slot.

## [0.4.1] - 2026-07-04

### Added

- **Sprint 22.2: Standard Item Components** — Completes Sprint 22 (the first commit only shipped 22.1). Registers the four standard components from `docs/inventory_equipment.md` §7 on Sprint 16's `ComponentRegistry`: `durability` (applies when `max_durability` is set; state `{"current": N}`), `openable` (applies to containers; state `{"open": bool}`), `lit` (applies when `light > 0`; state `{"lit": bool}`), `container` (applies when `capacity` is set; state `{}`, contents are stacks not state). `game/standard_components.py` self-registers at import time (mirrors `game/traits.py`'s pattern); imported for side effects from `main.py`'s module scope. New `services/item_components.py` (`get_component_state`/`set_component_state`) centralizes instance-state mutation — JSON columns need a fresh dict object per write for SQLAlchemy to notice the change, so every setter reassigns `instance.state` rather than mutating in place. `open`/`close` commands added to `InventoryService`/`commands/inventory.py`, resolving carried-or-visible stacks with a registered `openable` component state. 6 new tests (component initial state on spawn, open/close round trip, already-open/already-closed messaging, non-openable item rejection). 354 focused tests passing; basedpyright 0 errors; ruff clean.

## [0.4.0] - 2026-07-04

### Summary

**Sprint 22 Complete — Standard Item Definition Fields (Tier 2 Layer A, first feature-band sprint).** Item definition expanded with equipment, encumbrance, light, durability, and effect-descriptor fields. `models/world.py`'s `Item` model gains 8 new optional/nullable fields: `slot` (equipment slot key), `wearable` (worn vs. wielded), `weight` (drives encumbrance), `quality` (common/fine/superior/rare/legendary, affects trade), `max_durability` (None = indestructible, else tracked per-instance), `light` (light level when equipped & lit), `capacity` (makes item a container), `effects` (effect descriptor list, registry-driven). `world/validator.py`'s `ItemData` updated to match, with corresponding loader updates in `world/loader.py` (import/export). New `check_item_definition_fields()` validator in `tools/validators.py` enforces: known slot names, wearable items must have slots, known qualities, containers must be takeable, non-negative weight/light/durability, known effect descriptor types, known stat names in effect descriptors. 9 new validator unit tests, all passing. Tier 1 foundation consumed: Tier 2 now starts on this layer. 348 focused tests + 3 e2e + 5 simulation tests passing; basedpyright 0 errors on `src/`; ruff clean. See `docs/inventory_equipment.md` §3–10 for the binding design. Next: Sprint 23 (equipment & encumbrance).

### Added

- **Sprint 22: Standard Item Definition Fields** — Tier 2 Layer A: item definition expansion for equipment/encumbrance/light mechanics. `Item` model gains 8 fields: `slot`, `wearable`, `weight`, `quality`, `max_durability`, `light`, `capacity`, `effects`. Content validators added for all fields (unknown slots, quality, effect types; wearable without slot; non-takeable containers; negative numeric values; unknown stats in effect descriptors). YAML loader updated to round-trip all fields on import/export. No new commands or services yet — just data modeling and validation. Sprints 23–35 build features on top of this foundation.

## [0.3.1] - 2026-07-04

### Changed

- `AGENTS.md`: codified strict semver discipline going forward — bump the version and update `CHANGELOG.md` in the same commit as every change from here on (minor bump per completed sprint, patch bump per fix/docs-only change), rather than batching version bumps only when explicitly requested.

## [0.3.0] - 2026-07-04

### Summary

**Sprints 20–21 Complete — Ledger & scheduled mobile entity (Tier 1 engine primitives), closing out the engine-core band.** `models/ledger.py`'s `CoinBalance` and `services/ledger.py`'s `LedgerService` add a coin balance on any registered holder (player/bank/corpse/shop; no `Player.coins` column) plus one atomic multi-leg `execute_exchange()` for coins and items together — validates every leg first, then applies every leg's mutations, so a failing leg leaves nothing partially applied. `models/mobile.py`'s `MobileRouteState` and `services/mobile_route.py`'s `MobileRouteService` add the generic scheduled route runner (the "moving room" primitive transit will ride on) — a waypoint state machine with ping-pong reversal or circular looping, position interpolation for the minimap, and pluggable `RouteHooks` (`may_depart`/`on_depart`/`on_arrive`/`on_tick`); reuses the existing `SchedulerService` for all timing, no second timing mechanism. 29 new tests, all green first run — no bugs caught, unlike Sprints 16/19. 538 focused tests + 3 e2e + 5 simulation tests passing; basedpyright 0 errors on `src/`; ruff clean. See `docs/engine_core.md` §3.7–3.8 for the binding specs. Tier 1 engine-core band (Sprints 16–21) is now complete; Tier 2 feature work starts at Sprint 22.

**Sprint 19 Complete — Meters, timed effects & traits (Tier 1 engine primitives).** `models/meters.py`'s `Meter` (one named-bounded-resource primitive instead of one column per resource) and `ActiveEffect` (clock-driven buffs/debuffs); `services/meters.py`'s `MeterService` and `services/effects.py`'s `EffectService` (both stateless-per-call for command-path get/adjust/apply/remove, engine-holding for their scheduler-driven regen/expiry sweeps); `game/traits.py`'s trait registry, shipping the one Tier 1 `TraitSource` (active effects' `grants_traits`) and registering both a trait and an active-effect `ModifierSource` with Sprint 18's resolver. The HP migration proves the primitive: `PlayerStats.current_hp`/`NPC.current_hp` are deleted outright, replaced by `Meter(entity, "hp")`, with `max_hp` staying as the definitional base. 25 new tests caught two real bugs in the scheduler sweeps (reading ORM attributes after `session.commit()` expired them). 509 focused tests + 3 e2e + 5 simulation tests passing; basedpyright 0 errors on `src/`; ruff clean. See `docs/engine_core.md` §3.3–3.4 for the binding specs. Next: Sprint 20 (ledger + atomic transfer).

**Sprints 17–18 Complete — Determinism: seedable RNG, modifier resolution & skill-check (Tier 1 engine primitives).** `game/rng.py`'s `GameRng` is now the one sanctioned randomness source in `src/lorecraft` (deterministic when seeded; bare `import random` is ruff-banned everywhere else in `src/`); one app-wide instance threads through `GameContext`, `SchedulerEventContext`, and `clock/weather.py`. `game/modifiers.py`'s `resolve()` is the one runtime resolver for stacked bonuses (fixed add→mult→clamp bucket order), with a pluggable `ModifierSource`/`ModifierRegistry` for collection. `game/checks.py`'s `skill_check()` composes both into the one roll-under-d100 helper every future perception/lockpicking/bartering/combat-to-hit check will share. 21 new unit tests; 484 focused tests + 3 e2e + 5 simulation tests passing (including the audit-regression diff and the concurrent-take-no-duplication guarantee); basedpyright 0 errors on `src/`; ruff clean. See `docs/engine_core.md` §3.5–3.6 for the binding specs.

**Sprint 16 Complete — Item location/ownership & instance state (Tier 1 engine primitive).** Unified `ItemStack`/`ItemInstance` model (`models/items.py`) replaces `Player.inventory: list[str]` and the `RoomItem` table outright — one atomic move primitive (`ItemLocationService.move()`, plus `spawn()`/`destroy()`/`materialize()`) for every place an item changes hands (take/drop/give, world import, save/load, changeset item-deletion cleanup). A pluggable `ComponentRegistry` (`game/components.py`) and `HolderRegistry` (`game/holders.py`, built-ins: player/room/container) round out the primitive; Tier 1 registers no components or extra holder types, leaving those to Tier 2. Full blast-radius migration across services/inventory.py, repos/item_repo.py, game/context.py, game/command_conditions.py, services/movement.py, services/quest.py, npc/side_effects.py, services/save.py (v1-save-compatible load), world/loader.py, world/versioning.py, tools/world_cli.py, scripts/import_world.py, admin/routers/players.py, main.py, web/session.py, web/frontend.py. 454 focused tests (23 new invariant tests for the move primitive) + 3 e2e + 5 simulation tests passing (including the audit-regression diff and the concurrent-take-no-duplication guarantee); basedpyright 0 errors on `src/`; ruff clean. See `docs/engine_core.md` §3.1–3.2 for the binding spec.

**Sprints 4–15 Complete — Player authentication shipped, foundation gate is green.** Player authentication (password login, JWT access/refresh tokens, single-use WebSocket tickets, retired the `?player_id=` trust-by-default, OAuth extensibility stub), module decomposition (web/parser/admin split into 9 focused modules), service consistency (ServiceContainer, register(bus) convention), extensibility seams (pluggable registries for dialogue side effects, dialogue/command conditions, feature-registration pattern documented), tooling infrastructure (repo-tracked issues/news, world content CLI, analytics query API, content linting), a browser E2E harness (Playwright against a live server), a simulation harness (real WebSocket clients against a live server, multi-player scenarios, audit-log regression diffing), observability + CI quality gates (structured logging with correlation IDs, command/event timing instrumentation, required GitHub Actions checks), a unified command lifecycle (rollback-on-error, shared `/ws`/`POST /command` room-broadcast step, unified `GameContext` construction), and core UX completion (world clock/weather WS push to all connected players, multi-player live lists refreshed on room-leave). 431 focused tests + 3 E2E tests + 5 simulation tests passing; basedpyright 0 errors on `src/`; ruff clean. All 8 foundation exit criteria now met — Sprints 16+ (engine-first Tier 1 primitives, then item/equipment/trading/exploration/combat/PvP; see `docs/engine_core.md` and `docs/roadmap.md`) are unblocked.

### Added

- **Sprint 21: Scheduled Mobile Entity ("moving room")** — The generic route-runner primitive transit vehicles (and, latently, wandering NPCs/patrols) ride on (`docs/engine_core.md` §3.8). `models/mobile.py`'s `MobileRouteState` (SQLModel table: `route_id` PK, `status` — `at_stop`/`in_transit`/`halted` — `current_index`/`next_index`, `direction`, `depart_epoch`/`arrive_epoch`) is the only persisted piece; `Waypoint` (`position_id`, `x`/`y`, `dwell_ticks`, `travel_ticks`) and `RouteSpec` (`route_id`, `waypoints`, `reverses`, `loop`, `tick_pushes`) in `services/mobile_route.py` are pure in-memory dataclasses the owning feature supplies at lifespan — Tier 1 never persists a spec. `MobileRouteService` is engine-holding schedulable, exactly the `SchedulerService` shape: `register(bus)` listens for `SCHEDULED_JOB_DUE` with `job_type="mobile_route"` (actions `depart`/`arrive`/`tick`, reusing `SchedulerService.schedule()` for all timing — no second timing mechanism); `add_route()` registers a spec/hooks pair and ensures a runtime state row exists without ever resetting one that's already there (a server restart resumes, it doesn't re-initialize); `start()`/`halt()`/`resume()` for manual control; pure `progress()`/`position()` for minimap interpolation. State machine: `at_stop` --(dwell elapses, `RouteHooks.may_depart` → `None`)--> `in_transit` --(arrive job)--> `at_stop` at the next waypoint, with index/direction advancing via reverse-at-ends (`reverses=True`, the default — ping-pongs regardless of `loop`) or loop-wraparound (`reverses=False, loop=True` — circular). A `may_depart` halt reason (e.g. weather) parks the route and reschedules a re-check after `dwell_ticks`; `resume()` forces an immediate re-check instead of waiting. `on_tick` fires `tick_pushes` times per segment with interpolated progress — throttled by design, never per world-tick; Tier 1 pushes nothing to clients itself, leaving the Tier 2 transit module to turn it into a `transit_update` WS message. A route whose spec/hooks disappear on restart (owning feature didn't re-`add_route()` before a pending job fires) halts instead of crashing. `AppState` gains a `mobile_routes: MobileRouteService` field, wired into `main.py`'s lifespan alongside the scheduler/meter/effect services. 15 new tests (full ping-pong round trip, circular looping, halt/resume, tick-push interpolation, spec-disappeared-on-restart) — all green first run.

- **Sprint 20: Ledger & Atomic Transfer** — A coin balance on any holder plus one atomic multi-party transfer for coins and items together (`docs/engine_core.md` §3.7). `models/ledger.py`'s `CoinBalance` (`holder_type`/`holder_id`/`balance`, one row per holder, using the same `HolderRegistry` as `ItemStack` — no `Player.coins` column). `services/ledger.py`'s `LedgerService` is stateless per-call (every method takes the caller's `Session` explicitly, matching `ItemLocationService`'s command-path shape — no engine/rng held, since there's no scheduler sweep for this primitive): `balance_of()`; `credit()` (the _only_ way coins enter play — world import, admin, loot); `execute_exchange(legs: Sequence[ExchangeLeg])` — each leg is a `give_from`/`give_to` `Location` pair plus `coins`/`stacks` to move. Validates every leg first (sufficient coin balance, destination holder exists, every stack is actually at its declared `give_from` with sufficient quantity) and only if _every_ leg passes does it apply _any_ mutation — a P2P trade's `accept()` becomes one `execute_exchange()` call with both directions as legs, atomically; a failing second leg leaves the first leg's mutation entirely un-applied. Reuses Sprint 16's `ItemLocationService.move()` for the stack legs. `GameContext` gains a required `ledger` field; `build_game_context()` constructs a fresh `LedgerService()` with no new required kwarg (no engine/rng dependency, unlike Sprint 19's `meters`/`effects` — smaller blast radius). 14 new tests, including a two-way trade-shaped exchange verifying coin conservation across both directions and an atomicity test verifying a failing leg applies nothing from any leg — all green first run.

- **Sprint 19: Meters, Timed Effects & Traits** — Two more Tier 1 engine-core primitives (`docs/engine_core.md` §3.3–3.4). `models/meters.py`'s `Meter` (`entity_type`/`entity_id`/`key`/`current`/`maximum`, one row per named resource — hp, fatigue, hunger, mana, ... — instead of one column each) and `ActiveEffect` (clock-driven buff/debuff, distinct from equipment effects which last only while equipped and from traits which are semi-permanent). `game/meters.py`'s `MeterDef`/`MeterRegistry` (key, `base_maximum` callback, `regen_per_tick`, `start_full`) and `services/meters.py`'s `MeterService`: `get()` creates a meter lazily from its registered def; `adjust()`/`set_current()`/`recompute_maximum()` are stateless per-call, taking the caller's `Session` (command-path shape, same as `ItemLocationService`); `_on_time_advanced()` is the regen sweep — its own short-lived session, ticking every already-created meter with a registered `regen_per_tick`, emitting `METER_DEPLETED`/`METER_RECOVERED` directly since no `GameContext` exists in scheduler-driven work (command-path `adjust()` stays pure per Sprint 16's "primitives emit nothing" convention — callers decide whether to queue a domain event from the returned `MeterChange.depleted`/`.recovered` flags). `game/effects.py`'s `EffectDef`/`EffectRegistry` and `services/effects.py`'s `EffectService`: `apply()`/`remove()`/`active_for()` stateless per-call; `_on_time_advanced()` sweeps expired `ActiveEffect` rows and emits `EFFECT_EXPIRED`. `game/traits.py`'s `TraitDef`/`TraitSource`/`TraitRegistry`: Tier 1 ships exactly one `TraitSource` (`ActiveEffectTraitSource`, sourcing from each active effect's `grants_traits`) and registers both an `ActiveEffectModifierSource` and a `TraitModifierSource` with Sprint 18's `ModifierRegistry` — fulfilling that sprint's "Tier 1 registers the active-effect and trait sources" promise. New `PlayerStats.traits: list[str]` column (empty by default; Tier 2 populates it). The HP migration is the proof-of-primitive: `PlayerStats.current_hp` and `NPC.current_hp` are **deleted outright** (not deprecated) — `max_hp` stays as the definitional base, fed to the "hp" `MeterDef`'s `base_maximum`, registered as bootstrap in `main.py`'s lifespan. Full blast radius: `world/loader.py` (NPC seeding no longer sets `current_hp` — `MeterService.get()` creates it lazily), `admin/routers/world.py` (NPC listing does a read-only `MeterRepo` lookup rather than triggering lazy-creation from a GET, falling back to `max_hp` for an as-yet-uncreated meter), `services/save.py` (`stats_snapshot` drops `current_hp`, gains a `"meters": {"hp": ...}` dict; loading converts both the new shape and the old v1 flat `"current_hp"` key). `GameContext` gains required `session`/`meters`/`effects` fields; `build_game_context()` gains required `meters`/`effects` keywords — both real entry points and every test fixture updated (same "factory is the single construction path" precedent as Sprints 16 and 17). `AppState` gains `meters`/`effects`; new `web/session.py` `get_meters()`/`get_effects()` accessors mirror `get_rng()`'s app-state-with-fallback shape. New `GameEvent` members: `METER_DEPLETED`, `METER_RECOVERED`, `EFFECT_APPLIED`, `EFFECT_EXPIRED`, `EFFECT_REMOVED`. 25 new invariant tests caught two real bugs: both `_on_time_advanced` sweeps built a list of ORM rows inside a `with Session(...)` block, then read attributes off them (`entity_type`/`entity_id`/`key`) _after_ the block closed the session — `session.commit()`'s default `expire_on_commit` invalidates every loaded attribute, so the post-block reads tried to lazy-refresh from a closed session and raised; fixed by capturing plain `(str, str, str)` tuples before the session closes, in both services. Also caught (and fixed) a test-isolation bug of its own: an early draft of the meter tests registered a throwaway `MeterDef` under the _real_ `"hp"` key and popped it in fixture teardown, which — since `MeterRegistry` is a shared module-level singleton — deleted the real `"hp"` registration `test_save.py` (and `main.py`'s bootstrap) rely on; renamed the test-only keys to `__test_hp__`/`__test_fatigue__`. Full suite (509 unit/integration + 3 e2e + 5 simulation, including the audit-regression diff and concurrent-take-no-duplication guarantee) green throughout.

- **Sprints 17–18: Determinism (Seedable RNG, Modifier Resolution & Skill-Check)** — Two more Tier 1 engine-core primitives (`docs/engine_core.md` §3.5–3.6), implemented in dependency order (18 before 17.2) rather than roadmap numeric order, since `skill_check()`'s signature needs the `Modifier` type from Sprint 18 and the doc's own build-order table already notes Sprint 18 has no dependencies. `game/rng.py`'s `GameRng` wraps `random.Random` behind a seedable, deterministic interface (`randint`/`uniform`/`choice`/`chance`) — the _only_ permitted `random` import in `src/lorecraft`, enforced by a new ruff `flake8-tidy-imports` banned-api rule (`TID251`) scoped to `src/` via `per-file-ignores` (test-harness timing jitter in `tests/simulation/virtual_player.py` isn't game logic and doesn't feed the audit-regression diff, so it's exempted). One `GameRng` instance per app, built in `main.py`'s lifespan from new `Settings.rng_seed` (env `LORECRAFT_RNG_SEED`, default `None` = OS entropy) and stored on `AppState`. `GameContext` gains a required `rng` field and `build_game_context()` a required `rng` keyword — both real entry points and every test fixture updated (the factory being the single construction path is what keeps this a bounded change, same as Sprint 16's `item_location` rollout). `SchedulerEventContext` gains `rng` too. `clock/weather.py` (previously the only `random` user, already structured around an injectable `choice` callable) now requires `rng: GameRng` in `register_weather_handlers()` instead of quietly defaulting to `random.choice`. `game/modifiers.py`'s `Modifier`/`resolve()` is the one runtime resolver for bonuses stacked from many sources — fixed bucket order (`add` → `mult` → `clamp_max`/`clamp_min`, commutative within each bucket, never stored/cached); a `ModifierSource` protocol + `ModifierRegistry` + `resolve_for()` handle collection, with Tier 1 registering zero sources (the active-effect/trait sources arrive with Sprint 19, equipment/terrain with Sprint 23+). `game/checks.py`'s `skill_check(rng, *, base, difficulty, modifiers=(), key="check")` resolves `effective` through the modifier resolver, clamps the success threshold to `[CHECK_FLOOR=5, CHECK_CEIL=95]` (no impossible checks, no sure things), and rolls 1-100 — one resolution path for perception, lockpicking, bartering, and combat-to-hit; skill _identity_ (which skills exist, use-based improvement) stays Tier 2 (Sprint 24). 21 new unit tests: 9 for `GameRng` (seeded-sequence equality, bounds, chance boundaries), 12 for the modifier resolver (including the spec's worked example — base perception 30, `+5 add`, `×1.1`/`×0.8 mult`, `clamp_max 95` → `30.8`), 9 for `skill_check` (difficulty shifts, floor/ceiling clamps, same-seed determinism). Full suite (484 unit/integration + 3 e2e + 5 simulation, including the audit-regression diff and concurrent-take-no-duplication guarantee) green throughout — this band only adds plumbing, no command yet rolls through `ctx.rng`.

- **Sprint 16: Item Location/Ownership & Instance State** — First Tier 1 engine-core primitive (`docs/engine_core.md` §3.1–3.2). `models/items.py`'s `ItemStack` (`item_id`, `owner_type`/`owner_id`/`slot`, `quantity`, optional `instance_id`) is now the _only_ way to say where an owned item lives — it **replaces** `Player.inventory: list[str]` and the `RoomItem` table outright (both deleted, not deprecated). `ItemInstance` carries per-instance component state (`state: JsonObject` keyed by component name); Tier 1 registers no components, but a new `ComponentRegistry` (`game/components.py`) lets Tier 2 (durability, openable, lit, container — Sprint 22) or any world author plug in without core edits. `game/holders.py`'s `HolderRegistry` defines which holder types exist (`player`, `room`, `container` built in) and their move validators (mechanical-capacity hooks like slot occupancy or container fullness — none registered yet, Tier 2's job). `services/item_location.py`'s `ItemLocationService` is the one atomic operation family: `spawn()` (create from nothing — world import, loot; merges into an existing fungible stack or creates one instance per unit for component-bearing items), `destroy()` (remove with quantity-underflow guard), `materialize()` (split one unit off a fungible stack into a fresh instance — a torch becoming _this_ 40%-burned torch), and `move()` (the primitive everything else composes: validates source quantity/dest holder existence/registered validators/container-cycle freedom, then splits or merges as needed, all-or-nothing within the caller's transaction). Every place an item changed hands was migrated onto this: `services/inventory.py` (take/drop/give/use), `game/context.py` (`get_inventory()`/`get_visible_entities()`), `game/command_conditions.py` (`item_in_inventory`), `services/movement.py` (locked-exit key checks), `services/quest.py` (item-carried conditions/rewards), `npc/side_effects.py` (dialogue `give_item`), `services/save.py` (save-slot snapshots — v2 shape is a list of `{item_id, quantity, instance_id}` dicts; **loading a v1 flat `list[str]` snapshot still works**, converting on read by re-spawning one unit at a time, which naturally re-merges into a single fungible stack), `world/loader.py`/`world/versioning.py`/`tools/world_cli.py`/`scripts/import_world.py` (room-item YAML import/export and changeset item-deletion cleanup), and the admin/WS/HTMX inventory views (`admin/routers/players.py`, `main.py`, `web/session.py`, `web/frontend.py`). New `Item.bound: bool` field (data only here; enforcement — can't drop/sell/trade — is Tier 2 policy). New `InventoryEntry` TypedDict (`types.py`) documents the WS/HTMX inventory push shape. Caught two real bugs along the way, both fixed before they shipped: (1) every `raise` in `ItemLocationService` had `GameError`'s `(message, code)` constructor arguments backwards; (2) `StackRepo.delete_stack()` didn't flush after `session.delete()`, so a stack destroyed to exactly zero was still visible to a same-transaction `find_stack()` lookup (`Session.get()` consults the identity map before the DB). Also discovered and worked around a pydantic recursion bug unrelated to this feature: a bare `list[JsonValue]` SQLModel field type (as opposed to `dict[str, JsonValue]`, which is fine) sends pydantic's forward-ref resolver into infinite recursion on this pydantic/typing version — `SaveSlot.inventory` is typed `list[Any]` instead, with the JSON shape documented in a comment. 23 new unit tests for the primitive's invariants (`test_item_location_service.py`) plus the full existing suite (431 unit/integration + 3 e2e + 5 simulation, including the audit-regression diff and the concurrent-take-no-duplication guarantee) all green unchanged — no audit-event schema or ordering changes from this migration, by design.

- **Sprint 4: Player Authentication** — Real password auth replacing the previous zero-authentication lobby (anyone could one-click enter as any existing character). New `PlayerAuth` table (provider-agnostic `provider`/`provider_subject`/`credential_hash`, ready for OAuth without a schema change). `web/auth.py`'s `login_or_register()` creates an account atomically on first login, verifies the stored password hash on repeat login, and _claims_ pre-existing passwordless players (e.g. dev-seeded `player-1`) on first authenticated login — shared by `POST /auth/login` (JSON API) and the browser's `/lobby/enter`/`/lobby/create` (one password-checking code path for both). Password hashing reuses `admin/auth.py`'s existing PBKDF2-HMAC-SHA256 primitives rather than adding bcrypt/argon2 as a second hashing convention. `POST /auth/login` issues 15-minute access + 8-hour refresh JWTs (reusing `admin/auth.py`'s `create_token`/`decode_token`, signed with `Settings.player_session_secret`, a distinct token `type` from the browser's `lorecraft_session` cookie so neither can be replayed as the other); `POST /auth/refresh` rotates them, verifying the player still exists. `POST /auth/ws-ticket` mints a single-use, 60-second ticket (in-memory on `AppState.ws_tickets`, matching the existing `pending_disambig` pattern) — accepts either a bearer access token or the browser's signed session cookie, since browsers can't easily attach custom headers to a WebSocket upgrade. `main.py`'s `/ws` endpoint now resolves the connecting player via `?ticket=` first, rejecting outright on an invalid/expired/reused ticket rather than silently falling back to `?player_id=`. `Settings.allow_query_player_id` now defaults to `False`; kept as an explicit opt-in for test fixtures that intentionally exercise the wire protocol directly (`tests/simulation/`'s `VirtualPlayer`, several state-resolution integration tests) rather than the login UI. `POST /auth/oauth/{provider}/callback` is a genuine 501 stub marking the extension point — `PlayerAuth`'s shape already supports it, nothing is wired up. Fixed two bugs surfaced along the way: (1) JWT `create_token()` only had second-precision `iat`, so two tokens issued for the same subject within the same second were byte-for-byte identical — added a `jti` claim, fixing both the new player refresh endpoint and the pre-existing admin one; (2) flipping `allow_query_player_id` off exposed that `GET /lobby` depended on `get_current_player` (which now 401s with no session), so a brand-new visitor couldn't reach the page that lets them log in — a real e2e browser test failure caught this before unit tests would have; new `get_current_player_optional()` fixes it for `/lobby` only. 44 new/updated tests across `test_player_authentication.py` (15), `test_player_login.py` (9), and updated lobby/session/simulation/characterization tests for the password requirement.

- **Sprint 15: Core UX Completion** — Closed the last two `[~]` STATUS partials. **15.1 World clock/weather WS push:** `ConnectionManager.broadcast_global()` sends a message to every connected player regardless of room; `main.py` wires a `TIME_ADVANCED` handler that broadcasts current clock/weather state (`time_update`: hour, minute, day, season, weather) to all players on every tick, not just on connect/reconnect SSR. **15.2 Multi-player live lists:** `game/broadcast.py`'s `broadcast_command_effects()` now sends a second `state_change` (`players-online` panel) to the room a player _left_, not just the room they entered — previously, occupants of the old room only saw the departure narration text in the feed, with no live players-list refresh until they took some other action. Both verified with new/updated simulation tests exercising the real WS broadcast path over a live server.

- **Sprint 14: Unify Command Lifecycle** — `CommandEngine._execute_parsed` (`game/engine.py`) now catches exceptions from the command handler instead of letting them propagate uncaught: on a crash it rolls back the game DB session (new `GameContext.rollback_state`/`rollback_state_changes()`, wired at both entry points), discards any partial `ctx.messages`/`room_messages`/`updates`/`pending_events` the crashed handler produced (never tell clients something happened until the DB says it happened), replaces them with a generic error message, and records a new `GameEvent.COMMAND_FAILED` audit event (severity `ERROR`). New `game/broadcast.py`'s `broadcast_command_effects()` is now the one place step 12 of the architecture.md §26 lifecycle (room broadcast) lives — both `main.py`'s `/ws` command loop (now `async`) and `web/frontend.py`'s `POST /command` call it after `CommandEngine.handle_command()` returns, closing the gap Sprint 12's simulation tests surfaced: the raw `/ws` path never re-broadcast a command's `ctx.room_messages` narration or a `state_change` nudge to other WS-connected room occupants the way `POST /command` did. `web/frontend.py`'s previous inline copy of that logic is gone in favor of the shared function. New simulation test exercises the previously-broken `/ws` path over a real socket; full existing suite (unit/integration/e2e/simulation) confirms `POST /command` behavior is unchanged. **Follow-up:** `game/context.py`'s `build_game_context()` factory (Sprint 6.3) turned out to be unused by both real entry points, which still constructed `GameContext` inline — extended it to accept `audit_session` (a separate `Session`, matching real usage, replacing the old same-session `create_audit_repo` bool) and `rollback_state`, stopped it from synthesizing a fallback `WorldClock` when `clock` isn't given (a fabricated clock is silently wrong data, not a safe default — real callers pass `room_repo.world_clock()`, which can legitimately be `None`), and switched both `main.py` and `web/frontend.py` to call it. Neither entry point builds any repo by hand for `GameContext` anymore.

- **Sprint 13: Observability & CI Quality Gates** — `observability.py`: `configure_logging()` attaches a correlation-aware log formatter/filter to the root logger (idempotent; level from new `Settings.log_level`/`LORECRAFT_LOG_LEVEL`, default `INFO`), and `bind_transaction_context()` publishes a `TransactionContext`'s IDs to a `contextvars.ContextVar` for the duration of one command so every log call anywhere in that call stack picks them up automatically — wired into `create_app()` and both command entry points (`main.py`'s `/ws` loop, `web/frontend.py`'s `POST /command`). `CommandEngine._execute_parsed` (`game/engine.py`) now times each command handler and stamps `duration_ms` onto the `COMMAND_EXECUTED` audit event payload; `EventBus.emit()` (`game/events.py`) times each handler dispatch onto a new `HandlerResult.duration_ms` field and logs handler timing + registered-handler count ("depth") at DEBUG. New `analytics.command_latency_percentiles()` (p50/p95/p99) + `GET /admin/analytics/latency`. `.github/workflows/ci.yml`: three required jobs on push/PR to `main` — `quality` (`make lint` + `make typecheck` + `make test-cov`), `simulation` (`make test-simulation`), `e2e` (Playwright + `pytest tests/e2e`); new `make lint`/`make typecheck`/`test-cov` targets; new `pytest-cov` dev dependency with `[tool.coverage.report] fail_under = 80` (baseline ~82%). Fixed a latent bug found while dry-running the CI commands locally: `tests/simulation/*.py`'s `from tests.simulation.conftest import ...` only resolved under `python -m pytest`, not the bare `pytest` that `make test-simulation`/CI actually invoke — fixed by adding `"."` to `pythonpath` in `pyproject.toml`.

- **Sprint 12: Simulation Harness MVP** — `tests/simulation/`, a third test transport alongside the ASGI-transport integration tests and the Sprint 11 browser E2E harness: real `websockets` clients against a real, live `uvicorn` server, per `architecture.md` §25. `virtual_player.py`'s `VirtualPlayer` wraps one real `/ws` connection (`send_command()`/`run_script()` with optional timing jitter, `wait_for_broadcast()` for pushed messages). `conftest.py`'s `simulation_server`/`simulation_server_factory` fixtures boot the real app against a disposable per-test sqlite DB and the real `world_content/world.yaml` (same no-synthetic-world-content pattern as `tests/e2e/`). `test_multiplayer_scenarios.py` covers `player_joined` broadcast fan-out and concurrent `take` of a single-quantity item (exactly one winner, no duplication). `test_audit_regression.py` runs a fixed script against two independent fresh servers and diffs the normalized audit trail for determinism. New `simulation` pytest marker excluded from `pytest`/`make test` by default (`-m "not simulation"`, run via `make test-simulation`); no new install required (`websockets`/`httpx` were already transitive via `fastapi[standard]`, now declared explicitly in the `dev` extra). Surfaced but intentionally left unfixed: the raw `/ws` command loop doesn't yet re-broadcast `room_messages` to other room occupants the way `POST /command` does — tracked by Sprint 14 (unify command lifecycle).

- Launcher DB initialization: `./start.sh --init-dbs-if-missing` creates missing seed
  game/audit DBs before launch; `--init-dbs-only` performs setup and exits. Game DB
  import reads `world.yaml` from `--world-dir`/`--world`, defaulting to
  `world_content/`. Added `scripts/create_audit_db.py` for standalone audit schema
  creation.

- **Sprint 11: Browser E2E Harness** — `tests/e2e/` drives the HTMX/Alpine UI through a real headless-Chromium browser against a real, live `uvicorn` server, catching regressions (HTMX swaps, OOB panel updates) that the ASGI-transport integration tests can't see. `conftest.py`'s `live_server` fixture boots `create_app()` on a background thread with a disposable per-test sqlite DB and the real `world_content/world.yaml`; `test_gameplay_flows.py` covers character creation, movement with room/inventory panel updates, and dialogue → quest-start, exercising the same Ashmoore golden path documented in `docs/roadmap.md`. New optional `e2e` dependency group (`playwright`) and a `pytest` marker keep the suite out of the default `pytest`/`make test` run (`-m "not e2e"`); `make test-e2e` installs the extra + Chromium binary and runs it explicitly.

- **Sprint 10.5: Tooling Infrastructure** — `docs/tooling_infrastructure.md` design, implemented across five sub-sprints:
  - **10.5.1 Issues** — `docs/issues.yaml` (repo-tracked, git-blame-able) imported into the DB on first startup and re-exported on every admin mutation. `GET/POST/PUT /admin/issues` CRUD, TUI F6 screen, web panel Issues tab.
  - **10.5.2 News** — `docs/news.yaml` announcements with the same YAML↔DB sync pattern. In-game `news` command, public unauthenticated `/api/news` (JSON) and `/api/news/feed` (RSS 2.0), admin CRUD, TUI F7 screen, web panel News tab. `GameContext` gained an optional `news_repo`, wired at both direct construction sites and the `build_game_context()` factory.
  - **10.5.3 World CLI** — `python -m lorecraft.tools.world_cli {import,export,validate,diff,merge,stats}`. Added `export_world_document()` to `world/loader.py` (inverse of `import_world()`) as the shared basis for export/diff/merge/stats. Smoke-tested against the real `world_content/world.yaml`.
  - **10.5.4 Analytics** — `lorecraft.analytics` query functions over the audit log (top commands, NPC interaction counts, quest completions) and `PlayerSession` rows (player-hours), exposed via `GET /admin/analytics/{commands,npcs,quests,player-hours}`. No dashboard yet, per the design doc; command latency/event-bus-depth metrics wait on Sprint 13 instrumentation.
  - **10.5.5 Content linting** — `lorecraft.tools.validators`: dangling dialogue node references, room reachability from a start room, dead item references (`usable_with`, NPC `loot_table`), duplicate item names per room, oversized item stacks. Wired into `world_cli.py validate` via `--start-room`/`--strict`.

- **Sprint 10.4: Feature Registration Pattern** — `docs/feature-registration.md` documents the pattern for adding new gameplay features (combat, trading, PvP) without core edits: features define models, services, commands, and register with pluggable registries (CommandRegistry, CommandConditionRegistry, SideEffectRegistry, dialogue ConditionRegistry, RuleEngine, and ServiceContainer). Example structure shown for future combat feature (Sprint 18).

- **Sprint 10.3: Pluggable Command Conditions** — `game/command_conditions.py` — CommandConditionRegistry with pluggable condition predicates. Replaced hardcoded `_evaluate_condition` if/elif chain in registry.py with registry.evaluate(). Built-in conditions (requires_light, not_in_combat, flag_set, item_in_inventory, etc.) registered at module load; new predicates can be added without core edits.

- **Sprint 10.2: Pluggable Dialogue Conditions** — `npc/dialogue_conditions.py` — ConditionRegistry for dialogue choice/exit visibility. Replaced hardcoded flag checks in \_visible_choices with registry-based \_choice_visible() that evaluates all condition fields via registered predicates (required_flags, forbidden_flags initially; level_check, has_item, etc. can be added).

- **Sprint 10.1: Pluggable Dialogue Side Effects** — `npc/side_effects.py` — SideEffectRegistry replacing hardcoded if/elif branches in \_apply_side_effects. Built-in handlers (set_flags, clear_flags, give_item, start_quest, end_dialogue) registered at module load; new effects can be added without touching dialogue.py.

- **Sprint 9.4: Item Matcher Consolidation** — Replaced three near-identical inline matching loops in `repos/item_repo.py` with one `_match_kind()` classifier plus two thin aggregators: `_best_matches()` (exact-wins, fuzzy-fallback; used by `search_in_room`/`search_player_items`) and `_any_matches()` (position-preserving any-match filter; used by `inventory_slots_matching`, which must stay positionally addressable for indexed take/drop like "2.sword"). Verified position ordering is unchanged with a mixed exact/fuzzy manual check. Same public API, same behavior.

- **Sprint 9.3: Inventory Take/Drop DRY** — Added `InventoryService._resolve_single()` (shared find→disambiguate step, generic over match shape via an `item_of` extractor) and `_do_take()`/`_do_drop()` (shared act step: remove, say, tell_room, emit event). Applied to `_take_one`, `_take_quantity`, `_take_indexed`, `_drop_one`, `_drop_quantity`, `_drop_indexed`, plus `examine`/`use_item`/`give_item` which had the same boilerplate. Behavior preserved exactly (same messages, same disambiguation prompts, same event counts).

- **Sprint 9.2: Event-Wiring Convention** — `QuestService.register(bus)` added, matching the convention already used by `NpcScheduler`/`SchedulerService`. Replaces the three inline `bus.on(GameEvent.X, quest_service.check_progression)` calls in `main.py`'s lifespan with one `services.quest.register(bus)` call.

- **Sprint 9.1: Service Container** — `services/container.py` — `ServiceContainer` dataclass holding the five stateless gameplay services (movement, inventory, save, dialogue, quest), built once via `ServiceContainer.build()`. `AppState` now carries a `services` field; `main.py` builds one container per app lifespan and passes it to both command registration and event wiring instead of each command module (and `main.py`'s inline `QuestService()`) constructing its own. `register_all_commands(registry, services=None)` defaults to a fresh container so existing direct-call test sites and the `web/session.py` standalone fallback keep working unchanged. `register_social_commands` gained an optional `dialogue_service` parameter, matching the other three command modules.

- **Sprint 8.3: Admin API Decomposition** — Split `admin/api.py` (817 lines) into per-resource routers under `admin/routers/`:
  - `players.py` (191 lines) — list/state/teleport/flags/freeze/unfreeze
  - `audit.py` (93 lines) — query_audit, session_replay
  - `world.py` (357 lines) — rooms, items, NPCs, and changesets (create/scan/promote)
  - `clock.py` (125 lines) — get/pause/resume/time-ratio/weather
  - `accounts.py` (93 lines) — list/create/revoke admin accounts
  - `admin/api.py` now 20 lines: mounts `auth_router` + the 5 resource routers onto `admin_router`. Same route paths, same `admin_router` export, so `main.py` required no changes.
  - HTTPException raises remain at the route layer per router (already separated from game-state logic — no service-layer HTTP leakage to fix).
  - All 23 admin API integration tests pass unchanged; basedpyright 0 errors on `admin/`.

- **Sprint 8.2: Parser Grammar Extraction** — Split `game/parser.py` (778 lines) into:
  - `game/grammar.py` (322 lines) — Grammar constants (ARTICLES, PREPOSITIONS, PHRASAL_VERBS, DIRECTIONS, VERB_ALIASES, etc), text processing (normalize, tokenize, make_phrase), semantic rules (extract_quantity_and_adjectives, direct_role_for_verb, find_first_preposition, map_prep_to_role), fuzzy matching (score_match).
  - `game/diagnostics.py` (119 lines) — ParseDiagnostics dataclass, diagnose_command, print_diagnostics for parser debugging.
  - `parser.py` now 399 lines, focused on command parsing (ParsedCommand, ParseResult, parse_command, parse). Re-exports diagnostics for backwards compatibility.
- Fuzzy matching and grammar rules now reusable for alternative parsers or CLI modes.
- All parser tests passing (37 comprehensive tests + full integration suite).

- **Sprint 8.1: Web Frontend Decomposition** — Split `web/frontend.py` (1,306 lines) into three focused modules:
  - `web/session.py` (380 lines) — Dependency injection (get_engines, get_app_state, get_command_engine, get_manager, get_bus), session auth (player_session_secret, set_player_session_cookie, ensure_player_session), state snapshots (inventory_snapshot, room_panel_context, active_quests_snapshot, world_time_snapshot), presence helpers (format_idle_duration, presence_for_player, players_here), grace period expiration, CommandResult dataclass.
  - `web/rendering.py` (180 lines) — Template rendering (build_map_data, audit_to_feed, feed_items_html), HTML output formatting (mark_oob_swap), command resolution (resolve_command_text), dev player creation.
  - `frontend.py` (784 lines) — Focuses exclusively on FastAPI routing and HTTP endpoints. Updated all endpoint handlers and test imports.
- Replaced `getattr`-chain state access in dependency injection with explicit functions (FastAPI `Depends()` ready for Sprint 9).

### Added

- **Sprint 7.4: Event-Flow Characterization Tests** — 10 unit tests locking in event-bus behavior before Sprint 8–9 refactors. Covers: event emission order and priority-based handler execution (higher priority runs first); exception isolation (one handler's error doesn't block others); multiple event types and handlers per event; handler result collection with success/error status; work-event classification. Tests verify core event dispatch guarantees. Tests in `tests/integration/test_event_flow.py`.
- **Sprint 7.3: Admin WebSocket Characterization Tests** — 7 integration tests locking in current behavior of `/admin/ws` endpoint before Sprint 8–9 refactors. Coverage: token validation (JWT accept/reject with code 1008), connection lifecycle (accept, receive, disconnect), multiple concurrent clients, error handling (malformed messages, connection errors). Verifies graceful error handling and state cleanup on disconnect. Tests in `tests/integration/test_admin_websocket.py`.
- **Sprint 7.2: Admin API Characterization Tests** — 6 additional integration tests extending admin endpoint coverage to 23/28 endpoints (~82% coverage) in `test_admin_api.py`. New coverage: player state manipulation (freeze/unfreeze with session status), world data queries (items, NPCs), clock management (time ratio), admin account management (list accounts). Tests verify proper HTTP status codes, role-based access control, and state mutations.
- **Sprint 7.1: Web Characterization Tests** — 23 integration tests locking in current behavior of `web/frontend.py` before Sprint 8–9 refactors. Coverage areas: (1) State resolution — game screen SSR with player/room/inventory/feed snapshots, error handling for missing rooms/players; (2) Session reconnect edge cases — grace period handling, presence status rendering (`online`/`grace`/`away`/idle duration); (3) Feed pagination — `/partials/feed?since=X` filtering, chronological ordering, COMMAND event exclusion; (4) Error rendering — missing room/player handling, empty inventory, many items, multiline OOB swap attributes. Tests in `tests/integration/test_frontend_characterization.py`.

### Fixed

- **Sprint 6: Type Safety Foundation** — Removed 18 `cast(GameContext, ctx)` calls from command handlers by properly typing the context parameter as `GameContext` instead of `object`. Command handlers are now type-checked by basedpyright to ensure safe context access. Replaced `cast(Any, ctx)` + unsafe `getattr()` in `game/registry.py` condition evaluation with direct `GameContext` attribute access. Upgraded basedpyright to `standard` mode (was `basic`); 0 errors.
- **Sprint 5: Error Handling Foundation** — Replaced 20 silent `except Exception` blocks with specific exception types and logging across auth, websocket, frontend, and parser modules (improves debuggability in production). Added guards against quantity underflow in `ItemRepo.remove_from_room()` (now raises `ConflictError` instead of silently deleting).
- Ambiguous `examine`/`inspect`/`x` targets now defer to `InventoryService`'s numbered disambiguation prompt (`disambig_pending` + choice number) instead of blocking at parse time with a plain "Perhaps you meant" list — matching `take`/`drop` behavior.
- HTMX `POST /command` now calls `CommandEngine.handle_command()` (commands were previously not executed).
- WebSocket client connects to `/ws?player_id=…` instead of the non-existent `/ws/game` path.
- Dev seed DB (`test_dbs/`) regenerated from Ashmoore `world_content/world.yaml`; `player-1` now starts at `village_square` with working exits.
- Removed hardcoded tavern/Mira/sword quest seed from `main.py`; empty databases bootstrap from `world_content/world.yaml` via `lorecraft.world.bootstrap`.
- Lobby and game templates use `current_player.username` instead of the nonexistent `name` field.
- Dialogue `choice 1` / numeric replies parse correctly (`choice_index`); bare digits during conversation map to `choice N`.
- HTMX out-of-band swaps for the dialogue overlay (and other panels) now attach `hx-swap-oob` even when partial markup splits attributes across lines.
- Dialogue overlay hides reliably on `bye` / End conversation (no conflicting Tailwind `flex` + `hidden` classes).
- Terminal dialogue nodes (e.g. Mira’s farewell) show their final line in the overlay instead of closing before the text appears.
- `quit` starts the disconnect grace period, notifies the room, and refreshes Here Now for other clients.
- WebSocket disconnect broadcasts feed text and refreshes the player list for roommates.

### Added

- **Sprint 6: Type Safety Foundation** — `CommandHandler` protocol in `types.py` for type-safe command dispatch. All 22 command handlers now use `ctx: GameContext` instead of `ctx: object`, enabling the type checker to verify context usage and catch errors at type-check time rather than runtime. Added `build_game_context()` factory in `game/context.py` for centralized GameContext construction (all entry points: websocket, scheduler, tests). Added TypedDict schemas for WebSocket and API payloads: `WsFeedAppend`, `WsStateChange`, `WsPlayerLeft`, `WsNarrative`, `ApiStatusResponse`.
- **Sprint 5: Error Hierarchy** — `lorecraft/errors.py` with `GameError` base class (machine-readable error codes) and five domain-specific exceptions: `ValidationError`, `NotFoundError`, `PermissionError`, `ConflictError`. Enables typed error handling, analytics tracking, and error-based testing. Comprehensive unit tests in `tests/unit/test_errors.py`.
- `services/scheduler.py` — `SchedulerService`, a persistent DB-backed job scheduler (Sprint 3, roadmap). `schedule(job_type, at_game_epoch, payload)` persists a `ScheduledJob` row; on every `TIME_ADVANCED` tick it marks due jobs `dispatched` and emits `GameEvent.SCHEDULED_JOB_DUE` for each so owning subsystems (combat, NPC movement, delayed world effects) can react without the scheduler knowing any game rules. `cancel(job_id)` marks a pending job cancelled. Wired into `AppState.scheduler` / `main.py` alongside the clock runner and NPC scheduler.
- `models/scheduler.py` — `ScheduledJob` table (`job_type`, `due_at_epoch`, `status`, `payload`, `created_at`), registered in `db.GAME_TABLE_MODELS`.
- `repos/scheduler_repo.py` — `SchedulerRepo.due(current_epoch)` for querying pending jobs at or before a game epoch.
- Graphify actually connected to the dev workflow: `make install-hooks` previously pointed `core.hooksPath` at a `.githooks/` directory that didn't exist. Added `.githooks/post-commit` (refreshes `graphify-out/graph.json` after each commit) and a Claude Code `SessionStart` hook (`.claude/settings.json` + `.claude/hooks/session-start.sh`) so web sessions get the graph refreshed automatically. `scripts/graphify-refresh.sh` now skips gracefully (exit 0) instead of failing when the `graphify` binary isn't installed.
- Item `aliases` (YAML/model/loader/validator) so players can refer to an item by a nickname sharing no words with its name (e.g. "blade"/"shortsword" for Rusty Iron Sword); wired through `GameContext.get_visible_entities()`/`get_inventory()` for parser fuzzy resolution and `ItemRepo` room/inventory search.
- Context-aware `help`: generated from real command metadata (`CommandDefinition.help_text`, `CommandRegistry.all_commands()`) instead of a hardcoded string; varies by dialogue (social + global only), combat (`NOT_IN_COMBAT`-gated commands drop out), and `Room.disabled_commands`.
- `use <item> [on/with <other>]` + `InventoryService.use_item()` — wires the previously-orphaned `Item.usable_with` field into gameplay; combining two items whose `usable_with` lists reference each other emits `GameEvent.ITEM_USED`. Added a `cage_key`/`cage_lock` `usable_with` example to `world_content/world.yaml`.
- `GameContext.parsed_command` — the dispatch loop now stashes the current `ParsedCommand` on context before invoking a handler, so handlers can read secondary roles (e.g. `use X on Y`, `give X to Y`) via `command_patterns.py` helpers instead of only the single noun string.
- `give <item> to <name>` + `InventoryService.give_item()` — hands a carried item to an NPC in the room and emits `GameEvent.ITEM_GIVEN`.
- `unlock <direction>` / `lock <direction>` + `MovementService.unlock()`/`lock()` — persist `Exit.locked` (while carrying `key_item_id`) so an exit unlocked once no longer needs the key for later movement, including by other players.
- `NpcRepo.find_in_room()` — shared NPC name lookup used by `talk` and `give`.
- `lorecraft.world.bootstrap` — YAML-driven empty-DB import and configurable dev player seeding.
- Config env vars: `LORECRAFT_WORLD_YAML_PATH`, `LORECRAFT_SEED_PLAYER_ID`, `LORECRAFT_SEED_PLAYER_USERNAME`, `LORECRAFT_SEED_PLAYER_START_ROOM`.
- NPC (Mira), dialogue tree, and sample quest in `world_content/world.yaml` for Ashmoore playtesting.
- Dialogue overlay and quest tracker partials for the HTMX game UI (OOB swaps on talk/quest updates).
- `dialogue_panel_state()` — rebuilds overlay content from persisted dialogue flags (node text and choices).
- `ConnectionManager.is_connected()` and Here Now presence from DB room occupancy plus live WS status.
- Here Now labels: online (green), grace **(Reconnecting…)**, away/idle (grey, e.g. `Idle 2h4m`).
- Dev `player-2` seeded for multi-player testing; `?player_id=` overrides the lobby cookie.
- World clock SSR in the game header; WS client handlers for `time_update` and `clock_tick`.
- Integration tests for HTMX command dispatch, dialogue choices, farewell nodes, and `bye` (`tests/integration/test_frontend_command.py`).
- Unit tests for world bootstrap, dialogue panel state, player presence, OOB markup, and `choice` parsing.

### Changed

- `import_world.py` wipes NPCs, dialogue trees, and quests on `--fresh`; seeds `player-1` and `player-2`; resets players on fresh import.
- `start.sh` copies `test_dbs/` seed databases again (not `game.db`).
- Admin and integration tests updated for Ashmoore room IDs (`village_square`, `wandering_crow_inn`, `market_stalls`, etc.).
- Key gallery disambiguation fixture exit link updated for Ashmoore topology (`blacksmith_forge`).
- Dialogue overlay styles NPC lines as a quoted blockquote; End conversation is a numbered option matching other choices.
- Removed duplicate panel wrapper IDs in `game.html` (inventory, Here Now) so OOB swaps target a single element.

## [0.2.0] - 2026.06.29

### Fixed

- `take`/`drop` item matching now singularizes item names as well as player input, so plural queries like `take herbs` match items named `Bundle of Dried Herbs`.
- Inventory command text and all inventory panels now group duplicate carried items with `[quantity]` prefixes (e.g. `[2] Worn Copper Coin`).

### Added

- Integrated Lorecraft parser v1 (`lorecraft_parser_v1`): semantic roles, prepositions, adjectives, quantities, quoted strings, phrasal verbs, compound commands (`;`), optional `GameContext` fuzzy resolution with disambiguation, in-character parse errors, and diagnostic tracing.
- Added `parse_command`, `ParseResult`, `diagnose_command`, and `registry_verb` helpers in `src/lorecraft/game/parser.py`; kept `parse()` as a backward-compatible wrapper for legacy callers.
- Added `GameContext.get_visible_entities()` and `GameContext.get_inventory()` for parser entity resolution.
- Wired `CommandEngine` and the HTMX frontend command path through `parse_command` (including compound execution and suggestion messages).
- Added comprehensive parser tests in `tests/game/test_parser_comprehensive.py`.
- Added offline parser diagnostic CLI at `tools/parser_diag.py`.
- Added `docs/command_parser.md` — parser output model, command pattern taxonomy, and handler integration guidance.
- Added `src/lorecraft/game/command_patterns.py` — `CommandPattern` enum, verb mapping, and typed role helpers (`speech_roles`, `transfer_roles`, `container_roles`, …).
- Added pattern-grouped parser tests in `tests/game/test_parser_patterns.py` and `tests/unit/test_command_patterns.py`; shared fixture in `tests/game/conftest.py`.
- Added `docs/parser_and_commands.md` — command authoring guide, item disambiguation layers, and Key Gallery testing notes.
- Added `key_gallery` room (Red Key, Iron Key, Rusty Iron Key, Steel Key, Cage Key, Cage Lock, Rusty Iron Sword, Red Rose) in `world_content/world.yaml` for in-game disambiguation testing; pytest helpers live in `tests/fixtures/disambig_fixtures.py`.
- Added `tests/unit/test_inventory_disambiguation.py` for shortened-name matching and numbered ambiguity prompts.
- `take`/`drop` object ambiguity now defers to `InventoryService` numbered disambiguation instead of blocking at parse time.
- `take` and `drop` now accept quantity, all, and indexed selectors: `take 2 coin`, `take 2 coins`, `take all coin`, `drop all coin`, and `take 2.coin` (second matching instance).
- Room `look` text and web room panel now group duplicate visible items with `[quantity]` prefixes, matching inventory display.
- HTMX inventory panel now refreshes when picking up another copy of an already-carried item (fixed set-based change detection).
- Replaced the primary player web UI with the HTMX + Alpine.js + Jinja2 server-rendered template (lorecraft_frontend_starter).
- Added `src/lorecraft/web/frontend.py` — lobby, game screen, command POST (with OOB updates), and all partial endpoints (`/partials/*`).
- Added `templates/` (base, game, lobby, partials for feed/room/inventory/minimap/players) and `static/css+js`.
- Wired Jinja2Templates + StaticFiles mount in `main.py`; root `/` now redirects to new lobby.
- Lobby provides player selector using existing seeded players; game screen SSRs panels using real repos + audit log for feed.
- `/command` executes via core CommandEngine/GameContext, returns feed items + OOB swaps for changed panels, and broadcasts `state_change` via ConnectionManager.
- Added `recent_for_room` / `recent_for_actor` + `get_exits_with_names` + `list_all` helpers to support the UI.
- Old vanilla client assets preserved under `/static` (flat) for backward compat during transition.
- Command processing, feed (audit-backed), movement, inventory, and minimap exits now work via the new UI.

### Added (Phase 4 — NPCs & Quests)

- Added `models/dialogue.py` — `DialogueTree` SQLModel table storing full dialogue tree as a JSON blob.
- Added `repos/dialogue_repo.py` and `repos/quest_repo.py` — data access for dialogue trees and quest progress.
- Added `npc/dialogue.py` — `DialogueService` with `start`, `choose`, and `end` methods; flag-gated choices; side effects (`set_flags`, `clear_flags`, `give_item`, `start_quest`, `end_dialogue`); dialogue state stored in `player.flags`.
- Added `npc/scheduler.py` — `NpcScheduler` subscribes to `HOUR_CHANGED` and moves NPCs according to their schedule.
- Added `services/quest.py` — `QuestService.check_progression` subscribes to `ITEM_TAKEN`, `PLAYER_MOVED`, and `ITEM_DROPPED`; evaluates stage conditions (`flag_set`, `flag_clear`, `room_visited`, `item_in_inventory`); advances or completes quests and awards rewards.
- Added `commands/social.py` — `talk`/`speak`, `choice`/`choose`, `say`, `bye`/`farewell`/`goodbye` commands.
- Extended world YAML validator and loader to accept `npcs`, `dialogue_trees`, and `quests` sections.
- Seeded starter world with Mira the Innkeeper (NPC), her dialogue tree, and a sample "Lights in the Square" quest.
- Added dialogue overlay to game client — appears with NPC name, node text, and clickable choice buttons; hides when dialogue ends; "End conversation" button closes via `bye` command.
- Added live quest tracker to game client right panel — shows active quest titles and current stage descriptions; updates on quest start, stage advance, and completion.
- Added `quest_repo` and `dialogue_repo` fields to `GameContext` (optional, backward-compatible).
- Added 14 new unit tests in `test_dialogue.py` and `test_quest_service.py`.

### Added (Phase 6 — Admin Tools)

- Added Phase 6 admin tools: JWT auth, role-based REST API, and admin push WebSocket at `/admin/ws`.
- Added `admin/auth.py` — PBKDF2-HMAC-SHA256 password hashing, PyJWT access/refresh token issue and verify, role hierarchy (`observer < moderator < world-builder < superadmin`), FastAPI dependency shortcuts.
- Added `admin/api.py` — admin router with endpoints for player management (list, state, teleport, flags, freeze/unfreeze), audit log query, world rooms/items/NPCs, changeset lifecycle (create, scan, promote), clock control (pause/resume, time-ratio, weather), and admin account management.
- Added `admin/websocket.py` — per-connection async queue, `AdminBroadcaster` fan-out, JWT auth via `?token=` query param.
- Added `admin/broadcaster.py` — `AdminBroadcaster` for safe push from synchronous EventBus handlers to async WS clients.
- Added `world/versioning.py` — `VersioningService` with changeset CRUD, conflict scanner (broken exits, displaced players, held items), and atomic promotion with `WorldMeta.schema_version` bump.
- Added `models/admin.py` — `AdminUser` SQLModel table with role and revocation support.
- Added `state.py` — `AppState` dataclass extracted from `main.py` to break circular imports.
- Added admin web panel at `/admin` — single-file SPA (Terminal Gothic styling) with login, live WS push, and tabs for all admin sections.
- Added Textual TUI (`admin/tui/app.py`) as an optional `admin-tui` dependency group; F1–F5 screen routing; credential storage at `~/.config/lorecraft-admin/credentials.json`.
- Added `LORECRAFT_ADMIN_JWT_SECRET`, `LORECRAFT_ADMIN_SEED_USERNAME`, `LORECRAFT_ADMIN_SEED_PASSWORD`, `LORECRAFT_ADMIN_SEED_ROLE` config env vars.
- Added `pyjwt>=2.9.0` as a production dependency.
- Added 39 new tests across `tests/unit/test_admin_auth.py`, `tests/integration/test_admin_api.py`, and `tests/integration/test_versioning.py`.

### Changed

- Updated `start.sh` to create `.venv` when missing and install Lorecraft editably with the admin TUI extra when dependencies are absent or incomplete.
- Excluded `admin/tui` from basedpyright checks (optional Textual dependency not installed in base venv).
- Extracted `AppState` from `main.py` into `lorecraft/state.py` to allow admin router import without circular dependency.
- Seeded `WorldMeta` singleton in `_ensure_starter_world` to support changeset promotion.

### Verified

- `.venv/bin/python -m pytest` passes with 89 tests.
- `.venv/bin/ruff check src tests` passes.
- `.venv/bin/ruff format --check src tests` passes.
- `.venv/bin/basedpyright --warnings` passes (TUI excluded).

## [0.1.0] - 2026-06-27

### Added

- Added `docs/status.md` to track implementation progress against the architecture overview.
- Added initial `src/lorecraft` package scaffold for the multiplayer text adventure engine.
- Added environment-driven settings in `lorecraft.config`.
- Added core game primitives:
  - `GameContext` for per-command execution state.
  - `TransactionContext` and transaction source types.
  - `GameEvent`, `Event`, and synchronous `EventBus`.
  - `RuleEngine` and `RuleResult`.
  - `CommandRegistry`, command scopes, command conditions, and condition evaluation.
  - `ParsedCommand` parser with direction aliases, verb aliases, and article stripping.
  - `CommandEngine` dispatch scaffold.
  - `ConnectionManager` for WebSocket-style player connections and room broadcasts.
- Added pytest-based unit test structure under `tests/unit`.
- Added placeholder `tests/integration` and `tests/simulation` directories for future database and WebSocket coverage.
- Added `make test` for focused local verification.
- Added repository agent instructions in `AGENTS.md`, with `CLAUDE.md` importing them for Claude Code compatibility.
- Added guidance to keep `CHANGELOG.md` current and synchronize package versions in `pyproject.toml` and `src/lorecraft/__init__.py`.
- Added guidance to aim for type hints in new and changed Python code while allowing pragmatic omissions.
- Added a `dev` optional dependency group for local development tools: BasedPyright, pytest, and Ruff.
- Added pre-commit configuration for file hygiene, secrets detection, Ruff, YAML linting, Prettier for JavaScript/TypeScript files, and BasedPyright push checks.
- Added SQLModel table definitions for world, player, session, quest, combat, versioning, interaction, and audit persistence.
- Added database bootstrap helpers for creating game tables and audit tables in separate SQLite databases.
- Added shared structural typing aliases and protocols for JSON payloads, WebSocket connections, command contexts, players, and rooms.
- Added thin SQLModel repository wrappers for players, rooms, items, NPCs, and audit events.
- Added repository unit tests covering core game model and audit event round trips.
- Added FastAPI service wiring with startup table initialization and shared app state.
- Added `/health` and `/ws` endpoints for service health checks and player command WebSocket sessions.
- Added direct ASGI integration tests for lifespan startup, health checks, WebSocket connection, and command dispatch.
- Added audit recording for blocked and executed commands.
- Added meta commands for `help` and `quit`.
- Added movement commands and `MovementService` room transitions.
- Added WebSocket movement integration coverage for persisted room changes.
- Added a minimal browser client harness with WebSocket connection, message routing, state tracking, text feed, command input, and room/session status display.
- Added static asset routes for the browser client.
- Added starter world bootstrap for empty databases so the browser harness can connect as `player-1`.
- Added browser client smoke coverage for the served HTML, CSS, and JavaScript contract.
- Added repo-local seed test database files that `start.sh` copies into `/tmp` for browser harness startup.
- Added a persistent world clock runner with startup fast-forwarding and boundary events.
- Added weather and season state transitions driven by day changes.
- Added inventory inspection and item movement commands for `look`, `examine`, `take`, `drop`, and `inventory`.
- Added YAML world validation and import helpers for rooms, exits, items, and room item placement.
- Added a Tailwind-powered world UI layout with minimap, status, feed, inventory, and quest panels.
- Added SVG minimap rendering for visited rooms and fog-of-war adjacent rooms.
- Added structured WebSocket UI snapshots for room, visited-room, inventory, and time state.
- Added save/load commands and `SaveSlotService` for player-owned state.
- Added WebSocket disconnect grace, reconnect session reuse, reconnect sync payloads, and grace-expiry state handling.
- Added system audit events for disconnect, reconnect, and expired grace transitions.

### Changed

- Documented the project package layout as `src/lorecraft` in `docs/architecture.md`.
- Configured pytest to import package code from `src`.
- Added `sqlmodel` as a production dependency for the persistence layer.
- Added a BasedPyright project configuration for the `src` package and local `.venv`.
- Replaced broad `Any` annotations in the command, event, rule, connection, and model layers with narrower protocols and JSON types.
- Preserved full SQLAlchemy database URLs while retaining existing SQLite path handling.
- Added FastAPI and Starlette as production dependencies for the service layer.
- Tightened `GameContext` to use concrete repository, model, event bus, and connection manager types.
- Extended `CommandEngine` to commit state changes, write audit events, and flush queued domain events.
- Packaged the browser client assets with the Python package.
- Declared PyYAML as a production dependency for world authoring imports.
- Updated the browser client router to render inventory and minimap state from structured updates.
- Added SQLite compatibility handling for the save-slot `visited_rooms` column.

### Verified

- `.venv/bin/python -m pytest` passes with 49 tests.
- `.venv/bin/ruff check src tests` passes.
- `.venv/bin/ruff format --check src tests` passes.
- `.venv/bin/basedpyright --warnings` passes.
