#!/usr/bin/env bash
# Discover movies via TMDB API with taxonomy integration

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
    trending)
        uv run python -m src.cli trending "$@"
        ;;
    search-genre|genre)
        uv run python -m src.cli search-genre "$@"
        ;;
    by-director|director)
        uv run python -m src.cli by-director "$@"
        ;;
    bridge)
        uv run python -m src.cli bridge "$@"
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
        echo "discover-movies: Movie discovery via TMDB API"
        echo ""
        echo "Commands:"
        echo "  similar <movie>      Find similar movies"
        echo "  trending             Get trending movies"
        echo "  search-genre <genre> Search by genre"
        echo "  by-director <name>   Get movies by director"
        echo "  bridge <attr>        Search by bridge (Precision, Resilience, etc.)"
        echo "  fresh                Get new releases"
        echo "  recommendations      Get recommendations (requires consume-movie history)"
        echo "  check                Test API connectivity"
        echo "  sanity               Run sanity checks"
        echo ""
        echo "Options:"
        echo "  -n, --limit N        Max results (default: 10)"
        echo "  -j, --json           Output as JSON (includes taxonomy)"
        echo "  -r, --range RANGE    Time range: day, week"
        echo ""
        echo "Examples:"
        echo "  ./run.sh similar 'There Will Be Blood'"
        echo "  ./run.sh trending --range week"
        echo "  ./run.sh search-genre 'psychological thriller'"
        echo "  ./run.sh by-director 'Paul Thomas Anderson'"
        echo "  ./run.sh bridge Corruption"
        echo "  ./run.sh fresh --json"
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
