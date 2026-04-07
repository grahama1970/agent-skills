#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== monitor-episodic-archiver sanity ==="

# 1. Core files exist
echo -n "Core files exist... "
for f in monitor_archiver.py state.py task_monitor_integration.py run.sh SKILL.md; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        exit 1
    fi
done
echo "OK"

# 2. run.sh is executable
echo -n "run.sh executable... "
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "OK"
else
    echo "FAIL"
    exit 1
fi

# 3. CLI loads
echo -n "CLI loads... "
if uv run --with typer --with rich --with python-arango --with loguru --with httpx --with python-dotenv --no-project -- python monitor_archiver.py --help >/dev/null 2>&1; then
    echo "OK"
else
    echo "FAIL"
    exit 1
fi

# 4. Nightly command exists
echo -n "Nightly command exists... "
HELP_OUT=$(uv run --with typer --with rich --with python-arango --with loguru --with httpx --with python-dotenv --no-project -- python monitor_archiver.py --help 2>&1)
if echo "$HELP_OUT" | grep -q "nightly"; then
    echo "OK"
else
    echo "FAIL: nightly not in help output"
    exit 1
fi

# 5. ArangoDB reachable
echo -n "ArangoDB reachable... "
if curl -sf http://localhost:8529/_api/version >/dev/null 2>&1; then
    echo "OK"
else
    echo "SKIP (ArangoDB not running)"
fi

# 6. State dir writable
echo -n "State dir writable... "
STATE_DIR="$HOME/.pi/monitor-episodic-archiver"
mkdir -p "$STATE_DIR"
touch "$STATE_DIR/.sanity_test" && rm "$STATE_DIR/.sanity_test"
echo "OK"

# 7. Scheduler exists
echo -n "Scheduler available... "
SCHEDULER="$SCRIPT_DIR/../scheduler/run.sh"
if [[ -x "$SCHEDULER" ]]; then
    echo "OK"
else
    echo "SKIP (scheduler not found)"
fi

echo "=== sanity passed ==="
