# Repository agent instructions

## Current focus: foundation before features (2026-07-01)

The core engine must be very well designed, well tooled, well tested, and internally
consistent **before** expanding commands or adding combat/trading/PvP. Do not skimp on
code design and quality.

- `CODE_AUDIT.md` findings + the `docs/project/roadmap.md` foundation band (Sprints 5–15) are the
  active work queue. Feature sprints (16+) are gated behind the roadmap's foundation exit criteria.
- When touching code, leave it more consistent than found: typed errors from
  `lorecraft/errors.py` instead of silent `except Exception`; no new `cast(GameContext, ctx)`;
  one service-wiring style; no new mixed-concern mega-modules.
- Prefer finishing or removing a half-done seam over adding a new one.

## Codebase structure (tier split, 2026-07-05)

The Tier 1/Tier 2/web separation is now physical (branch `tier_split`, CHANGELOG 0.15.0–0.30.0):

- **`src/lorecraft/engine/`** — Tier 1 engine primitives (`game/`, `services/`, `repos/`, `models/`, `clock/`). Runs headless. **Must not import `lorecraft.features` or any web host** — enforced by `tests/unit/test_tier_boundaries.py`. When adding engine code, only depend on other `engine.*`, `lorecraft.types`, stdlib, and third-party.
- **`src/lorecraft/features/<feature>/`** — Tier 2 optional features (33 packages), each an `__init__.py` exporting a `FeatureManifest` (+ `service.py`/`models.py`/`repo.py`/`commands.py`/`conditions.py`/… as needed). Features may import `engine.*` and each other, **never a web host**. New features: add a package with a manifest; it is auto-discovered by `discover_features()`.
- **`src/lorecraft/webui/`** — web hosts: `player/` (player UI) + `admin/` (admin console). The third axis, composing engine + features. May import both; the engine may not import web.
- **Composition layers** (may import both engine and features): `main.py`, `commands/` (shell verbs `meta`/`social`/`news`/`report` + `register_all_commands`), `services/container.py` (`ServiceContainer`).
- Feature verbs live in `features/<x>/commands.py`; the engine owns the `CommandRegistry` mechanism but provides no verbs. See [`docs/archive/tier_split_refactor.md`](docs/archive/tier_split_refactor.md) — the single source of truth — for the remaining (additive, deliberately deferred) work: the `WebHost`/`presentation.py` feature-UI seam and feature enable/disable tests.

## Multi-agent scaffolding (2026-07-06)

For parallel agent work:

- **Worktree isolation:** Each agent gets its own `.venv`, `var/app.sqlite`, and docs copy via `make bootstrap` (first-time setup).
- **Codex worktrees:** Codex-created worktrees are not guaranteed to have the background
  `.claude` session bootstrap. Before running tests in a freshly created Codex worktree,
  run `make bootstrap` from that worktree and allow network access if dependency install
  needs it. Confirm `.venv/bin/python -c "import lorecraft; print(lorecraft.__file__)"`
  resolves under the worktree before trusting test output.
- **Testing:** After `make bootstrap`, activate the worktree's own `.venv` and plain `make test` runs against the worktree's code — no `PYTHONPATH` needed. (The `PYTHONPATH="$PWD/src"` recipe below remains the fallback for un-bootstrapped worktrees.)
- **Commits:** Use conventional-commits (`feat:`, `fix:`, `docs:`) — they will feed the automated release workflow.
- **Version coordination (planned):** A GitHub Action will handle version bumps + CHANGELOG updates on merge to `main`; once it lands, agents stop touching version files. **Until then the manual rule below still applies.**

See [`docs/project/multi-agent-workflow.md`](docs/project/multi-agent-workflow.md) for the full design and workflow examples.

## Context strategy

- Start with local files and tests.
- Use Ref before changing code that depends on external APIs, libraries, SDKs, or framework behavior.
- Create a new branch for any changes which are large in scope or risky.

## Code intelligence — CodeGraph-first exploration (2026-07-19)

**All code exploration queries should use CodeGraph MCP (`codegraph_explore` tool) as the primary strategy, falling back to grep/read only when CodeGraph cannot answer the question.** The index is live (updated on every code change via `graph-refresh.sh` hook) and sub-millisecond — it's faster and more accurate than recursive grep or manual file reads.

**When to use `codegraph_explore` (MCP tool):**
- Multi-file queries: "what functions call X?", "where is Y defined?", "what imports Z?"
- Architecture questions: "what depends on this module?", "what's the call chain from A to B?"
- Impact analysis: "if I change X, what breaks?", "who calls this function?"
- Any question naming symbols, files, or architectural boundaries

**When grep/read is acceptable (no MCP call needed):**
- Verifying your own edits or checking a file you just modified
- Reading test output or logs
- Reading static documentation or non-code files
- One-off syntax checks or inline searches within files you already have open

**Useful MCP query patterns:**
- `codegraph_explore` with natural language: `"Where is the GameContext class used?"`
- `codegraph_explore` with symbol names: `"parser, execute_command, CommandRegistry"`
- Shell fallback (if MCP tool unavailable): `codegraph explore "<question>"`

**Shell commands (MCP unavailable fallback):**
- `codegraph explore "<question>"` — natural language query
- `codegraph node <symbol-or-file>` — inspect a specific symbol/file
- `codegraph callers <symbol>` — who calls this?
- `codegraph callees <symbol>` — what does this call?
- `codegraph impact <symbol>` — what depends on this?
- `codegraph affected <changed-files>` — what files are impacted by these changes?
- `codegraph status` — check index freshness

Treat CodeGraph as derived data. Never commit `.codegraph/`.
Run `make ai-graph` when an explicit incremental refresh is needed (typically not required — the hook keeps it live).

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

### Tier 1 = mechanism, Tier 2 = policy (2026-07-12)

Beyond the import-direction rule in "Codebase structure" above, the tiers also split by
**who decides what a behavior actually does**:

- **Tier 1 (`engine/`) provides unopinionated functionality and hooks.** It knows _how_ to do
  a class of thing — apply a delta to a player's stats, resolve a modifier stack, detect a
  threshold crossing — but never _what_ that thing should be for any particular feature. A
  Tier 1 function that hardcodes "leveling grants coins and skill points" has leaked policy
  into the mechanism layer; it should instead expose a generic "apply this delta" primitive
  and let a Tier 2 caller decide the delta's contents.
- **Tier 2 (`features/<x>/`) is the malleable, opinionated layer.** It is where a specific
  feature tells a Tier 1 mechanism what to actually do — quest rewards, economy pricing, XP
  curves and level-up payouts, skill-tree costs. This is also where that opinion should be
  **data-driven** per the bullets above: expressed in `world_content/` YAML or a DB-backed
  config row, not a Python constant, so it can be re-authored without a code change.
- When planning or reviewing a design, state explicitly which parts are Tier 1 (the hook/
  primitive) and which are Tier 2 (the opinion/config feeding it) — don't leave this implicit.
  A design that can't be split this way cleanly is a sign the mechanism is still coupled to
  one feature's assumptions and should be generalized before a second feature needs the same
  hook with different opinions.

### Prefer live-tunable configuration where sensible (2026-07-12)

Data-driven (previous section) is necessary but not sufficient — YAML-authored config that
only takes effect after a world reseed (`economy.regions` in `world_content/world.yaml` is
the current example) still requires a deploy-like action to change. Where a value is a game-
balance dial an admin would plausibly want to retune without restarting or reseeding the
server — reward amounts, pricing multipliers, XP curves — prefer the **live-tunable** pattern
already established by `WorldClock` (`webui/admin/routers/clock.py`): a DB-backed singleton,
optionally YAML-seeded for initial authoring, exposed through an admin endpoint that mutates
the DB row _and_ pushes the new value into the running server state in the same call, so the
change is live with no restart. Not every config value needs this — static world topology or
one-time content doesn't — but default to asking "would an admin want to change this live?"
rather than assuming YAML + reseed is always enough. (`economy.regions` is a known gap here —
currently reseed-only — flagged in `docs/project/roadmap.md`'s backlog as a candidate for this pattern.)

## Workflow

- Make small, reviewable changes.
- Prefer existing project patterns.
- Type hint all new features; omit hints only when they would be noisy, brittle, or not easily expressible.
- Write unit tests for all new features.
- After new code, run focused verification on modified or new files (see **Testing**).
- Keep `docs/project/roadmap.md` updated with current implementation progress (it is the single source of truth for what's done and what's next — mark sprint/task checkboxes and update its "Current position" section rather than a separate status doc).
- Keep `docs/guides/user_guide.md` and `docs/worldbuilding/admin_builder_guide.md` updated.
- After changing any scripting-vocabulary registration (a `register_spec(...)` call — a new or
  edited condition/effect/behavior-mode descriptor), regenerate the builder-guide reference in
  the **same commit**: `make scripting-docs` (rewrites `docs/worldbuilding/scripting_api.md` from the live
  catalog). A CI drift-check (`tests/unit/test_scripting_api_doc.py`) fails the build if it's
  stale — same shape as the `make ai-graph` rule.
- Keep version numbers synchronized in `pyproject.toml` and `src/lorecraft/__init__.py`.
- Follow semver and bump the version with every commit, in the same commit as the change:
  each completed sprint is a minor bump (0.x.0); a bug fix or docs-only change is a patch
  bump (0.x.y). Update `CHANGELOG.md` in lockstep (move `[Unreleased]` content under the new
  dated version heading, per the existing changelog format).
  _(Planned: once the release GitHub Action from `docs/project/multi-agent-workflow.md` lands, version
  bumping + CHANGELOG move to merge time and this manual rule is retired. Conventional-commit
  titles — `feat:`/`fix:`/`docs:` — are what the action will read, so use them now.)_
- Keep commit messages clean: do **not** add `Co-Authored-By:` or `Claude-Session:`
  (or any similar agent/attribution) trailers to commit messages. Strip them if a
  template or tool would otherwise append them.
- Summarize changed files, risks, and verification.

## Testing

Prefer the Makefile targets so agents pick up the repo's parallel pytest setup and invoke
tools through the active venv (`python -m ...`):

| Target        | Command                | Notes                                                                                                                                                              |
| ------------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Default suite | `make test`            | Parallel (`-n auto --dist=loadfile`); excludes e2e and simulation markers                                                                                          |
| Coverage gate | `make test-cov`        | Same parallelism + `--cov=src/lorecraft`; matches CI `quality` job                                                                                                 |
| Lint          | `make lint`            | `ruff check` + `ruff format --check`                                                                                                                               |
| Types         | `make typecheck`       | `basedpyright`                                                                                                                                                     |
| E2E           | `make test-e2e`        | Parallel (`-n auto --dist=loadfile`, since `a7f76b4`) — each worker gets its own isolated browser + server (random port, unique `tmp_path` DB); browser tests only |
| Simulation    | `make test-simulation` | Serial; live-server harness only                                                                                                                                   |

**Lint/format are hook-owned, not agent-owned (2026-07-18).** A `PostToolUse` hook
(`.claude/hooks/format-lint.sh`) already runs `ruff format` + `ruff check --fix` on every
Edit/Write to a `.py` file, in real time, at zero token cost, and prints any remaining
non-autofixable finding straight back to the editing agent in the same turn. Do not run
`ruff`/`make lint` yourself mid-task, and do not ask another agent to — fix whatever the hook
already handed you and move on. `make lint` still exists as a pre-merge/CI-parity safety net
(Test & QA can be dispatched to it explicitly), but a clean run is the expected default now, not
something to proactively verify. `make typecheck` (basedpyright) has no hook equivalent and
stays a real, necessary verification step.

### Agent dispatch and lane discipline live in the orchestration skill

Which specialist to dispatch, backend/test-writer/QA lane discipline (including the narrow
`cargo check`/`--collect-only` compile-sanity carve-outs), Test & QA's lane table (split by
language: `test-qa-python` for `py-*`, `test-qa-rust` for `rust-*`), when to run a narrow lane vs.
a full gate, and parallel-dispatch rules are all owned by the `lorecraft-orchestration` skill
(`.claude/skills/lorecraft-orchestration/SKILL.md`) — that skill is the source of truth for
orchestration policy, not this file. Invoke it for genuinely multi-domain, risky, or
multi-specialist work; it also documents when *not* to bother (a small single-file edit doesn't
need dispatch — just do it).

This file stays general: repo conventions, testing commands/mechanics, and cross-session git
safety below apply whether or not a task is being orchestrated at all.

### Invoking pytest directly

When you must invoke pytest directly (e.g. a single file or `-k` filter), use the same
parallelism and module invocation — do **not** run bare `pytest`:

```bash
python -m pytest -n auto --dist=loadfile path/to/test_file.py
python -m pytest -n auto --dist=loadfile --cov=src/lorecraft --cov-report=term-missing path/to/test_file.py
```

- `--dist=loadfile` keeps all cases in a file on one worker (required for file-scoped fixtures).
- Override worker count: `PYTEST_WORKERS=4 make test` (default `auto`).
- Requires the dev extra (`pytest-xdist`, `pytest-cov` for coverage runs): `pip install -e ".[dev]"`.
- `make test-e2e` already runs `-n $(PYTEST_WORKERS) --dist=loadfile` (parallel) — don't assume
  it's serial or route around it. It's capped well below available cores by file count, though:
  15 e2e files means at most 15 concurrent workers regardless of `PYTEST_WORKERS`/core count.
  Splitting an oversized e2e file (e.g. one bundling 10+ tests) raises this ceiling the same way
  the 2026-07-05 unit-test split did — a Pytest Writer task, not something to do ad hoc.
- Do not add `-n` to `make test-simulation`; that target stays genuinely serial (live-server
  harness, no per-test isolation to safely parallelize against).

### Running tests from a git worktree (use the worktree's own venv, not a PYTHONPATH hack)

Every session running inside a `.claude/worktrees/<name>` checkout gets its own isolated `.venv`
**automatically**: `session-start.sh` fires `bash scripts/bootstrap-worktree.sh` in the background
the instant the session starts (idempotent — safe to fire repeatedly; see the script). Codex
worktrees do **not** necessarily get that automatic background setup, so run `make bootstrap`
manually in a new Codex worktree before tests; if dependency installation fails with DNS/network
errors, rerun the same bootstrap with network access rather than falling back to a different
venv. That venv's editable install resolves `import lorecraft` to **that worktree's**
`src/lorecraft`, not the primary tree's.

**Use it directly — this is the default, not a fallback:**

```bash
.venv/bin/python -m pytest -n auto --dist=loadfile path/to/test_file.py
.venv/bin/python -m basedpyright
# or: source .venv/bin/activate — then plain `python`/`pytest`/`make test` all resolve correctly
```

- Bootstrap runs in the background, so confirm it finished before trusting a result:
  `cat var/bootstrap-status` should read `ready` (starts as `running`). If the file/venv is
  missing entirely, run `make bootstrap` yourself — idempotent, worktree-scoped, and refuses to
  run from the primary tree by design.
- Confirm you're testing the right tree once: `.venv/bin/python -c "import lorecraft; print(lorecraft.__file__)"`
  must print a path **under your worktree**, not the repo root.
- Once bootstrapped, plain `make test` / `make lint` / `make typecheck` just work against the
  worktree's own code — no extra flags, no `PYTHONPATH`.

**Only fall back to `PYTHONPATH="$PWD/src"` + primary-venv-activation for a genuinely
un-bootstrapped location** — e.g. an ad hoc `/tmp/<scratch>` worktree created for a one-off git
operation that unexpectedly also needs to run Python (rare; most scratch worktrees are git-only
and never touch Python). This recipe is fragile in practice — easy to activate the wrong venv or
drop the `PYTHONPATH` prefix on one command in a chain and silently test the primary tree instead
with no error — so prefer bootstrapping the location instead when Python work is actually needed
there:

```bash
MAIN=$(dirname "$(git rev-parse --git-common-dir)")
source "$MAIN/.venv/bin/activate"
PYTHONPATH="$PWD/src" python -m pytest -n auto --dist=loadfile path/to/test_file.py
```

- **e2e/live-server tests:** point the app's content mirrors at a temp dir in the fixture
  (`issues_yaml_path`/`news_yaml_path`/`help_yaml_path` → `tmp_path`) so a run can't export
  test data into the repo's `docs/*.yaml`.

### The shared primary-tree checkout race (git commands, not just Python)

The primary working tree (repo root, `/home/petem/src/Gamedev/lorecraft`) has exactly **one**
working-directory checkout, shared by every concurrent agent session that hasn't been given
its own `.claude/worktrees/<name>` — and even sessions that _have_ one will sometimes `cd`
into the primary tree out of habit to run a `git` command. That checkout's HEAD is mutable
shared state: another concurrent session can (and, in practice, will) `git checkout` it to a
different branch between your commands, with no lock and no warning.

**Concretely, this happened:** an agent `cd`'d into the primary tree to commit a
Cogsworth world-content change on `main`, which succeeded. Between that commit and a later
`git merge --ff-only <branch>` run the same way, a _different_ concurrent session checked out
`develop` in that same shared directory. The merge command — still reasoning "I'm on main" —
silently fast-forwarded whatever branch happened to be checked out at that moment (`develop`),
not `main`. Nothing errored; `main` was simply left one commit behind, and `develop` gained a
commit nobody intended to put there. Untangling it required read-only forensics (`git reflog`,
`git merge-base --is-ancestor`) to prove no work was lost, then careful, user-confirmed
ref repairs — all avoidable.

**Rule:** never run `git commit` / `merge` / `checkout` / `reset` / `switch` by `cd`-ing into
the primary tree's root directory. This applies even for "just a quick fix-up commit" —
that's exactly the situation that caused the incident above.

**Fix — dedicated scratch worktree.** Any task that needs to read or write a _shared_ branch
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

**The routine case — `main` refuses because it's simply resting in the primary tree, not
because a concurrent session diverted it.** `main`'s normal resting state _is_ checked out in
the primary tree, so `git worktree add <scratch> main` fails on essentially every integration,
not just the rare concurrent-session collision above. For exactly this routine case, the user
has pre-approved (2026-07-13) a standing, narrowly-scoped resolution that does not require
asking each time: a single atomic, pre/post-verified command run against the primary tree's
_path_, without `cd`-ing into it and without any other command in between:

```bash
git -C <primary-tree-path> branch --show-current   # verify: must print "main"
git -C <primary-tree-path> status --short           # verify: must be empty (clean)
git -C <primary-tree-path> merge --ff-only <scratch-branch>
git -C <primary-tree-path> rev-parse main           # verify: must equal the new commit
git -C <primary-tree-path> symbolic-ref -q HEAD     # verify: prints refs/heads/main, not empty
```

**This is narrowly scoped — it is not a general license to reach for `git -C`/`cd` whenever
some other command is blocked.** If the refusal instead looks like a _different_ concurrent
session has `main` (or any branch) checked out somewhere unexpected — not simply the primary
tree's normal resting state — that is still the "stop and confirm with the user" case above,
not this one. And if a command is denied by the harness's own permission-classifier (a tool-use
block, not a git-level "already checked out" conflict), that is a different failure mode
entirely: never substitute `git -C`, a literal `cd`, or any other command to reach the identical
outcome — report the block and let the user decide. See the Integrator/Orchestrator agent
definitions' "permission-classifier blocks are stop signals, not routing problems" for the
2026-07-13 incident where conflating these two cases — treating a permission denial as if it
were the routine "main is resting in the primary tree" case — was the actual violation, and
don't repeat that conflation in the other direction either.

**Version-bump collisions are a related, accepted risk.** Two branches built concurrently by
different sessions can independently claim the same "next" version number (each is blind to
the other's in-flight work) — this has happened in practice (two unrelated branches both
claiming `v0.76.0`). It's not something a single agent can prevent unilaterally; whoever
integrates/merges those branches together is the one who discovers and resolves the collision
by renumbering one of them. Don't try to pre-empt it by scanning every open branch before every
bump — just bump against your own branch's ancestry, and expect the integrator to reconcile.

### The shared _designated_ worktree race — a second, distinct failure mode (2026-07-12)

The primary-tree race above is well-known; this is a related but separate trap that bit
multiple sub-agents across the Sprint 71/72 work: **a session's own `.claude/worktrees/<name>`
checkout is not automatically safe just because it isn't the primary tree.**

**What happens:** an orchestrator (or a user directly) dispatches several sub-agents in the
same session — e.g. four parallel Sprint 72 tasks. Each dispatched agent's shell defaults to
the _same_ designated worktree directory unless told otherwise. If two or more of those agents
run concurrently (or even just interleaved — one finishes a tool call, another's turn runs a
`git checkout` in between), the directory's checked-out branch gets switched out from under
whichever agent thinks it's still on its own branch. This happened repeatedly and independently
across at least three different sub-agents in one session (each noticed its `HEAD`/branch had
changed mid-task, sometimes multiple times) — not a one-off, but the _default_ outcome of
dispatching parallel agents into a shared worktree without explicit isolation.

**Rule for anyone dispatching sub-agents that will edit files or run git commands (Orchestrator,
or a top-level session doing this directly):** if more than one such agent may run with any
overlap — parallel dispatch, or even sequential dispatch where you can't guarantee the first
fully finished including its commit before the second starts — give each one its **own**
disposable scratch worktree, not the shared session directory:

```bash
git worktree add /tmp/<task-name> <base-branch-or-commit>   # isolated, no race possible
# ... agent does all its work here, commits to its own branch ...
git worktree remove /tmp/<task-name>   # clean up once merged/no longer needed
```

**Rule for any agent working in a worktree, even one it believes is exclusively its own:**
verify before trusting it — `pwd` and `git branch --show-current`/`git log -1` — immediately
before any edit or commit, not just once at the start of the task. A shared directory's branch
can change _between_ your own tool calls, not just between sessions. If it doesn't match what
you expect, stop and create your own scratch worktree rather than proceeding on an assumption.

**This compounds with venv isolation above.** A `.claude/worktrees/<name>` _session_ worktree
already got its `.venv` bootstrapped automatically at session start (see above) — no action
needed there. A `/tmp/<scratch>` worktree created ad hoc for a git operation does **not** get
that treatment (`session-start.sh` never fires there); if one of those unusually also needs to
run Python, run `make bootstrap` in it explicitly rather than reaching for `PYTHONPATH` by
habit. Confirm the resolved `lorecraft.__file__` path points under _that specific worktree_, not
the primary tree or a different worktree, before trusting any test result run there — the
failure mode ("green/red for the wrong tree") is silent either way.
