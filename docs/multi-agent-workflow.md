# Multi-Agent Workflow & Scaffolding

This document describes the scaffolding and coordination strategy for parallel agent work in lorecraft.

## Agent Roles

Role-specific subagent definitions live in `.claude/agents/` (name, model, tool access, and
system prompt per role). An Orchestrator fields requests and routes to the specialists below;
specialists report back in the structured formats their own definition specifies.

| Agent | File | Model | Owns |
|---|---|---|---|
| Orchestrator | `.claude/agents/orchestrator.md` | sonnet | Decomposition, routing, validation |
| Research & Planning | `.claude/agents/research-planner.md` | opus | Precedent search, roadmap fit, risk flags |
| Backend Engineer | `.claude/agents/backend-engineer.md` | opus | Engine/feature Python, tier boundaries |
| Frontend Specialist | `.claude/agents/frontend-specialist.md` | sonnet | HTMX/Alpine/Tailwind webui |
| Test & QA | `.claude/agents/test-qa.md` | haiku | Running suites, structured pass/fail |
| Docs Writer | `.claude/agents/docs-writer.md` | sonnet | user_guide/admin_guide/roadmap/CHANGELOG entries |
| Integrator | `.claude/agents/integrator.md` | haiku | Version bump, CHANGELOG dated headings, merge/tag |

Only the Integrator touches version files and dated `CHANGELOG.md` headings — every other
agent leaves those alone, consistent with the version/changelog coordination model below.

## Worktree Bootstrap

Each agent spawns in an isolated `git worktree` with its own Python venv, database, and docs fixtures.

### Setup (Automatic)

`.claude/hooks/session-start.sh` launches `scripts/bootstrap-worktree.sh` in the
**background** (non-blocking) on every session start, so session start never waits
on `pip install`. The script is idempotent — safe to fire every session:

- **`.venv/`** — isolated Python environment; skipped if it already resolves
  `import lorecraft` to this worktree (fast path once bootstrapped)
- **`var/app.sqlite`** — empty database; **never recreated** if it already exists
  (may hold in-progress session state)
- **`docs/*.yaml`** — copy of world YAML fixtures from the primary tree; refreshed
  every run (cheap, non-destructive)
- **`.env.local`** — per-worktree config (from `.env.example`); only seeded if absent

It never runs in the primary tree (which already has its own venv) — the hook
checks that `.git` is a file, which is only true in a linked worktree.

Progress is logged to `var/bootstrap.log`; current state is one word (plus a reason
on failure) in `var/bootstrap-status`: `running`, `ready`, or `failed: <reason>`.

### Manual invocation

Still available as an escape hatch — to force a fixture refresh mid-session, retry
after a failure, or bootstrap a worktree the hook hasn't reached yet:

```bash
make bootstrap
# or equivalently:
./scripts/bootstrap-worktree.sh
```

### Waiting for background bootstrap

Don't assume the venv is ready just because a session has started — poll the status
file, with a fallback to kicking it off yourself if the hook hasn't fired (e.g. a
worktree that predates this setup):

```bash
for _ in $(seq 1 30); do
  status=$(cat var/bootstrap-status 2>/dev/null || echo missing)
  case "$status" in
    ready) break ;;
    failed*) echo "$status — see var/bootstrap.log"; break ;;
    running) sleep 3 ;;
    missing) bash scripts/bootstrap-worktree.sh >/dev/null 2>&1 & sleep 3 ;;
  esac
done
```

### Verification

Confirm the worktree is set up correctly:

```bash
source .venv/bin/activate
python -c "import lorecraft; print(lorecraft.__file__)"
# Must print a path under this worktree, not under the primary tree
```

If status is `failed` or the wait above times out, fall back to the
`PYTHONPATH` borrow-trick below rather than blocking on a broken bootstrap.

## Testing from a Worktree

Once bootstrap is `ready` (auto-triggered, or run manually), the worktree's own
`.venv` has an editable install of the worktree's source, so the plain Makefile
targets work with no `PYTHONPATH` tricks:

```bash
source .venv/bin/activate
make test                              # unit tests
make test-cov                          # + coverage gate
make test-e2e                          # e2e (re-syncs docs/*.yaml from primary first)
make typecheck
```

**Fallback (un-bootstrapped worktree):** borrow the primary venv and redirect imports —
see "Running tests from a git worktree" in AGENTS.md:

```bash
MAIN=$(dirname "$(git rev-parse --git-common-dir)")
source "$MAIN/.venv/bin/activate"
PYTHONPATH="$PWD/src" make test
```

## Branching & Commits

### Per-Agent Workflow

1. **Create worktree** (system/user, not agent):
   ```bash
   # Harness creates via EnterWorktree(name="feature-xyz")
   # Agent lands on branch feature/xyz (from origin/main)
   ```

2. **Rebase from origin/main** (agent):
   ```bash
   git fetch origin main && git rebase origin/main
   ```

3. **Work in feature branch** (agent):
   ```bash
   git commit -m "feat(area): description"  # conventional-commit format
   git commit -m "fix(area): another fix"
   ```

4. **Create PR** (agent, programmatically):
   ```bash
   gh pr create --title "..." --body "$(cat <<'EOF'
   ...
   EOF
   )"
   ```

5. **Commit locally, push branch** (agent):
   ```bash
   git push origin feature/xyz
   ```

6. **User merges PR** (manual or auto-merge) to `main`.

### Commit Message Format

Use **conventional-commits** to enable automated version bumping:

- `feat(area): description` → triggers minor version bump
- `fix(area): description` → triggers patch version bump
- `docs: description` → triggers patch version bump
- `refactor(area): description` → no version bump
- `chore: description` → no version bump

Enforce locally with a pre-commit hook (optional but recommended):

```bash
git config core.hooksPath .githooks
```

## Version & Changelog Coordination

### Problem

Multiple agents commit to different branches. When PRs merge, version files (`pyproject.toml`, `src/lorecraft/__init__.py`) and `CHANGELOG.md` would conflict if agents tried to update them.

**Solution:** Single authoritative point of coordination.

### Automatic Release (GitHub Action) — *planned, not yet implemented*

Until this action lands, the manual per-commit version-bump rule in AGENTS.md remains in force.

On every merge to `main`, a GitHub Action runs:

1. **Fetches all commits** since the last version tag
2. **Counts commit types:**
   - `feat:` commits → minor bump (e.g., 0.42.0 → 0.43.0)
   - `fix:` + `docs:` commits → patch bump (e.g., 0.42.0 → 0.42.1)
3. **Updates CHANGELOG.md:**
   - Moves `[Unreleased]` section → new dated section with version
   - Lists all commits by category
4. **Updates version files:**
   - `pyproject.toml` → `version = "0.43.0"`
   - `src/lorecraft/__init__.py` → `__version__ = "0.43.0"`
5. **Commits & tags:**
   ```
   chore: release v0.43.0
   ```

**Agents never touch version files.** The workflow is:

```
agent commit feat(...) → push → PR → merge to main → Action updates version+tag
```

## Directory Structure

```
.claude/worktrees/
  feature-xyz/              ← agent's worktree
    .venv/                  ← isolated Python (per-worktree)
    var/
      app.sqlite            ← isolated database
    docs/
      world.yaml            ← copy from primary tree
      issues.yaml
      help.yaml
    .env.local              ← per-worktree config
    src/
      lorecraft/            ← agent's code edits
    tests/
      ...

src/lorecraft/             ← primary source tree (shared)
```

**Key:** `.venv`, `var/app.sqlite`, `.env.local` are **not shared** between worktrees.

## Makefile Targets

| Target | When | Notes |
|--------|------|-------|
| `make bootstrap` | Manual worktree setup/re-sync | Normally auto-triggered in the background by `session-start.sh`; idempotent — creates venv/db/.env.local if missing, always refreshes docs copy |
| `make test` | Run unit tests | Uses whichever venv is active |
| `make test-cov` | Unit tests + coverage gate | Required before PR merge |
| `make test-e2e` | Browser e2e tests | Re-syncs docs/*.yaml from primary tree when run in a worktree |
| `make lint` | Lint checks | |
| `make typecheck` | Type checking (basedpyright) | |
| `make ai-graph` | Update architecture graph | For impact analysis |

## Example: Agent Workflow

```bash
# System/user: create worktree
EnterWorktree(name="feature-scavenger-hunts")
# → worktree on branch feature/scavenger-hunts from origin/main
# → session-start.sh already kicked off bootstrap in the background

# Agent: wait for background bootstrap (see "Waiting for background bootstrap" above),
# falling back to `make bootstrap` directly if var/bootstrap-status is missing/failed
cd /path/to/worktree
source .venv/bin/activate

# Agent: verify isolation
python -c "import lorecraft; print(lorecraft.__file__)"   # must print a worktree path

# Agent: rebase from main
git fetch origin main && git rebase origin/main

# Agent: work
make test                # run tests
# ... edit code, commit ...
git commit -m "feat(hunts): event scheduling logic"
git commit -m "feat(hunts): UI markers for active events"
make test-cov            # final coverage check

# Agent: push & PR
git push origin feature/scavenger-hunts
gh pr create --title "Scavenger hunt events" --body "..."

# User: merge
# (clicks merge on GitHub, or action auto-merges)
# → GitHub Action runs: detects 2 feat: commits → 0.42.0 → 0.43.0
#                        updates CHANGELOG.md + version files
#                        commits + tags v0.43.0
```

## FAQ

**Q: Can I share the `.venv` across worktrees?**
A: No. An editable install (`pip install -e .`) points at exactly one tree, so a shared venv silently tests the wrong source. Bootstrap (auto-triggered by `session-start.sh`, or run manually via `make bootstrap`) gives each worktree its own venv; the `PYTHONPATH` fallback exists only if bootstrap hasn't completed yet.

**Q: What if docs/*.yaml change while I'm testing?**
A: `make test-e2e` syncs from the primary tree before running. Unit tests use whatever copy is currently in `docs/` — bootstrap refreshes it every time it runs (every session, in the background), so it's rarely more than one session stale; force an immediate refresh with `make bootstrap`.

**Q: Why doesn't bootstrap just block session start until it's done?**
A: `pip install -e ".[dev]"` can take well over a minute on a cold cache — blocking every session on that (including sessions that never touch Python) is a worse trade than a short poll-and-wait the first time an agent actually needs the venv. See "Waiting for background bootstrap" above.

**Q: How do agents coordinate if they're on parallel branches?**
A: They don't need to. Each agent:
- Works on its own feature branch
- Has its own worktree (isolated db, venv, docs)
- Creates its own PR
- The release bot handles version coordination at merge time

**Q: What if two PRs merge at the same time?**
A: The GitHub Action is atomic. It processes all commits since the last tag in one run, calculates a single version bump, and commits once. Later runs see the new tag and skip those commits.

**Q: Can I test my changes against the "real" game state (primary db)?**
A: Not recommended. Use fixtures (`world_content/`) or setup in tests. The isolation is intentional — agents shouldn't affect each other's work. For integration testing, that's what e2e tests do (they set up their own state).
