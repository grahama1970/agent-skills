#!/bin/bash
#
# Integration tests for orchestrate skill
# Works with both pi and claude code backends
#
# Usage:
#   ./tests/test_orchestrate.sh           Run all tests
#   ./tests/test_orchestrate.sh parsing   Run only parsing tests
#   ./tests/test_orchestrate.sh parallel  Run only parallel tests
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASSED=0
FAILED=0

pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    PASSED=$((PASSED + 1))
}

fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    FAILED=$((FAILED + 1))
}

skip() {
    echo -e "${YELLOW}[SKIP]${NC} $1"
}

# ============================================================================
# Test: run.sh script availability
# ============================================================================
test_script_availability() {
    echo "=== Script Availability Tests ==="

    if [[ -x "$SKILL_DIR/run.sh" ]]; then
        pass "run.sh is executable"
    else
        fail "run.sh missing or not executable"
    fi

    if [[ -x "$SKILL_DIR/quality-gate.sh" ]]; then
        pass "quality-gate.sh is executable"
    else
        fail "quality-gate.sh missing or not executable"
    fi

    if [[ -x "$SKILL_DIR/preflight.sh" ]]; then
        pass "preflight.sh is executable"
    else
        fail "preflight.sh missing or not executable"
    fi
}

# ============================================================================
# Test: Help command
# ============================================================================
test_help_command() {
    echo ""
    echo "=== Help Command Tests ==="

    if "$SKILL_DIR/run.sh" --help 2>&1 | grep -q "orchestrate run"; then
        pass "run.sh --help shows run command"
    else
        fail "run.sh --help missing run command"
    fi

    if "$SKILL_DIR/run.sh" --help 2>&1 | grep -q "schedule"; then
        pass "run.sh --help shows schedule command"
    else
        fail "run.sh --help missing schedule command"
    fi

    if "$SKILL_DIR/run.sh" --help 2>&1 | grep -q "Parallel"; then
        pass "run.sh --help mentions Parallel field"
    else
        fail "run.sh --help missing Parallel field mention"
    fi
}

# ============================================================================
# Test: Preflight validation
# ============================================================================
test_preflight_validation() {
    echo ""
    echo "=== Preflight Validation Tests ==="

    # Test with valid fixture
    if "$SKILL_DIR/preflight.sh" "$FIXTURES_DIR/parallel_tasks.md" >/dev/null 2>&1; then
        pass "preflight.sh passes for valid task file"
    else
        fail "preflight.sh failed for valid task file"
    fi

    # Test with blockers - create temp file
    local temp_blockers
    temp_blockers=$(mktemp)
    cat > "$temp_blockers" << 'EOF'
# Task List: Test

## Tasks
- [ ] **Task 1**: Do something
  - Agent: general-purpose

## Questions/Blockers
- What database should we use?
- How should we handle auth?
EOF

    if ! "$SKILL_DIR/preflight.sh" "$temp_blockers" >/dev/null 2>&1; then
        pass "preflight.sh blocks when questions exist"
    else
        fail "preflight.sh should block when questions exist"
    fi

    rm -f "$temp_blockers"
}

# ============================================================================
# Test: Quality gate detection
# ============================================================================
test_quality_gate_detection() {
    echo ""
    echo "=== Quality Gate Detection Tests ==="

    # Create temp Python project
    local temp_dir
    temp_dir=$(mktemp -d)
    echo '[project]
name = "test"
version = "0.1.0"' > "$temp_dir/pyproject.toml"

    pushd "$temp_dir" > /dev/null

    # Quality gate should detect Python and try to run tests
    # It will fail (no tests) but should detect the project type
    local output
    output=$("$SKILL_DIR/quality-gate.sh" 2>&1 || true)

    if echo "$output" | grep -q "Python project"; then
        pass "quality-gate.sh detects Python project"
    else
        fail "quality-gate.sh failed to detect Python project"
    fi

    popd > /dev/null
    rm -rf "$temp_dir"

    # Create temp Node project
    temp_dir=$(mktemp -d)
    echo '{"name": "test", "scripts": {"test": "echo ok"}}' > "$temp_dir/package.json"

    pushd "$temp_dir" > /dev/null

    output=$("$SKILL_DIR/quality-gate.sh" 2>&1 || true)

    if echo "$output" | grep -q "Node.js project"; then
        pass "quality-gate.sh detects Node.js project"
    else
        fail "quality-gate.sh failed to detect Node.js project"
    fi

    popd > /dev/null
    rm -rf "$temp_dir"
}

# ============================================================================
# Test: Scheduler integration
# ============================================================================
test_scheduler_integration() {
    echo ""
    echo "=== Scheduler Integration Tests ==="

    # Need jq for scheduler tests
    if ! command -v jq &>/dev/null; then
        skip "jq not installed - skipping scheduler tests"
        return
    fi

    local temp_dir
    temp_dir=$(mktemp -d)
    local temp_tasks="$temp_dir/tasks.md"

    # Create minimal task file
    cat > "$temp_tasks" << 'EOF'
# Task List: Test
## Tasks
- [ ] **Task 1**: Test
  - Agent: general-purpose
## Questions/Blockers
None
EOF

    # Override scheduler home for test isolation
    export SCHEDULER_HOME="$temp_dir/scheduler"

    # Test schedule command
    if "$SKILL_DIR/run.sh" schedule "$temp_tasks" --cron "0 2 * * *" 2>&1 | grep -q "Scheduled"; then
        pass "run.sh schedule creates job"
    else
        fail "run.sh schedule failed"
    fi

    # Verify job was created
    if [[ -f "$SCHEDULER_HOME/jobs.json" ]] && jq -e '.["orchestrate:tasks"]' "$SCHEDULER_HOME/jobs.json" > /dev/null; then
        pass "Schedule job appears in jobs.json"
    else
        fail "Schedule job not found in jobs.json"
    fi

    # Verify cron is correct
    if jq -r '.["orchestrate:tasks"].cron' "$SCHEDULER_HOME/jobs.json" | grep -q "0 2 \* \* \*"; then
        pass "Schedule job has correct cron"
    else
        fail "Schedule job cron incorrect"
    fi

    # Test unschedule command
    if "$SKILL_DIR/run.sh" unschedule "$temp_tasks" 2>&1 | grep -q "Unscheduled"; then
        pass "run.sh unschedule removes job"
    else
        fail "run.sh unschedule failed"
    fi

    # Verify job was removed
    if ! jq -e '.["orchestrate:tasks"]' "$SCHEDULER_HOME/jobs.json" > /dev/null 2>&1; then
        pass "Job removed from jobs.json"
    else
        fail "Job still in jobs.json after unschedule"
    fi

    unset SCHEDULER_HOME
    rm -rf "$temp_dir"
}

# ============================================================================
# Test: Parallel task parsing (via preflight)
# ============================================================================
test_parallel_parsing() {
    echo ""
    echo "=== Parallel Parsing Tests ==="

    # The parallel_tasks.md fixture has tasks with Parallel: 0, 1, 1, 2
    # Preflight should pass (valid format)
    if "$SKILL_DIR/preflight.sh" "$FIXTURES_DIR/parallel_tasks.md" >/dev/null 2>&1; then
        pass "Parallel field parsed without error"
    else
        fail "Parallel field parsing failed"
    fi

    # Check that multiple tasks can have same parallel value
    local same_parallel
    same_parallel=$(grep -c "Parallel: 1" "$FIXTURES_DIR/parallel_tasks.md")
    if [[ "$same_parallel" -eq 2 ]]; then
        pass "Multiple tasks can have same Parallel value"
    else
        fail "Expected 2 tasks with Parallel: 1, got $same_parallel"
    fi
}

# ============================================================================
# Main
# ============================================================================
main() {
    echo "=========================================="
    echo "  Orchestrate Skill Integration Tests"
    echo "=========================================="
    echo ""

    local filter="${1:-all}"

    case "$filter" in
        parsing)
            test_parallel_parsing
            ;;
        parallel)
            test_parallel_parsing
            ;;
        preflight)
            test_preflight_validation
            ;;
        quality)
            test_quality_gate_detection
            ;;
        scheduler)
            test_scheduler_integration
            ;;
        all)
            test_script_availability
            test_help_command
            test_preflight_validation
            test_quality_gate_detection
            test_scheduler_integration
            test_parallel_parsing
            ;;
        *)
            echo "Unknown filter: $filter" >&2
            echo "Usage: $0 [all|parsing|parallel|preflight|quality|scheduler]" >&2
            exit 1
            ;;
    esac

    echo ""
    echo "=========================================="
    echo "  Results: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"
    echo "=========================================="

    if [[ $FAILED -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
