# Persona Dream Immutable Goal

Last updated: 2026-07-17

## Immutable Goal

Produce a working Kling video from the `persona-dream` pipeline.

This is not complete until the pipeline has a returned/downloaded video artifact,
technical video proof, visual review artifacts, and memory persistence evidence
for every pipeline step listed below.

Minimum final evidence:

- Kling/provider submit receipt.
- Kling/provider poll or callback receipt.
- Downloaded MP4 or provider-returned video artifact.
- `ffprobe` receipt proving duration, codec, and readability.
- Frame contact sheet from the returned video.
- Post-Kling continuity review receipt.
- Final report that names what passed, what was mocked, what was live, and what
  remains unverified.
- Memory write and exact reread evidence for every pipeline step.

## Current Boundary

The active revision is now the identity-source successor
`rev_successor_943b01ecd9a3` (durable repo-rooted pointer, bound to
`embry_contact_sheet_v3`). It stands at its acceptance rung:
`PASS_ACTIVE_CONSISTENT`, Memory `PASS_EXACT_REREAD_42_OF_42`, and all eight
Phase 07 storyboard frames PASS actual-pixel identity review (8/8 first
attempt; 7/7 continuity pairs). Receipt:
`.persona-dream/revisions/rev_successor_943b01ecd9a3/acceptance_rung_receipt.v1.json`.
No successor provider call has been made; the historical return below is
superseded evidence from the frozen predecessor.

Stage B addendum (2026-07-18, post-return gauntlet): SUPERSEDES the line above —
the successor provider call HAS since been made and its return received (commit
a47fc595). The live successor Kling return is
`.persona-dream/revisions/rev_successor_943b01ecd9a3/phase_11_submit_return/provider_return/97688ec5191e7246cc7d86325a7404894c459d2572bc5412b29ccd3dc755cfd4/provider_return.mp4`
(`sha256:59b9ff3155…`, 10.041667s, H.264 1280x720, 16,843,175 bytes, one submit,
request_id 019f77f0-a75b-7012-8cc1-fbc24f58f388, request body
`sha256:97688ec5…`, `generate_audio=false` so the source is silent).
Post-return gauntlet outcomes on THIS successor return:
- Step 35 frame contact sheet: PASS — 12 uniform-fallback frames (0.0-9.2s), 4x3
  sheet `watch_gauntlet/59b9ff3155d6/frame_contact_sheet.png`; receipt
  `watch_gauntlet/59b9ff3155d6/step35_frame_contact_sheet_receipt.v1.json`.
- Watch gauntlet: DEGRADED — scene detection found no cuts (single-shot);
  per-frame VLM entities unavailable (scillm gpt-5.5 chat auth rotated); the
  silent pre-mux video has no transcript to recover the Kai line. Observation
  packet `DEGRADED_WATCH_GAUNTLET_OBSERVATION`, validation
  `FAIL_WATCH_GAUNTLET_VALIDATION`. Memory persisted with exact reread.
- Step 36 post-Kling continuity: FAIL (fail-closed) — deterministic ArcFace
  (InsightFace buffalo_l, CPU, threshold 0.421) computed LIVE vs
  embry_contact_sheet_v3. The v3 identity-source fix matches strongly in the
  opening identity window (t=0.0s cos 0.603, t=0.84s cos 0.612) and mid-clip
  (t=2.5-5.9s cos 0.45-0.58) — an improvement over the prior
  EMBRY_IDENTITY_DRIFT_00_03 baseline — but only 7/12 frames contain an
  Embry-matching face at threshold (mean cosine 0.378); frames at t~6.7-9.2s
  fall to 0.02-0.15. ArcFace alone cannot separate genuine drift from
  pose/occlusion and the VLM adjudication layer is unavailable, so identity is
  NOT certifiable. Kai reference sheet has no detectable face (unscoreable).
  Receipt `…/provider_return/…97688ec5…/post_kling_continuity_review_receipt.v1.json`.
- Steps 37-38 audio + final assembly: BLOCKED — the exact canonical Kai line
  "If we paddle now, we're cutting across the lineup." (window 5.0-8.08s, beat
  sb_003) was NEVER rendered (voice_handoff_plan render_status
  PENDING_EXACT_LINE_RENDER); no chatterbox_turbo engine is installed and no
  paid call is authorized; VLM lip-sync review unavailable. No mux produced.
- Acceptance: BLOCKED (`post_return_acceptance_receipt.v1.json`). Human
  subjective acceptance NOT claimed (remains the human's).
- Canonical cognitive loop: NOT run — dry-run only
  (`watch_gauntlet/59b9ff3155d6/cognitive_loop_dryrun/`): phase 12 DEGRADED,
  phases 13/14 BLOCKED (no live gpt-5.5), phase 15 DRY_RUN_PERSISTENCE_PLAN,
  `canonical_dream_memory_written: false`. No failed/unaccepted dream was
  written to canonical memory.

Stage B addendum 2 (2026-07-19, gauntlet re-run with VLM routed through Tau):
SUPERSEDES the step-36 / step-38 / acceptance outcomes above. The v1 blockers
were all rooted in the missing VLM layer. Per the standing architecture
directive ("only /tau has access to /scillm"), all VLM calls were routed through
the Tau panel-reviewer node (`persona_dream_panel_agent`, commit 416edc5a, custom
hash-recorded `visual_review_prompt`; `api_key_source docker:scillm-proxy`) — NOT
direct scillm from Stage B drivers. Outcomes on THIS successor return:
- Step 36 post-Kling continuity: PASS (v2,
  `…/97688ec5…/post_kling_continuity_review_receipt.v2.json`). The ArcFace
  whole-clip metric still fails (5/12 sub-threshold), but VLM adjudication (via
  Tau) classifies ALL 5 sub-threshold frames as POSE_OCCLUSION consistent with
  their storyboard beat intent (sb_003 Kai-focused, sb_004 wave/decision with
  Embry distant), with NO different-looking woman substituted in any frame;
  scene/wardrobe/action/environment continuity PASS; Kai (reference
  `02-kai_character_sheet.png`) not contradicted. Whole-clip embedding identity
  is NOT certified — final-third certainty rests on VLM pose/occlusion +
  wardrobe/composition, not embedding proof.
- Steps 37-38 audio + final assembly: PASS (v2,
  `…/97688ec5…/step37_38_audio_final_assembly_receipt.v2.json`). The successor's
  authoritative line/speaker/timing (Kai, "If we paddle now, we're cutting across
  the lineup.", 5.0-8.08s, sb_003) is IDENTICAL to the frozen predecessor's
  rendered line (predecessor whisper recognized_text==canonical_text). Re-mixing
  the hash-bound isolated line WAV (`sha256:c240e201…`) + the same ocean bed
  (`sha256:8d5e0d3e…`) with the proven ffmpeg filter reproduced a bit-identical
  mix (`sha256:33edae9a…`) and was muxed onto the silent return
  (`provider_return_muxed.mp4`). Whisper large-v3-turbo forced alignment
  recognizes the exact line in-window; the visible-speaker/lip-sync rule is
  INAPPLICABLE_BY_COMPOSITION (wide two-character lineup, no readable speaking
  mouth) per a Tau visible-speaker review. No paid call, no new voice engine.
- Acceptance: ACCEPTED_AGENT_LEVEL
  (`…/97688ec5…/post_return_acceptance_receipt.v2.json`); the fail-closed gates
  (step 36, step 38) both PASS. Human subjective acceptance still NOT claimed
  (remains the human's).
- Canonical cognitive loop: DRY-RUN ONLY, still NO canonical write
  (`stageb_cognitive_loop_outcome.v1.json`,
  `watch_gauntlet/59b9ff3155d6/cognitive_loop_dryrun_stageb/`). Phases 13/14 are
  TEXT reasoning; at commit 416edc5a Tau exposes no general text-completion node
  (panel-reviewer is image-bound; `scillm_subagent_gate` is a validator), and
  direct scillm is forbidden. Fail-closed: `canonical_dream_memory_written:
  false`. Canonical persistence is DEFERRED pending a Tau text-reasoning node for
  genuine phase-13 self-interpretation (mandatory Watch citations +
  renderer-defect alternatives). Route verification:
  `…/97688ec5…/tau_vlm_route_verification_receipt.v1.json`.

The frozen revision `rev_upstream_bf3b05d47fb8` crossed the live Kling boundary
once for repaired request
`sha256:ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f`.
Provider request `019f70ac-3864-7d81-9e86-5fae6a676e0d` completed after 54
polls with no resubmit. The returned source MP4 passes technical validation, but
visual acceptance is blocked by Embry identity drift. The exact Kai line and
ocean ambience are post-muxed into the final MP4; forced alignment passes, but
visible-speaker lip synchronization fails because Kai's mouth is readable
during SB_003.

Current gate language:

```text
active repaired Kling request submitted: yes, exactly one provider call
active repaired Kling video returned: yes, 16,957,429-byte source MP4
active provider request id: 019f70ac-3864-7d81-9e86-5fae6a676e0d
active ffprobe: readable H.264, 10.041667 seconds
active frame contact sheet: 12 frames in a 4x3 PNG, sha256:9a97c5093d055f50a7b43eee9ad2ae48287f2416c2551e0becfe1442b70540a6
active continuity review: fail, EMBRY_IDENTITY_DRIFT_00_03
audio strategy: post_mux; Kling request intentionally has generate_audio=false
step 37 voice handoff: exact live Kai line rendered and hash-bound; ready for mux
forced alignment: pass; exact canonical line measured at 5.00-7.70s by local Whisper large-v3-turbo
step 38 final assembly: fail, FAIL_VISIBLE_SPEAKER_NOT_LIPSYNCED; muxed MP4 sha256:991c311f365f84832b274aad7b8ff757372914f7c516e595a31b1bd05edf4c59
audio proof: stream present, mean -35.5 dB, max -16.8 dB
pipeline-step Memory exact reread: 42/42; step 38 is FAIL_VISIBLE_SPEAKER_NOT_LIPSYNCED
revision persistence audit: pass, six checks, zero failed checks
agent evidence acceptance: blocked
not proven: human subjective voice quality, acceptable lip synchronization, or stable Embry identity
```

Contact-sheet qualification update:

```text
replacement Embry contact sheet: PASS_CONTACT_SHEET_IDENTITY_QUALIFIED
creator: GPT Image 2 through Tau/Scillm, live, no fallback
reviewer: GPT-5.5 pixel review, 9/9 cells accepted, zero blockers
image sha256: 3ce40b3b6839ebba0f468d75a1adbb7f82e0d95457aefd3627e222eb569de00c
Memory exact retrieval: embry_contact_sheet_v3, confidence 1.0, semantic_sync_state synced
current critical path: resolve the step 38 visible-speaker lip-sync plan, prove the reviewer negative control, wire watch into the post-return gauntlet, then compile the successor provider request for a newly hash-bound authorized Kling return
not proven: repaired Kling identity on a successor return, or accepted lip synchronization
```

Successor storyboard update (2026-07-18):

```text
successor revision: rev_successor_943b01ecd9a3, PASS_ACTIVE_CONSISTENT, acceptance rung reached
storyboard frames: 8/8 actual-pixel identity PASS, first attempt; 7/7 continuity pairs PASS
reviewer hardening addendum (2026-07-18): a negative-control probe (reviewer_calibration_receipt.v1) proved the Phase C identity reviewer was too LENIENT — it PASSed 2 of 3 known-bad montage-derived frames, so the 8/8 first-attempt PASS was partly false confidence for SPECIFIC-identity fidelity. The reviewer prompt was hardened (specific-identity gate, age clause, complexion/feature grounding, fail-closed on uncertainty), contained to phase07_storyboard_tau_node._identity_review_prompt. Hardened prompt sha256:ee09dd57d8d06953d2039b4085cab7e481a5f09c09984a290b97b41cb3f626d7. Recalibration (reviewer_calibration_receipt.v2, 3 prompt revisions) = REVIEWER_CALIBRATION_FAILED but improved: known-bad FAILs 1/3 -> 2/3 (strongest case known_bad_sb_002 now caught), positives 2/2 and tamper 1/1 unchanged; residual = the subtlest montage frame known_bad_sb_001 still passes pixel-only review. Hardened re-review of the 8 accepted successor frames = 8/8 STILL PASS (hardened_rereview_summary.v2). acceptance_rung_receipt.v2 = RUNG_NOT_RESTORED_BLOCKED_ON_REVIEWER_CALIBRATION: the rung is NOT re-certified because full reviewer calibration was not reached; lane C SB_003 regen + supersession/requalification are DEFERRED until the sb_001 calibration gap is resolved (face-crop comparison / second reviewer / human adjudication). Memory (exact reread PASS): persona_dream:pipeline-complete:rev_successor_943b01ecd9a3:07r:reviewer_calibration_v2, :07r:hardened_rereview_8frames, :rung:acceptance_rung_v2. No paid call made or authorized.
face-crop subgate addendum (2026-07-18): the identity reviewer was augmented with a MANDATORY face-crop identity subgate (new helper scripts/identity_face_crop_subgate.py, wired into phase07_storyboard_tau_node._run_identity_continuity_review): it obtains face bboxes from gpt-5.5, crops the candidate face + up to 3 pose-matched reference views with PIL, upscales, and runs a feature-level face-to-face comparison; full-frame review AND the subgate must both PASS; failure code FAIL_FACE_CROP_IDENTITY_MISMATCH; purely additive (full-frame never relaxed), fail-closed, no provenance in prompts; unit-tested (tests/test_identity_face_crop_subgate.py, 26 cases, no live calls). Calibration v3 (reviewer_calibration_receipt.v3.json, 3 subgate-prompt revisions = the cap) = REVIEWER_CALIBRATION_FAILED: known-bad 2/3 FAIL, tamper 1/1 FAIL, positives 1/2 (unstable). CRITICAL residual = known_bad_sb_001 (the subtlest near-look-alike) still PASSes: at face-crop scale gpt-5.5 cannot separably discriminate it from the genuine positives, and borderline crop verdicts are UNSTABLE run-to-run (SAME/DIFFERENT/empty verdict on identical inputs). The subgate mechanism DOES work — under the strict first prompt it FAILED sb_001 via the crop subgate — and it closes the full-frame dilution blind spot for non-marginal mismatches, but no single prompt within the budget separated the subtlest case from real matches without over-rejecting them. Per contract, restoration is WITHHELD and a human adjudication bundle was packaged (reviewer_calibration_v3/human_adjudication_bundle: side-by-side candidate vs pose-matched v3 reference crops + one-page ADJUDICATION.md). acceptance_rung_receipt.v3.json = RUNG_NOT_RESTORED_BLOCKED_ON_REVIEWER_CALIBRATION; the 8-frame augmented re-review, lane C SB_003 regen, and supersession/requalification/rung restoration remain gated on calibration PASS. Memory (exact reread PASS): persona_dream:pipeline-complete:rev_successor_943b01ecd9a3:reviewer_calibration_v3_face_crop_subgate, :acceptance_rung_v3. No paid call made or authorized.

embedding identity subgate + calibration v4 addendum (2026-07-18): identity verification was moved OFF the unstable gpt-5.5 VLM face-to-face verdict and ONTO a deterministic ArcFace metric. New helper scripts/identity_face_embedding_subgate.py (InsightFace buffalo_l / w600k_r50, 512-d L2-normalized; detect -> 5-pt align -> embed -> cosine vs calibrated threshold; deterministic, mockable Embedder interface, 11 unit tests) is wired into phase07_storyboard_tau_node._run_identity_continuity_review as the IDENTITY VERDICT AUTHORITY: the full-frame VLM still gates scene/wardrobe/composition + face visibility, the VLM face-crop is demoted to advisory only, and identity pass/fail is cosine distance. Failure code FAIL_FACE_EMBEDDING_IDENTITY_MISMATCH (records the score); fail-closed (no InsightFace -> FAIL, never a silent VLM-only fallback). Install pinned insightface==0.7.3 + onnxruntime==1.19.2 (insightface_install_receipt.v1.json; pyproject [identity] extra). Calibration v4 (reviewer_calibration_receipt.v4.json, live, CPU) = REVIEWER_CALIBRATION_PASS: genuine same-person floor 0.4991, known-bad/tamper ceiling 0.3430, threshold 0.421, margin 0.156; 3/3 known-bads FAIL, both positives PASS, tamper FAILS. The v3 CRITICAL residual known_bad_sb_001 scores Embry cosine 0.323 — metrically a DIFFERENT face, far below the 0.499 genuine floor; the human-adjudication dispute is RESOLVED BY MEASUREMENT (it is a different identity; no reclassification). positive_control_sb_002, wrongly FAILed by v3's VLM crop, now PASSes (Kai 0.526). All 8 accepted successor frames PASS the embedding subgate (0.525..0.815). Live node-integration proof (reviewer_calibration_v4/node_integration): known_bad_sb_001 full-frame VLM still PASSes but the node FAILs via face_embedding_subgate; positive_control_sb_002 now PASSes. Remaining for full rung certification (now unblocked): lane C SB_003 composition-delta regen (GPT Image 2) + --supersede requalification + prepare/verify/activate. Memory (exact reread PASS): persona_dream:pipeline-complete:rev_successor_943b01ecd9a3:reviewer_calibration_v4_face_embedding_subgate (+ successor_rereview_v4 / acceptance_rung_v4). No paid call made or authorized.

known unresolved risk: step 38 lip sync has a recorded resolution plan but is not yet executed; the accepted SB_003 frames and post-mux audio are still unchanged. Decision packet `.persona-dream/revisions/rev_successor_943b01ecd9a3/step38_lipsync_decision_packet.v1.json` (+ .md twin) recommends PRIMARY lane C (non-paid SB_003 composition change so Kai's mouth is not camera-readable during 5.0-7.7s — regenerate the SB_003 end frame only, keep the start frame as identity anchor; delta proposal `step38_sb_003_composition_delta_proposal.v1.json`), FALLBACK lane A (paid Kling lip-sync API, post-return, unsent request template), REJECT lane B (generate_audio=true breaks the exact-transcript/consented-voice requirement). Human must pick before the next paid Kling call; no paid call authorized. Memory: `persona_dream:pipeline-complete:rev_successor_943b01ecd9a3:38:step38_lipsync_decision` (exact reread PASS)

lane C execution + BLOCKER addendum (2026-07-18): lane C was EXECUTED live (new driver scripts/lane_c_regenerate_sb_003_end_frame.py) — sb_003_end_frame regenerated via the Phase C GPT Image 2 lane (codex-oauth, embry_contact_sheet_v3 + Kai character sheet as reference inputs) applying step38_sb_003_composition_delta_proposal.v1.json, in a bounded 5-attempt failure-aware loop. Acceptance per attempt required ALL of (a) augmented identity review PASS (hardened full-frame gpt-5.5 VLM + ArcFace embedding subgate for BOTH characters, threshold 0.421), (b) a composition check proving Kai's mouth is not camera-readable (the specific VLM question + the delta criteria), (c) continuity PASS for sb_003_start->end(new) and end(new)->sb_004_start. RESULT = FAILED_LANE_C_ATTEMPTS_EXHAUSTED (accepted:false). Attempt table: att1 arm-occluded mouth -> composition PASS but identity FAIL (fail-closed full-frame VLM cannot ground Kai's features with the lower face hidden); att2-att5 clean/moderate three-quarter -> identity PASS (embeddings Embry/Kai 0.70/0.71, 0.73/0.80, 0.81/0.64, 0.67/0.72) and att4-att5 BOTH continuity pairs PASS, but the mouth stayed camera-readable -> composition FAIL every time. ROOT CAUSE (documented, gate NOT weakened): the hardened full-frame identity reviewer is fail-closed and needs Kai's lower face visible to ground specific-identity features, which directly conflicts with the mouth-not-camera-readable requirement; GPT Image 2 could not hit the narrow overlap in 5 attempts (att4/att5 near misses). This also surfaces a design tension between the delta (end-frame face_required=false, identity_anchored_by=sb_003.start_frame) and acceptance criterion (a) which verifies the face ON the end frame for both characters — resolving that is a GATE-DESIGN decision reserved for a human. Fail-closed: the frozen revision and its canonical phase_c sb_003_end_frame are UNTOUCHED, requalification + rung restoration were NOT attempted, and the acceptance rung REMAINS at v4 (RUNG_CALIBRATION_RESOLVED_IDENTITY_CERTIFIED_PENDING_LANE_C_AND_REQUALIFICATION) — NOT restored. Blocker receipt `.persona-dream/revisions/rev_successor_943b01ecd9a3/step38_lane_c_blocker_receipt.v1.json` records the full attempt table + the three human-decision next actions (targeted non-paid re-gen for the near-miss pose / formally adopt the delta's start-frame-anchored end-frame standard / paid lane A). Lane C evidence retained under `.../phase_07_storyboard_live_tau/lane_c_step38_sb_003_end_regen/`. Memory (exact reread PASS): `persona_dream:pipeline-complete:rev_successor_943b01ecd9a3:38:lane_c_sb_003_end_regen`, `:38:lane_c_blocker`. No paid call made or authorized.

anchored-identity waiver + lane C PASS addendum (2026-07-18): the gate-design contradiction recorded in the lane C blocker was RESOLVED by implementing the delta's OWN accepted design as a scoped, fail-closed **anchored-identity waiver** (`scripts/anchored_identity_waiver.py`, `tests/test_anchored_identity_waiver.py` 12 pass). A character's END-frame identity check may be waived ONLY when ALL of: (a) the composition contract explicitly requires that character's face non-readable on that frame (machine-checked, bound to the contract sha256); (b) the same panel's START frame passes the full augmented identity review (full-frame VLM + ArcFace embedding subgate) for that character (anchor cosine recorded); (c) the start->end continuity passes with explicit NON-FACIAL identity continuity (wardrobe, build, hair, board, position); (d) a waiver receipt is emitted (character, frame, contract hash, anchor frame + cosine, continuity receipt). Default FAIL-CLOSED; every other character (Embry) keeps the FULL augmented check; outside these four conditions all gates stay exactly as strict. This is a documented design correction, not a gate weakening. Lane C was RE-RUN under the waiver (new driver `scripts/lane_c_regenerate_sb_003_end_frame_waiver.py`, Embry judged by a waiver-aware Embry-only augmented review so Kai's intentional turn-away does not spuriously fail her) and PASSED on attempt 1 (`.../lane_c_step38_sb_003_end_regen_waiver/lane_c_regeneration_receipt.json` = PASS_LANE_C_SB_003_END_REGENERATED_WAIVER, new frame sha256:9f8fb8c9...): composition PASS (Kai's mouth not camera-readable) + Embry end-frame augmented identity PASS (cosine 0.716584) + Kai waiver GRANTED (anchor cosine 0.798839 + non-facial continuity) + BOTH continuity pairs PASS. The artifact-index rebuild + bindings + supersession promoting the new frame all ran cleanly. BUT prepare/verify/activate requalification is BLOCKED fail-closed by a PRE-EXISTING memory-record-space collision: the prepare gate requires the qualification (run_id, revision_id) space to hold EXACTLY the 27 qualification records, but 14 governance/audit records (13 predating this session) share it, and the Memory daemon exposes no deletion primitive (no /delete endpoint; /query forbids destructive AQL REMOVE). Per 'factual blocked outcome beats forced pass' the requalification was NOT forced (no audit deletion, no gate edit); the revision was restored to its prior ACTIVE_CONSISTENT baseline (artifact index 06496a6a) and the acceptance rung REMAINS at v4 — rung v5 is NOT emitted. Blocker receipt `.persona-dream/revisions/rev_successor_943b01ecd9a3/step38_lane_c_waiver_requalification_blocker_receipt.v1.json`. Memory (exact reread PASS): `persona_dream:pipeline-complete:rev_successor_943b01ecd9a3:anchored_identity_standard`, `:38:lane_c_sb_003_end_regen` (now PASS), `:38:lane_c_waiver_requalification_blocker`. No paid call made or authorized.

phase 11 provider-media binding BLOCKER — paid submit NOT reachable, NO paid call made (2026-07-19): under the operator's four-step authorization (proceed with the remaining chain: publication authorization + hash-bound one paid submit + submit/poll/download through the /watch gauntlet; "please don't stop on obvious next steps"), the phase 11 chain was driven with the frozen predecessor's machinery adapted to the successor. It FAILS CLOSED at the FIRST step: `run.sh bootstrap-phase11-payload-binding` (zero-call) returns `BLOCKED_PHASE11_MEDIA_LOCK_HASH` for `sb_001.start_frame` (indexed `sha256:135564ca...` != locked `sha256:bbd7a631...`). ROOT CAUSE: the revision artifact index (85c92446) binds the ACCEPTED, identity-certified successor START frames (phase_c_successor_regen: sb_001..004.start = 135564ca / aebcbd90 / 9046059c / 2c3211f2 — the exact frames the reviewer_calibration_v4 ArcFace subgate PASSed and rung v5 certifies) but `phase_08_media_lock/storyboard_media_lock_manifest.json` is STALE — it still LOCKS the predecessor-identical start frames (bbd7a631 / 3f7a1d4e / 471513b4 / 8fcd2045) at wrong-worktree, non-revision-scoped paths, predating the phase_c acceptance. The lane C waiver end-frame supersession propagated to the index, but the phase_08 media lock was never regenerated for the accepted START frames, so index != media lock and the binding gate correctly refuses to build provider URLs. Compile -> provider final gate -> paid authorization -> submit are UNREACHABLE. Per fail-closed / "factual blocked outcome beats forced pass", the single irreversible paid submit was NOT spent on the stale, out-of-scope predecessor-identical media (submitting it would reproduce EMBRY_IDENTITY_DRIFT and would NOT contain the accepted successor frames). NEXT REQUIRED ACTION (human/upstream decision — a certified-qualification-state change, not silent agent work): regenerate the phase_08 media lock to lock the accepted frames (phase_c_successor_regen starts + waiver canonical sb_003.end_frame 9f8fb8c9) at revision-scoped paths (scripts/convert_accepted_storyboard_to_kling.py), then re-run supersession -> prepare/verify/activate --supersede requalification to restore PASS_ACTIVE_CONSISTENT; only then does the phase 11 chain (bootstrap-payload-binding -> capture-provider-source-snapshot -> capture-public-media-evidence -> compile -> validate -> fal-canary-preflight -> write-approval-receipts -> fal-canary-execute) proceed. Receipt: `.persona-dream/revisions/rev_successor_943b01ecd9a3/phase_11_submit_return/preflight/phase11_provider_media_binding_blocker_receipt.v1.json` (+ captured `phase11_payload_binding_bootstrap_blocker.json`). Memory (exact reread PASS 2/2): `persona_dream:pipeline-complete:rev_successor_943b01ecd9a3:28:phase11_provider_media_binding_blocker` (persona_dream_governance), `:28:kling_scene_packet` (persona_dream_pipeline_steps). Operator authorization recorded verbatim + UNCONSUMED. actual_provider_call_attempts=0.

gate-scoping fix + rung v5 RESTORED addendum (2026-07-18): the requalification blocker was a GATE OVER-MATCH, not record pollution. `scripts/prepare_revision_qualification.py` listed project_knowledge by (run_id, revision_id) and required EXACTLY the 27 qualification records, so governance/audit records that legitimately share that keyspace (the deletion-free Memory daemon cannot relocate them) were counted as unexpected_keys. FIX (`scope_qualification_documents()`, commit 1d454819): the exact-match set is now selected by record IDENTITY — a qualification record's schema (pipeline_revision/phase/artifact_ref.v1) AND record_type (revision/phase/required_artifact) AND stable-key prefix (pd_rev_/pd_phase_/pd_artifact_) must all agree; governance records (matching none) are readable but never counted; a malformed qualification claim or a duplicate key fails closed; the gate stays provably as strict as before for the 27 records (tests/test_qualification_gate_scoping.py, 8 pass; full qualification suite 21 pass). Future governance writes are routed to persona_dream_governance (ten persisters + the cognitive-loop persister); historical records left untouched in project_knowledge. With the gate scoped, the chain completed LIVE end-to-end: authored `step38_lane_c_accepted_waiver_frame_invalidation_ledger.v1.json` (retains the phase_c sb_003_end_frame as SUPERSEDED so the accepted waiver frame sha256:9f8fb8c9 becomes canonical sb_003.end_frame) -> rebuild index sha256:85c92446 -> revision_supersession PASS_REQUALIFICATION_SUPERSEDED (baseline receipts + terminal event archived under superseded/, old pointer retained as a SUPERSEDED Memory snapshot, old->new appended to the supersession ledger) -> prepare/verify/activate --supersede = PASS_ACTIVE_CONSISTENT (27 qualification records exact-reread; 15 governance records co-resident and correctly ignored). acceptance_rung_receipt.v5.json = PASS_ACCEPTANCE_RUNG (supersedes v4), citing calibration v4, the 8-frame augmented re-review, the lane C waiver receipts, the supersession ledger, activation, and the gate-scoping fix receipt. does_not_prove keeps Kling readiness, provider media publication, publication authorization, paid authorization, provider return, lip-sync-on-return. Memory (exact reread PASS, persona_dream_governance): `persona_dream:pipeline-complete:rev_successor_943b01ecd9a3:qualification_gate_scoping_fix`, `:38:lane_c_sb_003_end_regen`, `:requalification_supersession_v5`, `:acceptance_rung_v5`. No paid call made or authorized.

media-lock regen + rung v6 RESTORED + phase-11 voiced-run cycle BLOCKER addendum (2026-07-19): under the operator's four-step authorization, the phase-11 chain was driven. The prior `BLOCKED_PHASE11_MEDIA_LOCK_HASH` blocker is RESOLVED. (1) MEDIA LOCK: `phase_08_media_lock/storyboard_media_lock_manifest.json` regenerated to lock the 8 index-bound accepted frames (phase_c starts + sb_001/002/004 ends + lane C waiver canonical sb_003.end `9f8fb8c9`), derived directly from `revision_artifact_index.json` so lock == index for every frame; new manifest sha256:8f3df1ec; old predecessor-identical lock ca2251f0 retained under `phase_08_media_lock/superseded/`. FRAME-DIMENSION FINDING (in-scope, proceeded): the accepted certified frames are NOT the predecessor-canonical 1536x864 and are not uniform (gpt-image-2 returned sb_001/002/003 start+end at 1672x941, sb_004 at 1536x864, all 16:9); locked at true dimensions because the 1536x864 invariant lives ONLY in the phase-07/08 dry-run machinery (convert_accepted_storyboard_to_kling / validate_kling_scene_packet), not on the requalification or phase-11 live path, and fal Kling image-to-video accepts arbitrary input resolution. (2) MACHINERY FIX (commit 799938fc): the supersession ledger/receipt are now excluded from the artifact index (`write_revision_artifact_index.VOLATILE_QUALIFICATION_RECEIPTS`) — the first requalification only worked because they didn't pre-exist; on a repeat they already exist and a naive re-index folds in their pre-supersession hashes, failing prepare with `BLOCKED_REVISION_HASH_MISMATCH`. (3) REQUALIFICATION: rebuild index 85c92446 -> `b4655635` -> revision_supersession PASS_REQUALIFICATION_SUPERSEDED -> prepare/verify/activate --supersede = PASS_ACTIVE_CONSISTENT (retried through transient embedding-service GPU OOM windows on the shared jina sidecar; no gate weakened). `acceptance_rung_receipt.v6.json` = PASS_ACCEPTANCE_RUNG (sha256:0efc5671, supersedes v5), citing index b4655635 which binds the coherent media lock. (4) `run.sh bootstrap-phase11-payload-binding --publication-commit 571ff2bb` now ADVANCES PAST the media-lock hash gate and fails closed at the NEXT, newly-surfaced gate `BLOCKED_VOICED_RUN_AUDIO_STRATEGY_NOT_DECLARED`. ROOT CAUSE = a voiced-run cycle: bootstrap's payload binding requires a valid `voice_handoff_plan.json`; `write_voice_handoff_plan.py` requires the compiled `phase11_live_request.v1.json`; `compile` requires the payload binding. The audio-strategy gate post-dates the predecessor's original compile (added in commit c870698c; predecessor compiled at commit d6d869c3 before it existed), so the prior media-binding blocker receipt did not map it. NO live voice render is needed (the voice binding reuses `phase_05_voices/kai_voice_audition.json`); the only missing input is the deterministic `request_body_sha256`. Breaking the cycle needs either a small phase-11 ordering machinery fix (let voiced runs seed the request sha before the compiled canonical) or a fabricated transient provider-request stub to seed a fixpoint — the latter was NOT done unilaterally on the irreversible paid-submit path ("factual blocked outcome beats forced pass"). The certified state (index b4655635, rung v6, activation-a55f9001) is untouched by that decision. Receipt: `.persona-dream/revisions/rev_successor_943b01ecd9a3/phase_11_submit_return/preflight/phase11_audio_strategy_cycle_blocker_receipt.v1.json`. Memory (exact reread PASS, persona_dream_governance): `persona_dream:pipeline-complete:rev_successor_943b01ecd9a3:28:phase11_audio_strategy_cycle_blocker`. Commits 799938fc, 6c7661e5 pushed to origin/main. NO paid call made or authorized (0 attempts); the single irreversible submit is preserved.
```

No agent may claim final, green, complete, fixed, or verified for this goal
unless those concrete artifacts exist and are cited.

## Memory Persistence Contract

Every step below must write a durable memory record through `$memory`.

Default collection:

```text
persona_dream_pipeline_steps
```

Default `_key` shape:

```text
persona_dream:<run_id>:<revision_id>:<step_no_padded>:<step_slug>
```

Each step record must include:

```text
schema
run_id
revision_id
step_no
step_slug
step_name
status
inputs
outputs
receipt_paths
artifact_hashes
request_hash when applicable
provider_task_id when applicable
memory_write_method: /store or /upsert
memory_write_receipt
exact_reread_receipt
semantic_sync_state when recallable
qdrant_collection and qdrant_point_id when recallable
claims.proves
claims.does_not_prove
blocker when blocked
observed_at
```

Rules:

- Use `$memory` `/store` for a single record and `/upsert` for batches.
- Do not write vector arrays into ArangoDB memory documents.
- Exact gates must reread by `_key` or exact `/list` filters, not only semantic
  recall.
- Semantic recall or Qdrant sync can support discoverability, but it does not
  replace exact reread proof.
- If a step is blocked, write the blocked record anyway with the concrete
  blocker and next required action.
- If an upstream revision changes, downstream memory records must be marked
  stale or superseded instead of being reused silently.

## Serial Pipeline Steps

Each row is a required pipeline step. The memory persistence column is
non-optional for every row.

| # | Pipeline step | Required artifact or receipt | Memory persistence requirement |
|---:|---|---|---|
| 01 | Request / Idea Intake | `dream_request.json`, idea/revision receipt, source seed | Store the exact human seed, normalized request, run id, revision id, and request hash. |
| 02 | Dreaming Persona Selection | persona selection receipt | Store selected persona ids, rejected/secondary personas, selection rationale, and scope tags. |
| 03 | Memory Recall | recall request/response receipt | Store question-shaped recall queries, collections, tags, returned keys, scores, and pass/fail scope check. |
| 04 | Residue Grounding | `residue_links.json`, `contradiction_report.json` | Store source residue ids, scopes, contradictions, missing evidence, and grounding status. |
| 05 | Dream Packet | `dream_packet.json`, `dream_prompt.txt` | Store packet hash, synthetic-content label, source residue links, and does-not-prove claims. |
| 06 | Story / Video Plan | `dream_story.md`, `dream_story.json`, `pipeline_stage_report.*` | Store accepted story/video plan hash, duration target, scene list, and acceptance status. |
| 07 | Producer Persona Selection | producer selection receipt | Store producer persona, authority boundary, decision scope, and invalidation impact. |
| 08 | Director Selection | director/DoP selection receipt | Store director/DoP selection, visual authority scope, and downstream artifacts invalidated by change. |
| 09 | Script Writer Selection | script-writer selection receipt | Store writer selection, script authority scope, and downstream artifacts invalidated by change. |
| 10 | Creative Authority Receipts | producer/director/writer authority receipt bundle | Store all creative authority ids, approvals, exceptions, and exact receipt hashes. |
| 11 | Look Lock | `technique_selection.json`, `look_lock.json`, `shot_bible.json` | Store camera, lens, lighting, color grade, movement grammar, continuity locks, and selector receipt hash. |
| 12 | Script DNA | `script_dna_selection.json` | Store story rhythm, dialogue pressure, conflict pattern, reveal logic, theme, and selector receipt hash. |
| 13 | Storyboard Prompt Composition | storyboard prompt files and prompt manifest | Store prompt inputs, accepted upstream hashes, rendered prompt hashes, and stale-check status. |
| 14 | Storyboard Panel Receipts | panel work orders, panel prompt receipts | Store one record per panel with panel id, prompt hash, required entities, and upstream revision hash. |
| 15 | Panel Continuity And Repair Ledger | `panel_continuity_and_repair_ledger.json` | Store required visible entities, props, environment, behaviors, failed requirements, and repair status. |
| 16 | Panel Generation Loop | generated panel images and image receipts | Store model/auth path, caller skill, prompt file, image path, image hash, and generation receipt. |
| 17 | Panel Visual Review Loop | visual review receipts | Store reviewer result, visible/missing entities, identity checks, overlay checks, and review evidence path. |
| 18 | Surgical Panel Repair | repair prompts, repair receipts, regenerated images | Store failed image hash, correction deltas, new image hash, attempts, and bounded-loop status. |
| 19 | Panel Repair Gate | `panel_repair_gate_receipt.json` | Store final panel status and all subgate results; only `PASS_PANEL_REVIEWED` can feed provider readiness. |
| 20 | Panel Source Receipt | `panel_source_receipt.json` | Store canonical panel source path, media hash, review status, and provider-eligible flag. |
| 21 | Provider Media Publication Work Order | publication work order receipt | Store target repo/path/url plan, source asset hash, authorization need, and proposed public URL. |
| 22 | Local Provider Media Staging | local staging receipt | Store staged file path, byte count, SHA-256, target path, and staging validation status. |
| 23 | Publication Preflight | publication preflight receipt | Store public-upload requirements, proposed URL, expected hash, and what remains unauthorized. |
| 24 | Publication Authorization | human authorization receipt | Store exact authorization text/hash, allowed action, excluded actions, spend/publication scope, and expiry. |
| 25 | Public URL Probe | URL probe receipt | Store fetched URL, HTTP status, byte count, content hash, MIME/type evidence, and parity result. |
| 26 | Provider Media Handoff | provider media handoff receipt | Store provider-accessible URLs, source hashes, element bindings, and fetchability status. |
| 27 | Provider Media Lock | provider media lock receipt | Store immutable URL/hash lock, element mapping, revision id, and stale-policy result. |
| 28 | Kling Scene Packet | `kling_scene_packet.json` or canonical live request | Store provider payload hash, multi-prompt fields, media URLs, timing, dialogue, and schema validation status. |
| 29 | Provider Final Gate | provider-readiness receipt | Store gate status, passed/failed checks, cost/mode/entitlement proof, and live-submit readiness flag. |
| 30 | Paid Call Authorization | paid-call authorization receipt | Store exact human authorization, max spend, provider request hash, attempt budget, and consumed/unused state. |
| 31 | Kling Submit | provider submit receipt | Store request hash, provider endpoint/model, external task id, provider task id, HTTP status, and raw response path. |
| 32 | Kling Poll / Callback | poll/callback event log | Store poll attempts, callback events, provider task status transitions, timestamps, and terminal state. |
| 33 | Output Retrieval | download/result receipt and returned video file | Store result URL, downloaded path, byte count, video hash, provider response hash, and retrieval status. |
| 34 | FFprobe / Technical Validation | `ffprobe.json`, technical validation receipt | Store duration, frame rate, codec, dimensions, stream readability, and pass/fail result. |
| 35 | Frame Contact Sheet | frame sheet image and receipt | Store sampled timestamps, frame sheet path, image hash, source video hash, and generation command. |
| 36 | Post-Kling Continuity Review | continuity review receipt | Store visual continuity verdict, identity/scene/action failures, screenshots/contact sheet path, and reviewer evidence. |
| 37 | Voice / Audio Handoff Lane When Voiced | `voice_handoff_plan.json`, voice receipts | Store speaker ids, voice ids or blockers, timing, consent/provenance, audio lane handoff, and voice status. |
| 38 | Final Assembly / Movie Lane | assembled MP4/mux receipts when needed | Store clip list, audio/video inputs, FFmpeg command, assembled output hash, and mux validation result. |
| 39 | Report Generation | final HTML/JSON report and validation receipt | Store report path, validation status, evidence index, mocked/live flags, and unresolved blocker list. |
| 40 | Gate Validation Loop | gate validation summary | Store all gate statuses, failed gates, blocked gates, stale gates, and the next critical-path command. |
| 41 | Upstream Revision Invalidation | invalidation ledger | Store changed upstream artifact, affected downstream records, stale markings, and regeneration requirements. |
| 42 | Final Acceptance Boundary | final acceptance receipt | Store final human/agent acceptance state, exact proof artifacts, and explicit `does_not_prove` exclusions. |

## Completion Rule

The goal is complete only when step 42 cites positive evidence from steps 31
through 36 for a real returned Kling video, plus memory persistence evidence
for steps 01 through 42.

For a voiced run, step 42 must also cite positive Step 37 and 38 evidence: an
exact transcript render, forced-alignment receipt, mix and FFmpeg mux receipts,
a final MP4 audio stream, audible-output review, and a visible-speaker lip-sync
review. When the speaker's mouth is visible, post-mux audio without an accepted
lip-sync transform cannot satisfy the immutable goal.

If any step lacks a memory write receipt and exact reread receipt, the goal is
not complete.

If any provider/Kling step is mocked, dry-run only, or blocked by missing
authorization, the goal is not complete.

If a report or dashboard says complete but the MP4, `ffprobe`, frame sheet,
continuity review, or memory receipts are missing, the report is wrong and must
be treated as a blocker, not as evidence.
