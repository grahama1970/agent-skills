#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

test -f "$SKILL_DIR/SKILL.md"
test -f "$SKILL_DIR/run.sh"
test -f "$SKILL_DIR/scripts/bakeoff.py"
test -f "$SKILL_DIR/references/make-interfaces-feel-better.md"
test -x "$SKILL_DIR/run.sh"

python3 -m py_compile "$SKILL_DIR/scripts/bakeoff.py"

rg -n '`new`|`improve`|`ship`|/mockup-lab|/review-design|/test-interactions|/create-image|/ux-lab|Can you \\$create-mockup bakeoff' "$SKILL_DIR/SKILL.md" >/dev/null
rg -n 'concentric|optical|tabular|transition: all|hit areas' "$SKILL_DIR/references/make-interfaces-feel-better.md" >/dev/null

echo "create-mockup sanity: PASS"
