#!/usr/bin/env bash
# PostToolUse hook (all tools, no matcher). Pops the matching start timestamp
# audit-log-pre.sh pushed (LIFO stack per session), computes duration_ms, and
# appends one structured line per tool call to var/audit.log. This is the
# metrics baseline referenced in docs/AGENT_ROUTING_AND_METRICS.md Part 3 —
# zero LLM cost, fires unconditionally so routing/timing data is never
# missing because an agent forgot to report it.
#
# Agent attribution is best-effort: the hook payload doesn't reliably carry
# an explicit subagent name across all Claude Code versions, so we try a few
# plausible field names before falling back to "main". Status is similarly
# best-effort — read from tool_response.is_error when present.
#
# Fail-open by design: never blocks, exits 0 even if jq/date/paths are
# unavailable.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
payload=$(cat 2>/dev/null)

session=$(printf '%s' "$payload" | jq -r '.session_id // "unknown"' 2>/dev/null)
tool=$(printf '%s' "$payload" | jq -r '.tool_name // "unknown"' 2>/dev/null)
agent=$(printf '%s' "$payload" | jq -r '.agent_name // .subagent_type // .agent // "main"' 2>/dev/null)

# Best-effort "what did this target" — first populated of a few common keys.
detail=$(printf '%s' "$payload" | jq -r '
  (.tool_input.file_path // .tool_input.command // .tool_input.pattern //
   .tool_input.description // .tool_input.skill // .tool_input.path // "")
  | tostring' 2>/dev/null | tr '\n' ' ' | cut -c1-200)

status=$(printf '%s' "$payload" | jq -r '
  if (.tool_response.is_error // false) then "error" else "success" end' 2>/dev/null)

stack_file="$root/var/.audit-stack/${session}.stack"
duration_ms="NA"
if [ -f "$stack_file" ] && [ -s "$stack_file" ]; then
  last_line=$(tail -n 1 "$stack_file" 2>/dev/null)
  start_ms="${last_line%%|*}"
  sed -i '$d' "$stack_file" 2>/dev/null || true
  if [ -n "$start_ms" ] && [ "$start_ms" != "0" ]; then
    now_ms=$(date +%s%3N 2>/dev/null || echo 0)
    duration_ms=$((now_ms - start_ms))
  fi
fi

log_dir="$root/var"
mkdir -p "$log_dir" 2>/dev/null || exit 0
ts=$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)

printf '%s session=%s agent=%s tool=%s status=%s duration_ms=%s detail="%s"\n' \
  "$ts" "${session:0:8}" "$agent" "$tool" "$status" "$duration_ms" "$detail" \
  >>"$log_dir/audit.log" 2>/dev/null

exit 0
