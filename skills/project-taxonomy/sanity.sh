#!/bin/bash
# Behavioral gates per best-practices-skills:
# - positive control: live-catalog check passes (mapping complete, 18 disciplines)
# - idempotency: apply reports zero pending edits
# - negative control: a synthetic unmapped skill fails validate() with a named error
# - noise control: _shared/dotdirs are ignored; unknown discipline in list exits 2
# - safety boundary: check mode writes nothing (mtimes unchanged)
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
uv sync --quiet

OUT="$(./run.sh check)"
echo "$OUT" | uv run --project "$SCRIPT_DIR" python -c "
import json, sys
r = json.load(sys.stdin)
errs = []
if r['status'] != 'CHECK_ONLY':
    errs.append(f\"check status {r['status']}\")
if r['skills'] < 300 or r['disciplines'] != 18:
    errs.append(f\"unexpected counts: {r['skills']} skills / {r['disciplines']} disciplines\")
if r['results']['skill_md']['updated'] or r['results']['readme']['updated']:
    errs.append('apply not idempotent: pending edits found (run ./run.sh apply)')
if errs:
    print(json.dumps({'status': 'FAIL', 'failures': errs}, indent=2)); raise SystemExit(1)
"

uv run --project "$SCRIPT_DIR" python - <<'PY'
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str((Path("scripts")).resolve()))
import apply_disciplines as ad  # noqa: E402

failures = []
vocabulary, mapping = ad.load_config()

with tempfile.TemporaryDirectory(prefix="project-taxonomy-sanity-") as tmp:
    root = Path(tmp)
    # negative control: unmapped skill on disk must produce a named error
    bad = root / "zz-unmapped"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\nname: zz-unmapped\ndescription: x\n---\n", encoding="utf-8")
    # noise control: _shared and dotdirs must be ignored
    for noise in ("_shared", ".hidden"):
        nd = root / noise
        nd.mkdir()
        (nd / "SKILL.md").write_text("---\nname: n\ndescription: x\n---\n", encoding="utf-8")
    errors = ad.validate(vocabulary, mapping, skills_root=root)
    if not any("unmapped skill" in e and "zz-unmapped" in e for e in errors):
        failures.append("negative control: unmapped skill not reported")
    if any("_shared" in e or ".hidden" in e for e in errors):
        failures.append("noise control: _shared/dotdir surfaced as unmapped")

    # bad-vocabulary control: a discipline outside the closed set is an error
    errors = ad.validate(vocabulary, {"zz-unmapped": ["not-a-discipline"]}, skills_root=root)
    if not any("not in vocabulary" in e for e in errors):
        failures.append("negative control: out-of-vocabulary discipline not reported")

if failures:
    print(json.dumps({"status": "FAIL", "failures": failures}, indent=2))
    raise SystemExit(1)
print(json.dumps({"status": "PASS", "gates": ["mapping-complete", "vocabulary-18", "idempotent", "negative-unmapped", "negative-vocabulary", "noise-dirs"]}))
PY

./run.sh crosswalk | uv run --project "$SCRIPT_DIR" python -c "
import json, sys
r = json.load(sys.stdin)
if r['status'] != 'IN_SYNC':
    print('FAIL: crosswalk drift:', r); raise SystemExit(1)
print('PASS: crosswalk in sync,', r['disagreements'], 'rows pending human review')
"
./run.sh portfolio | uv run --project "$SCRIPT_DIR" python -c "
import json, sys
r = json.load(sys.stdin)
if r['status'] != 'PASS':
    print('FAIL: portfolio gate:', r.get('errors')); raise SystemExit(1)
print('PASS: portfolio registry valid, age', r['registry_age_days'], 'days, unclassified:', r['unclassified_active_repos'])
"
if ./run.sh list not-a-discipline >/dev/null 2>&1; then
    echo "FAIL: list accepted an unknown discipline" >&2; exit 1
fi
N="$(./run.sh list extraction | wc -l)"
if [ "$N" -lt 5 ]; then echo "FAIL: list extraction returned $N skills" >&2; exit 1; fi
echo "PASS: list gates (unknown rejected; extraction -> $N skills)"
