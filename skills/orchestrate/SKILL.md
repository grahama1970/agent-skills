---
name: orchestrate
description: >
  Stabilized async task executor. Dispatches plan YAML tasks to local shell commands
  or code-runner patch runs by default, with broader runners and brittle gates behind
  explicit opt-in flags. Use when user says "run these tasks", "execute the plan",
  "orchestrate this".
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Task, AskUserQuestion
triggers:
  - orchestrate this
  - run these tasks
  - execute the plan
  - run the task file
  - execute tasks
  - start orchestration
  - run 0N_TASKS
  - resume tasks
  - schedule tasks
  - with codex
  - with gemini
  - with deepseek
metadata:
  short-description: Execute task files with quality gates and multi-backend support
provides:
  - task-execution
  - orchestration
composes:
  - code-runner
  - scillm
  - memory
  - plan
  - review-plan
  - task-monitor
  - test-lab
  - agentic-evals
read_before_use:
  - structured_execute.py
  - run.sh
  - docs/README.md
taxonomy:
  - orchestration
  - execution
disciplines:
  - agentic-orchestration
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Orchestrate

Task execution engine with preflight checks and explicit runner dispatch. The default
mode is conservative but usable: foreground execution, serial tasks, YAML plans,
`local` and `code-runner` runners only, and optional advisory services. For
source-mutating code-runner tasks, a valid complete-task contract lands a source
commit after isolated worktree DoD and source DoD pass.

## Usage

```bash
# Execute tasks from a file
orchestrate run <task-file>

# Execute with a specific model backend
orchestrate run <task-file> with codex

# Preview routing plan without executing
orchestrate run <task-file> with codex --dry-run

# Check session status
orchestrate status

# Resume a paused session
orchestrate resume [session-id]

# Schedule recurring runs
orchestrate schedule <task-file> --cron "0 2 * * *"

# Remove scheduled run
orchestrate unschedule <task-file>
```

## Model Routing (`with <model>`)

Choose which LLM backend powers each orchestration run or individual step.

### Command-level routing

```bash
orchestrate run tasks.md with codex      # All LLM steps use codex
orchestrate run tasks.md with gemini     # All LLM steps use Gemini
orchestrate run tasks.md with deepseek   # All LLM steps use DeepSeek
```

For structured YAML plans, command-level `with <model>` fills missing backends on
non-local tasks. Explicit task-level `backend:` values still win.

### Per-step routing (in task files)

```markdown
## Step 1: Assess the problem
- skill: /assess with codex

## Step 2: Scan skills
- skill: /skills-ci scan

## Step 3: Research gaps
- skill: /dogpile with claude
```

### Precedence (CSS-like)

1. **Step-level `with <model>`** — highest priority
2. **Command-level `with <model>`** — default for steps that don't specify
3. **Auto-detect** — fallback (current behavior)

### Model Registry

| Model | Backend | Command |
|-------|---------|---------|
| `pi` | Pi CLI | `pi --tool orchestrate` (full features) |
| `claude` | Claude via scillm | `scillm --model text-claude` |
| `codex` | Codex via scillm | `scillm --model gpt-5.5` with high reasoning |
| `gemini` | Google Gemini via scillm | `scillm --model text-gemini-oauth` |
| `deepseek` | DeepSeek via scillm | `scillm --model deepseek-ai/DeepSeek-V3` |
| `ptc` | Parallel Task Compiler | Enables parallel execution + auto-detected backend |

Override with `ORCHESTRATE_BACKEND=pi|claude|codex` or use `with <model>` syntax.

## Stabilization Mode Defaults

Until `/orchestrate` and `/code-runner` are reliable, V1 defaults remove brittle
surface area:

| Feature | Default | Opt-in |
|---------|---------|--------|
| Runners | `local`, `code-runner` only | `ORCHESTRATE_ALLOW_NON_CORE_RUNNERS=1` |
| Deprecated `subagent-service` | blocked | `ORCHESTRATE_ALLOW_LEGACY_RUNNERS=1` |
| Source apply / commits | allowed only by explicit task contract | `ORCHESTRATE_FORCE_PATCH_ONLY=1` |
| `/test-lab` blind eval | advisory optional | `ORCHESTRATE_REQUIRE_TEST_LAB=1` |
| T2 review | skipped with warning event | `ORCHESTRATE_ENABLE_T2_REVIEW=1` |
| Patch chaining | disabled | `ORCHESTRATE_ENABLE_PATCH_CHAINING=1` |
| Skill context injection | disabled | `ORCHESTRATE_ENABLE_SKILL_CONTEXT=1` |
| Parallel tasks | forced `max_concurrency=1` | `ORCHESTRATE_ALLOW_PARALLEL=1` |
| Background mode | blocked | `ORCHESTRATE_ALLOW_BACKGROUND=1` |
| Human `/interview` escalation | artifact-only, non-blocking | `ORCHESTRATE_ENABLE_INTERVIEW_ESCALATION=1` |

Stabilized plans should use structured YAML, foreground execution, and one
`code-runner` task at a time. Treat skipped optional services as visible warnings,
not proof that the run is fully validated.

## Parallel Execution (Opt-in)

Independent tasks can be grouped into execution levels, but this is disabled by
default during stabilization. Set `ORCHESTRATE_ALLOW_PARALLEL=1` before using
`execution.max_concurrency > 1`.

```bash
ORCHESTRATE_ALLOW_PARALLEL=1 orchestrate run tasks.yaml
```

The DAG executor uses task dependencies to determine readiness, but the stable
default still runs one task at a time.

## Task File Format

> **Prefer YAML** (`0N_TASKS.yaml`). `/plan` outputs YAML natively.
> Legacy markdown (`0N_TASKS.md`) is auto-converted via `structured_plan.py`.

### YAML (preferred — no parsing ambiguity)

```yaml
version: 1
kind: orchestrate-plan
metadata:
  title: "Feature Name"
  goal: "one-line summary"
execution:
  max_concurrency: 1
lanes:
  - id: "0"
    label: "Setup"
tasks:
  - id: "1"
    title: "Task description"
    lane: "0"
    runner: "code-runner"  # stable default also allows "local"
    backend: "codex"
    mode: "iterative"
    depends_on: []
    implementation:
      - "What to do"
    definition_of_done:
      command: "uv run pytest tests/ -q"
      assertion: "All tests pass"
```

### Legacy Markdown (auto-converted)

```markdown
### Task 1: Title
  - Agent: general-purpose
  - Model: sonnet
  - Parallel: 0
  - Dependencies: none
  - **Definition of Done**:
    - Command: uv run pytest tests/ -q
    - Assertion: All tests pass
```

## Quality Gates

- **Preflight**: `preflight.sh` validates task file structure before execution
- **Review-plan**: Auto-runs `/review-plan check` on structured YAML plans (advisory)
- **Per-task**: `quality-gate.sh` runs after each task (tests, lint, etc.)

## Live Monitor

Every structured run writes a browser monitor into the session directory:

- `monitor.html` — live HTML view of the pipeline
- `monitor.css` — readable styling for task state, lanes, gates, and payloads
- `monitor.js` — polls `status.json` and `plan.json` every two seconds
- `monitor-server.json` — owned localhost URL and PID for the session monitor

The monitor must make the pipeline transparent: show the full plan, DAG/lane
grouping, dependencies, current status, gate text, definition of done, errors,
and raw plan/status payloads. It is not a static report. Structured execution
starts an owned localhost HTTP server for the session and prints `monitor_url`
in the `session_started` event.

## Architecture Note: Task Runners

| Runner | Backend | Use Case |
|--------|---------|----------|
| `code-runner` | /scillm | Iterative, context-protected code tasks with allowlist + DoD verification; returns a patch artifact by default |
| `scillm` | /scillm | One-shot LLM inference; disabled by default during stabilization |
| `local` | shell | Deterministic commands (setup, tests, scripts) |

## Path Resolution

All sibling skill references use `SKILLS_DIR` env var with fallback to `$SCRIPT_DIR/..`:
- `SKILLS_DIR` — override for non-standard skill locations
- `_shared/structured_plan.py` — YAML loader/validator
- `review-plan/review_plan.py` — domain validation
- `code-runner/run.sh` — self-improvement loop executor; runs in `isolated_worktree`; review-only mode leaves source unchanged, complete-task mode requires `apply_to_source: true`, `commit_on_success: true`, and `rollback_on_failure: true`

## Code-Runner Source Apply

By default, `/orchestrate` forwards a valid complete-task code-runner contract so
successful DoD runs produce a real source commit. Patch-only remains available by
omitting source-apply fields or by setting `ORCHESTRATE_FORCE_PATCH_ONLY=1`.

To opt into source mutation for a task, set all three fields:

```yaml
apply_to_source: true
commit_on_success: true
rollback_on_failure: true
```

`/orchestrate` passes these fields to `/code-runner`, records `source_commit`,
and can run blind tests against the source repo after the commit. If blind/review
fails and rollback is enabled, `/orchestrate` reverts `source_commit`. `/test-lab`
remains advisory unless `ORCHESTRATE_REQUIRE_TEST_LAB=1`.

Reliability acceptance for this usable path requires real
`/review-plan -> /orchestrate -> /code-runner -> /scillm` runs that prove:

- source DoD rollback on failed source verification,
- source commit revert on failed blind tests,
- multi-round code-runner recovery,
- source-apply serialization for shared `cwd`,
- clean source status after successful and failed tasks.

## Human Escalation

Human notification belongs in `/orchestrate`, not `/code-runner`. When a
`code-runner` task exhausts its automated retry budget, `/orchestrate` fails
closed by default:

- writes `{task_id}.failure-bundle.json`
- writes `{task_id}.interview-request.json`
- marks downstream dependents blocked
- exits nonzero

The failure bundle records task identity, failure code, attempt count, visible
DoD, stdout/stderr tails, patch/result artifact paths, source commit and rollback
status, blocked downstream task IDs, and a recommended human question.

Blocking `/interview` invocation is opt-in for local/operator workflows:

```bash
ORCHESTRATE_ENABLE_INTERVIEW_ESCALATION=1 orchestrate run tasks.yaml
```

CI always remains artifact-only even if the env flag is set.
