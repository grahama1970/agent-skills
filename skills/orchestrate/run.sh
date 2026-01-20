#!/bin/bash
#
# Orchestrate Skill - Task execution with quality gates
#
# Usage:
#   orchestrate run <task-file>    Execute tasks from file
#   orchestrate status             Show current session status
#   orchestrate resume [id]        Resume paused session
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

show_help() {
    cat <<'EOF'
Orchestrate - Task execution with quality gates

Usage:
  orchestrate run <task-file>    Execute tasks from markdown file
  orchestrate status             Show current/paused session status
  orchestrate resume [id]        Resume a paused session (or latest)

Examples:
  orchestrate run tasks.md       Run all tasks in tasks.md
  orchestrate status             Check what's running or paused
  orchestrate resume             Resume the most recent paused session

Task file format:
  ## Task 1: Title
  - Agent: claude-sonnet-4-20250514
  - Parallel: 1

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

    local backend
    backend=$(detect_backend)

    case "$backend" in
        pi)
            # Use pi's orchestrate tool directly
            pi --tool orchestrate --task-file "$task_file"
            ;;
        claude)
            # Claude Code: use print mode with the task file
            echo "Running with Claude Code..."
            local prompt="Execute the tasks in $task_file sequentially. For each task:
1. Read the task description
2. Implement it fully
3. Self-verify by running: $ORCHESTRATE_DIR/quality-gate.sh
4. If tests fail, FIX the code and retry until they pass
5. Mark the task complete with [x] when done

Start with the first incomplete task."
            claude --print -p "$prompt"
            ;;
        codex)
            # Codex: similar approach
            echo "Running with Codex..."
            local prompt="Execute the tasks in $task_file sequentially. For each task:
1. Read the task description
2. Implement it fully
3. Self-verify by running: $ORCHESTRATE_DIR/quality-gate.sh
4. If tests fail, FIX the code and retry until they pass
5. Mark the task complete with [x] when done

Start with the first incomplete task."
            codex exec --full-auto -p "$prompt"
            ;;
        *)
            echo "Error: No supported agent CLI found (pi, claude, or codex)" >&2
            exit 1
            ;;
    esac
}

cmd_status() {
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
    -h|--help|help|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1" >&2
        echo "Run 'orchestrate --help' for usage." >&2
        exit 1
        ;;
esac
