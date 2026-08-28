# Gates: persona-dream Phase 11→16 provider-return finish

OWNS: `skills/persona-dream/**`

Scope: consume and validate the existing active successor Kling/Fal return. No new provider submit is allowed for request `sha256:97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4` because the attempt ledger already records one completed live call.

- [x] PD11-1: active revision request compiles without using the stale external checkout path
  CHECK: `./skills/persona-dream/run.sh compile-phase11-canonical-live-request --run-root skills/persona-dream/reports/pipeline-complete --json | tee /tmp/phase11-compile-after-status-update.json`
  EXPECT: `status=PASS_PHASE11_CANONICAL_COMPILER`, `request_body_sha256=sha256:97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4`
  EVIDENCE: `/tmp/phase11-compile-after-status-update.json`

- [x] PD11-2: existing provider effect is reconciled; no blind Kling retry
  CHECK: read `phase11_provider_return_envelope.v1.json`, `attempt_ledger.v1.json`, and bytes for `provider_return.mp4`
  EXPECT: `status=PASS_PHASE11_PROVIDER_RETURN_RECEIVED`, `submitted=true`, `actual_provider_call_attempts=1`, `request_id=019f77f0-a75b-7012-8cc1-fbc24f58f388`, MP4 sha `sha256:59b9ff3155d6ba9d0b90d795bafe7b84cc4e10849db08299217b65d61e211fff`
  EVIDENCE: `skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3/phase_11_submit_return/provider_return/97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4/phase11_provider_return_envelope.v1.json`

- [x] PD11-3: post-return visual/audio acceptance is read from superseding receipts
  CHECK: read `post_return_acceptance_receipt.v2.json`, `post_kling_continuity_review_receipt.v2.json`, and `step37_38_audio_final_assembly_receipt.v2.json`
  EXPECT: `ACCEPTED_AGENT_LEVEL`, `PASS_POST_KLING_CONTINUITY_REVIEW`, `PASS_AUDIO_FINAL_ASSEMBLY`
  EVIDENCE: `skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3/phase_11_submit_return/provider_return/97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4/post_return_acceptance_receipt.v2.json`

- [x] PD12-15: cognitive loop and canonical memory persistence are proven by current receipts and live readback
  CHECK: read `watch_gauntlet/59b9ff3155d6/cognitive_loop/cognitive_loop_receipt.json` and query Memory `/list` for `_key=dream_dream_successor_943b01ecd9a3`
  EXPECT: `status=PASS_COGNITIVE_LOOP`, `canonical_dream_memory_written=true`, Memory readback `FOUND`
  EVIDENCE: `skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3/watch_gauntlet/59b9ff3155d6/cognitive_loop/cognitive_loop_receipt.json`

- [x] PD16-1: failed semantic recall query is recorded in pipeline-self-repair ledger
  CHECK: `./skills/pipeline-self-repair/run.sh record-failure ... --ledger skills/persona-dream/local/unlazy/finish-phase11-kling/replay_ledger.jsonl --json | tee /tmp/persona-dream-phase16-record-failure.json`
  EXPECT: `status=RECORDED_NEEDS_TRIAGE`, immutable goal comparison `PASS_COMPARED_TO_IMMUTABLE_GOAL`
  EVIDENCE: `skills/persona-dream/local/unlazy/finish-phase11-kling/replay_ledger.jsonl`

- [x] PD16-2: Phase 16 semantic recall gate repaired without mutating canonical dream/persona records
  CHECK: `uv run --project skills/persona-dream pytest skills/persona-dream/tests/test_phase16_semantic_recall_contract.py skills/persona-dream/tests/test_phase16_strict_traversal.py -q`
  EXPECT: `5 passed`
  EVIDENCE: command output in this run

- [x] PD16-3: Phase 16 full behavior evaluation passes after repair
  CHECK: `./skills/persona-dream/run.sh phase16-behavior-evaluation --json | tee /tmp/persona-dream-phase16-behavior-eval-after-query-repair.json`
  EXPECT: `overall_status=PASS`, `6_semantic_recall=true`, `7_multihop_traversal=true`, `8_grounded_use_and_synthetic_distinction=true`, `9_identity_consistency=true`
  EVIDENCE: `skills/persona-dream/reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3/phase_16_behavior_evaluation/phase16_behavior_evaluation_receipt.v1.json`

- [x] PD-GOAL-OPEN: remaining research-goal gates are explicit and not claimed complete
  CHECK: `jq '.next_step.blocked_by' skills/persona-dream/CURRENT_STATUS.json`
  EXPECT: human listener collection/signature and PCTOM held-out benefit remain listed until actually run
  EVIDENCE: `/tmp/persona-dream-final-blockers.json` -> `human_responses_complete:0/20`, `signed_human_interpretation_missing`, `pctom_heldout_benefit_unrun`
