#!/usr/bin/env bash
# Sanity check for ops-embry-agent skill.
# Validates that the systemd unit file and install script exist,
# and that busctl is available for D-Bus introspection.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="${SCRIPT_DIR}/../../systemd"
ERRORS=0

echo "=== ops-embry-agent sanity ==="

# Check systemd unit file exists
if [[ -f "${SYSTEMD_DIR}/embry-agent.service" ]]; then
    echo "[OK] embry-agent.service found"
else
    echo "[FAIL] embry-agent.service not found at ${SYSTEMD_DIR}"
    ERRORS=$((ERRORS + 1))
fi

# Check install script exists and is executable-ready
if [[ -f "${SYSTEMD_DIR}/install.sh" ]]; then
    echo "[OK] install.sh found"
else
    echo "[FAIL] install.sh not found"
    ERRORS=$((ERRORS + 1))
fi

# Check busctl is available
if command -v busctl &>/dev/null; then
    echo "[OK] busctl available"
else
    echo "[WARN] busctl not found — D-Bus introspection won't work"
fi

# Check journalctl is available
if command -v journalctl &>/dev/null; then
    echo "[OK] journalctl available"
else
    echo "[WARN] journalctl not found — log viewing won't work"
fi

# Check run.sh is present
if [[ -f "${SCRIPT_DIR}/run.sh" ]]; then
    echo "[OK] run.sh found"
else
    echo "[FAIL] run.sh not found"
    ERRORS=$((ERRORS + 1))
fi

if [[ $ERRORS -gt 0 ]]; then
    echo "SANITY FAILED: $ERRORS error(s)"
    exit 1
fi

echo "SANITY OK"
