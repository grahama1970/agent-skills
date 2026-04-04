#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== [monitor-skill-health] Sanity Check ==="

for f in SKILL.md run.sh monitor.py pyproject.toml; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: missing $f"
        exit 1
    fi
done

echo "Check: required files present"

if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not executable"
    exit 1
fi

echo "Check: run.sh executable"

help_output="$($SCRIPT_DIR/run.sh --help 2>&1)"
if ! grep -q "Monitor skill health" <<< "$help_output"; then
    echo "FAIL: help output missing expected header"
    exit 1
fi

echo "Check: CLI help OK"

json_output="$($SCRIPT_DIR/run.sh audit --limit 1 --no-memory --no-deep-review --json 2>/dev/null || true)"
if ! grep -q '"summary"' <<< "$json_output"; then
    echo "FAIL: audit did not produce JSON summary"
    exit 1
fi

echo "Check: audit JSON output OK"

echo "Result: PASS"
