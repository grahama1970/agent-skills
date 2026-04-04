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
    prove)
        shift
        exec uv run --directory "$SCRIPT_DIR" python prove.py "$@"
        ;;
    *)
        echo "Usage: $0 {prove} [args...]"
        echo ""
        echo "Commands:"
        echo "  prove    Lean4 formal theorem proving via certainly-bridge"
        echo ""
        echo "Examples:"
        echo "  $0 prove 'Prove n+0=n'"
        echo ""
        echo "For LLM completions, call the proxy directly:"
        echo "  curl http://localhost:4001/v1/chat/completions \\"
        echo "    -H 'Authorization: Bearer sk-dev-proxy-123' \\"
        echo "    -H 'Content-Type: application/json' \\"
        echo "    -d '{\"model\":\"text\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}'"
        exit 1
        ;;
esac
