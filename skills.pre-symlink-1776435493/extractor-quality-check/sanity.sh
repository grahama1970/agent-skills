#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

PASS=0; FAIL=0
check() {
    local desc="$1"; shift
    if "$@" > /dev/null 2>&1; then
        echo "  PASS: $desc"; PASS=$((PASS+1))
    else
        echo "  FAIL: $desc"; FAIL=$((FAIL+1))
    fi
}

echo "=== Sanity: extractor-quality-check ==="

# Core files
check "SKILL.md exists" test -f SKILL.md
check "run.sh exists" test -f run.sh
check "run.sh executable" test -x run.sh

# Key modules
check "annealing.py exists" test -f annealing.py
check "batch_review.py exists" test -f batch_review.py
check "datalake_state_collector.py exists" test -f datalake_state_collector.py
check "inline_reviewer.py exists" test -f inline_reviewer.py
check "inline_review_loop.py exists" test -f inline_review_loop.py
check "convergence_tracker.py exists" test -f convergence_tracker.py

# Persona definitions
check "margaret_chen_persona.yaml exists" test -f margaret_chen_persona.yaml
check "jennifer_cheung_persona.yaml exists" test -f jennifer_cheung_persona.yaml

# CLI help
check "run.sh --help works" ./run.sh --help

# Import check — annealing module should parse cleanly
check "annealing.py imports" python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('annealing', '$SCRIPT_DIR/annealing.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, 'ANNEALING_SCHEDULE'), 'missing ANNEALING_SCHEDULE'
"

# Line count check (max 800 lines per Python file)
for pyfile in *.py; do
    [ -f "$pyfile" ] || continue
    lines=$(wc -l < "$pyfile")
    check "$pyfile under 800 lines ($lines)" test "$lines" -lt 800
done

echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ]
