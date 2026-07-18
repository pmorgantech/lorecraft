---
kindle_doc_weaver: ignore
---

# Engine / game-data separation — deep-dive plan

**Status:** planning only (plan-ahead, not scheduled). Deepens the [`wishlist.md`](wishlist.md) →
*Engine / game-data separation* note into a concrete contract + phased path. **Do not build
speculatively** — act only when a scripting-layer decision or a second world creates the pressure
(see *Triggers*).

## Vision

**One engine, many worlds.** Lorecraft (the Python/FastAPI engine) should run any number of settings
— a fantasy Ashmoore, a sci-fi world, a teaching sandbox — each living in **its own content repo**,
without forking the engine. `architecture.md` already gestures at this (`world_content/` annotated
"separate git repo (symlinked or submodule)") but it's never been made real.

## Current state (what's already true — and what isn't)

**Already in our favor:**
- The **tier split is done** — `engine/` is import-pure, `features/` are Tier 2, `webui/` are hosts.
  Content is *data*, loaded at the composition layer, never imported by the engine.
- **All content paths are env-externalized** — `LORECRAFT_WORLD_YAML_PATH` (+ `_ISSUES_`, `_NEWS_`,
  `_HELP_YAML_PATH`) already point the loader anywhere; "the path is external" is mostly solved.
- **A validator + a versioning/changeset system exist** — `world/validator.py` (pydantic schema +
  cross-ref checks), `world/versioning.py` (schema migrations bumping `WorldMeta.schema_version`),
  and `WorldMeta.schema_version` / `engine_version` are already separate plumbing.
- **A single load seam** — `world/loader.py` + `world/bootstrap.py` (`ensure_world_bootstrapped`)
  are the one place YAML → DB happens.

**Still coupled / undecided:**
- **Content lives inside the engine repo** — `world_content/world.yaml` ships in-tree, and
  `docs/{issues,news,help_topics}.yaml` live under `docs/` (an inconsistent split; see below).
- **No published content contract** — the YAML schema is enforced by `validator.py` but not
  *packaged/versioned* as "what a content repo must provide."
- **Tests depend on the Ashmoore world** — `world_content/world.yaml` is both the reference/example
  *and* the test fixture; a split must decide which it is.
- **No scripting layer yet** — the sharpest future edge (below).

## What "content" is (and an inventory decision)

Not everything currently in YAML is *world* content:

| Kind | Today | Verdict |
|------|-------|---------|
| Rooms, exits, items, NPCs, dialogue, quests, shops, transit | `world_content/world.yaml` | **World content** → content repo |
| Help topics | `docs/help_topics.yaml` | **World content** (per-setting help) → content repo |
| News / announcements | `docs/news.yaml` | **Operational** (ops publishes) → could be either; lean content repo |
| Issues (dev tracker) | `docs/issues.yaml` | **Engine-dev artifact** → stays with the engine repo |

**Decision to make early:** consolidate world content under one root (e.g. `world_content/`) so a
content repo is a single directory, not scattered across `docs/`. Issues stay behind.

## The content contract

The engine↔content boundary, versioned and validated:

1. **Directory layout** — a content root with a known shape (`world.yaml`, `help_topics.yaml`,
   `news.yaml`, optional `scripts/`, optional media). One env var (`LORECRAFT_CONTENT_ROOT`) or a
   small manifest points at it.
2. **Schema + version** — the YAML schema `world/validator.py` already enforces, plus a declared
   **content schema version** the engine checks against a supported range (the `WorldMeta.schema_version`
   / `world/versioning.py` migration plumbing already exists; extend it to gate load with a clear
   "content vN needs engine ≥ X" error instead of a crash).
3. **Validation as the gate** — `world/validator.py` + `tools/validators.py` are the acceptance test
   a content repo must pass in *its own* CI (shipped as a callable/CLI the content repo depends on).
4. **Scripting entry points** — *if/when* a scripting layer exists (below), the contract declares
   where scripts live and how they're loaded, so scripting is content, not engine code.

## The hard part: the scripting layer

Today builders configure **YAML only**; custom behavior needs backend code via the pluggable
registries (this session's `open_timed_passage` handler is an example — it's *engine* code today).
An established scripting layer (Evennia Python modules / Aardwolf Lua / Ranvier JS) would be **game
data too** — so:

> **Whatever scripting decision is made, design its loading path as if the content repo is already
> external.** If scripting loads by importing engine-internal modules, the split becomes impossible
> to retrofit.

Options when the pressure comes (unchanged from the wishlist): Python modules (full power, needs the
external-load path designed right), embedded Lua (sandboxed, in-game editable, needs a binding
layer), or stay YAML-only (safest; extend registries). **This plan's only ask now:** don't add
scripting via an engine-internal import path.

## Phased migration (when triggered)

1. **Consolidate + contract.** Move `help_topics.yaml`/`news.yaml` under one content root; publish
   the schema + `validate` CLI as the content contract; gate load on a content-schema-version check
   with a clear error. *(Engine-repo-only; no external repo yet.)*
2. **Externalize the reference world.** `world_content/` becomes a real separate repo, pulled in via
   git submodule / package / a configured `LORECRAFT_CONTENT_ROOT`. Ashmoore is relabeled the
   **reference/example content repo**, not the engine's only world.
3. **Decouple tests.** Tests either vendor a small `tests/fixtures/`-style content package or pull
   the reference content repo explicitly — so the engine suite doesn't secretly depend on Ashmoore.
4. **(If scripting lands)** ship scripts through the same external boundary from day one.

## Risks & decisions

- **Test/fixture coupling** is the biggest practical snag — the engine suite loads Ashmoore today.
  Phase 3 must give tests a first-class content source, or every content edit risks breaking engine CI.
- **Version-skew UX** — a content repo pinned to an old schema against a newer engine must fail with
  a *clear, actionable* message (the migration plumbing exists; wire it into the load gate).
- **Don't over-abstract** — one clean loader seam + a validated contract is the goal, not a plugin
  framework. `world_content/` staying in-tree is *fine* until a second world or scripting appears.

## Triggers (when to act — not before)

- A **scripting-layer decision** is made (or firmly deferred) — design its load path external either way.
- A **second world/setting** is actually wanted (the real "one engine, many worlds" pressure).
- Revisit this note at that point; until then, the constraint it imposes is only: *keep the load seam
  clean and design any new content-loading (esp. scripting) as if the content repo is external.*
