#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# /streamdeck-lab — Stream Deck layout evaluator, generator, and ground truth editor

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
cd "$SCRIPT_DIR"

# Ensure uv available
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
    gui|app)
        uv run --project "$SCRIPT_DIR" python app.py "$@"
        ;;

    evaluate)
        uv run --project "$SCRIPT_DIR" python streamdeck_lab.py evaluate "$@"
        ;;

    evaluate-all)
        uv run --project "$SCRIPT_DIR" python streamdeck_lab.py evaluate-all "$@"
        ;;

    generate)
        uv run --project "$SCRIPT_DIR" python streamdeck_lab.py generate "$@"
        ;;

    mutate)
        uv run --project "$SCRIPT_DIR" python streamdeck_lab.py mutate "$@"
        ;;

    push)
        uv run --project "$SCRIPT_DIR" python streamdeck_lab.py push "$@"
        ;;

    events)
        uv run --project "$SCRIPT_DIR" python streamdeck_lab.py events "$@"
        ;;

    promote)
        uv run --project "$SCRIPT_DIR" python streamdeck_lab.py promote "$@"
        ;;

    sanity)
        bash "${SCRIPT_DIR}/sanity.sh"
        ;;

    help|--help|-h)
        echo "streamdeck-lab: Stream Deck layout evaluation and generation"
        echo ""
        echo "GUI:"
        echo "  gui|app            Launch the Stream Deck Lab QML application"
        echo ""
        echo "Evaluation:"
        echo "  evaluate           Evaluate a template against ground truth"
        echo "  evaluate-all       Evaluate all templates"
        echo ""
        echo "Generation:"
        echo "  generate           Generate a dynamic page layout from context + events"
        echo "  mutate             Apply a single event mutation to a template"
        echo "  push               Generate and push a page to Stream Deck hardware"
        echo ""
        echo "Catalog:"
        echo "  events             List available events (optionally filtered by context)"
        echo "  promote            Tag a template as promoted/lab-verified"
        echo ""
        echo "Utility:"
        echo "  sanity             Check dependencies and environment"
        echo ""
        echo "Examples:"
        echo "  ./run.sh gui"
        echo "  ./run.sh evaluate --template sentinel_hud"
        echo "  ./run.sh evaluate-all"
        echo "  ./run.sh generate --context sentinel_hud --events missile_warning,fuel_bingo --json"
        echo "  ./run.sh mutate --template sentinel_hud --event threat_popup --json"
        echo "  ./run.sh events --context sentinel_hud"
        ;;

    *)
        echo "Unknown command: $CMD"
        echo "Run './run.sh help' for usage"
        exit 1
        ;;
esac
