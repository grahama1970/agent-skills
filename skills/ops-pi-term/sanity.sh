#!/usr/bin/env bash
# sanity.sh — Quick validation that ops-pi-term skill is functional
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  [OK] $desc"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== ops-pi-term sanity check ==="

# 1. SKILL.md exists and has valid frontmatter
check "SKILL.md exists" test -f "$SKILL_DIR/SKILL.md"
check "SKILL.md has frontmatter" grep -q "^name: ops-pi-term" "$SKILL_DIR/SKILL.md"
check "SKILL.md has triggers" grep -q "^  - test pi term" "$SKILL_DIR/SKILL.md"
check "SKILL.md has provides" grep -q "^  - pi-term-testing" "$SKILL_DIR/SKILL.md"
check "SKILL.md has composes" grep -q "^  - test-lab" "$SKILL_DIR/SKILL.md"
check "SKILL.md has taxonomy" grep -q "^  - validation" "$SKILL_DIR/SKILL.md"

# 2. run.sh exists and is executable
check "run.sh exists" test -f "$SKILL_DIR/run.sh"
check "run.sh is executable" test -x "$SKILL_DIR/run.sh"

# 3. Test script exists
check "interaction test script exists" test -f "$SKILL_DIR/tests/pi-term-interaction-tests.sh"

# 4. Required directories
check "tests/ directory exists" test -d "$SKILL_DIR/tests"
check "screenshots/ directory exists" test -d "$SKILL_DIR/screenshots"
check "fixtures/ directory exists" test -d "$SKILL_DIR/fixtures"

# 5. Required tools available
check "xdotool available" command -v xdotool
check "import (ImageMagick) available" command -v import

# 6. WezTerm repo exists
check "WezTerm repo exists" test -d ${HOME}/workspace/experiments/wezterm
check "Pi Mono Lua config exists" test -d ${HOME}/workspace/experiments/pi-mono/packages/wezterm

echo ""
echo "  Sanity: $PASS pass, $FAIL fail"
[[ $FAIL -eq 0 ]]
