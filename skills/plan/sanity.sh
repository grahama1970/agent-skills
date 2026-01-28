#!/bin/bash
# Sanity check for plan skill
# Verifies the skill can run and validate task files

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Plan Skill Sanity Check ==="

# Check Python availability
if command -v uv &> /dev/null; then
    EXEC=(uv run python)
    echo "[OK] uv available"
elif command -v python3 &> /dev/null; then
    EXEC=(python3)
    echo "[OK] python3 available"
else
    echo "[FAIL] No Python interpreter found"
    exit 1
fi

# Check plan.py exists and is valid Python
if [ ! -f "$SCRIPT_DIR/plan.py" ]; then
    echo "[FAIL] plan.py not found"
    exit 1
fi

"${EXEC[@]}" -m py_compile "$SCRIPT_DIR/plan.py"
echo "[OK] plan.py syntax valid"

# Test dependency analysis
DEPS=$("${EXEC[@]}" "$SCRIPT_DIR/plan.py" --analyze-deps "use camelot and pdfplumber" --json)
if echo "$DEPS" | grep -q "camelot"; then
    echo "[OK] Dependency analysis works (found camelot)"
else
    echo "[FAIL] Dependency analysis failed"
    exit 1
fi

# Test that well-known packages are filtered
WELL_KNOWN=$("${EXEC[@]}" "$SCRIPT_DIR/plan.py" --analyze-deps "use requests and json" --json)
if echo "$WELL_KNOWN" | grep -q '"non_standard_packages": \[\]'; then
    echo "[OK] Well-known packages correctly filtered"
else
    echo "[WARN] Well-known package filtering may need adjustment"
fi

# Create a test task file and validate it
TEST_FILE=$(mktemp)
cat > "$TEST_FILE" << 'EOF'
# Task List: Test

**Created**: 2026-01-28
**Goal**: Test validation

## Context

Test context.

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| N/A | Standard library only | N/A | N/A |

## Questions/Blockers

None - all requirements clear.

---

## Tasks

### P0: Setup (Sequential)

- [ ] **Task 1**: Test task
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Sanity**: None (standard library only)
  - **Definition of Done**:
    - Test: `tests/test_feature.py::test_basic`
    - Assertion: Returns expected value

---

## Completion Criteria

- [ ] All tasks complete
EOF

VALIDATION=$("${EXEC[@]}" "$SCRIPT_DIR/plan.py" --validate "$TEST_FILE" --json)
rm -f "$TEST_FILE"

if echo "$VALIDATION" | grep -q '"valid": true'; then
    echo "[OK] Task file validation works"
else
    echo "[FAIL] Task file validation failed"
    echo "$VALIDATION"
    exit 1
fi

echo ""
echo "=== All sanity checks passed ==="
exit 0
