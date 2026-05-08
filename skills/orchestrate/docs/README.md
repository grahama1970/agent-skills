# Orchestrate Skill

`/orchestrate` exists for work that is too stateful, risky, or multi-step to hand to a single agent prompt. It turns a plan into an inspectable execution session: tasks have dependencies, runners, evidence, artifacts, pause points, and quality gates.

Use it when you need to see why work started, what produced each result, where a failure came from, and what a human operator can safely change before execution continues. It works with Pi, Claude Code, Antigravity, and Codex.

## Quick Start

```bash
# Execute a dependency-aware task file
orchestrate run 01_TASKS.md

# Inspect live progress in the terminal dashboard
.pi/skills/task-monitor/run.sh tui

# Hand recurring work to the scheduler
orchestrate schedule 01_TASKS.md --cron "0 2 * * *"
```

## Use Cases

### 1. Multi-Step Feature Implementation
Use a task file when the order of operations matters and later work depends on earlier evidence.

```bash
cat > 01_TASKS.md << 'EOF'
# Task List: Add User Authentication

## Context
Adding OAuth2 authentication to the API.

## Tasks
- [ ] **Task 1**: Create auth middleware
  - Agent: general-purpose
  - Parallel: 0

- [ ] **Task 2**: Add login endpoint
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1

- [ ] **Task 3**: Add logout endpoint
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1

- [ ] **Task 4**: Integration tests
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 2, Task 3

## Questions/Blockers
None
EOF

orchestrate run 01_TASKS.md
```

### 2. Overnight Batch Processing
For maintenance work that can run unattended, register the plan with the scheduler and inspect the job registry afterward.

```bash
orchestrate schedule refactor_tasks.md --cron "0 1 * * *"

cat ~/.pi/scheduler/jobs.json | jq
```

### 3. Continuous Quality Improvement
```bash
# Quality-gated repair keeps rerunning until the gate passes or MaxRetries is hit.
- [ ] **Task 1**: Fix flaky test
  - Mode: retry-until-pass
  - Gate: ./run_tests.sh
  - MaxRetries: 5
```

### 4. Research + Implementation Flow
Split discovery from editing when the first pass should gather options and the second pass should apply one choice.

```bash
- [ ] **Task 1**: Research authentication patterns
  - Agent: explore
  - Parallel: 0

- [ ] **Task 2**: Implement chosen pattern
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 1
```

## Commands

| Command | Description |
|---------|-------------|
| `orchestrate run <file>` | Execute tasks from markdown file |
| `orchestrate status` | Show running/paused sessions |
| `orchestrate resume [id]` | Resume a paused session |
| `orchestrate schedule <file> --cron "..."` | Schedule recurring runs |
| `orchestrate unschedule <file>` | Remove from schedule |

## Monitoring with Task-Monitor TUI

Task-monitor provides two operator surfaces: a Rich TUI for terminal supervision and an HTTP API for browser dashboards or remote agents.

```bash
.pi/skills/task-monitor/run.sh tui

.pi/skills/task-monitor/run.sh tui --filter orchestrate
```

**TUI Display:**
```
╭─────────────────────────────────────────────────────────────╮
│  Active Tasks                                               │
├─────────────────────────────────────────────────────────────┤
│  orchestrate:01_TASKS:abc123    [=======>    ] 3/5  60%    │
│  Current: Task 4 - Integration tests                        │
│  Success: 3  Failed: 0  Status: running                     │
╰─────────────────────────────────────────────────────────────╯

╭─────────────────────────────────────────────────────────────╮
│  Upcoming Schedule                                          │
├─────────────────────────────────────────────────────────────┤
│  orchestrate:refactor    0 2 * * *    Next: 02:00 tomorrow │
│  orchestrate:cleanup     0 * * * *    Next: in 45 minutes  │
╰─────────────────────────────────────────────────────────────╯
```

**Start API Server (for remote monitoring):**
```bash
.pi/skills/task-monitor/run.sh serve --port 8765
```

The HTTP monitor exposes normalized task-viewer data for live consoles and control surfaces:

- `GET /orchestrate/sessions` lists recent structured execution sessions.
- `GET /orchestrate/sessions/{session_id}` returns `status.json` with normalized states: `queued`, `running`, `passed`, `failed`, `blocked`, `stale`, `paused`, `skipped`, `retrying`.
- `GET /orchestrate/sessions/{session_id}/events/stream` streams append-only JSONL events over SSE.
- `GET /orchestrate/sessions/{session_id}/artifacts/{artifact_path}` serves logs, diffs, review files, and reports without exposing arbitrary local paths.
- `POST /orchestrate/sessions/{session_id}/control` writes guarded intervention files.

## Human Review Roundtable

For design, policy, architecture, or ambiguous tradeoff decisions, an `/orchestrate` plan can include a review step that calls `/argue` or `/roundtable`. Treat this as an optional judgment layer, not as deterministic proof that the implementation is correct.

Complex personas such as Brandon, Margaret, and Jennifer can be loaded to stress-test a plan from security, quality, operational, or stakeholder perspectives before implementation continues. Use this when the next step depends on critique, alignment, or a decision record rather than another `code-runner` round.

Roundtable output should be persisted as an artifact. If the review gates execution, summarize the decision into task status so the monitor can show why the session paused, changed direction, or proceeded.

Keep the distinction clear:

- `/review-plan` validates structure, dependencies, safety, and execution readiness.
- `/argue` tests a decision with bounded for/against positions and a judge rubric.
- `/roundtable` runs a stateful multi-persona review where each participant can react to prior claims before moderator synthesis.

## Mid-Task Intervention (Factory Droid)

A watchdog polls the session directory every 2 seconds for intervention files. These controls work during active runner execution, so an operator can pause, cancel, annotate, or redirect work before the whole plan finishes.

### Intervention Files

Create these files in the session directory (printed at orchestration start):

| File | Effect | Latency |
|------|--------|---------|
| `PAUSE` | Pause after current tasks finish | <2s detection |
| `KILL_<task_id>` | Kill specific subagent mid-stream | <2s |
| `ABORT` | Kill ALL running tasks, stop plan | <2s |
| `SKIP_<task_id>` | Skip a queued task (on next unpause) | Next pause cycle |
| `COURSE_CORRECT_<task_id>.md` | Add operator guidance to task state | <2s |
| `PAUSE_TASK_<task_id>` | Request task pause at next safe point | <2s |
| `RERUN_<task_id>` | Record rerun request while paused | <2s |

The session directory also contains `INTERVENTION.md` with all task IDs for
easy reference.

### Pause a Running Orchestration
Locate the active session, create `PAUSE`, then remove it once the operator notes or skip files are ready.

```bash
ls ~/.pi/skills/orchestrate/structured/

touch ~/.pi/skills/orchestrate/structured/session-1234567890/PAUSE

rm ~/.pi/skills/orchestrate/structured/session-1234567890/PAUSE
```

### Kill a Specific Subagent Mid-Stream
Use a task-specific kill file when one runner is unhealthy but the rest of the session should remain inspectable.

```bash
touch ~/.pi/skills/orchestrate/structured/session-1234567890/KILL_T3

# The watchdog cancels the active process and records a CANCELLED event.
```

### Abort Everything
Abort is the session-level stop. It cancels running work and prevents queued dependents from starting.

```bash
touch ~/.pi/skills/orchestrate/structured/session-1234567890/ABORT
```

### Programmatic Intervention (Project Agent)
Agents can write the same files directly when an outer supervisor needs to intervene.

```python
session_dir = Path("~/.pi/skills/orchestrate/structured/session-1234567890")
(session_dir / "KILL_T3").touch()  # Kill one task
(session_dir / "ABORT").touch()    # Kill everything
```

### Resume a Paused Session
```bash
orchestrate run plan.yaml --resume
```

### State Persistence
- Progress is saved to `status.json` after scheduling, state changes, task completion, and intervention handling.
- `events.jsonl` is append-only session provenance for task lifecycle, control, and failure events.
- Task artifacts (`*.stdout.txt`, `*.stderr.txt`, `*.result.json`, `*.hunk.md`, review outputs) are referenced from `status.json`.
- Safe to kill between tasks (will resume from checkpoint)
- Cancelled tasks render as `failed` with failure code `CANCELLED` for the task-viewer contract.

## Handling Questions/Blockers

Orchestrations **will not run** if the task file has unresolved questions:

```markdown
## Questions/Blockers
- Which database should we use? PostgreSQL or MongoDB?
- Should we support OAuth1 or only OAuth2?
```

### Workflow for Questions

1. **Agent creates task file with questions**
2. **Preflight check blocks execution**
3. **Human answers questions** (edit the file or tell the agent)
4. **Agent updates file** - removes answered questions or marks "None"
5. **Orchestration proceeds**

```bash
# This will fail with questions present:
orchestrate run 01_TASKS.md
# Error: Unresolved questions/blockers found. Please resolve before running.

# After answering questions (change to "None" or remove section):
## Questions/Blockers
None

# Now it runs:
orchestrate run 01_TASKS.md
```

### Answering Questions Mid-Session
If a task discovers it needs clarification:
1. Session pauses automatically
2. Question added to task file
3. Human answers
4. Resume with `orchestrate resume`

## Scheduling Recurring Tasks

### Schedule Commands
Use explicit cron expressions for recurring plans. Keep the schedule small enough that failures remain easy to attribute.

```bash
orchestrate schedule tasks.md --cron "0 2 * * *"

orchestrate schedule quick_check.md --cron "*/15 * * * *"

orchestrate schedule daily_tasks.md --cron "0 9 * * 1-5"

orchestrate unschedule tasks.md
```

### Cron Syntax Reference
```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sun=0)
│ │ │ │ │
* * * * *

Examples:
  0 2 * * *     Daily at 2:00 AM
  */15 * * * *  Every 15 minutes
  0 9-17 * * 1-5  Hourly 9am-5pm, Mon-Fri
  0 0 * * 0     Weekly on Sunday midnight
```

### View Scheduled Jobs
The scheduler, raw job registry, and task-monitor TUI all expose the same recurring-work state from different angles.

```bash
.pi/skills/scheduler/run.sh list

cat ~/.pi/scheduler/jobs.json | jq

.pi/skills/task-monitor/run.sh tui
```

### Run Scheduled Job Immediately
```bash
.pi/skills/scheduler/run.sh run orchestrate:01_TASKS
```

## Parallel Task Execution

Tasks with the same `Parallel` value run concurrently:

```markdown
- [ ] **Task 1**: Setup (must run first)
  - Parallel: 0

- [ ] **Task 2**: Build frontend
  - Parallel: 1
  - Dependencies: Task 1

- [ ] **Task 3**: Build backend (runs WITH Task 2)
  - Parallel: 1
  - Dependencies: Task 1

- [ ] **Task 4**: Deploy (waits for both)
  - Parallel: 2
  - Dependencies: Task 2, Task 3
```

**Execution Flow:**
```
Group 0: Task 1 runs alone
         ↓
Group 1: Task 2 ──┬── runs in parallel
         Task 3 ──┘
         ↓
Group 2: Task 4 runs after both complete
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TASK_MONITOR_API_URL` | `http://localhost:8765` | Task-monitor API endpoint |
| `TASK_MONITOR_ENABLED` | `true` | Set to "false" to disable monitoring |
| `SCHEDULER_HOME` | `~/.pi/scheduler` | Scheduler data directory |
| `ORCHESTRATE_STATE_DIR` | `.orchestrate` | Session state directory |

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User / Agent                            │
│                          │                                  │
│              orchestrate run tasks.md                       │
│                          ▼                                  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  Scheduler  │◄───│ Orchestrate │───►│Task-Monitor │     │
│  │             │    │             │    │             │     │
│  │ Cron jobs   │    │ Executes    │    │ Rich TUI    │     │
│  │ jobs.json   │    │ tasks in    │    │ HTTP API    │     │
│  │             │    │ parallel    │    │             │     │
│  │ Triggers    │    │ groups      │    │ Shows       │     │
│  │ runs on     │    │             │    │ progress    │     │
│  │ schedule    │    │ Pushes      │    │ real-time   │     │
│  │             │    │ progress    │    │             │     │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘     │
│         │                  │                  │             │
│         └──────────────────┼──────────────────┘             │
│                            │                                │
│              ~/.pi/scheduler/jobs.json                      │
│              (shared state for schedule panel)              │
└─────────────────────────────────────────────────────────────┘
```

## Troubleshooting

### "Unresolved questions/blockers found"
Edit task file, change `## Questions/Blockers` section to `None` or remove questions.

### Task stuck / not progressing
Start with the orchestrate session view, then inspect task-monitor and the emitted artifacts.

```bash
orchestrate status

.pi/skills/task-monitor/run.sh tui

ls -la /tmp/pi-orchestrate-*/
```

### Scheduled job not running
Verify the service, confirm the job is enabled, then trigger the same job manually to isolate scheduler versus plan failures.

```bash
.pi/skills/scheduler/run.sh status

cat ~/.pi/scheduler/jobs.json | jq '.["orchestrate:tasks"].enabled'

.pi/skills/scheduler/run.sh run orchestrate:tasks
```

### Resume fails
Inspect the saved state before deleting anything. Remove a state file only when it is clearly corrupted and the run can restart safely.

```bash
ls -la .orchestrate/

cat .orchestrate/<session-id>.state.json | jq

rm .orchestrate/<session-id>.state.json
```

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Agent-facing skill documentation |
| `run.sh` | CLI wrapper (detects pi/claude/codex) |
| `README.md` | This file - user guide |
| `preflight.sh` | Validates task files before execution |
| `quality-gate.sh` | Auto-detects and runs project tests |
| `sanity.sh` | Self-test for the skill |
| `tests/` | Integration tests |

## When to Use Orchestrate vs Ralphy

| Use Orchestrate When | Use Ralphy When |
|---------------------|-----------------|
| Tasks depend on each other | Tasks are independent |
| Quality gates matter (tests must pass) | Speed over quality gates |
| You need memory recall (prior solutions) | You want branch-per-task PRs |
| You need pause/resume | Maximum parallelism |
| Sequential reliability is critical | Auto-merge with conflict resolution |

**Orchestrate**: Careful, sequential/parallel-group execution with memory-first approach and quality verification.

**Ralphy**: Fast parallel execution with git worktrees and automatic PR workflows.
