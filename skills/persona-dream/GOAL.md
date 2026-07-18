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
