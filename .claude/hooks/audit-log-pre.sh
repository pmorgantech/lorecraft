#!/usr/bin/env bash
# PreToolUse hook (all tools, no matcher). Records a start timestamp keyed to
# this session so audit-log-post.sh can compute a per-tool-call duration_ms.
# Paired with audit-log-post.sh — see that script for the log format and the
# rationale (docs/project/AGENT_ROUTING_AND_METRICS.md Part 3: metrics baseline for
# free, 0 tokens, fires every time so it's never forgotten).
#
# Fail-open by design: never blocks a tool call, never emits permission JSON.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
payload=$(cat 2>/dev/null)

session=$(printf '%s' "$payload" | jq -r '.session_id // "unknown"' 2>/dev/null)
tool=$(printf '%s' "$payload" | jq -r '.tool_name // "unknown"' 2>/dev/null)

stack_dir="$root/var/.audit-stack"
mkdir -p "$stack_dir" 2>/dev/null || exit 0
stack_file="$stack_dir/${session}.stack"

now_ms=$(date +%s%3N 2>/dev/null || echo 0)
printf '%s|%s\n' "$now_ms" "$tool" >>"$stack_file" 2>/dev/null

exit 0
