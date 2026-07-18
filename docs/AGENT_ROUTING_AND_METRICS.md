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

**2026-07-17 update: automated capture is live.** `var/audit.log` (gitignored, per-machine) is
now populated automatically by a `PreToolUse`/`PostToolUse` hook pair
(`.claude/hooks/audit-log-pre.sh` + `audit-log-post.sh`) — every tool call from every agent
(main session + subagents) gets one line with timestamp, session, agent (best-effort — see
below), tool, status, duration_ms, and a truncated detail (file path / command / pattern). Zero
LLM cost; fires unconditionally, so it can't be forgotten. Sample line:

```
2026-07-17T21:04:12.501Z session=58b9f32b agent=main tool=Edit status=success duration_ms=226 detail="/path/to/file.py"
```

**Known limitation:** `agent` attribution is best-effort — the hook payload doesn't reliably
expose an explicit subagent name across all Claude Code versions, so the field falls back
through a few plausible keys before defaulting to `"main"`. Treat per-agent breakdowns from this
log as approximate until that's confirmed reliable; `tool`/`status`/`duration_ms` are accurate
regardless. The four dimensions below describe what to do with this data once collected — the
"How to capture" sections now mostly reduce to "grep/awk `var/audit.log`" rather than manual
logging.

Track these four dimensions to measure agent effectiveness and catch routing issues:

### 1. Agent Routing Accuracy (Task → Right Agent)

**What to measure:**
- How many times was a task routed to the wrong agent initially?
- How often did an agent correctly redirect vs. improvise out-of-lane?
- Which agent types are most frequently misrouted?

**How to capture:**
- `var/audit.log`'s `Agent` tool calls (dispatches) plus each session's own report text is the
  raw material — redirects aren't a distinct logged event yet, so cross-reference dispatch
  entries against agent handoff reports for "redirected to X" language.
- Monthly sample: review 5-10 random tasks, check if routing matched decision tree above

**Target:** >95% first-dispatch accuracy. <1% of tasks require re-routing due to scope mismatch.

### 2. Execution Time per Agent

**What to measure:**
- Time from dispatch to completion per agent type
- Breakdown: time-to-first-tool-use (setup), tool execution (work), report (summary)
- Identify slow agents (bottlenecks) vs. quick turnarounds

**How to capture:**
- `duration_ms` is logged per tool call in `var/audit.log`; sum by `agent`+session for a rough
  per-task total: `awk -F'duration_ms=' '{split($2,a," "); sum+=a[1]} END {print sum"ms"}' var/audit.log`
- Group by task type (e.g., "small feature" vs. "schema refactor") using the session/detail fields

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
- `var/audit.log` has one line per tool call already — `grep 'tool=Bash' var/audit.log | wc -l`
  vs. total lines gives Bash share; `grep 'tool=Skill'` gives skill-call frequency
- Count tool calls per task: `awk -F'tool=' '{split($2,a," "); print a[1]}' var/audit.log | sort | uniq -c`
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
- `grep 'status=error' var/audit.log` surfaces tool-level failures, including permission
  denials the hook payload marked as errored (`tool_response.is_error`); cross-reference the
  timestamp against the session transcript for the actual denial reason (the audit log doesn't
  capture *why*, only *that* it failed)
- Redirects aren't a distinct logged event — cross-reference `tool=Agent` dispatch entries
  against handoff report text ("route to X") until a dedicated redirect log line is added
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

## Part 6.5: Model Tiers by Agent (2026-07-17)

Not every agent needs the same model — reasoning depth should match the task's actual
ambiguity, not default uniformly to one tier:

| Agent | Model | Why |
|-------|-------|-----|
| `backend-engineer` | Sonnet | Production code, design tradeoffs, edge cases |
| `frontend-specialist` | Sonnet | Templates + Alpine + accessibility judgment calls |
| `pytest-writer` | Sonnet | Subtle: reward-hacking prevention, test structure |
| `docs-writer` | Sonnet | Prose quality + verifying examples against source |
| `database-specialist` | Sonnet | Schema/index/normalization tradeoffs are genuinely subtle |
| `lorecraft-code-reviewer` | **Opus** | Adversarial review needs deep reasoning: is this policy leaking into Tier 1? Is this actually idiomatic for this codebase, or just different? |
| `research-planner` | **Opus** | Design precedent + feasibility + tier classification benefits from the deepest available reasoning — mistakes here propagate into every downstream agent's work |
| `integrator` | **Haiku** | Mechanical: checklist verification, version arithmetic, CHANGELOG heading moves — doesn't need Sonnet-level reasoning |
| `test-qa` | Haiku | Reads structured test output, doesn't author code |

**Rationale for the two upgrades:** `lorecraft-code-reviewer` and `research-planner` sit at
points where a shallow pass costs the most downstream — a review that misses a Tier 1/Tier 2
policy leak, or a design analysis that misclassifies tunability, produces work for multiple
other agents to redo. Opus's extra reasoning is worth the token cost specifically at these two
gates, not everywhere.

**Rationale for the one downgrade:** `integrator`'s job (Pre-merge checklist, version bump
arithmetic, CHANGELOG heading move) is close to deterministic — Haiku's reasoning is sufficient
and the higher volume of small release tasks makes the token savings worth it.

---

## Part 7: Automated Hooks (2026-07-17)

Several rules that used to live only in AGENTS.md — and depended on an agent remembering to
follow them — are now enforced automatically by hooks (`.claude/hooks/`, wired via
`.claude/settings.json`). Hooks run **outside the token budget entirely**: they're shell
commands the harness executes directly around a tool call, not something the model reasons
about or pays for. This means they fire unconditionally, every time, for every agent (main
session or subagent) — the exact property you want for a "never forgotten" rule.

| Hook | Fires on | Replaces this manual AGENTS.md rule | Script |
|------|----------|--------------------------------------|--------|
| Auto-format/lint | `PostToolUse`, any Edit/Write to a `.py` file under `src/`/`tests/` | "run `make lint`" / style consistency | `format-lint.sh` |
| Audit logging | `PreToolUse` + `PostToolUse`, every tool call | (new capability — see Part 3) | `audit-log-pre.sh` + `audit-log-post.sh` |
| Scripting-docs regen | `PostToolUse`, any Edit/Write to a `.py` file containing `register_spec(` | "regenerate the builder-guide reference in the same commit: `make scripting-docs`" | `scripting-docs-check.sh` |
| CodeGraph refresh | `PostToolUse`, any Edit/Write to a `.py` file under `src/` (only if `.codegraph/` already exists) | "After code changes, run `make ai-graph`" | `graph-refresh.sh` |

**2026-07-18 update — lint/format is now a closed loop, not just automated.** `format-lint.sh`
originally only auto-fixed and reformatted silently. It now also runs a check-only `ruff check`
pass after `--fix` and prints anything left over (by definition, non-autofixable — a real
finding, not a style nit) directly into the hook output the editing agent sees immediately.
Combined with agent definitions that already prohibit running `ruff`/`make lint` themselves
(`backend-engineer`, `frontend-specialist` — no Bash tool at all; explicit "don't run lint"
text), this means **no agent should ever spend a tool call on linting or formatting** — the hook
produces the fix (free) and the remaining-findings list (free); the agent's only job is to read
that list and fix what it says. `test-qa.md`'s `make lint` target is now explicitly scoped as a
pre-merge/CI-parity safety net, not a routine per-task check — see that agent's definition for
the reasoning (a clean run is now the expected default, not something to proactively verify).

**Design notes:**
- All four are **fail-open**: any missing tool, wrong file type, or unexpected error exits 0
  silently rather than blocking the agent's edit. A hook should never be the reason a legitimate
  edit fails.
- `scripting-docs-check.sh` and `graph-refresh.sh` are debounced (5s / 10s) so a burst of edits
  in one turn triggers one regen, not one per file.
- `format-lint.sh` stays silent on an already-clean file with no remaining findings — it only
  prints when there's something to act on (a reformat happened, or a non-autofixable finding
  remains), keeping hook noise low.
- AGENTS.md's Workflow/Testing sections still state these rules in prose — that's intentional
  documentation of intent, not redundant with the hook. The hook is the enforcement; the prose
  is why it exists. If the hook and the prose ever disagree, trust the hook (it's what actually
  ran) and fix the prose.

**What did *not* move to a hook (and why):** version bumps + CHANGELOG updates stay manual
(Integrator's job) — deciding *whether* a change warrants a minor vs. patch bump requires
judgment (was this a `feat:` or a `fix:`?) that a shell script can't reliably infer from a diff
alone. Data-driven-config and Tier 1/Tier 2 boundary rules also stay as agent-definition
guidance rather than hooks — those are design judgment calls (does this value belong in YAML or
does it need to be live-tunable? does this Tier 1 function actually encode one feature's
opinion?), not mechanical checks a script can enforce with confidence. `test_tier_boundaries.py`
already exists as the mechanical backstop for the one part of that ruleset (import direction)
that *can* be checked automatically.

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
