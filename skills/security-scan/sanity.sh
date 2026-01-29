#!/usr/bin/env bash
# Sanity check for security-scan skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== security-scan sanity check ==="

# Add ~/.local/bin to PATH for gitleaks/trivy
export PATH="$HOME/.local/bin:$PATH"

# Check 1: run.sh --help works
echo "[1/4] Testing run.sh --help..."
if ./run.sh --help > /dev/null 2>&1; then
    echo "  ✓ run.sh --help works"
else
    echo "  ✗ run.sh --help failed"
    exit 1
fi

# Check 2: Python imports succeed
echo "[2/4] Testing Python imports..."
if python -c "import security_scan; print('  ✓ security_scan imports')"; then
    :
else
    echo "  ✗ security_scan import failed"
    exit 1
fi

# Check 3: CLI version command works
echo "[3/4] Testing version command..."
VERSION=$(python security_scan.py version 2>&1)
if [[ "$VERSION" == *"security-scan"* ]]; then
    echo "  ✓ version command works: $VERSION"
else
    echo "  ✗ version command failed"
    exit 1
fi

# Check 4: External tools available
echo "[4/4] Checking external tools..."
TOOLS_OK=true
for tool in semgrep bandit pip-audit gitleaks trivy; do
    if command -v "$tool" &> /dev/null; then
        echo "  ✓ $tool available"
    else
        echo "  ✗ $tool not found"
        TOOLS_OK=false
    fi
done

if [ "$TOOLS_OK" = false ]; then
    echo ""
    echo "WARNING: Some tools missing. Install them for full functionality."
    echo "  pip install semgrep bandit pip-audit"
    echo "  See SKILL.md for gitleaks/trivy installation"
fi

echo ""
echo "=== sanity check PASSED ==="
exit 0
