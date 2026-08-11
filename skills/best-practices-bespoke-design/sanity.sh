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
python -m json.tool "$ROOT/schemas/bespoke-review-bundle.schema.json" >/dev/null
python -m json.tool "$ROOT/schemas/bespoke-review-transport.schema.json" >/dev/null
python -m json.tool "$ROOT/fixtures/passing-receipt.json" >/dev/null
python -m json.tool "$ROOT/fixtures/failing-receipt.json" >/dev/null
python -m json.tool "$ROOT/fixtures/valid-url-review-bundle.json" >/dev/null
python -m json.tool "$ROOT/fixtures/valid-url-review-bundle-rotated-nonce.json" >/dev/null
python -m json.tool "$ROOT/fixtures/valid-attachment-review-bundle.json" >/dev/null
python -m json.tool "$ROOT/fixtures/valid-url-rater.json" >/dev/null
python -m json.tool "$ROOT/fixtures/valid-attachment-rater.json" >/dev/null
python -m json.tool "$ROOT/fixtures/valid-blocked-transport.json" >/dev/null

for script in \
  "$ROOT/scripts/validate_receipt.py" \
  "$ROOT/scripts/validate_review_bundle.py" \
  "$ROOT/scripts/validate_review_transport.py" \
  "$ROOT/scripts/prove_sequential_threshold.py"; do
  python - "$script" <<'PYCODE'
from pathlib import Path
import sys
path = Path(sys.argv[1])
compile(path.read_text(encoding='utf-8'), str(path), 'exec')
PYCODE
done

python "$ROOT/scripts/validate_receipt.py" "$ROOT/fixtures/passing-receipt.json" >/dev/null
python "$ROOT/scripts/validate_review_bundle.py" "$ROOT/fixtures/valid-url-review-bundle.json" >/dev/null
python "$ROOT/scripts/validate_review_bundle.py" "$ROOT/fixtures/valid-url-review-bundle-rotated-nonce.json" >/dev/null
python "$ROOT/scripts/validate_review_bundle.py" "$ROOT/fixtures/valid-attachment-review-bundle.json" >/dev/null
python "$ROOT/scripts/validate_review_transport.py" "$ROOT/fixtures/valid-url-rater.json" >/dev/null
python "$ROOT/scripts/validate_review_transport.py" "$ROOT/fixtures/valid-attachment-rater.json" >/dev/null
python "$ROOT/scripts/validate_review_transport.py" "$ROOT/fixtures/valid-blocked-transport.json" >/dev/null
python "$ROOT/scripts/prove_sequential_threshold.py" --yes-required 4 --seat-cap 5 >/dev/null

if python "$ROOT/scripts/validate_receipt.py" "$ROOT/fixtures/failing-receipt.json" >/dev/null 2>&1; then
  fail "negative fixture unexpectedly passed"
fi
for fixture in \
  invalid-missing-canonical-render.json \
  invalid-render-digest.json \
  invalid-candidate-as-credential.json \
  invalid-confidential-publication.json; do
  if python "$ROOT/scripts/validate_review_bundle.py" "$ROOT/fixtures/$fixture" >/dev/null 2>&1; then
    fail "negative review bundle fixture unexpectedly passed: $fixture"
  fi
done
for fixture in \
  invalid-wrong-fingerprint.json \
  invalid-leaked-nonce.json \
  invalid-preflight-counted-rater.json \
  invalid-unpreserved-raw-output.json \
  invalid-stale-unit.json \
  invalid-transport-alters-design-gate.json; do
  if python "$ROOT/scripts/validate_review_transport.py" "$ROOT/fixtures/$fixture" >/dev/null 2>&1; then
    fail "negative review transport fixture unexpectedly passed: $fixture"
  fi
done
python - "$ROOT/fixtures/valid-url-review-bundle.json" "$ROOT/fixtures/valid-url-review-bundle-rotated-nonce.json" <<'PYCODE'
import json
import sys
first = json.load(open(sys.argv[1], encoding="utf-8"))
second = json.load(open(sys.argv[2], encoding="utf-8"))
assert first["candidate_fingerprint"] == second["candidate_fingerprint"]
assert first["delivery"]["access_nonce_sha256"] != second["delivery"]["access_nonce_sha256"]
PYCODE

required=(
  "$ROOT/references/owltastic-design-dna.md"
  "$ROOT/references/visual-world-brief.yaml"
  "$ROOT/references/acceptance-tests.md"
  "$ROOT/references/review-url-transport.md"
)
for path in "${required[@]}"; do
  [[ -s "$path" ]] || fail "missing or empty reference: $path"
done

printf 'PASS: best-practices-bespoke-design sanity\n'
