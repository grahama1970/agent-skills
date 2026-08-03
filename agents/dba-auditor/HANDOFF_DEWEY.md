# Handoff Report: Dewey (dba-auditor) Nightly Monitor-Sparta Repair Loop

**Timestamp**: 2026-06-24T19:00:00Z  
**Active Agent**: OpenCode  
**Project Root**: `/home/graham/workspace/experiments/agent-skills/agents/dba-auditor`

## 1. Project Overview

- **Ecosystem**: Python + shell + ArangoDB + scillm/Chutes
- **Core Purpose**: Dewey is the DBA Auditor cron agent that runs `/monitor-sparta repair-cycle` nightly until 29/29 PASS. It reads coverage gaps from monitor-sparta health checks and attempts to fix them through the repair-cycle pipeline.
- **Key repos**: `agent-skills` (Dewey scripts in `agents/dba-auditor/`), `memory` (monitor_sparta.py, services.yaml)

## 2. Current State

### What is working
- **Reading coverage gaps**: √ `health --json` completes in ~65s and shows 23/29 PASS with clear failing dimensions
- **Per-cycle logging**: √ `dewey.log` shows START, BUDGETS, BASELINE, CYCLE_START, REPAIR_STEP, STOP with timestamps and durations
- **repair-cycle completes**: √ Now finishes in ~356s (was timing out before R2 timeout fix)
- **Named step output**: √ Steps now include `id` (e.g. `sparta_qdrant_embed_batch`, `monitor_health_fix`, `create_qras_backfill`)
- **Unfixable dim classification**: √ `sparta_explorer_page_purpose` and `qra_coverage_per_control` correctly tagged
- **Morning report**: √ Written on every run with stop_reason, final health, remaining failures
- **Unit tests**: 19/19 passing
- **`once` and `start` subcommands**: Both functional
- **Calibrated timeouts**: `--repair-timeout-s`, `--wait-timeout-s`, `--embed-batch-limit` all configurable

### What is broken / not proven

1. **repair-cycle fixes nothing**: Despite completing, zero health dimensions improve after a full cycle. Same 5 dims failing before and after: `embedding_gaps`, `description_completeness`, `inline_embedding_policy`, `qra_coverage_per_control`, `sparta_explorer_page_purpose`

2. **Embed lane silently no-ops**: `sparta_qdrant_embed_batch` with `--embed-batch-limit 200` processes 200 docs but drops all 200 (already in Qdrant). Yet `embedding_gaps` dimension reports 170 missing. Health check and embed batch are checking different things — no `eligible_count`, `changed_count`, or `skip_reason` in step output.

3. **Health --fix doesn't progress**: `monitor_health_fix` runs for 165s but the same 5 dims are still failing after. No per-dimension fix result (skipped/attempted/succeeded/failed).

4. **Worker wait always times out**: `create_qras_backfill` launches a worker then `_wait_for_monitor_workers` polls until wait_timeout_s (300s). The worker is still running after 300s. No evidence the worker ever completes or creates QRAs.

5. **QRA lane contract ambiguous**: `qra_coverage_per_control` is in both `UNFIXABLE_DIMENSIONS` AND has a `create_qras_backfill` repair lane. These conflict. Need to decide: is it repairable via scillm/Chutes or operator-required?

6. **Step output missing detail**: Steps have `id` and `duration_s` but not `eligible_count`, `changed_count`, `command`, `rc`, `skip_reason`, or before/after failed dimensions.

## 3. What WebGPT Already Provided (R1 + R2)

- R1: `dewey-P0-solution.zip` — initial orchestrator with stall tracking, health diff, morning report
- R2: `dewey-P0-r2-fixes.zip` — fixed timeout calibration, unfixable dim handling, db_session_command flags
- Both ported and tested. 19/19 unit tests pass.

## 4. R3 WebGPT Result And Port Status

R3 was submitted through `$create-architecture` to the Sparta Explorer WebGPT tab and returned:

- `webgpt-engagement/run-7/sparta-dewey-r3-diagnostics-solution.zip`
- SHA256: `3d89ec00a9fb361abe459aaea9e8387ae934870cd2bf6d53a6cc3d1474fb8b31`
- Required files present: `MANIFEST.json`, `ARCHITECTURE.md`, `prompt_improvements.md`, helper source, tests, fixtures, patch plan, commands.

R3 contract decision:

- **Option B**: `qra_coverage_per_control` is operator/review-gated and remains unfixable by Dewey default repair-cycle.
- Dewey must not launch unbounded `create_qras_backfill` workers from default `repair-cycle`.
- `repair-cycle` should emit an explicit `qra_coverage_operator_lane` step and write an operator queue entry.

Ported locally:

- `memory/scripts/validation/monitor_sparta_r3_diagnostics.py`
- `memory/scripts/validation/monitor_sparta.py` imports the helper, enriches embed/health-fix steps, emits `qra_coverage_operator_lane`, skips worker wait when no workers started, and adds final `r3_diagnostics`.
- `agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py`
- `/home/graham/workspace/experiments/fixtures/dewey_r3/*.json`

Proof:

- `python -m py_compile scripts/validation/monitor_sparta.py scripts/validation/monitor_sparta_r3_diagnostics.py` PASS.
- `uv run pytest -q agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py` PASS: 5/5.
- `uv run pytest -q agent-skills/agents/dba-auditor/tests/test_dewey_monitor_sparta_nightly.py` PASS: 19/19.
- Live `health --json`: 24/29 PASS, five failures remain.
- Live guarded `repair-cycle`: exited `1` because failures remain, but R3 receipt shape passed:
  - step ids: `sparta_qdrant_embed_batch`, `monitor_health_fix`, `qra_coverage_operator_lane`
  - `create_qras_backfill`: absent
  - `worker_wait.status`: `no_workers`
  - `r3_diagnostics.contract`: `Option B: QRA coverage is operator/review-gated and remains unfixable by Dewey`

Live proof artifacts:

- `webgpt-engagement/run-7/dewey-r3-health-before.json`
- `webgpt-engagement/run-7/dewey-r3-repair-cycle.json`
- `webgpt-engagement/run-7/dewey-r3-live-proof.sha256`

Remaining live failures after R3:

1. `embedding_gaps`
2. `description_completeness`
3. `qra_coverage_per_control`
4. `inline_embedding_policy`
5. `sparta_explorer_page_purpose`

## 4.1 Inline Embedding Policy Slice

User clarified the compliance rule: all embeddings are in Qdrant and there
should be **no** embeddings in ArangoDB.

Patch:

- `memory/scripts/validation/sparta_repair_manifests.py`
- `strip_synced_vectors()` now strips inline vector fields from SPARTA Arango
  collections regardless of per-document Qdrant metadata. The old implementation
  only stripped documents with `qdrant_point_id != null` and
  `semantic_sync_state == "synced"`, which left legacy inline vectors behind.

Live mutation:

```bash
SPARTA_MONITOR_MUTATION_ENABLED=1 \
uv run python scripts/validation/sparta_repair_manifests.py strip-synced-vectors \
  --collection sparta_controls \
  --collection sparta_url_knowledge \
  --batch-size 5000 \
  --limit 0 \
  --output /home/graham/workspace/experiments/agent-skills/agents/dba-auditor/webgpt-engagement/run-8/inline-vector-strip.json
```

Proof:

- Before: `inline_embedding_policy` failed with `total_inline_embedding_arrays=54871`
  - `sparta_controls=11473`
  - `sparta_url_knowledge=43398`
- Mutation stripped:
  - `sparta_controls=11473`
  - `sparta_url_knowledge=43398`
- After: `inline_embedding_policy` passed with `total_inline_embedding_arrays=0`

Artifacts:

- `webgpt-engagement/run-8/inline-vector-strip.json`
- `webgpt-engagement/run-8/inline-health-before.json`
- `webgpt-engagement/run-8/inline-health-after.json`
- `webgpt-engagement/run-8/inline-vector-proof.sha256`

## 4.2 Qdrant Metadata Backfill Slice

After inline vectors were removed, `embedding_gaps` expanded because the health
check correctly stopped counting inline Arango vectors as embeddings. User
clarified that embeddings live in Qdrant, so the next Dewey slice repaired
Arango metadata for points that already existed in Qdrant.

Patch:

- `memory/scripts/validation/sparta_repair_manifests.py`
- Added `backfill-qdrant-metadata`.
- The command computes the canonical Qdrant point id for missing Arango docs,
  checks that the point exists in Qdrant, then writes only metadata:
  `qdrant_collection`, `qdrant_point_id`, `embedding_model`,
  `embedding_version`, `text_hash`, and `semantic_sync_state="synced"`.
- It does **not** create embeddings and does **not** write inline vectors.

Proof:

- Before metadata repair:
  - `sparta_controls=11643`
  - `sparta_url_knowledge=43398`
- Sample run updated 100/100 controls and reduced `sparta_controls` to 11543.
- Full passes:
  - controls pass 1: updated 5804, missing Qdrant points 170
  - url knowledge pass 1: updated 42709, missing Qdrant points 0
  - controls pass 2: updated 5328, missing Qdrant points 170
  - url knowledge pass 2: updated 689, missing Qdrant points 0
  - controls pass 3: updated 241, missing Qdrant points 170
- After metadata repair:
  - `embedding_gaps` still fails, but only `sparta_controls=170`
  - all remaining samples are `MID_*` controls whose expected Qdrant points are absent

Artifacts:

- `webgpt-engagement/run-9/embedding-health-before.json`
- `webgpt-engagement/run-9/qdrant-metadata-controls-sample.json`
- `webgpt-engagement/run-9/embedding-health-sample-after.json`
- `webgpt-engagement/run-9/qdrant-metadata-controls-full.json`
- `webgpt-engagement/run-9/qdrant-metadata-url-knowledge-full.json`
- `webgpt-engagement/run-9/qdrant-metadata-controls-pass2.json`
- `webgpt-engagement/run-9/qdrant-metadata-url-knowledge-pass2.json`
- `webgpt-engagement/run-9/qdrant-metadata-controls-pass3.json`
- `webgpt-engagement/run-9/embedding-health-after-pass3.json`
- `webgpt-engagement/run-9/qdrant-metadata-proof.sha256`

Next Dewey invocation:

- Repair only the remaining 170 `MID_*` controls by creating/restoring their
  missing Qdrant points or classifying them as non-embeddable with a concrete
  source reason. Do not rerun broad metadata backfill unless health shows new
  metadata-only gaps.

## 4.3 Missing Qdrant Points Slice

After metadata backfill converged, `embedding_gaps` still reported
`sparta_controls=170`. Sample inspection showed these were `MID_*` EMB3D
mitigation controls with real descriptions and no matching Qdrant point.

Patch:

- `memory/scripts/migrate_arango_embeddings_to_qdrant.py`
- `--needs-embed-only` now matches the health-check definition exactly:
  no inline embedding and no synced Qdrant metadata. Previously it selected all
  docs without Qdrant metadata, including docs still covered by inline vectors,
  which made Dewey process the wrong rows.

Live invocation:

```bash
uv run python scripts/migrate_arango_embeddings_to_qdrant.py \
  --collection sparta_controls \
  --needs-embed-only \
  --limit 200 \
  --batch-size 200 \
  --embed-batch-size 16
```

Result:

- `processed=170`
- `synced=170`
- `pending=0`
- `failed=0`
- `dropped=0`

Post-health proof:

- `embedding_gaps`: PASS, `All documents have embeddings`
- `inline_embedding_policy`: PASS, `total_inline_embedding_arrays=0`
- Overall monitor-sparta: `26/29`

Artifacts:

- `webgpt-engagement/run-10/embed-missing-mid-controls.json`
- `webgpt-engagement/run-10/embedding-health-after-embed.json`
- `webgpt-engagement/run-10/embed-missing-mid-proof.sha256`

Remaining failures after this slice:

1. `description_completeness`
2. `qra_coverage_per_control`
3. `sparta_explorer_page_purpose`

## 4.4 Description Completeness Slice

`description_completeness` failed on exactly 12 pipe-composite placeholder
controls. These were not real source controls with missing descriptions; they
were composite IDs such as `T0883|T1581|T1101|T0860|T1650`.

Pre-check:

- Pipe-composite controls: 12
- Description-completeness failures: 12
- QRA refs: 12, already `review_status="rejected"` and
  `normal_coverage_excluded=true`
- Relationship refs: 12, all self-reference relationships

Patch:

- `memory/scripts/validation/sparta_repair_manifests.py`
- Added `quarantine-composite-placeholder-controls`.
- The command does not delete records and does not invent descriptions.
- It marks the 12 composite placeholder controls as deprecated,
  non-QRA-eligible, and coverage-excluded, and rejects/excludes their
  self-reference relationships.
- The artifact includes rollback state for touched controls and relationships.

Live invocation:

```bash
SPARTA_MONITOR_MUTATION_ENABLED=1 \
uv run python scripts/validation/sparta_repair_manifests.py \
  quarantine-composite-placeholder-controls \
  --output /home/graham/workspace/experiments/agent-skills/agents/dba-auditor/webgpt-engagement/run-11/quarantine-composite-placeholder-controls.json
```

Result:

- `candidate_count=12`
- `control_updated=12`
- `relationship_updated=12`

Post-health proof:

- `description_completeness`: PASS, `All non-deprecated controls have real descriptions`
- `embedding_gaps`: PASS
- `inline_embedding_policy`: PASS
- Overall monitor-sparta: `27/29`

Artifacts:

- `webgpt-engagement/run-11/description-health-before.json`
- `webgpt-engagement/run-11/quarantine-composite-placeholder-controls.json`
- `webgpt-engagement/run-11/description-health-after.json`
- `webgpt-engagement/run-11/description-quarantine-proof.sha256`

Remaining failures after this slice:

1. `qra_coverage_per_control`
2. `sparta_explorer_page_purpose`

## 4.5 Dewey Once Supervisor Check

After the project-agent-supervised data repair slices, Dewey was invoked using
its actual supported CLI:

```bash
SPARTA_MONITOR_MUTATION_ENABLED=1 \
uv run python agents/dba-auditor/scripts/dewey_overnight_run.py once \
  --session-id post-data-fixes \
  --wait-timeout-s 300 \
  --embed-batch-limit 200
```

Result:

- Dewey baseline: `26/28`
- Failed dimensions:
  - `qra_coverage_per_control`
  - `sparta_explorer_page_purpose`
- `repair-cycle` duration: `0.688s`
- Final: `26/28`
- Exit code: `1` because monitor is not pass.

Interpretation:

- Dewey no longer churns on the fixed deterministic data bugs.
- Remaining failures are not Dewey data-repair lanes:
  - `qra_coverage_per_control` is operator/review-gated by R3 Option B.
  - `sparta_explorer_page_purpose` is a Sparta Explorer UI/product contract slice.
- Cron may treat those two owner slices as `OPERATOR_REQUIRED`, not as a
  repairable failure loop. Do not claim `PASS` until monitor-sparta health is
  actually green.

Artifacts:

- `webgpt-engagement/run-12/dewey-once-post-data-fixes.receipt.json`
- `webgpt-engagement/run-12/dewey-once-post-data-fixes.sha256`

## 4.6 R3 Repair-Cycle And Cron Contract Fix

Additional project-agent fixes on 2026-06-24:

- `monitor_sparta.py repair-cycle` no longer launches
  `create_qras_backfill` by default when `qra_coverage_per_control` fails.
- It writes an explicit `qra_coverage_operator_lane` step and appends
  `qra_operator_lane.jsonl`.
- It enriches repair-cycle receipts with R3 diagnostics before printing or
  writing artifacts.
- It skips worker waiting when no workers were started and reports
  `worker_wait.status="no_workers"`.
- It restores missing local helpers for repair-cycle health subprocesses and
  parses the top-level `health --json` payload rather than nested detail JSON.
- `dewey_nightly_cron.sh` now calls the supported CLI shape:
  `start --session-id "${RUN_ID}"`, with `DEWEY_SESSION_BASE`.
- `start --skip-scans` now passes `--skip-scans` through to
  `render_overnight_morning_report.py`.

Focused tests:

```bash
uv run pytest -q \
  tests/health/test_monitor_sparta_repair_cycle_helpers.py \
  /home/graham/workspace/experiments/agent-skills/agents/dba-auditor/tests/test_dewey_monitor_sparta_nightly.py \
  /home/graham/workspace/experiments/agent-skills/agents/dba-auditor/tests/test_dewey_r3_monitor_sparta_diagnostics.py
```

Result: `13 passed`.

Live repair-cycle proof:

```bash
SPARTA_MONITOR_MUTATION_ENABLED=1 \
uv run python scripts/validation/monitor_sparta.py repair-cycle \
  --artifact-dir /home/graham/workspace/experiments/agent-skills/agents/dba-auditor/webgpt-engagement/run-13/live-repair-cycle-artifacts \
  --embed-batch-limit 1 \
  --wait-timeout-s 1 \
  --json \
  > /home/graham/workspace/experiments/agent-skills/agents/dba-auditor/webgpt-engagement/run-13/live-repair-cycle.json
```

Result:

- Exit code: `1` because failures remain.
- Baseline/final: real `26/29`, not parser-failed `0/0`.
- Step ids: `monitor_health_fix`, `qra_coverage_operator_lane`.
- `create_qras_backfill`: absent.
- `worker_wait.status`: `no_workers`, `worker_count=0`.
- Contract violations: none.

Live Dewey once proof after the monitor patch:

```bash
SPARTA_MONITOR_MUTATION_ENABLED=1 \
uv run python agents/dba-auditor/scripts/dewey_overnight_run.py once \
  --session-id operator-only-smoke-20260624T-after-r3patch \
  --wait-timeout-s 300 \
  --embed-batch-limit 200
```

Result:

- Exit code: `10`.
- `repair_exit_code`: `null`.
- Baseline/final: Dewey-scored `26/28`; `monitor_sparta_mutation_default`
  waived because mutation mode was intentionally enabled for the smoke.
- `terminal_status`: `OPERATOR_REQUIRED`.
- Remaining Dewey-scored dimensions:
  - `qra_coverage_per_control`
  - `sparta_explorer_page_purpose`

Artifacts:

- `webgpt-engagement/run-13/live-repair-cycle.json`
- `webgpt-engagement/run-13/live-repair-cycle-artifacts/repair_cycle.json`
- `webgpt-engagement/run-13/live-repair-cycle-artifacts/qra_operator_lane.jsonl`
- `/mnt/storage12tb/skills/review-db/outputs/dewey-sessions/operator-only-smoke-20260624T-after-r3patch/once_receipt.json`

SHA256:

- `ab7ccde010159ae81bedb6d09595aa70dff9725e19cb8ab5c3677583e9d1d5bd`
  `live-repair-cycle.json`
- `052c205c3c7d2805be28be8515f89ceef9a0d92d18d6ecc7bada96f086f4e84e`
  `qra_operator_lane.jsonl`
- `f36dcf1e886fd7598ce083d5bc0e365f42a971433d0216342ce7aecbf8f5b956`
  `once_receipt.json`

Live Dewey `start` proof:

```bash
SPARTA_MONITOR_MUTATION_ENABLED=1 \
uv run python agents/dba-auditor/scripts/dewey_overnight_run.py start \
  --session-id start-operator-smoke-20260624T2048Z \
  --skip-scans \
  --max-cycles 1 \
  --wait-timeout-s 300 \
  --embed-batch-limit 200
```

Result:

- Exit code: `0`.
- Steps: `backup_first`, `monitor_sparta_iteration`, `morning_report`.
- Run receipt:
  `/mnt/storage12tb/skills/review-db/outputs/dewey-overnight-runs/start-operator-smoke-20260624T2048Z/run_receipt.json`.
- `terminal_status`: `OPERATOR_REQUIRED`.
- `monitor_pass`: `false`.
- Iteration cycle 1 stopped before repair with
  `stop_reason="operator_required_only"`.
- Morning report latest files were refreshed on `2026-06-24 16:58:04`.

SHA256:

- `eb9cde6582603fad5d0d35d0640d5f8ab6e63ced41b298ae303da61efc3808a4`
  `run_receipt.json`
- `4900a58a010364d28da5c17961218263760421a573bb5f7012c5b8dd5e807a5b`
  `coverage_iteration.json`
- `56d30c6aff6992f9b5f274b281211641b7b2b6380fc41349e8aa36f1671b586d`
  `backup_receipt.json`

Proof scope:

- `mocked: yes` for unit tests covering repairable-to-operator transitions and
  cron-facing `start` terminal handling.
- `live: yes` for current operator-only monitor-sparta state, R3 repair-cycle
  receipt shape, and Dewey `once` operator terminal state.
- Live `start` is proven for the current operator-only state.
- Still not live-proven: a future run with a newly introduced repairable data
  defect. The current live database has no repairable Dewey-scored failures
  left.

## 5. Key Files

| File | Purpose |
|------|---------|
| `agent-skills/agents/dba-auditor/scripts/dewey_overnight_run.py` | Dewey orchestrator (start/once) |
| `agent-skills/agents/dba-auditor/scripts/dewey_nightly_cron.sh` | Cron wrapper with flock |
| `agent-skills/agents/dba-auditor/scripts/db_repair_session.py` | Backup/verify/revert session |
| `agent-skills/agents/dba-auditor/scripts/sanity_live_repair_cycle_smoke.sh` | Live smoke test |
| `agent-skills/agents/dba-auditor/tests/test_dewey_monitor_sparta_nightly.py` | Dewey terminal/retry/cron contract tests |
| `memory/scripts/validation/monitor_sparta.py` | 10,780-line health check + repair-cycle |
| `memory/.agents/services.yaml` | Cron service config |
| `agent-skills/agents/dba-auditor/webgpt-engagement/run-3/creation-bundle.md` | R3 bundle (current WebGPT engagement) |

## 6. Next Steps

1. Treat `qra_coverage_per_control` and `sparta_explorer_page_purpose` as
   operator/product-owned until separate accepted repair slices exist.
2. Do not claim monitor-sparta `PASS` while those dimensions fail.
3. If a future health run shows a repairable Dewey-scored failure
   (`embedding_gaps`, `description_completeness`, `inline_embedding_policy`,
   relationship/framework manifest failures), invoke Dewey and expect one
   bounded repair-cycle, persisted artifacts, session verify, and retry until
   `PASS`, `OPERATOR_REQUIRED`, or `REPAIRABLE_FAILURES_REMAIN`.
4. Run a full cron-style `start` proof when an operator accepts backup/report
   cost, or when a repairable failure reappears naturally.

## 7. WebGPT Tab

- **Original stale tab ID**: 837355531
- **Completed R3 tab ID**: 837356331
- **Completed R3 URL**: `https://chatgpt.com/g/g-p-6a22b674b76881918809ceac4396a409-sparta-explorer/c/6a3c2db3-a390-83ea-bec5-82d8f295ce14`
- **Desktop**: 2
- **Project**: sparta
