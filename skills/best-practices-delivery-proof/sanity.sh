#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_MD="$SCRIPT_DIR/SKILL.md"

echo "=== [best-practices-delivery-proof] Sanity Check ==="

python3 - "$SKILL_MD" <<'PY'
import sys
from pathlib import Path

import yaml

path = Path(sys.argv[1])
text = path.read_text()
if not text.startswith("---\n"):
    raise SystemExit("FAIL: SKILL.md does not start with YAML frontmatter")
front = yaml.safe_load(text.split("---\n", 2)[1])
for key in ("name", "description", "triggers", "provides", "composes", "complies"):
    if not front.get(key):
        raise SystemExit(f"FAIL: frontmatter missing {key}")
if front["name"] != "best-practices-delivery-proof":
    raise SystemExit("FAIL: frontmatter name mismatch")

body = text.split("---\n", 2)[2]
# Each rule is load-bearing; a future edit must not silently drop one.
required = [
    "Rule 1", "Rule 2", "Rule 3", "Rule 4", "Rule 5", "Rule 6", "Rule 7",
    "DESTINATION",
    "stopVisible=true composerChars=0",
    "read this whole file before acting",
    "NEEDS_ATTENTION",
    "pkill -f",
]
for needle in required:
    if needle not in body:
        raise SystemExit(f"FAIL: body missing required content: {needle!r}")
print("PASS: frontmatter and all seven rules present")
PY

echo "=== Sanity OK ==="
