#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# security-scan: Self-hosted security scanning orchestrator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Add ~/.local/bin to PATH for gitleaks/trivy
export PATH="$HOME/.local/bin:$PATH"

exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/security_scan.py" "$@"
