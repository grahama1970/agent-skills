#!/usr/bin/env python3
"""Compare Surf's live desktop index with the independent X11 root property."""
import json
import os
from pathlib import Path
import subprocess
import sys


def run(*args):
    return subprocess.check_output(args, text=True, timeout=30)


if __name__ == '__main__':
    manager = dict(line.split('=', 1) for line in run('systemctl', '--user', 'show-environment').splitlines() if '=' in line)
    for key in ('DISPLAY', 'XAUTHORITY'):
        if key in manager:
            os.environ.setdefault(key, manager[key])
    def desktop():
        return int(run('xprop', '-root', '_NET_CURRENT_DESKTOP').rsplit('=', 1)[1].strip())
    before = desktop()
    negative = '--without-display' in sys.argv
    if negative:
        os.environ['DISPLAY'] = ''
        os.environ.pop('XAUTHORITY', None)
    skill = Path(__file__).resolve().parents[1]
    observed = json.loads(run(str(skill / 'run.sh'), 'kde.spaces'))
    after = None if negative else desktop()
    result = {'live': True, 'missing_display_injected': negative, 'expected_before': before, 'expected_after': after,
              'observed': observed['current_desktop_index'], 'inventory': observed}
    valid = result['observed'] is None if negative else before == after == result['observed']
    result['status'] = 'PASS' if valid else 'FAIL'
    Path('/tmp/surf-kde-desktop-index.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'inventory'}))
    raise SystemExit(0 if result['status'] == 'PASS' else 1)
