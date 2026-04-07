#!/usr/bin/env bash
#
# Sanity check for create-story skill
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== create-story Sanity Check ==="

# 1. Check Python syntax
echo -n "[1/4] Python syntax... "
python -m py_compile "${SCRIPT_DIR}/orchestrator.py"
echo "OK"

# 2. Check dependencies can import
echo -n "[2/4] Dependencies... "
uv run --project "${SCRIPT_DIR}" python -c "import click; import rich; print('OK')"

# 3. Check CLI help works
echo -n "[3/4] CLI help... "
uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/orchestrator.py" --help > /dev/null
echo "OK"

# 4. Check subcommands registered
echo -n "[4/4] Subcommands... "
HELP_OUTPUT=$(uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/orchestrator.py" --help 2>&1)
for cmd in create research draft critique refine; do
    if ! echo "$HELP_OUTPUT" | grep -q "$cmd"; then
        echo "FAIL: missing command '$cmd'"
        exit 1
    fi
done
echo "OK"

echo ""
echo "All sanity checks passed!"
