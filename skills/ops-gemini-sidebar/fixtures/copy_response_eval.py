#!/usr/bin/env python3
"""Copy an already-completed, operator-bound sidebar code answer through live X11.

No prompts are sent. A fresh poison value must be replaced by the selected
response. This tests clipboard delivery, not provider identity or design merit.
"""
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

from paste_only_eval import clipboard, run

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.environ['DISPLAY'] = os.environ.get('OPS_GEMINI_SIDEBAR_DISPLAY', ':0')
    coords = Path(os.environ['OPS_GEMINI_SIDEBAR_COORDS'])
    plan = json.loads(coords.read_text())
    windows = run('xdotool', 'search', '--onlyvisible', '--name', plan['window_title']).splitlines()
    if len(windows) != 1:
        raise RuntimeError('Exactly one operator-bound window required')
    marker = os.environ.get('OPS_GEMINI_SIDEBAR_RESPONSE_MARKER', 'FILE: skills/explain-project/')
    poison = 'NOT_COPIED_' + uuid4().hex
    clipboard(poison)
    out = Path(tempfile.mkdtemp(prefix='gemini-copy-response-'))
    result = out / 'answer.md'
    receipt = run(str(ROOT / 'run.sh'), 'copy-response', '--coords', str(coords),
                  '--out', str(result), '--execute', '--display', os.environ['DISPLAY'], '--json')
    (out / 'dispatch.json').write_text(receipt)
    samples = []
    deadline = time.monotonic() + 5
    while True:
        actual = run('xclip', '-selection', 'clipboard', '-o')
        samples.append({'monotonic': time.monotonic(), 'prefix': actual[:80], 'chars': len(actual)})
        if actual != poison or time.monotonic() >= deadline:
            break
        time.sleep(.2)
    (out / 'clipboard-samples.json').write_text(json.dumps(samples, indent=2))
    passed = actual != poison and actual.startswith(marker) and result.read_text() == actual
    proof = {'schema': 'ops_gemini_sidebar.copy_eval.v1', 'status': 'PASS' if passed else 'FAIL',
             'chars': len(actual), 'out': str(result), 'prefix': actual[:100],
             'proof_scope': 'Real desktop response copy/readback; operator supplies provider binding; no design acceptance claim'}
    (out / 'result.json').write_text(json.dumps(proof, indent=2))
    print(json.dumps(proof, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
