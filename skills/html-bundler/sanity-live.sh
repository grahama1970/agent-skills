#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ "${SURF_LIVE:-0}" != "1" ]]; then
  echo "Set SURF_LIVE=1 to run live surf capture (opens Chrome via skills/surf)." >&2
  exit 0
fi

out="/tmp/html-bundler-live-sanity.zip"
root="/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict/pipeline_review_8892"
url="http://127.0.0.1:8892/index.html"
rm -f "$out"

if [[ ! -f "$root/index.html" ]]; then
  echo "live fixture missing at $root/index.html; falling back to minimal fixture html serve path not used" >&2
  fixture_html="$(pwd)/tests/fixtures/minimal/index.html"
  zip_path="$(./run.sh capture --html "$fixture_html" --out "$out")"
else
  zip_path="$(./run.sh capture --url "$url" --root "$root" --source-entry index.html --out "$out")"
fi
[[ "$zip_path" == "$out" ]]
[[ -f "$out" ]]

python3 - <<'PY'
import zipfile
from pathlib import Path
out = Path("/tmp/html-bundler-live-sanity.zip")
with zipfile.ZipFile(out) as zf:
    names = set(zf.namelist())
for required in ("manifest.json", "README_FOR_CHATGPT.md", "BUNDLE_ASSESSMENT.md"):
    assert required in names, required
assert any(n.startswith("captures/") and n.endswith(".png") for n in names), names
assert any(n.startswith("source/") for n in names) or "source/" in zf.read("BUNDLE_ASSESSMENT.md").decode()
manifest = json.loads(zf.read("manifest.json"))
assert "stdout_preview" not in json.dumps(manifest)
assert any("-scroll-" in n for n in names), names
print("live zip contract ok")
PY

echo "html-bundler sanity-live passed: $out"
