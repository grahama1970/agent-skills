#!/bin/bash
#
# Debug PDF Skill - Failure-to-fixture automation for PDF extractors
#
# Usage:
#   ./run.sh analyze <url>                    Analyze a single failed PDF URL
#   ./run.sh batch <url-file>                 Analyze multiple URLs from file
#   ./run.sh combine <output.pdf>             Combine all fixtures into one test PDF
#   ./run.sh list-patterns                    Show known failure patterns
#   ./run.sh status                           Show current debug session status
#   ./run.sh detectors                        List registered detection functions
#   ./run.sh recall [query]                   Recall patterns from memory
#   ./run.sh learn --pattern <p> --details <d>  Store pattern to memory
#
# Examples:
#   ./run.sh analyze "https://example.com/broken.pdf"
#   ./run.sh batch failed_urls.txt --output report.json
#   ./run.sh combine all_failures.pdf --max-pages 20
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Data directory for persistent state
DATA_DIR="${DEBUG_PDF_DATA:-$HOME/.pi/debug-pdf}"
mkdir -p "$DATA_DIR"

# Detect sibling skill paths (relative to pi-mono structure)
PI_SKILLS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MEMORY_SKILLS_DIR="${MEMORY_SKILLS_DIR:-/home/graham/workspace/experiments/memory/.agents/skills}"

# Validate Python environment
ensure_venv() {
    if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
        echo "[debug-pdf] Creating virtual environment..."
        uv venv "$SCRIPT_DIR/.venv"
    fi
    if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
        uv pip install -e "$SCRIPT_DIR" -q 2>/dev/null || true
    fi
}

show_help() {
    cat <<'EOF'
Debug PDF - Failure-to-fixture automation for PDF extractors

Usage:
  debug-pdf analyze <url>                 Analyze a single failed PDF URL
  debug-pdf batch <url-file>              Analyze multiple URLs from file
  debug-pdf combine [output.pdf]          Combine fixtures into one test PDF
  debug-pdf list-patterns                 Show known failure patterns
  debug-pdf status                        Show current session status

Options:
  --repro                Create reproduction fixture (default: true)
  --no-repro             Skip fixture generation
  --output <path>        Custom output path for results
  --max-pages <n>        Max pages for combined PDF (default: 20)
  --send-inbox           Send results to extractor inbox

Examples:
  # Analyze single failure
  debug-pdf analyze "https://example.com/broken.pdf"

  # Process batch of failed URLs
  echo "https://url1.pdf" > failed.txt
  echo "https://url2.pdf" >> failed.txt
  debug-pdf batch failed.txt --output analysis.json

  # Combine all discovered issues into stress test PDF
  debug-pdf combine stress_test.pdf --max-pages 15

Workflow:
  1. Extractor reports failures via agent-inbox
  2. debug-pdf analyzes each failure URL
  3. Identifies patterns (scanned, TOC dots, watermarks, etc.)
  4. Generates minimal reproduction fixtures
  5. Combines into single test PDF for regression testing

For full documentation see SKILL.md
EOF
}

cmd_analyze() {
    local url="$1"
    shift

    if [[ -z "$url" ]]; then
        echo "Error: URL required" >&2
        echo "Usage: debug-pdf analyze <url> [--repro] [--send-inbox]" >&2
        exit 1
    fi

    ensure_venv
    source "$SCRIPT_DIR/.venv/bin/activate"
    python "$SCRIPT_DIR/debug_pdf.py" main --url "$url" "$@"
}

cmd_batch() {
    local url_file="$1"
    shift

    if [[ -z "$url_file" || ! -f "$url_file" ]]; then
        echo "Error: URL file required and must exist" >&2
        echo "Usage: debug-pdf batch <url-file> [--output report.json]" >&2
        exit 1
    fi

    ensure_venv
    source "$SCRIPT_DIR/.venv/bin/activate"
    python "$SCRIPT_DIR/debug_pdf.py" batch --file "$url_file" "$@"
}

cmd_combine() {
    local output="${1:-combined_fixtures.pdf}"
    shift 2>/dev/null || true

    ensure_venv
    source "$SCRIPT_DIR/.venv/bin/activate"
    python "$SCRIPT_DIR/debug_pdf.py" combine --output "$output" "$@"
}

cmd_list_patterns() {
    cat <<'EOF'
Known PDF Failure Patterns:

STRUCTURAL:
  scanned_no_ocr        - Scanned image PDF without text layer
  sparse_content_slides - Slide deck with minimal text per page
  multi_column          - Complex multi-column layouts
  watermarks            - Text obscured by watermark overlays

ENCODING:
  toc_noise             - Table of contents with dotted leaders (.......)
  metadata_artifacts    - Print metadata (Jkt/PO/Frm codes) in content
  invisible_chars       - Zero-width spaces, direction markers
  curly_quotes          - Windows-1252 encoded smart quotes
  ligatures             - fi/fl/ff ligature characters

LAYOUT:
  footnotes_inline      - Footnotes merged into body text
  split_tables          - Tables spanning multiple pages
  header_footer_bleed   - Headers/footers mixed into content
  diagram_heavy         - Many embedded diagrams/charts

NETWORK:
  archive_org_wrap      - Wayback Machine URL wrapper issues
  auth_required         - Marketing platform cookie/login gates
  access_restricted     - Government/defense access controls (403)

CONTRACT/SIGNATURE:
  signed_contract       - Contract with signature fields (first pages)
  government_signed     - DoD/Federal PKI signed document

Use fixture-tricky to generate test cases:
  cd ../fixture-tricky && ./run.sh gauntlet --output test.pdf

Use 'debug-pdf detectors' to see registered detection functions.
Use 'debug-pdf recall' to search memory for known patterns.
EOF
}

cmd_status() {
    echo "=== Debug PDF Session Status ==="
    echo ""

    if [[ -d "$DATA_DIR/sessions" ]]; then
        local count=$(find "$DATA_DIR/sessions" -name "*.json" 2>/dev/null | wc -l)
        echo "Sessions: $count"

        if [[ -f "$DATA_DIR/last_analysis.json" ]]; then
            echo ""
            echo "Last analysis:"
            jq -r '.url // "unknown"' "$DATA_DIR/last_analysis.json" 2>/dev/null || true
            jq -r '"  Patterns: " + (.patterns | join(", "))' "$DATA_DIR/last_analysis.json" 2>/dev/null || true
        fi
    else
        echo "No sessions found. Run 'debug-pdf analyze <url>' to start."
    fi

    echo ""
    echo "Fixture directory: $DATA_DIR/fixtures/"
    if [[ -d "$DATA_DIR/fixtures" ]]; then
        local fixtures=$(find "$DATA_DIR/fixtures" -name "*.pdf" 2>/dev/null | wc -l)
        echo "Generated fixtures: $fixtures"
    fi
}

# Main dispatch
case "${1:-}" in
    analyze)
        shift
        cmd_analyze "$@"
        ;;
    batch)
        shift
        cmd_batch "$@"
        ;;
    combine)
        shift
        cmd_combine "$@"
        ;;
    list-patterns|patterns)
        cmd_list_patterns
        ;;
    status)
        cmd_status
        ;;
    detectors)
        ensure_venv
        source "$SCRIPT_DIR/.venv/bin/activate"
        python "$SCRIPT_DIR/debug_pdf.py" detectors
        ;;
    recall)
        shift
        ensure_venv
        source "$SCRIPT_DIR/.venv/bin/activate"
        python "$SCRIPT_DIR/debug_pdf.py" recall "${1:-PDF extraction failure patterns}"
        ;;
    learn)
        shift
        ensure_venv
        source "$SCRIPT_DIR/.venv/bin/activate"
        python "$SCRIPT_DIR/debug_pdf.py" learn "$@"
        ;;
    -h|--help|help|"")
        show_help
        ;;
    *)
        # Default: treat first arg as URL for backward compatibility
        if [[ "$1" == --* ]]; then
            echo "Unknown option: $1" >&2
            show_help
            exit 1
        fi
        # Assume it's a URL for analyze
        cmd_analyze "$@"
        ;;
esac
