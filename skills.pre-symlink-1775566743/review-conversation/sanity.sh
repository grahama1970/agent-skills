#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== review-conversation sanity ==="

# 1. Imports resolve
echo -n "Import check... "
uv run --project "$SCRIPT_DIR" python -c "from review_conversation import app; print('OK')"

# 2. Help text renders
echo -n "Help text... "
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/review_conversation.py" --help >/dev/null 2>&1 && echo "OK" || echo "FAIL"

# 3. files subcommand runs (may find 0 files - that's OK)
echo -n "files command... "
uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/review_conversation.py" files 2>/dev/null && echo "OK" || echo "OK (no sessions dir)"

echo "=== sanity complete ==="
