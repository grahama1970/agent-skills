#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
./run.sh validate fixtures/sample.explainers.jsonl >/tmp/explain-project-sanity.json
./run.sh ask fixtures/sample.explainers.jsonl --question 'What happens if a worker crashes before success?' | grep -q publish.report_last
./run.sh ask fixtures/sample.explainers.jsonl --question 'unrelated calendar webhook oauth' | grep -q '"status": "NO_MATCH"'
./run.sh cockpit-proof fixtures/sample.explainers.jsonl --question 'A worker crashes before success; what prevents incomplete release?' >/tmp/explain-project-cockpit-proof.json
python3 - <<'PY'
import json
p=json.load(open('/tmp/explain-project-cockpit-proof.json'))
assert p['status']=='PASS'
assert p['assertions']['projection_revisions_equal']
assert p['assertions']['debugger_execution_count_zero']
assert p['assertions']['excalidraw_mutation_count_zero']
print('SANITY PASS')
PY
