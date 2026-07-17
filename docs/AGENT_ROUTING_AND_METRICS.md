# Agent Routing and Metrics Guide

**Date:** 2026-07-17
**Purpose:** Document agent dispatch routing, skill routing by role, and metrics for tracking efficiency and correctness.

---

## Part 1: Agent Routing Decision Tree

Use this to determine which agent to dispatch for a given task.

### Is this a code change or implementation task?

**YES** → Continue below.
**NO** → Jump to [Non-Implementation Tasks](#non-implementation-tasks).

#### What type of code change?

| Task Type | Primary Agent | Secondary Agents | Notes |
|-----------|---------------|------------------|-------|
| **Engine logic, services, models, conditions/effects** | `backend-engineer` | `database-specialist` (if schema changes), `lorecraft-code-reviewer` (after done) | Tier 1/2 code |
| **Player/admin UI, templates, Alpine/Tailwind** | `frontend-specialist` | `lorecraft-code-reviewer` (after done) | Web layer only |
| **New test suite, coverage gap, e2e/Playwright work** | `pytest-writer` | `test-qa` (runs them), `lorecraft-code-reviewer` (if tests look suspicious) | Test authoring only |
| **Bug fix (code already exists, not growing scope)** | Use primary agent for that code type + `lorecraft-code-reviewer` | Same as above | Route by code ownership |
| **Refactoring (cleanup, splitting, improving structure)** | Use primary agent for that code type | Add `database-specialist` if schema touched | Same routing rules apply |

### Non-Implementation Tasks

| Task Type | Agent(s) | Notes |
|-----------|---------|-------|
| **Run tests, check coverage, typecheck, lint** | `test-qa` | Advisory + structured reporting only |
| **Review completed code (idiomatic, smells, security)** | `lorecraft-code-reviewer` | Reports findings; does not fix |
| **Write/update docs, roadmap, user guide** | `docs-writer` | Also generates scripting docs from live registry |
| **Investigate design, precedent, feasibility** | `research-planner` | Produces design analysis for `docs-writer` to commit |
| **Schema design review (indexes, normalization, migrations)** | `database-specialist` | Advisory only; Backend Engineer applies fixes |
| **Version bumps, CHANGELOG, merging, tagging** | `integrator` | Final release gate; only agent touching version files |

---

## Part 2: Skill Routing (Role-Based Access)

Agents now have `Skill` tool enabled. Below are **recommended** skill calls by agent role. Agents can call skills outside their primary lane if a task genuinely needs it, but the defaults below reflect their specialization and keep routing predictable.

### Backend Engineer → recommended skills

- `code-review` — self-review complex functions before handoff (optional, not required)
- `test-writer` — when implementing, pair with new tests (collaborative, not solo)
- `verify` — end-to-end validation before handing to Test & QA
- `worldbuilding` — when creating NPC behavior, rooms, items in features/

### Frontend Specialist → recommended skills

- `code-review` — self-review complex templates/Alpine logic (optional)
- `verify` — test UI in browser before handing to Test & QA
- `dataviz` — if building charts/analytics UI

### Pytest Writer → recommended skills

- `code-review` — flag suspicious tests to `lorecraft-code-reviewer` if found
- `test-writer` — recursive if splitting or creating new test approaches
- `verify` — validate that tests exercise real behavior

### Test & QA → recommended skills

- `code-review` — minimal; failures are routed back to primary agent
- `verify` — run focused checks per domain

### Docs Writer → recommended skills

- `kindle-doc-weaver` — export docs to EPUB/PDF
- `code-review` — validate code examples in docs match actual source
- `lorecraft-orchestration` — if coordinating multi-agent doc updates

### Database Specialist → recommended skills

- `code-review` — validate schema patterns match codebase conventions
- `verify` — test migration/query patterns before Backend Engineer implements

### Research Planner → recommended skills

- `code-review` — optional, validate design analysis against existing patterns
- `verify` — exploratory verification of design feasibility

### Integrator → recommended skills

- `code-review` — final check before merge (low bar; catch last-minute issues)
- `lorecraft-orchestration` — if coordinating multi-agent merges/releases

### Skills to avoid calling (or route instead)

| Skill | Why | Route to |
|-------|-----|----------|
| `ci-writer` | CI configuration is rare in Lorecraft; usually done by main session | Main session or `integrator` if release-critical |
| `dockerfile-writer` | Lorecraft ships as Python; no Docker workflow yet | Main session if ever added |
| `env-validator` | Not currently used; would be deployment tooling | Main session |
| `pre-commit-setup` | Rare reconfig; usually a session-level setup task | Main session |
| `update-config` | Agent tools/permissions are set up once; not a per-task change | Main session |
| `keybindings-help` | User-specific; not task-related | User directly |

---

## Part 3: Metrics to Track

Track these four dimensions to measure agent effectiveness and catch routing issues:

### 1. Agent Routing Accuracy (Task → Right Agent)

**What to measure:**
- How many times was a task routed to the wrong agent initially?
- How often did an agent correctly redirect vs. improvise out-of-lane?
- Which agent types are most frequently misrouted?

**How to capture:**
- Tag task dispatch: `@backend-engineer` (dispatched), note if redirected to `@docs-writer` during execution
- Monthly sample: review 5-10 random tasks, check if routing matched decision tree above

**Target:** >95% first-dispatch accuracy. <1% of tasks require re-routing due to scope mismatch.

### 2. Execution Time per Agent

**What to measure:**
- Time from dispatch to completion per agent type
- Breakdown: time-to-first-tool-use (setup), tool execution (work), report (summary)
- Identify slow agents (bottlenecks) vs. quick turnarounds

**How to capture:**
- Timestamp dispatch, first tool call, and task completion
- Log format: `Agent=backend-engineer, StartTime=2026-07-17T14:22:00Z, FirstToolTime=+2s, CompleteTime=+45s`
- Group by task type (e.g., "small feature" vs. "schema refactor")

**Target:**
- Simple code edits: <10 min (including verification)
- Medium features: 30–60 min
- Complex refactors: 90–120 min
- Long pole: tests or integration

### 3. Tool Usage Patterns

**What to measure:**
- Which tools does each agent actually use? (vs. tools they have access to)
- Are agents calling skills, or skipping them when they should?
- Bash frequency for agents that have it (catch runaway shell usage)

**How to capture:**
- Log every tool call: `Agent=backend-engineer, Tool=Edit, File=src/lorecraft/engine/services/foo.py`
- Count tool calls per task: `backend-engineer: Read(8), Edit(3), Write(0), Skill(0), Grep(1)`
- Identify over-used or under-used tools

**Target:**
- No agent should use >5% Bash calls (catch debugging workarounds)
- Agents with Skill access should use skills 1–2x per medium task (collaborative validation)
- Read/Edit/Write should dominate for backend/frontend agents

### 4. Error Rates & Redirects

**What to measure:**
- How often does an agent encounter a permission block?
- How often does an agent redirect to another agent mid-task?
- Which redirects are expected (scope discovery) vs. unexpected (routing error)?

**How to capture:**
- Log permission denials: `Agent=backend-engineer, Tool=Bash, Outcome=DENIED`
- Log redirects: `Agent=backend-engineer, Redirect=database-specialist, Reason=schema_review_needed`
- Flag unexpected: e.g., `frontend-specialist` redirecting to `backend-engineer` for HTML changes

**Target:**
- <1% permission blocks per agent (tools properly configured)
- <5% explicit redirects (agent correctly identifies out-of-lane work)
- 0% unexpected redirect types (routing discipline)

---

## Part 4: Interpreting Metrics & Adjusting

### Metric: High redirect rate for an agent type

**Possible causes:**
- Task description is ambiguous (scope not clear before dispatch)
- Agent decision tree is unclear (agent doesn't know when to redirect)
- Routing decision tree doesn't match actual agent capability

**Action:**
- Review redirect logs; categorize by type (schema → DB specialist, tests → pytest-writer, etc.)
- If >20% of redirects are to the same secondary agent, update the primary agent's definition to call that skill proactively
- Update decision tree if a pattern emerges

### Metric: Slow execution for an agent type

**Possible causes:**
- Agent is taking on work outside its lane (lots of redirects)
- No skill tool → agent re-doing work another agent already did
- Verification step is expensive (e.g., full test suite when focused test suffices)

**Action:**
- Add skill tool if missing (refer to Part 2)
- Request Test & QA focused run instead of full suite
- Check handoff format; if agent is re-reading parent's work, clarify dispatch briefing

### Metric: Permission blocks for specific tools

**Possible causes:**
- Tool is needed but permission not configured
- Agent is attempting work outside its lane (hitting permission classifier)
- Worktree/session permissions are stale

**Action:**
- If legitimate work (e.g., `backend-engineer` needs Bash for a one-off CLI task), ask user to enable permission
- If pattern emerges (e.g., `frontend-specialist` frequently blocked on Bash), reconsider tool assignment
- Update AGENTS.md or settings if a tool was wrongly removed/added

### Metric: Low skill usage despite having Skill tool

**Possible causes:**
- Agents don't know about available skills
- Agents are hesitant to call skills (fear of over-delegating)
- Relevant skills are hard to discover

**Action:**
- Highlight skill names in agent handoff templates: "Use `/code-review` to validate before handoff"
- Periodically remind agents of complementary skill paths (e.g., "pytest-writer → verify")
- Ensure skill descriptions in system-reminder are up-to-date

---

## Part 5: Monthly Metrics Review Checklist

Run this checklist on the 1st of each month to stay ahead of drift:

- [ ] **Routing accuracy:** Sample 5–10 tasks; check vs. decision tree. Fix any systematic misroutes.
- [ ] **Execution time:** Aggregate by agent type. Flag any >25% regression. Investigate cause.
- [ ] **Tool usage:** Confirm no agent is over-using Bash; confirm Skill adoption is >20%.
- [ ] **Redirects:** Categorize, ensure <5% rate. Update decision tree if pattern found.
- [ ] **Permission blocks:** Any new blocks? Update agent definition or resolve permissions.
- [ ] **Skill discovery:** Remind teams of available skills; update Part 2 if new skills land.
- [ ] **Decision tree:** Update AGENTS.md routing section if agent responsibilities shifted.

---

## Part 6: Example: Tracing a Task

**Scenario:** A user asks, "Add a player stat (e.g., 'charisma') to the character sheet UI."

### Expected routing:

1. **Initial dispatch:** `backend-engineer` (must add model field, service methods)
2. **Backend work:** Edits `engine/models/player.py`, `features/stats/models.py`, creates repo method
   - Calls `/verify` to check stat is queryable and doesn't break tier boundaries
3. **Redirect:** Hands off to `frontend-specialist` once API contract stable
4. **Frontend work:** Adds template in `webui/player/templates/character.html`, Alpine.js for display
   - Calls `/verify` to check rendering and responsive breakpoints
5. **Code review:** `lorecraft-code-reviewer` checks both backend and frontend
   - No findings → "ready for Test & QA"
6. **Testing:** `test-qa` runs `make test` (units) and `make test-e2e` (UI)
   - If e2e fails, routes back to `frontend-specialist` for fix
7. **Docs:** `docs-writer` updates `docs/user_guide.md` (new stat section)
8. **Release:** `integrator` bumps version, updates CHANGELOG, merges

### Metrics to log:

- `backend-engineer`: 20 min (Read models + edit + verify)
- `frontend-specialist`: 15 min (Read templates + edit + verify)
- `lorecraft-code-reviewer`: 5 min (review both)
- `test-qa`: 10 min (run suites, 2 e2e failures escalated)
- `frontend-specialist`: +10 min (second pass, fixes e2e)
- `docs-writer`: 8 min (update guide)
- `integrator`: 3 min (merge + tag)

**Total:** 71 min, 0 permission blocks, 1 redirect (backend → frontend, expected).

---

## References

- **AGENTS.md** — Agent definitions and hard rules
- **docs/multi-agent-workflow.md** — Workflow for parallel agents
- **CODE_AUDIT.md** — Baseline code quality metrics
