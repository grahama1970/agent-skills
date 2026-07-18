# Handoff Report: persona-dream

**Timestamp**: 2026-06-30T20:00:00-04:00
**Status**: See canonical current handoff at `local/HANDOFF.md`.

This top-level file redirects to the detailed handoff. The current handoff covers UX Lab Dream/Kling preflight React surface implementation — 12-phase pipeline, Gemini design packet mostly implemented, blocked on image modal click not working through draggable parent.

## 2026-07-18 Embedding identity subgate + calibration v4 — ADJUDICATION RESOLVED BY MEASUREMENT

- The v3 human-adjudication dispute over `known_bad_sb_001` is **resolved by measurement**, not by a human verdict. Identity verification was moved off the unstable gpt-5.5 VLM face-to-face judgment and onto a deterministic ArcFace metric: InsightFace `buffalo_l` (`w600k_r50`, 512-d L2-normalized) — detect -> 5-pt align -> embed -> cosine vs a calibrated threshold. VLMs are not metric identity verifiers; the run-to-run instability was the model waffling on a face it genuinely could not place.
- New helper `scripts/identity_face_embedding_subgate.py` (deterministic, mockable `Embedder` interface, 11 unit tests). Wired into `phase07_storyboard_tau_node._run_identity_continuity_review` as the IDENTITY VERDICT AUTHORITY: the full-frame VLM still gates scene/wardrobe/composition + face visibility, the VLM face-crop is demoted to advisory, and pass/fail on identity comes from cosine distance. Failure code `FAIL_FACE_EMBEDDING_IDENTITY_MISMATCH` (records the offending score). Fail-closed: no InsightFace -> FAIL, never a silent VLM-only fallback. Install pinned (`insightface==0.7.3`, `onnxruntime==1.19.2`), receipt at `insightface_install_receipt.v1.json`.
- Calibration v4 (`reviewer_calibration_receipt.v4.json`, live, CPU onnxruntime) = **REVIEWER_CALIBRATION_PASS**. Genuine same-person floor 0.4991, known-bad/tamper ceiling 0.3430, **threshold 0.421, margin 0.156**. 3/3 known-bads FAIL, both positives PASS, tamper FAILS. The disputed `known_bad_sb_001` scores Embry cosine **0.323** — metrically a DIFFERENT face, far below the 0.499 genuine floor; **no reclassification needed** (the answer to adjudication Q1/Q2 is: different identity). `positive_control_sb_002`, which v3 wrongly FAILed on the VLM crop, now PASSes (Kai 0.526). All 8 accepted successor frames PASS the embedding subgate (0.525..0.815).
- Live node-integration proof (`reviewer_calibration_v4/node_integration/`): `known_bad_sb_001` full-frame VLM still PASSes but the node now FAILs via `face_embedding_subgate`; `positive_control_sb_002` now PASSes. The exact v3 blind spot and over-rejection are both closed.
- Remaining for full rung certification (was gated on calibration PASS, now unblocked): lane C SB_003 composition-delta regen (decided-and-deferred, needs GPT Image 2), and the `--supersede` requalification + prepare/verify/activate pipeline. Memory (exact reread PASS): `...:reviewer_calibration_v4_face_embedding_subgate` (+ re-review / rung v4 keys). No paid call made or authorized.

## 2026-07-18 Face-crop identity subgate + calibration v3 — SUPERSEDED by v4 above (was: HUMAN ADJUDICATION required)

- Augmented the identity reviewer with a MANDATORY face-crop identity subgate: new helper `scripts/identity_face_crop_subgate.py`, wired into `phase07_storyboard_tau_node._run_identity_continuity_review`. It gets face bboxes from gpt-5.5, crops the candidate face + up to 3 pose-matched reference views (PIL, upscaled), and runs a feature-level face-to-face comparison. Full-frame review AND the subgate must both PASS; failure code `FAIL_FACE_CROP_IDENTITY_MISMATCH`. Additive (full-frame never relaxed), fail-closed, no provenance in prompts. Unit-tested: `tests/test_identity_face_crop_subgate.py` (26 cases, no live calls).
- Calibration v3 (`reviewer_calibration_receipt.v3.json`, 3 subgate-prompt revisions = the cap) = REVIEWER_CALIBRATION_FAILED: known-bad **2/3** FAIL, tamper 1/1 FAIL, positives **1/2** (unstable). CRITICAL residual: `known_bad_sb_001` (subtlest near-look-alike) still PASSes — not separably discriminable from the genuine positives at gpt-5.5 face-crop scale, with run-to-run instability (SAME/DIFFERENT/empty verdict on identical inputs).
- The subgate mechanism works (under the strict first prompt it FAILED sb_001 via the crop subgate) and closes the full-frame dilution blind spot for non-marginal mismatches; but a clean PASS was not achievable within the revision budget without over-rejecting genuine frames.
- Packaged a human adjudication bundle: `reviewer_calibration_v3/human_adjudication_bundle/` (montages `dispute_01_embry_...png`, `dispute_02_kai_...png` — disputed candidate vs pose-matched v3 reference crops — plus `ADJUDICATION.md` with the exact per-frame question). **Action: a human answers Q1/Q2 (is known_bad_sb_001 a different identity or an acceptable match?) and Q3 (require best-of-N agreement / second reviewer for borderline crops?), then route per ADJUDICATION.md.**
- `acceptance_rung_receipt.v3.json` = RUNG_NOT_RESTORED_BLOCKED_ON_REVIEWER_CALIBRATION. The 8-frame augmented re-review, lane C SB_003 regen, and supersession/requalification/rung restoration remain gated on calibration PASS. Memory (exact reread PASS): `...:reviewer_calibration_v3_face_crop_subgate`, `...:acceptance_rung_v3`. No paid call made or authorized.

## 2026-07-18 Reviewer hardening (identity continuity) — superseded by v3 above

- A negative-control probe proved the Phase C identity reviewer was too lenient (PASSed 2/3 known-bad montage frames), so the successor 8/8 first-attempt Phase C PASS was partly false confidence for specific-identity fidelity.
- Hardened `phase07_storyboard_tau_node._identity_review_prompt` (contained to the review prompt contract). Hardened prompt `sha256:ee09dd57d8d06953d2039b4085cab7e481a5f09c09984a290b97b41cb3f626d7`.
- Recalibration `reviewer_calibration_receipt.v2.json` = REVIEWER_CALIBRATION_FAILED but improved (known-bad FAILs 1/3 -> 2/3; positives 2/2, tamper 1/1). Residual: subtlest montage frame `known_bad_sb_001` still passes pixel-only review after the 3-revision cap.
- Hardened re-review of the 8 accepted successor frames = 8/8 STILL PASS (`hardened_rereview/hardened_rereview_summary.v2.json`).
- `acceptance_rung_receipt.v2.json` = RUNG_NOT_RESTORED_BLOCKED_ON_REVIEWER_CALIBRATION. Lane C SB_003 end-frame regen + supersession/requalification are DEFERRED until the sb_001 calibration gap is resolved (face-crop-only comparison, a second stricter reviewer, or human adjudication), then re-run calibration to PASS before restoring/certifying the rung. No paid call made or authorized.

## Current Truth

- The active handoff is:

```text
/home/graham/workspace/experiments/agent-skills/.opencode/skills/persona-dream/local/HANDOFF.md
```

- The React file is:

```text
/home/graham/workspace/experiments/pi-mono/packages/ux-lab/src/components/dream/DreamWorkspace.tsx
```

- The server routes are in:

```text
/home/graham/workspace/experiments/pi-mono/packages/ux-lab/server/index.ts
```

- The live route is:

```text
http://localhost:3002/watch#dream
```

- TypeScript compiles clean (exit 0).
- API servers running on ports 3001/3002.
- Memory daemon at `http://127.0.0.1:8601`.
- Persona media endpoint at `/api/persona-media` returns HTTP 200.

## Next Required Step

Fix the image modal click-through issue in `MemoryLinker` (draggable parent intercepts events). Then proceed to Phase 03 StoryMatrix wiring.

## Watch Post-Return Gauntlet (Phase 12 perception)

`watch` is now wired into the post-return gauntlet as the sole owner of
rendered-media perception, replacing the bespoke fixed 12-frame contact-sheet +
`watch-codex-vision` lane.

- **Harness**: `scripts/watch_post_return_gauntlet.py` — runs `watch`
  (scene-driven frames, Whisper transcript) over a returned MP4 and emits
  `watch_gauntlet/<video_sha_prefix>/dream_observation_packet.v1.json`
  (schema `persona_dream.watch_gauntlet_observation_packet.v1`) with per-frame
  observed entities, timestamps, coverage gaps, and hooks for GOAL steps
  35 (frame sheet), 36 (identity continuity), 38 (visible-speaker lip sync).
- **Proven**: validated against the frozen historical Kling return
  (`muxed_provider_return.mp4`, `sha256:991c311f…`). Receipt:
  `reports/pipeline-complete/.persona-dream/revisions/rev_successor_943b01ecd9a3/watch_gauntlet/991c311f365f/watch_gauntlet_validation_receipt.v1.json`
  → `PASS_WATCH_GAUNTLET_VALIDATED` (5/5 expectations). Codex-oauth vision
  independently corroborated `EMBRY_IDENTITY_DRIFT_00_03`; Whisper recovered the
  canonical Kai line consistent with the forced-alignment receipt.
- **Known degradation**: per-frame VLM entity descriptions are unavailable
  (`watch` default `vlm-chutes` model returns HTTP 401); recorded as a coverage
  gap, not faked. Vision drift corroboration is an independent probabilistic
  check — the frozen human continuity review remains authoritative.

**Next steps**: (1) restore a working `watch` per-frame VLM model to fill the
entity coverage gap; (2) once a freshly authorized successor Kling return exists,
run the same gauntlet against it (`--source-revision-id rev_successor_…`) to
observe the repaired output; Phase 12 is only *complete* when a successor return
is observed and its identity/lip-sync outcomes are recorded.

## Cognitive Loop 13-15 (Self-Interpretation, ToM Validation, Persistence)

Phases 13-15 are implemented and fixture-and-live-slice proven on the HISTORICAL
Kling return (`991c311f365f`). This is NOT the closed-loop research claim.

- **Runner**: `scripts/run_cognitive_loop.py` chains 12 -> 13 -> 14 -> 15 from an
  observation packet and emits `cognitive_loop_receipt.json`.
- **Phase 13** `scripts/phase13_self_interpretation.py` (+ schema
  `schemas/dream_self_interpretation.v1.schema.json`): scillm gpt-5.5 drafts;
  deterministic gate requires every accepted claim to cite >=1 Watch observation
  id AND >=1 source-memory id, and the honesty rule forces the renderer-defect
  explanation to be favored on an identity-DRIFT review.
- **Phase 14** `scripts/phase14_tom_validation.py` (+ schema
  `schemas/tom_candidate.v1.schema.json`): LLM proposes bounded ToM candidates;
  deterministic gate rejects any grounding not a subset of the parent accepted
  interpretation.
- **Phase 15** `scripts/phase15_dream_persistence.py`: default dry-run plan
  (exact would-write payloads + hashes, zero canonical writes); canonical write
  requires `--allow-canonical-write` + a non-superseded return id and hard-fails
  on this superseded return; write path proven into non-canonical
  `persona_dream_loop_validation`.
- **Tests**: `tests/test_cognitive_loop_phases.py` (16 cases, no live calls).
- **Receipts**:
  `.persona-dream/revisions/rev_successor_943b01ecd9a3/cognitive_loop/991c311f365f/`.

**Next steps**: (1) Phase 16 (recall + behavior) remains unimplemented as a closed
proof — needs Qdrant semantic recall of the stored dream, multi-hop traversal,
and before/after conversation evidence. (2) The closed-loop research claim requires
a freshly authorized, non-superseded successor return: run the Watch gauntlet on
it, then `run_cognitive_loop.py` with `--allow-canonical-write --return-id <successor>`
to exercise the real canonical persistence path (which is intentionally blocked
today). (3) Restore a working `watch` per-frame VLM model to fill the entity
coverage gap that currently weakens frame-level observation citations.
