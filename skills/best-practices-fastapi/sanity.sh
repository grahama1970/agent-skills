#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${TMPDIR:-/tmp}/best-practices-fastapi-flask-app.py"

echo "=== [best-practices-fastapi] Sanity Check ==="

echo -n "Check 1 - required files: "
for f in SKILL.md run.sh scripts/convert_to_flask.py fixtures/route_manifest.json fixtures/invalid_route_manifest.json fixtures/agentic_eval.json; do
  test -f "$SCRIPT_DIR/$f"
done
echo "PASS"

echo -n "Check 2 - skill contract text: "
grep -q "framework-neutral" "$SCRIPT_DIR/SKILL.md"
grep -q 'Use `$memory` as the default persistence boundary' "$SCRIPT_DIR/SKILL.md"
grep -q "Terraform stays outside the app" "$SCRIPT_DIR/SKILL.md"
grep -q "Flask fallback" "$SCRIPT_DIR/SKILL.md"
grep -q "Swagger/OpenAPI as a demo harness" "$SCRIPT_DIR/SKILL.md"
grep -q "Body(..., openapi_examples" "$SCRIPT_DIR/SKILL.md"
grep -q "Authorize" "$SCRIPT_DIR/SKILL.md"
grep -q "data-qid" "$SCRIPT_DIR/SKILL.md"
grep -q "externalDocs" "$SCRIPT_DIR/SKILL.md"
grep -q "x-code-location" "$SCRIPT_DIR/SKILL.md"
grep -q "x-artifact-location" "$SCRIPT_DIR/SKILL.md"
grep -q "Uvicorn reload restarts the server" "$SCRIPT_DIR/SKILL.md"
echo "PASS"

echo -n "Check 3 - converter positive: "
"$SCRIPT_DIR/run.sh" convert-to-flask "$SCRIPT_DIR/fixtures/route_manifest.json" --out "$OUT" >/tmp/best-practices-fastapi-convert.out
python3 -m py_compile "$OUT"
grep -q "@app.route('/eval/batch'" "$OUT"
grep -q "contracts.EvalBatchRequest.model_validate" "$OUT"
echo "PASS"

echo -n "Check 4 - converter rejects invalid manifest: "
if "$SCRIPT_DIR/run.sh" convert-to-flask "$SCRIPT_DIR/fixtures/invalid_route_manifest.json" --out "$OUT.invalid" >/tmp/best-practices-fastapi-invalid.out 2>/tmp/best-practices-fastapi-invalid.err; then
  echo "FAIL"
  exit 1
fi
grep -q "manifest validation failed" /tmp/best-practices-fastapi-invalid.err
echo "PASS"

echo "Result: PASS"
