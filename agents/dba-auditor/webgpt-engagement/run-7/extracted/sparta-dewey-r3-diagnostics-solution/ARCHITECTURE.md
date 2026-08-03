# Dewey R3 Diagnostics Architecture

## Scope

This bundle is a `$create-architecture` creation artifact for the SPARTA / Dewey R3 slice. It addresses the specific state where `monitor_sparta.py repair-cycle` completes but fixes nothing. Dewey remains the nightly orchestrator. Repair behavior and diagnostics stay inside `monitor_sparta.py repair-cycle` and its helper lanes.

## Decision: QRA lane contract is Option B

R3 resolves the QRA conflict as **Option B**:

> `qra_coverage_per_control` is operator/review-gated and remains unfixable by Dewey's default nightly database repair loop.

Why this is the correct R3 contract:

1. QRA generation creates/reviews reasoning artifacts. That is not equivalent to a deterministic DB repair.
2. The R3 evidence shows an unbounded `create_qras_backfill` worker can run past the wait budget and still leave health unchanged.
3. The handoff already says `qra_coverage_per_control` and `sparta_explorer_page_purpose` are unfixable by Dewey.
4. R3 is a diagnostic and contract-resolution slice, not a new scillm/Chutes QRA generation implementation.

### Consequences

- Keep `qra_coverage_per_control` in Dewey `UNFIXABLE_DIMENSIONS`.
- Do **not** launch `create_qras_backfill` from default `repair-cycle` merely because `qra_coverage_per_control` is failing.
- Emit an explicit `qra_coverage_operator_lane` step with:
  - `eligible_count`
  - `changed_count: 0`
  - `skip_reason: operator_review_required`
  - `operator_queue_path` when available
  - a debug hint telling the operator to run bounded QRA generation/review outside Dewey and rerun `health --json`
- If old code still launches `create_qras_backfill`, R3 diagnostics must flag it as `contract_violation: true`.

## Repair-cycle receipt contract

Every repair-cycle step that can affect health must expose the following top-level fields:

```json
{
  "id": "step_id",
  "ok": true,
  "duration_s": 1.23,
  "eligible_count": 170,
  "changed_count": 0,
  "skip_reason": "all_processed_documents_already_present_in_qdrant"
}
```

Additional fields are lane-specific.

### Embed lane: `sparta_qdrant_embed_batch`

Problem observed:

```text
processed=200 synced=200 dropped=200 resume_offset=200
```

while `embedding_gaps` still reports missing embeddings.

Required normalized fields:

```json
{
  "id": "sparta_qdrant_embed_batch",
  "eligible_count": 170,
  "changed_count": 0,
  "processed_count": 200,
  "synced_count": 200,
  "dropped_count": 200,
  "skip_reason": "all_processed_documents_already_present_in_qdrant",
  "health_embed_mismatch": true,
  "debug_hint": "compare health-check eligible IDs with migrate_arango_embeddings_to_qdrant candidate query"
}
```

Interpretation:

- `eligible_count` comes from the health dimension when available.
- `changed_count` is inferred from migration counters. For the current output shape, `changed_count = max(synced - dropped, 0)`.
- If `changed_count == 0` while `embedding_gaps` remains failed, emit `health_embed_mismatch: true`.

### Health fix lane: `monitor_health_fix`

Problem observed: `health --fix` runs for ~165s and returns the same failed dimensions.

Required normalized fields:

```json
{
  "id": "monitor_health_fix",
  "status": "attempted_no_progress",
  "eligible_count": 5186,
  "changed_count": 0,
  "skip_reason": "all_attempted_dimensions_still_failing",
  "per_dimension_results": [
    {
      "dimension": "description_completeness",
      "before_status": "failed",
      "after_status": "failed",
      "result": "stuck",
      "eligible_count": 12,
      "affected_count_before": 12,
      "affected_count_after": 12,
      "changed_count": 0,
      "skip_reason": "no_records_changed"
    }
  ]
}
```

Required per-dimension result vocabulary:

| Result | Meaning |
|---|---|
| `succeeded` | Failed before, passed after |
| `stuck` | Failed before and failed after |
| `regressed` | Passed before, failed after |
| `unchanged_pass` | Passed before and passed after |
| `skipped` | Explicitly not attempted |

For unfixable dimensions:

- `qra_coverage_per_control` → `skip_reason: operator_review_required`
- `sparta_explorer_page_purpose` → `skip_reason: not_repairable_by_monitor_sparta`

### Worker wait

Default R3 behavior should avoid starting QRA workers for `qra_coverage_per_control`. Worker wait still needs a normalized receipt for any worker lanes that are legitimately started.

Required normalized fields:

```json
{
  "ok": false,
  "worker_count": 1,
  "pids": [2923121],
  "pid_files": [],
  "log_paths": [],
  "waited_s": 300,
  "timed_out": true,
  "completed": false,
  "still_running": true,
  "status": "timed_out"
}
```

## Files in this solution

### New helper source

`memory/scripts/validation/monitor_sparta_r3_diagnostics.py`

A dependency-free helper module that:

- parses embed lane counters from stdout/stderr tails
- extracts failed health dimensions from common monitor-sparta JSON shapes
- computes `eligible_count` and `changed_count` best-effort
- produces per-dimension health-fix results
- implements the Option B QRA operator-lane step
- normalizes worker-wait receipts
- can enrich a captured legacy repair-cycle JSON receipt for tests
- can append a JSONL operator-lane manifest entry

### Tests

`agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py`

Covers:

- embed lane silent no-op detection
- health-fix per-dimension diagnostics
- QRA Option B contract and old worker-launch violation flag
- worker wait `timed_out` / `still_running` reporting
- JSONL operator manifest writing

### Fixtures

- `fixtures/dewey_r3/repair_cycle_noop_input.json`
- `fixtures/dewey_r3/expected_noop_diagnostics.json`

These encode the observed R3 failure mode and expected diagnostic shape.

## Required integration into `monitor_sparta.py`

The creation bundle did not include the 10,780-line `monitor_sparta.py`; this solution therefore avoids shipping a dangerous wholesale replacement. Port the helper surgically:

1. Copy `monitor_sparta_r3_diagnostics.py` next to `monitor_sparta.py`.
2. Import the helper in `monitor_sparta.py`.
3. In `repair_cycle()`, call helper functions when appending step receipts.
4. Replace default `create_qras_backfill` launch for `qra_coverage_per_control` with `qra_operator_lane_step()` unless an explicit human/operator QRA mode is added later.
5. Before returning/printing the repair-cycle receipt, call `enrich_repair_cycle_receipt(receipt)` as a final guard.

Minimal import:

```python
try:
    from monitor_sparta_r3_diagnostics import (
        enrich_repair_cycle_receipt,
        failed_dimensions as r3_failed_dimensions,
        qra_operator_lane_step,
        should_skip_qra_repair_lane,
        summarize_worker_wait,
        write_operator_manifest_entry,
    )
except Exception:  # fail-open for import during mechanical port only; remove once tests pass
    enrich_repair_cycle_receipt = None
```

Minimal QRA lane replacement:

```python
baseline_failed = set(r3_failed_dimensions(baseline_health))
if should_skip_qra_repair_lane(baseline_failed):
    operator_path = str(Path(state_dir) / "operator_queue" / "qra_coverage.jsonl")
    write_operator_manifest_entry(operator_path, session_id=session_id, baseline_health=baseline_health)
    steps.append(qra_operator_lane_step(baseline_health, operator_queue_path=operator_path))
else:
    # existing non-QRA worker repair logic, if any
    ...
```

Minimal final enrichment:

```python
receipt = {
    "baseline": baseline_health,
    "steps": steps,
    "worker_wait": worker_wait,
    "final": final_health,
    "stop_reason": stop_reason,
}
if enrich_repair_cycle_receipt is not None:
    receipt = enrich_repair_cycle_receipt(receipt)
return receipt
```

## Isolated sanity commands

From the unzipped solution root:

```bash
python -m py_compile memory/scripts/validation/monitor_sparta_r3_diagnostics.py
python -m pytest -q agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py
```

No database, Qdrant, ArangoDB, scillm, Chutes, or live SPARTA services are required for the isolated helper tests.

## Port commands

From the actual repo workspace that has both `memory/` and `agent-skills/` checked out:

```bash
# 1. Unpack the solution somewhere outside the repo.
unzip sparta-dewey-r3-diagnostics-solution.zip -d /tmp/sparta-dewey-r3

# 2. Copy the finished helper, tests, and fixtures.
cp /tmp/sparta-dewey-r3/sparta-dewey-r3-diagnostics-solution/memory/scripts/validation/monitor_sparta_r3_diagnostics.py \
  /home/graham/workspace/experiments/memory/scripts/validation/monitor_sparta_r3_diagnostics.py

mkdir -p /home/graham/workspace/experiments/agent-skills/agents/dba-auditor/tests
cp /tmp/sparta-dewey-r3/sparta-dewey-r3-diagnostics-solution/agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py \
  /home/graham/workspace/experiments/agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py

mkdir -p /home/graham/workspace/experiments/fixtures/dewey_r3
cp /tmp/sparta-dewey-r3/sparta-dewey-r3-diagnostics-solution/fixtures/dewey_r3/*.json \
  /home/graham/workspace/experiments/fixtures/dewey_r3/

# 3. Apply the surgical monitor_sparta.py integration described in PATCH_PLAN.md.
# Do not overwrite monitor_sparta.py wholesale.

# 4. Run isolated checks.
cd /home/graham/workspace/experiments
python -m py_compile memory/scripts/validation/monitor_sparta_r3_diagnostics.py
python -m py_compile memory/scripts/validation/monitor_sparta.py
PYTHONPATH=memory/scripts/validation python -m pytest -q \
  agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py
```

## Local port verification commands

After the project agent mechanically ports the helper into `monitor_sparta.py`:

```bash
# Non-mutating health baseline.
cd /home/graham/workspace/experiments/memory
uv run python scripts/validation/monitor_sparta.py health --json | tee /tmp/dewey-r3-health-before.json

# Mutating repair-cycle proof. Only run when the local operator accepts mutation.
SPARTA_MONITOR_MUTATION_ENABLED=1 \
uv run python scripts/validation/monitor_sparta.py repair-cycle \
  --json \
  --wait \
  --wait-timeout-s 300 \
  --embed-batch-limit 200 | tee /tmp/dewey-r3-repair-cycle.json

# Verify required R3 receipt fields are present.
python - <<'PY'
import json
p = '/tmp/dewey-r3-repair-cycle.json'
receipt = json.load(open(p))
steps = receipt.get('steps', [])
assert any(s.get('id') == 'sparta_qdrant_embed_batch' and 'eligible_count' in s and 'changed_count' in s for s in steps)
assert any(s.get('id') == 'monitor_health_fix' and 'per_dimension_results' in s for s in steps)
assert any(s.get('id') == 'qra_coverage_operator_lane' for s in steps), 'QRA lane should be explicit operator skip under Option B'
assert receipt.get('r3_diagnostics', {}).get('contract', '').startswith('Option B')
print('R3 receipt shape OK')
PY
```

Do not re-enable Dewey cron until the live mutating repair-cycle receipt above shows the required R3 fields and the morning report path remains valid.

## Non-claims

- This zip does not prove 29/29 PASS.
- This zip does not prove a live mutating repair-cycle; the project agent must run that locally.
- This zip does not replace `monitor_sparta.py` wholesale because the creation bundle did not include that source file and the bundle explicitly says not to replace the 10,780-line file.
- This zip does not implement Chutes/DeepSeek V4 QRA generation. Under R3 Option B, that belongs to an explicit operator/reviewer lane, not default Dewey repair-cycle.
