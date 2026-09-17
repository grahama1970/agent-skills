#!/usr/bin/env bash
# Regression guard for sparta#86: real countermeasure (CM) and weakness (CWE)
# controls must GROUND through /answer, exactly like technique controls do.
# RED while the bug is open (CM0029/CWE-287 -> can_answer=False/None, 0 sources);
# GREEN once the pipeline grounds them. This transition IS the fix proof.
#
# Env: ENDPOINT (default http://127.0.0.1:8601). Exits 0 only if BOTH real
# controls ground AND the known-good technique control still grounds (so a
# regression that breaks techniques to "fix" controls also fails this guard).
set -uo pipefail
ENDPOINT="${ENDPOINT:-http://127.0.0.1:8601}"

grounds() {  # $1=question -> prints "true"/"false"; nonempty sources required
  curl -s "${ENDPOINT}/answer" -H 'content-type: application/json' \
    -d "{\"q\": \"$1\", \"scope\": \"sparta\", \"k\": 10}" \
  | python3 -c "import sys,json
try: d=json.load(sys.stdin)
except Exception: print('false'); sys.exit()
srcs=d.get('sources') or d.get('source_keys') or []
print('true' if (d.get('can_answer') is True and len(srcs)>0) else 'false')"
}

cm=$(grounds "What does SPARTA CM0029 cover?")
cwe=$(grounds "What does SPARTA say about CWE-287?")
tech=$(grounds "What does SPARTA say about IA-0007.02?")   # known-good control

echo "CM0029=${cm} CWE-287=${cwe} IA-0007.02(control)=${tech}"

if [ "$tech" != "true" ]; then
  echo "FAIL: known-good technique IA-0007.02 stopped grounding — environment/regression, not the #86 fix." >&2
  exit 2
fi
if [ "$cm" = "true" ] && [ "$cwe" = "true" ]; then
  echo "PASS: CM and CWE controls ground (sparta#86 fixed)."
  exit 0
fi
echo "FAIL: sparta#86 open — real CM/CWE controls do not ground." >&2
exit 1
