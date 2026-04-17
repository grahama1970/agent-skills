#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"
echo "=== [create-journal-entry] Sanity Check ==="

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
JOURNAL_MODULE="$SKILLS_DIR/memory/persona_journal.py"
if [[ -f "$JOURNAL_MODULE" ]]; then
    echo "PASS"
else
    echo "FAIL: persona_journal.py not found at $JOURNAL_MODULE"
    exit 1
fi

# Check 5: persona_journal.py syntax check
echo -n "Check 5 - persona_journal.py syntax: "
if python3 -m py_compile "$JOURNAL_MODULE" 2>/dev/null; then
    echo "PASS"
else
    echo "FAIL: syntax error in persona_journal.py"
    exit 1
fi

# Check 6: YAML frontmatter in SKILL.md
echo -n "Check 6 - SKILL.md frontmatter: "
if head -1 "$SCRIPT_DIR/SKILL.md" | grep -q '^---'; then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

# Check 7: Sub-modules exist
echo -n "Check 7 - Journal sub-modules: "
MISSING=0
for mod in persona_journal_mood.py persona_journal_memory.py persona_journal_generation.py; do
    if [[ ! -f "$SKILLS_DIR/memory/$mod" ]]; then
        echo "WARN: missing $mod"
        MISSING=1
    fi
done
[[ $MISSING -eq 0 ]] && echo "PASS"
[[ $MISSING -ne 0 ]] && echo "WARN (non-fatal, monolith fallback may work)"

# Check 8: memory_integration.py exists in persona-journal
echo -n "Check 8 - memory_integration.py: "
if [[ -f "$SKILLS_DIR/persona-journal/memory_integration.py" ]]; then
    echo "PASS"
else
    echo "WARN: memory_integration.py not found (memory hooks disabled)"
fi

echo ""
echo "SKIP: Journal generation (requires CHUTES_API_KEY and LLM)"
echo "SKIP: ArangoDB storage (requires running ArangoDB)"
echo ""
echo "Result: PASS"
