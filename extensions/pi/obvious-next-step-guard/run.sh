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
  eval-qra-count-status-pass)
    cat > /tmp/onsg_qra_count_candidate.txt <<'EOF'
You’re right to ask for the exact number.

**QRA ledger-auditor:** I checked **30 seeded eval cases**, not 12–20.

Those were:
`case-01` through `case-30`

Breakdown:
- `12` expected `PASS`
- `14` expected `FAIL`
- `4` expected `NEEDS_HUMAN_REVIEW`
- final result: `30/30` passed
- invalid creator output sent to reviewer: `0`

Important boundary: these were **QRA ledger-auditor eval cases**, not 30 arbitrary production QRAs manually hardened one-by-one.

Status Report
- Changed: clarified the actual QRA count and proof boundary.
- Verified: `python3` read the r8 results and printed `QRA_CASE_COUNT 30`, IDs `case-01` through `case-30`, `QRA_PASS_COUNT 30`, `QRA_FAIL_COUNT 0`, expected verdict counts `{'FAIL': 14, 'NEEDS_HUMAN_REVIEW': 4, 'PASS': 12}`.
- Proof: `/tmp/memory-hardening-vague-report-qra-count.txt`; QRA r8 result JSON.
- Not done: none for the QRA count answer.
EOF
    node "$CHECK" < /tmp/onsg_qra_count_candidate.txt > /tmp/onsg_qra_count_pass.json
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_qra_count_pass.json','utf8')); if(d.decision!=='pass') throw new Error(JSON.stringify(d)); console.log('QRA_COUNT_STATUS_PASS_OK')"
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
  eval-completed-typed-failure-pass)
    cat > /tmp/onsg_completed_typed_failure_candidate.txt <<'EOF'
Corrected answer: `agent-skills#1555` is closed, and the Ask/SciLLM empty-response failure is now typed as `scillm_empty_response_200` instead of generic `handler_execution_failed`.

Status Report
- Changed: Ask now gives an actionable recovery code when SciLLM returns HTTP 200 with empty assistant content; triage-error recognizes the same old receipt shape.
- Verified: `gh issue view 1555 --repo grahama1970/agent-skills --json number,state,closed,labels,url` read back `state=CLOSED`, `closed=true`; `git fetch origin main && git rev-parse origin/main` read back `9ec27a6659019ba658410abecd21b3cf9bdf4703`.
- Proof: `/tmp/triage-ask-handler-empty-response-1555-after.json`; `/tmp/ask-1555-agentic-eval.json`; `/tmp/triage-error-1555-agentic-eval.json`; `/tmp/research-routing-retry-brave-project-watchdog-triage-evals-close.json`; issue URL `https://github.com/grahama1970/agent-skills/issues/1555`.
- Not done: none for `agent-skills#1555` closure.
EOF
    node "$CHECK" < /tmp/onsg_completed_typed_failure_candidate.txt > /tmp/onsg_completed_typed_failure_pass.json
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_completed_typed_failure_pass.json','utf8')); if(d.decision!=='pass'||d.features.failure_report!==false) throw new Error(JSON.stringify(d)); console.log('COMPLETED_TYPED_FAILURE_PASS_OK')"
    ;;
  eval-completed-research-routing-triage-pass)
    cat > /tmp/onsg_research_routing_triage_candidate.txt <<'EOF'
Status Report
- Changed: The installed `research-routing-gates` checker now treats successful `triage-error` or Tau evidence as satisfying the broad-error sanity step, so it does not demand an extra `ask_fast_single` call after triage already ran.
- Verified: `node /home/graham/.pi/agent/extensions/research-routing-gates/research-gate-check.mjs < /tmp/research-routing-status-report-repro-payload.json` returned `decision=pass`; `skills/agentic-evals/run.sh run /home/graham/.pi/agent/extensions/research-routing-gates/fixtures/agentic_eval.json --case real-world-triage-satisfies-broad-error-gate --output /tmp/research-routing-triage-satisfies-broad-error-eval.json` returned `readiness=READY`, `PASS=1`, `trial_count=2`.
- Proof: `/tmp/research-routing-status-report-repro-after.json`; `/tmp/research-routing-triage-satisfies-broad-error-eval.json`; patched files under `/home/graham/.pi/agent/extensions/research-routing-gates/`.
- Not done: none for this gate repair.
EOF
    node "$CHECK" < /tmp/onsg_research_routing_triage_candidate.txt > /tmp/onsg_research_routing_triage_pass.json
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_research_routing_triage_pass.json','utf8')); if(d.decision!=='pass'||d.features.failure_report!==false) throw new Error(JSON.stringify(d)); console.log('RESEARCH_ROUTING_TRIAGE_COMPLETION_PASS_OK')"
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
  eval-json-remaining-followup)
    cat > /tmp/onsg_json_remaining_candidate.txt <<'EOF'
{
  "changed": ["research gate retry prompt"],
  "verified": ["focused eval passed"],
  "proof": ["/tmp/receipt.json"],
  "remaining": "rename/migration was not performed"
}
EOF
    set +e
    node "$CHECK" < /tmp/onsg_json_remaining_candidate.txt > /tmp/onsg_json_remaining_followup.json 2>/tmp/onsg_json_remaining_followup.err
    rc=$?
    set -e
    test "$rc" -eq 2
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_json_remaining_followup.json','utf8')); if(d.decision!=='follow_up'||!d.actionable_actions.some(a=>a.includes('rename/migration'))) throw new Error(JSON.stringify(d)); console.log('JSON_REMAINING_FOLLOWUP_OK')"
    ;;
  eval-json-remaining-none-pass)
    cat > /tmp/onsg_json_remaining_none_candidate.txt <<'EOF'
{
  "changed": ["research gate retry prompt"],
  "verified": ["focused eval passed"],
  "proof": ["/tmp/receipt.json"],
  "remaining": "none"
}
EOF
    node "$CHECK" < /tmp/onsg_json_remaining_none_candidate.txt > /tmp/onsg_json_remaining_none_pass.json
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_json_remaining_none_pass.json','utf8')); if(d.decision!=='pass') throw new Error(JSON.stringify(d)); console.log('JSON_REMAINING_NONE_PASS_OK')"
    ;;
  eval-text-remaining-rename-followup)
    printf 'Status Report\n- Changed: checker patched.\n- Verified: focused eval passed.\n- Proof: /tmp/receipt.json.\n- Remaining: rename/migration was not performed.\n' > /tmp/onsg_text_remaining_rename_candidate.txt
    set +e
    node "$CHECK" < /tmp/onsg_text_remaining_rename_candidate.txt > /tmp/onsg_text_remaining_rename_followup.json 2>/tmp/onsg_text_remaining_rename_followup.err
    rc=$?
    set -e
    test "$rc" -eq 2
    node -e "const fs=require('fs');const d=JSON.parse(fs.readFileSync('/tmp/onsg_text_remaining_rename_followup.json','utf8')); if(d.decision!=='follow_up'||!d.actionable_actions.some(a=>a.includes('rename/migration'))) throw new Error(JSON.stringify(d)); console.log('TEXT_REMAINING_RENAME_FOLLOWUP_OK')"
    ;;
  help|--help|-h)
    echo "Usage: run.sh eval-zero-invalid-pass|eval-qra-count-status-pass|eval-sensible-memory-status-pass|eval-hook-thrash-status-pass|eval-completed-typed-failure-pass|eval-completed-research-routing-triage-pass|eval-real-failure-followup|eval-unacted-next-followup|eval-json-remaining-followup|eval-json-remaining-none-pass|eval-text-remaining-rename-followup"
    ;;
  *) echo "unknown command: $cmd" >&2; exit 2;;
esac
