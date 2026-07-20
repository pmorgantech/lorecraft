#!/usr/bin/env bash
# PostToolUse hook (matcher: Write|Edit). Auto-formats Rust files immediately
# after every edit, so style drift never survives past the edit that created
# it — agents don't need to remember `cargo fmt`, and should never run it
# themselves (see AGENTS.md / agent definitions — format is hook-owned, not
# agent-owned). Zero LLM cost: this is the ONLY place rustfmt runs mid-task.
#
# Deliberately does NOT run clippy here, unlike format-lint.sh's ruff-check
# step: clippy needs to compile the crate (seconds, not milliseconds), which
# would make every single edit pay a real wait — wrong tradeoff for a
# real-time hook. Clippy stays a Test & QA `rust-lint` lane responsibility,
# run once per verification pass instead of once per edit.
#
# Fail-open by design: any missing tool, non-.rs file, or file outside rust/
# exits 0 with no output. Only prints when the file was actually reformatted.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
payload=$(cat 2>/dev/null)
f=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -z "$f" ] && exit 0
[ -f "$f" ] || exit 0

case "$f" in
*.rs) ;;
*) exit 0 ;;
esac

# Only format files inside this project's rust/ workspace — never a
# worktree/scratch path outside the checkout, never a third-party file.
case "$f" in
"$root"/rust/*) ;;
*) exit 0 ;;
esac

command -v rustfmt >/dev/null 2>&1 || exit 0

before=$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1)
rustfmt --edition 2021 "$f" >/dev/null 2>&1
after=$(sha256sum "$f" 2>/dev/null | cut -d' ' -f1)

if [ "$before" != "$after" ]; then
  echo "[auto-format] rustfmt reformatted $(basename "$f")"
fi

exit 0
