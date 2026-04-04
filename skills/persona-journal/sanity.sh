#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [persona-journal] Sanity Check ==="

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

# Check 3: Bash syntax check
echo -n "Check 3 - run.sh bash syntax: "
if bash -n "$SCRIPT_DIR/run.sh" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: run.sh has syntax errors"
    exit 1
fi

# Check 4: persona_journal.py exists in memory skill (run.sh dependency)
echo -n "Check 4 - persona_journal.py exists: "
JOURNAL_MODULE="$SCRIPT_DIR/../memory/persona_journal.py"
if [[ -f "$JOURNAL_MODULE" ]]; then
    echo "PASS"
else
    echo "WARN: persona_journal.py not found at $JOURNAL_MODULE"
    echo "  (run.sh delegates to this module)"
fi

# Check 5: If journal module exists, syntax check it
if [[ -f "$JOURNAL_MODULE" ]]; then
    echo -n "Check 5 - persona_journal.py syntax: "
    if python3 -m py_compile "$JOURNAL_MODULE" 2>/dev/null; then
        echo "PASS"
    else
        echo "FAIL: syntax error in persona_journal.py"
        exit 1
    fi
else
    echo "Check 5 - SKIP (persona_journal.py not found)"
fi

# Check 6: YAML frontmatter
echo -n "Check 6 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

echo ""
echo "SKIP: Journal generation (requires CHUTES_API_KEY and LLM)"
echo "SKIP: ArangoDB storage (requires running ArangoDB)"
echo "SKIP: /dogpile historical event lookup (requires API keys)"
echo ""
echo "Result: PASS"
