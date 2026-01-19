#!/bin/bash
# Sanity check for surf skill
# Verifies Chrome and CDP functionality work correctly
set -e

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$SKILL_DIR/run.sh"

echo "=== Surf Skill Sanity Check ==="
echo ""

# 1. Check Chrome is installed
echo -n "1. Chrome installation... "
if command -v google-chrome &>/dev/null || command -v chromium &>/dev/null; then
    CHROME=$(command -v google-chrome || command -v chromium)
    echo "OK ($CHROME)"
else
    echo "FAIL (Chrome not found)"
    exit 1
fi

# 2. Check run.sh exists and is executable
echo -n "2. run.sh executable... "
if [[ -x "$RUN" ]]; then
    echo "OK"
else
    echo "FAIL (run.sh not executable)"
    exit 1
fi

# 3. Test CDP start (if not already running)
echo -n "3. CDP start... "
if curl -s "http://127.0.0.1:9222/json/version" &>/dev/null; then
    echo "OK (already running)"
    ALREADY_RUNNING=1
else
    if "$RUN" cdp start &>/dev/null; then
        echo "OK (started)"
        ALREADY_RUNNING=0
    else
        echo "FAIL (could not start)"
        exit 1
    fi
fi

# 4. Test CDP endpoint responds
echo -n "4. CDP endpoint... "
if curl -s "http://127.0.0.1:9222/json/version" | grep -q "webSocketDebuggerUrl"; then
    echo "OK"
else
    echo "FAIL (endpoint not responding)"
    exit 1
fi

# 5. Test CDP env command
echo -n "5. CDP env command... "
if "$RUN" cdp env 2>/dev/null | grep -q "BROWSERLESS_DISCOVERY_URL"; then
    echo "OK"
else
    echo "FAIL"
    exit 1
fi

# 6. Test CDP status command
echo -n "6. CDP status command... "
if "$RUN" cdp status 2>/dev/null | grep -q "RUNNING"; then
    echo "OK"
else
    echo "FAIL"
    exit 1
fi

# 7. Test help command
echo -n "7. Help command... "
if "$RUN" --help 2>/dev/null | grep -q "CDP Management"; then
    echo "OK"
else
    echo "FAIL"
    exit 1
fi

# Cleanup if we started CDP
if [[ "$ALREADY_RUNNING" == "0" ]]; then
    echo -n "8. CDP stop... "
    if "$RUN" cdp stop &>/dev/null; then
        echo "OK"
    else
        echo "FAIL"
    fi
fi

echo ""
echo "=== All sanity checks passed ==="
