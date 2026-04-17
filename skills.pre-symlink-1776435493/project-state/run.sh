#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

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
    --full        All 6 phases including /dogpile competitive research (~2min)
    --json        Output as JSON (default: Markdown)
    --output FILE Write to file instead of stdout

  Default (no flag) runs Phases 1-4 + 6 (~30s):
    Infrastructure, Memory, Doc-Code Drift, Best Practices, Gap Analysis

Examples:
  ./run.sh report              # Standard 5-phase report
  ./run.sh report --quick      # Infrastructure only
  ./run.sh report --full       # All phases including competitive landscape
  ./run.sh report --json       # JSON output
  ./run.sh report --output state.json --json
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
