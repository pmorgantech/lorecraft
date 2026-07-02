#!/usr/bin/env bash
# Refreshes graphify-out/graph.json at session start so Graphify-backed
# architecture context (see AGENTS.md) is available from the first turn.
# graphify-refresh.sh no-ops cleanly if the `graphify` binary isn't present.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
"$root/scripts/graphify-refresh.sh" || true
