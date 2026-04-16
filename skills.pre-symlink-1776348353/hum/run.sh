#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# /hum — Persona humming pipeline
# Orchestrates: /ingest-youtube, /create-stems, /learn-artist, /create-music

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
    add)
        uv run python -m src.cli add "$@"
        ;;
    train)
        uv run python -m src.cli train "$@"
        ;;
    list)
        uv run python -m src.cli list "$@"
        ;;
    play)
        uv run python -m src.cli play "$@"
        ;;
    info)
        uv run python -m src.cli info "$@"
        ;;
    sanity)
        bash "${SCRIPT_DIR}/sanity.sh"
        ;;
    help|--help|-h)
        echo "hum: Persona humming pipeline"
        echo ""
        echo "Commands:"
        echo "  add <url>            Full pipeline: download, stem, convert, cache"
        echo "  train                Train persona RVC voice model"
        echo "  list                 List cached hums"
        echo "  play <track>         Play a cached hum through PipeWire"
        echo "  info <track>         Show track metadata"
        echo "  sanity               Check all dependencies"
        echo ""
        echo "Options:"
        echo "  --persona NAME       Target persona (default: embry)"
        echo "  --mood TAGS          Comma-separated mood tags"
        echo "  --bridges ATTRS      Comma-separated bridge attributes"
        echo "  --pitch N            Pitch shift in semitones (default: 0)"
        echo "  --f0method METHOD    F0 method: rmvpe, harvest, crepe (default: rmvpe)"
        echo "  --json               Output as JSON"
        echo ""
        echo "Examples:"
        echo "  ./run.sh add 'https://youtu.be/Dordpe3KX_I' --persona embry --mood playful"
        echo "  ./run.sh train --persona embry"
        echo "  ./run.sh list --persona embry"
        echo "  ./run.sh play hawaiian_war_chant"
        ;;
    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
