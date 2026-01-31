#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure uv is available
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Please install uv."
    exit 1
fi

# Dispatch to sub-scripts
case "$1" in
    batch)
        shift
        exec uv run --directory "$SCRIPT_DIR" python batch.py "$@"
        ;;
    vlm)
        shift
        exec uv run --directory "$SCRIPT_DIR" python vlm.py "$@"
        ;;
    prove)
        shift
        exec uv run --directory "$SCRIPT_DIR" python prove.py "$@"
        ;;
    preflight)
        shift
        exec uv run --directory "$SCRIPT_DIR" python preflight.py "$@"
        ;;
    *)
        echo "Usage: $0 {batch|vlm|prove|preflight} [args...]"
        echo ""
        echo "Examples:"
        echo "  $0 batch single 'Hello world'"
        echo "  $0 batch file --input prompts.jsonl"
        echo "  $0 vlm describe image.png"
        echo "  $0 prove 'Prove n+0=n'"
        echo "  $0 preflight preflight --model $CHUTES_MODEL_ID"
        exit 1
        ;;
esac
