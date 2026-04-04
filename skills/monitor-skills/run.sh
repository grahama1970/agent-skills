#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# monitor-skills - Continuous skill monitoring with auto-drift correction
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SKILLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Configuration
STATE_DIR="${HOME}/.pi/monitor-skills"
CANONICAL_REPO="${HOME}/workspace/experiments/agent-skills/skills"
REGISTRY_FILE="${HOME}/.agent_skills_targets"
HISTORY_FILE="${STATE_DIR}/sync_history.jsonl"
STATE_FILE="${STATE_DIR}/task_state.json"

mkdir -p "$STATE_DIR"

# Skill patterns to check in each project
SKILL_PATTERNS=(
    ".pi/skills"
    ".agent/skills"
    ".agents/skills"
    ".codex/skills"
    ".claude/skills"
    ".github/skills"
)

# Files to ignore when comparing
EXCLUDE_PATTERNS=(
    ".venv"
    "__pycache__"
    ".git"
    ".DS_Store"
    "node_modules"
    ".pytest_cache"
    "*.pyc"
)

usage() {
    cat <<EOF
monitor-skills - Auto-correct skill drift across all projects

Usage: ./run.sh <command> [options]

Commands:
  sync              Auto-correct drift now
  check             Check drift without correcting
  status            Show health dashboard
  model-health      Model lifecycle health (shadow agreement, stale models)
  auto-trigger      Auto-trigger retraining when conditions met
  register          Register for continuous monitoring
  history           View sync log
  gap-scan          Detect missing skills via Shadow-LEGO cascade
  gap-status        Show gap scan history and proposal counts
  register-nightly  Register gap-scan at 4:00 AM + existing sync

Options:
  --dry-run         Preview without syncing
  --quiet           Suppress output
  --json            Output as JSON
  --skill NAME      Target specific skill
  --interval TIME   Sync frequency (for register)

Examples:
  ./run.sh sync                    # Auto-correct all drift
  ./run.sh check --json            # JSON drift report
  ./run.sh auto-trigger --dry-run  # Preview auto-trigger actions
  ./run.sh auto-trigger --execute  # Actually trigger retraining
  ./run.sh register --interval 15m # Enable 15-min auto-sync
  ./run.sh gap-scan --dry-run --json  # Preview gap detection
  ./run.sh gap-status              # Show gap scan state
  ./run.sh register-nightly        # Register 4:00 AM gap scan
EOF
}

# Get all registered project paths
get_projects() {
    local projects=("$HOME")  # Always include home

    if [[ -f "$REGISTRY_FILE" ]]; then
        while IFS= read -r line; do
            [[ "$line" =~ ^#.*$ ]] && continue
            [[ -z "$line" ]] && continue
            local path="${line/#\~/$HOME}"
            [[ -d "$path" ]] && projects+=("$path")
        done < "$REGISTRY_FILE"
    fi

    printf '%s\n' "${projects[@]}"
}

# Build find exclude args from EXCLUDE_PATTERNS
build_find_excludes() {
    local excludes=""
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        excludes="$excludes -not -path '*/$pattern/*'"
    done
    echo "$excludes"
}

# Find newest version of a skill across all locations
find_newest_skill() {
    local skill_name="$1"
    local newest_path=""
    local newest_time=0

    # Check canonical
    if [[ -d "$CANONICAL_REPO/$skill_name" ]]; then
        local t
        t=$(find "$CANONICAL_REPO/$skill_name" -maxdepth 2 -type f \
            \( -name "*.py" -o -name "*.md" -o -name "*.sh" \) \
            -not -path '*/.venv/*' -not -path '*/__pycache__/*' \
            -not -path '*/.pytest_cache/*' -not -path '*/node_modules/*' \
            -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
        t=${t%.*}
        if [[ -n "$t" && "$t" -gt "$newest_time" ]]; then
            newest_time=$t
            newest_path="$CANONICAL_REPO/$skill_name"
        fi
    fi

    # Check all projects
    while IFS= read -r project; do
        for pattern in "${SKILL_PATTERNS[@]}"; do
            local skill_path="$project/$pattern/$skill_name"
            if [[ -d "$skill_path" ]]; then
                local t
                t=$(find "$skill_path" -maxdepth 2 -type f \
                    \( -name "*.py" -o -name "*.md" -o -name "*.sh" \) \
                    -not -path '*/.venv/*' -not -path '*/__pycache__/*' \
                    -not -path '*/.pytest_cache/*' -not -path '*/node_modules/*' \
                    -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
                t=${t%.*}
                if [[ -n "$t" && "$t" -gt "$newest_time" ]]; then
                    newest_time=$t
                    newest_path="$skill_path"
                fi
            fi
        done
    done < <(get_projects)

    echo "$newest_path"
}

# Get all unique skill names across all locations
get_all_skills() {
    local skills=()

    # From canonical
    if [[ -d "$CANONICAL_REPO" ]]; then
        for dir in "$CANONICAL_REPO"/*/; do
            [[ -d "$dir" ]] || continue
            local name=$(basename "$dir")
            [[ "$name" == ".*" ]] && continue
            [[ "$name" =~ ^[0-9] ]] && continue  # Skip task files
            skills+=("$name")
        done
    fi

    # From all projects
    while IFS= read -r project; do
        for pattern in "${SKILL_PATTERNS[@]}"; do
            local skills_dir="$project/$pattern"
            [[ -d "$skills_dir" ]] || continue
            for dir in "$skills_dir"/*/; do
                [[ -d "$dir" ]] || continue
                local name=$(basename "$dir")
                [[ "$name" == ".*" ]] && continue
                [[ "$name" =~ ^[0-9] ]] && continue
                skills+=("$name")
            done
        done
    done < <(get_projects)

    # Unique and sorted
    printf '%s\n' "${skills[@]}" | sort -u
}

# Sync a skill from source to all destinations
sync_skill() {
    local skill_name="$1"
    local source_path="$2"
    local dry_run="${3:-0}"
    local synced_count=0

    # Build rsync exclude args
    local exclude_args=()
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        exclude_args+=("--exclude" "$pattern")
    done

    # Sync to canonical first
    if [[ "$source_path" != "$CANONICAL_REPO/$skill_name" ]]; then
        mkdir -p "$CANONICAL_REPO/$skill_name"
        if [[ "$dry_run" -eq 1 ]]; then
            echo "  [DRY-RUN] $source_path -> $CANONICAL_REPO/$skill_name"
        else
            rsync -av --update "${exclude_args[@]}" "$source_path/" "$CANONICAL_REPO/$skill_name/" >/dev/null 2>&1
            synced_count=$((synced_count + 1))
        fi
    fi

    # Sync from canonical to all projects
    while IFS= read -r project; do
        for pattern in "${SKILL_PATTERNS[@]}"; do
            local target="$project/$pattern/$skill_name"
            local parent="$project/$pattern"

            # Only sync to existing skill directories (don't create new ones everywhere)
            if [[ -d "$parent" ]]; then
                if [[ "$target" != "$source_path" ]]; then
                    mkdir -p "$target"
                    if [[ "$dry_run" -eq 1 ]]; then
                        echo "  [DRY-RUN] $CANONICAL_REPO/$skill_name -> $target"
                    else
                        rsync -av --update "${exclude_args[@]}" "$CANONICAL_REPO/$skill_name/" "$target/" >/dev/null 2>&1
                        synced_count=$((synced_count + 1))
                    fi
                fi
            fi
        done
    done < <(get_projects)

    echo "$synced_count"
}

# Log sync action to history
log_sync() {
    local skill="$1"
    local source="$2"
    local count="$3"

    local entry=$(cat <<EOF
{"timestamp":"$(date -Iseconds)","skill":"$skill","source":"$source","synced_to":$count}
EOF
)
    echo "$entry" >> "$HISTORY_FILE"
}

# Update task-monitor state
update_state() {
    local status="$1"
    local skills_synced="$2"
    local conflicts="$3"

    cat > "$STATE_FILE" <<EOF
{
  "last_run": "$(date -Iseconds)",
  "status": "$status",
  "skills_synced": $skills_synced,
  "conflicts": $conflicts,
  "next_run": "$(date -d '+15 minutes' -Iseconds 2>/dev/null || echo 'unknown')"
}
EOF
}

# Command: sync
cmd_sync() {
    local dry_run=0
    local quiet=0
    local target_skill=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry_run=1 ;;
            --quiet) quiet=1 ;;
            --skill) shift; target_skill="$1" ;;
            *) ;;
        esac
        shift
    done

    [[ "$quiet" -eq 0 ]] && echo "=== Skill Auto-Sync ==="

    local total_synced=0
    local skills_processed=0
    local drift_found=0

    while IFS= read -r skill; do
        [[ -n "$target_skill" && "$skill" != "$target_skill" ]] && continue

        local newest=$(find_newest_skill "$skill")
        [[ -z "$newest" ]] && continue

        # Check if canonical is already newest
        local canonical_path="$CANONICAL_REPO/$skill"
        if [[ "$newest" != "$canonical_path" ]]; then
            drift_found=$((drift_found + 1))
            [[ "$quiet" -eq 0 ]] && echo "Drift: $skill (newest at $newest)"

            local count=$(sync_skill "$skill" "$newest" "$dry_run")
            total_synced=$((total_synced + count))

            [[ "$dry_run" -eq 0 ]] && log_sync "$skill" "$newest" "$count"
        fi

        skills_processed=$((skills_processed + 1))
    done < <(get_all_skills)

    [[ "$quiet" -eq 0 ]] && echo ""
    [[ "$quiet" -eq 0 ]] && echo "Processed: $skills_processed skills"
    [[ "$quiet" -eq 0 ]] && echo "Drift found: $drift_found"
    [[ "$quiet" -eq 0 ]] && echo "Synced: $total_synced targets"

    update_state "success" "$drift_found" 0
}

# Command: check
cmd_check() {
    local json_output=0
    local target_skill=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --json) json_output=1 ;;
            --skill) shift; target_skill="$1" ;;
            *) ;;
        esac
        shift
    done

    local results=()

    while IFS= read -r skill; do
        [[ -n "$target_skill" && "$skill" != "$target_skill" ]] && continue

        local newest=$(find_newest_skill "$skill")
        [[ -z "$newest" ]] && continue

        local canonical_path="$CANONICAL_REPO/$skill"
        local has_drift="false"
        [[ "$newest" != "$canonical_path" ]] && has_drift="true"

        local newest_time=$(find "$newest" -maxdepth 2 -type f \
            \( -name "*.py" -o -name "*.md" -o -name "*.sh" \) \
            -not -path '*/.venv/*' -not -path '*/__pycache__/*' \
            -not -path '*/.pytest_cache/*' -not -path '*/node_modules/*' \
            -printf '%T@\n' 2>/dev/null | sort -rn | head -1)
        newest_time=${newest_time%.*}
        local newest_date=$(date -d "@$newest_time" '+%Y-%m-%d %H:%M' 2>/dev/null || echo "unknown")

        if [[ "$json_output" -eq 1 ]]; then
            results+=("{\"skill\":\"$skill\",\"newest\":\"$newest\",\"date\":\"$newest_date\",\"drift\":$has_drift}")
        else
            if [[ "$has_drift" == "true" ]]; then
                echo "⚠️  $skill: drift (newest at $newest)"
            fi
        fi
    done < <(get_all_skills)

    if [[ "$json_output" -eq 1 ]]; then
        echo "[$(IFS=,; echo "${results[*]}")]"
    fi
}

# Command: status
cmd_status() {
    echo "=== Monitor Skills Status ==="
    echo ""

    if [[ -f "$STATE_FILE" ]]; then
        echo "Last run: $(cat "$STATE_FILE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('last_run','unknown'))" 2>/dev/null)"
        echo "Status: $(cat "$STATE_FILE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)"
    else
        echo "No previous runs recorded"
    fi

    echo ""
    echo "Skills with drift:"
    cmd_check 2>/dev/null | head -10 || echo "  (none)"

    echo ""
    echo "Model health:"
    cmd_model_health --summary 2>/dev/null || echo "  (no model health data)"

    echo ""
    echo "Registered projects:"
    get_projects | while read -r p; do echo "  $p"; done
}

# Command: register
cmd_register() {
    local interval="15m"
    local disable=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --interval) shift; interval="$1" ;;
            --disable) disable=1 ;;
            *) ;;
        esac
        shift
    done

    # Convert interval to cron format
    local cron_expr="*/15 * * * *"  # Default 15 min
    case "$interval" in
        5m)  cron_expr="*/5 * * * *" ;;
        10m) cron_expr="*/10 * * * *" ;;
        15m) cron_expr="*/15 * * * *" ;;
        30m) cron_expr="*/30 * * * *" ;;
        1h)  cron_expr="0 * * * *" ;;
    esac

    if [[ "$disable" -eq 1 ]]; then
        echo "Disabling monitor-skills scheduler job..."
        "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" unregister --name "monitor-skills-sync" 2>/dev/null || true
        echo "Disabled"
    else
        echo "Registering monitor-skills for $interval intervals..."
        "$PROJECT_ROOT/.pi/skills/scheduler/run.sh" register \
            --name "monitor-skills-sync" \
            --cron "$cron_expr" \
            --command "$SCRIPT_DIR/run.sh sync --quiet" \
            --workdir "$PROJECT_ROOT" \
            --description "Auto-correct skill drift every $interval" 2>/dev/null || true
        echo "Registered: monitor-skills-sync ($cron_expr)"
    fi
}

# Command: model-health
cmd_model_health() {
    local summary_only=0

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --summary) summary_only=1 ;;
            *) ;;
        esac
        shift
    done

    local registries=()
    local shadows=()

    # Discover registries
    local assistant_reg="${SKILLS_DIR}/assistant/model_registry.json"
    local bond_reg="${SKILLS_DIR}/skill-lab/state/bond_registry.json"
    [[ -f "$assistant_reg" ]] && registries+=("--registry" "$assistant_reg")
    [[ -f "$bond_reg" ]] && registries+=("--registry" "$bond_reg")

    # Discover shadow files
    local assistant_shadow="${HOME}/.pi/assistant/shadow.jsonl"
    local bond_shadow="${SKILLS_DIR}/skill-lab/state/shadow.jsonl"
    [[ -f "$assistant_shadow" ]] && shadows+=("--shadow" "$assistant_shadow")
    [[ -f "$bond_shadow" ]] && shadows+=("--shadow" "$bond_shadow")

    if [[ ${#registries[@]} -eq 0 && ${#shadows[@]} -eq 0 ]]; then
        echo "  No registries or shadow files found"
        return
    fi

    local output
    output=$(command python3 "${SCRIPT_DIR}/probes/model_health.py" "${registries[@]}" "${shadows[@]}" 2>/dev/null) || {
        echo "  Model health probe failed"
        return
    }

    if [[ "$summary_only" -eq 1 ]]; then
        echo "$output" | command python3 -c "
import sys, json
report = json.load(sys.stdin)
for reg in report.get('registry_summary', []):
    name = reg['path'].split('/')[-1]
    if not reg.get('exists'):
        continue
    parts = []
    for s in ('validators', 'classifiers', 'regressors'):
        info = reg.get(s, {})
        total = info.get('total', 0)
        if total:
            shadow = info.get('shadow_mode', 0)
            parts.append(f'{s}: {total} ({shadow} shadow)')
    if parts:
        print(f'  {name}: {\"  \".join(parts)}')
shadow = report.get('shadow_agreement', [])
if shadow:
    with_data = [s for s in shadow if s['sample_count'] > 0]
    print(f'  Shadow tasks with data: {len(with_data)}/{len(shadow)}')
ready = report.get('training_ready', [])
if ready:
    print(f'  Training-ready tasks: {len(ready)}')
stale = report.get('stale_models', [])
if stale:
    print(f'  Stale models (>30d): {len(stale)}')
" 2>/dev/null
    else
        echo "$output"
    fi
}

# Command: history
cmd_history() {
    local limit=20
    local target_skill=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --limit) shift; limit="$1" ;;
            --skill) shift; target_skill="$1" ;;
            *) ;;
        esac
        shift
    done

    if [[ ! -f "$HISTORY_FILE" ]]; then
        echo "No sync history yet"
        return
    fi

    echo "=== Sync History ==="
    if [[ -n "$target_skill" ]]; then
        grep "\"skill\":\"$target_skill\"" "$HISTORY_FILE" | tail -n "$limit"
    else
        tail -n "$limit" "$HISTORY_FILE"
    fi
}

# Command: auto-trigger
cmd_auto_trigger() {
    local dry_run_flag="--dry-run"
    local extra_args=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --execute) dry_run_flag=""; extra_args+=("--execute") ;;
            --dry-run) dry_run_flag="--dry-run" ;;
            *) ;;
        esac
        shift
    done

    local registries=()
    local shadows=()

    # Discover registries
    local assistant_reg="${SKILLS_DIR}/assistant/model_registry.json"
    local bond_reg="${SKILLS_DIR}/skill-lab/state/bond_registry.json"
    [[ -f "$assistant_reg" ]] && registries+=("--registry" "$assistant_reg")
    [[ -f "$bond_reg" ]] && registries+=("--registry" "$bond_reg")

    # Discover shadow files
    local assistant_shadow="${HOME}/.pi/assistant/shadow.jsonl"
    local bond_shadow="${SKILLS_DIR}/skill-lab/state/shadow.jsonl"
    [[ -f "$assistant_shadow" ]] && shadows+=("--shadow" "$assistant_shadow")
    [[ -f "$bond_shadow" ]] && shadows+=("--shadow" "$bond_shadow")

    command python3 "${SCRIPT_DIR}/probes/model_health.py" auto-trigger \
        "${registries[@]}" "${shadows[@]}" "${extra_args[@]}" $dry_run_flag
}

# Command: gap-scan
cmd_gap_scan() {
    local args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) args+=("--dry-run") ;;
            --json) args+=("--json") ;;
            *) ;;
        esac
        shift
    done
    command python3 "${SCRIPT_DIR}/probes/skill_gap.py" gap-scan "${args[@]}"
}

# Command: gap-status
cmd_gap_status() {
    command python3 "${SCRIPT_DIR}/probes/skill_gap.py" gap-status
}

# Command: register-nightly
cmd_register_nightly() {
    local scheduler="$PROJECT_ROOT/.pi/skills/scheduler/run.sh"

    # Register existing sync (unchanged)
    echo "Registering monitor-skills-sync (every 15 min)..."
    "$scheduler" register \
        --name "monitor-skills-sync" \
        --cron "*/15 * * * *" \
        --command "$SCRIPT_DIR/run.sh sync --quiet" \
        --workdir "$PROJECT_ROOT" \
        --description "Auto-correct skill drift every 15m" 2>/dev/null || true

    # Register gap-scan at 4:00 AM
    echo "Registering monitor-skills-gap-scan (4:00 AM)..."
    "$scheduler" register \
        --name "monitor-skills-gap-scan" \
        --cron "0 4 * * *" \
        --command "$SCRIPT_DIR/run.sh gap-scan" \
        --workdir "$PROJECT_ROOT" \
        --description "Nightly skill gap detection via Shadow-LEGO cascade" 2>/dev/null || true

    echo "Registered:"
    echo "  monitor-skills-sync:     */15 * * * *"
    echo "  monitor-skills-gap-scan: 0 4 * * *"
}

# Main
case "${1:-help}" in
    sync)    shift; cmd_sync "$@" ;;
    check)   shift; cmd_check "$@" ;;
    status)  shift; cmd_status "$@" ;;
    model-health) shift; cmd_model_health "$@" ;;
    auto-trigger) shift; cmd_auto_trigger "$@" ;;
    register) shift; cmd_register "$@" ;;
    history) shift; cmd_history "$@" ;;
    gap-scan) shift; cmd_gap_scan "$@" ;;
    gap-status) shift; cmd_gap_status "$@" ;;
    register-nightly) shift; cmd_register_nightly "$@" ;;
    help|--help|-h) usage ;;
    *) echo "Unknown command: $1"; usage; exit 1 ;;
esac
