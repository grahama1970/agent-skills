#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== create-sound-design Sanity Check ==="

# 1. Python syntax check
echo "[1/6] Python syntax..."
python3 -m py_compile create_sound_design/*.py 2>/dev/null && echo "OK" || { echo "FAIL"; exit 1; }

# 2. Dependencies available
echo "[2/6] Dependencies..."
if [[ ! -d .venv ]]; then
    uv venv .venv
    uv pip install -e .
fi
source .venv/bin/activate
python -c "import typer, loguru, rich, yaml" && echo "OK" || { echo "FAIL"; exit 1; }

# 3. CLI help
echo "[3/6] CLI help..."
python -m create_sound_design.cli --help >/dev/null 2>&1 && echo "OK" || { echo "FAIL"; exit 1; }

# 4. Subcommands available
echo "[4/6] Subcommands..."
for cmd in start continue status list auto export; do
    python -m create_sound_design.cli $cmd --help >/dev/null 2>&1 || { echo "FAIL: $cmd"; exit 1; }
done
echo "OK"

# 5. sfx-catalog integration
echo "[5/6] sfx-catalog integration..."
SFX_CATALOG_PATH="$SCRIPT_DIR/../sfx-catalog"
if [[ -d "$SFX_CATALOG_PATH" ]]; then
    echo "OK (sfx-catalog available)"
else
    echo "WARN (sfx-catalog not found - will use graceful fallback)"
fi

# 6. Import check
echo "[6/6] Core imports..."
python -c "from create_sound_design import run_sound_design_session" && echo "OK" || { echo "FAIL"; exit 1; }

echo ""
echo "All sanity checks passed!"
