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

echo "=== Sanity: argue ==="
check "SKILL.md exists" test -f SKILL.md
check "config.py exists" test -f config.py
check "debates dir exists" test -d debates

# Import check — config.py should parse cleanly
check "config.py imports" python3 -c "import importlib.util; spec = importlib.util.spec_from_file_location('config', '$SCRIPT_DIR/config.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)"

# Verify key constants are defined in config
check "config has DEFAULT_MAX_ROUNDS" python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('config', '$SCRIPT_DIR/config.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
assert hasattr(mod, 'DEFAULT_MAX_ROUNDS'), 'missing DEFAULT_MAX_ROUNDS'
assert hasattr(mod, 'VALID_MODES'), 'missing VALID_MODES'
assert hasattr(mod, 'DEBATES_DIR'), 'missing DEBATES_DIR'
"

# SKILL.md frontmatter check
check "SKILL.md has name field" grep -q "^name:" SKILL.md
check "SKILL.md has triggers" grep -q "triggers:" SKILL.md

# Line count check (max 800 lines per Python file)
for pyfile in *.py; do
    [ -f "$pyfile" ] || continue
    lines=$(wc -l < "$pyfile")
    check "$pyfile under 800 lines ($lines)" test "$lines" -lt 800
done

echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ]
