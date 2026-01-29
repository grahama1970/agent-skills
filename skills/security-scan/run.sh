#!/usr/bin/env bash
# security-scan: Self-hosted security scanning orchestrator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add ~/.local/bin to PATH for gitleaks/trivy
export PATH="$HOME/.local/bin:$PATH"

# Run with uv if available, otherwise fall back to python
if command -v uv &> /dev/null; then
    exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/security_scan.py" "$@"
else
    exec python "$SCRIPT_DIR/security_scan.py" "$@"
fi
