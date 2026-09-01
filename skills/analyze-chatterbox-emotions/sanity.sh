#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python3 -m pytest tests -q
fixture="/tmp/analyze-chatterbox-emotions-fixture.wav"
out="/tmp/analyze-chatterbox-emotions-sanity.json"
report="/tmp/analyze-chatterbox-emotions-sanity.md"
./run.sh fixture-wav --out "$fixture" >/dev/null
./run.sh analyze --audio "$fixture" --expected-text "hello tender voice" --transcript "hello tender voice" --target-label tender --out "$out" --report "$report" >/dev/null
python3 - <<'PY'
import json, pathlib
out = pathlib.Path('/tmp/analyze-chatterbox-emotions-sanity.json')
report = pathlib.Path('/tmp/analyze-chatterbox-emotions-sanity.md')
payload = json.loads(out.read_text())
assert payload['schema'] == 'analyze_chatterbox_emotions.voice_eval.v1'
assert payload['mocked'] is False
assert payload['prosody']['duration_sec'] > 1.0
assert report.is_file() and 'Pause evidence' in report.read_text()
print('PASS_ANALYZE_CHATTERBOX_EMOTIONS_SANITY')
PY
