# Dewey R3 Commands

## Isolated solution sanity

Run from the unzipped solution root:

```bash
python -m py_compile memory/scripts/validation/monitor_sparta_r3_diagnostics.py
python -m pytest -q agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py
```

## Local port verification after integrating helper into monitor_sparta.py

Run from `/home/graham/workspace/experiments/memory`:

```bash
uv run python scripts/validation/monitor_sparta.py health --json | tee /tmp/dewey-r3-health-before.json

SPARTA_MONITOR_MUTATION_ENABLED=1 \
uv run python scripts/validation/monitor_sparta.py repair-cycle \
  --json \
  --wait \
  --wait-timeout-s 300 \
  --embed-batch-limit 200 | tee /tmp/dewey-r3-repair-cycle.json
```

Then assert shape:

```bash
python - <<'PY'
import json
receipt = json.load(open('/tmp/dewey-r3-repair-cycle.json'))
steps = receipt.get('steps', [])
assert any(s.get('id') == 'sparta_qdrant_embed_batch' and 'eligible_count' in s and 'changed_count' in s for s in steps)
assert any(s.get('id') == 'monitor_health_fix' and 'per_dimension_results' in s for s in steps)
assert any(s.get('id') == 'qra_coverage_operator_lane' for s in steps)
assert receipt.get('r3_diagnostics', {}).get('contract', '').startswith('Option B')
print('R3 receipt shape OK')
PY
```

## Dewey once proof after port

Run from `/home/graham/workspace/experiments/agent-skills/agents/dba-auditor`:

```bash
SPARTA_MONITOR_MUTATION_ENABLED=1 \
uv run python scripts/dewey_overnight_run.py once \
  --repair-timeout-s 900 \
  --wait-timeout-s 300 \
  --embed-batch-limit 200 \
  --session-root /tmp/dewey-r3-once
```

Expected artifacts:

```text
/tmp/dewey-r3-once/*/dewey.log
/tmp/dewey-r3-once/*/once_receipt.json
/tmp/dewey-r3-once/*/morning_report.md
```

Do not enable cron until this proof succeeds and the receipt contains R3 diagnostics.
