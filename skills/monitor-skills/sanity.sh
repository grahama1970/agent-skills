#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [monitor-skills] Sanity Check ==="

# Check 1: Required files exist
echo "Check 1: Required files..."
for f in SKILL.md run.sh; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "  All required files present"

# Check 2: run.sh is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh is not executable"
    exit 1
fi
echo "  run.sh is executable"

# Check 3: Required CLI tools
for cmd in rsync python3 find; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "FAIL: Required command not found: $cmd"
        exit 1
    fi
done
echo "  CLI tools available (rsync, python3, find)"

# Check 4: State directory can be created
STATE_DIR="${HOME}/.pi/monitor-skills"
mkdir -p "$STATE_DIR"
echo "  State directory OK: $STATE_DIR"

# Check 5: help command works
help_output=$("$SCRIPT_DIR/run.sh" help 2>&1)
if ! echo "$help_output" | grep -q "monitor-skills"; then
    echo "FAIL: run.sh help did not produce expected output"
    exit 1
fi
echo "  run.sh help works"

# Check 6: check command runs (read-only drift detection)
"$SCRIPT_DIR/run.sh" check 2>&1 || true
echo "  check command executes"

# Check 7: status command runs
status_output=$("$SCRIPT_DIR/run.sh" status 2>&1 || true)
if echo "$status_output" | grep -q "Monitor Skills Status"; then
    echo "  status command works"
else
    echo "FAIL: status command did not produce expected output"
    exit 1
fi

# Check 8: Verify registry file handling
REGISTRY_FILE="${HOME}/.agent_skills_targets"
if [[ -f "$REGISTRY_FILE" ]]; then
    project_count=$(grep -v "^#" "$REGISTRY_FILE" | grep -v "^$" | wc -l)
    echo "  Registry has $project_count registered projects"
else
    echo "  No registry file at $REGISTRY_FILE (will use defaults)"
fi

# Check 9: Gap detection module imports
gap_import=$(uv run --project "$SCRIPT_DIR" python3 -c "from probes.skill_gap import run_gap_scan, gap_scan_status; print('ok')" 2>&1) || true
if [[ "$gap_import" == "ok" ]]; then
    echo "  Gap detection module imports OK"
else
    echo "WARN: Gap detection module import failed: $gap_import"
fi

echo "Result: PASS"
