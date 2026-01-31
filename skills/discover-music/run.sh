#!/usr/bin/env bash
# Discover music via MusicBrainz + ListenBrainz

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
    search-tag|tag)
        uv run python -m src.cli search-tag "$@"
        ;;
    bridge)
        uv run python -m src.cli bridge "$@"
        ;;
    fresh)
        uv run python -m src.cli fresh "$@"
        ;;
    user-top|user)
        uv run python -m src.cli user-top "$@"
        ;;
    check)
        uv run python -m src.cli check "$@"
        ;;
    sanity)
        ./sanity.sh
        ;;
    help|--help|-h)
        echo "discover-music: Music discovery via MusicBrainz + ListenBrainz"
        echo ""
        echo "Commands:"
        echo "  similar <artist>     Find similar artists"
        echo "  trending             Get trending artists site-wide"
        echo "  search-tag <tag>     Search by genre/style tag"
        echo "  bridge <attr>        Search by HMT bridge (Precision, Resilience, etc.)"
        echo "  fresh                Get fresh/new releases"
        echo "  user-top <username>  Get user's top artists"
        echo "  check                Test API connectivity"
        echo "  sanity               Run sanity checks"
        echo ""
        echo "Options:"
        echo "  -n, --limit N        Max results (default: 10)"
        echo "  -j, --json           Output as JSON"
        echo "  -r, --range RANGE    Time range: week, month, year, all_time"
        echo ""
        echo "Examples:"
        echo "  ./run.sh similar 'Chelsea Wolfe'"
        echo "  ./run.sh trending --range week"
        echo "  ./run.sh search-tag 'doom metal'"
        echo "  ./run.sh bridge Corruption"
        echo "  ./run.sh fresh --json"
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
