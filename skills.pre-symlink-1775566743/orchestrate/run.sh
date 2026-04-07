#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
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
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'


PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
# SKILLS_DIR can be overridden for non-standard skill locations
SKILLS_DIR="${SKILLS_DIR:-$SCRIPT_DIR/..}"
SHARED_PLAN_PY="$SKILLS_DIR/_shared/structured_plan.py"
STRUCTURED_EXECUTE_PY="$SCRIPT_DIR/structured_execute.py"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Detect which agent CLI is available
detect_backend() {
    if [[ -n "$ORCHESTRATE_BACKEND" ]]; then
        echo "$ORCHESTRATE_BACKEND"
        return
    fi
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

run_in_twin() {
    local task_file="$1"
    local backend="$2"
    
    # Copy task file into container
    docker cp "$task_file" "$TWIN_ID:/workspace/tasks.md"
    
    # Copy orchestrate scripts into container
    docker cp "$SCRIPT_DIR/quality-gate.sh" "$TWIN_ID:/workspace/"
    docker cp "$SCRIPT_DIR/preflight.sh" "$TWIN_ID:/workspace/"
    
    case "$backend" in
        pi)
            docker exec -it "$TWIN_ID" bash -c "cd /workspace && pi -p 'Execute the tasks in tasks.md sequentially, marking each [x] when done.'"
            ;;
        claude)
            echo "Warning: Claude execution in Digital Twin is experimental"
            docker exec -it "$TWIN_ID" bash -c "cd /workspace && claude --task-file tasks.md"
            ;;
        *)
            echo "Error: No agent backend available in container" >&2
            exit 1
            ;;
    esac
    
    # Copy results back
    docker cp "$TWIN_ID:/workspace/tasks.md" "$task_file"
    
    echo ""
    echo "Task execution complete in Digital Twin: $TWIN_ID"
}

# State directory for session persistence
STATE_DIR="${ORCHESTRATE_STATE_DIR:-.orchestrate}"
ORCHESTRATE_DIR="${ORCHESTRATE_HOME:-$SCRIPT_DIR}"
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

# ---------------------------------------------------------------------------
# Model routing: `with <model>` support
# ---------------------------------------------------------------------------

# Valid model names for `with <model>` syntax
VALID_MODELS="pi claude codex gemini deepseek ptc"

route_to_model() {
    local prompt="$1"
    local model="$2"
    local task_file="${3:-}"
    local quality_gate="$SCRIPT_DIR/quality-gate.sh"

    case "$model" in
        pi)
            pi -p "$prompt"
            ;;
        claude|codex|gemini)
            echo "Warning: subagent-service is deprecated. Falling back to scillm for model '$model'." >&2
            "$SCRIPT_DIR/../scillm/run.sh" complete --model "$model" "$prompt"
            ;;
        deepseek)
            "$SCRIPT_DIR/../scillm/run.sh" complete --model "deepseek-ai/DeepSeek-V3" "$prompt"
            ;;
        ptc)
            # ptc is not a model backend — it enables parallel execution
            # The actual model comes from detect_backend() or step-level with <model>
            export ORCHESTRATE_PARALLEL=true
            local actual_backend
            actual_backend=$(detect_backend)
            route_to_model "$prompt" "$actual_backend" "$task_file"
            ;;
        *)
            echo "Error: Unknown model '$model'. Valid: $VALID_MODELS" >&2
            return 1
            ;;
    esac
}

resolve_model() {
    # Precedence: step model > command model > detect_backend()
    local step_model="${1:-}"
    local cmd_model="${2:-}"

    if [[ -n "$step_model" ]]; then
        echo "$step_model"
    elif [[ -n "$cmd_model" ]]; then
        echo "$cmd_model"
    else
        detect_backend
    fi
}

show_help() {
    cat <<'EOF'
Orchestrate - Task execution with quality gates

Usage:
  orchestrate run <task-file>                Execute tasks from markdown file
  orchestrate run <task-file> with <model>   Execute with specific model backend
  orchestrate run <task-file> --dry-run      Show routing plan without executing
  orchestrate run <task-file> --resume       Resume from last completed task
  orchestrate status                         Show current/paused session status
  orchestrate resume [id]                    Resume a paused session (or latest)
  orchestrate schedule <file> --cron         Schedule recurring task file runs
  orchestrate unschedule <file>              Remove scheduled run

Model routing:
  orchestrate run tasks.md with codex        Use codex for all LLM steps
  orchestrate run tasks.md with gemini       Use Gemini via scillm
  orchestrate run tasks.md with deepseek     Use DeepSeek via scillm

  Per-step override in task files:
    - skill: /assess with codex
    - skill: /dogpile with claude

  Precedence: step-level > command-level > auto-detect

  Valid models: pi, claude, codex, gemini, deepseek, ptc

Examples:
  orchestrate run tasks.md                         Run all tasks now
  orchestrate run tasks.md with codex              Run with codex backend
  orchestrate run tasks.md with codex --dry-run    Preview routing plan
  orchestrate status                               Check sessions
  orchestrate resume                               Resume most recent
  orchestrate schedule tasks.md --cron "0 2 * * *" Run nightly at 2am
  orchestrate unschedule tasks.md                  Remove from scheduler

Task file format:
  ## Task 1: Title
  - Agent: claude-sonnet-4-20250514
  - skill: /assess with codex
  - Parallel: 1
  - Dependencies: none

  Task description here.

For full documentation see SKILL.md in this directory.
EOF
}

cmd_run() {
    local task_file=""
    local cmd_model=""
    local dry_run=false
    local resume=false
    local background=false

    # Parse args: <task-file> [with <model>] [--dry-run] [--resume] [--background]
    while [[ $# -gt 0 ]]; do
        case "$1" in
            with)
                cmd_model="$2"
                shift 2
                ;;
            --dry-run)
                dry_run=true
                shift
                ;;
            --resume)
                resume=true
                shift
                ;;
            --background|--bg)
                background=true
                shift
                ;;
            --twin-id)
                TWIN_ID="$2"
                shift 2
                ;;
            *)
                if [[ -z "$task_file" ]]; then
                    task_file="$1"
                fi
                shift
                ;;
        esac
    done

    task_file="${task_file:-$TASK_FILE}"

    if [[ -z "$task_file" ]]; then
        echo "Error: task file required" >&2
        echo "Usage: orchestrate run <task-file> [with <model>] [--dry-run]" >&2
        exit 1
    fi

    if [[ ! -f "$task_file" ]]; then
        echo "Error: file not found: $task_file" >&2
        exit 1
    fi

    local is_structured=false
    case "$task_file" in
        *.json|*.yaml|*.yml) is_structured=true ;;
    esac

    # Validate model name if specified
    if [[ -n "$cmd_model" ]]; then
        local valid=false
        for m in $VALID_MODELS; do
            if [[ "$m" == "$cmd_model" ]]; then
                valid=true
                break
            fi
        done
        if [[ "$valid" == "false" ]]; then
            echo "Error: Unknown model '$cmd_model'. Valid: $VALID_MODELS" >&2
            exit 1
        fi
        echo "Model override: $cmd_model"
    fi

    # Dry-run: show routing plan and exit
    if [[ "$dry_run" == "true" ]]; then
        echo "=== Routing Plan (dry-run) ==="
        echo "Task file: $task_file"
        echo "Command-level model: ${cmd_model:-<auto-detect>}"
        echo "Auto-detected backend: $(detect_backend)"
        echo ""

        if [[ "$is_structured" == "true" ]]; then
            local summary_json
            summary_json=$(mktemp)
            python3 "$SHARED_PLAN_PY" summary "$task_file" > "$summary_json" 2>/dev/null
            python3 - "$summary_json" <<'PY'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
for task in data.get("tasks", []):
    runner = task.get("runner") or "<unset>"
    backend = task.get("backend") or "<unset>"
    lane = task.get("lane") or "<unset>"
    print(f"  Task {task.get('id')}: {task.get('title')} → runner={runner}, backend={backend}, lane={lane}")
print("")
print("=== Done (no execution) ===")
PY
            rm -f "$summary_json"
            return 0
        fi

        # Parse per-step routing from task file
        local step_num=0
        local in_step=false
        local step_title=""
        local step_model=""
        while IFS= read -r line; do
            # Match step headers: ## Task N: Title or ## Step N: Title
            if [[ "$line" =~ ^##[[:space:]]+(Task|Step)[[:space:]]+([0-9]+) ]]; then
                # Print previous step if any
                if [[ "$in_step" == "true" ]]; then
                    local resolved
                    resolved=$(resolve_model "$step_model" "$cmd_model")
                    printf "  Step %d: %-40s → %s\n" "$step_num" "$step_title" "$resolved"
                fi
                step_num="${BASH_REMATCH[2]}"
                step_title="${line#*: }"
                step_title="${step_title%% \[*}"  # strip [DONE] etc
                step_model=""
                in_step=true
            fi
            # Match skill lines with model: - skill: /foo with bar
            if [[ "$in_step" == "true" && "$line" =~ -[[:space:]]*skill:[[:space:]]*/[a-z-]+[[:space:]]+with[[:space:]]+([a-z]+) ]]; then
                step_model="${BASH_REMATCH[1]}"
            fi
            # Match Model: metadata
            if [[ "$in_step" == "true" && "$line" =~ -[[:space:]]*Model:[[:space:]]*(.+) ]]; then
                step_model="${BASH_REMATCH[1]}"
                step_model="${step_model%% *}"  # trim
            fi
        done < "$task_file"
        # Print last step
        if [[ "$in_step" == "true" ]]; then
            local resolved
            resolved=$(resolve_model "$step_model" "$cmd_model")
            printf "  Step %d: %-40s → %s\n" "$step_num" "$step_title" "$resolved"
        fi

        echo ""
        echo "=== Done (no execution) ==="
        return 0
    fi

    # If running in Digital Twin, verify container exists
    if [[ -n "$TWIN_ID" ]]; then
        if ! docker inspect "$TWIN_ID" &>/dev/null; then
            echo "Error: Digital Twin container not found: $TWIN_ID" >&2
            echo "Hint: Start a twin with: .pi/skills/battle/run.sh battle --mode docker" >&2
            exit 1
        fi
        echo "Running in Digital Twin: $TWIN_ID"
    fi

    # Run preflight check for all backends
    if [[ -x "$SCRIPT_DIR/preflight.sh" ]]; then
        echo "Running preflight check..."
        if [[ -n "$TWIN_ID" ]]; then
            docker exec "$TWIN_ID" bash -c "cd /workspace && $(cat "$SCRIPT_DIR/preflight.sh")" "$task_file" || {
                echo "Error: Preflight check failed inside Digital Twin." >&2
                exit 1
            }
        else
            if [[ "$is_structured" == "true" ]]; then
                if ! python3 "$SHARED_PLAN_PY" validate "$task_file" >/dev/null; then
                    echo "Error: Structured plan validation failed. Resolve issues before running." >&2
                    exit 1
                fi
                # Run /review-plan if available (full validation: claims, routing, blind tests)
                # Resolve skill sibling path: prefer SKILLS_DIR env, fall back to relative
                local skills_dir="${SKILLS_DIR:-$SCRIPT_DIR/..}"
                local review_plan_py="$skills_dir/review-plan/review_plan.py"
                if [[ -f "$review_plan_py" ]]; then
                    echo "Running /review-plan..."
                    local review_output review_exit=0
                    review_output=$(python3 "$review_plan_py" check "$task_file" 2>&1) || review_exit=$?
                    # If review-plan itself crashed, block — a broken validator is not a pass
                    if [[ $review_exit -ne 0 ]] && ! echo "$review_output" | grep -qE "(PASS|WARN|FAIL)"; then
                        echo "Error: /review-plan crashed (exit $review_exit):" >&2
                        echo "$review_output" | tail -10 >&2
                        if [[ "${ORCHESTRATE_SKIP_REVIEW:-0}" != "1" ]]; then
                            exit 1
                        fi
                        echo "Warning: ORCHESTRATE_SKIP_REVIEW=1 — proceeding despite crash." >&2
                    fi
                    # Count FAIL-grade findings — these are non-negotiable blockers
                    # Match actual findings ([FAIL] or **adversarial-test**:), not summary lines like "0 FAIL"
                    local fail_count
                    fail_count=$(echo "$review_output" | grep -cE '^\s*-?\s*\*?\*?(FAIL|adversarial-test)\*?\*?:|\[FAIL\]' || true)
                    if [[ "$fail_count" -gt 0 ]]; then
                        echo "BLOCKED: /review-plan found $fail_count FAIL-grade issues:" >&2
                        echo "$review_output" | grep -E '^\s*-?\s*\*?\*?(FAIL|adversarial-test)\*?\*?:|\[FAIL\]' >&2
                        echo "" >&2
                        echo "Fix the plan, then re-run. Use: review-plan review $task_file --suggest-fixes" >&2
                        if [[ "${ORCHESTRATE_SKIP_REVIEW:-0}" != "1" ]]; then
                            exit 1
                        fi
                        echo "Warning: ORCHESTRATE_SKIP_REVIEW=1 — proceeding despite FAIL findings." >&2
                    elif echo "$review_output" | grep -q "WARN"; then
                        echo "Warning: /review-plan found issues. Run 'review-plan review $task_file --suggest-fixes' for details." >&2
                    fi
                fi
            else
                if ! "$SCRIPT_DIR/preflight.sh" "$task_file"; then
                    echo "Error: Preflight check failed. Resolve issues before running." >&2
                    exit 1
                fi
            fi
        fi
        echo ""
    fi

    # Compute resume flag once for both structured and converted-markdown paths
    local resume_flag=""
    if [[ "$resume" == "true" ]]; then
        resume_flag="--resume"
    fi

    if [[ "$is_structured" == "true" ]]; then
        if [[ -n "$cmd_model" ]]; then
            echo "Error: command-level 'with <model>' does not override structured task backends." >&2
            echo "Set runner/backend per task in the structured plan instead." >&2
            exit 1
        fi
        if [[ "$background" == "true" ]]; then
            # Background mode: launch executor as detached process, print session info.
            # The project agent reads the first JSON line to get session_dir for intervention.
            echo "Launching orchestration in background..."
            local log_file="${ORCHESTRATE_DIR}/structured/bg-$(date +%s).log"
            mkdir -p "$(dirname "$log_file")"
            nohup uv run --project "$SCRIPT_DIR" python "$STRUCTURED_EXECUTE_PY" run "$task_file" $resume_flag \
                > "$log_file" 2>&1 &
            local bg_pid=$!
            echo "PID: ${bg_pid}"
            echo "Log: ${log_file}"
            # Wait briefly for session_started JSON to appear
            sleep 2
            head -1 "$log_file" 2>/dev/null || true
            echo ""
            echo "Monitor: tail -f ${log_file}"
            echo "Status:  python3 ${STRUCTURED_EXECUTE_PY} status"
            echo "Kill:    touch <session_dir>/ABORT"
            return 0
        fi
        echo "Executing structured plan with explicit runner dispatch..."
        uv run --project "$SCRIPT_DIR" python "$STRUCTURED_EXECUTE_PY" run "$task_file" $resume_flag
        return $?
    fi

    # Convert markdown → structured YAML, then dispatch per-task via structured executor.
    # This ensures each task gets its own subagent call with the correct backend
    # (claude for code, gemini for design reviews, codex for code reviews).
    echo "Converting markdown plan to structured format for per-task dispatch..."

    local converted_yaml
    converted_yaml="${task_file%.md}.auto.yaml"

    # set +e: allow python failure so fallback can execute (set -e would abort)
    set +e
    python3 -c "
import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.dirname('$SHARED_PLAN_PY'))
from structured_plan import markdown_to_structured

plan = markdown_to_structured(Path('$task_file'))
# Default all tasks without a runner to code-runner
for task in plan.get('tasks', []):
    if not task.get('runner'):
        task['runner'] = 'code-runner'
    # If no backend specified, use command-level model or claude
    if not task.get('backend'):
        task['backend'] = '${cmd_model:-claude}'

import yaml
with open('$converted_yaml', 'w') as f:
    yaml.dump(plan, f, default_flow_style=False, sort_keys=False)

print(f'Converted {len(plan.get(\"tasks\", []))} tasks to {\"$converted_yaml\"}')" 2>&1
    local convert_exit=$?
    set -e

    if [[ $convert_exit -ne 0 ]]; then
        echo "Error: Failed to convert markdown to structured format." >&2
        echo "Falling back to legacy single-prompt dispatch..." >&2
        # Legacy fallback: send entire file as one prompt
        local backend
        backend=$(resolve_model "" "$cmd_model")
        local task_content
        task_content=$(cat "$task_file")
        local prompt="Execute all incomplete tasks (marked [ ]) in this task file sequentially. For each task, implement it fully, then mark [x] when done. Skip tasks already marked [x].\n\n$task_content"
        route_to_model "$prompt" "$backend"
        return $?
    fi

    echo "Executing structured plan with per-task dispatch..."
    uv run --project "$SCRIPT_DIR" python "$STRUCTURED_EXECUTE_PY" run "$converted_yaml" $resume_flag
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
            pi -p "Resume orchestration session $session_id. Read the task file and continue from the first incomplete task (marked [ ])."
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
