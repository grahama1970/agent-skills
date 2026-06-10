#!/usr/bin/env bash
unset VIRTUAL_ENV
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export REVIEW_PAGE_CALLER_CWD="${PWD}"
cd "$SCRIPT_DIR"
exec uv run --project "$SCRIPT_DIR" python page_review.py "$@"
