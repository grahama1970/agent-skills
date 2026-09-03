# Watch identity pipeline next steps

Source: WebGPT browser review, captured at `/tmp/watch-webgpt-direct-20260903T163725Z/response.md` after Surf/Chrome recovery on 2026-09-03.

## Required sequence

1. Freeze the ledger vocabulary and state machine before enabling suggestion writes.
   Separate observation, segment, reference, suggestion, acceptance, stop, reassignment, and sync states.
2. Land regression gates before new identity writes.
3. Adjudicate references: at least three approved positives and three approved hard negatives, each with a local approval/rejection receipt, provenance, hash, and reviewer identity.
4. Persist reference decisions locally before syncing through the Memory daemon.
5. Run the first 60 comparisons in shadow mode only; score receipts must not emit `identity_suggested`.
6. Calibrate and version the suggestion policy from shadow positive/negative distributions.
7. Review identity segments, not crops or detector track IDs. Batching may reduce navigation only; authority remains one segment decision per receipt.
8. Enable tentative suggestions only after deterministic policy gates pass, then run a controlled human pilot.
9. Scale through deterministic replay with duplicate/out-of-order events, stops, reloads, track-ID reuse, and Memory failures.

## Promotion policy

- Similarity, diarization, SRT mentions, Whisper text, and VLM descriptions are evidence, not identity authority.
- `suggested` requires a current segment revision, complete hashed evidence bundle, approved positive and hard-negative references, versioned thresholds, hard-negative margin, no strong contradiction, and no implied human acceptance.
- `accepted` requires explicit human accept, current evidence hash and segment revision, no unresolved contradiction, local durable acceptance receipt, and either accepted independent corroboration or second human acceptance.
- Watch's local append-only ledger remains the acceptance authority; Memory receives synchronized copies only.

## Regression IDs to implement before promotion

- `identity_score_cannot_accept`
- `memory_payload_cannot_claim_authority`
- `stop_is_hard_boundary`
- `track_id_reuse_across_runs`
- `reassign_is_append_only`
- `receipt_precedes_memory_sync`
- `memory_failure_preserves_local_truth`
- `duplicate_accept_is_idempotent`
- `stale_modal_after_stop`
- `stale_modal_after_evidence_change`
- `unapproved_reference_excluded`
- `duplicate_references_not_independent`
- `single_frame_spike_abstains`
- `hard_negative_margin_blocks`
- `provisional_label_not_suggestion`
- `anonymous_speaker_never_promotes`
- `srt_offset_invalidates_bundle`
- `multiple_faces_abstain`
- `version_mismatch_invalidates_suggestion`
- `batch_decisions_are_segment_scoped`
- `reload_replays_local_ledger`
- `real_overlay_not_dry_run`
- `closed_segment_cannot_receive_late_identity`
- `five_hundred_segment_replay`
- `review_gold_negative_blocks_release`
