#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$DIR/obvious-next-step-check.mjs"
cmd="${1:-help}"
case "$cmd" in
  eval-zero-invalid-pass)
    cat > /tmp/onsg_zero_invalid_candidate.txt <<'EOF'
VERIFIED: The QRA ledger-auditor eval repair is now through the requested gate: Tau creator-reviewer course-correcting run r8 finished `30/30`, with max 2 creator attempts and zero invalid creator outputs sent to reviewer.

Status Report
- Changed: QRA ledger-auditor prompt/eval contract now uses deterministic precheck rules.
- Verified: `python3` read results.course_correcting.json and showed state complete, pass_count 30, fail_count 0, max creator attempts 2, invalid-to-reviewer violations 0.
- Proof: /mnt/storage12tb/skills/ask/outputs/eval-reports/qra-ledger-auditor-v4-course-correcting-jsonmode-r8-20260830T1631Z/results.course_correcting.json.
- Not done: none for the requested QRA ledger-auditor eval repair action.
EOF
    node "$CHECK" < /tmp/onsg_zero_invalid_candidate.txt > /tmp/onsg_zero_invalid_pass.json
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_zero_invalid_pass.json','utf8')); if(d.decision!=='pass') throw new Error(JSON.stringify(d)); console.log('ZERO_INVALID_COMPLETION_PASS_OK')"
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
    echo "Usage: run.sh eval-zero-invalid-pass|eval-real-failure-followup|eval-unacted-next-followup"
    ;;
  *) echo "unknown command: $cmd" >&2; exit 2;;
esac
