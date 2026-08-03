# R3: repair-cycle runs but fixes nothing — need diagnostics + QRA lane resolution

## Executive Summary

`repair-cycle` now **completes** (356s) and produces **named steps with durations**. But **zero dimensions are fixed** after a full cycle. The probe with `--embed-batch-limit 200` shows the embed lane processes 200 docs but drops all 200 (already in Qdrant). Health --fix runs 165s and changes nothing. QRA backfill is launched but the worker wait times out at 300s while the worker is still running.

This is a **diagnostic and contract resolution engagement**, not a Dewey orchestrator change. Dewey works correctly as an orchestrator. The issue is inside `monitor_sparta.py repair-cycle` — its fix lanes don't move the health needle.

## Raw repair-cycle JSON (key sections)

```json
{
  "baseline": {"passed": 23, "total": 28, "failed_dimensions": ["embedding_gaps","description_completeness","qra_coverage_per_control","inline_embedding_policy","sparta_explorer_page_purpose"]},
  "steps": [
    {
      "id": "sparta_qdrant_embed_batch",
      "ok": true, "duration_s": 6.86,
      "stdout_tail": "processed=200 synced=200 dropped=200 resume_offset=200"
    },
    {
      "id": "monitor_health_fix",
      "ok": true, "duration_s": 164.95,
      "summary": {"passed": 23, "total": 28, "failed_dimensions": ["embedding_gaps","description_completeness","qra_coverage_per_control","inline_embedding_policy","sparta_explorer_page_purpose"]}
    },
    {
      "id": "create_qras_backfill",
      "ok": true, "duration_s": 16.22,
      "started": true, "pid": 2923121
    }
  ],
  "worker_wait": {"timed_out": true, "waited_s": 300, "create_qras_running": true},
  "final": {"passed": 23, "total": 28},
  "stop_reason": "failures_remain"
}
```

## Problems to Fix

### P1: Embed lane silently no-ops
`sparta_qdrant_embed_batch` processes 200 docs but **drops all 200** — they're already in Qdrant. Yet the `embedding_gaps` dimension still reports 170 missing. These are checking different things. The step needs:
- `eligible_count` (how many docs the health check thinks are missing)
- `skip_reason` (why they were dropped)
- `changed_count` (how many new embeddings were created)
- `debug_hint` (what the health check vs embed batch disagree on)

### P2: Health --fix doesn't change dimensions
`monitor_health_fix` runs for 165s but the same 5 dims fail before and after. Need:
- Per-dimension fix result: skipped, attempted, succeeded, failed
- For `description_completeness`: how many descriptions were eligible, how many were updated
- For `inline_embedding_policy`: what exactly was checked/fixed
- For `embedding_gaps`: why the fix lane thinks 170 are missing but the embed batch found 0

### P3: Worker wait always times out
`_wait_for_monitor_workers` polls 30s and waits until `wait_timeout_s` (300s). The QRA worker is still running after 300s. Need:
- Whether the worker eventually completes
- Whether its output actually creates QRAs
- Whether the health check after the worker finishes shows improvement

### P4: QRA lane contract is ambiguous
Currently `qra_coverage_per_control` is in `UNFIXABLE_DIMENSIONS` but also has a repair lane (`create_qras_backfill`). These conflict. Resolve:
- **Option A**: QRA coverage IS repairable via scillm/Chutes DeepSeek V4 → implement a bounded QRA repair lane inside `monitor_sparta.py repair-cycle` with receipt, batch limit, model pool, review state, and rollback. Remove from UNFIXABLE_DIMENSIONS.
- **Option B**: QRA coverage is operator-required/review-gated → keep in UNFIXABLE_DIMENSIONS, remove the repair lane, short-circuit Dewey when only QRA + UX remain.
- **Option C**: Split: direct QRA coverage for native controls IS repairable, but control-to-control comparison QRAs are review-gated. Implement A for native, B for comparison.

### P5: DeepSeek V4 model pool
If QRA generation should use DeepSeek V4 (via Chutes/scillm) instead of the current `qra-deepseek-pool` (DeepSeek V3.2-TEE), configure the model pool in `monitor_sparta.py` or scillm config. Dewey should not hard-code model names — the repair receipt should log the resolved model/pool.

## Required Output

Return ONE zip named `dewey-R3-diagnostics.zip` containing:

1. **`ARCHITECTURE.md`** — updated with QRA lane contract resolution (P4)
2. **`memory/scripts/validation/monitor_sparta.py`** — repair-cycle fixes for P1-P3:
   - Each step includes `eligible_count`, `changed_count`, `skip_reason`
   - Health --fix reports per-dimension result
   - Worker wait reports whether the worker eventually completed
   - Optionally: DeepSeek V4 pool config (P5)
3. **`agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py`** — if QRA lane contract changes, update UNFIXABLE_DIMENSIONS
4. **`prompt_improvements.md`**
5. **`MANIFEST.json`**

## Non-Goals
- Do not change Dewey's orchestrator role. All repairs stay inside repair-cycle.
- Do not make Dewey call scillm directly. If scillm calls are needed, add them to repair-cycle.
- Do not replace the 10,780-line monitor_sparta.py wholesale. Only patch the repair-cycle function and its helper lanes.

## Acceptance Gates

| Gate | Evidence |
|------|----------|
| Embed lane reports eligible_count + changed_count | Raw JSON from `repair-cycle --json` shows `eligible_count` and `changed_count` in step output |
| Health --fix reports per-dimension result | Raw JSON shows per-dimension status like `{"dimension": "description_completeness", "result": "skipped", "reason": "no eligible controls"}` |
| Worker wait tracks worker completion | `worker_wait` shows whether the QRA worker completed or is still running |
| QRA lane contract resolved | ARCHITECTURE.md states which option (A/B/C) and UNFIXABLE_DIMENSIONS matches |

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260624T182332Z:92c82020>>>

Do not print anything after that marker.
