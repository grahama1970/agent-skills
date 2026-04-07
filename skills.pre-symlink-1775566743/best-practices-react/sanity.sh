#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

PASS=0; FAIL=0
check() {
    local desc="$1"; shift
    if "$@" > /dev/null 2>&1; then
        echo "  PASS: $desc"; PASS=$((PASS+1))
    else
        echo "  FAIL: $desc"; FAIL=$((FAIL+1))
    fi
}

echo "=== Sanity: best-practices-react ==="

# Core files
check "SKILL.md exists" test -f SKILL.md
check "README.md exists" test -f README.md
check "AGENTS.md exists" test -f AGENTS.md

# Sub-skill directories
check "skills/ dir exists" test -d skills
check "react-best-practices sub-skill" test -d skills/react-best-practices
check "web-design-guidelines sub-skill" test -d skills/web-design-guidelines
check "react-native-skills sub-skill" test -d skills/react-native-skills
check "composition-patterns sub-skill" test -d skills/composition-patterns

# Each sub-skill should have a SKILL.md
for subskill in react-best-practices web-design-guidelines react-native-skills composition-patterns; do
    check "$subskill/SKILL.md exists" test -f "skills/$subskill/SKILL.md"
done

# SKILL.md frontmatter
check "SKILL.md has name field" grep -q "^name:" SKILL.md
check "SKILL.md has description" grep -q "^description:" SKILL.md

echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ]
