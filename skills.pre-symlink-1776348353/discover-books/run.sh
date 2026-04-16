#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Discover books via OpenLibrary API with taxonomy integration

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
cd "$SCRIPT_DIR"

# Ensure dependencies
if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Sync dependencies if needed
if [[ ! -d ".venv" ]]; then
    uv sync --quiet
fi

CMD="${1:-help}"
shift || true

case "$CMD" in
    similar)
        uv run python -m src.cli similar "$@"
        ;;
    by-author|author)
        uv run python -m src.cli by-author "$@"
        ;;
    search-subject|subject)
        uv run python -m src.cli search-subject "$@"
        ;;
    bridge)
        uv run python -m src.cli bridge "$@"
        ;;
    trending)
        uv run python -m src.cli trending "$@"
        ;;
    fresh)
        uv run python -m src.cli fresh "$@"
        ;;
    recommendations|rec)
        uv run python -m src.cli recommendations "$@"
        ;;
    check)
        uv run python -m src.cli check "$@"
        ;;
    sanity)
        ./sanity.sh
        ;;
    help|--help|-h)
        echo "discover-books: Book discovery via OpenLibrary API"
        echo ""
        echo "Commands:"
        echo "  similar <book>       Find similar books"
        echo "  by-author <name>     Get books by author"
        echo "  search-subject <subj> Search by subject/genre"
        echo "  bridge <attr>        Search by bridge (Precision, Resilience, etc.)"
        echo "  trending             Get trending/popular books"
        echo "  fresh                Get recent releases"
        echo "  recommendations      Get recommendations (requires consume-book history)"
        echo "  check                Test API connectivity"
        echo "  sanity               Run sanity checks"
        echo ""
        echo "Options:"
        echo "  -n, --limit N        Max results (default: 10)"
        echo "  -j, --json           Output as JSON (includes taxonomy)"
        echo ""
        echo "Examples:"
        echo "  ./run.sh similar 'Dune'"
        echo "  ./run.sh by-author 'Frank Herbert'"
        echo "  ./run.sh search-subject 'science fiction'"
        echo "  ./run.sh bridge Resilience"
        echo "  ./run.sh trending --json"
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
