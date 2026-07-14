#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d /tmp/artifact-reader-sanity.XXXXXX)"
SOURCE="$TMP_DIR/source.md"
OUT="$TMP_DIR/reader"
RECEIPT="$OUT/artifact-reader-server-receipt.json"

cleanup() {
  if [[ -f "$RECEIPT" ]]; then
    "$SCRIPT_DIR/run.sh" stop "$RECEIPT" >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

printf '# Reader proof\n\nThis is a real local artifact.\n' > "$SOURCE"

render_json="$($SCRIPT_DIR/run.sh render "$SOURCE" --out "$OUT" --title "Reader proof")"
python3 - "$render_json" "$OUT" <<'PY'
import hashlib
import json
import pathlib
import sys

result = json.loads(sys.argv[1])
out = pathlib.Path(sys.argv[2])
manifest = json.loads((out / "artifact-reader-manifest.json").read_text())
assert result["ok"] is True
assert manifest["schema"] == "artifact_reader.manifest.v1"
assert manifest["controls"] == {"copy": True, "download": True}
expected = "sha256:" + hashlib.sha256((out / "artifact.md").read_bytes()).hexdigest()
assert manifest["source"]["sha256"] == expected
reader = (out / "index.html").read_text()
assert "id=\"copy\"" in reader
assert 'document.execCommand("copy")' in reader
PY

if "$SCRIPT_DIR/run.sh" render "$TMP_DIR/missing.md" --out "$TMP_DIR/missing-out" >/dev/null 2>&1; then
  echo "FAIL: missing source was accepted" >&2
  exit 1
fi

ln -s "$SOURCE" "$TMP_DIR/source-link.md"
if "$SCRIPT_DIR/run.sh" render "$TMP_DIR/source-link.md" --out "$TMP_DIR/link-out" >/dev/null 2>&1; then
  echo "FAIL: source symlink was accepted" >&2
  exit 1
fi

start_json="$($SCRIPT_DIR/run.sh start "$OUT")"
url="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["url"])' "$start_json")"
port="$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["port"])' "$start_json")"

test "$port" -gt 0
curl --fail --silent --show-error "$url" | grep -q 'Reader proof'
curl --fail --silent --show-error "${url}artifact.md" | grep -q 'real local artifact'

python3 - "$RECEIPT" <<'PY'
import json
import pathlib
import sys

receipt = json.loads(pathlib.Path(sys.argv[1]).read_text())
assert receipt["schema"] == "artifact_reader.server_receipt.v1"
assert receipt["mocked"] is False
assert receipt["live"] is True
assert receipt["port"] > 0
assert receipt["ops_workstation"]["default_route_interface"]
assert receipt["ops_workstation"]["lan_ipv4"]
PY

"$SCRIPT_DIR/run.sh" status "$RECEIPT" >/dev/null
"$SCRIPT_DIR/run.sh" stop "$RECEIPT" >/dev/null
if "$SCRIPT_DIR/run.sh" status "$RECEIPT" >/dev/null 2>&1; then
  echo "FAIL: stopped server still reports alive" >&2
  exit 1
fi

echo "PASS: artifact-reader live render, bounded serving, lifecycle, and negative controls"
