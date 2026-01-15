#!/usr/bin/env bash
# Sanity check: Anthropic Claude with Opus 4.5
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/run_sanity.sh" anthropic opus-4.5 "${1:-120}"
