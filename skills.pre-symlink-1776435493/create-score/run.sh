#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# create-score Skill Runner
# Scene music generation via ACE-Step Docker
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

usage() {
    cat <<EOF
Usage: ./run.sh <command> [options]

Commands:
  up                            Start ACE-Step Docker service
  down                          Stop ACE-Step Docker service
  generate --prompt "..." --out FILE  Generate scene music
  sanity                        Run fast sanity checks
  sanity-full                   Run full pipeline test (GPU required)

Options:
  --help                        Show this help message

Examples:
  ./run.sh up
  ./run.sh generate --prompt "cinematic tension, strings" --duration-s 30 --out scene.wav
  ./run.sh down
EOF
}

# Check for uv
if ! command -v uv >/dev/null 2>&1; then
    echo "[create-score] Error: uv not found. Install uv first." >&2
    exit 1
fi

# Parse command
COMMAND="${1:-help}"
shift || true

case "$COMMAND" in
    up|down|generate)
        exec uv run --project "${SCRIPT_DIR}" python -m create_score.cli "$COMMAND" "$@"
        ;;
    sanity)
        exec "${SCRIPT_DIR}/sanity/sanity.sh"
        ;;
    sanity-full)
        exec "${SCRIPT_DIR}/sanity/sanity_full.sh"
        ;;
    help|--help|-h)
        usage
        exit 0
        ;;
    *)
        echo "Unknown command: $COMMAND"
        usage
        exit 1
        ;;
esac
