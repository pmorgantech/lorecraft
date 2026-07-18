#!/usr/bin/env bash
# PostToolUse hook (matcher: Write|Edit). Auto-formats and lint-fixes Python
# files immediately after every edit, so style drift never survives past the
# edit that created it — agents don't need to remember `make lint` /
# `ruff format` and reviewers don't waste a round-trip on formatting nits.
# Zero LLM cost.
#
# Fail-open by design: any missing tool, non-.py file, or file outside
# src/tests exits 0 with no output. Only prints a line when it actually
# changed something, to keep hook noise low.
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

# Only format files inside this project's src/ or tests/ trees — never a
# worktree/scratch path outside the checkout, never a third-party file.
case "$f" in
"$root"/src/* | "$root"/tests/*) ;;
*) exit 0 ;;
esac

if [ -x "$root/.venv/bin/python" ]; then
  ruff_cmd=("$root/.venv/bin/python" -m ruff)
elif command -v ruff >/dev/null 2>&1; then
  ruff_cmd=(ruff)
else
  exit 0
fi

before=$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1)
"${ruff_cmd[@]}" format "$f" >/dev/null 2>&1
"${ruff_cmd[@]}" check --fix --quiet "$f" >/dev/null 2>&1
after=$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1)

if [ "$before" != "$after" ]; then
  echo "[auto-format] ruff reformatted $(basename "$f")"
fi

exit 0
