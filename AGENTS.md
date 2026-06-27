# Repository agent instructions

## Context strategy
- Start with local files and tests.
- Use Graphify for architecture, impact analysis, dependency paths, and unfamiliar subsystems when graphify-out/graph.json exists.
- Use Ref before changing code that depends on external APIs, libraries, SDKs, or framework behavior.
- Use Exa for recent ecosystem research, changelogs, examples, or public issue research.

## Workflow
- Make small, reviewable changes.
- Prefer existing project patterns.
- Run focused tests/lints after changes.
- Keep `CHANGELOG.md` up to date for user-visible changes.
- Keep version numbers synchronized in `pyproject.toml` and `src/lorecraft/__init__.py`.
- Summarize changed files, risks, and verification.
