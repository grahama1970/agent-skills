#!/usr/bin/env bash
#
# create-music Sanity Check Suite
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== create-music Sanity Suite ==="
echo ""

# Environment check
echo "[1/3] Environment check..."
bash "${SCRIPT_DIR}/sanity/check_env.sh"
echo ""

# Check if we have test stems to validate
TEST_STEMS="${SCRIPT_DIR}/work/test_stems"
TEST_MIX="${SCRIPT_DIR}/work/test_mix.wav"

if [[ -d "$TEST_STEMS" ]] && [[ -f "$TEST_MIX" ]]; then
    echo "[2/3] Alignment check..."
    uv run python "${SCRIPT_DIR}/sanity/check_alignment.py" --stems "$TEST_STEMS"
    echo ""

    echo "[3/3] Reconstruction check..."
    uv run python "${SCRIPT_DIR}/sanity/check_reconstruction.py" --mix "$TEST_MIX" --stems "$TEST_STEMS"
    echo ""
else
    echo "[2/3] Alignment check... SKIPPED (no test data)"
    echo "[3/3] Reconstruction check... SKIPPED (no test data)"
    echo ""
    echo "To run full sanity suite, provide test data:"
    echo "  mkdir -p ${SCRIPT_DIR}/work/test_stems"
    echo "  cp /path/to/mix.wav ${TEST_MIX}"
    echo "  cp /path/to/stems/*.wav ${TEST_STEMS}/"
fi

echo "=== Sanity Suite Complete ==="
