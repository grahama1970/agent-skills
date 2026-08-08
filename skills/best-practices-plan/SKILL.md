---
name: best-practices-plan
description: >
  Best practices for orchestration-ready task files. Enforces adversarial testing,
  skill chain syntax, definition-of-done requirements, gate definitions, persona
  routing, and /model directives. Referenced by /plan and /review-plan.
triggers:
  - plan best practices
  - task file conventions
  - plan conventions
  - plan rules
  - task file rules
  - how to write tasks
provides:
  - plan-conventions
  - plan-linting
composes:
  - memory
  - agentic-evals
taxonomy:
  - precision
metadata:
  short-description: Conventions for orchestration-ready task files
  version: "1.0.0"
disciplines:
  - engineering-standards
  - agentic-orchestration
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Best Practices: Task Plans

Conventions for `0N_TASKS.yaml` files that `/plan` produces and `/orchestrate` executes.
`/review-plan` validates these rules. `/plan` MUST follow them. No exceptions.

**YAML is the source of truth.** Every task MUST have: `id`, `title`, `lane`, `runner`,
`backend`, `mode`, `depends_on`, `definition_of_done`. Plans without these fields will
fail `/review-plan` validation and `/orchestrate` will refuse to execute them.

## Rule 1: Adversarial Testing (NON-NEGOTIABLE)

Every implementation task MUST have a **blind test that the coding agent cannot see**.

This is not optional. This is not "nice to have". The coding agent that implements
the code MUST NEVER see the test source, test assertions, or expected values. The
agent sees ONLY the test output: pass/fail and failure descriptions.

### Why blind?

ImpossibleBench (arXiv:2510.20270) showed GPT-5 cheats 76% of the time when it can
see tests, but near-zero when tests are hidden. If the agent can read the test, it
optimizes for passing the test rather than actual correctness. **The test is an
adversary — an adversary you can see is no adversary at all.**

### What makes a test adversarial?

1. **The implementing agent CANNOT view or modify the test source**
2. **The test is generated/maintained by a separate process** (`/test-lab`)
3. **The agent sees ONLY pass/fail output** — no assertion code, no expected values
4. **The test can distinguish a correct implementation from a broken one**

```
# GOOD — blind: agent sees only output, not the test code
test-lab/run.sh run .pi/skills/stop-gates/ --domain skills

# GOOD — blind: hidden tests generated from the plan
test-lab/run.sh verify-task 3.1 .pi/extensions/ --max-retries 3

# GOOD — blind: sanity.sh is a pre-existing harness the agent doesn't write
./sanity.sh  # exits 0 or fails with description

# BAD — agent writes AND runs its own test (can game it)
uv run pytest tests/test_auth.py  # if agent wrote test_auth.py, it's not adversarial

# BAD — confirms existence, not correctness
ls .pi/extensions/stop-gates.ts  # File could be empty

# BAD — vague
"verify it works"
```

### Template

Every implementation task should include:

```markdown
- **Test**: `/test-lab verify-task <task-id> <target>` OR `sanity.sh` exits 0
- **Blind**: Agent cannot view test source — sees only pass/fail output
- **Catches**: <specific failure mode the test detects>
```

Example:
```markdown
- **Test**: `test-lab/run.sh verify-task 3.1 .pi/extensions/ --domain skills`
- **Blind**: Agent sees only "FAIL: quality gate did not block commit without tests"
- **Catches**: Missing quality gate — if stop-gates.ts is broken, commit goes through
```

## Rule 2: Skill Chain Syntax

Tasks SHOULD reference skills with `/skill-name` notation. Natural language without
explicit chains gets flagged for Tier 3 routing (slower, less reliable).

```
# GOOD — explicit chain, unambiguous
Use /memory recall then /assess findings then /plan next steps

# BAD — natural language, requires inference
Check memory and then assess what we found
```

When voice is the input channel, the human speaks `/slash` as "slash":
```
Brandon, slash assess your CMMC posture
```

## Rule 3: Definition of Done

Every implementation task MUST have a DoD with:

1. A **runnable command** (not prose)
2. A **concrete assertion** (not "it works")
3. An **exit code check** (exits 0, or specific output)

```
# GOOD
- **Definition of Done**: `uv run pytest tests/test_gate.py -x` exits 0

# GOOD
- **Definition of Done**: `./run.sh review plan.md --json | jq .fail` returns 0

# BAD
- **Definition of Done**: Verify the gate works correctly

# BAD
- **Definition of Done**: Feature is implemented
```

## Rule 4: Gate Definitions

Every implementation task MUST have a Gate field — what must be true before the
task can be considered complete.

```
- **Gate**: `echo "git commit" | pi -p 2>&1 | grep -q "BLOCKED"` — commit blocked without tests
```

## Rule 5: Persona Routing

Tasks involving persona agents MUST specify the persona:

```
# GOOD
Brandon /assess CMMC posture
@brandon-bailey: assess CMMC posture

# BAD
Have someone check CMMC
```

## Rule 6: `/model` Directive and `with <model>` Routing

Tasks with cost sensitivity SHOULD specify a model. Use `with <model>` syntax for per-step routing:

```
# GOOD — per-step model routing
- skill: /assess with codex
- skill: /dogpile with claude
- skill: /create-react-designs with gemini

# GOOD — command-level default
/orchestrate run tasks.md with codex

# GOOD — cost-sensitive inline directive
/model haiku
Use /memory recall to check for prior solutions

# OK (defaults to session model)
Use /memory recall to check for prior solutions
```

### Model Selection Guidance

| Model | Best For |
|-------|----------|
| `codex` | Debugging, complex reasoning, code generation |
| `gemini` | UI design, visual tasks, multimodal |
| `claude` | Simple coordination, cheap/fast steps |
| `deepseek` | Batch extraction, cost-sensitive LLM work |
| `pi` | Full orchestration features (parallel, pause/resume) |

### Precedence

1. Step-level `with <model>` — highest
2. Command-level `with <model>` — default for all steps
3. Auto-detect — fallback

## Rule 7: Skill Overlap Check

Tasks MUST NOT propose building functionality that an existing skill provides.
Before writing a task, check `skills-manifest.json` or `/memory recall "skill:<capability>"`.

```
# BAD — /fetcher already does this
## Task 3: Build a web page scraper

# GOOD — uses existing skill
## Task 3: Use /fetcher to extract content from target URLs
```

## Rule 8: Phase Ordering

- Blocking tasks MUST come before dependent tasks
- Parallelizable tasks SHOULD be grouped
- Every phase SHOULD have a time estimate

## Rule 9: UI Development Pipeline (NON-NEGOTIABLE)

**NEVER write production React/TSX views directly.** All UI work MUST go through the
full design pipeline. No shortcuts. No "rough drafts". No "I'll clean it up later".

### The Pipeline (ALL steps required, IN ORDER)

1. `/plan` — Task file with Phase 0 skill discovery, capability overlap, DoD
2. `/review-plan` — Validate task file before proceeding
3. `/ux-lab` — Design and iterate the component in the workbench
4. `/review-design --persona nico-bailon` — Get persona feedback on screenshots
5. `/test-interactions --persona nico-bailon` — Validate keyboard workflow
6. **THEN** write production TSX

### Why?

On 2026-03-12, 560 lines of QuarantineView.tsx were blurted out bespoke — no `/plan`,
no manifest, no `/ux-lab`, no `/review-design`, no `/test-interactions`. Every single
quality gate was bypassed. This is the worst-case anti-pattern: agents writing UI code
that skips the entire design pipeline.

### What triggers this rule?

- New views
- Significant rewrites of existing views
- Adding new tabs or panels to existing views
- Any UI change that affects layout or interaction patterns

### What does NOT trigger this rule?

- Bug fixes to existing components (typos, broken imports, CSS tweaks)
- Adding a prop or event handler to an existing component
- Non-visual code (API routes, data models, utilities)

### `/orchestrate` enforcement — NO STEP COLLAPSING

On 2026-03-14, `/orchestrate` collapsed the pipeline into single agents that wrote
6,458 lines of production TSX across 7 views, skipping `/review-design` and
`/test-interactions` entirely. Review/interaction tasks were marked "COMPLETE —
designs match approved mockups" without actually running Playwright. This is the
same anti-pattern at scale.

**`/orchestrate` MUST NOT:**
- Mark review/interaction tasks as complete without actually running Playwright
- Collapse design + review + interaction + production-write into a single agent
- Allow production code to be written in the same task as design iteration
- Declare "designs match approved mockups" as a substitute for running `/review-design`
- Put design, review, interaction, and production-write in the same Parallel group

**Task file structure that enforces this (REQUIRED for UI tasks):**

```
Task N:   Write TSX draft in /ux-lab           → Parallel: X
Task N+1: /review-design (Playwright screenshots) → Parallel: X+1, depends: Task N
Task N+2: /test-interactions (Playwright tests)    → Parallel: X+1, depends: Task N+1
Task N+3: Write production TSX from approved design → Parallel: X+2, depends: Task N+2
```

Each step MUST be a **separate task** with **separate Parallel group** and **explicit
dependency** on the prior step. This prevents `/orchestrate` from collapsing them.

### `/review-plan` enforcement

`/review-plan` MUST flag as **FAIL** any task that:
- Produces `.tsx` or `.jsx` files without referencing `/ux-lab` in a prior task
- References "create component" or "build view" without the design pipeline
- Has DoD that says "component renders" without `/review-design` approval
- Puts design, review, interaction, and production-write in the same Parallel group
- Has a production-write task that does not depend on a `/test-interactions` task

## Rule 10: Persona-Driven Requirements (NON-NEGOTIABLE)

Every `/plan` MUST identify **who uses the thing being built** and involve that
persona in requirements gathering. A plan without a persona is a plan built for
nobody.

### Why?

On 2026-03-13, a /learn-datalake viewer plan was written without consulting the
Nico Bailon persona — the person who would use the quarantine queue 8 hours a day.
The agent wrote requirements from its own perspective instead of the user's. This
produces interfaces nobody wants to use.

### The rule

1. **Every task file MUST have a `## Primary Persona` section** naming the persona
   who will use the feature being built
2. **Requirements MUST come from the persona's perspective** — what does THEIR
   workflow look like? What do THEY need? What's THEIR day?
3. **The persona MUST be involved in `/review-design`** and **`/test-interactions`**
4. **For UI work**: the persona's `viewer_priorities` and `qa_workflow` from their
   persona YAML drive the requirements, not the agent's assumptions

### What triggers this rule?

- ALL plans. Every feature is built for someone. Name them.
- Infrastructure/plumbing tasks: the persona is the developer who maintains it
- UI tasks: the persona is the end user who sits in front of it
- Pipeline tasks: the persona is the operator who monitors it

### `/review-plan` enforcement

`/review-plan` MUST flag as **FAIL** any task file that:
- Has no `## Primary Persona` section
- Describes UI requirements without referencing a persona's workflow
- Uses `/review-design` or `/test-interactions` without specifying `--persona`

## Rule 11: MEMORY.md Is Not Aspirational

Agent MUST read and follow MEMORY.md, feedback memories, and project memories
before writing any code. These are not suggestions — they are rules from prior
sessions that exist because the agent already made the mistake once.

### Why?

Every feedback memory exists because the agent ignored a rule, the user corrected
it, and the correction was stored. Ignoring stored corrections means the user has
to repeat themselves indefinitely. This is the definition of a broken agent.

### What this means in practice

1. **Before writing code**: Check if relevant feedback memories exist
2. **Before designing UI**: Check feedback_uxlab_first.md (Rule 9 above)
3. **Before any significant action**: Check if MEMORY.md has context on the current project
4. **If a memory says "don't do X"**: Don't do X. Period.

### `/review-plan` enforcement

`/review-plan` SHOULD flag as **WARN** any task file where:
- The plan contradicts known feedback memories
- The plan proposes an approach that was previously rejected

## Rule 11: No Exceptions

These rules apply to ALL task files consumed by `/orchestrate`. There are no
"quick and dirty" exceptions. A plan without adversarial tests is a plan that
wastes agent time on broken implementations.

The cost of writing a test is 30 seconds. The cost of a broken implementation
cascading through 5 dependent tasks is hours.

## Example: Well-Formed Task

```markdown
### Task 3.1: Create stop-gates.ts extension

- **What**: Block `git commit` if tests haven't passed this session
- **Why**: Claude Code's quality-gate.sh Stop hook needs a Pi equivalent
- **Implementation**:
  1. Listen on `tool_result` for pytest/npm test success
  2. Listen on `tool_call` for `git commit` — block if no test passed
  3. Register `/quality-gate` diagnostic command
- **File**: `.pi/extensions/stop-gates.ts`
- **Test**: `echo "run git commit -m test" | pi -p 2>&1 | grep -q "BLOCKED"`
- **Adversarial**: Catches missing quality gate — commit goes through without tests
- **Gate**: Agent cannot commit if tests haven't passed this session
- **Definition of Done**: `echo "run git commit" | pi -p 2>&1 | grep -q "BLOCKED"` exits 0
```

## Rule 12: Anti-Silo Rules (NON-NEGOTIABLE)

Before creating new code, check if an existing skill/module already does it:

1. **New retrieval/search** → MUST be a RecallSource in `/memory`, NOT standalone
2. **New tag extraction** → MUST use `/taxonomy`, NOT reimplemented
3. **New data storage** → MUST use ArangoDB via existing `arango_client.py`
4. **New quality assessment** → MUST compose `/review-*` or `/reality-check-*`
5. **New intent/routing** → MUST compose `/memory intent`
6. **New screenshot/rendering** → Check `/pdf-screenshot`, `pdf_bridge.render_page_image()`
7. **New LLM prompts** → MUST go through `/prompt-lab` for evaluation
8. **New convergence loops** → MUST follow Convergence Loop Rules below

Every task file MUST have a `capability_overlap` section documenting what was checked.

## Rule 13: Convergence Loop Rules

Any plan with iterative improvement loops MUST satisfy:

1. **Dual rationale** — two-persona loops need first-person rationale from BOTH
2. **Active remediation** — what changes between rounds? Who makes the change?
3. **Module separation** — loop orchestrator and dialogue in separate files (800-line limit)
4. **Context isolation** — large artifacts use `/subagent-service` for protected context

## Rule 14: Phase 0 Skill Discovery (BLOCKING GATE)

Before ANY planning:

1. `/memory recall` — check prior solutions
2. `skills-manifest.json` — find composable skills
3. `/assess` — read target codebase

Decision matrix:

| /memory recall | Skill match | Action |
|----------------|-------------|--------|
| Strong match | Covers it | **STOP** — use existing |
| Partial match | 60%+ | **EXTEND** existing |
| Weak match | No match | **PROCEED** |

## Integration

| Skill | Relationship |
|-------|-------------|
| `/plan` | MUST consult this skill when generating task files |
| `/review-plan` | VALIDATES these rules against task files |
| `/orchestrate` | REFUSES to execute task files that fail `/review-plan` |
| `/best-practices-skills` | Complementary: this is for plans, that is for skills |
