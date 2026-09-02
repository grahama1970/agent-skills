#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
python3 - <<'PY'
from pathlib import Path
text = Path('SKILL.md').read_text(encoding='utf-8')
required = [
    'name: best-practices-chatterbox',
    'best-practices-python',
    'best-practices-skills',
    'analyze-chatterbox-emotions',
    '$memory recall',
    'bottle rocket ... a room',
    'render_chunks',
    'pause_after_ms',
    '[sniff] [sniff] ... give me a second',
    'intensity',
    'exaggeration=0.7-0.8',
    'Turbo ignores `exaggeration` and `cfg_weight`',
    '[pause:750ms]',
    './run.sh sweep-plan',
    './run.sh check-reference',
    'Streaming boundary',
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit('MISSING_REQUIRED_TEXT ' + repr(missing))
print('PASS_BEST_PRACTICES_CHATTERBOX_TEXT_CONTRACT')
PY
python3 -m pytest tests/test_chatterbox_contract_tools.py -q
./run.sh check-contract --out /tmp/best-practices-chatterbox-contract-sanity.json | grep -F 'PASS_BEST_PRACTICES_CHATTERBOX_CONTRACT'
./run.sh preprocess --text 'I *cannot* -- [SIGH] keep pretending....' | grep -F '... [sigh]'
./run.sh ssml --text '<speak>Wait <break time="800ms"/><express-as type="gasp">look out</express-as></speak>' | grep -F '[pause:800ms]'
./run.sh plan-silence --text 'I need a second. [pause:1.2s] [sniff] [sniff] ... give me a second.' --tone grief_safe | grep -F '"pause_after_ms": 1200'
./run.sh sweep-plan --text 'I cannot believe you pulled this off! ... [gasp] That was incredible.' | grep -F '"run_count": 16'
printf '%s\n' 'PASS_BEST_PRACTICES_CHATTERBOX_SANITY'
