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

## Context strategy

- Start with local files and tests.
- Use Graphify for architecture, impact analysis, dependency paths, and unfamiliar subsystems when graphify-out/graph.json exists.
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
- Keep `CHANGELOG.md` updated with meaningful, user-visible changes.
- Keep `docs/user_guide.md` and `docs/admin_builder_guide.md` updated.
- Keep version numbers synchronized in `pyproject.toml` and `src/lorecraft/__init__.py`.
- Follow semver and bump the version with every commit, in the same commit as the change:
  each completed sprint is a minor bump (0.x.0); a bug fix or docs-only change is a patch
  bump (0.x.y). Update `CHANGELOG.md` in lockstep (move `[Unreleased]` content under the new
  dated version heading, per the existing changelog format).
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
