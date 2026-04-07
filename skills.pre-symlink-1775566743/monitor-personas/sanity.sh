#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== monitor-personas Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh monitor.py integrations.py sources.py state.py personas.yaml pyproject.toml; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: $f missing"
        exit 1
    fi
done
echo "OK"

# Check 2: run.sh is executable
echo -n "Check 2: run.sh executable... "
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not executable"
    exit 1
fi
echo "OK"

# Check 3: Python dependencies importable
echo -n "Check 3: Python dependencies... "
if ! python3 -c "import typer; import yaml; import rich" 2>/dev/null; then
    echo "FAIL: Missing Python deps (typer, pyyaml, rich)"
    echo "  Run: cd $SCRIPT_DIR && uv sync"
    exit 1
fi
echo "OK"

# Check 4: personas.yaml is valid YAML
echo -n "Check 4: personas.yaml valid... "
if ! python3 -c "import yaml; yaml.safe_load(open('$SCRIPT_DIR/personas.yaml'))" 2>/dev/null; then
    echo "FAIL: personas.yaml is not valid YAML"
    exit 1
fi
echo "OK"

# Check 5: help command works
echo -n "Check 5: help command... "
if ! "$SCRIPT_DIR/run.sh" help >/dev/null 2>&1; then
    echo "FAIL: run.sh help failed"
    exit 1
fi
echo "OK"

# Check 6: State directory writable
echo -n "Check 6: State directory... "
STATE_DIR="${PERSONA_MONITOR_STATE_DIR:-$HOME/.pi/monitor-personas}"
mkdir -p "$STATE_DIR" 2>/dev/null
if [[ ! -w "$STATE_DIR" ]]; then
    echo "FAIL: $STATE_DIR not writable"
    exit 1
fi
echo "OK ($STATE_DIR)"

# Check 7: yt-dlp available (used for YouTube persona monitoring)
echo -n "Check 7: yt-dlp... "
if ! command -v yt-dlp >/dev/null 2>&1; then
    echo "WARN (yt-dlp not found; YouTube source checks will fail)"
else
    echo "OK"
fi

# Check 8: integrations module loads
echo -n "Check 8: integrations module... "
if ! python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/integrations.py').read())" 2>/dev/null; then
    echo "FAIL: integrations.py has syntax errors"
    exit 1
fi
echo "OK"

echo "Result: PASS"
