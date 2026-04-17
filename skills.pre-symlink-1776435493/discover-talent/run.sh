#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Discover actors/talent via TMDB API with taxonomy integration

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
    search)
        uv run python -m discover_talent.cli search "$@"
        ;;
    filmography)
        uv run python -m discover_talent.cli filmography "$@"
        ;;
    by-movie|cast)
        uv run python -m discover_talent.cli by-movie "$@"
        ;;
    bridge)
        uv run python -m discover_talent.cli bridge "$@"
        ;;
    similar)
        uv run python -m discover_talent.cli similar "$@"
        ;;
    images)
        uv run python -m discover_talent.cli images "$@"
        ;;
    check)
        uv run python -m discover_talent.cli check "$@"
        ;;
    sanity)
        ./sanity/sanity.sh
        ;;
    help|--help|-h)
        echo "discover-talent: Actor/talent discovery via TMDB API"
        echo ""
        echo "Commands:"
        echo "  search <name>        Search actors by name"
        echo "  filmography <name>   Get actor's filmography"
        echo "  by-movie <movie>     Get cast of a movie"
        echo "  bridge <attr>        Search by bridge (Precision, Resilience, etc.)"
        echo "  similar <name>       Find similar actors"
        echo "  images <name>        Get profile images for an actor"
        echo "  check                Test API connectivity"
        echo "  sanity               Run sanity checks"
        echo ""
        echo "Options:"
        echo "  -n, --limit N        Max results (default: 10)"
        echo "  -j, --json           Output as JSON (includes taxonomy)"
        echo "  -d, --department D   Department filter (Acting, Directing)"
        echo ""
        echo "Examples:"
        echo "  ./run.sh search 'Florence Pugh'"
        echo "  ./run.sh filmography 'Florence Pugh'"
        echo "  ./run.sh by-movie 'Oppenheimer'"
        echo "  ./run.sh bridge Corruption"
        echo "  ./run.sh similar 'Florence Pugh'"
        echo "  ./run.sh images 'Ana de Armas' --limit 5 --json"
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
