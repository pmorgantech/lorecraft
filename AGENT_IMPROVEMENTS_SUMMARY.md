# Agent Infrastructure Improvements (2026-07-17)

**Commit:** 8bbfb3c
**Summary:** Added Skill routing capability to agents, disambiguated code-reviewer naming, and created comprehensive metrics framework.

---

## What Changed

### 1. Skill Tool Access (Now in 8 agents)

All implementation and verification agents can now call skills directly:

| Agent | Tools Before | Tools After | Benefit |
|-------|--------------|-------------|---------|
| backend-engineer | Read, Edit, Write, Grep, Glob | + **Skill** | Self-validate via `/code-review` or `/verify` before handoff |
| frontend-specialist | Read, Edit, Write, Grep, Glob, **Bash** | **- Bash** + **Skill** | UI-only agent no longer needs shell; can call `/verify` |
| pytest-writer | Read, Edit, Write, Grep, Glob, Bash | + **Skill** | Self-validate test quality via `/code-review` or recursive `/test-writer` |
| test-qa | Read, Grep, Bash | + **Skill** | Route failures via `/verify` for focused checks |
| docs-writer | Read, Edit, Write, Grep, Glob, Bash | + **Skill** | Call `/code-review` to validate code examples; `/kindle-doc-weaver` to export |
| database-specialist | Read, Grep, Glob, Bash | + **Skill** | Self-validate schema patterns via `/code-review`; test migrations via `/verify` |
| research-planner | Read, Grep, Glob, Bash | + **Skill** | Optional `/code-review` of design analysis; `/verify` feasibility |
| integrator | Read, Edit, Grep, Bash | + **Skill** | Final `/code-review` pass before merge; `/lorecraft-orchestration` for multi-agent releases |

**Result:** Agents can now self-route for validation without requiring parent-session oversight. Reduces back-and-forth; keeps workflow tighter.

### 2. Code-Reviewer Renamed to Lorecraft-Code-Reviewer

**Why:** The agent name `code-reviewer` shadowed the skill name `code-review`, creating dispatch confusion.

| Old | New | Effect |
|-----|-----|--------|
| Agent: `code-reviewer` | Agent: `lorecraft-code-reviewer` | Unambiguous agent reference |
| Skill: `code-review` | Skill: `code-review` (unchanged) | Skill name stays clear |
| Files: `.claude/agents/code-reviewer.md` | `.claude/agents/lorecraft-code-reviewer.md` | File renamed; old file deleted |

**No behavior change:** Same advisory-only role (Read/Grep/Glob, no Edit). Just a name clarity fix.

### 3. Frontend-Specialist No Longer Has Bash

| Reason | Detail |
|--------|--------|
| **Not needed** | Frontend agent only writes templates/JS/CSS; no shell tasks in spec |
| **Consistency** | Other implementation agents (backend-engineer) don't have Bash either |
| **Clarity** | Tool list now reflects agent's lane: Read, Edit, Write, Grep, Glob, **Skill** |

### 4. New: Metrics & Routing Framework

**File:** `docs/AGENT_ROUTING_AND_METRICS.md` (286 lines)

#### Decision Trees

- **Agent routing:** Which agent for which task type (backend, frontend, tests, reviews, docs, etc.)
- **Skill routing:** Which skills agents should call by role (backend-engineer → code-review, verify, test-writer, worldbuilding)
- **Skills to avoid:** Which skills to route elsewhere (ci-writer, dockerfile-writer, etc.)

#### Four Key Metrics

1. **Routing Accuracy** — Did the task land with the right agent initially? Target: >95% first-dispatch.
2. **Execution Time** — How long per agent type? Baseline: 10 min (simple), 30–60 min (medium), 90–120 min (complex).
3. **Tool Usage Patterns** — Which tools dominate? Flag if Bash >5%, Skill <20% (under-used), or unexpected patterns.
4. **Error Rates & Redirects** — Permission blocks, mid-task redirects, redirect categories. Target: <5% total redirects.

#### Monthly Review Checklist

- [ ] Routing accuracy: sample 5–10 tasks
- [ ] Execution time: aggregate by agent type, flag >25% regression
- [ ] Tool usage: confirm Bash <5%, Skill >20%
- [ ] Redirects: categorize, ensure <5% rate
- [ ] Permission blocks: any new blocks to resolve
- [ ] Skill discovery: remind teams, update if new skills land
- [ ] Decision tree: update AGENTS.md if responsibilities shifted

#### Example Trace

"Add charisma stat to character sheet UI" walked through 7 agents over 71 minutes, with metrics logged at each step.

---

## How to Use This

### For Dispatching Tasks

1. **Consult the decision tree** in `docs/AGENT_ROUTING_AND_METRICS.md` Part 1
2. **Dispatch the primary agent** with a clear scope briefing
3. **Let agents call skills** as needed (they have Skill tool now)
   - Example: backend-engineer may call `/verify` before handing to frontend-specialist
   - Example: pytest-writer may call `/code-review` to flag suspicious test patterns to lorecraft-code-reviewer

### For Tracking Metrics

1. **Log dispatch & completion** with timestamps
2. **Tag agent & task type** for aggregation
3. **Note redirects** if any (expected or unexpected)
4. **Monthly checkpoint** using the checklist (1st of each month)

### For Understanding Skill Routing

- **Backend Engineer** can call: `code-review`, `test-writer`, `verify`, `worldbuilding`
- **Frontend Specialist** can call: `code-review`, `verify`, `dataviz`
- **Pytest Writer** can call: `code-review`, `test-writer`, `verify`
- **Etc.** — See Part 2 for role-by-role recommendations

---

## Impact on Workflow

### Before

- Agent finishes code → hands off to *different* agent for review
- Review agent finds issues → returns to original agent
- Original agent fixes → re-routes to review agent again
- **Cadence:** code → review → fix → re-review (multiple round trips)

### After

- Agent finishes code → calls `/code-review` or `/verify` themselves (optional)
- If self-review looks good → hands off to lorecraft-code-reviewer once (not twice)
- If issues found → agent fixes and re-runs skill (no re-handoff needed)
- **Cadence:** code → self-check → submit → independent review (fewer round trips)

**Net effect:** Faster validation, cleaner handoffs, better visibility into work quality.

---

## Next Steps (Recommended)

### Immediate (This Sprint)

- [ ] Update dispatch workflows to reference new decision tree
- [ ] Train agents on available skills (reminder in agent briefings)
- [ ] Start tracking metrics for a representative week

### Short Term (Next 2 Sprints)

- [ ] Run first monthly metrics review (1st of August)
- [ ] Adjust decision tree if routing patterns emerge
- [ ] Add agent redirect logs to session summaries

### Longer Term

- [ ] Build metrics dashboard (automation)
- [ ] Correlate routing accuracy with feature velocity
- [ ] Refine skill recommendations based on actual usage patterns

---

## Files Changed

```
.claude/agents/backend-engineer.md              (added Skill)
.claude/agents/database-specialist.md           (added Skill)
.claude/agents/docs-writer.md                   (added Skill)
.claude/agents/frontend-specialist.md           (removed Bash, added Skill)
.claude/agents/integrator.md                    (added Skill)
.claude/agents/code-reviewer.md                 (RENAMED → lorecraft-code-reviewer.md)
.claude/agents/pytest-writer.md                 (added Skill)
.claude/agents/research-planner.md              (added Skill)
.claude/agents/test-qa.md                       (added Skill)
docs/AGENT_ROUTING_AND_METRICS.md               (NEW, 286 lines)
```

---

## Questions?

- **"When should an agent call a skill vs. just do the work?"**
  → See Part 2 recommendations. Optional for self-checks; required for cross-domain validation.

- **"Does this slow down work (more tool calls)?"**
  → No — agents already have these tools in the harness. Skill tool just unlocks self-routing. Most agents will call skills 0–2 times per task (optional), not per line of code.

- **"How do I track metrics in my own workflow?"**
  → See Part 3 "How to capture" sections. Minimal: timestamp dispatch/completion + tag agent/type. A spreadsheet or simple log suffices to start; automate later if patterns emerge.

- **"Do existing agents need retraining?"**
  → Not really. Skill tool is opt-in. Agent definitions emphasize role-based skills (Part 2), but "use if you find it helpful" is the vibe. Frontend-specialist: clarify Bash removal so no one tries to run shell commands. Lorecraft-code-reviewer: same agent role, just a name that doesn't shadow the skill.
