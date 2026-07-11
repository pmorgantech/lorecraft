#!/usr/bin/env bash
# Refreshes graphify-out/graph.json at session start so Graphify-backed
# architecture context (see AGENTS.md) is available from the first turn.
# graphify-refresh.sh no-ops cleanly if the `graphify` binary isn't present.
#
# Also auto-bootstraps worktrees (isolated venv/db/docs fixtures) in the
# background — see docs/multi-agent-workflow.md. Launched non-blocking so
# session start never waits on `pip install`; bootstrap-worktree.sh is
# idempotent, so firing it on every session start is safe and cheap once
# a worktree is already bootstrapped. Agents poll var/bootstrap-status
# rather than assuming the venv is ready immediately.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
"$root/scripts/graphify-refresh.sh" || true

# A linked worktree's .git is a *file* (pointing at the real gitdir); the
# primary tree's .git is a directory and already has its own venv — never
# bootstrap there.
if [ -f "$root/.git" ]; then
    nohup bash "$root/scripts/bootstrap-worktree.sh" >/dev/null 2>&1 &
    disown 2>/dev/null || true
fi
