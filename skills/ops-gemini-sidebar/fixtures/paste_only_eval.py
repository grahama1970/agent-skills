#!/usr/bin/env python3
"""Live desktop draft check on an operator-calibrated, empty sidebar composer.

No provider call is requested. Uses real X11 and a poisoned clipboard before
readback so stale outbound clipboard contents cannot manufacture success.
Provider identity must be established by the caller's current window capture.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'{args[0]} exit {result.returncode}: {result.stdout}\n{result.stderr}')
    return result.stdout


def clipboard(text):
    proc = subprocess.Popen(['xclip', '-selection', 'clipboard', '-i'], stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    proc.stdin.write(text)
    proc.stdin.close()
    time.sleep(.2)


def main():
    coords = Path(os.environ['OPS_GEMINI_SIDEBAR_COORDS'])
    plan = json.loads(coords.read_text())
    os.environ['DISPLAY'] = os.environ.get('OPS_GEMINI_SIDEBAR_DISPLAY', ':0')
    windows = run('xdotool', 'search', '--onlyvisible', '--name', plan['window_title']).splitlines()
    if len(windows) != 1:
        raise RuntimeError('Exactly one calibrated Chrome window required')
    run('xdotool', 'windowactivate', '--sync', windows[0])
    run('xdotool', 'mousemove', str(plan['composer']['x']), str(plan['composer']['y']), 'click', '1')
    poison = 'UNSELECTED-' + uuid4().hex
    clipboard(poison)
    run('xdotool', 'key', 'ctrl+a', 'ctrl+c')
    time.sleep(.2)
    if run('xclip', '-selection', 'clipboard', '-o') != poison:
        raise RuntimeError('Composer is not empty; refusing to overwrite an existing draft')
    out = Path(tempfile.mkdtemp(prefix='gemini-paste-only-'))
    prompt = out / 'prompt.txt'
    marker = 'DRAFT_ONLY_' + uuid4().hex
    prompt.write_text(marker)
    dispatch = run(str(ROOT / 'run.sh'), 'submit', '--prompt-file', str(prompt),
                   '--coords', str(coords), '--paste-only', '--execute', '--display', os.environ['DISPLAY'], '--json')
    (out / 'dispatch.json').write_text(dispatch)
    time.sleep(1)
    run('import', '-window', windows[0], str(out / 'draft.png'))
    clipboard(poison)
    run('xdotool', 'key', 'ctrl+a', 'ctrl+c')
    time.sleep(.2)
    readback = run('xclip', '-selection', 'clipboard', '-o')
    (out / 'draft-readback.txt').write_text(readback)
    passed = readback == marker
    if passed:
        run('xdotool', 'key', 'BackSpace')
    receipt = {'schema': 'ops_gemini_sidebar.paste_only_eval.v1',
               'status': 'PASS' if passed else 'FAIL', 'marker': marker,
               'draft_readback': readback, 'output_dir': str(out),
               'proof_scope': 'Live desktop draft retention, not Gemini delivery/response or design acceptance'}
    (out / 'result.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
