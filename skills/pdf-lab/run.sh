#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# pdf-lab — Self-improving PDF extraction convergence loop
#
# Usage:
#   ./run.sh tune <pdf> [options]            Diagnose, reproduce, converge, write fix
#   ./run.sh diagnose <pdf> [options]        Quick delta diagnosis (no tuning)
#   ./run.sh compare <pdf> <gt.json>         Compare extraction vs ground truth
#   ./run.sh tune-gt <pdf> [options]         VLM-guided convergence vs ground truth
#   ./run.sh synthetic [options]             Generate synthetic reproduction PDF
#   ./run.sh status                          Show recent tuning results
#   ./run.sh history                         List all pdf-lab code changes
#   ./run.sh rollback --sha <sha>            Rollback a specific fix
#   ./run.sh verify-real <pdf> <fixture_dir>  Verify tuned params on real PDF
#   ./run.sh regression-check --sha <sha>    Re-run regression for a fix
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Data directory for persistent state
DATA_DIR="${PDF_LAB_DATA:-$HOME/.pi/pdf-lab}"
mkdir -p "$DATA_DIR"

# Extractor project root (resolve from skill location)
EXTRACTOR_ROOT="${EXTRACTOR_ROOT:-/home/graham/workspace/experiments/extractor}"
export EXTRACTOR_ROOT

# Detect sibling skill paths
PI_SKILLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MEMORY_SKILLS_DIR="${MEMORY_SKILLS_DIR:-/home/graham/workspace/experiments/memory/.agents/skills}"

show_help() {
    cat <<'EOF'
pdf-lab — Self-Improving PDF Extraction Convergence Loop

Usage:
  pdf-lab tune <pdf> [options]            Diagnose, reproduce, converge, write fix
  pdf-lab diagnose <pdf> [options]        Quick delta diagnosis (no tuning)
  pdf-lab compare <pdf> <gt.json>         Compare extraction vs ground truth
  pdf-lab tune-gt <pdf> [options]         VLM-guided convergence vs ground truth
  pdf-lab synthetic [options]             Generate synthetic reproduction PDF
  pdf-lab status                          Show recent tuning results
  pdf-lab history                         List all pdf-lab code changes
  pdf-lab rollback --sha <sha>            Rollback a specific fix
  pdf-lab verify-real <pdf> <fixture_dir>  Verify tuned params on real PDF
  pdf-lab regression-check --sha <sha>    Re-run regression for a fix

Tune Options:
  --review-json <path>     Review result JSON (S00 estimate + extraction counts)
  --debug-json <path>      Debug-pdf patterns JSON
  --persona <name>         Persona who flagged the issue (default: "Margaret Chen")
  --persona-role <role>    Persona role (default: "extraction quality")
  --max-iterations <n>     Max convergence iterations (default: 5)
  --converge               Enable convergence loop
  --write-back             Write winning fix to pipeline code
  --dry-run                Find fix but don't write it
  --json                   JSON output

Diagnose Options:
  --profile-json <path>    S00 profile JSON
  --structural-json <path> S11 structural JSON

Synthetic Options:
  --patterns <json>        Pattern list as JSON array
  --output <path>          Output PDF path

Examples:
  # Full convergence with write-back
  ./run.sh tune /path/to/doc.pdf \
    --review-json review.json --debug-json debug.json \
    --converge --write-back --json

  # Dry run (preview changes)
  ./run.sh tune /path/to/doc.pdf \
    --review-json review.json --debug-json debug.json \
    --converge --dry-run --json

  # Quick delta diagnosis
  ./run.sh diagnose /path/to/doc.pdf \
    --profile-json profile.json --structural-json structural.json

  # VLM-guided convergence against ground truth
  ./run.sh tune-gt /path/to/fixture.pdf -g /path/to/ground_truth.json --max-rounds 5

  # Generate synthetic from patterns
  ./run.sh synthetic --patterns '["multi_column","split_tables"]' --output /tmp/repro.pdf
EOF
}

cmd_tune() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" tune "$@"
}

cmd_diagnose() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" diagnose "$@"
}

cmd_compare() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" compare "$@"
}

cmd_tune_gt() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" tune-gt "$@"
}

cmd_synthetic() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" synthetic "$@"
}

cmd_status() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" status
}

cmd_history() {
    echo "=== pdf-lab Code Change History ==="
    echo ""
    cd "$EXTRACTOR_ROOT"
    git log --all --oneline --grep="pdf-lab:" 2>/dev/null || echo "No pdf-lab commits found."
    echo ""
    echo "Persona attribution:"
    git log --all --oneline --grep="Reviewed-By:" --format="%h %s | %b" 2>/dev/null | head -20 || true
}

cmd_rollback() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" rollback "$@"
}

cmd_verify_real() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" verify-real "$@"
}

cmd_regression_check() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" regression-check "$@"
}

# Main dispatch
case "${1:-}" in
    tune)
        shift
        cmd_tune "$@"
        ;;
    diagnose)
        shift
        cmd_diagnose "$@"
        ;;
    compare)
        shift
        cmd_compare "$@"
        ;;
    tune-gt)
        shift
        cmd_tune_gt "$@"
        ;;
    synthetic)
        shift
        cmd_synthetic "$@"
        ;;
    status)
        cmd_status
        ;;
    history)
        cmd_history
        ;;
    rollback)
        shift
        cmd_rollback "$@"
        ;;
    verify-real)
        shift
        cmd_verify_real "$@"
        ;;
    regression-check)
        shift
        cmd_regression_check "$@"
        ;;
    gui|app)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/app.py" "$@"
        ;;
    answer)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" answer "$@"
        ;;
    book)
        shift
        uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" book "$@"
        ;;
    -h|--help|help|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1" >&2
        show_help
        exit 1
        ;;
esac
