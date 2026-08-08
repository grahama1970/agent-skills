#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

[[ -f "$ROOT/SKILL.md" ]] || fail "missing SKILL.md"
[[ "$(sed -n '1p' "$ROOT/SKILL.md")" == "---" ]] || fail "SKILL.md must open with YAML frontmatter"
grep -q '^name: best-practices-bespoke-design$' "$ROOT/SKILL.md" || fail "wrong or missing skill name"
grep -q '^description:' "$ROOT/SKILL.md" || fail "missing description"
grep -q '^triggers:' "$ROOT/SKILL.md" || fail "missing triggers"
grep -q '^provides:' "$ROOT/SKILL.md" || fail "missing provides"
grep -q '^composes:' "$ROOT/SKILL.md" || fail "missing composes"
grep -q '^complies:' "$ROOT/SKILL.md" || fail "missing complies"

python -m json.tool "$ROOT/schemas/bespoke-design-receipt.schema.json" >/dev/null
python -m json.tool "$ROOT/fixtures/passing-receipt.json" >/dev/null
python -m json.tool "$ROOT/fixtures/failing-receipt.json" >/dev/null
python - "$ROOT/scripts/validate_receipt.py" <<'PYCODE'
from pathlib import Path
import sys
path = Path(sys.argv[1])
compile(path.read_text(encoding='utf-8'), str(path), 'exec')
PYCODE

python "$ROOT/scripts/validate_receipt.py" "$ROOT/fixtures/passing-receipt.json" >/dev/null

if python "$ROOT/scripts/validate_receipt.py" "$ROOT/fixtures/failing-receipt.json" >/dev/null 2>&1; then
  fail "negative fixture unexpectedly passed"
fi

required=(
  "$ROOT/references/owltastic-design-dna.md"
  "$ROOT/references/visual-world-brief.yaml"
  "$ROOT/references/acceptance-tests.md"
)
for path in "${required[@]}"; do
  [[ -s "$path" ]] || fail "missing or empty reference: $path"
done

printf 'PASS: best-practices-bespoke-design sanity\n'
