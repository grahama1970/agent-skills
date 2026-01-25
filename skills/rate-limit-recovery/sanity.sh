#!/bin/bash
set -euo pipefail

# Sanity check script for rate-limit-recovery skill
# Tests basic functionality and dependencies

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/rate_limit_recovery.py"

echo "Running sanity checks for rate-limit-recovery skill..."

# Check Python availability
echo -n "Checking Python 3... "
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo "✓ Found: $PYTHON_VERSION"
else
    echo "✗ Python 3 not found"
    exit 1
fi

# Check Python script exists and is readable
echo -n "Checking Python script... "
if [[ -f "$PYTHON_SCRIPT" && -r "$PYTHON_SCRIPT" ]]; then
    echo "✓ Found and readable"
else
    echo "✗ Missing or not readable: $PYTHON_SCRIPT"
    exit 1
fi

# Check Python syntax
echo -n "Checking Python syntax... "
if python3 -m py_compile "$PYTHON_SCRIPT" 2>/dev/null; then
    echo "✓ Syntax OK"
else
    echo "✗ Syntax errors detected"
    python3 -m py_compile "$PYTHON_SCRIPT"
    exit 1
fi

# Check required Python modules
echo -n "Checking required modules... "
REQUIRED_MODULES=("json" "os" "subprocess" "sys" "argparse" "datetime" "pathlib" "typing" "glob" "re")
MISSING_MODULES=()

for module in "${REQUIRED_MODULES[@]}"; do
    if ! python3 -c "import $module" 2>/dev/null; then
        MISSING_MODULES+=("$module")
    fi
done

if [[ ${#MISSING_MODULES[@]} -eq 0 ]]; then
    echo "✓ All required modules available"
else
    echo "✗ Missing modules: ${MISSING_MODULES[*]}"
    exit 1
fi

# Test help command
echo -n "Testing help command... "
if python3 "$PYTHON_SCRIPT" --help &>/dev/null; then
    echo "✓ Help command works"
else
    echo "✗ Help command failed"
    exit 1
fi

# Test basic recover command (should auto-detect or show appropriate message)
echo -n "Testing basic recover command... "
RECOVER_OUTPUT=$(python3 "$PYTHON_SCRIPT" recover 2>&1 || true)
if [[ "$RECOVER_OUTPUT" == *"Could not auto-detect platform"* ]] || [[ "$RECOVER_OUTPUT" == *"Recovering from"* ]]; then
    echo "✓ Basic recover command responds correctly"
else
    echo "✗ Basic recover command failed"
    echo "Output: $RECOVER_OUTPUT"
    exit 1
fi

# Check run script exists and is executable
echo -n "Checking run script... "
RUN_SCRIPT="${SCRIPT_DIR}/run.sh"
if [[ -f "$RUN_SCRIPT" && -x "$RUN_SCRIPT" ]]; then
    echo "✓ Found and executable"
else
    echo "✗ Missing or not executable: $RUN_SCRIPT"
    exit 1
fi

# Test run script help
echo -n "Testing run script help... "
if "$RUN_SCRIPT" --help &>/dev/null; then
    echo "✓ Run script help works"
else
    echo "✗ Run script help failed"
    exit 1
fi

# Check SKILL.md exists
echo -n "Checking SKILL.md... "
if [[ -f "${SCRIPT_DIR}/SKILL.md" && -r "${SCRIPT_DIR}/SKILL.md" ]]; then
    echo "✓ Found and readable"
else
    echo "✗ Missing or not readable: SKILL.md"
    exit 1
fi

# Verify SKILL.md has required sections
echo -n "Checking SKILL.md content... "
if grep -q "name: rate-limit-recovery" "${SCRIPT_DIR}/SKILL.md" && \
   grep -q "description:" "${SCRIPT_DIR}/SKILL.md" && \
   grep -q "triggers:" "${SCRIPT_DIR}/SKILL.md"; then
    echo "✓ Required sections present"
else
    echo "✗ Missing required sections in SKILL.md"
    exit 1
fi

echo ""
echo "All sanity checks passed! ✓"
echo "Rate-limit-recovery skill is ready to use."
echo ""
echo "To test the skill:"
echo "  ./run.sh recover                    # Auto-detect platform"
echo "  ./run.sh recover --platform codex   # Specific platform"
echo "  ./run.sh recover --help             # Show all options"