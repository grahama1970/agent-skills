#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

python3 - <<'PY'
import importlib.util
import sys
if importlib.util.find_spec('typer') is None:
    sys.stderr.write('agent-debugger sanity requires typer. Install with: python3 -m pip install typer==0.12.5\n')
    raise SystemExit(2)
PY

mkdir -p "$TMP_DIR/scripts"
cat > "$TMP_DIR/scripts/failing_target.py" <<'PY'
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--value', required=True)
args = parser.parse_args()

items = [1, 2, 3]
value = int(args.value)
payload = {'key': None}
Path('target_output.txt').write_text(f"value={value};items={len(items)};key={payload['key']}\n")
PY

target_hash_before="$(python3 - <<PY
from pathlib import Path
import hashlib
p = Path('$TMP_DIR/scripts/failing_target.py')
print(hashlib.sha256(p.read_bytes()).hexdigest())
PY
)"

pushd "$TMP_DIR" >/dev/null
bash "$SCRIPT_DIR/run.sh" init-python \
  --task sanity-case \
  --target scripts/failing_target.py \
  --target-arg=--value \
  --target-arg=7 \
  --breakpoint 'scripts/failing_target.py:11:value,len(items),payload.get("key")'

python3 - <<'PY'
from pathlib import Path
import json

manifest_path = Path('.plan-iterate/sanity-case/debug/debug_manifest.json')
harness_path = Path('.plan-iterate/sanity-case/debug/harness_sanity_case.py')
launch_path = Path('.vscode/launch.json')
commands_path = Path('.plan-iterate/sanity-case/debug/debug_commands.jsonl')
observations_path = Path('.plan-iterate/sanity-case/debug/debug_observations.jsonl')
state_path = Path('.plan-iterate/sanity-case/debug/debug_session_state.json')

required = [manifest_path, harness_path, launch_path, commands_path, observations_path, state_path]
missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit(f'missing generated files: {missing}')

manifest = json.loads(manifest_path.read_text())
assert manifest['schema'] == 'agent_debugger_manifest.v1'
assert manifest['language'] == 'python'
assert manifest['task'] == 'sanity-case'
assert manifest['launch_config_name'] == 'Agent Debugger: sanity-case'
assert manifest['target_args'] == ['--value', '7']
assert manifest['breakpoints'][0]['file'] == 'scripts/failing_target.py'
assert manifest['breakpoints'][0]['line'] == 11
assert manifest['breakpoints'][0]['expressions'] == ['value', 'len(items)', 'payload.get("key")']
assert manifest['commands_path'].endswith('debug_commands.jsonl')
assert manifest['observations_path'].endswith('debug_observations.jsonl')
assert manifest['session_state_path'].endswith('debug_session_state.json')

launch = json.loads(launch_path.read_text())
config = next(item for item in launch['configurations'] if item['name'] == 'Agent Debugger: sanity-case')
assert config['type'] == 'debugpy'
assert config['request'] == 'launch'
assert config['program'].endswith('.plan-iterate/sanity-case/debug/harness_sanity_case.py')
assert config['justMyCode'] is False

harness = harness_path.read_text()
assert 'runpy.run_path' in harness
assert 'scripts/failing_target.py' in harness
PY

python3 .plan-iterate/sanity-case/debug/harness_sanity_case.py

grep -q 'value=7;items=3;key=None' target_output.txt
popd >/dev/null

target_hash_after="$(python3 - <<PY
from pathlib import Path
import hashlib
p = Path('$TMP_DIR/scripts/failing_target.py')
print(hashlib.sha256(p.read_bytes()).hexdigest())
PY
)"

if [[ "$target_hash_before" != "$target_hash_after" ]]; then
  echo "FAIL: target script was modified by generator or harness" >&2
  exit 1
fi

if [[ -d "$SCRIPT_DIR/models" || -d "$SCRIPT_DIR/outputs" || -d "$SCRIPT_DIR/logs" || -d "$SCRIPT_DIR/data" ]]; then
  echo "FAIL: heavy artifact directory exists inside skill folder" >&2
  exit 1
fi

echo "PASS agent-debugger sanity"
