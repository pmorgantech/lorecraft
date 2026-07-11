# Repository agent instructions

## Current focus: foundation before features (2026-07-01)

The core engine must be very well designed, well tooled, well tested, and internally
consistent **before** expanding commands or adding combat/trading/PvP. Do not skimp on
code design and quality.

- `CODE_AUDIT.md` findings + the `docs/roadmap.md` foundation band (Sprints 5–15) are the
  active work queue. Feature sprints (16+) are gated behind the roadmap's foundation exit criteria.
- When touching code, leave it more consistent than found: typed errors from
  `lorecraft/errors.py` (once it exists) instead of silent `except Exception`; no new
  `cast(GameContext, ctx)`; one service-wiring style; no new mixed-concern mega-modules.
- Prefer finishing or removing a half-done seam over adding a new one.

## Codebase structure (tier split, 2026-07-05)

The Tier 1/Tier 2/web separation is now physical (branch `tier_split`, CHANGELOG 0.15.0–0.30.0):

- **`src/lorecraft/engine/`** — Tier 1 engine primitives (`game/`, `services/`, `repos/`, `models/`, `clock/`). Runs headless. **Must not import `lorecraft.features` or any web host** — enforced by `tests/unit/test_tier_boundaries.py`. When adding engine code, only depend on other `engine.*`, `lorecraft.types`, stdlib, and third-party.
- **`src/lorecraft/features/<feature>/`** — Tier 2 optional features (24 packages), each an `__init__.py` exporting a `FeatureManifest` (+ `service.py`/`models.py`/`repo.py`/`commands.py`/`conditions.py`/… as needed). Features may import `engine.*` and each other, **never a web host**. New features: add a package with a manifest; it is auto-discovered by `discover_features()`.
- **`src/lorecraft/webui/`** — web hosts: `player/` (player UI) + `admin/` (admin console). The third axis, composing engine + features. May import both; the engine may not import web.
- **Composition layers** (may import both engine and features): `main.py`, `commands/` (shell verbs `meta`/`social`/`news`/`report` + `register_all_commands`), `services/container.py` (`ServiceContainer`).
- Feature verbs live in `features/<x>/commands.py`; the engine owns the `CommandRegistry` mechanism but provides no verbs. See [`docs/tier_split_refactor.md`](docs/tier_split_refactor.md) — the single source of truth — for the remaining (additive, deliberately deferred) work: the `WebHost`/`presentation.py` feature-UI seam and feature enable/disable tests.

## Multi-agent scaffolding (2026-07-06)

For parallel agent work:

- **Worktree isolation:** Each agent gets its own `.venv`, `var/app.sqlite`, and docs copy via `make bootstrap` (first-time setup).
- **Testing:** After `make bootstrap`, activate the worktree's own `.venv` and plain `make test` runs against the worktree's code — no `PYTHONPATH` needed. (The `PYTHONPATH="$PWD/src"` recipe below remains the fallback for un-bootstrapped worktrees.)
- **Commits:** Use conventional-commits (`feat:`, `fix:`, `docs:`) — they will feed the automated release workflow.
- **Version coordination (planned):** A GitHub Action will handle version bumps + CHANGELOG updates on merge to `main`; once it lands, agents stop touching version files. **Until then the manual rule below still applies.**

See [`docs/multi-agent-workflow.md`](docs/multi-agent-workflow.md) for the full design and workflow examples.

## Context strategy

- Start with local files and tests.
- Use Graphify for architecture, impact analysis, dependency paths, and unfamiliar subsystems when graphify-out/graph.json exists.
- After code changes, run `make ai-graph` to refresh graphify-out/graph.json (AST re-extraction, no LLM needed) so the graph doesn't drift.
- Use Ref before changing code that depends on external APIs, libraries, SDKs, or framework behavior.
- Create a new branch for any changes which are large in scope or risky.

## Design principles

- Prefer **data-driven** configuration (world YAML, fixture modules, config files) over
  runtime branching on room names, item IDs, or other world content baked into application code.
- Do not inspect the database for specific room/world IDs to choose behaviour at runtime
  unless there is no practical data source — if you need topology or test content, put it in
  `world_content/` or a dedicated fixture module and load/import it explicitly.
- Avoid **reward hacking** in tests: do not add production special cases solely to make a
  test pass. Tests should set up their own fixtures under `tests/fixtures/` or use imported
  world data (`world_content/world.yaml`); production paths should stay general.
- Keep test-only world content (disambiguation rooms, overlapping item names, etc.) out of
  `src/lorecraft/`. The engine loads world data from YAML/DB, not from pytest helpers.

## Workflow

- Make small, reviewable changes.
- Prefer existing project patterns.
- Type hint all new features; omit hints only when they would be noisy, brittle, or not easily expressible.
- Write unit tests for all new features.
- After new code, run focused verification on modified or new files (see **Testing**).
- Keep `docs/roadmap.md` updated with current implementation progress (it is the single source of truth for what's done and what's next — mark sprint/task checkboxes and update its "Current position" section rather than a separate status doc).
- Keep `docs/user_guide.md` and `docs/admin_builder_guide.md` updated.
- After changing any scripting-vocabulary registration (a `register_spec(...)` call — a new or
  edited condition/effect/behavior-mode descriptor), regenerate the builder-guide reference in
  the **same commit**: `make scripting-docs` (rewrites `docs/scripting_api.md` from the live
  catalog). A CI drift-check (`tests/unit/test_scripting_api_doc.py`) fails the build if it's
  stale — same shape as the `make ai-graph` rule.
- Keep version numbers synchronized in `pyproject.toml` and `src/lorecraft/__init__.py`.
- Follow semver and bump the version with every commit, in the same commit as the change:
  each completed sprint is a minor bump (0.x.0); a bug fix or docs-only change is a patch
  bump (0.x.y). Update `CHANGELOG.md` in lockstep (move `[Unreleased]` content under the new
  dated version heading, per the existing changelog format).
  *(Planned: once the release GitHub Action from `docs/multi-agent-workflow.md` lands, version
  bumping + CHANGELOG move to merge time and this manual rule is retired. Conventional-commit
  titles — `feat:`/`fix:`/`docs:` — are what the action will read, so use them now.)*
- Keep commit messages clean: do **not** add `Co-Authored-By:` or `Claude-Session:`
  (or any similar agent/attribution) trailers to commit messages. Strip them if a
  template or tool would otherwise append them.
- Summarize changed files, risks, and verification.

## Testing

Prefer the Makefile targets so agents pick up the repo's parallel pytest setup and invoke
tools through the active venv (`python -m ...`):

| Target | Command | Notes |
|--------|---------|-------|
| Default suite | `make test` | Parallel (`-n auto --dist=loadfile`); excludes e2e and simulation markers |
| Coverage gate | `make test-cov` | Same parallelism + `--cov=src/lorecraft`; matches CI `quality` job |
| Lint | `make lint` | `ruff check` + `ruff format --check` |
| Types | `make typecheck` | `basedpyright` |
| E2E | `make test-e2e` | Serial; browser tests only |
| Simulation | `make test-simulation` | Serial; live-server harness only |

When you must invoke pytest directly (e.g. a single file or `-k` filter), use the same
parallelism and module invocation — do **not** run bare `pytest`:

```bash
python -m pytest -n auto --dist=loadfile path/to/test_file.py
python -m pytest -n auto --dist=loadfile --cov=src/lorecraft --cov-report=term-missing path/to/test_file.py
```

- `--dist=loadfile` keeps all cases in a file on one worker (required for file-scoped fixtures).
- Override worker count: `PYTEST_WORKERS=4 make test` (default `auto`).
- Requires the dev extra (`pytest-xdist`, `pytest-cov` for coverage runs): `pip install -e ".[dev]"`.
- Do not add `-n` to `make test-e2e` or `make test-simulation`; those targets stay serial.

### Running tests from a git worktree (the PYTHONPATH footgun)

Agents usually work in a `.claude/worktrees/<name>` checkout, and there's a subtle trap
that silently tests the **wrong** source. Two facts cause it:

1. **The `.venv` lives only in the primary working tree (repo root), not in the worktree.**
   So `python` isn't even on `PATH` in a fresh worktree shell until you activate that venv.
2. **That venv's editable install (`pip install -e`) resolves `import lorecraft` to the
   *primary* tree's `src/lorecraft`** — *not* your worktree's. So a bare
   `python -m pytest` (or `make test`) run from a worktree passes/fails against the primary
   tree's code and **your worktree edits are never exercised.** Nothing errors; you just get
   green (or red) for the wrong tree.

**Fix:** activate the primary venv and prepend `PYTHONPATH=<worktree>/src` so imports resolve
to the worktree. Copy-paste recipe that works from *inside* any worktree (no hardcoded paths):

```bash
MAIN=$(dirname "$(git rev-parse --git-common-dir)")   # primary working tree (repo root)
source "$MAIN/.venv/bin/activate"                      # `python`/`pytest` on PATH only after this
PYTHONPATH="$PWD/src" python -m pytest -n auto --dist=loadfile path/to/test_file.py
PYTHONPATH="$PWD/src" python -m basedpyright            # typecheck the worktree too
```

- Confirm you're testing the right tree once: `PYTHONPATH="$PWD/src" python -c "import lorecraft, sys; print(lorecraft.__file__)"`
  must print a path **under your worktree**, not the repo root.
- To use the Makefile targets from a worktree, inject the same var:
  `PYTHONPATH="$PWD/src" make test` (xdist workers inherit the env). `ruff` needs no PYTHONPATH.
- Heavier but foolproof alternative: give the worktree its own venv
  (`python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`); then plain
  `make test` "just works" there. Prefer the `PYTHONPATH` one-liner for quick runs.
- **e2e/live-server tests:** point the app's content mirrors at a temp dir in the fixture
  (`issues_yaml_path`/`news_yaml_path`/`help_yaml_path` → `tmp_path`) so a run can't export
  test data into the repo's `docs/*.yaml`. `PYTHONPATH="$PWD/src"` still applies.

### The shared primary-tree checkout race (git commands, not just Python)

The primary working tree (repo root, `/home/petem/src/Gamedev/lorecraft`) has exactly **one**
working-directory checkout, shared by every concurrent agent session that hasn't been given
its own `.claude/worktrees/<name>` — and even sessions that *have* one will sometimes `cd`
into the primary tree out of habit to run a `git` command. That checkout's HEAD is mutable
shared state: another concurrent session can (and, in practice, will) `git checkout` it to a
different branch between your commands, with no lock and no warning.

**Concretely, this happened:** an agent `cd`'d into the primary tree to commit a
Cogsworth world-content change on `main`, which succeeded. Between that commit and a later
`git merge --ff-only <branch>` run the same way, a *different* concurrent session checked out
`develop` in that same shared directory. The merge command — still reasoning "I'm on main" —
silently fast-forwarded whatever branch happened to be checked out at that moment (`develop`),
not `main`. Nothing errored; `main` was simply left one commit behind, and `develop` gained a
commit nobody intended to put there. Untangling it required read-only forensics (`git reflog`,
`git merge-base --is-ancestor`) to prove no work was lost, then careful, user-confirmed
ref repairs — all avoidable.

**Rule:** never run `git commit` / `merge` / `checkout` / `reset` / `switch` by `cd`-ing into
the primary tree's root directory. This applies even for "just a quick fix-up commit" —
that's exactly the situation that caused the incident above.

**Fix — dedicated scratch worktree.** Any task that needs to read or write a *shared* branch
(typically local `main`) — merging multiple agents' branches together, bumping the version,
moving a `CHANGELOG.md` entry under a dated heading — should do it in its own disposable
worktree, never the primary tree's checkout:

```bash
git worktree add /tmp/<scratch-name> main   # isolated checkout of main, no race possible
cd /tmp/<scratch-name>
# ... do the integration work, commit directly (this *is* main — no separate merge step needed) ...
cd - && git worktree remove /tmp/<scratch-name>   # clean up when done
```

Git itself enforces one useful safety rail here: it refuses to check out (or `branch -f`) a
branch that's already checked out somewhere else. Treat that refusal as a signal that another
session is using it — don't force past it (`git worktree remove --force`, `branch -f` from
elsewhere) without confirming with the user first, since the branch pointer may be something
another concurrent agent is actively relying on.

**Version-bump collisions are a related, accepted risk.** Two branches built concurrently by
different sessions can independently claim the same "next" version number (each is blind to
the other's in-flight work) — this has happened in practice (two unrelated branches both
claiming `v0.76.0`). It's not something a single agent can prevent unilaterally; whoever
integrates/merges those branches together is the one who discovers and resolves the collision
by renumbering one of them. Don't try to pre-empt it by scanning every open branch before every
bump — just bump against your own branch's ancestry, and expect the integrator to reconcile.
