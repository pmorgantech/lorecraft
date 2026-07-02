# Repository agent instructions

## Context strategy

- Start with local files and tests.
- Use Graphify for architecture, impact analysis, dependency paths, and unfamiliar subsystems when graphify-out/graph.json exists.
- Use Ref before changing code that depends on external APIs, libraries, SDKs, or framework behavior.
- Create a new branch for any changes which are large in scope or risky.

## Design principles

- Prefer **data-driven** configuration (world YAML, fixture modules, config files) over
  runtime branching on room names, item IDs, or other world content baked into application code.
- Do not inspect the database for specific room/world IDs to choose behaviour at runtime
  unless there is no practical data source — if you need topology or test content, put it in
  `world_content/` or a dedicated fixture module and load/import it explicitly.
- Avoid **reward hacking** in tests: do not add production special cases solely to make a
  test pass. Tests should set up their own fixtures under `tests/fixtures/` or use imported
  world data (`world_content/world.yaml`); production paths should stay general.
- Keep test-only world content (disambiguation rooms, overlapping item names, etc.) out of
  `src/lorecraft/`. The engine loads world data from YAML/DB, not from pytest helpers.

## Workflow

- Make small, reviewable changes.
- Prefer existing project patterns.
- Type hint all new features; omit hints only when they would be noisy, brittle, or not easily expressible.
- Write unit tests for all new features.
- After new code, run focused: unit tests, formatter, and basedpyright on modified or new files.
- Keep `docs/status.md` updated with current implementation progress.
- Keep `CHANGELOG.md` updated with meaningful, user-visible changes.
- Keep version numbers synchronized in `pyproject.toml` and `src/lorecraft/__init__.py`.
- Summarize changed files, risks, and verification.
