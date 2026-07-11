#!/usr/bin/env bash
# Bootstrap script for agent worktrees: isolated venv, database, and docs.
# Usage: ./scripts/bootstrap-worktree.sh   (or: make bootstrap)
#
# Idempotent — safe to run repeatedly (e.g. fired automatically, in the
# background, by .claude/hooks/session-start.sh on every session start):
#   - venv: skipped if it already resolves `import lorecraft` to THIS worktree
#   - database: never touched if var/app.sqlite already exists (may hold
#     in-progress session state)
#   - docs fixtures: always refreshed from the primary tree (cheap, safe)
#   - .env.local: only seeded if absent (never clobbers local overrides)
#
# Writes progress to var/bootstrap.log and status to var/bootstrap-status
# (running / ready / failed: <reason>) so other processes/agents can poll
# without blocking on this script directly.

MAIN=$(dirname "$(git rev-parse --git-common-dir)")
WORKTREE="$PWD"

if [ "$MAIN" = "$WORKTREE" ]; then
    echo "❌ Error: run this from a worktree, not the primary tree ($MAIN)"
    exit 1
fi

mkdir -p var
STATUS_FILE="var/bootstrap-status"
LOG_FILE="var/bootstrap.log"

echo "running" > "$STATUS_FILE"
# Tee so a manual `make bootstrap` run still shows progress interactively,
# while a background-launched run (from session-start.sh) still gets logged.
exec > >(tee -a "$LOG_FILE") 2>&1

on_error() {
    echo "failed: see $LOG_FILE" > "$STATUS_FILE"
}
trap on_error ERR
set -euo pipefail

echo "📦 Bootstrapping worktree at $WORKTREE... ($(date -Iseconds))"

# 1. Python venv — skip if already isolated to this worktree (idempotent fast path).
if [ -x .venv/bin/python ] && .venv/bin/python -c "
import lorecraft, os, sys
sys.exit(0 if os.path.abspath(lorecraft.__file__).startswith(os.path.abspath('$WORKTREE')) else 1)
" 2>/dev/null; then
    echo "  ➜ venv already isolated to this worktree, skipping install."
else
    echo "  ➜ Creating Python venv..."
    python3 -m venv .venv
    .venv/bin/pip install -U pip setuptools wheel
    .venv/bin/pip install -e ".[dev]"
fi

# 2. Empty SQLite database — never touch an existing one (may hold session state).
if [ ! -f var/app.sqlite ]; then
    echo "  ➜ Creating local database..."
    # `< /dev/null` opens a connection but never writes, so sqlite3 never flushes
    # the file to disk (confirmed on 3.45.1) — VACUUM forces an actual write.
    sqlite3 var/app.sqlite "VACUUM;"
else
    echo "  ➜ Database already exists, leaving as-is."
fi

# 3. Docs YAML fixtures — always refresh from the primary tree (cheap, non-destructive).
echo "  ➜ Refreshing docs fixtures..."
mkdir -p docs
cp "$MAIN"/docs/*.yaml docs/ 2>/dev/null || true

# 4. Local .env.local (per-worktree overrides) — only seed if absent.
if [ ! -f .env.local ]; then
    echo "  ➜ Setting up .env.local..."
    cp "$MAIN"/.env.example .env.local 2>/dev/null || true
fi

echo "ready" > "$STATUS_FILE"
echo "✅ Worktree ready at $WORKTREE"
