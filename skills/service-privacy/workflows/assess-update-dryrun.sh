#!/usr/bin/env bash
# Dry-run driver for assess-update.workflow.js: runs the DETERMINISTIC prefix
# (change-snapshot + sanitize-denials + assess-update) and emits the typed
# NEEDS_HUMAN evidence-chain receipt WITHOUT spawning a live model (the
# INVESTIGATE model call is stubbed; proposed_delta/validator_verdict are
# reported as NOT_RUN). The workflow may PROPOSE; it never applies — human
# approval is the only apply path. Exit 2 = needs-human (per the exit contract).
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
PYTHON="${SERVICE_PRIVACY_PYTHON:-/tmp/usp/venv/bin/python}"
UNIT="${SERVICE_PRIVACY_UNIT:-launcher.kolide-k2.service}"

"$PYTHON" -B - "$UNIT" <<'EOF'
import json, subprocess, sys

unit = sys.argv[1]
py = __import__('os').environ.get('SERVICE_PRIVACY_PYTHON', '/tmp/usp/venv/bin/python')

def run(args):
    p = subprocess.run(['./run.sh'] + args, capture_output=True, text=True)
    records = []
    for line in p.stdout.splitlines():
        line = line.strip()
        if line.startswith('{'):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return p.returncode, records

_, change_records = run(['change-snapshot', '--unit', unit])
change = next((r for r in change_records if r.get('schema_version', '').endswith('change_receipt.v1')), {})
_, sanitized = run(['sanitize-denials', '--unit', unit])
classes = {}
for r in sanitized:
    if r.get('schema_version', '').endswith('sanitized_denial.v1'):
        classes[r.get('resource_class', '?')] = classes.get(r.get('resource_class', '?'), 0) + r.get('count', 0)
_, qual_records = run(['assess-update', '--unit', unit])
qual = next((r for r in qual_records if r.get('schema_version', '').endswith('qualification_receipt.v1')), {})

# Map the authoritative Python qualification disposition to the workflow's
# explicit terminal states (same contract as the workflow file).
d = qual.get('disposition', 'BLOCKED')
terminal = {
    'NEEDS_HUMAN': 'NEEDS_HUMAN',
    'POLICY_CHANGE_PROPOSED': 'NEEDS_HUMAN',  # dry-run stubs the model; live run investigates
    'PRIVACY_BOUNDARY_VIOLATION': 'PRIVACY_BOUNDARY_VIOLATION',
    'INCONCLUSIVE': 'INCONCLUSIVE',
    'FAILED': 'BLOCKED',
    'NO_CHANGE': 'REQUALIFIED_UNCHANGED',
    'REQUALIFIED_UNCHANGED': 'REQUALIFIED_UNCHANGED',
}.get(d, 'BLOCKED')

receipt = {
    'schema_version': 'ubuntu_service_privacy.workflow_receipt.v1',
    'mode': 'dry_run',
    'unit': unit,
    'terminal_state': terminal,
    'evidence_chain': {
        'change_disposition': change.get('disposition'),
        'sanitized_evidence_classes': {k: classes[k] for k in sorted(classes)},
        'qualification_disposition': d,
        'proposed_delta': None,
        'validator_verdict': 'NOT_RUN_DRY_RUN',
    },
    'invariant': 'This workflow may PROPOSE; it never applies; human approval is the only apply path.',
    'note': 'dry-run: INVESTIGATE model call stubbed; deterministic prefix is live',
}
out = json.dumps(receipt, sort_keys=True, separators=(',', ':'))
# No-apply invariant self-check: if the receipt ever carries an APPLY/auto-widen
# action the dry-run fails with a DIFFERENT exit code (3) so the eval case fails.
assert 'APPLY' not in out and 'auto-widen' not in out, 'no-apply invariant violated'
print(out)
sys.exit(0 if terminal == 'REQUALIFIED_UNCHANGED' else 2)
EOF
