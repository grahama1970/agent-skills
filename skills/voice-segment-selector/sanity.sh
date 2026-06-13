#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== voice-segment-selector sanity ==="

command -v ffmpeg >/dev/null || { echo "FAIL: ffmpeg required"; exit 1; }
command -v ffprobe >/dev/null || { echo "FAIL: ffprobe required"; exit 1; }
echo "PASS: ffmpeg/ffprobe present"

uv sync --quiet
uv run python -m pytest -q
echo "PASS: unit tests"

FIXTURE="$SCRIPT_DIR/tests/fixtures/sample.wav"
if [[ ! -f "$FIXTURE" ]]; then
  ffmpeg -y -f lavfi -i "sine=frequency=180:duration=8" -ar 16000 -ac 1 "$FIXTURE" >/dev/null 2>&1
fi

JOB="/tmp/voice-segment-selector-sanity-$$"
./run.sh prepare --input "$FIXTURE" --job-dir "$JOB" --classifier f0 --no-transcribe --min-clip-sec 3 --max-clip-sec 8
test -f "$JOB/candidates.jsonl"
test -f "$JOB/manifest.json"
./run.sh export --job-dir "$JOB" --auto-accept-top 1 --out-dir "$JOB/voice-dataset"
test -f "$JOB/voice-dataset/metadata.jsonl"
echo "PASS: prepare/export smoke"
echo "voice-segment-selector sanity passed"
