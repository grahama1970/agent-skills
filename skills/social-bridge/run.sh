#!/usr/bin/env bash
# Social Bridge - Security Content Aggregator
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source .env files for credentials
if [[ -f "$SCRIPT_DIR/../../../.env" ]]; then
    set -a
    source "$SCRIPT_DIR/../../../.env"
    set +a
fi

# Use conda python if available (has telethon), otherwise system python
PYTHON="${CONDA_PYTHON:-/home/graham/miniconda3/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python"
fi

# Run the social-bridge CLI
"$PYTHON" "$SCRIPT_DIR/social_bridge.py" "$@"
