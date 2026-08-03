# Dewey R3 Patch Plan

## Why this is a surgical patch, not a wholesale file replacement

The R3 creation bundle did not include the actual 10,780-line `memory/scripts/validation/monitor_sparta.py`. Replacing that file from WebGPT without the source would be unsafe. This solution therefore ships a finished helper module, tests, fixtures, and exact integration steps. The project agent should port mechanically into the live file and then run the live mutating proof.

## Contract alignment

### Dewey `UNFIXABLE_DIMENSIONS`

Keep:

```python
UNFIXABLE_DIMENSIONS = {
    "sparta_explorer_page_purpose",
    "qra_coverage_per_control",
}
```

Do not remove `qra_coverage_per_control` from this set in R3.

### monitor-sparta repair-cycle

Default `repair-cycle` should repair/diagnose only deterministic repair lanes:

- `embedding_gaps`
- `description_completeness`
- `inline_embedding_policy`

Default `repair-cycle` should skip and queue operator work for:

- `qra_coverage_per_control`
- `sparta_explorer_page_purpose`

## Mechanical integration checklist

### 1. Copy helper source

Copy:

```text
memory/scripts/validation/monitor_sparta_r3_diagnostics.py
```

into the repo next to:

```text
memory/scripts/validation/monitor_sparta.py
```

### 2. Import helper in `monitor_sparta.py`

Add near the existing imports:

```python
from monitor_sparta_r3_diagnostics import (
    build_embed_step_diagnostics,
    build_health_fix_diagnostics,
    enrich_repair_cycle_receipt,
    failed_dimensions as r3_failed_dimensions,
    qra_operator_lane_step,
    should_skip_qra_repair_lane,
    summarize_worker_wait,
    write_operator_manifest_entry,
)
```

If import order or package layout requires relative import, use the local style already used by `monitor_sparta.py`.

### 3. Embed lane receipt

Where `repair_cycle()` appends the `sparta_qdrant_embed_batch` step, enrich the step before append:

```python
raw_embed_step = {
    "id": "sparta_qdrant_embed_batch",
    "ok": embed_result.ok,
    "duration_s": embed_duration_s,
    "command": embed_command,
    "rc": embed_result.returncode,
    "stdout_tail": embed_stdout_tail,
    "stderr_tail": embed_stderr_tail,
}
steps.append(build_embed_step_diagnostics(raw_embed_step, baseline_health, health_after_embed_or_fix))
```

If `health_after_embed_or_fix` is not available at that point, pass `baseline_health` and rely on final `enrich_repair_cycle_receipt()` to normalize again after the later health check.

### 4. Health --fix receipt

Where `repair_cycle()` runs `health --fix`, keep the existing subprocess behavior, then run a fresh `health --json` and compare it with the pre-fix health:

```python
health_fix_step = {
    "id": "monitor_health_fix",
    "ok": health_fix_rc == 0,
    "duration_s": health_fix_duration_s,
    "command": health_fix_command,
    "rc": health_fix_rc,
    "stdout_tail": health_fix_stdout_tail,
    "stderr_tail": health_fix_stderr_tail,
    "summary": health_after_fix,
}
health_fix_step.update(
    build_health_fix_diagnostics(
        baseline_health,
        health_after_fix,
        attempted_dimensions=r3_failed_dimensions(baseline_health),
    )
)
steps.append(health_fix_step)
```

### 5. QRA lane skip instead of default worker launch

Replace default `create_qras_backfill` launch for `qra_coverage_per_control` with:

```python
baseline_failed = set(r3_failed_dimensions(baseline_health))
if should_skip_qra_repair_lane(baseline_failed):
    operator_queue_path = str(Path(state_dir) / "operator_queue" / "qra_coverage_per_control.jsonl")
    write_operator_manifest_entry(
        operator_queue_path,
        session_id=session_id,
        baseline_health=baseline_health,
    )
    steps.append(qra_operator_lane_step(
        baseline_health,
        operator_queue_path=operator_queue_path,
    ))
else:
    # Keep only legitimate non-QRA worker repair lanes here.
    pass
```

If the product later chooses Option A or C, that should be a new creation round with an explicit bounded scillm/Chutes lane, model pool, review state, and rollback receipt.

### 6. Worker wait normalization

When `_wait_for_monitor_workers()` returns, normalize its receipt:

```python
worker_wait = summarize_worker_wait(raw_worker_wait, started_workers=started_workers)
```

If no workers were launched, skip the wait or record:

```python
worker_wait = summarize_worker_wait({"ok": True, "waited_s": 0}, started_workers=[])
```

### 7. Final receipt guard

Immediately before returning or printing the `repair-cycle` JSON receipt:

```python
receipt = enrich_repair_cycle_receipt(receipt)
```

This catches old step shapes and guarantees R3 diagnostic fields exist in the final JSON.

## Acceptance assertions after port

The live `repair-cycle --json` receipt must satisfy:

```python
steps = receipt["steps"]
assert any(s["id"] == "sparta_qdrant_embed_batch" and "eligible_count" in s and "changed_count" in s for s in steps)
assert any(s["id"] == "monitor_health_fix" and "per_dimension_results" in s for s in steps)
assert any(s["id"] == "qra_coverage_operator_lane" for s in steps)
assert not any(s["id"] == "create_qras_backfill" and s.get("started") for s in steps), "Option B forbids default unbounded QRA worker launch"
```

## Rollback

The patch is easy to roll back:

1. Remove the import block from `monitor_sparta.py`.
2. Revert the few receipt-enrichment call sites.
3. Delete `memory/scripts/validation/monitor_sparta_r3_diagnostics.py`.
4. Delete the added R3 test and fixtures.
5. Rerun the existing Dewey unit tests and `python -m py_compile scripts/validation/monitor_sparta.py`.

Do not delete operator queue JSONL entries written during live runs unless they are explicitly marked test/session data and the operator approves cleanup.
