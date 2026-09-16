#!/usr/bin/env bash
# Anti-pattern linter for pi-subagents workflowScripts.
# Usage: validate-workflowscript.sh <file.workflow.js>
# exit 0 = clean; exit 1 = violations listed (patterns the runtime rejects or
# that break portability/robustness per best-practices-workflowscript).
set -uo pipefail
FILE="${1:-}"
[[ -n "$FILE" && -f "$FILE" ]] || { echo "usage: $0 <file.workflow.js>"; exit 2; }

fail=0
check() { # pattern label
  if grep -nE "$1" "$FILE" >/dev/null 2>&1; then
    echo "VIOLATION [$2]:"; grep -nE "$1" "$FILE" | head -3; fail=1
  fi
}

check 'async[[:space:]]+function' 'nested async function (not portable)'
check '=>'          'arrow function (not portable)'
check 'async[[:space:]]*\(' 'async arrow/paren helper'
check 'require\(|from[[:space:]]+.fs.|node:fs|process\.' 'host globals / fs (scripts have none)'
check 'git add -A|git add \.|git stash|git reset --hard|git checkout main ' 'banned git mutation in child task text'
check 'workflowScript\s*:\s*['"'"'"]'   'nested workflowScript launch (children cannot)'

# advisories (do not fail, but surface)
grep -nE 'while[[:space:]]*\(|for[[:space:]]*\(;;' "$FILE" >/dev/null 2>&1 \
  && { echo "ADVISORY: unbounded while/for(;;) loop — confirm cap source (config gate child)"; }
grep -q 'model-preflight' "$FILE" || grep -qE 'PREFLIGHT|preflight' "$FILE" \
  || { echo "ADVISORY: no provider preflight reference — required if the workflow consumes models/web seats"; }
grep -q 'origin/main' "$FILE" \
  || { echo "ADVISORY: no origin/main comparison note — mutating children need the CRIT method note"; }

if (( fail )); then
  echo "RESULT: FAIL — fix violations, then run subagent({action:'validate',workflowScriptPath})"
  exit 1
fi
echo "RESULT: CLEAN — now run subagent({action:'validate',workflowScriptPath:'$FILE'}) before launching"
