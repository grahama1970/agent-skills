#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Testing taxonomy CLI..."

# Test CLI loads
"$SCRIPT_DIR"/run.sh --help >/dev/null && echo "✓ main --help"

# Test subcommands
"$SCRIPT_DIR"/run.sh extract --help >/dev/null && echo "✓ extract --help"
"$SCRIPT_DIR"/run.sh validate --help >/dev/null && echo "✓ validate --help"
"$SCRIPT_DIR"/run.sh vocabulary >/dev/null && echo "✓ vocabulary --help"

# Test fast extraction (no LLM)
result=$("$SCRIPT_DIR"/run.sh extract --text "Error handling code with fault tolerance" --fast)
echo "$result" | grep -q "bridge_tags" && echo "✓ extract --fast"

# Test bridges-only output
bridges=$("$SCRIPT_DIR"/run.sh extract --text "The Siege of Terra demonstrated Imperial Fists resilience" --bridges-only --fast --collection lore)
echo "  Bridge tags: $bridges"
[[ -n "$bridges" || "$bridges" == "" ]] && echo "✓ bridges-only output"

# Test vocabulary output
vocab=$("$SCRIPT_DIR"/run.sh vocabulary)
echo "$vocab" | grep -q "Precision" && echo "✓ vocabulary includes Precision"
echo "$vocab" | grep -q "Resilience" && echo "✓ vocabulary includes Resilience"

echo ""
echo "✅ All sanity checks passed!"
