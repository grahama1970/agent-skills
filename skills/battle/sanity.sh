#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Battle Skill Sanity ==="

# Check run.sh
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh exists and is executable"
else
    echo "  [FAIL] run.sh missing or not executable"
    exit 1
fi

# Check SKILL.md
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "  [PASS] SKILL.md exists"
else
    echo "  [FAIL] SKILL.md missing"
    exit 1
fi

# Check battle.py exists
if [[ -f "$SCRIPT_DIR/battle.py" ]]; then
    echo "  [PASS] battle.py exists"
else
    echo "  [FAIL] battle.py missing"
    exit 1
fi

# Check CLI help works
if "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    echo "  [PASS] run.sh --help works"
else
    echo "  [FAIL] run.sh --help failed"
    exit 1
fi

# Check required sibling skills exist
SKILLS_DIR="$SCRIPT_DIR/.."
for skill in hack anvil memory task-monitor; do
    if [[ -d "$SKILLS_DIR/$skill" ]]; then
        echo "  [PASS] Sibling skill '$skill' exists"
    else
        echo "  [WARN] Sibling skill '$skill' not found"
    fi
done

echo ""
echo "Result: PASS"
echo "Battle skill is ready."
