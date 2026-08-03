#!/bin/bash
#
# Integration tests for orchestrate skill
# Works with both pi and claude code backends
#
# Usage:
#   ./tests/test_orchestrate.sh           Run all tests
#   ./tests/test_orchestrate.sh parsing   Run only parsing tests
#   ./tests/test_orchestrate.sh parallel  Run only parallel tests
#   ./tests/test_orchestrate.sh full-pipeline  Run plan/review/orchestrate/code-runner E2E only
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"
export AGENT_SKILLS_ARTIFACT_ROOT="${AGENT_SKILLS_ARTIFACT_ROOT:-${TMPDIR:-/tmp}/agent-skills-orchestrate-test-artifacts-$$}"

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
# Test: portable readiness command
# ============================================================================
test_pipeline_readiness_command() {
    echo ""
    echo "=== Pipeline Readiness Command Tests ==="

    if env -u VIRTUAL_ENV python "$SKILL_DIR/pipeline_readiness.py" --profile quick --json >/tmp/orchestrate-pipeline-readiness.json 2>&1; then
        if grep -q '"status":' /tmp/orchestrate-pipeline-readiness.json && grep -q 'plan-review-orchestrate-pipeline' /tmp/orchestrate-pipeline-readiness.json; then
            pass "pipeline_readiness.py quick JSON reports pipeline gates"
        else
            cat /tmp/orchestrate-pipeline-readiness.json >&2 || true
            fail "pipeline_readiness.py quick JSON missing expected readiness markers"
        fi
    else
        cat /tmp/orchestrate-pipeline-readiness.json >&2 || true
        fail "pipeline_readiness.py quick JSON failed"
    fi
    rm -f /tmp/orchestrate-pipeline-readiness.json
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

    # Test with heading-style tasks used by newer plan files
    local temp_headings
    temp_headings=$(mktemp)
    cat > "$temp_headings" << 'EOF'
# Task List: Heading Tasks

## Capability Overlap
- acknowledged

## Questions/Blockers
- None

### Task 1.1: Heading task
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: none
  - **Definition of Done**:
    - Test: test-lab/run.sh verify-task 1.1 . --domain python
    - Assertion: passes
EOF

    if "$SKILL_DIR/preflight.sh" "$temp_headings" >/dev/null 2>&1; then
        pass "preflight.sh passes for heading-style task format"
    else
        fail "preflight.sh failed for heading-style task format"
    fi

    rm -f "$temp_headings"

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
# Test: Parser edge cases
# ============================================================================
test_parser_edge_cases() {
    echo ""
    echo "=== Parser Edge Cases Tests ==="

    # Edge cases fixture should pass preflight
    if "$SKILL_DIR/preflight.sh" "$FIXTURES_DIR/edge_cases.md" >/dev/null 2>&1; then
        pass "Edge cases file passes preflight"
    else
        fail "Edge cases file failed preflight"
    fi

    # Test: Colons in task title
    if grep -q "colon: in title" "$FIXTURES_DIR/edge_cases.md"; then
        pass "Task with colon in title exists"
    else
        fail "Task with colon in title missing"
    fi

    # Test: Alternative numbering (3. instead of Task 3)
    if grep -qE '^\s*-\s*\[ \]\s*3\.' "$FIXTURES_DIR/edge_cases.md"; then
        pass "Alternative numbering format (3.) detected"
    else
        fail "Alternative numbering format not found"
    fi

    # Test: Already completed task ([x])
    if grep -qE '^\s*-\s*\[x\]' "$FIXTURES_DIR/edge_cases.md"; then
        pass "Completed task ([x]) detected"
    else
        fail "Completed task marker not found"
    fi

    # Test: Multiline description (should have multiple lines after Task 5)
    local desc_lines
    desc_lines=$(sed -n '/Task 5/,/^## /p' "$FIXTURES_DIR/edge_cases.md" | grep -c "^\s*[a-zA-Z]")
    if [[ "$desc_lines" -ge 3 ]]; then
        pass "Multiline description preserved ($desc_lines lines)"
    else
        fail "Multiline description not preserved (only $desc_lines lines)"
    fi
}

# ============================================================================
# Test: Questions/Blockers parsing variations
# ============================================================================
test_questions_variations() {
    echo ""
    echo "=== Questions/Blockers Variation Tests ==="

    # Create temp files with different question formats
    local temp_dir
    temp_dir=$(mktemp -d)

    # Test: "None" should pass
    cat > "$temp_dir/none.md" << 'EOF'
# Task List: Test
## Tasks
- [ ] **Task 1**: Test
  - Agent: explore
## Questions/Blockers
None
EOF
    if "$SKILL_DIR/preflight.sh" "$temp_dir/none.md" >/dev/null 2>&1; then
        pass "Questions: 'None' passes"
    else
        fail "Questions: 'None' should pass"
    fi

    # Test: "N/A" should pass
    cat > "$temp_dir/na.md" << 'EOF'
# Task List: Test
## Tasks
- [ ] **Task 1**: Research task
  - Agent: explore
## Questions/Blockers
- N/A
EOF
    if "$SKILL_DIR/preflight.sh" "$temp_dir/na.md" >/dev/null 2>&1; then
        pass "Questions: 'N/A' passes"
    else
        fail "Questions: 'N/A' should pass"
    fi

    # Test: Actual question should block
    cat > "$temp_dir/question.md" << 'EOF'
# Task List: Test
## Tasks
- [ ] **Task 1**: Research task
  - Agent: explore
## Questions/Blockers
- What database should we use?
EOF
    if ! "$SKILL_DIR/preflight.sh" "$temp_dir/question.md" >/dev/null 2>&1; then
        pass "Actual question blocks execution"
    else
        fail "Actual question should block execution"
    fi

    # Cleanup
    rm -rf "$temp_dir"
}

# ============================================================================
# Test: Structured plan routing/no-fallback behavior
# ============================================================================
test_structured_plans() {
    echo ""
    echo "=== Structured Plan Tests ==="

    local temp_struct
    temp_struct=$(mktemp --suffix=.json)
    local temp_root
    temp_root=$(dirname "$temp_struct")
    cat > "$temp_struct" << EOF
{
  "version": 1,
  "kind": "orchestrate-plan",
  "repo_root": "$temp_root",
  "title": "Structured test",
  "capability_overlap": ["ok"],
  "questions_blockers": ["None"],
  "lanes": [{"id": "backend"}],
  "tasks": [
    {
      "id": "t1",
      "title": "Sample task",
      "runner": "scillm",
      "backend": "gemini-2.5-flash",
      "mode": "one_shot",
      "lane": "backend",
      "prompt": "Reply with exactly: ok",
      "depends_on": [],
      "tests": ["test-lab/run.sh verify-task t1 . --domain python"],
      "definition_of_done": {"command": "true", "assertion": "passes"}
    }
  ]
}
EOF

    if "$SKILL_DIR/run.sh" run "$temp_struct" with codex --dry-run 2>&1 | grep -q "runner=scillm"; then
        pass "Structured dry-run reports runner/backend/lane"
    else
        fail "Structured dry-run missing routing details"
    fi

    if ! "$SKILL_DIR/run.sh" run "$temp_struct" with codex >/tmp/orchestrate-structured.out 2>&1; then
        if grep -q "Stabilization mode allows only" /tmp/orchestrate-structured.out; then
            pass "Structured execution blocks non-core scillm runner by default"
        else
            fail "Structured execution failed without explicit routing error"
        fi
    else
        fail "Structured execution should block direct scillm runner by default"
    fi

    rm -f "$temp_struct" /tmp/orchestrate-structured.out
}

# ============================================================================
# Test: Structured plan execution
# ============================================================================
test_structured_execution() {
    echo ""
    echo "=== Structured Execution Tests ==="

    local temp_dir
    temp_dir=$(mktemp -d)
    local temp_struct="$temp_dir/plan.json"

    cat > "$temp_struct" << EOF
{
  "version": 1,
  "kind": "orchestrate-plan",
  "repo_root": "$temp_dir",
  "title": "Structured execution test",
  "capability_overlap": ["ok"],
  "questions_blockers": ["None"],
  "execution": {"max_concurrency": 2},
  "lanes": [{"id": "lane-a"}, {"id": "lane-b"}],
  "tasks": [
    {
      "id": "t1",
      "title": "Write first artifact",
      "runner": "local",
      "mode": "deterministic",
      "lane": "lane-a",
      "cwd": "$temp_dir",
      "command": "printf 'one' > one.txt",
      "depends_on": [],
      "tests": ["test-lab/run.sh verify-task t1 . --domain python"],
      "definition_of_done": {"command": "test -f one.txt", "assertion": "one.txt exists"}
    },
    {
      "id": "t2",
      "title": "Write dependent artifact",
      "runner": "local",
      "mode": "deterministic",
      "lane": "lane-b",
      "cwd": "$temp_dir",
      "command": "test -f one.txt && printf 'two' > two.txt",
      "depends_on": ["t1"],
      "tests": ["test-lab/run.sh verify-task t2 . --domain python"],
      "definition_of_done": {"command": "test -f two.txt", "assertion": "two.txt exists"}
    }
  ]
}
EOF

    if "$SKILL_DIR/run.sh" run "$temp_struct" >/tmp/orchestrate-structured-exec.out 2>&1; then
        if [[ -f "$temp_dir/one.txt" && -f "$temp_dir/two.txt" ]]; then
            pass "Structured execution runs local tasks with dependencies"
        else
            fail "Structured execution did not produce expected artifacts"
        fi
    else
        cat /tmp/orchestrate-structured-exec.out >&2 || true
        fail "Structured execution failed for valid local plan"
    fi

    rm -rf "$temp_dir" /tmp/orchestrate-structured-exec.out
}

# ============================================================================
# Test: scillm contract compliance
# ============================================================================
test_scillm_contract_compliance() {
    echo ""
    echo "=== scillm Contract Compliance Tests ==="

    local assess_output
    assess_output=$("$SKILL_DIR/../scillm/run.sh" assess "$SKILL_DIR/structured_execute.py" --json 2>&1) || true
    if echo "$assess_output" | grep -q '"errors": 0'; then
        pass "structured_execute.py passes scillm usage assessment"
    else
        echo "$assess_output" >&2
        fail "structured_execute.py violates scillm usage assessment"
    fi

    if grep -q 'X-Caller-Skill": "orchestrate"' "$SKILL_DIR/structured_execute.py"; then
        pass "structured_execute.py sets X-Caller-Skill"
    else
        fail "structured_execute.py missing X-Caller-Skill"
    fi

    if grep -q 'reasoning_effort.*high' "$SKILL_DIR/structured_execute.py"; then
        pass "structured_execute.py forwards high reasoning for Codex"
    else
        fail "structured_execute.py missing Codex reasoning_effort"
    fi

    if ! grep -q '../scillm/run.sh" complete' "$SKILL_DIR/run.sh"; then
        pass "run.sh does not call removed scillm complete command"
    else
        fail "run.sh still calls removed scillm complete command"
    fi
}

# ============================================================================
# Test: real /orchestrate -> /code-runner entrypoint with deterministic backend
# ============================================================================
test_code_runner_mock_e2e() {
    echo ""
    echo "=== Code-Runner Mock E2E Tests ==="

    if "$SCRIPT_DIR/run_orchestrate_code_runner_mock_e2e.sh" >/tmp/orchestrate-code-runner-mock-e2e.out 2>&1; then
        pass "real orchestrate -> code-runner mock E2E preserves patch-only boundary"
    else
        cat /tmp/orchestrate-code-runner-mock-e2e.out >&2 || true
        fail "real orchestrate -> code-runner mock E2E failed"
    fi

    rm -f /tmp/orchestrate-code-runner-mock-e2e.out
}

# ============================================================================
# Test: full plan -> review-plan -> orchestrate -> code-runner pipeline
# ============================================================================
test_full_pipeline_mock_e2e() {
    echo ""
    echo "=== Full Pipeline Mock E2E Tests ==="

    if "$SCRIPT_DIR/run_plan_review_orchestrate_code_runner_mock_e2e.sh" >/tmp/plan-review-orchestrate-code-runner-mock-e2e.out 2>&1; then
        pass "plan -> review-plan -> orchestrate -> code-runner mock E2E gates and executes correctly"
    else
        cat /tmp/plan-review-orchestrate-code-runner-mock-e2e.out >&2 || true
        fail "plan -> review-plan -> orchestrate -> code-runner mock E2E failed"
    fi

    rm -f /tmp/plan-review-orchestrate-code-runner-mock-e2e.out
}

# ============================================================================
# Test: external-project adoption canary
# ============================================================================
test_external_project_adoption_smoke() {
    echo ""
    echo "=== External Project Adoption Smoke Tests ==="

    if "$SCRIPT_DIR/run_external_project_adoption_smoke.sh" >/tmp/external-project-adoption-smoke.out 2>&1; then
        pass "external project adoption smoke fails fast then succeeds after baseline commit"
    else
        cat /tmp/external-project-adoption-smoke.out >&2 || true
        fail "external project adoption smoke failed"
    fi

    rm -f /tmp/external-project-adoption-smoke.out
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
            test_parser_edge_cases
            ;;
        parallel)
            test_parallel_parsing
            ;;
        preflight)
            test_preflight_validation
            test_questions_variations
            test_structured_plans
            test_structured_execution
            test_scillm_contract_compliance
            ;;
        quality)
            test_quality_gate_detection
            ;;
        scheduler)
            test_scheduler_integration
            ;;
        edge)
            test_parser_edge_cases
            test_questions_variations
            ;;
        full-pipeline)
            test_full_pipeline_mock_e2e
            test_external_project_adoption_smoke
            ;;
        all)
            test_script_availability
            test_pipeline_readiness_command
            test_help_command
            test_preflight_validation
            test_quality_gate_detection
            test_scheduler_integration
            test_parallel_parsing
            test_parser_edge_cases
            test_questions_variations
            test_structured_plans
            test_structured_execution
            test_scillm_contract_compliance
            test_code_runner_mock_e2e
            test_full_pipeline_mock_e2e
            test_external_project_adoption_smoke
            ;;
        *)
            echo "Unknown filter: $filter" >&2
            echo "Usage: $0 [all|parsing|parallel|preflight|quality|scheduler|edge|full-pipeline]" >&2
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
