---
name: plan
description: >
  Create orchestration-ready YAML task files (0N_TASKS.yaml) for /orchestrate.
  Decomposes goals into tasks with explicit runner, backend, mode, and lane fields.
  Supports code-only, design-only, and hybrid plans. Use when user says "plan this",
  "create task file", "break this down into tasks".
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, AskUserQuestion
triggers:
  - plan this
  - create task file
  - break this down
  - prepare tasks
  - plan implementation
  - create 0N_TASKS
  - task breakdown
  - decompose this
  - let's plan
metadata:
  short-description: Create orchestration-ready YAML task files
provides:
  - task-planning
composes:
  - memory
  - assess
  - task-monitor
  - best-practices-plan
  - review-plan
  - recommend-skill-chain
  - orchestrate
read_before_use:
  - plan.py
  - design_pipeline.py
  - interviews.py
taxonomy:
  - orchestration
  - planning
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# /plan

Create YAML task files that `/orchestrate` executes directly. No markdown intermediate.

**Before writing any plan, read `/best-practices-plan`** — it has the rules this skill enforces.

## Workflow

The full pipeline is: `/plan` → `/review-plan` → `/orchestrate`. The agent runs all three
when the user says `/plan`. The user only needs to say `/plan` once.

```
1. /memory recall     — Check if this problem was already solved
2. SKILL DISCOVERY    — Find existing skills that do what's needed (BLOCKING)
3. /assess            — Read the target codebase
4. Identify persona   — WHO uses this? Name them.
5. Decompose          — Break into tasks with runner/backend/mode
6. Output YAML        — Write 0N_TASKS.yaml
7. plan.py --dag      — Show execution DAG to human for approval
8. plan.py --validate — Schema validation
9. /review-plan       — Full validation (claims, routing, blind tests, overlap)
10. If PASS → ask human: "Plan ready. Run /orchestrate?"
11. If human approves → /orchestrate run 0N_TASKS.yaml
```

### Step 2: Runner Selection (which tasks get /code-runner)

Not every task needs `/code-runner`. **Code-runner is EXPENSIVE** — worktree isolation,
git commit/revert cycle, multi-round LLM loop, T0 scoring, memory learning. Most tasks
are simpler than that.

**Runner is auto-routed if left empty.** Set it explicitly only when the heuristic is wrong.

| Runner | When to use | Auto-routed when | Example |
|--------|-------------|------------------|---------|
| `local` | Shell command, no LLM needed | Has `command`, no `prompt` | `pytest`, `npm install`, `ruff check --fix` |
| `scillm` | One-shot LLM call, simple edit | Has `prompt`, no `allowlist`+DoD assertion | Add a field, rename variable, generate docstring, classify |
| `code-runner` | Complex bounded code task with verification | Has `prompt` + `allowlist` + DoD `assertion` | Fix multi-file bug, implement feature with test suite |

**Use code-runner ONLY when ALL of these are true:**
- The task writes/edits 1-3 specific files (use `allowlist`)
- There's a runnable DoD command with a verifiable assertion
- The fix may need multiple attempts (not a mechanical edit)
- Dependencies are known and listed in `read_context`
- **The DoD command does NOT require a live server** (code-runner uses git worktree isolation — the running dev server serves from the main working directory, not the worktree)

**NEVER use code-runner when the DoD calls a live HTTP endpoint** (e.g. `curl http://localhost:3001/...`).
Code-runner edits files in an isolated worktree. The dev server doesn't see those edits.
The DoD `curl` will always hit the OLD code and fail. Use `scillm` (one-shot edit to the
working directory) + a separate `local` task to restart the server and verify with `curl`.

**Use scillm (not code-runner) for:**
- Mechanical edits: add a field, update an import, rename a variable
- Config changes: update YAML, add an entry to a list
- Text generation: docstrings, summaries, classifications
- Any task where "just do it once, correctly" is sufficient
- **Server endpoint code where the DoD requires `curl` to a live server** — edits must land in the working directory, not a worktree

**Use local for:**
- Running tests, linters, formatters, build commands
- File operations: copy, move, create directories
- Anything that's a shell command, not LLM reasoning

**code-runner fields the project agent must provide:**
- `allowlist` — files the LLM can write (scope boundary)
- `read_context` — files the LLM should read for interface context (NOT write)
- `definition_of_done` — runnable verification command with assertions
- `blind_tests` — hidden assertions in `/test-lab` (required for code-runner, enforced by /review-plan)

### Step 3: Skill Discovery (BLOCKING — do NOT skip)

Before writing ANY task, check if an existing skill already does it. The agent MUST NOT
write bespoke code when a skill exists. This is the #1 source of architectural debt.

**How to check:**

```bash
# Search the manifest (fastest — one file, all 225+ skills)
cat ~/.pi/skills-manifest.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for s in data['skills']:
    d = (s.get('description') or '').lower()
    if any(kw in d for kw in ['cache', 'redis', 'api']):
        print(f'  /{s[\"name\"]}: {s[\"description\"][:100]}')
"

# Or search skill names directly
ls ~/.pi/skills/ | grep -i cache

# Or ask memory
/memory recall "skill:caching" OR "skill:redis"
```

**Decision for each piece of work:**

| Existing skill covers it? | Action |
|---------------------------|--------|
| Yes, fully | CALL the skill. Do NOT rewrite it. |
| Yes, 60%+ | EXTEND the skill. Add what's missing. |
| No match | CREATE new code — but document WHY in capability_overlap. |

Every task in the YAML should map to CALL, EXTEND, or CREATE. If the plan is mostly
CREATE, you haven't looked hard enough. `/review-plan` will flag tasks that overlap
with existing skills as FAIL.

### Step 4: Compliance Governance (BLOCKING for SPARTA/CAE plans)

Plans that involve CAE (Claims-Arguments-Evidence) trees, SPARTA controls, compliance
verdicts, or posture assessments MUST enforce "analyst workbench, not truth engine":

**Non-negotiable rules:**

| Requirement | Implementation |
|-------------|----------------|
| NEEDS_VERIFICATION default | All CAE claims/verdicts default to NEEDS_VERIFICATION, never auto-PASS |
| Human review gate | Every posture change requires compliance officer review before status change |
| No autonomous certification | Agent NEVER writes "certified", "compliant", "approved" without human gate |
| Retrieval language only | Use "retrieved", "found", "extracted" — never "determined", "verified", "confirmed" |

**In YAML plans, add to metadata:**

```yaml
metadata:
  compliance_governance:
    principle: "Analyst workbench, not truth engine"
    verdicts: "All default to NEEDS_VERIFICATION"
    human_gate: "Compliance officer reviews before status change"
```

**In task prompts, include:**

```
COMPLIANCE GOVERNANCE: This is an analyst workbench, not a truth engine.
- All verdicts default to NEEDS_VERIFICATION
- Human reviews before any status change
- Use retrieval language ("retrieved", "found"), not judgment language ("verified", "confirmed")
```

`/review-plan` will FAIL plans that:
- Auto-approve verdicts without human gates
- Use "certified", "compliant", "approved" without human review step
- Missing `compliance_governance` metadata for SPARTA/CAE plans

Reference: `docs/WALKTHROUGH_QRA_COVERAGE_AND_EVIDENCE_CASES.md`

Steps 7-11 happen automatically after writing the YAML. The human only intervenes if
`/review-plan` FAILs (fix the plan) or if they want to amend the DAG before execution.

### If /review-plan FAILs

Triage each failure:

| Failure type | Action |
|---|---|
| Missing field (mode, DoD command) | Fix it yourself — no human input needed |
| Wrong runner/backend | Fix if obvious, ask human if ambiguous |
| Missing capability_overlap | Run `/memory recall` and fill it in |
| Skill overlap detected | Ask human: use existing skill or justify new code? |
| Ambiguous requirements | Use `/interview` for structured choices |
| Claims don't match codebase | Re-read the code with `/assess` |

After fixes, re-run `/review-plan`. Do NOT proceed to `/orchestrate` until PASS.
Do NOT silently skip FAILs — every FAIL must be resolved or explicitly waived by the human.

## Plan Types

Auto-detected from goal text. All types use the same YAML schema.

| Type | Detected When | Pattern |
|------|---------------|---------|
| **code** | No UI keywords | `local` for setup, `code-runner` for implementation |
| **design** | views, components, TSX, dashboard, UI, React | `/mockup-lab` (Stitch) → `/ux-lab` (code) → `/mockup-lab review` (VLM verify) → `/test-interactions` |
| **hybrid** | Both UI and code keywords | Stitch pipeline for UI views, code tasks in later waves |

### Design Plans

**Rule: The agent NEVER designs UI.** Stitch designs it. The agent codes it.

Design plans MUST specify **device type** (desktop, mobile, tablet). Pass `--device`
to every `/mockup-lab` command. Stitch defaults to mobile if not specified.

For any plan with UI work, each component follows 3 steps:

1. `/mockup-lab` — Stitch generates design, human approves (`--device desktop`)
2. `/ux-lab` — Agent codes React component from approved screenshots
3. `/mockup-lab review` — Gemini VLM verifies implementation matches design

For small changes (colors, spacing, adding a column), skip step 1 and use
`/ux-lab` + `/review-design` directly.

Read `.pi/skills/mockup-lab/design-to-code.yaml` for the detailed checklist.

**DoD for UI tasks must be visual** — "tsc compiles" is not done. Done means
a screenshot shows real data matching the approved design.

## YAML Schema

```yaml
version: 1
kind: orchestrate-plan

metadata:
  title: "Feature Name"
  goal: "one-line summary"
  plan_type: code          # code, design, or hybrid
  created: "2026-03-17"
  primary_persona:         # WHO uses this (required)
    name: "Nico Bailon"
    role: "QA Engineer"
    source: ".pi/agents/nico-bailon/AGENTS.md"

execution:
  max_concurrency: 3       # parallel lanes
  wave_barrier: false      # if true, wave N must complete before wave N+1 starts
  scheduling_policy: dependency_only  # or wave_then_dependency

capability_overlap:        # Phase 0 evidence (required)
  - "/memory recall returned: no prior Redis caching solution"
  - "Checked /fetcher, /dogpile — no overlap"

questions_blockers:
  - "None"

lanes:
  - id: "0"
    label: "Wave 0: Setup"
  - id: "1"
    label: "Wave 1: Implementation"
  - id: "2"
    label: "Wave 2: Validation"

tasks:
  - id: "1"
    title: "Add Redis to docker-compose"
    lane: "0"
    runner: "local"          # deterministic shell command
    backend: ""              # no LLM needed
    mode: ""
    depends_on: []
    command: "docker compose up -d redis && redis-cli ping"
    definition_of_done:
      command: "redis-cli ping"
      assertion: "Returns PONG"

  - id: "2"
    title: "Create cache utility module"
    lane: "1"
    runner: "code-runner"       # self-improvement loop
    backend: "codex"            # which LLM
    mode: "iterative"           # iterative/one_shot/review
    depends_on: ["1"]
    preconditions:              # checked before task dispatch
      - type: service_reachable
        url: "http://localhost:6379"
      - type: path_exists
        path: "src/"
    read_context:               # structured: path + optional line range
      - path: "src/config.py"
        start_line: 1
        end_line: 50
      - "src/types.py"          # simple string also works
    implementation:
      - "Create src/cache.py with get/set/invalidate"
      - "TTL-based expiration using Redis SETEX"
    tests:
      - "test-lab/run.sh verify-task 2 src/ --domain python"
      - "tests/test_cache.py::test_set_get_ttl"
    definition_of_done:
      command: "uv run pytest tests/test_cache.py -q"
      assertion: "Value expires after TTL"
```

## Task Fields Reference

### Runner (how the task executes)

**Leave `runner` empty** — `plan.py` auto-routes based on task shape. Set explicitly only to override.

| Runner | Auto-routed when | Required Fields |
|--------|------------------|-----------------|
| `local` | Has `command`, no `prompt` | `command` |
| `skill` | Has `skill` field set | `skill` (+ optional `skill_command`, `skill_args`) |
| `scillm` | Has `prompt`, no `allowlist` + DoD assertion | `prompt` (backend/mode auto-filled) |
| `code-runner` | Has `prompt` + `allowlist` + DoD assertion | `prompt`, `allowlist`, `definition_of_done.assertion` |

### Backend (which LLM model)

| Backend | scillm Model | Best For | Cost |
|---------|--------------|----------|------|
| `text-claude` | Claude Sonnet 4.6 (OAuth) | Boilerplate, scaffolding, monitoring | Low |
| `text-claude-opus` | Claude Opus 4.5 (OAuth) | Architecture, novel design, cross-skill composition | High |
| `gpt-5.3-codex` | OpenAI Codex (OAuth) | Code review, deep analysis, refactoring | Medium |
| `text-gemini-oauth` | Gemini via CLI (OAuth) | Long content, large context, visual tasks | Medium |
| `text` | Chutes DeepSeek (PAYG) | **Batch work** — high concurrency, no OAuth limits | Low |

**Decision heuristic**: "call existing script and check output" → `text-claude`. "understand 3 systems and wire them together" → `text-claude-opus`. "review this code" → `gpt-5.3-codex`. "batch 100 items" → `text`.

**Note:** OAuth models (`text-claude*`, `gpt-5.3-codex`) are NOT for batch — use `text` (Chutes) for high-concurrency batch work.

### Mode (execution style)

| Mode | Use For |
|------|---------|
| `iterative` | Multi-turn agent work (coding, design iteration) |
| `one_shot` | Single LLM inference (classification, extraction) |
| `review` | Review/assessment tasks |

### Execution (plan-level scheduling)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_concurrency` | int | 3 | Max parallel tasks across all lanes |
| `wave_barrier` | bool | false | If true, all wave N tasks must complete before wave N+1 starts |
| `scheduling_policy` | string | `dependency_only` | `dependency_only`: run when deps satisfied. `wave_then_dependency`: enforce wave barrier first |

Wave numbers are derived from lane IDs: lane `"0"`, `"0.1"`, `"0.2"` = wave 0; lane `"1"`, `"1.1"` = wave 1.

### Preconditions (per-task)

Checked before task dispatch. Task fails immediately if any precondition fails.

| Type | Required Field | Description |
|------|----------------|-------------|
| `path_exists` | `path` | File or directory must exist |
| `service_reachable` | `url` | HTTP GET must return 2xx |
| `env_var_set` | `var` | Environment variable must be non-empty |
| `command_succeeds` | `command` | Shell command must exit 0 |

```yaml
preconditions:
  - type: service_reachable
    url: "http://localhost:6379"
  - type: path_exists
    path: "src/config.py"
  - type: env_var_set
    var: "DATABASE_URL"
  - type: command_succeeds
    command: "docker ps | grep -q postgres"
```

### Structured read_context

Files the LLM reads for context but does NOT write. Supports line ranges to reduce prompt size.

```yaml
read_context:
  - "src/types.py"                    # full file (string)
  - path: "src/config.py"             # structured: full file
  - path: "src/large_module.py"       # structured: lines 100-200 only
    start_line: 100
    end_line: 200
```

## Usage

```bash
# Emit YAML template
plan.py

# Validate existing plan
plan.py --validate 01_TASKS.yaml

# Visualize execution DAG (waves, parallelism, routing)
plan.py --dag 01_TASKS.yaml

# Output DAG as Mermaid flowchart (for docs/PRs)
plan.py --mermaid 01_TASKS.yaml

# Convert legacy markdown to YAML
plan.py --convert 01_TASKS.md -o 01_TASKS.yaml

# Render YAML as markdown (for human review)
plan.py --render 01_TASKS.yaml

# Add a task to an existing plan (auto-assigns ID, wires deps)
plan.py --add-task 01_TASKS.yaml "title=Run integration tests|runner=local|lane=2|depends_on=2|command=pytest tests/"

# Remove a task (cleans up dangling deps)
plan.py --remove-task 01_TASKS.yaml:3

```

## Pipeline Position

```
/plan → /review-plan → /orchestrate
```

For design plans, the execution pipeline inside `/orchestrate` is:

```
/mockup-lab generate → /interview (human review) → /mockup-lab iterate
      ↓ approved design
/ux-lab (code React component)
      ↓ built component
/mockup-lab review (Gemini VLM visual diff)
      ↓ match_score < 90 → fix code → re-review
      ↓ match_score >= 90 → done
/test-interactions (verify interactions)
```

| Skill | Role |
|-------|------|
| `/best-practices-plan` | Rules this skill MUST follow (read first) |
| `/review-plan` | Validates the YAML before `/orchestrate` runs it |
| `/orchestrate` | Executes the YAML with per-task dispatch |
| `/test-lab` | Generates blind adversarial tests (required per task) |
| `/memory` | Phase 0: check for prior solutions |
| `/assess` | Phase 0: read the target codebase |
| `/interview` | Gather requirements when goal is ambiguous |
| `/dogpile` | Research unfamiliar dependencies |
| `/mockup-lab` | Design generation (Stitch) + VLM review (scillm) for UI plans |
| `/ux-lab` | React component development with Vite HMR |

## Common Mistakes

### WRONG: Writing bespoke code when a skill already exists
```yaml
tasks:
  - id: "1"
    title: "Implement PDF extraction"
    runner: "code-runner"
    # A /extractor skill already does this!
```

### RIGHT: Check skill manifest first, call existing skills
```bash
cat ~/.pi/skills-manifest.json | python3 -c "..."  # search for existing skills
# Then in YAML: runner: local, command: ".pi/skills/extractor/run.sh ..."
```

### WRONG: Skipping /review-plan and going straight to /orchestrate
```bash
/orchestrate run 01_TASKS.yaml  # untested plan, may have skill overlap or wrong routing
```

### RIGHT: Always validate plan before execution
```bash
plan.py --validate 01_TASKS.yaml
/review-plan 01_TASKS.yaml  # must PASS before /orchestrate
```

### WRONG: Design tasks without specifying --device for Stitch
```yaml
tasks:
  - title: "Generate mockup"
    command: "mockup-lab generate"  # defaults to mobile!
```

### RIGHT: Always specify device type for design tasks
```yaml
tasks:
  - title: "Generate mockup"
    command: "mockup-lab generate --device desktop"
```

### WRONG: Inline Python that reads .env without load_dotenv
```yaml
tasks:
  - id: "1"
    title: "Query ArangoDB"
    runner: "local"
    command: |
      python3 -c "
      from arango import ArangoClient
      # Fails: ARANGO_PASS not loaded from .env
      client = ArangoClient().db('memory', password=os.environ['ARANGO_PASS'])
      "
```

### RIGHT: Load .env before accessing environment variables
```yaml
tasks:
  - id: "1"
    title: "Query ArangoDB"
    runner: "local"
    command: |
      python3 -c "
      from dotenv import load_dotenv, find_dotenv
      load_dotenv(find_dotenv())  # Load .env FIRST
      import os
      from arango import ArangoClient
      client = ArangoClient().db('memory', password=os.environ['ARANGO_PASS'])
      "
```
