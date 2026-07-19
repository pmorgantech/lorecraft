#!/usr/bin/env bash
# PostToolUse hook (matcher: Write|Edit). Regenerates docs/worldbuilding/scripting_api.md
# immediately after any edit that touches scripting-vocabulary registration
# (a register_spec(...) call — a new/edited condition, effect, or
# behavior-mode descriptor), per AGENTS.md's "same commit" rule. Previously
# this relied on the editing agent remembering to run `make scripting-docs`;
# the CI drift-check (tests/unit/test_scripting_api_doc.py) would catch a
# miss, but only after a full CI round-trip. This hook fires unconditionally
# so the doc never drifts in the first place. Zero LLM cost.
#
# Fail-open by design: skips cleanly if the file isn't Python, doesn't
# contain register_spec(, or `make`/Makefile is unavailable.
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

grep -q 'register_spec(' "$f" 2>/dev/null || exit 0

# Debounce: a batch of edits across several vocabulary files in the same
# turn shouldn't each trigger a full regen — skip if we ran in the last 5s.
marker="$root/var/.scripting-docs-last-run"
now=$(date +%s)
if [ -f "$marker" ]; then
  last=$(cat "$marker" 2>/dev/null || echo 0)
  [ $((now - last)) -lt 5 ] 2>/dev/null && exit 0
fi
mkdir -p "$root/var" 2>/dev/null
echo "$now" >"$marker" 2>/dev/null

if command -v make >/dev/null 2>&1 && [ -f "$root/Makefile" ]; then
  if (cd "$root" && make scripting-docs >/dev/null 2>&1); then
    echo "[scripting-docs] docs/worldbuilding/scripting_api.md regenerated (register_spec change in $(basename "$f"))"
  fi
fi

exit 0
