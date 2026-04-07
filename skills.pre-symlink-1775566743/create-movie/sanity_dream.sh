#!/bin/bash
# sanity_dream.sh: Verify dream mode end-to-end
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Dream Mode Sanity Check ==="

# 1. Check help output (CLI structure)
echo -n "[1/4] CLI structure... "
uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/orchestrator.py" dream --help > /dev/null
echo "OK"

# 2. Check generate help
echo -n "[2/4] Generate subcommand... "
uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/orchestrator.py" dream generate --help > /dev/null
echo "OK"

# 3. Run end-to-end Python sanity test
echo "[3/4] End-to-end dream test..."
uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/sanity/dream_e2e.py" || {
    echo "❌ Dream E2E test failed"
    exit 1
}

# 4. Verify dream_mode.py fetch_day_residue can be imported
echo -n "[4/4] dream_mode imports... "
uv run --project "${SCRIPT_DIR}" python -c "from create_movie.phases.dream_mode import fetch_day_residue; print('OK')"

echo ""
echo "✅ Dream mode sanity check passed!"
