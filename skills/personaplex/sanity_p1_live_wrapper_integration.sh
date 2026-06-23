#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/skills/personaplex/scripts:$ROOT/skills/personaplex/scripts/_p1_compat:${PYTHONPATH:-}"
python3 -m unittest discover -s skills/personaplex/tests -p 'test_p1_live_wrapper_integration.py' -v
python3 skills/personaplex/scripts/personaplex_p1_live_wrapper_probe.py \
  --fixture skills/personaplex/fixtures/p1_live_wrapper_two_turn_probe.json \
  --run-root /tmp/personaplex-p1-live-wrapper-sanity \
  --transport-mode normal \
  --json > /tmp/personaplex-p1-live-wrapper-sanity-output.json
python3 - <<'PYCHECK'
import json
from pathlib import Path
out = json.loads(Path('/tmp/personaplex-p1-live-wrapper-sanity-output.json').read_text())
assert out['ok'] is True, out
assert out['sealed_turn_keys'] == ['conversation:p1-session:000002'], out['sealed_turn_keys']
assert out['stale_rejection_count'] >= 1, out['stale_rejection_count']
assert out['release_receipts'][0]['queue_depth_at_release'] == 0, out['release_receipts']
assert out['results'][0]['status'] == 'stale_fenced', out['results']
assert out['results'][1]['status'] == 'sealed', out['results']
print('p1 live wrapper integration sanity ok')
print('final_receipt=' + out['final_receipt_path'])
PYCHECK
