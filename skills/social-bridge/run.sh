#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Social Bridge - Security Content Aggregator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source .env files for credentials
if [[ -f "$SCRIPT_DIR/../../../.env" ]]; then
    set -a
    source "$SCRIPT_DIR/../../../.env"
    set +a
fi

# Run the social-bridge CLI in the skill's uv project environment.
exec uv run --project "$SCRIPT_DIR" python "$SCRIPT_DIR/social_bridge.py" "$@"
