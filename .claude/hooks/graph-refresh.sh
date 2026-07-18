#!/usr/bin/env bash
# PostToolUse hook (matcher: Write|Edit). Keeps the CodeGraph index
# (.codegraph/) in sync after any source edit under src/, so codegraph_explore
# never serves stale results mid-session — agents don't need to remember
# `make ai-graph`. AST-only re-extraction (`codegraph sync`), no LLM call,
# zero token cost. Complements session-start.sh, which only refreshes once at
# session boot; this keeps it current through a long editing session too.
#
# Fail-open by design: skips cleanly if .codegraph/ doesn't exist (indexing
# is the user's decision — AGENTS.md), the file isn't under src/, or the
# codegraph binary isn't installed. Debounced so a burst of edits in one
# turn doesn't re-sync per file.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
payload=$(cat 2>/dev/null)
f=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$f" ] && exit 0
[ -f "$f" ] || exit 0

case "$f" in
*.py) ;;
*) exit 0 ;;
esac
case "$f" in
"$root"/src/*) ;;
*) exit 0 ;;
esac

[ -d "$root/.codegraph" ] || exit 0
command -v codegraph >/dev/null 2>&1 || exit 0

marker="$root/var/.graph-refresh-last-run"
now=$(date +%s)
if [ -f "$marker" ]; then
  last=$(cat "$marker" 2>/dev/null || echo 0)
  [ $((now - last)) -lt 10 ] 2>/dev/null && exit 0
fi
mkdir -p "$root/var" 2>/dev/null
echo "$now" >"$marker" 2>/dev/null

if (cd "$root" && codegraph sync . >/dev/null 2>&1); then
  echo "[codegraph] index refreshed after edit to $(basename "$f")"
fi

exit 0
