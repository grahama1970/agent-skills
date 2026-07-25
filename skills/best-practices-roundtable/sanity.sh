#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKILL_MD="$SCRIPT_DIR/SKILL.md"
ASK_SKILL="$REPO_ROOT/skills/ask/SKILL.md"

echo "=== [best-practices-roundtable] Sanity Check ==="

python3 - "$SKILL_MD" <<'PY'
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
text = path.read_text()
if not text.startswith("---\n"):
    raise SystemExit("FAIL: SKILL.md does not start with YAML frontmatter")
try:
    _, frontmatter, body = text.split("---", 2)
except ValueError as exc:
    raise SystemExit(f"FAIL: malformed frontmatter: {exc}") from exc
meta = yaml.safe_load(frontmatter)
required = ["name", "description", "triggers", "provides", "composes", "complies"]
missing = [key for key in required if key not in meta]
if missing:
    raise SystemExit(f"FAIL: missing frontmatter fields: {missing}")
if meta["name"] != "best-practices-roundtable":
    raise SystemExit(f"FAIL: wrong skill name: {meta['name']!r}")
for dep in ("ask", "best-practices-tau-dag"):
    if dep not in meta["composes"]:
        raise SystemExit(f"FAIL: missing composed dependency {dep!r}")
for phrase in (
    "concurrent seats with equal context",
    "Model agreement is advisory evidence",
    "EXECUTABLE_SLICES",
    "NEEDS_ATTENTION",
    "attributed dissent",
):
    if phrase not in body:
        raise SystemExit(f"FAIL: missing protocol phrase: {phrase}")
print("Check 1 - SKILL.md contract: PASS")
PY

echo -n "Check 2 - Ask composes roundtable practices: "
if ! grep -A20 '^composes:' "$ASK_SKILL" | grep -q 'best-practices-roundtable'; then
    echo "FAIL"
    exit 1
fi
echo "PASS"

echo -n "Check 3 - Ask body points roundtables to this skill: "
if ! grep -q 'best-practices-roundtable' "$ASK_SKILL"; then
    echo "FAIL"
    exit 1
fi
echo "PASS"

echo -n "Check 4 - No placeholder TODOs: "
if grep -q 'TODO' "$SKILL_MD"; then
    echo "FAIL"
    exit 1
fi
echo "PASS"

echo ""
echo "Result: PASS"
