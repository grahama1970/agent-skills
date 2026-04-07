# Task List: Prompt-Lab Hardening for QRA Generation at Scale

**Created**: 2026-02-04
**Goal**: Harden prompt-lab skill for reliable 1000+ case QRA batch operations

## Context

The prompt-lab skill handles SPARTA QRA (Question-Reasoning-Answer) generation with three-tier validation (ambiguity, anchoring, grounding). While the validation architecture is solid, the skill lacks production resilience patterns needed for large-scale batch operations. This task list addresses the P0 blockers identified in the assessment.

## Crucial Dependencies (Sanity Scripts)

| Library | API/Method | Sanity Script | Status |
|---------|------------|---------------|--------|
| rapidfuzz | `fuzz.partial_ratio()` | N/A (already verified in citation_validator.py) | - |
| duckdb | `connect()`, `execute()` | N/A (SPARTA connector handles) | - |
| typer/rich | CLI framework | N/A (well-known) | - |

> No new dependencies needed - hardening uses standard library patterns.

## Questions/Blockers

None - assessment provided clear requirements.

## Tasks

### P0: Batch Resilience (Sequential - Foundation)

- [x] **Task 1**: Add batch checkpoint/resume capability
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: none
  - **Files**:
    - Create `batch_checkpoint.py` (new module)
    - Update `prompt_lab.py` test_sparta command
  - **Definition of Done**:
    - Test: Manual test - crash at case 50, resume continues from 50
    - Assertion: `--resume` flag loads checkpoint and skips completed cases

- [x] **Task 2**: Add per-case timeout with circuit breaker
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 1
  - **Files**: Update `prompt_lab.py` run_eval function
  - **Definition of Done**:
    - Test: Set `--case-timeout 1` with slow LLM mock, verify timeout triggers
    - Assertion: Cases exceeding 120s (default) are skipped with timeout error logged; batch halts after 5 consecutive timeouts

- [x] **Task 3**: Add structured error returns for agent consumption
  - Agent: general-purpose
  - Parallel: 0
  - Dependencies: Task 2
  - **Files**: Update `prompt_lab.py` exception handling
  - **Definition of Done**:
    - Test: Run with `--json` flag and trigger error, verify JSON structure
    - Assertion: All errors return `{"success": false, "error": "...", "error_code": "...", "exit_code": 1}`

### P1: Operational Transparency (Parallel after P0)

- [x] **Task 4**: Add .batch_state.json for task-monitor compatibility
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 3
  - **Files**: Update `task_monitor_client.py`
  - **Definition of Done**:
    - Test: Run test-sparta, check `.batch_state.json` exists
    - Assertion: File follows task-monitor schema with `completed`, `total`, `status`, `current_item`

- [x] **Task 5**: Add retry logic for transient LLM API errors
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 3
  - **Files**: Update `llm.py` call_llm function
  - **Definition of Done**:
    - Test: Mock 503 response, verify retry with backoff
    - Assertion: Retries 3 times with exponential backoff (1s, 2s, 4s) before failing

- [x] **Task 6**: Add heartbeat for long-running cases
  - Agent: general-purpose
  - Parallel: 1
  - Dependencies: Task 4
  - **Files**: Update `task_monitor_client.py` and `prompt_lab.py`
  - **Definition of Done**:
    - Test: Run with --verbose, verify heartbeat messages every 30s for slow cases
    - Assertion: State file updates every 30s even if case is still processing

### P2: Code Quality (Parallel after P1)

- [x] **Task 7**: Fix silent DB connection errors
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: Task 6
  - **Files**: Update `sparta_connector.py` exception handling
  - **Definition of Done**:
    - Test: Point at non-existent DB, verify warning logged
    - Assertion: DB errors logged with `console.print("[yellow]...")` instead of silent `pass`

- [x] **Task 8**: Update sanity.sh line count threshold
  - Agent: general-purpose
  - Parallel: 2
  - Dependencies: none
  - **Files**: Update `sanity.sh`
  - **Definition of Done**:
    - Test: Run `./sanity.sh`, verify it passes
    - Assertion: CLI threshold increased to 1800 lines (current is 1579, will grow with hardening)

### P3: Validation (After All Implementation)

- [ ] **Task 9**: Run 500-case stress test
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Tasks 1-8
  - **Definition of Done**:
    - Test: `./run.sh test-sparta --cases 500 --json-stream | tee stress_test_results.jsonl`
    - Assertion: Completes without crash, checkpoint file created, all gates pass or explicit failures logged

- [ ] **Task 10**: Verify resume-from-checkpoint
  - Agent: general-purpose
  - Parallel: 3
  - Dependencies: Task 9
  - **Files**: None (verification only)
  - **Definition of Done**:
    - Test: Start 50-case run, Ctrl+C at ~25, run with `--resume`, verify continues
    - Assertion: Total cases processed = 50 (not 75 from double-processing)

## Completion Criteria

- [x] All P0 tasks (1-3) complete - batch resilience in place
- [x] All P1 tasks (4-6) complete - operational transparency
- [x] All P2 tasks (7-8) complete - code quality
- [ ] Stress test (Task 9) passes without crash
- [ ] Resume test (Task 10) verifies checkpoint works
- [x] `./sanity.sh` passes

## Architecture Notes

### Checkpoint File Schema

```json
{
  "task_name": "test-sparta-100",
  "total_cases": 100,
  "completed_case_ids": ["control_001", "control_002", ...],
  "last_completed_at": "2026-02-04T10:30:00",
  "metrics_snapshot": {
    "ambiguity_rate": 0.98,
    "anchoring_rate": 0.99,
    "grounding_rate": 0.92
  }
}
```

### Error Code Schema

```python
ERROR_CODES = {
    "TIMEOUT": "Case processing exceeded deadline",
    "CIRCUIT_BREAKER": "Too many consecutive failures",
    "LLM_ERROR": "LLM API returned error",
    "DB_ERROR": "Database connection failed",
    "VALIDATION_ERROR": "Response failed validation",
    "PARSE_ERROR": "Failed to parse LLM response",
}
```

### Circuit Breaker Logic

```python
MAX_CONSECUTIVE_FAILURES = 5
consecutive_failures = 0

for case in cases:
    try:
        result = process(case)
        consecutive_failures = 0  # Reset on success
    except TimeoutError:
        consecutive_failures += 1
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            raise CircuitBreakerError("Batch halted: too many timeouts")
```

## Notes

- **Backward Compatible**: All changes are additive - existing CLI behavior unchanged without new flags
- **Env Vars**: `PROMPT_LAB_CASE_TIMEOUT_S` (default: 120), `PROMPT_LAB_MAX_CONSECUTIVE_FAILURES` (default: 5)
- **Line Count**: prompt_lab.py currently 1579 lines, may grow to ~1700 with hardening
