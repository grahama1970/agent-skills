Diagnosis

The defect is not merely that the prior reviewer made a bad judgment. The pipeline has no enforceable identity-continuity proof object between three existing boundaries:

The locked character sheets are copied into Phase 07 but are never qualified for internal identity consistency.

Storyboard frames are reviewed independently against those sheets, using model prose as the decisive signal, without deterministic face metrics or adjacent-frame comparisons.

The provider return is accepted from a manually authored contact-sheet receipt that contains aggregate PASS labels but no per-frame face detections, reference similarities, adjacent-appearance comparisons, or policy-bound thresholds.

The existing Phase 07 machinery is the correct starting point: _promote_reviewer_accepted_frames() already calls _attach_identity_continuity_review() and refuses promotion on a failed result. However, _run_identity_continuity_review() currently performs a one-frame VLM comparison, and the stored receipt primarily preserves the VLM’s JSON verdict and prose. The active example receipt demonstrates that shape: it records verdict: PASS and descriptive identity notes, but not the frame hash, reference hashes, face crops, embedding scores, adjacent-frame scores, or a fused deterministic decision.

The finalizer currently extracts 12 frames and explicitly says its contact-sheet receipt does not prove persona identity, yet downstream code later hardcodes step 36 and step 42 as passing. The final-acceptance producer likewise writes accepted: true and post_kling_continuity_passed: true rather than deriving those fields from a validated identity receipt.

Implementation decision

Use a hybrid gate:

A pinned deterministic face detector, alignment model, face-quality model, and face-embedding model provide repeatable measurements.

The existing VLM review provides semantic assignment and visual-context checks: which detected face is Embry or Kai, whether the face is actually readable, whether a crop is occluded, and whether a visually obvious identity change exists.

Neither system can independently produce PASS.

Any mismatch from either system fails.

Any missing, ambiguous, low-quality, or conflicting evidence blocks or fails according to the declared coverage requirement.

An ArcFace-compatible embedding is appropriate because ArcFace is designed to create discriminative identity representations on a normalized angular space. A face-quality signal such as MagFace is useful for preventing low-quality crops from being treated as reliable identity evidence. Neither supplies a universal production threshold: the decision thresholds must be calibrated and frozen for the exact model and project evidence rather than copied from another benchmark.
CVF Open Access
+2
CVF Open Access
+2

No model downloads may occur during a gate run. Detector, quality, and embedding model files must already exist locally, have pinned versions and SHA-256 digests, and be named in the gate policy. Missing models produce BLOCKED_IDENTITY_BACKEND_UNAVAILABLE.

1. Exact files and insertion points
1.1 Shared identity gate

Add:

skills/persona-dream/scripts/identity_continuity_gate.py

skills/persona-dream/contracts/identity_continuity_policy.v1.json

skills/persona-dream/schemas/identity_continuity_policy.v1.schema.json

skills/persona-dream/schemas/identity_reference_qualification.v1.schema.json

skills/persona-dream/schemas/identity_temporal_continuity_review.v1.schema.json

identity_continuity_gate.py owns only:

Safe resolution and hashing of identity images.

Face detection, alignment, quality measurement, and embedding.

Reference-set qualification.

Per-frame and temporal-sequence identity classification.

Fusion of deterministic and VLM findings.

Receipt creation and verification.

It must not generate images, submit provider requests, mutate video, or write final acceptance.

Expose these functions:

load_identity_policy(path)
qualify_reference_sets(...)
review_single_identity_image(...)
review_temporal_identity_sequence(...)
verify_reference_qualification_receipt(...)
verify_temporal_identity_receipt(...)

Raw embedding vectors should remain in local .npz artifacts. Receipts and Memory store only:

Model identity and model-file hashes.

Embedding artifact path and hash.

Face crop hashes.

Similarities and classifications.

Policy hash.

Do not put vector arrays in Memory documents.

1.2 Reuse the Phase 07 VLM machinery

Modify:

skills/persona-dream/scripts/phase07_storyboard_tau_node.py

Make the existing image-plus-reference VLM call reusable without duplicating its transport code:

identity_vlm_review(
    *,
    image_path,
    annotated_image_path,
    detected_faces,
    reference_assets,
    required_characters,
    review_context,
    identity_review_policy,
) -> structured_result

_run_identity_continuity_review() becomes a compatibility wrapper around the shared hybrid gate. Retain _attach_identity_continuity_review() and the existing fail-closed promotion behavior.

Reference qualification insertion

Inside _ensure_optimum_identity_contract(), immediately after both locked reference assets have been copied and hashed:

qualification = qualify_reference_sets(
    Embry=[references/01-embry_character_sheet.jpg],
    Kai=[references/02-kai_character_sheet.png],
    policy=identity_policy,
    vlm_callback=identity_vlm_review,
)
write receipts/identity_reference_qualification.v1.json
attach receipt relative path, hash, policy hash, and status to storyboard_packet
return blockers unless qualification.status == PASS_IDENTITY_REFERENCE_QUALIFIED

The current frame-generation path extends blockers from _ensure_optimum_identity_contract() but can continue into its generation loop. Add an immediate fail-closed return at that point when the identity-reference qualification has not passed. The relevant call currently occurs before frame generation.

Storyboard consumption insertion

At the beginning of _promote_reviewer_accepted_frames():

Resolve the qualification receipt from the packet.

Recompute its SHA-256.

Recompute the locked character-sheet hashes.

Verify the policy hash and model hashes.

Require PASS_IDENTITY_REFERENCE_QUALIFIED.

Then, for every candidate frame, _attach_identity_continuity_review() must require:

Qualified references.

Deterministic face findings.

Structured VLM findings.

Fused per-character classifications.

Frame and reference hashes.

Adjacent accepted-frame comparison where an earlier accepted appearance exists.

No accepted storyboard frame may be created from a stale or missing qualification receipt.

1.3 Provider-request guard

Modify:

skills/persona-dream/scripts/phase11_payload_binding.py

skills/persona-dream/scripts/phase11_canonical_common.py

skills/persona-dream/scripts/validate_phase11_canonical_live_request.py

Add:

require_identity_reference_qualification(context)

Call it at the start of build_payload_binding(), before _media_lock_assets() and before character-reference records are assembled.

The Phase 11 binder currently locates Embry and Kai character-sheet artifacts and inserts them directly into provider element packs without proving that those sheets passed an identity-set qualification.

The guard must verify:

Qualification receipt is indexed.

Receipt path is revision-relative.

Receipt, policy, Embry sheet, and Kai sheet hashes recompute.

Receipt status is PASS_IDENTITY_REFERENCE_QUALIFIED.

Character IDs and reference artifact IDs match the exact files used in the provider payload.

Every required accepted storyboard frame has a passing hybrid identity receipt under the same policy hash.

Bind these fields into the payload-binding and canonical-media receipts:

identity_reference_qualification_relative_path
identity_reference_qualification_sha256
identity_policy_sha256
identity_embedding_model_sha256
identity_reviewed_storyboard_frame_hashes

validate_phase11_canonical_live_request.py must independently repeat this verification and emit BLOCKED_PHASE11_IDENTITY_QUALIFICATION_REQUIRED on any mismatch. This prevents a manually edited canonical request from bypassing the binder.

1.4 Post-provider temporal review

Modify:

skills/persona-dream/scripts/finalize_provider_return.py

Add an identity action and insert it into all after build_frames() and before audio muxing:

frames
-> identity temporal review
-> stop if identity failed
-> dialogue/delivery validation
-> mux

Add:

build_identity_review(revision_root, request_sha256)

It reads:

The exact provider-return MP4 hash.

frames_manifest.json.

All 12 sampled frame hashes.

The qualified reference receipt and locked references.

Storyboard beat time ranges and identity-readability requirements.

It writes:

identity_temporal_continuity_review.v1.json

Face crops and annotated detection frames.

Hashed embedding artifacts.

A replacement post_kling_continuity_review_receipt.v2.json.

The current post_kling_continuity_review_receipt.v1.json remains immutable historical evidence. Version 2 must name its SHA-256 in supersedes.

finalize_provider_return.py all must terminate nonzero immediately when temporal identity review fails. It must not proceed to an acceptance-producing path.

1.5 Dialogue synchronization and delivery

Modify:

skills/persona-dream/scripts/finalize_provider_return.py

skills/persona-dream/scripts/persist_voice_handoff_memory.py

Add schemas:

skills/persona-dream/schemas/dialogue_storyboard_sync_receipt.v1.schema.json

skills/persona-dream/schemas/voice_delivery_review_receipt.v1.schema.json

Before build_mux() calculates delay_ms, derive the allowed dialogue window from the canonical SB_003 storyboard record and compare it with:

phase_06_script/timed_transcript.json

voice_handoff_plan.json

Render receipt.

Actual audio_mix_receipt.dialogue_delay_ms.

The current plan binds the Kai line to start_s: 0.0, despite its later-story cue, and the muxer directly converts that value to a zero-millisecond delay.

Write:

dialogue_storyboard_sync_receipt.v1.json

with:

storyboard_packet_path/hash
timed_transcript_path/hash
voice_handoff_plan_path/hash
panel_id
panel_time_range
line_id
speaker
line_start_s
line_end_s
rendered_audio_duration_s
required_overlap_s
actual_overlap_s
mix_delay_ms
expected_mix_delay_ms
status
blocking_findings

The delivery receipt must include:

engine
engine_version
engine_binary_or_model_sha256
canonical_spoken_text
synthesis_input_text
paralinguistic_tags_requested
paralinguistic_tags_supported
paralinguistic_tags_applied
voice_direction
resolved_delivery
render_receipt_path/hash
rendered_wav_path/hash
status
blocking_findings
claims

Chatterbox Turbo supports native paralinguistic tags; therefore a non-neutral line contract can require a supported tag and prove that the exact tagged input reached the Turbo model. Tag presence is technical contract evidence, not proof of subjective acting quality.
GitHub
+1

persist_voice_handoff_memory.py currently promotes step 37 from render_status and step 38 from file existence, non-silence, and mux hashes. It does not check storyboard timing or resolved delivery. Require both new receipts before either step can pass.

1.6 Final acceptance and Memory derivation

Modify:

skills/persona-dream/scripts/persist_immutable_goal_steps.py

Add schema:

skills/persona-dream/schemas/final_acceptance_reconciliation_receipt.v1.schema.json

Replace the hardcoded statuses for steps 36–42 with:

derive_late_step_states(revision_root)

Required derivation:

step 36:
  PASS only if post_kling v2 passes
  AND identity reference qualification passes
  AND temporal identity receipt passes

step 37:
  PASS only if voice delivery and dialogue sync pass

step 38:
  PASS only if dialogue sync, delivery, mix, mux, ffprobe,
  and audibility receipts all pass and bind the same output hash

step 39:
  BLOCKED when any 36-38 state is non-passing

step 40:
  BLOCKED when any required pipeline step is non-passing

step 42:
  PASS only when steps 1-41 pass and 42 exact Memory records reread

42/42 must mean “42 states persisted,” never “42 states passed.”

For the present return, write an append-only reconciliation receipt:

phase_13_final_acceptance/final_acceptance_reconciliation_receipt.v1.json

Required fields:

schema
status: BLOCKED_FINAL_ACCEPTANCE
accepted: false
run_id
revision_id
request_body_sha256
provider_mp4_sha256
superseded_final_acceptance_path
superseded_final_acceptance_sha256
superseded_post_kling_receipt_path
superseded_post_kling_receipt_sha256
blocking_receipts [{path, sha256, status}]
affected_steps
prior_step_states
replacement_step_states
memory_exact_reread_count
observed_at
claims.proves
claims.does_not_prove

Do not delete the old passing receipt. The reconciliation receipt explicitly supersedes it.

Upsert the same deterministic Memory keys with replacement states and exactly reread them:

Step 36: FAIL_IDENTITY_TEMPORAL_CONTINUITY

Step 37: FAIL_VOICE_DELIVERY_CONTRACT

Step 38: FAIL_DIALOGUE_STORYBOARD_SYNC

Step 39: BLOCKED_STALE_FINAL_REPORT

Step 40: BLOCKED_NONPASSING_GATES

Step 42: BLOCKED_FINAL_ACCEPTANCE

Each replacement record must preserve:

supersedes.status
supersedes.observed_at
supersedes.artifact_hashes
invalidation_receipt_path
invalidation_receipt_sha256
1.7 Return read model

Modify:

skills/persona-dream/server/src/stages.ts

Focused tests under skills/persona-dream/server/tests/**

buildProviderReturnStage() currently changes its display status when the review string contains FAIL, but its effectiveState still becomes accepted_current whenever the return belongs to the active revision.

Change the decision to:

accepted_current only when:
  post_kling v2 status == PASS_POST_KLING_CONTINUITY_REVIEW
  identity temporal status == PASS_IDENTITY_TEMPORAL_CONTINUITY
  final acceptance reconciliation is absent or accepted == true
  required audio sync/delivery receipts pass for the displayed muxed output

For this return:

status = RETURN_RECEIVED_IDENTITY_FAILED
acceptance.state = blocked
effectiveState = blocked_current
failureOrGap includes EMBRY_IDENTITY_DRIFT_00_03

Continue exposing the MP4 as evidence. Do not present it as accepted.

2. Receipt schemas
identity_reference_qualification.v1

Top-level required fields:

schema
status
run_id
revision_id
policy_path
policy_sha256
characters
cross_character_checks
blocking_findings
mocked
live
observed_at
claims

Per character:

character_id
reference_assets [
  artifact_id
  relative_path
  sha256
  size_bytes
  media_type
]
detector_model
detector_model_sha256
quality_model
quality_model_sha256
embedding_model
embedding_model_sha256
embedding_metric
embedding_artifact_path
embedding_artifact_sha256
detections [
  face_id
  source_asset_sha256
  bbox
  landmarks
  detector_score
  face_height_px
  quality_score
  readability
  aligned_crop_path
  aligned_crop_sha256
]
readable_face_count
non_readable_face_count
pairwise_similarity_matrix
identity_cluster_count
vlm_request_sha256
vlm_response_sha256
vlm_findings
result
blockers

A named character passes only when all readable faces form one qualified identity cluster and the VLM finds no readable identity inconsistency.

identity_temporal_continuity_review.v1

Required fields:

schema
status
run_id
revision_id
request_body_sha256
source_video_relative_path
source_video_sha256
frames_manifest_relative_path
frames_manifest_sha256
reference_qualification_path
reference_qualification_sha256
policy_sha256
frame_count
frames
transitions
character_results
coverage_results
blocking_findings
mocked
live
observed_at
claims

Per frame and character:

frame_index
timestamp_seconds
frame_path
frame_sha256
expected_presence
readability_required
face_id
bbox
crop_path
crop_sha256
detector_score
quality_score
readability_class
embedding_artifact_sha256
similarity_to_expected_reference
similarity_to_other_reference
expected_vs_other_margin
similarity_to_previous_readable_appearance
embedding_classification
vlm_classification
fused_classification
blocking_findings
post_kling_continuity_review_receipt.v2

Require all existing beat subgates plus:

identity_reference_qualification_receipt
identity_reference_qualification_sha256
identity_temporal_continuity_receipt
identity_temporal_continuity_sha256
identity_policy_sha256
identity_subgate_status
supersedes

A top-level PASS is schema-invalid unless identity_subgate_status is PASS_IDENTITY_TEMPORAL_CONTINUITY.

3. Classification rules
Classification	Meaning	Gate effect
READABLE_MATCH	Face meets readability policy; embedding and VLM both match the expected qualified character; adjacent comparison passes.	May contribute to PASS.
READABLE_MISMATCH	Either deterministic comparison or VLM finds a wrong identity, character swap, or adjacent discontinuity.	Immediate FAIL.
READABLE_INDETERMINATE	Evidence is readable, but similarity lies in the uncertainty band or systems disagree without a hard mismatch.	BLOCKED; never PASS.
NON_READABLE_ALLOWED	Face is below readability threshold in a beat where face readability is explicitly optional.	Recorded coverage only; does not prove identity.
NON_READABLE_REQUIRED	Face is too small, hidden, blurred, profile-only, or absent in a beat requiring identity readability.	Immediate FAIL.
NOT_PRESENT_ALLOWED	Character is explicitly not required in that sampled frame.	Neutral.
NOT_PRESENT_REQUIRED	Required character is missing.	Immediate FAIL.
MULTIPLE_CANDIDATES	More than one plausible face maps to the same required character.	FAIL unless the policy explicitly resolves a unique track.
REFERENCE_INCONSISTENT	A readable reference face forms another identity cluster or fails the expected reference identity.	Reference qualification FAIL; storyboard and Phase 11 block.
REFERENCE_INSUFFICIENT_COVERAGE	Fewer than the policy-required readable reference views exist.	Reference qualification FAIL.

A NON_READABLE_ALLOWED sample cannot satisfy a minimum readable-coverage requirement.

4. Hybrid fusion and threshold policy

No similarity constant should be embedded directly in Python. The policy file contains exact numeric thresholds and their calibration provenance:

detector_min_confidence
minimum_face_height_px
minimum_quality_score
minimum_reference_readable_faces
reference_match_threshold
reference_mismatch_threshold
adjacent_match_threshold
other_identity_margin
maximum_readable_gap_seconds
calibration_artifact_path
calibration_artifact_sha256
detector_model_sha256
quality_model_sha256
embedding_model_sha256

Calibration must demonstrate a separable operating interval for the exact pinned model:

positive_floor = minimum accepted same-character calibration similarity
negative_ceiling = maximum known different-character calibration similarity

require negative_ceiling < positive_floor
require configured mismatch_threshold >= negative_ceiling
require configured match_threshold <= positive_floor
require mismatch_threshold < match_threshold

Missing calibration, overlapping positive/negative distributions, changed model hashes, or changed policy hashes block the gate.

Fusion:

embedding MATCH when:
    expected_similarity >= match_threshold
    AND adjacent_similarity >= adjacent_match_threshold
    AND expected_similarity - strongest_other_similarity >= other_identity_margin

embedding MISMATCH when:
    expected_similarity <= mismatch_threshold
    OR strongest_other_similarity >= expected_similarity
    OR adjacent_similarity <= mismatch_threshold

otherwise embedding INDETERMINATE

Final classification:

if reference set is not qualified:
    FAIL REFERENCE_INCONSISTENT

if readability is required and no readable face exists:
    FAIL NON_READABLE_REQUIRED

if deterministic == MISMATCH or VLM == MISMATCH:
    FAIL READABLE_MISMATCH

if deterministic == MATCH and VLM == MATCH:
    PASS READABLE_MATCH

otherwise:
    BLOCK READABLE_INDETERMINATE

The VLM’s own verdict: PASS is ignored by the aggregate decision function. It supplies structured observations only.

5. Pseudocode
Reference qualification
Python
Run
def qualify_reference_sets(reference_assets, policy, vlm_callback):
    assert_models_and_policy_hashes(policy)

    character_results = {}

    for character_id, assets in reference_assets.items():
        readable = []
        non_readable = []

        for asset in assets:
            assert_relative_contained_file(asset.path)
            assert_sha256_and_size(asset)

            detections = detect_align_and_score_faces(asset.path, policy)

            for detection in detections:
                crop = persist_aligned_crop(detection)
                if not meets_readability_policy(detection, policy):
                    non_readable.append(record_non_readable(detection, crop))
                    continue

                embedding = embed_face(crop, policy.embedding_model)
                readable.append(record_readable(detection, crop, embedding))

        if len(readable) < policy.minimum_reference_readable_faces:
            character_results[character_id] = fail(
                "REFERENCE_INSUFFICIENT_COVERAGE"
            )
            continue

        similarities = pairwise_cosine(readable.embeddings)
        clusters = cluster_with_policy_threshold(similarities, policy)
        vlm = vlm_callback(
            full_assets=assets,
            numbered_face_crops=readable.crops,
            expected_character=character_id,
        )

        blockers = []
        if len(clusters) != 1:
            blockers.append("REFERENCE_INCONSISTENT")
        if any(score <= policy.reference_mismatch_threshold
               for score in similarities.readable_pairs):
            blockers.append("REFERENCE_INCONSISTENT")
        if vlm.has_readable_identity_inconsistency:
            blockers.append("REFERENCE_INCONSISTENT")

        character_results[character_id] = result(blockers, readable, vlm)

    cross = compare_character_clusters(character_results)
    if cross.maximum_similarity violates policy.other_identity_margin:
        add_global_blocker("REFERENCE_CHARACTER_CLUSTERS_COLLIDE")

    status = PASS only when every character passes and no global blocker
    persist_hashed_embeddings_and_receipt()
    return receipt
Provider-return temporal continuity
Python
Run
def review_temporal_identity_sequence(
    frames_manifest,
    reference_qualification,
    storyboard_packet,
    policy,
    vlm_callback,
):
    require_reference_qualification_pass(reference_qualification)
    frames = load_and_rehash_all_frames(frames_manifest)
    beat_requirements = identity_coverage_from_storyboard(storyboard_packet)

    previous_readable = {}
    frame_results = []
    transitions = []
    blockers = []

    for frame in chronological(frames):
        detections = detect_align_and_score_faces(frame.path, policy)
        annotated = write_numbered_detection_overlay(frame, detections)

        vlm = vlm_callback(
            image_path=frame.path,
            annotated_image_path=annotated,
            detected_faces=detections,
            qualified_references=reference_qualification,
            beat=beat_for_timestamp(frame.timestamp),
        )

        for character in required_characters:
            requirement = beat_requirements.at(frame.timestamp, character)
            candidate = fuse_assignment(
                character,
                detections,
                reference_qualification,
                vlm,
                policy,
            )

            if candidate is None or not candidate.readable:
                classification = classify_non_readable(requirement)
                record(classification)
                if classification == NON_READABLE_REQUIRED:
                    blockers.append(character_missing_code(...))
                continue

            reference_scores = compare_to_reference_cluster(candidate, character)
            other_scores = compare_to_other_clusters(candidate, character)
            adjacent_score = (
                cosine(candidate.embedding, previous_readable[character].embedding)
                if character in previous_readable else None
            )

            deterministic = classify_embedding(
                reference_scores,
                other_scores,
                adjacent_score,
                policy,
            )
            semantic = classify_vlm(vlm, character, candidate.face_id)
            fused = fuse_fail_closed(deterministic, semantic)

            if fused != READABLE_MATCH:
                blockers.append(identity_blocker(character, frame, fused))

            if character in previous_readable:
                transitions.append(
                    transition_record(previous_readable[character], candidate)
                )

            previous_readable[character] = candidate
            frame_results.append(full_hashed_record(...))

    coverage_results = enforce_minimum_readable_coverage(
        frame_results,
        beat_requirements,
    )
    blockers.extend(coverage_results.blockers)

    status = (
        PASS_IDENTITY_TEMPORAL_CONTINUITY
        if not blockers
        else FAIL_IDENTITY_TEMPORAL_CONTINUITY
    )
    return persist_receipt(status, frame_results, transitions, blockers)
Final acceptance derivation
Python
Run
def derive_late_step_states(revision_root):
    identity = require_temporal_identity_receipt(revision_root)
    post_kling = require_post_kling_v2(revision_root)
    dialogue_sync = require_dialogue_sync_receipt(revision_root)
    delivery = require_delivery_receipt(revision_root)
    mux = verify_mux_chain(revision_root)

    step36 = PASS if (
        identity.status == PASS_IDENTITY_TEMPORAL_CONTINUITY
        and post_kling.status == PASS_POST_KLING_CONTINUITY_REVIEW
    ) else FAIL_IDENTITY_TEMPORAL_CONTINUITY

    step37 = PASS if (
        dialogue_sync.status == PASS_DIALOGUE_STORYBOARD_SYNC
        and delivery.status == PASS_VOICE_DELIVERY_CONTRACT
    ) else FAIL_VOICE_HANDOFF_CONTRACT

    step38 = PASS if (
        step37 is PASS
        and mux.all_hashes_and_receipts_pass
    ) else FAIL_FINAL_ASSEMBLY_CONTRACT

    step39 = PASS if steps36_38 pass else BLOCKED_STALE_FINAL_REPORT
    step40 = PASS if all required steps pass else BLOCKED_NONPASSING_GATES
    step42 = PASS only if step40 passes and exact_memory_count == 42

    return replacement_states
6. Current-return invalidation

For the current active MP4, run only local analysis and persistence operations:

Qualify the locked Embry and Kai reference sets.

Run the temporal gate over all 12 existing sampled frames.

Persist the detected Embry mismatch around the first shot-to-close-shot transition as:

EMBRY_IDENTITY_DRIFT_00_03

The finding must name:

Both frame indices and timestamps.

Both frame hashes.

Both face-crop hashes.

Similarity to the Embry reference cluster.

Adjacent similarity.

VLM structured findings.

Policy and model hashes.

Write post_kling_continuity_review_receipt.v2.json with a failed identity subgate.

Write failed dialogue-sync and delivery receipts from the existing plan and render evidence.

Write final_acceptance_reconciliation_receipt.v1.json with accepted: false.

Upsert and exactly reread the replacement Memory states.

Refresh the Return read model.

The MP4, contact sheet, frame files, old receipts, and old Memory evidence remain as immutable history.

7. Focused tests
Python tests

Add:

skills/persona-dream/tests/test_identity_reference_qualification.py

skills/persona-dream/tests/test_identity_temporal_continuity.py

skills/persona-dream/tests/test_final_acceptance_identity_invalidation.py

Update:

Existing Phase 07 reviewer tests.

Finalizer tests.

Voice-handoff Memory tests.

Phase 11 payload-binding tests.

Required cases:

Two consistent Embry reference views and two consistent Kai views pass.

One readable wrong-person pane in the Embry sheet produces REFERENCE_INCONSISTENT.

Only one readable face produces REFERENCE_INSUFFICIENT_COVERAGE.

Changed reference hash invalidates a prior qualification receipt.

Storyboard frame with embedding mismatch and VLM PASS fails.

Storyboard frame with embedding match and VLM mismatch fails.

Uncertainty-band result blocks and cannot be promoted.

Required unreadable SB_001 face fails.

Explicitly optional non-readable wide SB_004 face is recorded but does not satisfy coverage.

Provider frames with consistent identity pass.

Fixture reproducing the active 0–3 second Embry change fails with EMBRY_IDENTITY_DRIFT_00_03.

Missing adjacent readable comparison fails verification.

Mutating any frame, crop, embedding artifact, policy, or response hash invalidates the receipt.

Phase 11 payload compilation blocks when reference qualification is missing, failed, stale, or unindexed.

VLM prose saying PASS cannot compensate for missing deterministic evidence.

Dialogue at zero seconds fails SB_003 synchronization.

Dialogue in the canonical SB_003 window with matching mix delay passes.

Neutral delivery or missing required tag fails.

Supported, contract-approved tag with matching render receipt passes the technical delivery gate.

Exact Memory reread remains 42 while final acceptance is blocked, proving count and pass-state are separate.

Server tests

Add focused cases to skills/persona-dream/server/tests/read-model.test.ts:

Failed identity receipt yields RETURN_RECEIVED_IDENTITY_FAILED.

Failed return remains playable as evidence.

Failed return has acceptance.state === 'blocked'.

Failed return has effectiveState === 'blocked_current'.

Old passing receipt cannot override a newer reconciliation receipt.

A valid v2 receipt plus passing reconciliation produces accepted state.

Missing identity receipt fails closed rather than inheriting the v1 manual pass.

8. Minimal no-provider-call repair order

Freeze and hash the existing MP4, frames manifest, 12 frames, contact sheet, old continuity receipt, old final acceptance receipt, and current Memory states.

Add the policy, schemas, and shared hybrid identity gate.

Insert reference qualification into Phase 07 and the Phase 11 guards.

Run reference qualification against the existing locked sheets.

Run temporal identity review against the existing provider frames.

Persist the expected EMBRY_IDENTITY_DRIFT_00_03 failure and v2 failed post-Kling receipt.

Validate the existing audio evidence and persist:

DIALOGUE_STORYBOARD_SYNC_FAILED

KAI_DELIVERY_FLAT

Reconcile final artifacts and upsert the corrected Memory states.

Verify all 42 keys exactly reread, with steps 36, 37, 38, 39, 40, and 42 non-passing.

Verify the Return read model exposes the current MP4 as blocked evidence, not accepted output.

Optionally rerender and remux the Kai line locally at the correct SB_003 time with an approved supported delivery tag. This can clear the two audio blockers but cannot clear the identity failure.

Stop. Do not compile, authorize, or submit another Kling request.

The successful outcome of this repair is not a newly accepted video. It is a correctly invalidated current return, qualified references for future work, enforceable storyboard and provider preconditions, and a post-provider identity gate that cannot be upgraded by advisory prose alone.
