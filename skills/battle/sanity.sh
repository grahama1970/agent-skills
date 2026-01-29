#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Battle Skill Sanity ==="
echo ""

# Track failures
FAILURES=0

pass() {
    echo "  [PASS] $1"
}

fail() {
    echo "  [FAIL] $1"
    FAILURES=$((FAILURES + 1))
}

warn() {
    echo "  [WARN] $1"
}

# -----------------------------------------------------------------------------
# File existence checks
# -----------------------------------------------------------------------------
echo "1. Checking file structure..."

# Check run.sh
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    pass "run.sh exists and is executable"
else
    fail "run.sh missing or not executable"
fi

# Check SKILL.md
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    pass "SKILL.md exists"
else
    fail "SKILL.md missing"
fi

# Check battle.py (new thin CLI)
if [[ -f "$SCRIPT_DIR/battle.py" ]]; then
    pass "battle.py exists"
else
    fail "battle.py missing"
fi

# Check battle_monolith.py (backup)
if [[ -f "$SCRIPT_DIR/battle_monolith.py" ]]; then
    pass "battle_monolith.py backup exists"
else
    warn "battle_monolith.py backup not found"
fi

# Check module files
MODULES="config.py state.py memory.py scoring.py digital_twin.py red_team.py blue_team.py orchestrator.py report.py qemu_support.py"
for module in $MODULES; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        pass "Module $module exists"
    else
        fail "Module $module missing"
    fi
done

# Check __init__.py
if [[ -f "$SCRIPT_DIR/__init__.py" ]]; then
    pass "__init__.py exists"
else
    fail "__init__.py missing"
fi

echo ""

# -----------------------------------------------------------------------------
# Module size checks (< 500 lines each)
# -----------------------------------------------------------------------------
echo "2. Checking module sizes (< 500 lines)..."

for module in $MODULES battle.py; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        LINES=$(wc -l < "$SCRIPT_DIR/$module")
        if [[ $LINES -lt 500 ]]; then
            pass "$module: $LINES lines"
        else
            fail "$module: $LINES lines (exceeds 500)"
        fi
    fi
done

echo ""

# -----------------------------------------------------------------------------
# Python syntax checks
# -----------------------------------------------------------------------------
echo "3. Checking Python syntax..."

cd "$SCRIPT_DIR"
for module in $MODULES battle.py __init__.py __main__.py; do
    if [[ -f "$SCRIPT_DIR/$module" ]]; then
        if python3 -m py_compile "$module" 2>/dev/null; then
            pass "$module syntax OK"
        else
            fail "$module has syntax errors"
        fi
    fi
done

echo ""

# -----------------------------------------------------------------------------
# Import checks (no circular imports)
# -----------------------------------------------------------------------------
echo "4. Checking imports work..."

cd "$SCRIPT_DIR"
if python3 -c "import config" 2>/dev/null; then
    pass "config imports OK"
else
    fail "config import failed"
fi

if python3 -c "import state" 2>/dev/null; then
    pass "state imports OK"
else
    fail "state import failed"
fi

if python3 -c "import memory" 2>/dev/null; then
    pass "memory imports OK"
else
    fail "memory import failed"
fi

if python3 -c "import scoring" 2>/dev/null; then
    pass "scoring imports OK"
else
    fail "scoring import failed"
fi

if python3 -c "import digital_twin" 2>/dev/null; then
    pass "digital_twin imports OK"
else
    fail "digital_twin import failed"
fi

if python3 -c "import red_team" 2>/dev/null; then
    pass "red_team imports OK"
else
    fail "red_team import failed"
fi

if python3 -c "import blue_team" 2>/dev/null; then
    pass "blue_team imports OK"
else
    fail "blue_team import failed"
fi

if python3 -c "import orchestrator" 2>/dev/null; then
    pass "orchestrator imports OK"
else
    fail "orchestrator import failed"
fi

if python3 -c "import battle" 2>/dev/null; then
    pass "battle imports OK"
else
    fail "battle import failed"
fi

echo ""

# -----------------------------------------------------------------------------
# CLI help checks
# -----------------------------------------------------------------------------
echo "5. Checking CLI commands..."

# Main help
if "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    pass "run.sh --help works"
else
    fail "run.sh --help failed"
fi

# Battle command help
if "$SCRIPT_DIR/run.sh" battle --help >/dev/null 2>&1; then
    pass "battle command help works"
else
    fail "battle command help failed"
fi

# Status command
if "$SCRIPT_DIR/run.sh" status >/dev/null 2>&1; then
    pass "status command works"
else
    fail "status command failed"
fi

# Report command (expected to fail without battle_id)
if "$SCRIPT_DIR/run.sh" report --help >/dev/null 2>&1; then
    pass "report command help works"
else
    fail "report command help failed"
fi

# Resume command help
if "$SCRIPT_DIR/run.sh" resume --help >/dev/null 2>&1; then
    pass "resume command help works"
else
    fail "resume command help failed"
fi

# Stop command help
if "$SCRIPT_DIR/run.sh" stop --help >/dev/null 2>&1; then
    pass "stop command help works"
else
    fail "stop command help failed"
fi

echo ""

# -----------------------------------------------------------------------------
# Required sibling skills
# -----------------------------------------------------------------------------
echo "6. Checking sibling skills..."

SKILLS_DIR="$SCRIPT_DIR/.."
for skill in hack anvil task-monitor; do
    if [[ -d "$SKILLS_DIR/$skill" ]]; then
        pass "Sibling skill '$skill' exists"
    else
        warn "Sibling skill '$skill' not found"
    fi
done

# Check .agent skills
AGENT_SKILLS_DIR="$SCRIPT_DIR/../../.agent/skills"
for skill in memory dogpile taxonomy; do
    if [[ -d "$AGENT_SKILLS_DIR/$skill" ]]; then
        pass "Agent skill '$skill' exists"
    else
        warn "Agent skill '$skill' not found"
    fi
done

echo ""

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
echo "================================"
if [[ $FAILURES -eq 0 ]]; then
    echo "Result: PASS"
    echo "Battle skill is ready."
    exit 0
else
    echo "Result: FAIL ($FAILURES failures)"
    echo "Please fix the issues above."
    exit 1
fi
