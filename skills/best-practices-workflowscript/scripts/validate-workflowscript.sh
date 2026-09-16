#!/usr/bin/env bash
# Anti-pattern linter for pi-subagents workflowScripts.
# Usage: validate-workflowscript.sh <file.workflow.js> [--json-out <path>]
# exit 0 = clean; exit 1 = violations listed (patterns the runtime rejects or
# that break portability/robustness per best-practices-workflowscript).
# --json-out writes {file, verdict, violations:[{line,rule}], advisories:[...]}
# so callers get a content oracle, not just exit codes.
set -uo pipefail
FILE=""
JSON_OUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json-out) JSON_OUT="$2"; shift 2 ;;
    *) FILE="$1"; shift ;;
  esac
done
[[ -n "$FILE" && -f "$FILE" ]] || { echo "usage: $0 <file.workflow.js> [--json-out <path>]"; exit 2; }

VIOLATIONS_FILE="$(mktemp /tmp/wfs-viol.XXXXXX)"
ADVISORIES_FILE="$(mktemp /tmp/wfs-adv.XXXXXX)"
trap 'rm -f "$VIOLATIONS_FILE" "$ADVISORIES_FILE"' EXIT

fail=0
check() { # pattern rule-id
  local hits
  hits="$(grep -nE "$1" "$FILE" 2>/dev/null)" || return 0
  while IFS= read -r line; do
    printf '%s\t%s\n' "${line%%:*}" "$2" >> "$VIOLATIONS_FILE"
    echo "VIOLATION [$2]: $line"
  done <<< "$hits"
  fail=1
}

check 'async[[:space:]]+function' 'nested_async_function'
check '=>'          'arrow_function'
check 'async[[:space:]]*\(' 'async_paren_helper'
check 'require\(|from[[:space:]]+.fs.|node:fs|process\.' 'host_global_or_fs'
check 'git add -A|git add \.|git stash|git reset --hard|git checkout main ' 'banned_git_mutation'
check 'workflowScript\s*:\s*['"'"'"]'   'nested_workflowscript_launch'

# Self-contained header contract: purpose + Diagram: link + Launch: usage
first_lines="$(head -n 12 "$FILE")"
if ! printf '%s' "$first_lines" | head -n 1 | grep -q '^//'; then
  echo "VIOLATION [missing_self_contained_header]: file must start with a // header block"; echo -e '1\tmissing_self_contained_header' >> "$VIOLATIONS_FILE"; fail=1
elif ! printf '%s' "$first_lines" | grep -q 'Diagram:'; then
  echo "VIOLATION [missing_self_contained_header]: header must link its diagram: 'Diagram: <name>.diagram.md ($create-architecture)'"; echo -e '1\tmissing_self_contained_header' >> "$VIOLATIONS_FILE"; fail=1
elif ! printf '%s' "$first_lines" | grep -q 'Launch:'; then
  echo "VIOLATION [missing_self_contained_header]: header must contain a 'Launch:' usage line"; echo -e '1\tmissing_self_contained_header' >> "$VIOLATIONS_FILE"; fail=1
fi

grep -nE 'while[[:space:]]*\(|for[[:space:]]*\(;;' "$FILE" >/dev/null 2>&1 \
  && { echo "ADVISORY: unbounded while/for(;;) loop — confirm cap source (config gate child)"; \
       echo "unbounded_loop" >> "$ADVISORIES_FILE"; }
grep -q 'model-preflight' "$FILE" || grep -qE 'PREFLIGHT|preflight' "$FILE" || true
if ! grep -qE 'preflight' "$FILE"; then
  echo "ADVISORY: no provider preflight reference — required if the workflow consumes models/web seats"
  echo "no_preflight" >> "$ADVISORIES_FILE"
fi
grep -q 'origin/main' "$FILE" || {
  echo "ADVISORY: no origin/main comparison note — mutating children need the CRIT method note"
  echo "no_origin_main_note" >> "$ADVISORIES_FILE"
}

VERDICT="CLEAN"
(( fail )) && VERDICT="FAIL"
echo "RESULT: $VERDICT"

if [[ -n "$JSON_OUT" ]]; then
  python3 - "$FILE" "$VERDICT" "$VIOLATIONS_FILE" "$ADVISORIES_FILE" "$JSON_OUT" <<'PY'
import json, sys
path, verdict, vfile, afile, out = sys.argv[1:6]
violations=[]
for line in open(vfile):
    ln, rule = line.rstrip('\n').split('\t', 1)
    violations.append({"line": int(ln), "rule": rule})
advisories=[l.strip() for l in open(afile) if l.strip()]
json.dump({"file": path, "verdict": verdict, "violations": violations,
           "advisories": advisories}, open(out, 'w'), indent=1)
PY
fi
exit $(( fail ? 1 : 0 ))
