#!/usr/bin/env bash
# Adversarial guard: fabricated / non-existent controls must NOT ground — the
# no-false-confidence property. An attacker probing a made-up control ID must be
# refused (can_answer != true / no sources), never answered with invented text.
# GREEN today; this locks the safety property so a "fix" for sparta#86 that
# over-grounds (answers anything) cannot pass.
set -uo pipefail
ENDPOINT="${ENDPOINT:-http://127.0.0.1:8601}"

grounds() {
  curl -s "${ENDPOINT}/answer" -H 'content-type: application/json' \
    -d "{\"q\": \"$1\", \"scope\": \"sparta\", \"k\": 10}" \
  | python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('false'); sys.exit()
srcs=d.get('sources') or d.get('source_keys') or []
print('true' if (d.get('can_answer') is True and len(srcs)>0) else 'false')"
}

a=$(grounds "What does SPARTA say about SV-ZZ-99?")
b=$(grounds "What countermeasures address the threats related to SV-XX-77?")
echo "SV-ZZ-99(fabricated)=${a} SV-XX-77(fabricated)=${b}"

if [ "$a" = "false" ] && [ "$b" = "false" ]; then
  echo "PASS: fabricated controls correctly refused (no false confidence)."
  exit 0
fi
echo "FAIL: a fabricated control grounded — the pipeline invented an answer." >&2
exit 1
