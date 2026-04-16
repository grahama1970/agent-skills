#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [best-practices-prompt] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - Required files: "
FAIL=0
for f in SKILL.md; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        FAIL=1
    fi
done
[[ $FAIL -eq 0 ]] && echo "PASS"

# Check 2: YAML frontmatter in SKILL.md
echo -n "Check 2 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

# Check 3: Has provides field
echo -n "Check 3 - provides field: "
if grep -q '^provides:' "$SCRIPT_DIR/SKILL.md"; then
    echo "PASS"
else
    echo "FAIL: missing provides field"
    exit 1
fi

# Check 4: Has composes field
echo -n "Check 4 - composes field: "
if grep -q '^composes:' "$SCRIPT_DIR/SKILL.md"; then
    echo "PASS"
else
    echo "FAIL: missing composes field"
    exit 1
fi

# Check 5: Has weasel word table (core rule)
echo -n "Check 5 - Weasel word table present: "
if grep -q 'Weasel Word' "$SCRIPT_DIR/SKILL.md"; then
    echo "PASS"
else
    echo "FAIL: missing weasel word table"
    exit 1
fi

# Check 6: Has checklist section
echo -n "Check 6 - Prompt checklist present: "
if grep -q 'Prompt Template Checklist' "$SCRIPT_DIR/SKILL.md"; then
    echo "PASS"
else
    echo "FAIL: missing prompt checklist section"
    exit 1
fi

# Check 7: Has at least 10 rules
echo -n "Check 7 - Rule count: "
RULE_COUNT=$(grep -c '^### Rule:' "$SCRIPT_DIR/SKILL.md" || true)
if [[ "$RULE_COUNT" -lt 10 ]]; then
    echo "FAIL: only $RULE_COUNT rules found (expected 10+)"
    exit 1
fi
echo "PASS ($RULE_COUNT rules)"

echo ""
echo "Result: PASS"
