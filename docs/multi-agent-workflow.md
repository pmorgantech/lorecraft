# Multi-Agent Workflow & Scaffolding

This document describes the scaffolding and coordination strategy for parallel agent work in lorecraft.

## Worktree Bootstrap

Each agent spawns in an isolated `git worktree` with its own Python venv, database, and docs fixtures.

### Setup (First-Time)

When an agent enters a worktree, it runs:

```bash
make bootstrap
```

or equivalently:

```bash
./scripts/bootstrap-worktree.sh
```

This creates:

- **`.venv/`** — isolated Python environment (never shared with primary tree or other worktrees)
- **`var/app.sqlite`** — empty database for this agent's isolation
- **`docs/*.yaml`** — copy of world YAML fixtures from primary tree (read-only snapshots)
- **`.env.local`** — per-worktree config (from `.env.example` template)

### Verification

Confirm the worktree is set up correctly:

```bash
source .venv/bin/activate
python -c "import lorecraft; print(lorecraft.__file__)"
# Must print a path under this worktree, not under the primary tree
```

## Testing from a Worktree

After `make bootstrap`, the worktree's own `.venv` has an editable install of the
worktree's source, so the plain Makefile targets work with no `PYTHONPATH` tricks:

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
| `make bootstrap` | First-time worktree setup | Creates venv, db, .env.local, docs copy |
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

# Agent: setup
cd /path/to/worktree
make bootstrap
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
A: No. An editable install (`pip install -e .`) points at exactly one tree, so a shared venv silently tests the wrong source. `make bootstrap` gives each worktree its own venv; the `PYTHONPATH` fallback exists only for un-bootstrapped worktrees.

**Q: What if docs/*.yaml change while I'm testing?**
A: `make test-e2e` syncs from the primary tree before running. Unit tests use their copy (created at bootstrap); if you need fresh fixtures, re-run `make bootstrap`.

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
