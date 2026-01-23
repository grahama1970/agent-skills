#!/usr/bin/env bash
# Normalize text to handle PDF/Unicode encoding issues
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Use python3 directly - this script has no external dependencies
exec python3 "$SCRIPT_DIR/normalize.py" "$@"
