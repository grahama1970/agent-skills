#!/usr/bin/env bash
# Sanity checks for /ux-lab skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"
PACKAGE_DIR="${PROJECT_ROOT}/packages/ux-lab"

PASS=0
FAIL=0

check() {
    local label="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo "  PASS  ${label}"
        PASS=$((PASS + 1))
    else
        echo "  FAIL  ${label}"
        FAIL=$((FAIL + 1))
    fi
}

echo "ux-lab sanity checks"
echo "========================="

# Node >= 18
check "node >= 18" bash -c '
    ver=$(node --version 2>/dev/null | sed "s/^v//")
    major=$(echo "$ver" | cut -d. -f1)
    [[ "$major" -ge 18 ]]
'

# npm exists
check "npm exists" command -v npm

# package.json exists
check "packages/ux-lab/package.json exists" test -f "${PACKAGE_DIR}/package.json"

# SKILL.md exists
check "SKILL.md exists" test -f "${SCRIPT_DIR}/SKILL.md"

# run.sh is executable
check "run.sh is executable" test -x "${SCRIPT_DIR}/run.sh"

# ws package installed (WebSocket support)
check "ws package installed" test -d "${PACKAGE_DIR}/node_modules/ws"

# Test files exist
check "test/store.test.ts exists" test -f "${PACKAGE_DIR}/test/store.test.ts"
check "test/canvas.test.ts exists" test -f "${PACKAGE_DIR}/test/canvas.test.ts"
check "test/objects.test.ts exists" test -f "${PACKAGE_DIR}/test/objects.test.ts"
check "test/components.test.ts exists" test -f "${PACKAGE_DIR}/test/components.test.ts"
check "test/export.test.ts exists" test -f "${PACKAGE_DIR}/test/export.test.ts"
check "test/agent-store.test.ts exists" test -f "${PACKAGE_DIR}/test/agent-store.test.ts"
check "test/operation-log.test.ts exists" test -f "${PACKAGE_DIR}/test/operation-log.test.ts"
check "test/api.test.ts exists" test -f "${PACKAGE_DIR}/test/api.test.ts"
check "test/ws.test.ts exists" test -f "${PACKAGE_DIR}/test/ws.test.ts"
check "test/screenshot.test.ts exists" test -f "${PACKAGE_DIR}/test/screenshot.test.ts"
check "test/prompt.test.ts exists" test -f "${PACKAGE_DIR}/test/prompt.test.ts"
check "test/agent-panel.test.ts exists" test -f "${PACKAGE_DIR}/test/agent-panel.test.ts"
check "test/document.test.ts exists" test -f "${PACKAGE_DIR}/test/document.test.ts"
check "test/design.test.ts exists" test -f "${PACKAGE_DIR}/test/design.test.ts"

echo ""
echo "Results: ${PASS} passed, ${FAIL} failed"

if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
