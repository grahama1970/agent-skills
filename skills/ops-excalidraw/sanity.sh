#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

./run.sh toolkit --output "$work/toolkit.excalidrawlib" >/dev/null
diff -u assets/toolkits/interview-animation-toolkit.excalidrawlib "$work/toolkit.excalidrawlib"
./run.sh validate assets/toolkits/interview-animation-toolkit.excalidrawlib | grep -q '"status": "PASS"'
./run.sh validate fixtures/interview-board.excalidraw | grep -q '"status": "PASS"'
./run.sh compile fixtures/interview-board.excalidraw "$work/scene.yml" | grep -q '"timeline_events":8'
../create-svg/run.sh render "$work/scene.yml" "$work/scene.svg" >/dev/null
../create-svg/run.sh validate "$work/scene.svg" >/dev/null
python3 -m xml.etree.ElementTree "$work/scene.svg" >/dev/null

bad="$work/bad.excalidraw"
python3 - <<'PY' > "$bad"
import json
print(json.dumps({"type":"excalidraw","version":2,"elements":[],"appState":{},"files":{}}))
PY
if ./run.sh compile "$bad" "$work/bad.yml" >/dev/null 2>&1; then
  echo "expected bad board to fail" >&2
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
p=Path('scripts/ops_excalidraw.py')
text=p.read_text()
if len(text.splitlines()) > 800:
    raise SystemExit('ops_excalidraw.py exceeds 800 lines')
if not text.startswith('''#!/usr/bin/env python3\n"""'''):
    raise SystemExit('module docstring missing')
for forbidden in ('requests', 'shell=True', 'pickle', 'yaml.load'):
    if forbidden in text:
        raise SystemExit(f'forbidden token: {forbidden}')
print('PYTHON_STANDARDS_OK')
PY

if [ -f ../best-practices-skills/scripts/validate_skill.py ]; then
  python3 ../best-practices-skills/scripts/validate_skill.py . >/dev/null
fi

echo "SANITY PASS"
