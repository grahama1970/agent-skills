#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Testing review-story CLI..."

# Test CLI loads
"$SCRIPT_DIR"/run.sh --help >/dev/null && echo "✓ main --help"

# Test subcommands
"$SCRIPT_DIR"/run.sh review --help >/dev/null && echo "✓ review --help"
"$SCRIPT_DIR"/run.sh compare --help >/dev/null && echo "✓ compare --help"
"$SCRIPT_DIR"/run.sh synthesize --help >/dev/null && echo "✓ synthesize --help"

echo ""
echo "✅ All sanity checks passed!"
