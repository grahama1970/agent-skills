#!/usr/bin/env bash
# Sanity checks for /ask skill
# Tests: imports, memory-agent CLI, basic commands, dependencies

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== /ask Sanity Checks ==="
echo ""

FAIL=0

# Test 1: Python module imports
echo "1. Python module imports..."
if python3 -c "
import sys
import importlib.util

# Load ask modules directly from files to avoid path conflicts
ask_dir = '$SCRIPT_DIR'

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# Load modules from ask directory
ask_mod = load_module('ask', f'{ask_dir}/ask.py')
status_mod = load_module('ask_status', f'{ask_dir}/status.py')

# Load split modules
skills_exec_mod = load_module('skills_exec', f'{ask_dir}/skills_exec.py')
monitor_mod = load_module('monitor', f'{ask_dir}/monitor.py')
pipeline_mod = load_module('pipeline', f'{ask_dir}/pipeline.py')

# Verify expected exports exist
assert hasattr(ask_mod, 'ask')
assert hasattr(skills_exec_mod, 'run_skill')
assert hasattr(monitor_mod, 'AskMonitor')
assert hasattr(status_mod, 'show_status')
print('   All modules import OK')
"; then
    echo "   PASS"
else
    echo "   FAIL: Module imports failed"
    FAIL=1
fi

# Test 2: memory-agent CLI availability (fast path)
echo ""
echo "2. memory-agent CLI (fast path)..."
MEMORY_CLI="$HOME/.local/bin/memory-agent"
if [[ -x "$MEMORY_CLI" ]]; then
    echo "   memory-agent found at $MEMORY_CLI"
    echo "   PASS"
else
    echo "   WARN: memory-agent not at $MEMORY_CLI (will use slow run.sh fallback)"
    # Not a failure, just a warning
fi

# Test 3: status command (fast, no external deps needed)
echo ""
echo "3. Status command (--json)..."
if python3 status.py --scope sanity-test --json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'   scope: {data.get(\"scope\", \"?\")}')
print(f'   total_items: {data.get(\"total_items\", 0)}')
" 2>/dev/null; then
    echo "   PASS"
else
    echo "   FAIL: status command broken"
    FAIL=1
fi

# Test 4: ask command (help/syntax check)
echo ""
echo "4. Ask command (syntax check)..."
if python3 ask.py --help >/dev/null 2>&1; then
    echo "   --help works"
    echo "   PASS"
else
    echo "   FAIL: ask.py --help failed"
    FAIL=1
fi

# Test 5: learn command (help/syntax check)
echo ""
echo "5. Learn command (syntax check)..."
if python3 -m pipeline --help >/dev/null 2>&1 || python3 -c "from pipeline import main; import sys; sys.argv=['pipeline','--help']; main()" 2>/dev/null; then
    echo "   --help works"
    echo "   PASS"
else
    echo "   FAIL: learn.py --help failed"
    FAIL=1
fi

# Test 5b: nightly command (help/syntax check)
echo ""
echo "5b. Nightly command (syntax check)..."
if python3 nightly.py --help >/dev/null 2>&1; then
    echo "   --help works"
    echo "   PASS"
else
    echo "   FAIL: nightly.py --help failed"
    FAIL=1
fi

# Test 6: Dependency skills accessible
echo ""
echo "6. Dependency skills..."
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"

check_skill() {
    local name="$1"
    local path="$2"
    if [[ -x "$path" ]]; then
        echo "   $name: OK"
        return 0
    else
        echo "   $name: MISSING ($path)"
        return 1
    fi
}

# Check required dependencies
if check_skill "extractor" "$SKILLS_DIR/extractor/run.sh" && \
   check_skill "dogpile" "$SKILLS_DIR/dogpile/run.sh" && \
   check_skill "memory" "$SKILLS_DIR/memory/run.sh"; then
    echo "   PASS"
else
    echo "   WARN: Some skills missing (degraded functionality)"
fi

# Test 7: Task-monitor state file location
echo ""
echo "7. Task-monitor integration..."
TASK_MONITOR_DIR="$HOME/.pi/task-monitor"
if [[ -d "$TASK_MONITOR_DIR" ]] || mkdir -p "$TASK_MONITOR_DIR" 2>/dev/null; then
    echo "   task-monitor dir: $TASK_MONITOR_DIR"
    echo "   PASS"
else
    echo "   WARN: Cannot create task-monitor dir"
fi

# Test 8: AskMonitor class initialization (tests task-monitor integration)
echo ""
echo "8. AskMonitor task-monitor integration..."
if python3 -c "
from monitor import AskMonitor
m = AskMonitor('sanity-test', 'sanity-test', register=False)
print(f'   steps: {len(m.STEPS)}')
print(f'   initial status: {m.step_status[\"memory_check\"]}')
m.start_step('memory_check')
print(f'   running status: {m.step_status[\"memory_check\"]}')
m.complete_step('memory_check', success=True)
print(f'   done status: {m.step_status[\"memory_check\"]}')
"; then
    echo "   PASS"
else
    echo "   FAIL: AskMonitor broken"
    FAIL=1
fi

echo ""
echo "======================================="
if [[ $FAIL -eq 0 ]]; then
    echo "All sanity checks PASSED"
    exit 0
else
    echo "Some checks FAILED"
    exit 1
fi
