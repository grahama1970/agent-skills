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
]
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit('MISSING_REQUIRED_TEXT ' + repr(missing))
print('PASS_BEST_PRACTICES_CHATTERBOX_SANITY')
PY
