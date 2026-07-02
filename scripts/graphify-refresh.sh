#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$root"

if ! command -v graphify >/dev/null 2>&1; then
  echo "graphify: command not found — skipping graph refresh." >&2
  echo "Install it locally to enable Graphify-backed architecture context (see AGENTS.md)." >&2
  exit 0
fi

graphify .

echo
echo "Graph updated:"
echo "  graphify-out/GRAPH_REPORT.md"
echo "  graphify-out/graph.html"
echo "  graphify-out/graph.json"
