#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/project-state-uv-env}"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a; source "$PROJECT_ROOT/.env"; set +a
fi

show_usage() {
    cat <<'EOF'
Usage: run.sh <command> [args]

Commands:
  report          Generate comprehensive project state report
    --quick       Phase 1 only (infrastructure metrics, ~10s)
    --full        All 6 phases including external research (~2min)
    --json        Output as JSON (default: Markdown)
    --output FILE Write to file instead of stdout
    --cleanup-tail
                 Generate post-cleanup readiness state from a cleanup receipt
    --cleanup-receipt FILE
                 Existing cleanup receipt JSON for --cleanup-tail

  cleanup-tail    Write post-cleanup readiness artifacts without moving/deleting files
    --cleanup-receipt FILE  Existing cleanup receipt JSON
    --output-dir DIR        Destination for report.json, report.md, index.html

  config doctor   Check non-secret project-state configuration without prompting

  Default (no flag) runs Phases 1-4 + 6 (~30s):
    Infrastructure, Memory, Doc-Code Drift, Best Practices, Gap Analysis

Examples:
  ./run.sh report              # Standard 5-phase report
  ./run.sh report --quick      # Infrastructure only
  ./run.sh report --full       # All phases including competitive landscape
  ./run.sh report --json       # JSON output
  ./run.sh report --output state.json --json
  ./run.sh report --cleanup-tail --cleanup-receipt artifacts/cleanup/<run>/receipt.json --json --output artifacts/cleanup/project_state_after.json
  ./run.sh config doctor --json
EOF
}

# Check for uv
if command -v uv &> /dev/null; then
    EXEC=(uv run --project "$SCRIPT_DIR" python)
else
    EXEC=(python3)
fi

main() {
    if [[ $# -eq 0 ]]; then
        show_usage
        exit 1
    fi

    local command="$1"
    shift

    case "$command" in
        report)
            "${EXEC[@]}" "$SCRIPT_DIR/project_state.py" report "$@"
            ;;
        figures)
            "${EXEC[@]}" "$SCRIPT_DIR/project_state.py" figures "$@"
            ;;
        cleanup-tail)
            "${EXEC[@]}" "$SCRIPT_DIR/project_state.py" cleanup-tail "$@"
            ;;
        config)
            "${EXEC[@]}" "$SCRIPT_DIR/project_state.py" config "$@"
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            echo "Error: Unknown command: $command" >&2
            show_usage >&2
            exit 1
            ;;
    esac
}

main "$@"
