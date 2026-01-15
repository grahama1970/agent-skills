#!/usr/bin/env bash
# NOTE: gpt-5.2 not available on GitHub Copilot CLI
# Redirecting to gpt-5
echo "WARN: gpt-5.2 not available on github, using gpt-5 instead"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/run_sanity.sh" github gpt-5 "${1:-120}"
