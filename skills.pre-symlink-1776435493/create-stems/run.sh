#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
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

usage() {
    cat << 'EOF'
create-stems: Audio stem separation (Demucs + UVR)

Usage: ./run.sh <command> [options]

Commands:
  separate    Separate audio into stems
  sanity      Run environment health checks
  help        Show this help

Examples:
  ./run.sh separate --mix song.wav --out ./stems
  ./run.sh separate --mix song.wav --out ./stems --instrument vocals
  ./run.sh separate --mix song.wav --out ./stems --instrument oud
  ./run.sh separate --mix song.wav --out ./stems --model htdemucs --segment 12
  ./run.sh sanity
EOF
}

ensure_venv() {
    cd "${SCRIPT_DIR}"
    if [[ ! -d "${SCRIPT_DIR}/.venv" ]]; then
        echo "Creating virtual environment..."
        uv sync --quiet
    fi
}

CMD="${1:-help}"
shift || true

case "${CMD}" in
    separate)
        ensure_venv
        cd "${SCRIPT_DIR}"
        exec uv run python cli.py separate "$@"
        ;;
    sanity)
        exec bash "${SCRIPT_DIR}/sanity.sh"
        ;;
    help|--help|-h)
        usage
        exit 0
        ;;
    *)
        echo "Unknown command: ${CMD}"
        usage
        exit 1
        ;;
esac
