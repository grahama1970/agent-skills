#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Discover music via MusicBrainz + ListenBrainz

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
    youtube-search|yt-search)
        uv run python -m src.cli youtube-search "$@"
        ;;
    youtube-download|yt-download)
        uv run python -m src.cli youtube-download "$@"
        ;;
    youtube-stems|yt-stems)
        uv run python -m src.cli youtube-stems "$@"
        ;;
    recommend|rec)
        uv run python -m src.cli recommend "$@"
        ;;
    sanity)
        ./sanity.sh
        ;;
    help|--help|-h)
        echo "discover-music: Music discovery via MusicBrainz + ListenBrainz + YouTube"
        echo ""
        echo "Discovery Commands:"
        echo "  similar <artist>     Find similar artists"
        echo "  trending             Get trending artists site-wide"
        echo "  search-tag <tag>     Search by genre/style tag"
        echo "  bridge <attr>        Search by HMT bridge (Precision, Resilience, etc.)"
        echo "  fresh                Get fresh/new releases"
        echo "  user-top <username>  Get user's top artists"
        echo "  check                Test API connectivity"
        echo ""
        echo "Recommendation Engine:"
        echo "  recommend              Recommend artists from taste profile"
        echo "    --profile <path>     Path to taste profile JSON"
        echo "    --queue              Append to learn-artist training queue"
        echo ""
        echo "YouTube Integration:"
        echo "  youtube-search <query>   Search YouTube for music"
        echo "  youtube-download <id>    Download audio from YouTube"
        echo "  youtube-stems <id>       Download + separate stems (uses create-stems)"
        echo ""
        echo "Options:"
        echo "  -n, --limit N        Max results (default: 10)"
        echo "  -j, --json           Output as JSON"
        echo "  -o, --out DIR        Output directory"
        echo ""
        echo "Workflow Examples:"
        echo "  ./run.sh bridge Corruption                    # Find artists"
        echo "  ./run.sh youtube-search 'Nine Inch Nails Closer'"
        echo "  ./run.sh youtube-stems PTFwQP86BRs            # Download + stems"
        echo "  ./run.sh recommend --json                     # Recommendations from profile"
        echo "  ./run.sh recommend --queue                    # Recommend + queue for training"
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
