#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# pdf-lab — Self-improving PDF extraction convergence loop
#
# Usage:
#   ./run.sh tune <pdf> [options]            Diagnose, reproduce, converge, write fix
#   ./run.sh diagnose <pdf> [options]        Quick delta diagnosis (no tuning)
#   ./run.sh forensic <pdf> [options]        Page PNG + beautified JSON/schema report
#   ./run.sh toc-scan <pdf> [options]        Build section map before scans
#   ./run.sh preset-scan <pdf> [options]     Sweep every pdf_oxide preset
#   ./run.sh agent-scan <pdf> [options]      Create agent expected-elements JSON
#   ./run.sh extract-pages <pdf> --pages N   Extract selected pages with pdf_oxide
#   ./run.sh compare-json <expected> <actual> Compare expected vs actual JSON
#   ./run.sh agentic-extract <pdf> [options] Run agentic-first convergence skeleton
#   ./run.sh final-pass <final_extraction.json> Generate human triage queue
#   ./run.sh table-scan <pdf> [options]      Find table pages without pdf_oxide
#   ./run.sh element-scan <pdf> [options]    Inventory pdf_oxide element layers
#   ./run.sh compare <pdf> <gt.json>         Compare extraction vs ground truth
#   ./run.sh tune-gt <pdf> [options]         VLM-guided convergence vs ground truth
#   ./run.sh synthetic [options]             Generate synthetic reproduction PDF
#   ./run.sh status                          Show recent tuning results
#   ./run.sh status-report [options]         Create artifact-derived DoD/blocker report
#   ./run.sh verify --job-dir DIR            Verify runtime artifacts and write receipt
#   ./run.sh file-maintainer-ticket --job-dir DIR [--create]
#   ./run.sh coverage-loop [options]         Create Coverage anti-hallucination plan-loop artifact
#   ./run.sh memory-qa [options]             Create Memory/Qdrant final QA report
#   ./run.sh history                         List all pdf-lab code changes
#   ./run.sh rollback --sha <sha>            Rollback a specific fix
#   ./run.sh verify-real <pdf> <fixture_dir>  Verify tuned params on real PDF
#   ./run.sh regression-check --sha <sha>    Re-run regression for a fix
#
set -e

INVOCATION_DIR="$PWD"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
export UV_PROJECT_ENVIRONMENT="${PDF_LAB_UV_ENV:-/mnt/storage12tb/skills/pdf-lab/.venv}"

PDF_OXIDE_ROOT="${PDF_OXIDE_ROOT:-$INVOCATION_DIR}"
export PDF_OXIDE_ROOT
if [[ -d "$PDF_OXIDE_ROOT/python" ]]; then
    export PYTHONPATH="$PDF_OXIDE_ROOT/python${PYTHONPATH:+:$PYTHONPATH}"
fi

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
  pdf-lab forensic <pdf> [options]        Page PNG + beautified JSON/schema report
  pdf-lab toc-scan <pdf> [options]        Build section map before scans
  pdf-lab preset-scan <pdf> [options]     Sweep every pdf_oxide preset
  pdf-lab agent-scan <pdf> [options]      Create agent expected-elements JSON
  pdf-lab extract-pages <pdf> --pages N   Extract selected pages with pdf_oxide
  pdf-lab compare-json <expected> <actual> Compare expected vs actual JSON
  pdf-lab agentic-extract <pdf> [options] Run agentic-first convergence skeleton
  pdf-lab final-pass <final_extraction.json> Generate human triage queue
  pdf-lab table-scan <pdf> [options]      Find table pages without pdf_oxide
  pdf-lab element-scan <pdf> [options]    Inventory pdf_oxide element layers
  pdf-lab compare <pdf> <gt.json>         Compare extraction vs ground truth
  pdf-lab tune-gt <pdf> [options]         VLM-guided convergence vs ground truth
  pdf-lab synthetic [options]             Generate synthetic reproduction PDF
  pdf-lab status                          Show recent tuning results
  pdf-lab status-report [options]         Create artifact-derived DoD/blocker report
  pdf-lab verify --job-dir DIR            Verify runtime artifacts and write receipt
  pdf-lab file-maintainer-ticket --job-dir DIR [--create]
  pdf-lab coverage-loop [options]         Create Coverage anti-hallucination plan-loop artifact
  pdf-lab memory-qa [options]             Create Memory/Qdrant final QA report
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

Forensic Options:
  --query <text>            Search request to select an example page
  --page <n>                1-based page number; bypasses search
  --out <dir>               Output directory for page PNG, schema JSON, and HTML

TOC Scan Options:
  --out <dir>               Output directory for TOC JSON and HTML
  --toc-pages <n>           Front-matter pages to inspect for printed TOC evidence

Preset Scan Options:
  --out <dir>               Output directory for preset JSON, PNGs, and HTML
  --top-k <n>               Top pages to keep per preset
  --max-rendered <n>        Max high-signal pages to render
  --dpi <n>                 Render DPI for candidate thumbnails

Agentic Extraction Options:
  --out <dir>               Output directory for JSON contracts and diagnostics
  --target <float>          Required expected/actual JSON match accuracy
  --max-iterations <n>      Max extraction/compare attempts
  --max-pages <n>           Max representative pages selected by agent scan
  --preset <json>           Document-family preset JSON for isolated tuning
  --full-extract            Extract the entire document after target is reached

Final Pass Options:
  --out <dir>               Output directory for human_triage_queue.json
  --comparison <json>       Representative-page comparison JSON
  --preset <json>           Document-family preset JSON used for extraction
  --max-tasks <n>           Optional cap for smoke tests

Status Report Options:
  --out <html>              HTML report output path
  --json-out <json>         JSON report output path for UX/API consumption
  --public-dir <dir>        UX Lab public directory containing promoted artifacts
  --json                    Print JSON report to stdout

Table Scan Options:
  --out <dir>               Output directory for candidate JSON, PNGs, and HTML
  --max-candidates <n>      Max rendered candidate pages
  --dpi <n>                 Render DPI for candidate thumbnails

Element Scan Options:
  --out <dir>               Output directory for inventory JSON, PNGs, and HTML
  --max-rendered <n>        Max high-signal pages to render

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

  # Generate side-by-side page PNG and schema diagnostic report
  ./run.sh forensic /path/to/doc.pdf --query "complex table" --out /tmp/pdf-lab-forensic

  # Start here: build section map before extraction/triage
  ./run.sh toc-scan /path/to/doc.pdf --out /tmp/pdf-lab-toc-scan --json

  # Sweep every pdf_oxide semantic/generation preset
  ./run.sh preset-scan /path/to/doc.pdf --out /tmp/pdf-lab-preset-scan --json

  # Agentic-first JSON loop: expected JSON vs pdf_oxide actual JSON
  ./run.sh agentic-extract /path/to/doc.pdf \
    --out /tmp/pdf-lab-agentic --target 0.95 --max-iterations 5 --json

  # Same loop with an isolated document-family preset
  ./run.sh agentic-extract /path/to/doc.pdf \
    --preset python/pdf_oxide/presets/document_families/nist_sp_800_53r5_pdf.json \
    --out /tmp/pdf-lab-agentic-preset --target 0.95 --json

  # Find likely table pages without using pdf_oxide extraction
  ./run.sh table-scan /path/to/doc.pdf --out /tmp/pdf-lab-table-scan --json

  # Inventory every per-page element layer exposed by pdf_oxide
  ./run.sh element-scan /path/to/doc.pdf --out /tmp/pdf-lab-element-scan --json

  # VLM-guided convergence against ground truth
  ./run.sh tune-gt /path/to/fixture.pdf -g /path/to/ground_truth.json --max-rounds 5

  # Generate synthetic from patterns
  ./run.sh synthetic --patterns '["multi_column","split_tables"]' --output /tmp/repro.pdf

  # Artifact-derived definition-of-done report; use before claiming progress
  ./run.sh status-report \
    --out /tmp/pdf-lab-status-report.html \
    --json-out /tmp/pdf-lab-status-report.json
EOF
}

cmd_tune() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" tune "$@"
}

cmd_diagnose() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" diagnose "$@"
}

cmd_forensic() {
    if [[ $# -gt 0 && "$1" != /* && "$1" != -* && -e "$INVOCATION_DIR/$1" ]]; then
        set -- "$INVOCATION_DIR/$1" "${@:2}"
    fi
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" forensic "$@"
}

cmd_toc_scan() {
    if [[ $# -gt 0 && "$1" != /* && "$1" != -* && -e "$INVOCATION_DIR/$1" ]]; then
        set -- "$INVOCATION_DIR/$1" "${@:2}"
    fi
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" toc-scan "$@"
}

cmd_preset_scan() {
    if [[ $# -gt 0 && "$1" != /* && "$1" != -* && -e "$INVOCATION_DIR/$1" ]]; then
        set -- "$INVOCATION_DIR/$1" "${@:2}"
    fi
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" preset-scan "$@"
}

cmd_agent_scan() {
    if [[ $# -gt 0 && "$1" != /* && "$1" != -* && -e "$INVOCATION_DIR/$1" ]]; then
        set -- "$INVOCATION_DIR/$1" "${@:2}"
    fi
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" agent-scan "$@"
}

cmd_extract_pages() {
    if [[ $# -gt 0 && "$1" != /* && "$1" != -* && -e "$INVOCATION_DIR/$1" ]]; then
        set -- "$INVOCATION_DIR/$1" "${@:2}"
    fi
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" extract-pages "$@"
}

cmd_compare_json() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" compare-json "$@"
}

cmd_agentic_extract() {
    if [[ $# -gt 0 && "$1" != /* && "$1" != -* && -e "$INVOCATION_DIR/$1" ]]; then
        set -- "$INVOCATION_DIR/$1" "${@:2}"
    fi
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" agentic-extract "$@"
}

cmd_final_pass() {
    if [[ $# -gt 0 && "$1" != /* && "$1" != -* && -e "$INVOCATION_DIR/$1" ]]; then
        set -- "$INVOCATION_DIR/$1" "${@:2}"
    fi
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" final-pass "$@"
}

cmd_table_scan() {
    if [[ $# -gt 0 && "$1" != /* && "$1" != -* && -e "$INVOCATION_DIR/$1" ]]; then
        set -- "$INVOCATION_DIR/$1" "${@:2}"
    fi
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" table-scan "$@"
}

cmd_element_scan() {
    if [[ $# -gt 0 && "$1" != /* && "$1" != -* && -e "$INVOCATION_DIR/$1" ]]; then
        set -- "$INVOCATION_DIR/$1" "${@:2}"
    fi
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" element-scan "$@"
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

cmd_status_report() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" status-report "$@"
}

cmd_coverage_loop() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" coverage-loop "$@"
}

cmd_memory_qa() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/pdf_lab.py" memory-qa "$@"
}

cmd_verify() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/runtime_verify.py" "$@"
}

cmd_file_maintainer_ticket() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/scripts/file_maintainer_ticket.py" "$@"
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
    forensic)
        shift
        cmd_forensic "$@"
        ;;
    toc-scan)
        shift
        cmd_toc_scan "$@"
        ;;
    preset-scan)
        shift
        cmd_preset_scan "$@"
        ;;
    agent-scan)
        shift
        cmd_agent_scan "$@"
        ;;
    extract-pages)
        shift
        cmd_extract_pages "$@"
        ;;
    compare-json)
        shift
        cmd_compare_json "$@"
        ;;
    agentic-extract)
        shift
        cmd_agentic_extract "$@"
        ;;
    final-pass)
        shift
        cmd_final_pass "$@"
        ;;
    table-scan)
        shift
        cmd_table_scan "$@"
        ;;
    element-scan)
        shift
        cmd_element_scan "$@"
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
    status-report)
        shift
        cmd_status_report "$@"
        ;;
    coverage-loop)
        shift
        cmd_coverage_loop "$@"
        ;;
    memory-qa)
        shift
        cmd_memory_qa "$@"
        ;;
    verify)
        shift
        cmd_verify "$@"
        ;;
    file-maintainer-ticket)
        shift
        cmd_file_maintainer_ticket "$@"
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
