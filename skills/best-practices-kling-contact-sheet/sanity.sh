#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 -m py_compile \
  "$ROOT/scripts/create_asset_pack.py" \
  "$ROOT/scripts/validate_asset_pack.py"
find "$ROOT/scripts" -type d -name __pycache__ -prune -exec rm -rf {} +

python3 "$ROOT/scripts/create_asset_pack.py" \
  --root "$WORK" \
  --type character \
  --name Maya_Ren \
  --version 1 \
  --make-placeholders > "$WORK/create.out"

PACK="$WORK/CHAR_Maya_Ren_v01"
test -f "$PACK/manifest.json"
test -f "$PACK/description.txt"

python3 "$ROOT/scripts/validate_asset_pack.py" "$PACK" > "$WORK/validate_positive.out"
grep -q "Reference count is 4" "$WORK/validate_positive.out"
grep -q "File is empty placeholder" "$WORK/validate_positive.out"

NEG="$WORK/NEG_Bad_v01"
mkdir -p "$NEG/references"
cat > "$NEG/manifest.json" <<'JSON'
{
  "asset_name": "Bad",
  "asset_type": "character",
  "version": "v01",
  "references": [
    {
      "file": "references/only_one.png",
      "role": "main",
      "purpose": "negative control"
    }
  ],
  "description": {
    "core_identity": "",
    "visual_details": "",
    "do_not_change": [],
    "ignore": []
  }
}
JSON
touch "$NEG/references/only_one.png"

if python3 "$ROOT/scripts/validate_asset_pack.py" "$NEG" > "$WORK/validate_negative.out"; then
  echo "negative control unexpectedly passed" >&2
  exit 1
fi
grep -q "reference count should be 2-4" "$WORK/validate_negative.out"

FORBIDDEN_PATTERN="arg""parse|from arango|ArangoClient|/_api/cursor|sys\\.path\\.insert"
if rg -n "$FORBIDDEN_PATTERN" "$ROOT/scripts" "$ROOT/SKILL.md"; then
  echo "forbidden implementation pattern found" >&2
  exit 1
fi

jq empty "$ROOT/schemas/asset_pack_manifest.schema.json"
jq empty "$ROOT/schemas/asset_pack_manifest.example.json"

echo "best-practices-kling-contact-sheet sanity passed"
