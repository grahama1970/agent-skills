#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d /tmp/extract-audiobook-sanity.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

"$SCRIPT_DIR/run.sh" doctor --json > "$TMP_DIR/doctor.json"
python - "$TMP_DIR/doctor.json" <<'PY'
import json
import sys
report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["ffprobe"], report
assert report["ffmpeg"], report
print(json.dumps({"doctor_ok": report["ok"], "faster_whisper": report["faster_whisper"]}))
PY

PYTHONPATH="$SCRIPT_DIR" uv run --project "$SCRIPT_DIR" python -m unittest discover -s "$SCRIPT_DIR/tests" -v
