#!/usr/bin/env bash
# Sanity check: GitHub Copilot with GPT-5
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/run_sanity.sh" github gpt-5 "${1:-120}"
