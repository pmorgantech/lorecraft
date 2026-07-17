---
name: lorecraft-orchestration
description: Coordinate Lorecraft multi-agent work from the main session. Use when a request spans multiple domains, needs specialist dispatch, requires release/integration routing, or when deciding whether to use Backend Engineer, Frontend Specialist, Research Planner, Docs Writer, Pytest Writer, Test & QA, Code Reviewer, Database Specialist, or Integrator.
---

# Lorecraft Orchestration

Use the main session as orchestrator. Do not dispatch an Orchestrator subagent. Keep routing explicit, narrow, and proportional to risk.

## Default Flow

1. Restate the concrete outcome and affected area.
2. Dispatch only the specialists needed for that area.
3. Give each specialist a bounded task, relevant files, and a stop condition.
4. Keep implementation and verification separate.
5. Report blockers immediately; do not create retry loops.

## Dispatch Rules

- **No subagent**: small, single-file edits the main session can safely make and verify.
- **Research Planner**: ambiguous design, roadmap fit, tier split, tunability, or scope questions before implementation.
- **Backend Engineer**: Python implementation in `src/lorecraft/engine/` or `src/lorecraft/features/`. No tests, linting, formatting, docs, versioning, or merging.
- **Frontend Specialist**: templates, JS, CSS, player/admin UI, or feature presentation seams.
- **Database Specialist**: schema/model/index/query-shape review only when models, tables, indexes, or DB-backed config changed.
- **Pytest Writer**: test authoring, coverage backfill, slow-suite splitting, or test-quality repair.
- **Test & QA**: run scoped verification suites and report pass/fail. Use after implementation, not during it.
- **Code Reviewer**: risky or cross-cutting changes, security/auth/input handling, tier-boundary concerns, or when an independent review is explicitly useful.
- **Docs Writer**: user/admin docs, roadmap, wishlist, scripting docs, and `[Unreleased]` changelog entries.
- **Integrator**: version bump, changelog release heading, merge/tag, and final release gate.

## Keep Verification Scoped

Choose the narrowest useful QA lane:

- Backend-only logic: focused unit file(s), tier-boundary test if engine/features changed, then broader suite only if risk warrants.
- Schema change: Database Specialist review, then focused persistence/import/export tests.
- Frontend/UI: focused e2e/browser coverage plus any affected backend tests.
- Scripting vocabulary change: `make scripting-docs` and `tests/unit/test_scripting_api_doc.py`.
- Release/integration: Integrator owns the final release checklist.

Avoid duplicate suite runs. If Backend or Frontend implemented the change, Test & QA verifies it. If Pytest Writer authored tests, Test & QA may run broader verification afterward when needed.

## Parallelism

Run agents in parallel only when their files and responsibilities do not overlap. Subagents must stay in the branch/worktree where they begin; do not instruct them to create, switch, or remove worktrees. Review and QA agents can run in parallel after implementation if they inspect the same finished state.

## Handoff Template

Give each subagent:

- Goal: one sentence.
- Scope: files/packages to inspect or edit.
- Out of scope: what not to touch.
- Verification owner: usually Test & QA, not the implementer.
- Done signal: expected summary format and stop condition.

## Stop Conditions

Stop and ask or report when:

- A specialist finds a design decision outside its lane.
- A permission-classifier block occurs.
- The same failure repeats after one targeted retry.
- The requested work would require broad refactoring beyond the stated task.
