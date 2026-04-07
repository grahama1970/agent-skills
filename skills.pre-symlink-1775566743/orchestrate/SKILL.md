---
name: orchestrate
description: >
  Async DAG task executor with quality gates. Dispatches plan YAML tasks to code-runner
  (iterative code), scillm (one-shot LLM), or local (shell commands). Features: blind eval
  with information barrier, per-task timeout, T2 code review gate, pause/resume/cancel
  via file-based intervention. Use when user says "run these tasks", "execute the plan",
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
read_before_use:
  - structured_execute.py
  - run.sh
  - docs/README.md
taxonomy:
  - orchestration
  - execution
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Orchestrate

Task execution engine with quality gates, preflight checks, and multi-backend support.

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
| `claude` | Claude Code CLI | `claude -p` |
| `codex` | OpenAI Codex CLI | `codex exec --full-auto` |
| `gemini` | Google Gemini via scillm | `scillm --model gemini-2.5-pro` |
| `deepseek` | DeepSeek via scillm | `scillm --model deepseek-v3` |
| `ptc` | Parallel Task Compiler | Enables parallel execution + auto-detected backend |

Override with `ORCHESTRATE_BACKEND=pi|claude|codex` or use `with <model>` syntax.

## Parallel Execution (PTC)

Independent tasks (no dependency edges) are automatically grouped into execution levels
and run in parallel via `Promise.allSettled()`. Enabled by default.

```bash
# Explicitly enable parallel execution
orchestrate run tasks.md with ptc

# Disable parallel execution
orchestrate({ taskFile: "tasks.md", parallel: false })
```

The PTC compiler uses Kahn's algorithm to build a DAG from task dependencies,
groups tasks with zero in-degree into levels, and executes each level in parallel.
Tasks with `Parallel: N` metadata are grouped by their parallel number.

State is saved at level boundaries (not per-task) during parallel execution.
`continueOnError` works with `Promise.allSettled` — all parallel tasks finish
even if one fails.

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
  max_concurrency: 3
lanes:
  - id: "0"
    label: "Setup"
tasks:
  - id: "1"
    title: "Task description"
    lane: "0"
    runner: "code-runner"  # or "local" or "scillm"
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

## Architecture Note: Task Runners

| Runner | Backend | Use Case |
|--------|---------|----------|
| `code-runner` | /scillm | Iterative code tasks with DoD verification (default) |
| `scillm` | /scillm | One-shot LLM inference (classification, extraction) |
| `local` | shell | Deterministic commands (setup, tests, scripts) |

## Path Resolution

All sibling skill references use `SKILLS_DIR` env var with fallback to `$SCRIPT_DIR/..`:
- `SKILLS_DIR` — override for non-standard skill locations
- `_shared/structured_plan.py` — YAML loader/validator
- `review-plan/review_plan.py` — domain validation
- `code-runner/run.sh` — self-improvement loop executor
