#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [distill] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md run.sh; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
[[ $FAIL -eq 0 ]] && echo "PASS"
[[ $FAIL -ne 0 ]] && exit 1

# Check 2: run.sh is executable
echo -n "Check 2 - run.sh executable: "
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "PASS"
else
    echo "FAIL: run.sh not executable"
    exit 1
fi

# Check 3: doc2qra skill exists (distill forwards to /doc2qra)
echo -n "Check 3 - doc2qra skill: "
DOC2QRA_RUN="$SCRIPT_DIR/../doc2qra/run.sh"
if [[ -f "$DOC2QRA_RUN" ]]; then
    echo "PASS (found at $DOC2QRA_RUN)"
else
    echo "FAIL: doc2qra not found at $DOC2QRA_RUN"
    FAIL=1
fi

# Check 4: YAML frontmatter
echo -n "Check 4 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

# Check 5: Bash syntax check on run.sh
echo -n "Check 5 - run.sh bash syntax: "
if bash -n "$SCRIPT_DIR/run.sh" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: run.sh has syntax errors"
    exit 1
fi

echo ""
echo "SKIP: Full execution test (requires doc2qra and API keys)"
echo ""
echo "Result: PASS"
