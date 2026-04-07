#!/bin/bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== best-practices-d3 sanity check ==="

# 1. Rules directory exists with files
rule_count=$(ls "$SKILL_DIR/rules/"*.md 2>/dev/null | wc -l)
if [[ "$rule_count" -lt 5 ]]; then
  echo "FAIL: Expected at least 5 rule files, found $rule_count"
  exit 1
fi
echo "OK: $rule_count rules found"

# 2. Every rule has severity and category
for rule in "$SKILL_DIR/rules/"*.md; do
  name=$(basename "$rule" .md)
  if ! grep -q '^\*\*Severity\*\*:' "$rule"; then
    echo "FAIL: $name missing Severity"
    exit 1
  fi
  if ! grep -q '^\*\*Category\*\*:' "$rule"; then
    echo "FAIL: $name missing Category"
    exit 1
  fi
done
echo "OK: All rules have severity and category"

# 3. run.sh list works
output=$(bash "$SKILL_DIR/run.sh" list 2>&1)
if ! echo "$output" | grep -q "D3 Best Practice Rules"; then
  echo "FAIL: run.sh list didn't produce expected output"
  exit 1
fi
echo "OK: run.sh list works"

# 4. run.sh check works (on this skill dir — should be clean)
check_output=$(bash "$SKILL_DIR/run.sh" check "$SKILL_DIR" 2>&1)
echo "OK: run.sh check runs without error"

echo ""
echo "All sanity checks passed"
