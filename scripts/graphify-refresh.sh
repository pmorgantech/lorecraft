#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$root"

graphify .

echo
echo "Graph updated:"
echo "  graphify-out/GRAPH_REPORT.md"
echo "  graphify-out/graph.html"
echo "  graphify-out/graph.json"
