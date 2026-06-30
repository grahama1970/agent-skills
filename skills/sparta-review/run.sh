#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# sparta-review: Unified Brandon Bailey SPARTA assessment
# Merges review-sparta (assess) + reality-check-sparta (iterate/auto-fix)
# Adds /dogpile research and /ask cross-persona consultation
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPARTA_DIR="${HOME}/workspace/experiments/sparta"
PI_SKILLS="${HOME}/workspace/experiments/pi-mono/.pi/skills"

cd "$SKILL_DIR"

# Delegate to review-sparta for assessment commands
run_review() {
    local cmd="$1"; shift
    cd "$PI_SKILLS/review-sparta"
    if [[ ! -d ".venv" ]]; then
        uv venv .venv
        uv pip install --python .venv/bin/python typer rich duckdb httpx openpyxl
    fi
    source .venv/bin/activate
    python review_sparta.py "$cmd" "$@"
}

# Delegate to reality-check-sparta for iteration commands
# NOTE: Uses cli.py directly (not check.py) because check.py has a broken
# entry point that bypasses typer arg parsing.
run_reality_check() {
    local cmd="$1"; shift
    cd "$PI_SKILLS/reality-check-sparta"

    # For commands that the run.sh handles (iterate, loop, etc.), use run.sh
    # For the core 'check' command, route through cli.py directly for proper arg parsing
    case "$cmd" in
        check-direct)
            # Direct invocation via cli.py — proper typer arg parsing
            cd ${HOME}/workspace/experiments/sparta
            exec uv run python "$PI_SKILLS/reality-check-sparta/cli.py" "$@"
            ;;
        *)
            # Delegate to run.sh for compound commands (iterate, loop, watch, etc.)
            ./run.sh "$cmd" "$@"
            ;;
    esac
}

# /dogpile research integration
run_research() {
    local query="$1"; shift
    echo "=== Brandon Bailey Research (via /dogpile) ==="
    echo "Query: $query"
    echo ""
    cd "$PI_SKILLS/dogpile"
    ./run.sh search "$query" --preset vulnerability_research "$@"
}

# /ask consult integration
run_consult() {
    local persona="$1"; shift
    local question="$1"; shift
    echo "=== Brandon Consulting: $persona ==="
    echo "Question: $question"
    echo ""
    cd "$PI_SKILLS/ask"
    ./run.sh consult "$persona" "$question" "$@"
}

usage() {
    cat << 'EOF'
sparta-review: Unified Brandon Bailey SPARTA Assessment (v3.0)

┌─────────────────────────────────────────────────────────────────┐
│  QRA CONVERGENCE — Like model training, quality converges      │
│                                                                 │
│  generate → assess → fix prompts → verify → regenerate → ...   │
│       ↑                                           |             │
│       └──────── converging quality ───────────────┘             │
│                                                                 │
│  Each cycle reduces issues (like loss decreasing).              │
│  Stops when quality plateaus or target QRA count reached.       │
└─────────────────────────────────────────────────────────────────┘

Assessment:
  assess        Full Brandon Bailey assessment across all dimensions
  compare       Compare two runs side-by-side
  status        Quick health check

Self-Correction:
  check         Adversarial check with fix suggestions
  auto-fix      Identify and delete bad QRAs, then recheck
  recalibrate   Use /prompt-lab to optimize Stage 12 prompts

Convergence Loop (runs for days):
  converge      Full autonomous loop: generate→assess→fix→restart
  watch         Monitor batch, trigger checks at QRA checkpoints
  convergence   Track improvement trend over time

Research & Consultation:
  research      Brandon researches grey areas via /dogpile
  consult       Brandon asks a colleague via /ask

Reports:
  report        Generate client-facing assessment report
  history       Past findings from /memory

Common Options:
  --run-id ID       Pipeline run ID (default: latest)
  --samples N       Number of QRAs to sample (default: 20)
  --checkpoint N    QRA interval for convergence checks (default: 10000)
  --target N        Target QRA count (default: 90000)
  --full            Run all checks
  --store           Store findings in /memory
  --json            JSON output

Examples:
  # Full convergence loop (runs for days)
  ./run.sh converge --run-id run-recovery-verify --checkpoint 10000 --target 90000

  # Single assessment
  ./run.sh assess --run-id run-recovery-verify --full

  # Recalibrate prompts based on Brandon's findings
  ./run.sh recalibrate --run-id run-recovery-verify

  # Brandon researches a grey area
  ./run.sh research "RF jamming countermeasures for LEO constellations"

  # Consult a colleague
  ./run.sh consult "SOC Analyst" "Is GPS spoofing realistic for commercial sats?"
EOF
}

COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    # --- Assessment (review-sparta) ---
    assess)
        run_review review "$@"
        ;;
    compare)
        run_review compare "$@"
        ;;

    # --- Self-Correction (reality-check-sparta) ---
    check)
        run_reality_check check-direct "$@"
        ;;
    auto-fix)
        run_reality_check auto-fix "$@"
        ;;
    recalibrate)
        # Use /prompt-lab to optimize Stage 12 prompts based on failures
        cd "$SPARTA_DIR"
        exec uv run python "$SKILL_DIR/converge.py" --run-id "${RUN_ID:-run-recovery-verify}" \
            --dry-run --max-cycles 1 "$@"
        ;;

    # --- Convergence Loop (the main autonomous cycle) ---
    converge)
        # Full autonomous convergence: generate→assess→fix→restart
        cd "$SPARTA_DIR"
        exec uv run python "$SKILL_DIR/converge.py" "$@"
        ;;
    watch)
        run_reality_check watch "$@"
        ;;
    convergence)
        run_reality_check convergence "$@"
        ;;
    status)
        run_reality_check status "$@"
        ;;

    # --- Research & Consultation ---
    research)
        if [[ $# -lt 1 ]]; then
            echo "Usage: ./run.sh research \"query\" [--preset NAME]" >&2
            exit 1
        fi
        run_research "$@"
        ;;
    consult)
        if [[ $# -lt 2 ]]; then
            echo "Usage: ./run.sh consult \"Persona Name\" \"question\" [--also-ask \"P1,P2\"]" >&2
            exit 1
        fi
        run_consult "$@"
        ;;

    # --- Reports ---
    report)
        run_reality_check report "$@"
        ;;
    history)
        run_reality_check history "$@"
        ;;

    # --- Meta ---
    sanity)
        bash "$SKILL_DIR/sanity.sh"
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "Unknown command: $COMMAND" >&2
        usage
        exit 1
        ;;
esac
