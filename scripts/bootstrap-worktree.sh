#!/usr/bin/env bash
# Bootstrap script for agent worktrees: isolated venv, database, and docs.
# Usage: ./scripts/bootstrap-worktree.sh
#
# Sets up:
#   - Local Python venv (.venv/)
#   - Empty SQLite database (var/app.sqlite)
#   - Copy of docs YAML fixtures (docs/*.yaml)
#   - Local .env.local (from .env.example)

set -euo pipefail

MAIN=$(dirname "$(git rev-parse --git-common-dir)")
WORKTREE="$PWD"

if [ "$MAIN" = "$WORKTREE" ]; then
    echo "❌ Error: run this from a worktree, not the primary tree ($MAIN)"
    exit 1
fi

echo "📦 Bootstrapping worktree at $WORKTREE..."

# 1. Python venv (isolated to this worktree) — editable install of THIS tree,
# so `import lorecraft` resolves to the worktree's src/ with no PYTHONPATH tricks.
echo "  ➜ Creating Python venv..."
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e ".[dev]"

# 2. Empty SQLite database
echo "  ➜ Creating local database..."
mkdir -p var
if [ ! -f var/app.sqlite ]; then
    sqlite3 var/app.sqlite < /dev/null
fi

# 3. Copy docs YAML (read-only fixtures)
echo "  ➜ Copying docs fixtures..."
mkdir -p docs
cp "$MAIN"/docs/*.yaml docs/ 2>/dev/null || true

# 4. Local .env.local (per-worktree overrides)
echo "  ➜ Setting up .env.local..."
if [ ! -f .env.local ]; then
    cp "$MAIN"/.env.example .env.local 2>/dev/null || true
fi

echo "✅ Worktree ready at $WORKTREE"
echo ""
echo "Next steps:"
echo "  source .venv/bin/activate   # activate this worktree's venv"
echo "  make test                   # tests now run against this tree (no PYTHONPATH needed)"
echo ""
