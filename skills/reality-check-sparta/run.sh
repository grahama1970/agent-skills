#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
SPARTA_DIR="/home/graham/workspace/experiments/sparta"

usage() {
    cat << EOF
SPARTA QRA ADVERSARIAL Reality Check

Usage: ./run.sh <command> [options]

Commands:
  check         Run adversarial reality check with fresh verification
  watch         Monitor batch and trigger checks at QRA checkpoints (e.g., every 10K)
  status        Show current pipeline status
  history       Show past reality check findings from memory
  convergence   Show convergence analysis (issue trend over time)
  iterate       Run check, suggest fixes, and track convergence (self-correction loop)
  loop          Run iteration loop until all checks pass (auto-iterate)
  report        Generate client-facing assessment report
  auto-fix      Self-improvement loop: identify bad QRAs, delete, and recheck

Options:
  --run-id ID       Pipeline run ID (default: latest)
  --samples N       Number of QRAs to sample per check (default: 20)
  --checkpoint N    QRA interval for watch checkpoints (default: 10000)
  --interval N      Check interval in seconds for watch (default: 60)
  --full            Run full check (all URL alignments)
  --store           Store findings in /memory
  --json            Output as JSON
  --no-suggestions  Don't show fix suggestions

Self-Correction Workflow:
  1. ./run.sh check --run-id <id> --store     # Run check, see issues and suggestions
  2. [Apply suggested fixes to pipeline]
  3. ./run.sh check --run-id <id> --store     # Re-run to verify fixes
  4. ./run.sh convergence                     # Check if issues are decreasing

Examples:
  ./run.sh check --run-id run-recovery-verify --samples 20
  ./run.sh check --run-id run-recovery-verify --full --store
  ./run.sh watch --run-id run-recovery-verify --checkpoint 10000
  ./run.sh convergence
  ./run.sh history
EOF
}

# Default values
RUN_ID=""
SAMPLES=20
CHECKPOINT=10000
INTERVAL=60
FULL_CHECK=false
STORE_MEMORY=false
JSON_OUTPUT=false

# Parse arguments
COMMAND="${1:-}"
shift || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --run-id)
            RUN_ID="$2"
            shift 2
            ;;
        --samples)
            SAMPLES="$2"
            shift 2
            ;;
        --checkpoint)
            CHECKPOINT="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --full)
            FULL_CHECK=true
            shift
            ;;
        --store)
            STORE_MEMORY=true
            shift
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 1
            ;;
    esac
done

# Find latest run if not specified
if [[ -z "$RUN_ID" ]]; then
    RUN_ID=$(ls -t "$SPARTA_DIR/data/runs/" 2>/dev/null | head -1 || echo "")
    if [[ -z "$RUN_ID" ]]; then
        echo "ERROR: No runs found in $SPARTA_DIR/data/runs/" >&2
        exit 1
    fi
fi

DB_PATH="$SPARTA_DIR/data/runs/$RUN_ID/sparta.duckdb"

case "$COMMAND" in
    check)
        # Run from SPARTA dir to get duckdb dependency
        cd "$SPARTA_DIR"
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/check.py" \
            --db "$DB_PATH" \
            --run-id "$RUN_ID" \
            --samples "$SAMPLES" \
            ${FULL_CHECK:+--full} \
            ${STORE_MEMORY:+--store} \
            ${JSON_OUTPUT:+--json} \
            --suggest-fixes
        ;;
    watch)
        # Checkpoint monitor - watches batch and triggers checks at intervals
        cd "$SPARTA_DIR"
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/watch.py" \
            --run-id "$RUN_ID" \
            --checkpoint "$CHECKPOINT" \
            --samples "$SAMPLES" \
            --interval "$INTERVAL"
        ;;
    status)
        cd "$SPARTA_DIR"
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/check.py" --db "$DB_PATH" --status-only
        ;;
    convergence)
        cd "$SPARTA_DIR"
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/check.py" --convergence
        ;;
    iterate)
        # Self-correction loop: check, show fixes, repeat
        echo "=== SPARTA Self-Correction Loop ==="
        echo "Running adversarial check..."
        cd "$SPARTA_DIR"
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/check.py" \
            --db "$DB_PATH" \
            --run-id "$RUN_ID" \
            --samples "$SAMPLES" \
            ${FULL_CHECK:+--full} \
            --store \
            --suggest-fixes
        echo ""
        echo "=== Convergence Analysis ==="
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/check.py" --convergence
        echo ""
        echo "Next steps:"
        echo "  1. Apply suggested fixes to the pipeline"
        echo "  2. Re-run: ./run.sh iterate --run-id $RUN_ID"
        echo "  3. Track progress: ./run.sh convergence"
        ;;
    loop)
        # Automated iteration loop until clean
        echo "=== SPARTA Automated Iteration Loop ==="
        cd "$SPARTA_DIR"
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/check.py" \
            --db "$DB_PATH" \
            --run-id "$RUN_ID" \
            --iterate \
            --max-iterations 10 \
            ${STORE_MEMORY:+--store}
        ;;
    report)
        # Generate client-facing report
        cd "$SPARTA_DIR"
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/check.py" \
            --db "$DB_PATH" \
            --run-id "$RUN_ID" \
            --samples "$SAMPLES" \
            ${FULL_CHECK:+--full} \
            --client-report
        ;;
    history)
        # Query memory for past findings
        cd /home/graham/workspace/experiments/memory
        exec uv run --project "$SCRIPT_DIR" python -m graph_memory.agent_cli recall \
            --query "SPARTA reality check findings" \
            --scope sparta-qra \
            --k 10
        ;;
    auto-fix)
        # Self-improvement loop: identify bad QRAs, delete, and recheck
        echo "=== SPARTA Auto-Fix Self-Improvement Loop ==="
        cd "$SPARTA_DIR"
        exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/auto_fix.py" \
            --db "$DB_PATH" \
            --run-id "$RUN_ID" \
            --samples "$SAMPLES" \
            --max-iterations 10
        ;;
    "")
        usage
        exit 1
        ;;
    *)
        echo "Unknown command: $COMMAND" >&2
        usage
        exit 1
        ;;
esac
