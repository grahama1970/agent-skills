# Orchestrate Skill

Cross-agent task orchestration with scheduling, monitoring, and quality gates. Works with Pi, Claude Code, Antigravity, and Codex.

## Quick Start

```bash
# Run a task file
orchestrate run 01_TASKS.md

# Watch progress in real-time TUI
.pi/skills/task-monitor/run.sh tui

# Schedule nightly runs
orchestrate schedule 01_TASKS.md --cron "0 2 * * *"
```

## Use Cases

### 1. Multi-Step Feature Implementation
```bash
# Create task file with dependent tasks
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
```bash
# Schedule a large refactoring task to run overnight
orchestrate schedule refactor_tasks.md --cron "0 1 * * *"

# Check what's scheduled
cat ~/.pi/scheduler/jobs.json | jq
```

### 3. Continuous Quality Improvement
```bash
# Run tasks with quality gates - retries until tests pass
# Task file with retry-until-pass mode:
- [ ] **Task 1**: Fix flaky test
  - Mode: retry-until-pass
  - Gate: ./run_tests.sh
  - MaxRetries: 5
```

### 4. Research + Implementation Flow
```bash
# First task explores, later tasks implement
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

The task-monitor provides a real-time Rich TUI showing orchestration progress:

```bash
# Start the TUI
.pi/skills/task-monitor/run.sh tui

# Filter to specific tasks
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

## Pause, Resume, and Kill Tasks

### Pause a Running Orchestration
```bash
# Send SIGINT (Ctrl+C) to gracefully pause
# State is saved to .orchestrate/<session-id>.state.json

# Or from another terminal:
pkill -INT -f "orchestrate run"
```

### Resume a Paused Session
```bash
# List paused sessions
orchestrate status

# Output:
# Paused sessions:
#   abc12345
#     File: /path/to/01_TASKS.md
#     Status: paused
#     Progress: 3 tasks completed

# Resume specific session
orchestrate resume abc12345

# Resume most recent
orchestrate resume
```

### Kill a Running Task
```bash
# Hard kill (loses progress since last checkpoint)
pkill -9 -f "orchestrate run"

# Check for orphaned state
orchestrate status
```

### State Persistence
- Progress saved after each task completes
- State files in `.orchestrate/` directory
- Safe to kill between tasks (will resume from checkpoint)

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
```bash
# Schedule nightly at 2am
orchestrate schedule tasks.md --cron "0 2 * * *"

# Schedule every 15 minutes
orchestrate schedule quick_check.md --cron "*/15 * * * *"

# Schedule weekdays at 9am
orchestrate schedule daily_tasks.md --cron "0 9 * * 1-5"

# Remove from schedule
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
```bash
# Via scheduler skill
.pi/skills/scheduler/run.sh list

# Or directly
cat ~/.pi/scheduler/jobs.json | jq

# Via task-monitor TUI (shows "Upcoming Schedule" panel)
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
```bash
# Check status
orchestrate status

# Check task-monitor
.pi/skills/task-monitor/run.sh tui

# Check logs in output directory (shown at end of run)
ls -la /tmp/pi-orchestrate-*/
```

### Scheduled job not running
```bash
# Check scheduler is running
.pi/skills/scheduler/run.sh status

# Check job is enabled
cat ~/.pi/scheduler/jobs.json | jq '.["orchestrate:tasks"].enabled'

# Manually trigger
.pi/skills/scheduler/run.sh run orchestrate:tasks
```

### Resume fails
```bash
# List all state files
ls -la .orchestrate/

# Check state file contents
cat .orchestrate/<session-id>.state.json | jq

# Delete corrupted state to start fresh
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
