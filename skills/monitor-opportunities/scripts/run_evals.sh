#!/usr/bin/env bash
# Run every monitor-opportunities regression guard. Exit non-zero on ANY red.
# This is the source-of-truth "is the skill working?" gate the cron watches.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
for g in \
  eval_resume_not_stub \
  eval_field_classifier \
  eval_top_candidate_survives \
  eval_response_hardening \
  eval_linkedin_easy_apply \
  eval_top_applicant_shortlisted \
  eval_ashby_prefill \
; do
  if python3 "scripts/$g.py" >/dev/null 2>"scripts/.$g.err"; then
    echo "OK   $g"
  else
    echo "FAIL $g"
    sed 's/^/       /' "scripts/.$g.err" 2>/dev/null | head -3
    fail=1
  fi
  rm -f "scripts/.$g.err"
done

if [ "$fail" -ne 0 ]; then
  echo "EVAL_SUITE_RED"
  exit 1
fi
echo "EVAL_SUITE_GREEN"
