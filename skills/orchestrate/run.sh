#!/bin/bash
#
# Orchestrate Skill - Task execution with quality gates
#
# Usage:
#   orchestrate run <task-file>    Execute tasks from file
#   orchestrate status             Show current session status
#   orchestrate resume [id]        Resume paused session
#   orchestrate schedule <task-file> --cron "0 2 * * *"  Schedule recurring runs
#
# Follows HAPPYPATH principles: one command, minimal knobs, defaults work.
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect which agent CLI is available
detect_backend() {
    if command -v pi &>/dev/null; then
        echo "pi"
    elif command -v claude &>/dev/null; then
        echo "claude"
    elif command -v codex &>/dev/null; then
        echo "codex"
    else
        echo "none"
    fi
}

# State directory for session persistence
STATE_DIR="${ORCHESTRATE_STATE_DIR:-.orchestrate}"
ORCHESTRATE_DIR="${ORCHESTRATE_HOME:-$HOME/.pi/skills/orchestrate}"
SCHEDULER_HOME="${SCHEDULER_HOME:-$HOME/.pi/scheduler}"
SCHEDULER_JOBS_FILE="$SCHEDULER_HOME/jobs.json"

# Check for required dependencies
check_dependencies() {
    local missing=()

    if ! command -v jq &>/dev/null; then
        missing+=("jq")
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "Error: Missing required dependencies: ${missing[*]}" >&2
        echo "" >&2
        echo "Install with:" >&2
        echo "  Ubuntu/Debian: sudo apt install ${missing[*]}" >&2
        echo "  macOS: brew install ${missing[*]}" >&2
        echo "  Arch: sudo pacman -S ${missing[*]}" >&2
        return 1
    fi
    return 0
}

show_help() {
    cat <<'EOF'
Orchestrate - Task execution with quality gates

Usage:
  orchestrate run <task-file>         Execute tasks from markdown file
  orchestrate status                  Show current/paused session status
  orchestrate resume [id]             Resume a paused session (or latest)
  orchestrate schedule <file> --cron  Schedule recurring task file runs
  orchestrate unschedule <file>       Remove scheduled run

Examples:
  orchestrate run tasks.md                         Run all tasks now
  orchestrate status                               Check sessions
  orchestrate resume                               Resume most recent
  orchestrate schedule tasks.md --cron "0 2 * * *" Run nightly at 2am
  orchestrate unschedule tasks.md                  Remove from scheduler

Task file format:
  ## Task 1: Title
  - Agent: claude-sonnet-4-20250514
  - Parallel: 1          # Group 0 runs first, then all 1s in parallel, etc.
  - Dependencies: none

  Task description here.

For full documentation see SKILL.md in this directory.
EOF
}

cmd_run() {
    local task_file="$1"

    if [[ -z "$task_file" ]]; then
        echo "Error: task file required" >&2
        echo "Usage: orchestrate run <task-file>" >&2
        exit 1
    fi

    if [[ ! -f "$task_file" ]]; then
        echo "Error: file not found: $task_file" >&2
        exit 1
    fi

    # Run preflight check for all backends
    if [[ -x "$SCRIPT_DIR/preflight.sh" ]]; then
        echo "Running preflight check..."
        if ! "$SCRIPT_DIR/preflight.sh" "$task_file"; then
            echo "Error: Preflight check failed. Resolve issues before running." >&2
            exit 1
        fi
        echo ""
    fi

    local backend
    backend=$(detect_backend)

    case "$backend" in
        pi)
            # Use pi's orchestrate tool directly (full features)
            pi --tool orchestrate --task-file "$task_file"
            ;;
        claude)
            # Claude Code: Limited functionality warning
            echo "========================================"
            echo "WARNING: Running with Claude Code"
            echo "Limited features available:"
            echo "  - No parallel execution"
            echo "  - No pause/resume"
            echo "  - No task-monitor integration"
            echo "  - No memory recall"
            echo "For full features, use: pi --tool orchestrate"
            echo "========================================"
            echo ""

            # Read task file content to include in prompt
            local task_content
            task_content=$(cat "$task_file")

            local prompt="You are executing tasks from a task file. Follow these rules strictly:

## Task File Content
\`\`\`markdown
$task_content
\`\`\`

## Execution Rules
1. Execute tasks in order, respecting Dependencies
2. For each task:
   a. Read and understand the task description
   b. Implement it fully
   c. Run quality gate: $SCRIPT_DIR/quality-gate.sh
   d. If tests fail, FIX the code and retry until they pass
   e. Update the task file: change [ ] to [x] when done
3. Skip tasks already marked [x]
4. Stop if you encounter unresolved Questions/Blockers

Start with the first incomplete task (marked [ ])."

            claude -p "$prompt"
            ;;
        codex)
            # Codex: Limited functionality warning
            echo "========================================"
            echo "WARNING: Running with Codex"
            echo "Limited features available:"
            echo "  - No parallel execution"
            echo "  - No pause/resume"
            echo "  - No task-monitor integration"
            echo "  - No memory recall"
            echo "For full features, use: pi --tool orchestrate"
            echo "========================================"
            echo ""

            # Read task file content
            local task_content
            task_content=$(cat "$task_file")

            local prompt="You are executing tasks from a task file. Follow these rules strictly:

## Task File Content
\`\`\`markdown
$task_content
\`\`\`

## Execution Rules
1. Execute tasks in order, respecting Dependencies
2. For each task:
   a. Read and understand the task description
   b. Implement it fully
   c. Run quality gate: $SCRIPT_DIR/quality-gate.sh
   d. If tests fail, FIX the code and retry until they pass
   e. Update the task file: change [ ] to [x] when done
3. Skip tasks already marked [x]
4. Stop if you encounter unresolved Questions/Blockers

Start with the first incomplete task (marked [ ])."

            codex exec --full-auto -p "$prompt"
            ;;
        *)
            echo "Error: No supported agent CLI found (pi, claude, or codex)" >&2
            exit 1
            ;;
    esac
}

cmd_status() {
    check_dependencies || exit 1

    if [[ ! -d "$STATE_DIR" ]]; then
        echo "No orchestration sessions found."
        echo "Run 'orchestrate run <task-file>' to start."
        return 0
    fi

    local count
    count=$(find "$STATE_DIR" -name "*.state.json" 2>/dev/null | wc -l)

    if [[ "$count" -eq 0 ]]; then
        echo "No paused sessions."
        return 0
    fi

    echo "Paused sessions:"
    echo ""

    for state_file in "$STATE_DIR"/*.state.json; do
        [[ -f "$state_file" ]] || continue

        local session_id task_file status completed total
        session_id=$(basename "$state_file" .state.json)
        task_file=$(jq -r '.taskFile // "unknown"' "$state_file" 2>/dev/null)
        status=$(jq -r '.status // "unknown"' "$state_file" 2>/dev/null)
        completed=$(jq -r '.completedTaskIds | length' "$state_file" 2>/dev/null)

        echo "  $session_id"
        echo "    File: $task_file"
        echo "    Status: $status"
        echo "    Progress: $completed tasks completed"
        echo ""
    done

    echo "Resume with: orchestrate resume [session-id]"
}

cmd_resume() {
    local session_id="$1"

    if [[ ! -d "$STATE_DIR" ]]; then
        echo "No paused sessions to resume." >&2
        exit 1
    fi

    # If no session ID provided, find the most recent
    if [[ -z "$session_id" ]]; then
        local latest
        latest=$(ls -t "$STATE_DIR"/*.state.json 2>/dev/null | head -1)
        if [[ -z "$latest" ]]; then
            echo "No paused sessions found." >&2
            exit 1
        fi
        session_id=$(basename "$latest" .state.json)
        echo "Resuming most recent session: $session_id"
    fi

    local state_file="$STATE_DIR/$session_id.state.json"
    if [[ ! -f "$state_file" ]]; then
        echo "Session not found: $session_id" >&2
        exit 1
    fi

    local backend
    backend=$(detect_backend)

    case "$backend" in
        pi)
            pi --tool orchestrate --resume "$session_id"
            ;;
        *)
            echo "Resume only supported with pi backend currently." >&2
            echo "State file: $state_file" >&2
            exit 1
            ;;
    esac
}

cmd_schedule() {
    check_dependencies || exit 1

    local task_file="$1"
    shift
    local cron=""

    # Parse --cron argument
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --cron)
                cron="$2"
                shift 2
                ;;
            *)
                echo "Unknown option: $1" >&2
                exit 1
                ;;
        esac
    done

    if [[ -z "$task_file" ]]; then
        echo "Error: task file required" >&2
        echo "Usage: orchestrate schedule <task-file> --cron \"0 2 * * *\"" >&2
        exit 1
    fi

    if [[ ! -f "$task_file" ]]; then
        echo "Error: file not found: $task_file" >&2
        exit 1
    fi

    if [[ -z "$cron" ]]; then
        echo "Error: --cron required" >&2
        echo "Usage: orchestrate schedule <task-file> --cron \"0 2 * * *\"" >&2
        exit 1
    fi

    # Resolve to absolute path
    local abs_task_file
    abs_task_file=$(realpath "$task_file")

    # Generate job name from filename
    local job_name
    job_name="orchestrate:$(basename "$task_file" .md)"

    # Ensure scheduler directory exists
    mkdir -p "$SCHEDULER_HOME"

    # Load existing jobs or create empty
    local jobs="{}"
    if [[ -f "$SCHEDULER_JOBS_FILE" ]]; then
        jobs=$(cat "$SCHEDULER_JOBS_FILE")
    fi

    # Add/update job using jq
    local new_job
    new_job=$(jq -n \
        --arg name "$job_name" \
        --arg cron "$cron" \
        --arg command "$SCRIPT_DIR/run.sh run \"$abs_task_file\"" \
        --arg workdir "$(pwd)" \
        --arg desc "Orchestrate $task_file" \
        --argjson created "$(date +%s)" \
        '{
            name: $name,
            cron: $cron,
            command: $command,
            workdir: $workdir,
            enabled: true,
            description: $desc,
            created_at: $created
        }')

    # Merge into jobs
    jobs=$(echo "$jobs" | jq --arg name "$job_name" --argjson job "$new_job" '.[$name] = $job')

    # Save
    echo "$jobs" > "$SCHEDULER_JOBS_FILE"

    echo "Scheduled: $job_name"
    echo "  File: $abs_task_file"
    echo "  Cron: $cron"
    echo "  Next run: Use 'scheduler status' to see schedule"
}

cmd_unschedule() {
    check_dependencies || exit 1

    local task_file="$1"

    if [[ -z "$task_file" ]]; then
        echo "Error: task file required" >&2
        echo "Usage: orchestrate unschedule <task-file>" >&2
        exit 1
    fi

    local job_name
    job_name="orchestrate:$(basename "$task_file" .md)"

    if [[ ! -f "$SCHEDULER_JOBS_FILE" ]]; then
        echo "No scheduled jobs found." >&2
        exit 1
    fi

    # Remove job using jq
    local jobs
    jobs=$(cat "$SCHEDULER_JOBS_FILE")

    if echo "$jobs" | jq -e --arg name "$job_name" '.[$name]' > /dev/null 2>&1; then
        jobs=$(echo "$jobs" | jq --arg name "$job_name" 'del(.[$name])')
        echo "$jobs" > "$SCHEDULER_JOBS_FILE"
        echo "Unscheduled: $job_name"
    else
        echo "Job not found: $job_name" >&2
        exit 1
    fi
}

# Main dispatch
case "${1:-}" in
    run)
        shift
        cmd_run "$@"
        ;;
    status)
        cmd_status
        ;;
    resume)
        shift
        cmd_resume "$@"
        ;;
    schedule)
        shift
        cmd_schedule "$@"
        ;;
    unschedule)
        shift
        cmd_unschedule "$@"
        ;;
    -h|--help|help|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1" >&2
        echo "Run 'orchestrate --help' for usage." >&2
        exit 1
        ;;
esac
