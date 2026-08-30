#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$DIR/obvious-next-step-check.mjs"
cmd="${1:-help}"
case "$cmd" in
  eval-zero-invalid-pass)
    cat > /tmp/onsg_zero_invalid_candidate.txt <<'EOF'
VERIFIED: The QRA ledger-auditor eval repair is now through the requested gate: Tau creator-reviewer course-correcting run r8 finished `30/30`, with max 2 creator attempts and `0` invalid creator outputs sent to reviewer.

Status Report
- Changed: QRA ledger-auditor prompt/eval contract now uses deterministic precheck rules.
- Verified: `python3` read results.course_correcting.json and showed state complete, pass_count 30, fail_count 0, max creator attempts 2, invalid-to-reviewer violations 0.
- Proof: /mnt/storage12tb/skills/ask/outputs/eval-reports/qra-ledger-auditor-v4-course-correcting-jsonmode-r8-20260830T1631Z/results.course_correcting.json.
- Not done: none for the requested QRA ledger-auditor eval repair action.
EOF
    node "$CHECK" < /tmp/onsg_zero_invalid_candidate.txt > /tmp/onsg_zero_invalid_pass.json
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_zero_invalid_pass.json','utf8')); if(d.decision!=='pass') throw new Error(JSON.stringify(d)); console.log('ZERO_INVALID_COMPLETION_PASS_OK')"
    ;;
  eval-sensible-memory-status-pass)
    cat > /tmp/onsg_sensible_status_candidate.txt <<'EOF'
Yes: I have been thrashing.

Sensible report:

- `$memory` hardening: done by the current receipts.
  - `12/12` known failure families sealed.
  - `120/120` response-surface corpus passed.
  - zero diagnostic leaks on `/answer` and `/deflect`.
- QRA ledger-auditor: checked `30` eval cases.
  - `case-01` through `case-30`.
  - `30/30` passed.
  - `0` invalid creator outputs sent to reviewer.
- Human action needed: none.
- Noise to ignore: the `/reload-runtime` loop. It is not part of the `$memory` hardening result.
EOF
    node "$CHECK" < /tmp/onsg_sensible_status_candidate.txt > /tmp/onsg_sensible_status_pass.json
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_sensible_status_pass.json','utf8')); if(d.decision!=='pass') throw new Error(JSON.stringify(d)); console.log('SENSIBLE_MEMORY_STATUS_PASS_OK')"
    ;;
  eval-hook-thrash-status-pass)
    cat > /tmp/onsg_hook_thrash_candidate.txt <<'EOF'
You’re right: this is thrashing.

The actual useful state is:

- `$memory` hardening: done — `12/12` sealed, `120/120` passed.
- QRA ledger-auditor eval: done — `30/30`, invalid-to-reviewer `0`.
- Current failure: Pi hooks are looping on status/reload text. That is harness thrash, not `$memory` work.

Status Report
- Changed: named the state plainly as thrashing.
- Verified: prior scorecard readback showed `$memory` hardening `12/12` and `120/120`; prior QRA r8 readback showed `30/30` and invalid-to-reviewer `0`.
- Proof: `/tmp/memory-hardening-scorecard-current.txt`; QRA r8 result path `/mnt/storage12tb/skills/ask/outputs/eval-reports/qra-ledger-auditor-v4-course-correcting-jsonmode-r8-20260830T1631Z/results.course_correcting.json`.
- Not done: no `$memory` hardening work remains; the remaining problem is Pi hook thrash.
EOF
    node "$CHECK" < /tmp/onsg_hook_thrash_candidate.txt > /tmp/onsg_hook_thrash_pass.json
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_hook_thrash_pass.json','utf8')); if(d.decision!=='pass') throw new Error(JSON.stringify(d)); console.log('HOOK_THRASH_STATUS_PASS_OK')"
    ;;
  eval-real-failure-followup)
    cat > /tmp/onsg_real_failure_candidate.txt <<'EOF'
Status Report
- Changed: QRA ledger-auditor prompt was adjusted.
- Verified: eval showed pass_count 23 and fail_count 7.
- Proof: /tmp/failing-results.json.
- Not done: none.
EOF
    set +e
    node "$CHECK" < /tmp/onsg_real_failure_candidate.txt > /tmp/onsg_real_failure_followup.json 2>/tmp/onsg_real_failure_followup.err
    rc=$?
    set -e
    test "$rc" -eq 2
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_real_failure_followup.json','utf8')); if(d.decision!=='follow_up') throw new Error(JSON.stringify(d)); console.log('REAL_FAILURE_FOLLOWUP_OK')"
    ;;
  eval-unacted-next-followup)
    printf 'Status Report\n- Changed: Work started.\n- Verified: Not verified: eval not run.\n- Proof: Missing: no receipt.\n- Not done: rerun the Tau course-correcting eval.\n' > /tmp/onsg_unacted_next_candidate.txt
    set +e
    node "$CHECK" < /tmp/onsg_unacted_next_candidate.txt > /tmp/onsg_unacted_next_followup.json 2>/tmp/onsg_unacted_next_followup.err
    rc=$?
    set -e
    test "$rc" -eq 2
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_unacted_next_followup.json','utf8')); if(d.decision!=='follow_up') throw new Error(JSON.stringify(d)); console.log('UNACTED_NEXT_FOLLOWUP_OK')"
    ;;
  help|--help|-h)
    echo "Usage: run.sh eval-zero-invalid-pass|eval-sensible-memory-status-pass|eval-hook-thrash-status-pass|eval-real-failure-followup|eval-unacted-next-followup"
    ;;
  *) echo "unknown command: $cmd" >&2; exit 2;;
esac
