#!/usr/bin/env bash
# Sanity check for best-practices-streamdeck skill
set -euo pipefail

RULES_DIR="$(dirname "$0")/rules"

echo "=== best-practices-streamdeck sanity ==="

# Check all rule files have YAML frontmatter
fail=0
for f in "$RULES_DIR"/*.md; do
    [[ "$(basename "$f")" == _* ]] && continue
    if ! head -1 "$f" | grep -q '^---$'; then
        echo "FAIL: $f missing YAML frontmatter"
        fail=1
    fi
done

# Check SKILL.md exists
if [[ ! -f "$(dirname "$0")/SKILL.md" ]]; then
    echo "FAIL: SKILL.md missing"
    fail=1
fi

# Count rules
count=$(find "$RULES_DIR" -name '*.md' ! -name '_*' | wc -l)
echo "Rules: $count"

if [[ $fail -eq 0 ]]; then
    echo "PASS"
else
    echo "FAIL"
    exit 1
fi
