#!/usr/bin/env bash
# Sanity checks for /ask skill
# Tests: imports, memory skill access, basic commands, dependencies

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== /ask Sanity Checks ==="
echo ""

FAIL=0
PYTHON=(uv run --project "$SCRIPT_DIR" python)

# Test 1: Python module imports
echo "1. Python module imports..."
if PYTHONPATH="$SCRIPT_DIR/src" "${PYTHON[@]}" -c "
import ask.ask as ask_mod
import ask.argue as argue_mod
import ask.status as status_mod
import ask.doctor as doctor_mod
import ask.run_state as run_state_mod
import ask.reviewer_specs as reviewer_specs_mod
import ask.chain_specs as chain_specs_mod
import ask.chains_cli as chains_cli_mod
import ask.skills_exec as skills_exec_mod
import ask.monitor as monitor_mod
import ask.pipeline as pipeline_mod
assert hasattr(ask_mod, 'ask')
assert hasattr(argue_mod, 'run_argue')
assert hasattr(skills_exec_mod, 'run_skill')
assert hasattr(monitor_mod, 'AskMonitor')
assert hasattr(status_mod, 'show_status')
assert hasattr(doctor_mod, 'run_doctor')
assert hasattr(run_state_mod, 'create_run')
assert hasattr(reviewer_specs_mod, 'load_reviewer_specs')
assert hasattr(chain_specs_mod, 'load_chain_specs')
assert hasattr(chains_cli_mod, 'app')
assert hasattr(pipeline_mod, 'learn')
print('   All modules import OK')
"; then
    echo "   PASS"
else
    echo "   FAIL: Module imports failed"
    FAIL=1
fi

# Test 2: memory skill availability
echo ""
echo "2. memory skill..."
MEMORY_RUN="${SCRIPT_DIR}/../memory/run.sh"
if [[ -x "$MEMORY_RUN" ]]; then
    echo "   memory skill found at $MEMORY_RUN"
    echo "   PASS"
else
    echo "   WARN: memory skill not at $MEMORY_RUN"
fi

# Test 3: status command (fast, no external deps needed)
echo ""
echo "3. Status command (--json)..."
if PYTHONPATH="$SCRIPT_DIR/src" "${PYTHON[@]}" -m ask.status --scope sanity-test --json 2>/dev/null | "${PYTHON[@]}" -c "
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

# Test 4: doctor command validates runtime objects
echo ""
echo "4. Doctor command (--json)..."
if PYTHONPATH="$SCRIPT_DIR/src" "${PYTHON[@]}" -m ask.doctor --json >/tmp/ask-doctor-sanity.json 2>/dev/null || [[ -s /tmp/ask-doctor-sanity.json ]]; then
    if "${PYTHON[@]}" -c "
import json
data = json.load(open('/tmp/ask-doctor-sanity.json', encoding='utf-8'))
checks = {check['name'] for check in data.get('checks', [])}
assert 'reviewer-specs' in checks
assert 'chain-specs' in checks
assert 'artifact-root' in checks
print(f'   status: {data.get(\"status\")}')
"; then
        echo "   PASS"
    else
        echo "   FAIL: doctor output malformed"
        FAIL=1
    fi
else
    echo "   FAIL: doctor command broken"
    FAIL=1
fi

# Test 5: chains command validates saved review workflows
echo ""
echo "5. Chains command (validate --json)..."
if PYTHONPATH="$SCRIPT_DIR/src" "${PYTHON[@]}" -m ask.chains_cli validate --json | "${PYTHON[@]}" -c "
import sys, json
data = json.load(sys.stdin)
assert data.get('ok') is True
print('   chains: valid')
"; then
    echo "   PASS"
else
    echo "   FAIL: chains command broken"
    FAIL=1
fi

# Test 6: ask command (help/syntax check)
echo ""
echo "6. Ask command (syntax check)..."
if PYTHONPATH="$SCRIPT_DIR/src" "${PYTHON[@]}" -m ask.ask --help >/dev/null 2>&1; then
    echo "   --help works"
    echo "   PASS"
else
    echo "   FAIL: ask CLI --help failed"
    FAIL=1
fi

# Test 7: learn command (help/syntax check)
echo ""
echo "7. Learn command (syntax check)..."
if PYTHONPATH="$SCRIPT_DIR/src" "${PYTHON[@]}" -m ask.pipeline --help >/dev/null 2>&1 || PYTHONPATH="$SCRIPT_DIR/src" "${PYTHON[@]}" -c "from ask.pipeline import main; import sys; sys.argv=['pipeline','--help']; main()" 2>/dev/null; then
    echo "   --help works"
    echo "   PASS"
else
    echo "   FAIL: learn.py --help failed"
    FAIL=1
fi

# Test 5b: nightly command (help/syntax check)
echo ""
echo "5b. Nightly command (syntax check)..."
if PYTHONPATH="$SCRIPT_DIR/src" "${PYTHON[@]}" -m ask.nightly --help >/dev/null 2>&1; then
    echo "   --help works"
    echo "   PASS"
else
    echo "   FAIL: nightly CLI --help failed"
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
if "${PYTHON[@]}" -c "
from ask.monitor import AskMonitor
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

# Test 9: human chat examples route as documented
echo ""
echo "9. Human chat example routing..."
if PYTHONPATH="$SCRIPT_DIR/src" uv run --project "$SCRIPT_DIR" --group dev pytest -q \
    tests/test_deep_review_context.py \
    tests/test_deep_review_protocol.py \
    tests/test_deep_review_telemetry.py \
    tests/test_runtime_discipline.py \
    tests/test_human_chat_examples.py \
    tests/test_ask_cli_protocols.py \
    tests/test_review_protocols.py; then
    echo "   PASS"
else
    echo "   FAIL: human chat example routing broken"
    FAIL=1
fi

# Test 10: parallel-review DAG CLI sanity (deterministic; no live scillm call)
echo ""
echo "10. Parallel-review DAG CLI sanity..."
if PYTHONPATH="$SCRIPT_DIR/src" uv run --project "$SCRIPT_DIR" --group dev pytest -q \
    tests/test_run_state_protocol.py::test_cli_parallel_review_missing_target_pauses_with_needs_attention \
    tests/test_run_state_protocol.py::test_cli_argue_runs_two_parallel_advocates_then_judge \
    tests/test_run_state_protocol.py::test_cli_argue_verifier_failure_exits_needs_attention \
    tests/test_run_state_protocol.py::test_argue_verifier_rejects_for_without_counterargument \
    tests/test_run_state_protocol.py::test_argue_verifier_rejects_against_without_evidence_used \
    tests/test_run_state_protocol.py::test_argue_verifier_rejects_high_confidence_with_missing_evidence \
    tests/test_run_state_protocol.py::test_argue_verifier_requires_tie_breaker_for_decision_required \
    tests/test_run_state_protocol.py::test_argue_verifier_rejects_judge_evidence_not_from_advocates \
    tests/test_run_state_protocol.py::test_argue_verifier_allows_advocate_missing_evidence_as_judge_evidence \
    tests/test_run_state_protocol.py::test_cli_ask_dry_run_includes_argue_dag_options \
    tests/test_run_state_protocol.py::test_cli_parallel_review_runs_three_reviewers_then_judge \
    tests/test_run_state_protocol.py::test_cli_parallel_review_writes_code_runner_handoff_when_requested \
    tests/test_run_state_protocol.py::test_parallel_review_verifier_rejects_missing_judge \
    tests/test_run_state_protocol.py::test_parallel_review_rejects_target_outside_review_root \
    tests/test_run_state_protocol.py::test_parallel_review_rejects_symlink_target_outside_review_root \
    tests/test_run_state_protocol.py::test_parallel_review_redacts_obvious_secrets \
    tests/test_run_state_protocol.py::test_verifier_rejects_safe_verdict_for_unresolved_target \
    tests/test_run_state_protocol.py::test_verifier_rejects_safe_verdict_for_directory_only_target \
    tests/test_run_state_protocol.py::test_verifier_rejects_safe_verdict_for_truncated_target_bundle \
    tests/test_run_state_protocol.py::test_verifier_rejects_files_inspected_outside_target_bundle \
    tests/test_run_state_protocol.py::test_judge_best_and_hybrid_produce_distinct_judge_prompts \
    tests/test_run_state_protocol.py::test_parse_reviewer_output_normalizes_list_fields \
    tests/test_run_state_protocol.py::test_cli_parallel_review_verifier_failure_exits_needs_attention \
    tests/test_run_state_protocol.py::test_parallel_review_events_include_each_reviewer \
    tests/test_run_state_protocol.py::test_parallel_review_reviewer_calls_overlap \
    tests/test_run_state_protocol.py::test_parallel_review_single_reviewer_failure_preserves_artifacts \
    tests/test_run_state_protocol.py::test_cli_parallel_review_apply_fixes_prepares_code_runner_task_without_editing \
    tests/test_run_state_protocol.py::test_cli_parallel_review_apply_fixes_requires_explicit_dod_command \
    tests/test_run_state_protocol.py::test_cli_parallel_review_allowed_file_rejects_outside_repo \
    tests/test_run_state_protocol.py::test_cli_parallel_review_rejects_unknown_implementation_backend \
    tests/test_run_state_protocol.py::test_cli_code_runner_handoff_requires_parallel_review \
    tests/test_run_state_protocol.py::test_cli_parallel_review_rejects_unbounded_fanout \
    tests/test_run_state_protocol.py::test_cli_parallel_review_rejects_unknown_runner \
    tests/test_run_state_protocol.py::test_cli_parallel_review_rejects_unknown_dag_mode \
    tests/test_run_state_protocol.py::test_cli_ask_dry_run_includes_parallel_review_dag_options; then
    echo "   PASS"
else
    echo "   FAIL: parallel-review DAG CLI sanity broken"
    FAIL=1
fi

# Test 11: live /scillm parallel-review E2E (opt-in, non-mocked downstream)
echo ""
echo "11. Live /scillm parallel-review E2E..."
if [[ "${ASK_LIVE_SCILLM_E2E:-0}" == "1" ]]; then
    if PYTHONPATH="$SCRIPT_DIR/src" uv run --project "$SCRIPT_DIR" --group dev pytest -q \
        tests/test_parallel_review_live_e2e.py::test_live_parallel_review_scillm_composition; then
        echo "   PASS"
    else
        echo "   FAIL: live /scillm parallel-review E2E broken"
        FAIL=1
    fi
else
    echo "   SKIP: set ASK_LIVE_SCILLM_E2E=1 to call real /scillm"
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
