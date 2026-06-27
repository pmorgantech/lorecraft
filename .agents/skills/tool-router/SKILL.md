---
name: tool-router
description: Choose between local search, Graphify, Ref, and Exa for coding tasks.
---

# Tool Router

Use this workflow when a task may require architecture context, current docs, or current web research.

## Routing
- Local files first for concrete implementation details.
- Graphify for architecture, dependency paths, cross-module impact, and "how does this fit together?"
- Ref for framework/library/API documentation, especially when versions matter.
- Exa for current public information, examples, changelogs, ecosystem issues, or unknown tools.

## Default sequence
1. Inspect repo files.
2. If graphify-out/graph.json exists and the task crosses modules, query Graphify.
3. If external APIs are involved, query Ref.
4. If information may have changed recently, use Exa.
5. Make the smallest useful change.
6. Run focused tests or explain why not.
