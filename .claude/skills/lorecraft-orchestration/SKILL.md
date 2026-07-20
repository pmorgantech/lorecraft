---
name: lorecraft-orchestration
description: Coordinate Lorecraft multi-agent work from the main session. Use when a request spans multiple domains, needs specialist dispatch, requires release/integration routing, or when deciding whether to use Backend Engineer (Python or Rust), Frontend Specialist, Research Planner, Docs Writer, Pytest Writer, Rust Test Writer, Test & QA (Python or Rust), Code Reviewer, Database Specialist, or Integrator.
---

# Lorecraft Orchestration

Use the main session as orchestrator. Do not dispatch an Orchestrator subagent. Keep routing explicit, narrow, and proportional to risk.

This skill is the **source of truth for dispatch policy** — which specialist, which lane, when to
run in parallel, when a change needs a "full gate." `AGENTS.md` stays general (repo conventions,
testing commands, git/worktree safety) and does not duplicate this policy; if the two ever
disagree, this skill wins for anything about *how to orchestrate*.

## When to use this skill

**Not every prompt needs orchestration.** A small, single-file, low-risk edit — a docstring fix, a
one-line bug fix, a config tweak — is faster and just as safe done directly in the main session.
Reach for specialist dispatch when the work is genuinely multi-domain (touches Python *and* Rust,
or backend *and* frontend), risky (auth, persistence, tier boundaries, anything hard to reverse),
large enough to need implement→verify→review as separate passes, or the user explicitly asks for
it ("dispatch this," "use the backend engineer," "orchestrate this"). When in doubt on a small
task, just do it — don't dispatch a subagent to avoid a decision you can make yourself in one edit.

## Lane discipline (non-negotiable)

Engineers and test-writers write; QA runs; nobody grades their own work. Concretely:

- **Backend implementation is split by language, no generic "backend engineer":**
  `backend-engineer-python` (`src/lorecraft/engine/`, `src/lorecraft/features/`,
  `src/lorecraft/gateway/`, backend `webui/` routes/handlers) and `backend-engineer-rust`
  (`rust/`). Both write code and nothing else.
- **Test authoring is split the same way:** `Pytest Writer` (Python suites, the Python side of the
  parity harness) and `Rust Test Writer` (Rust integration tests, the `lorecraft-replay`
  parity/determinism harness). Both write tests and nothing else.
- **Verification is split the same way again:** `test-qa-python` (`py-*` lanes) and `test-qa-rust`
  (`rust-*` lanes). Either can be one of several parallel dispatches — multiple instances of the
  same agent for a multi-lane "full gate," or one of each language agent together when a change
  touches both `src/lorecraft/` and `rust/`. Their lanes never share mutable state, so parallel
  dispatch is always safe once implementation is finished.
- **Nobody self-verifies, no exceptions for "it's just my own new code":** none of the four
  writer/author agents above (`backend-engineer-python`, `backend-engineer-rust`, `Pytest Writer`,
  `Rust Test Writer`) ever runs a test suite and reports pass/fail — that's `test-qa-python`/
  `test-qa-rust`'s job, always, including for tests an agent just wrote itself. The only two
  narrow, compile/collect-sanity-only carve-outs (never a stand-in for a QA lane):
  - `backend-engineer-rust` and `Rust Test Writer`: a fast, single-crate `cargo check -p <crate>`
    (add `--tests` for test files) while iterating.
  - `Pytest Writer`: `pytest --collect-only` to confirm a new test is well-formed, not that it
    passes.
  `backend-engineer-python` has no equivalent carve-out at all — it never runs `pytest`/`make
  test`/coverage/typecheck itself, not even "just to sanity check one file."
- **The orchestrating session (you) is the loop between an implementer and QA — they never
  dispatch each other.** Dispatch the implementer; dispatch QA (narrowest relevant lane); if QA
  reports a failure, route its structured report — test name, assertion, traceback — back to the
  *same* implementer lane for a fix, then dispatch QA again. QA has no `Edit`/`Write` tool by
  design and must never be asked to patch a failure it finds.

## Default Flow

1. Restate the concrete outcome and affected area.
2. Dispatch only the specialists needed for that area.
3. Give each specialist a bounded task, relevant files, and a stop condition.
4. Keep implementation and verification separate.
5. Report blockers immediately; do not create retry loops.

## Dispatch Rules

- **No subagent**: small, single-file edits the main session can safely make and verify (see "When to use this skill").
- **Research Planner**: ambiguous design, roadmap fit, tier split, tunability, or scope questions before implementation.
- **`backend-engineer-python`**: Python implementation/fixes in `src/lorecraft/engine/`, `src/lorecraft/features/`, `src/lorecraft/gateway/`, or backend webui routes/handlers. No tests, linting, formatting, docs, versioning, or merging — ever, no exceptions.
- **`backend-engineer-rust`**: Rust implementation/fixes under `rust/`. No test suites, clippy, `cargo fmt --all`, docs, versioning, or merging — except its own narrow single-crate `cargo check` for compile-sanity while iterating.
- **Frontend Specialist**: templates, JS, CSS, player/admin UI, or feature presentation seams.
- **Database Specialist**: schema/model/index/query-shape review only when models, tables, indexes, or DB-backed config changed.
- **Pytest Writer**: Python test authoring, coverage backfill, slow-suite splitting, or test-quality repair. Writes and collect-checks tests; never runs them to prove pass/fail.
- **Rust Test Writer**: Rust integration tests and the cross-language parity/determinism harness (`lorecraft-replay`). Writes and compile-checks (`cargo check --tests`) tests; never runs them to prove pass/fail.
- **`test-qa-python`**: run scoped Python verification lanes (`py-*`) and report pass/fail. Use after implementation, not during it.
- **`test-qa-rust`**: run scoped Rust verification lanes (`rust-*`) and report pass/fail. Use after implementation, not during it. Dispatch alongside `test-qa-python` (parallel) when a change spans both languages.
- **Code Reviewer**: risky or cross-cutting changes, security/auth/input handling, tier-boundary concerns, or when an independent review is explicitly useful.
- **Docs Writer**: user/admin docs, roadmap, wishlist, scripting docs, and `[Unreleased]` changelog entries.
- **Integrator**: version bump, changelog release heading, merge/tag, and final release gate.

## Keep Verification Scoped

Choose the narrowest useful QA lane, and pace how often you re-run it:

- Backend-only logic: focused unit file(s), tier-boundary test if engine/features changed, then broader suite only if risk warrants.
- Schema change: Database Specialist review, then focused persistence/import/export tests.
- Frontend/UI: focused e2e/browser coverage plus any affected backend tests.
- Scripting vocabulary change: `make scripting-docs` and `tests/unit/test_scripting_api_doc.py`.
- Release/integration: Integrator owns the final release checklist.

**Iterating on a fix (write → verify → find a bug → fix → re-verify)**: dispatch the single
narrowest lane that covers what you touched — usually `py-unit` (or `rust-unit`), often scoped
further to the specific failing test file(s) or crate. Re-running a multi-lane gate on every
iteration of a fix loop is the expensive mistake to avoid — it has cost an 8-minute, 17-tool-call
dispatch in practice, not from any flaw in the QA agents' design, just from over-broad dispatch.

- `py-e2e`/`py-simulation`/`rust-build` are **conditional, not routine** — dispatch only when the
  change actually touches what they cover (`py-e2e`: `webui/` templates/JS or a user-facing
  command flow; `py-simulation`: multiplayer broadcast/fan-out, the world clock/scheduler, or the
  Rust gateway path). A docs-only, test-only, or single-service change doesn't need either.
- `py-coverage` runs **only when the user's prompt explicitly asked for coverage** — not your
  judgment call, not "as part of the final gate" by default. It's strictly slower than `py-unit`
  for the same test results plus a coverage report.
- `py-lint`/`rust-fmt-check` are **safety nets, not the primary feedback loop** — the format-lint
  hooks already auto-fix every edited file in real time. Dispatch only for explicit CI-parity
  confirmation (e.g. the Integrator's pre-merge gate).
- **Reserve the multi-lane "full gate" for one deliberate moment** — immediately before
  commit/integration, not the default shape of iterative verification. That one dispatch naming
  several lanes at once is still an explicit, intentional scope, not the over-broad default above.

Avoid duplicate suite runs. If Backend or Frontend implemented the change, QA verifies it once. If
a test-writer authored tests, QA may run broader verification afterward when needed — but the
test-writer itself never does.

## Parallelism

Independent lanes/agents that don't share mutable state or a working tree, and read the same
already-committed-or-staged code, can and should run concurrently — dispatch them as separate
`Agent` tool-use blocks in **one message**, not sequential turns:

- `py-unit`, `py-typecheck`, `py-e2e`, `py-simulation` (each isolated: own DB/fixtures/ports).
- `rust-unit`, `rust-lint`.
- `test-qa-python` and `test-qa-rust` together, for a change spanning both languages.
- Review and QA agents together, once implementation is finished and they're inspecting the same finished state.
- `backend-engineer-rust`/`Rust Test Writer` instances on genuinely independent crates, each in its own worktree.

Don't parallel-dispatch a verification lane against another agent that's actively editing the same
files. Subagents must stay in the branch/worktree where they begin; do not instruct them to
create, switch, or remove worktrees — see `AGENTS.md`'s worktree-race sections for why (a shared
checkout's branch can change between one dispatched agent's tool calls if another is running
concurrently in the same directory).

## Handoff Template

Give each subagent:

- Goal: one sentence.
- Scope: files/packages to inspect or edit.
- Out of scope: what not to touch.
- Verification owner: usually `test-qa-python`/`test-qa-rust`, not the implementer.
- Done signal: expected summary format and stop condition.

## Stop Conditions

Stop and ask or report when:

- A specialist finds a design decision outside its lane.
- A permission-classifier block occurs.
- The same failure repeats after one targeted retry.
- The requested work would require broad refactoring beyond the stated task.
