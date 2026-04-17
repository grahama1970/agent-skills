#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Export NIST OSCAL JSON from ArangoDB compliance evidence
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'

usage() {
  cat <<EOF
Usage:
  $0 export --framework <NIST-800-171|CMMC-L2> [--dry-run]
  $0 validate <file.json>

Subcommands:
  export    Export OSCAL assessment-results JSON from ArangoDB
  validate  Check a JSON file for required OSCAL fields
EOF
  exit 1
}

if [ $# -lt 1 ]; then
  usage
fi

SUBCMD="$1"
shift

case "$SUBCMD" in
  export)
    FRAMEWORK=""
    DRY_RUN=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --framework) FRAMEWORK="$2"; shift 2 ;;
        --dry-run)   DRY_RUN="1"; shift ;;
        *) echo "Unknown option: $1" >&2; usage ;;
      esac
    done
    if [ -z "$FRAMEWORK" ]; then
      echo "Error: --framework is required" >&2
      usage
    fi
    if [ "$FRAMEWORK" != "NIST-800-171" ] && [ "$FRAMEWORK" != "CMMC-L2" ]; then
      echo "Error: --framework must be NIST-800-171 or CMMC-L2" >&2
      exit 1
    fi
    python3 -c "
import json, sys, uuid
from datetime import datetime, timezone

framework = '$FRAMEWORK'
dry_run = bool('$DRY_RUN')

def build_oscal_shell(title_suffix, controls, qra_evidence, lessons_evidence):
    now = datetime.now(timezone.utc).isoformat()
    results = []
    for ctrl in controls:
        ctrl_id = ctrl.get('control_id', ctrl.get('_key', 'unknown'))
        ctrl_title = ctrl.get('title', ctrl.get('name', ctrl_id))
        findings = []
        for qra in qra_evidence:
            if qra.get('control_id') == ctrl_id or qra.get('control') == ctrl_id:
                findings.append({
                    'uuid': str(uuid.uuid4()),
                    'title': f'QRA: {qra.get(\"question\", qra.get(\"title\", \"untitled\"))}',
                    'description': qra.get('answer', qra.get('response', '')),
                    'target': {
                        'type': 'objective-id',
                        'target-id': ctrl_id,
                        'status': {'state': qra.get('status', 'satisfied')}
                    }
                })
        for lesson in lessons_evidence:
            if lesson.get('control_id') == ctrl_id or lesson.get('control') == ctrl_id:
                findings.append({
                    'uuid': str(uuid.uuid4()),
                    'title': f'Lesson: {lesson.get(\"title\", \"untitled\")}',
                    'description': lesson.get('description', lesson.get('body', '')),
                    'target': {
                        'type': 'objective-id',
                        'target-id': ctrl_id,
                        'status': {'state': 'informational'}
                    }
                })
        results.append({
            'uuid': str(uuid.uuid4()),
            'title': f'{ctrl_id} - {ctrl_title}',
            'description': ctrl.get('description', ''),
            'start': now,
            'findings': findings
        })
    return {
        'assessment-results': {
            'uuid': str(uuid.uuid4()),
            'metadata': {
                'title': f'Embry OS Compliance Export - {title_suffix}',
                'last-modified': now,
                'version': '1.0.0',
                'oscal-version': '1.1.2'
            },
            'results': results
        }
    }

if dry_run:
    sample_controls = [
        {'control_id': 'AC-1', 'title': 'Access Control Policy', 'description': 'Establish access control policy and procedures'},
        {'control_id': 'AC-2', 'title': 'Account Management', 'description': 'Manage system accounts'},
        {'control_id': 'SI-2', 'title': 'Flaw Remediation', 'description': 'Identify, report, and correct system flaws'},
    ]
    sample_qra = [
        {'control_id': 'AC-1', 'question': 'Is access control policy documented?', 'answer': 'Yes, documented in EMBRY-POL-001', 'status': 'satisfied'},
        {'control_id': 'AC-2', 'question': 'Are accounts reviewed quarterly?', 'answer': 'Automated review via state-daemon', 'status': 'satisfied'},
        {'control_id': 'SI-2', 'question': 'Is there a patching cadence?', 'answer': 'OSTree atomic updates on 14-day cycle', 'status': 'satisfied'},
    ]
    sample_lessons = [
        {'control_id': 'AC-1', 'title': 'KDE Wallet migration', 'description': 'Migrated 30 secrets from .env to KDE Wallet for ITAR compliance'},
    ]
    doc = build_oscal_shell(framework, sample_controls, sample_qra, sample_lessons)
    print(json.dumps(doc, indent=2))
    sys.exit(0)

# --- Live mode: query via /memory (no direct ArangoDB access) ---
import subprocess
from pathlib import Path

MEMORY_RUN = str(Path(__file__).resolve().parent.parent / 'memory' / 'run.sh')

def memory_sample(collection, limit=1000):
    cmd = [MEMORY_RUN, 'sample', '--collection', collection, '--limit', str(limit)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f'FATAL: /memory unavailable: {result.stderr}', file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout).get('items', [])

controls = memory_sample('sparta_controls')
qra = memory_sample('sparta_qra')
lessons = memory_sample('lessons')

if not controls:
    print('Warning: no controls found in sparta_controls', file=sys.stderr)

doc = build_oscal_shell(framework, controls, qra, lessons)
print(json.dumps(doc, indent=2))
"
    ;;

  validate)
    if [ $# -lt 1 ]; then
      echo "Error: validate requires a file path" >&2
      usage
    fi
    FILE="$1"
    if [ ! -f "$FILE" ]; then
      echo "Error: file not found: $FILE" >&2
      exit 1
    fi
    python3 -c "
import json, sys

path = '$FILE'
try:
    with open(path) as f:
        doc = json.load(f)
except json.JSONDecodeError as e:
    print(f'FAIL: invalid JSON - {e}', file=sys.stderr)
    sys.exit(1)

ar = doc.get('assessment-results')
if ar is None:
    print('FAIL: missing top-level \"assessment-results\" key', file=sys.stderr)
    sys.exit(1)

errors = []
if 'uuid' not in ar:
    errors.append('missing assessment-results.uuid')
if 'metadata' not in ar:
    errors.append('missing assessment-results.metadata')
else:
    meta = ar['metadata']
    for field in ('title', 'last-modified', 'version', 'oscal-version'):
        if field not in meta:
            errors.append(f'missing metadata.{field}')
if 'results' not in ar:
    errors.append('missing assessment-results.results')
elif not isinstance(ar['results'], list):
    errors.append('assessment-results.results must be an array')

if errors:
    for e in errors:
        print(f'FAIL: {e}', file=sys.stderr)
    sys.exit(1)

result_count = len(ar['results'])
finding_count = sum(len(r.get('findings', [])) for r in ar['results'])
print(f'PASS: valid OSCAL assessment-results ({result_count} results, {finding_count} findings)')
"
    ;;

  *)
    echo "Unknown subcommand: $SUBCMD" >&2
    usage
    ;;
esac
