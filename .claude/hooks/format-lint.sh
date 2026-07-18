#!/usr/bin/env bash
# PostToolUse hook (matcher: Write|Edit). Auto-formats and lint-fixes Python
# files immediately after every edit, so style drift never survives past the
# edit that created it — agents don't need to remember `make lint` /
# `ruff format`, and should never run either themselves (see AGENTS.md /
# agent definitions — lint & format are hook-owned, not agent-owned). Zero
# LLM cost: this is the ONLY place ruff runs mid-task now.
#
# After auto-fixing, this also runs a check-only pass and prints anything
# `--fix` couldn't resolve directly in the hook output — that's the one
# thing agents still need to act on (a real code change, not a style nit),
# so it's surfaced immediately instead of waiting for a separate Test & QA
# `make lint` dispatch. Do not re-run ruff after reading this output; the
# printed list is already the complete remainder.
#
# Fail-open by design: any missing tool, non-.py file, or file outside
# src/tests exits 0 with no output. Only prints when there's something to
# act on, to keep hook noise low.
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

# Whatever's left after --fix is, by definition, not auto-fixable — surface
# it now so the agent addresses it in the same turn instead of discovering
# it later via a separate lint dispatch.
remaining=$("${ruff_cmd[@]}" check --quiet "$f" 2>/dev/null)
if [ -n "$remaining" ]; then
  echo "[lint] $(basename "$f") — non-autofixable findings (fix directly, do not re-run ruff):"
  echo "$remaining"
fi

exit 0
