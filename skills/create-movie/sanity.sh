#!/usr/bin/env bash
#
# Sanity check for create-movie skill
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== create-movie Sanity Check ==="

# 1. Check Python syntax
echo -n "[1/5] Python syntax... "
python -m py_compile "${SCRIPT_DIR}/orchestrator.py"
echo "OK"

# 2. Check dependencies can import
echo -n "[2/5] Dependencies... "
uv run --project "${SCRIPT_DIR}" python -c "import click; import rich; print('OK')"

# 3. Check CLI help works
echo -n "[3/5] CLI help... "
uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/orchestrator.py" --help > /dev/null
echo "OK"

# 4. Check all subcommands registered
echo -n "[4/5] Subcommands... "
HELP_OUTPUT=$(uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/orchestrator.py" --help 2>&1)
for cmd in create research script build-tools generate assemble learn study study-all; do
    if ! echo "$HELP_OUTPUT" | grep -q "$cmd"; then
        echo "FAIL: missing command '$cmd'"
        exit 1
    fi
done
echo "OK"

# 5. Check Docker/FFmpeg sanity scripts
echo -n "[5/5] Core dependencies... "
"${SCRIPT_DIR}/sanity/run_all.sh" > /dev/null 2>&1 && echo "OK" || echo "WARN (Docker/FFmpeg optional)"

echo ""
echo "All sanity checks passed!"
