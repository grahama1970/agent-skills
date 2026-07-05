#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Ensure uv is available
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Please install uv."
    exit 1
fi

# Clear parent VIRTUAL_ENV to avoid mismatch warning when uv resolves its own .venv
unset VIRTUAL_ENV

# Dispatch to sub-scripts
case "$1" in
    generate-image)
        shift
        SCILLM_REPO="${SCILLM_REPO:-$HOME/workspace/experiments/scillm}"
        if [ ! -f "$SCILLM_REPO/scripts/generate_image.py" ]; then
            echo "Error: scillm image generator not found at $SCILLM_REPO/scripts/generate_image.py" >&2
            exit 1
        fi
        export PYTHONPATH="$SCILLM_REPO/src${PYTHONPATH:+:$PYTHONPATH}"
        exec python3 "$SCILLM_REPO/scripts/generate_image.py" "$@"
        ;;
    prove)
        shift
        exec uv run --directory "$SCRIPT_DIR" python prove.py "$@"
        ;;
    assess)
        shift
        exec python3 "$SCRIPT_DIR/scripts/assess_usage.py" "$@"
        ;;
    warm-check)
        shift
        exec python3 "$SCRIPT_DIR/scripts/warm_check.py" "$@"
        ;;
    *)
        echo "Usage: $0 {generate-image|prove|assess|warm-check} [args...]"
        echo ""
        echo "Commands:"
        echo "  generate-image  Generate an image artifact through the Scillm image surface"
        echo "  prove    Lean4 formal theorem proving via certainly-bridge"
        echo "  assess   Check external code for correct scillm usage patterns"
        echo ""
        echo "Examples:"
        echo "  $0 generate-image --prompt-file prompt.md --out image.png --json"
        echo "  $0 prove 'Prove n+0=n'"
        echo "  $0 assess /path/to/script.py"
        echo "  $0 assess /path/to/script.py --json"
        echo ""
        echo "For LLM completions, call the proxy directly:"
        echo "  curl http://localhost:4001/v1/chat/completions \\"
        echo "    -H 'Authorization: Bearer sk-dev-proxy-123' \\"
        echo "    -H 'Content-Type: application/json' \\"
        echo "    -d '{\"model\":\"text\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}'"
        exit 1
        ;;
esac
