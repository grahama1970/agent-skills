#!/usr/bin/env bash
# doc-to-qra: Convert document to Q&A pairs in memory
#
# Usage:
#   ./run.sh paper.pdf research
#   ./run.sh paper.pdf research "ML researcher"
#   ./run.sh https://arxiv.org/... research
#   ./run.sh paper.pdf research --dry-run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISTILL="$SCRIPT_DIR/../distill/run.sh"

# Parse args
INPUT="${1:-}"
SCOPE="${2:-}"
CONTEXT=""
DRY_RUN=""

shift 2 2>/dev/null || true

# Remaining args
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN="--dry-run" ;;
        *) CONTEXT="$arg" ;;
    esac
done

# Validate
if [[ -z "$INPUT" || -z "$SCOPE" ]]; then
    echo "doc-to-qra: Convert document to Q&A pairs in memory"
    echo ""
    echo "Usage: $0 <document> <scope> [context] [--dry-run]"
    echo ""
    echo "Examples:"
    echo "  $0 paper.pdf research"
    echo "  $0 paper.pdf research \"ML researcher\""
    echo "  $0 https://arxiv.org/pdf/... research"
    echo "  $0 paper.pdf research --dry-run"
    exit 1
fi

# Build distill command
ARGS=()

# Determine input type
if [[ "$INPUT" =~ ^https?:// ]]; then
    ARGS+=(--url "$INPUT")
elif [[ -f "$INPUT" ]]; then
    ARGS+=(--file "$INPUT")
else
    echo "Error: '$INPUT' is not a valid file or URL"
    exit 1
fi

ARGS+=(--scope "$SCOPE")

if [[ -n "$CONTEXT" ]]; then
    ARGS+=(--context "$CONTEXT")
fi

if [[ -n "$DRY_RUN" ]]; then
    ARGS+=(--dry-run)
fi

# Run distill
exec "$DISTILL" "${ARGS[@]}"
