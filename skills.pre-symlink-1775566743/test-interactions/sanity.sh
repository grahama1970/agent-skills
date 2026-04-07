#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_ROOT="$(dirname "$SKILL_DIR")"
EXIT=0

echo "=== test-interactions sanity ==="

# Check composed skills exist
for dep in surf review-design create-design-board interview; do
    if [ -d "$SKILLS_ROOT/$dep" ]; then
        echo "PASS: composed skill /$dep found"
    else
        echo "FAIL: composed skill /$dep missing at $SKILLS_ROOT/$dep"
        EXIT=1
    fi
done

# Check Python entrypoint parses
cd "$SKILL_DIR"
if uv run python -c "import test_interactions" 2>/dev/null; then
    echo "PASS: test_interactions.py imports cleanly"
else
    echo "FAIL: test_interactions.py import error"
    EXIT=1
fi

# Check typer CLI help
if uv run python test_interactions.py --help >/dev/null 2>&1; then
    echo "PASS: CLI --help works"
else
    echo "FAIL: CLI --help failed"
    EXIT=1
fi

exit $EXIT
