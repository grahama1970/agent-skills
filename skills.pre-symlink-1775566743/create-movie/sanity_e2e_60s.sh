#!/bin/bash
#
# Real E2E 60-Second Dream Sequence Sanity Test
#
# This test produces ACTUAL video output - no mocks, no dry-runs.
# If dependencies/APIs are unavailable, it FAILS CLEARLY.
#
# Usage:
#   ./sanity_e2e_60s.sh              # Full 60s test
#   ./sanity_e2e_60s.sh --dry-run    # Pre-flight only
#   ./sanity_e2e_60s.sh --duration 30 # Shorter test
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Real E2E 60-Second Dream Sanity Check ==="
echo "Location: ${SCRIPT_DIR}"
echo ""

# Run the Python E2E test
uv run --project "${SCRIPT_DIR}" python "${SCRIPT_DIR}/sanity/e2e_60s_dream.py" "$@"
