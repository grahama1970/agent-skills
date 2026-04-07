#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# train-voice: Unified voice training for personas
# Orchestrates PersonaPlex + Qwen3-TTS with interview collaboration

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
ROOT_DIR="$(dirname "$(dirname "$SKILLS_DIR")")"

# Storage paths
VOICE_STORAGE="${VOICE_STORAGE:-/mnt/storage12tb/media/personas}"
PERSONAPLEX_CACHE="${PERSONAPLEX_CACHE:-$HOME/.cache/personaplex}"

usage() {
    cat << 'USAGE'
train-voice: Unified voice training for personas

Usage: ./run.sh <command> [options]

Commands:
  train <persona>       Train voice from known references
  design <persona>      Collaborative voice design (triggers /interview)
  status <persona>      Check training status
  test <persona>        Generate test audio
  list                  List all voices with status

Train Options:
  --type TYPE           fictional, learning, narrator (default: fictional)
  --references REFS     Comma-separated "Actor:register" pairs
  --skip-personaplex    Skip PersonaPlex embedding extraction
  --skip-qwen3          Skip Qwen3-TTS training
  --epochs N            Qwen3-TTS training epochs (default: 5)
  --background          Run training in background

Design Options:
  --mode MODE           tui or html (default: auto)
  --output FILE         Save interview results
  --skip-train          Only design, don't auto-train

Examples:
  ./run.sh train "Embry" --references "Hailee Steinfeld:confident,Kristen Stewart:uncertain"
  ./run.sh design "Marcus Aurelius"
  ./run.sh status "Embry"
  ./run.sh test "Embry" --text "Hello, world"

USAGE
}

cmd_train() {
    local persona="${1:-}"
    shift || true

    if [[ -z "$persona" ]]; then
        echo "Error: Persona name required"
        usage
        exit 1
    fi

    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/train.py" train "$persona" "$@"
}

cmd_design() {
    local persona="${1:-}"
    shift || true

    if [[ -z "$persona" ]]; then
        echo "Error: Persona name required"
        usage
        exit 1
    fi

    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/design.py" "$persona" "$@"
}

cmd_status() {
    local persona="${1:-}"

    if [[ -z "$persona" ]]; then
        echo "Error: Persona name required"
        usage
        exit 1
    fi

    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/train.py" status "$persona"
}

cmd_test() {
    local persona="${1:-}"
    shift || true

    if [[ -z "$persona" ]]; then
        echo "Error: Persona name required"
        usage
        exit 1
    fi

    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/train.py" test "$persona" "$@"
}

cmd_list() {
    uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/train.py" list "$@"
}

# Main dispatch
case "${1:-}" in
    train)
        shift
        cmd_train "$@"
        ;;
    design)
        shift
        cmd_design "$@"
        ;;
    status)
        shift
        cmd_status "$@"
        ;;
    test)
        shift
        cmd_test "$@"
        ;;
    list)
        shift
        cmd_list "$@"
        ;;
    -h|--help|help|"")
        usage
        ;;
    *)
        echo "Unknown command: $1"
        usage
        exit 1
        ;;
esac
