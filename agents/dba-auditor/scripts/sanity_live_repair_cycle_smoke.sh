#!/usr/bin/env bash
set -euo pipefail

# Live smoke for the Dewey repair loop.  This intentionally runs the same
# one-cycle path cron will use, but without backup by default.  It verifies that
# the calibrated repair-cycle subprocess budget is long enough for real
# monitor-sparta health --json / health --fix runtimes.

MEMORY_REPO_ROOT="${MEMORY_REPO_ROOT:-/home/graham/workspace/experiments/memory}"
DEWEY_SESSION_ROOT="${DEWEY_SESSION_ROOT:-/mnt/storage12tb/skills/review-db/outputs/dewey-sessions}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ID="${DEWEY_RUN_ID:-dewey-smoke-$(date -u +%Y%m%dT%H%M%SZ)}"

export MEMORY_REPO_ROOT
export DEWEY_SESSION_ROOT
export DEWEY_RUN_ID="${RUN_ID}"
export DEWEY_WAIT_TIMEOUT_S="${DEWEY_WAIT_TIMEOUT_S:-300}"
export DEWEY_WORKER_POLL_S="${DEWEY_WORKER_POLL_S:-15}"
export DEWEY_EMBED_BATCH_LIMIT="${DEWEY_EMBED_BATCH_LIMIT:-${DEWEY_QRA_BATCH_LIMIT:-50}}"
# Default outer repair timeout matches R2 calibration: wait_timeout_s + 600.
export DEWEY_REPAIR_TIMEOUT_S="${DEWEY_REPAIR_TIMEOUT_S:-900}"
export DEWEY_HEALTH_JSON_TIMEOUT_S="${DEWEY_HEALTH_JSON_TIMEOUT_S:-300}"
export DEWEY_HEALTH_FIX_TIMEOUT_S="${DEWEY_HEALTH_FIX_TIMEOUT_S:-240}"
export DEWEY_STALL_LIMIT="${DEWEY_STALL_LIMIT:-8}"

OUT_JSON="${DEWEY_SESSION_ROOT}/${RUN_ID}/smoke_stdout.json"
mkdir -p "$(dirname "${OUT_JSON}")"

set +e
"${PYTHON_BIN}" "${SCRIPT_DIR}/dewey_overnight_run.py" once --wait-timeout-s "${DEWEY_WAIT_TIMEOUT_S}" --repair-timeout-s "${DEWEY_REPAIR_TIMEOUT_S}" --json > "${OUT_JSON}" 2> "${DEWEY_SESSION_ROOT}/${RUN_ID}/smoke_stderr.log"
rc=$?
set -e

"${PYTHON_BIN}" - <<'PY' "${OUT_JSON}" "${rc}"
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
rc = int(sys.argv[2])
if not path.exists() or not path.read_text(encoding='utf-8').strip():
    raise SystemExit(f"missing smoke output JSON: {path}")
data = json.loads(path.read_text(encoding='utf-8'))
run_dir = pathlib.Path(data['run_dir'])
for required in ['dewey.log', 'nightly_receipt.json', 'morning_report.md']:
    if not (run_dir / required).exists():
        raise SystemExit(f"missing {required} in {run_dir}")
log = (run_dir / 'dewey.log').read_text(encoding='utf-8')
if 'repair_cycle' not in log and data.get('stop_reason') not in {'all_green_at_baseline', 'operator_required_unfixable_only'}:
    raise SystemExit('dewey.log does not show repair_cycle execution or an accepted short-circuit')
# rc may be nonzero when health remains fail-closed; the smoke validates the path
# and receipt creation, not 29/29 product readiness.
print(json.dumps({
    'smoke_returncode': rc,
    'run_dir': str(run_dir),
    'stop_reason': data.get('stop_reason'),
    'final_health': data.get('final_health'),
    'morning_report': data.get('morning_report'),
}, sort_keys=True))
PY

exit 0
