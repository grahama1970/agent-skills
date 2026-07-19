# Project Knowledge: persona-dream

**Last updated:** 2026-07-19 (P1 Tau-routing debt paid — strict ratchet is the gate) by agent
**Status:** Active development

## Current Understanding

- 2026-07-19 (P1 TAU-ROUTING TEMPORARY_DEBT PAID, 23 → 0): the "only /tau may
  reach /scillm" boundary is fully clean. `check_tau_routing_boundary.py --strict`
  exits 0 and `sanity.sh` now runs it in `--strict` mode (the ratchet is the gate).
  8 callers migrated to the sanctioned Tau adapters (text →
  `tau_text_reasoning_adapter`, which is JSON-object-only so free-text callers wrap
  as `{"...": "..."}`; image/VLM → `tau_vlm_review_adapter`, and multi-image
  identity/continuity reviews via the new persona-dream-side glue
  `scripts/tau_vlm_composite_review.py` that composites frame + reference sheets
  into ONE labeled montage for the single-image Tau panel node — NOT a new Tau node,
  since work is scoped to agent-skills-main). watch's `qra._scillm_chat_completion`
  routes text+image through Tau; its Whisper transcription is already local (no
  scillm audio). 2 diagnostics permanently allowlisted (health probe, loopback
  transport-contract proof); 11 rung-ladder transport experiments retired (receipt
  `reports/pipeline-complete/.persona-dream/rung_ladder_retirement_receipt.v1.json`).
  Live-proven: 4 Tau routes at HTTP-200 (no paid provider),
  `reports/pipeline-complete/.persona-dream/tau_live_receipts/`. Suites: persona-dream
  388 passed, watch 45 passed. Governance: `persona_dream_governance/tau_routing_debt_paydown_20260719`.
- 2026-07-19 (P0 OBSERVATION PACKET v2 — ONE PACKET, ONE AUTHORITY): the two
  incompatible phase-12 observation notions (scene-driven
  `watch_gauntlet_observation_packet.v1` vs fixed-lane
  `dream_observation_packet.v1`) are unified by an evidence-only successor schema
  `schemas/dream_observation_packet.v2.schema.json`: typed independently-optional
  modules, **no silent-video assumption, no fixed frame count, psychological
  interpretation FORBIDDEN** (const-false flag + a deterministic psychology
  filter that strips inferred emotion/mood/intent from VLM text and records what
  it removed). `scripts/build_observation_packet_v2.py` assembled the single
  **ACCEPTED** successor packet
  (`watch_gauntlet/59b9ff3155d6/dream_observation_packet.v2.json`, supersedes the
  DEGRADED v1 by hash `sha256:5229c664…`, v1 retained + marked superseded by a
  sidecar): **live** per-frame visible entities over 12/12 frames via the
  sanctioned Tau **panel-reviewer VLM** route (`tau_vlm_review_adapter.py`, 12
  receipts all HTTP 200, no direct scillm), a **full-clip local Whisper
  large-v3-turbo** transcript (exact Kai line recognized), and the authoritative
  ArcFace + step-36/37/38 adjudications folded by reference+hash. **Durable
  lessons:** (1) *the sanctioned Tau panel-reviewer VLM function already carries a
  per-frame image + free-text prompt* — the "frame-shaped Tau VLM node still to be
  added" was not needed for evidence-only per-frame description. (2) *enrichment is
  not a rewrite* — all 7 read-only `persona_dream_watch_evidence` vertices remain
  representable (`CONSISTENT_WITH_ADDITIVE_ENRICHMENT`); the delta where v2 now
  carries evidence a vertex marked "unavailable" is recorded additively, never by
  editing the canonical vertex. Governance:
  `persona_dream_governance/persona_dream_observation_packet_v2_20260719` (exact
  reread PASS). 12 deterministic tests + the live run (fixture-only is not
  acceptance).

- 2026-07-19 (P1 TAU-ONLY MODEL-ROUTING BOUNDARY — enforced): the operator rule
  *only /tau may reach /scillm* is now a **deterministic static gate**
  (`scripts/check_tau_routing_boundary.py`), not a convention. It scans
  `skills/persona-dream` + `skills/watch` for direct scillm proxy calls and fails
  on any un-sanctioned one; it is wired into `run.sh check-tau-routing-boundary`,
  `sanity.sh`, and `run.sh test-suite` (via `tests/test_tau_routing_boundary.py`).
  **Durable lesson:** *a routing rule that isn't statically checked is not enforced*
  — 23 pre-existing direct-scillm callers existed despite the standing rule; they
  are now enrolled as `TEMPORARY_DEBT` (the authoritative migration backlog) so no
  NEW violation can land silently. Sanctioned routes: text/QRA →
  `tau_text_reasoning_adapter.py` (verified live, HTTP 200, no paid call); image/VLM
  → `persona_dream_panel_agent` panel-reviewer or a frame-shaped Tau VLM node still
  to be added (the text node cannot carry images or free-text). Migrating watch
  VLM/QRA + lane_c image review is deferred pending that VLM node.

- 2026-07-19 (P0 CORRECTNESS BUNDLE — Sol Pro review, closed): three verified
  cognitive-loop defects fixed. **Lessons (durable):** (1) *presence of a proof
  object is not proof* — `canonical_dream_memory_written = bool(canonical_write_proof)`
  certified nothing; it now requires staging AND publish AND commit-manifest to all
  reread-match, else `BLOCKED_CANONICAL_PERSISTENCE_INCOMPLETE` + nonzero exit.
  (2) *edges are not vertices* — the committed "14/14 traversal" proved 14 EDGES
  resolved, not that the 7 Watch-observation VERTICES existed (they didn't); phase16
  traversal is now STRICT (every edge target, including `persona_dream_watch_evidence`
  vertices, must resolve or traversal FAILS) and the old claim is corrected via
  `corrected_traversal_receipt.v1.json` (old kept, marked superseded). (3) *loops
  need typed transitions* — `scripts/cognitive_loop_transitions.py` is a 5-state
  machine (`ACCEPTED_OBSERVATION→PASS_INTERPRETATION→PASS_TOM_VALIDATION→
  STAGED_PERSISTENCE_VERIFIED→CANONICAL_COMMIT`) that hash-binds each predecessor
  (phase14 binds exact phase13; commit binds exact 13+14) and hard-stops the loop on
  any structural blocker before the next side effect; the aggregate no longer accepts
  a bare `DEGRADED*` status. phase15 is now transactional (idempotency key → stage →
  verify → publish → verify → commit manifest as the single source of canonical
  visibility; retain-and-mark since the `$memory` API has no delete primitive;
  detect-and-quarantine on rerun). Watch-evidence vertices are materialized
  (`synthetic_origin=true`, `psychological_interpretation_performed=false`). The live
  dream `dream_dream_successor_943b01ecd9a3` (19 records) was reconciled ADDITIVELY —
  7/7 Watch vertices materialized, retroactive commit manifest written, strict
  traversal re-run PASS — with the 19 pre-existing records re-read live but NEVER
  rewritten. A 4th lesson: a lossless daemon numeric round-trip (`0.0→0`) is not
  corruption — normalize numbers in the reread-fidelity hash only, never in the
  artifact-binding hash. Governance:
  `persona_dream_governance/persona_dream_p0_correctness_governance_20260719`
  (exact reread PASS). 54/54 lane tests green.

- 2026-07-19 (GREEN_CANONICAL_LANE — CI contract reconciliation): the default test
  suite went from 29 failed / 313 passed to **0 failed / 342 passed / 0 skipped**,
  stable across two runs, reproducible via the new `./run.sh test-suite` (also wired
  into `sanity.sh` as a CI guard). The root cause was **incomplete vendoring** of the
  b68bf3d1 (2026-07-11) one-scene dry-run pipeline harness into `skills/persona-dream/`
  — not obsolete-lane bit-rot — so the decision was **RESTORE, not retire** (no
  retirement receipt). Three restores + one expectation fix: (1) authored the
  never-committed `schemas/kling_scene_packet.schema.json` (Draft 2020-12, faithful to
  the one-scene fixture; value gates stay in the Python validators, not const-pinned);
  (2) recreated the omitted fixture PNG `fixtures/one_scene_kling_dry_run/artifacts/panel_001_reference.png`
  and re-locked its sha256 in two receipts; (3) fixed the work-order writers' relocated
  agent-contract path (`REPO = ROOT.parents[1]` → skill-owned `agents/`) and created
  five real subagent contracts (dreamer, memory, panel-repair-gate, panel-creator,
  panel-reviewer); (4) updated `test_run_sh_read` to the current PROJECT_KNOWLEDGE
  header. `MANIFEST.json` is a SHA-256 patch-bundle manifest (34 files, 8 schemas)
  verified by `scripts/verify_manifest.py` — resynced deterministically (only the kling
  schema entry drifted, 4704→4108 bytes; now passes). `kling.scene_packet.v1` has no
  phase-11 successor (`phase11_live_request.v1` never references `scene_packet`), and
  the affected test files are partially-live, so retirement would have suppressed green
  coverage. No revision/rung/qualification gate weakened; no assertion deleted. Receipt:
  `reports/pipeline-complete/.persona-dream/state/green_canonical_lane_reconciliation_receipt.v1.json`;
  memory `persona_dream:pipeline-complete:green_canonical_lane_ci_contract_reconciliation`
  (`persona_dream_governance`, exact reread PASS).

- 2026-07-18 (Phase 16 — Recall and Behavior Evaluation, the completion boundary):
  the founding experiment's machine-decidable acceptance boundary is now CLOSED.
  `scripts/phase16_behavior_evaluation.py` returns `overall_status: PASS` for all five
  probes against the canonical dream `persona_memory/dream_dream_successor_943b01ecd9a3`,
  routing every LLM probe through the Tau text node (no direct scillm), with deterministic
  code post-checks. Receipt: `.persona-dream/revisions/rev_successor_943b01ecd9a3/phase_16_behavior_evaluation/phase16_behavior_evaluation_receipt.v1.json`.
  (a) Semantic recall returns the dream from 3 differently-worded queries (ranks 1/3/7;
  dense 0.593/0.432/0.736) while an `orbital telemetry` negative control excludes it — proof
  that recall is discriminating, not returning everything. (b) Multi-hop traversal resolves all
  14 canonical edges live to 3 source memories + 7 Watch observations + 4 ToM nodes (actual
  vertex/edge keys recorded). (c) With context assembled ONLY from live `/recall`, the persona
  uses the dream and marks it as a dream. (d) It denies literal occurrence and the
  `synthetic_origin=true`/`literal_historical_event=false` flags reread exactly. (e) Identity is
  stable: the dream loop's canonical write-set is dream+edges+ToM only (it never wrote/updated an
  identity or source record), source anchors reread literal/unchanged, and a Tau values Q&A stays
  Kai-centered/value-stable — labeled the honest slice since no standalone Embry persona-definition
  file or runnable create-persona identity suite exists. DECISIVE LESSON: the natural "trouble at
  the water" question correctly pulls the persona to the LITERAL sick-day memory, not the dream —
  a grounded-USE-of-dream probe must ask about the dream's UNIQUE psychological content (accepting
  Kai's correction without losing autonomy), which the literal memories do not encode; otherwise
  correct persona behavior reads as a probe failure. What remains is NOT machine-decidable:
  Chatterbox voice expression (acceptance item 10) and the human's subjective acceptance of the
  rendered dream video.
- 2026-07-19 (phases 13-15 routed through Tau; FIRST canonical dream-memory write):
  the DEFERRED phase-13/14 text-reasoning blocker is resolved. At Tau commit `416edc5a`
  no general text-completion node existed (panel-reviewer is image-bound; `scillm_subagent_gate`
  is a validator; `dream_packet_agent` does no in-Tau LLM; the script-writer/reviewer command
  specs are dead pointers to unsupported roles — verified by reading their contracts). A minimal
  text-only node was added to the Tau repo (commit `09e64a44`,
  `tau_coding.persona_dream_text_reasoning_agent`, branch `issue-74-ready-queue-condition-block`):
  it carries a caller **hash-recorded prompt** + **caller-defined JSON output contract**, reuses
  panel-reviewer's scillm-key resolution (`api_key_source docker:scillm-proxy`), and emits a
  `tau.persona_dream.scillm_text_reasoning_receipt.v1` receipt (prompt/contract shas, model,
  http_status, raw output). Persona-dream's `scripts/tau_text_reasoning_adapter.py` dispatches
  phase 13/14 prompts to it by subprocess into the Tau repo — **NO direct scillm from
  persona-dream**; the deterministic citation/grounding gates are UNCHANGED (the LLM only drafts,
  code decides). **Live on the ACCEPTED successor return** (`watch_gauntlet/59b9ff3155d6/cognitive_loop/`):
  phase 13 PASS (4 interpretations, all citing Watch observation ids + source-memory ids; live
  `$memory` recall confirmed, one residue id matched), phase 14 PASS (4 ToM candidates accepted,
  subset-grounded), phase 15 `LIVE_CANONICAL_PERSISTENCE`. Phase 15 now permits a canonical write
  only when a **binding agent-level acceptance receipt** (`ACCEPTED_AGENT_LEVEL`, matching return
  video sha256 + return id, step_36 & step_38 PASS) overrides the DEGRADED observation status —
  and NEVER a historical origin, renderer DEFECT verdict, or superseded id (hard blocks, 8
  fail-closed tests). **19 canonical records** written through the `$memory` API with **exact
  reread-by-key**: the synthetic dream node `persona_memory/dream_dream_successor_943b01ecd9a3`
  (`synthetic_origin:true, literal_historical_event:false`), 4 `tom_candidates` nodes, and 3
  `derived_from` + 7 `observed_in_scene` + 4 `supports_interpretation` edges. Governance record
  (`persona_dream_governance/...:cognitive_loop_canonical_write`) + phase 13/14/15 step records
  (`persona_dream_pipeline_steps`, now `Live-Proven-On-Accepted-Return`) all exact reread. Loop
  receipt `PASS_COGNITIVE_LOOP`, `canonical_dream_memory_written: true`. Boundary: Phase 16
  (Qdrant semantic recall + downstream behavior change + human subjective acceptance) remains.

- 2026-07-19 (Stage B post-return gauntlet RE-RUN — VLM routed through Tau, ACCEPTED
  at agent level; canonical loop still DRY-RUN, fail-closed): the three v1 blockers were
  all downstream of the missing VLM layer. Per the standing directive "only /tau has access
  to /scillm", every VLM call was routed through the Tau panel-reviewer node
  (`tau_coding.persona_dream_panel_agent --role panel-reviewer`, Tau commit `416edc5a`,
  custom hash-recorded `visual_review_prompt`, `api_key_source docker:scillm-proxy`) — NOT
  direct scillm from Stage B drivers. **Step 36 PASS (v2):** ArcFace whole-clip metric still
  fails (5/12 sub-threshold) but VLM adjudication classifies all 5 low-cosine frames
  `POSE_OCCLUSION` consistent with beat intent, zero substituted persons; scene/wardrobe/
  action continuity PASS; Kai scored via the recovered face-bearing reference
  `02-kai_character_sheet.png` (not contradicted). **Steps 37-38 PASS (v2):** the successor's
  authoritative line equals the frozen predecessor's rendered line (whisper
  `recognized==canonical`); re-mixing the hash-bound isolated line WAV (`c240e201`) + same bed
  (`8d5e0d3e`) reproduced a bit-identical mix (`33edae9a`), muxed onto the silent return;
  whisper `large-v3-turbo` forced alignment in-window; lip-sync `INAPPLICABLE_BY_COMPOSITION`.
  **Acceptance ACCEPTED_AGENT_LEVEL** (both fail-closed gates pass); human subjective acceptance
  still the human's. **Canonical loop still dry-run, `canonical_dream_memory_written: false`** —
  phases 13/14 text reasoning has no Tau node at 416edc5a (panel-reviewer is image-bound) and
  direct scillm is forbidden; `run_cognitive_loop.py` also hardcodes `allow_canonical_write=False`.
  Fail-closed: canonical persistence DEFERRED. Receipts under `…/rev_successor_943b01ecd9a3/…/97688ec5…/`:
  `post_kling_continuity_review_receipt.v2.json`, `step37_38_audio_final_assembly_receipt.v2.json`,
  `post_return_acceptance_receipt.v2.json`, `tau_vlm_route_verification_receipt.v1.json`,
  `tau_step36_adjudication/`, `step37_38_successor_mux/`; loop outcome
  `stageb_cognitive_loop_outcome.v1.json`. Memory: `persona_dream_pipeline_steps` +
  `persona_dream_governance` written with exact reread match=true. LESSON: the VLM was never a
  scillm-auth problem to "chase" in the drivers — it was a ROUTING problem; Tau's panel-reviewer
  already holds sanctioned scillm access and takes one composite image + a hash-recorded prompt.

- 2026-07-18 (Stage B post-return gauntlet on the LIVE successor return — ACCEPTANCE
  BLOCKED, fail-closed; canonical cognitive loop NOT run): the successor Kling return
  (`sha256:59b9ff31…`, 10.041667s, one submit, request `sha256:97688ec5…`, silent) was
  received (commit `a47fc595`) and put through the post-return gauntlet on THIS return.
  Results: Step 35 frame contact sheet PASS (12 uniform frames, single-shot clip);
  Watch gauntlet DEGRADED (per-frame VLM + transcript unavailable — scillm gpt-5.5 chat
  auth ROTATED; silent pre-mux video); Step 36 post-Kling continuity FAIL — the live
  deterministic ArcFace read (buffalo_l, CPU, threshold 0.421) vs `embry_contact_sheet_v3`
  shows the identity-source fix matching STRONGLY in the opening identity window (cos
  0.60-0.61, an improvement over the prior `EMBRY_IDENTITY_DRIFT_00_03`) but clearing only
  7/12 frames overall (mean 0.378), with the final third at cos 0.02-0.15; ArcFace alone
  cannot separate drift from pose and the VLM adjudication layer is down, so identity is
  NOT certifiable; Kai reference sheet has no detectable face (unscoreable). Steps 37-38
  audio+assembly BLOCKED (the exact Kai line was never rendered; no chatterbox engine; no
  paid authorization; VLM lip-sync unavailable). Acceptance BLOCKED; canonical cognitive
  loop NOT run — dry-run only, `canonical_dream_memory_written: false`. LESSON: two
  independent hard dependencies gate this stage in the current environment — a live VLM
  (scillm gpt-5.5 chat, auth rotated) for continuity adjudication + phases 13/14, and a
  voice render engine (chatterbox_turbo, absent) for the never-rendered exact line — and
  the fail-closed contract correctly refused to fake acceptance or write a canonical dream.
  The deterministic ArcFace identity lane DID run live and gave a genuine, mixed verdict:
  the v3 identity source helps materially where Embry is clearly the foreground subject but
  does not clear the whole-clip metric gate. Receipts under
  `.../rev_successor_943b01ecd9a3/` (`post_return_acceptance_receipt.v1.json`,
  `watch_gauntlet/59b9ff3155d6/step35_frame_contact_sheet_receipt.v1.json` +
  `step36_arcface_identity_summary.json` + `step36_embry_presence_refine.json` +
  `cognitive_loop_dryrun/`, and `phase_11_submit_return/provider_return/…97688ec5…/`
  `post_kling_continuity_review_receipt.v1.json` + `step37_38_audio_final_assembly_receipt.v1.json`).

- 2026-07-18 (qualification gate scoping — DECISIVE LESSON: exact-match gates must
  select by record TYPE, not keyspace): the step-38 requalification blocker was NOT
  record pollution — it was gate OVER-MATCH. `prepare_revision_qualification` listed
  `project_knowledge` by `(run_id, revision_id)` and required the space to hold
  EXACTLY the 27 qualification records, so 15 governance/audit records that
  legitimately share that keyspace were counted as `unexpected_keys` and blocked the
  gate. The governance records were never qualification records; the gate's intent
  was "exactly the 27 qualification records exist and reread exactly." Fix
  (`scope_qualification_documents()`, commit 1d454819): select the exact-match set by
  record IDENTITY — qualification schema AND `record_type` AND stable-key prefix must
  all agree; governance records (matching none) are readable but never counted; a
  malformed qualification claim or duplicate key fails closed; the gate is provably as
  strict as before for the 27 records (tests/test_qualification_gate_scoping.py, 8
  pass; full suite 21 pass). LESSON: an exact-match/exclusive-ownership gate that
  selects rows by keyspace membership is permanently brittle on a DELETION-FREE store
  — any other sanctioned writer that shares the keyspace makes it over-match forever,
  and you cannot "clean up" past the mismatch because nothing can be deleted. Select
  by the record's own type/schema, and route unrelated writers to their own
  collection (future governance writes now go to `persona_dream_governance`; the ten
  governance persisters were repointed; historical records stay untouched in
  `project_knowledge`). With the gate scoped, the full chain completed live: rebuild
  index (promote the accepted lane C waiver frame `sha256:9f8fb8c9`, retain phase_c as
  superseded via an invalidation ledger) → `revision_supersession`
  PASS_REQUALIFICATION_SUPERSEDED → prepare/verify/activate `--supersede`
  PASS_ACTIVE_CONSISTENT → `acceptance_rung_receipt.v5.json` = PASS_ACCEPTANCE_RUNG
  (supersedes v4). `does_not_prove` keeps Kling readiness, provider media publication,
  publication authorization, paid authorization, provider return, lip-sync-on-return.
  No paid call made or authorized.

- 2026-07-18 (Lane C step 38 fix — EXECUTED LIVE, BLOCKED by a gate conflict): the
  primary lane C plan (regenerate ONLY sb_003_end_frame so Kai's mouth is not
  camera-readable during 5.0-7.7s, keeping sb_003_start as the identity anchor) was
  run live through a new bounded driver (scripts/lane_c_regenerate_sb_003_end_frame.py)
  on the same Phase C GPT Image 2 lane (codex-oauth; embry_contact_sheet_v3 + Kai
  character sheet as reference inputs), max 5 attempts, failure-aware repair. It did
  NOT converge: FAILED_LANE_C_ATTEMPTS_EXHAUSTED. The DECISIVE LESSON is a real,
  documented tension between two unweakened gates — the hardened full-frame identity
  reviewer is FAIL-CLOSED and needs Kai's lower face (nose/mouth/chin/jaw) visible to
  ground specific-identity features, which directly conflicts with the composition
  requirement that his mouth NOT be camera-readable. Attempt 1 hid the mouth by arm
  occlusion → composition PASS but identity FAIL; attempts 2-5 kept a verifiable face
  → identity PASS (embeddings 0.64-0.81; att4-att5 also both continuity pairs PASS)
  but the mouth stayed readable → composition FAIL. GPT Image 2 could not hit the
  narrow overlap in 5 tries (att4/att5 near misses), so this is a generation-
  controllability gap, not a strict impossibility. It also exposes a design tension:
  the delta says the end-frame face is NOT required (identity anchored by the start
  frame), but acceptance criterion (a) verifies the face on the end frame for both
  characters — reconciling that is a gate-design decision reserved for a human. Per
  the fail-closed contract, the frozen revision and its canonical sb_003_end_frame are
  untouched, requalification + rung restoration were NOT attempted, and the acceptance
  rung REMAINS at v4 (not restored). Blocker + full attempt table:
  step38_lane_c_blocker_receipt.v1.json. Memory (exact reread PASS): keys
  ...:38:lane_c_sb_003_end_regen and ...:38:lane_c_blocker. No paid call.

- 2026-07-18 (embedding identity subgate — DECISIVE LESSON): identity verification
  was moved from VLM judgment to a deterministic ArcFace cosine distance, and it
  resolved the v3 impasse cleanly. VLMs (gpt-5.5 vision) are NOT metric identity
  verifiers: the run-to-run instability on known_bad_sb_001 was the model unable to
  place a face that is genuinely a near-look-alike. The fix is the standard 1:1
  verification method — InsightFace buffalo_l (w600k_r50, 512-d L2-normalized):
  detect -> 5-pt align -> embed -> cosine similarity vs a calibrated threshold
  (scripts/identity_face_embedding_subgate.py; deterministic; mockable Embedder
  interface; 11 unit tests). Wired into
  phase07_storyboard_tau_node._run_identity_continuity_review as the IDENTITY VERDICT
  AUTHORITY (full-frame VLM keeps scene/wardrobe/composition + face visibility; VLM
  face-crop demoted to advisory; code FAIL_FACE_EMBEDDING_IDENTITY_MISMATCH records
  the score; fail-closed — no InsightFace means FAIL, never a silent VLM fallback).
  Calibration v4 (reviewer_calibration_receipt.v4.json, live CPU onnxruntime) =
  REVIEWER_CALIBRATION_PASS. Measured distributions: genuine same-person (reference-
  cell pairwise) floor 0.4991; known-bad/tamper offending ceiling 0.3430; cross-person
  (Embry-vs-Kai) 0.095..0.331. Threshold 0.421 (margin midpoint), margin 0.1561.
  known_bad_sb_001 Embry cosine 0.323 -> metrically a DIFFERENT face (the adjudication
  answer, by measurement: different identity; no reclassification). positive_control_
  sb_002, over-rejected by v3's VLM crop, PASSes (Kai 0.526). All 8 accepted successor
  frames PASS the embedding subgate (0.525..0.815). Live node integration confirmed
  end-to-end: known_bad_sb_001 full-frame VLM still PASSes but the node FAILs via the
  embedding subgate. Threshold recipe for the next agent: recompute genuine (positive +
  reference-cell pairwise) and known-bad distributions and set the threshold in the
  margin; re-derive if the reference sheet changes. Install pinned insightface==0.7.3
  + onnxruntime==1.19.2 (pyproject [identity] extra; insightface_install_receipt.v1.json).

- 2026-07-18 (face-crop identity subgate — SUPERSEDED by embedding subgate above): A zoomed-in face-crop subgate DID close
  the full-frame dilution blind spot — but only for non-marginal mismatches, and it
  did NOT fully calibrate. Mechanism (scripts/identity_face_crop_subgate.py, wired
  into phase07_storyboard_tau_node._run_identity_continuity_review, additive +
  fail-closed + provenance-free): ask gpt-5.5 for face bboxes, PIL-crop the candidate
  face plus up to 3 pose-matched reference views (frontal/3-4/profile), upscale, and
  run a feature-level face-to-face comparison; full-frame AND subgate must both PASS
  (code FAIL_FACE_CROP_IDENTITY_MISMATCH). Under a strict first prompt the subgate
  correctly FAILED the residual known_bad_sb_001 that full-frame review missed —
  proving the zoom surfaces the divergence. But calibration v3 (3 subgate-prompt
  revisions, the cap) = REVIEWER_CALIBRATION_FAILED: known-bad 2/3 FAIL, tamper 1/1,
  positives 1/2 (unstable). Hard lesson: known_bad_sb_001 is a genuine NEAR-LOOK-ALIKE
  — at face-crop scale gpt-5.5 cannot separably discriminate it from the genuine
  positives, and its verdicts on borderline crops are UNSTABLE run-to-run (the same
  two crops returned SAME, then DIFFERENT, then an empty verdict across runs). Any
  prompt strict enough to fail it also over-rejected real matches on surface
  warmth/pose; any prompt lenient enough to pass real matches also passed it. This is
  a discrimination-boundary case that belongs to human adjudication, not more prompt
  fiddling. Actionable for the next agent: (1) borderline face-crop comparisons need
  best-of-N agreement or a second independent reviewer before a FAIL/PASS is trusted —
  a single call is too noisy; (2) higher-resolution crops or a dedicated face-embedding
  distance metric may separate near-look-alikes better than a VLM prose comparison;
  (3) a packaged bundle (reviewer_calibration_v3/human_adjudication_bundle) with
  side-by-side candidate vs pose-matched reference crops + one-page questions is the
  right artifact when the model sits at its discrimination limit. Restoration stayed
  WITHHELD (acceptance_rung_receipt.v3 = RUNG_NOT_RESTORED_BLOCKED_ON_REVIEWER_CALIBRATION);
  a factual blocked outcome with an adjudication bundle beats a forced pass.
- 2026-07-18 (state-clearing audit + supersession): Re-qualifying an immutable
  revision after its artifact index is rebuilt (same revision id, changed index)
  needed a sanctioned path; in Phase D it was done ad hoc by hand-deleting the
  Memory active-pointer document, the immutable queue terminal event, and the
  three qualification receipts. That deletion is now audited with verdict
  `AUDIT_PASS_NO_EVIDENCE_LOST`: every cleared item's pre-deletion content is
  recoverable — the four files byte-for-byte from git commit `a97c734e` (old
  hashes reverified: prepare `040308e2`, verify `0fc97ae5`, activation
  `86e32aec`, terminal event `f7c182a8`), and the single-slot CAS pointer by
  deterministic re-derivation from the committed old activation receipt.
  Contrary to the worst-case hypothesis, the deleted receipts were the
  git-tracked revision-tree receipts, not the gitignored `state/` ones, so git
  recovery exists. Lesson: immutable-revision re-qualification of a rebuilt index
  must never depend on that luck. Codified fix: `scripts/revision_supersession.py`
  + `activate_revision_qualification.py --supersede` replace deletion with
  retain-and-mark supersession (archive predecessors under `superseded/`,
  snapshot the old pointer as `SUPERSEDED` in Memory, append an old→new
  artifact-index entry to an append-only ledger); every other pointer mismatch
  stays fail-closed. Audit receipt
  `.../revisions/rev_successor_943b01ecd9a3/state_clearing_audit_receipt.v1.json`;
  tests `tests/test_revision_requalification_supersession.py` (3/3).
- 2026-07-17 (afternoon, persistence audit): An external agent audit of
  `rev_idea_f3f9c48d5cc2` was reconciled with receipts
  (`scripts/audit_revision_persistence.py`, receipts under
  `.persona-dream/state/revision_persistence_audit_*.json`). Confirmed real:
  the frozen Phase 01-10 index never covers post-qualification Phase 11-13
  evidence (122 request-scoped files in the old revision, now hash-bound by a
  generated request-evidence index); dead absolute-path references exist in
  frozen receipts (38 unique missing paths inside the old revision, mostly
  dead /tmp worktrees); pointer `revisionRoot` values are non-portable
  absolute paths (cosmetic: all tooling derives roots from
  run_root + revisionId). Refuted with evidence: "Memory has zero Phase 11/12
  records" is false - the step collection holds 42 records for the old
  revision including steps 21-36 with request-scoped hashes, plus
  `pd_phase11_*` boundary records; "validation.json incorrectly says provider
  submission never ran" is a misread - the run-root validation describes the
  ACTIVE revision (new request, zero calls, coherent with its unused ledger),
  not the frozen revision's consumed request. The systemic fix is the new
  post-step audit gate; the active revision `rev_upstream_bf3b05d47fb8` passes
  it with zero unexpected unindexed files and full memory reread (27 + 42 +
  boundary record for request `ca90ba9f...`).
- 2026-07-17 (afternoon): The upstream-contract reconstruction gate is done.
  `rev_upstream_bf3b05d47fb8` (source `rev_idea_f3f9c48d5cc2`) was created,
  qualified, and activated in one bounded transaction
  (`scripts/reconstruct_upstream_contract_revision.py`): the seven canonical
  files for steps 05/11/12/15 exist and validate, the step-41 invalidation
  ledger covers steps 06-42, Memory prepare/verify/activation passed
  (339/339 hashes, `activation-1662abf63c5270c9d7ca17b46ef34c76`), and 42/42
  revision-bound step records were exactly reread. Steps 06-20 were then
  hash-revalidated (9/9 consistency checks). Key lesson: stage every artifact,
  ledger, and the deterministic step-record bundle inside the revision BEFORE
  computing the index/manifest; write all post-activation receipts under
  `.persona-dream/state/` so the frozen artifact set is never mutated.
- 2026-07-17 (afternoon): The repaired SB_004 request is compiled and fixed at
  `sha256:ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f`
  with an unused attempt ledger (`PREFLIGHT_READY`, zero calls, zero submit
  intents). The repair lives in `PANEL_CONCISE_ACTIONS["sb_004"]`
  (`scripts/phase11_payload_binding.py`): Embry-only forward commit through
  the safe channel, Kai held outside, lava-reef boundary sharply readable,
  432 chars. Preflight chain: binding bootstrap at publication commit
  `8b12d4c8c5af3fff6f0de2aa1a545b502ca71ed2`, reconcile upstream validation,
  live provider snapshot, live public media probes (6 assets), canonical
  compile, adapter preflight all PASS with zero technical blockers. Gate:
  `BLOCKED_AWAITING_HUMAN_APPROVAL` for five hash-bound approvals (template at
  `phase11_authorization_packet.v1.pending.json`; max spend $0.84). No paid
  call was made.
- 2026-07-17: The corrected Phase 11 request
  `sha256:ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41`
  made one live provider submission, polled 43 times, and returned an
  18,520,578-byte H.264 1280x720 24 fps MP4 lasting 10.041667 seconds. The MP4
  SHA-256 is
  `sha256:2545394fb8e48694acb2751b25cbf6fc55a4dfdbde66e241deecfb5f2f1ecd33`.
  Twelve Watch frames were assembled into a 4x3 contact sheet and inspected.
  Post-Kling continuity is `FAIL`: identity, wardrobe, boards, setting, and
  Kai's hand signal remain coherent, but SB_004 does not visibly show Embry's
  safe-channel commit or a readable lava-reef boundary. Memory exact reread is
  42/42 with 42 semantic syncs and 42 Qdrant pointers. Final acceptance remains
  blocked on steps 05, 11, 12, 15, 36, 40, and 42. Do not resubmit: the paid
  authorization was consumed and a repaired hash requires separate authority.
- 2026-07-15: `rev_repair_a8b93ffeca8f` is a semantic-mix counterexample: its
  Phase 01 request belongs to the Tau issue-41 fixture while Phase 03-10 belong
  to the Embry/Kai surfing idea. It must not be reported `ACTIVE_CONSISTENT`.
  The repair implementation creates a new immutable revision from an explicit
  human idea, writes ten hash-chained phase bindings, verifies Memory exact and
  dense recall, and only then activates. Code presence is not migration proof.
- 2026-07-15: The live semantic-mix repair activated
  `rev_idea_f3f9c48d5cc2` for run `pipeline-complete`. The explicit human idea
  is bound through 10/10 phase lineage records. Memory exact-reread verified 27
  synchronized documents (1 revision, 10 phases, 16 required artifacts), and
  the run-scoped active pointer and terminal event
  `repair-454b255245a1a162/000001-completed.json` agree with the activation
  receipt. Live run-detail reports all ten phases `accepted_current` and
  `ACTIVE_CONSISTENT`. That qualification remains scoped to Phases 01-10 and
  does not inherit any Phase 11 provider result.
- 2026-07-16: The canonical Phase 11 pre-Kling boundary for
  `rev_idea_f3f9c48d5cc2` is now live-validated and Memory-persisted. The exact
  Standard/audio-off request body hash is
  `sha256:ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41`.
  Its four prompts are 247, 268, 362, and 271 characters; SB_003 is silent,
  `multi_prompt` is present, `end_image_url` is absent, and the adapter
  preflight passed with a request-scoped submit-once fence.
  Memory `/upsert` wrote request-scoped key
  `pd_phase11_eb5dbe1257f6152103d1ce1e2700f9582d8ef6e5fb87e90e`, `/list`
  exactly reread it and the active pointer, semantic sync is `synced`, and
  question-shaped recall returned the same identity with dense score
  `0.7866844`. Current gate: `BLOCKED_AWAITING_HUMAN_APPROVAL` for five new
  hash-bound receipts: publication authorization, visual/media acceptance,
  exact-request acceptance, cost acceptance, and paid-call authorization.
  `actual_provider_call_attempts=0`, `provider_ready=false`,
  `live_submit_ready=false`, and no provider return or Watch observation exists.
- 2026-07-16: The separately authorized request
  `sha256:9966f6b65cc323ef4780aa2109e8814d0d61c64e81e33dbb33d023679dd42e16`
  consumed exactly one attempt, request ID
  `019f6b89-e69a-7371-9b98-313a96f5f020`, and failed with HTTP 422 because
  fal does not support `end_image_url` with `multi_prompt`. Its ledger is
  `FAILED`, `submit_intent_count=1`, `actual_provider_call_attempts=1`, and
  `automatic_resubmit_allowed=false`. The failure is Memory-persisted with
  exact reread, semantic sync, and dense recall. The compiler now preserves
  `sb_004.end_frame` as continuity-only evidence instead of a provider input.
- 2026-07-16: Graham explicitly authorized all five Phase 11 decisions for
  request body
  `sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71`
  with a maximum spend of `$0.84` and exactly one generation attempt. The
  adapter submitted once and received request ID
  `019f6acb-853c-7552-bc73-ff8a6548afb1`. fal queue status reached
  `Completed`, but result retrieval returned HTTP 422 with four errors: every
  `multi_prompt[*].prompt` exceeded the provider's 512-character maximum. The
  durable attempt ledger now records `state=FAILED`,
  `actual_provider_call_attempts=1`, `submit_intent_count=1`, and
  `automatic_resubmit_allowed=false`. No MP4 was returned and Watch was not
  invoked. The compiler also exposed a false-count defect by reporting zero
  attempts while blocking on the failed ledger. A corrected request requires a
  new request hash, new hash-bound approvals, and new explicit paid-call
  authorization; the consumed authorization must not be reused.
- 2026-07-16: Phase 11 Memory identities are now request-scoped. The failed
  request is separately persisted at
  `pd_phase11_ab56b1cf2875c1c9c35871073006bdc779397deae2777732` with one
  attempt, semantic sync, and dense recall `0.75495136`; the corrected request
  uses the distinct key above with zero attempts. The old run/revision-only key
  remains backward-readable history and is no longer a write target.
- Project initialized, knowledge tracking started
- Agent is persona-dream pipeline that generates cinematic Kling Omni sequences from persona memory. Purpose: test whether an AI agent can autonomously dream about events from memory like a real person. The pipeline must be treated as a no-omission serial gate loop from request intake through final report. The full pipeline order is: Request / Idea Intake → Dreaming Persona Selection → Memory Recall → Residue Grounding → Dream Packet → Story / Video Plan → Producer Persona Selection → Producer selects Director → Producer selects Script Writer → Creative Authority Receipts → Look Lock → Script DNA → Storyboard Prompt Composition → Storyboard Panel Receipts → Panel Continuity And Repair Ledger → Panel Generation Loop → Panel Visual Review Loop → Surgical Panel Repair → Panel Repair Gate → Panel Source Receipt → Provider Media Publication Work Order → Local Provider Media Staging → Publication Preflight → Publication Authorization → Public URL Probe → Provider Media Handoff → Provider Media Lock → Kling Scene Packet → Provider Final Gate → Paid Call Authorization → Kling Submit → Kling Poll / Callback → Output Retrieval → FFprobe / Technical Validation → Frame Contact Sheet → Post-Kling Continuity Review → Voice / Audio Handoff Lane when voiced → Final Assembly / Movie Lane → Report Generation → Gate Validation Loop → Upstream Revision Invalidation → Final Acceptance Boundary.
- 2026-06-30: **Do not omit the creative authority layer.** Producer Persona Selection, Director Selection, Script Writer Selection, and Creative Authority Receipts are mandatory upstream gates. Producer owns creative arbitration and run-level decisions. Director owns camera, lens, blocking, lighting, color grade, pacing, and visual continuity. Script Writer owns dialogue, story pressure, beat logic, scene tension, reveal structure, and Script DNA. Changes to producer/director/script-writer selections invalidate Look Lock, Script DNA, storyboard, panels, provider packets, reports, and downstream receipts unless a migration receipt proves derivation from the current upstream revision.
- 2026-06-30: Multi-scene hardening should reuse the same per-scene serial loop, but must namespace every scene/panel artifact. Do not use singleton paths such as `receipts/kling_scene_packet.json`, `receipts/panel_source_receipt.json`, or `receipts/panel_repair_gate_receipt.json` as mutable shared state for multi-scene runs. Use per-scene directories such as `scenes/scene_001/receipts/...`, aggregate only from immutable per-scene receipts, and fail the aggregate gate if any scene is blocked or stale. This prevents the observed class of regression where a later packet-install step copied an older singleton panel repair receipt back into the run root.
- 2026-06-30: Historical one-scene proof/report state used the Tau issue-41 fixture. Its old `15/15` report claim is superseded and is not evidence for the current Embry/Kai revision. The checked-in validation later reported only `12/15`, so neither report may be used as Phase 11 readiness proof.
- 2026-06-30: Multi-scene live image smoke now has real Scillm/Codex OAuth evidence, not fake workers. Command: `./run.sh multiscene-live-smoke --run-root /tmp/persona-dream-multiscene-live-20260630T020933Z --scene-count 2 --max-workers 2 --auth codex-oauth --model gpt-image-2 --quality high --image-timeout-s 900 --json`. Receipt: `/tmp/persona-dream-multiscene-live-20260630T020933Z/receipts/multiscene_live_smoke_receipt.json`; validation: `/tmp/persona-dream-multiscene-live-20260630T020933Z/receipts/multiscene_live_smoke_validation.json`; status `PASS`, `mocked:false`, `live:true`, `scene_count:2`, `max_workers:2`, `forbidden_singleton_receipts:[]`, `kling_called:false`, `paid_call_authorized:false`. Scene 001 contact sheet SHA `6834a68f2486be56accde3b5265deb28948ad7d2778fdfcfc5d97bb6394a7ae0`, panel SHA `eee1bb993e70b400f048e04908ed4da2832245ef8a3085f867411416c1211413`; Scene 002 contact sheet SHA `22ef9ba1a241321ebbf6e44637d40fe75b7c991708d965f0b228579acff80cab`, panel SHA `e3341e3029435f60c67caef77bb49b149300500adc970b034c397818da33fef6`.
- 2026-06-30: Live bug fixes found while hardening multi-scene: (1) Scillm project-agent doctor used stale shell `SCILLM_PROXY_KEY=sk-dev-proxy-123` while the running Docker proxy had a different local master key; fixed `scripts/sanity_project_agent_scillm_calls.py` to resolve the running proxy key and propagate it to child proof scripts. (2) `scripts/generate_image.py --auth codex-oauth` falsely reported Codex OAuth unavailable when called outside the Scillm import environment; fixed it to inspect `CODEX_HOME/auth.json`. (3) `generate_image.py` could hang after Codex had already written the requested PNG and receipt; fixed it to treat matching output+receipt as terminal evidence and terminate the child process. These were Scillm wrapper/runtime bugs, not Tau bugs, so no Tau ticket was filed.
- 2026-06-30: Multi-scene report artifact: `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/reports/multiscene-live-smoke/report.html`, generated from the live multi-scene receipt and validation. Served at `http://127.0.0.1:8898/report.html` during verification. CDP screenshot: `/tmp/codex-ui-verification/agent-skills/persona-dream-multiscene-live-report/20260630T021733Z.png`; marker/read JSON: `/tmp/codex-ui-verification/agent-skills/persona-dream-multiscene-live-report/20260630T021733Z.read.json`. Visual inspection confirmed the report shows real scene images and summary fields.
- 2026-06-30: The report generator caught a false-green regression from stale singleton receipts: `write-one-scene-kling-review-packet` reinstalled an older `panel_repair_gate_receipt.json`, causing provider eligibility to revert to false and the public probe URL to become missing. The repair was deterministic: copy the passing live probe receipt back to `receipts/provider_media_probe_receipt.json`, run `apply-provider-media-public-probe`, rewrite `panel_source_receipt.json`, reinstall the blocked Kling packet, and rerun the complete pipeline report. This lesson reinforces that timeouts, empty outputs, stale receipts, and overwritten singleton receipts must fail gates, not be summarized as accepted.
- 2026-06-19: patch_pipeline_report_ui design pass adds gate summary banner, section pass/fail badges, provisional downstream sections after blocked gates, 5-column panel storyboard table, deduped panel breakdown, collapsed contact-sheet provenance.

- 2026-06-23: **Harness phase repair accepted locally** (pending WebGPT phase review). Do **not** rewrite `medium_loop_dag_smoke.py` unless a live rung fails preflight. Keep it as the local serial proof ladder. Broken piece was viewer + artifact sync + overclaiming, not core Python rungs. Viewer now uses `TransportReactFlowDagWorkspace` via `personaDreamDagEvidenceAdapter.ts` (~247-line shell). Install fresh artifacts with `scripts/install_dag_harness_artifacts.py`. Route: `http://localhost:3002/#scillm/dag-harness`. Live PASS on 2026-06-23 for `scillm-one`, `scillm-two-concurrent`, `real-gates`.
- 2026-06-23: **Stop and ask human** when blocked or confused — codified in `.cursor/rules/stop-and-ask-human.mdc` and `~/.codex/AGENTS.md`. Do not spiral; wait for human scope/acceptance choices.
- 2026-06-23: **Agent anti-spiral rules** codified in `.cursor/rules/proof-ladder-scope-lock.mdc` and `~/.codex/AGENTS.md` (Proof Ladder And Harness Scope Lock). Key rule: if the next command does not produce an inspectable artifact answering the exact question, do not run it.
- 2026-06-22: The recent DAG/harness work must be treated as a failed/drifted implementation attempt, not proof of readiness. `scripts/medium_loop_dag_smoke.py` currently proves only a narrowed local serial gate smoke for real persona-dream Phase 2, Phase 5, and Phase 6 commands on the correct run root, plus an opt-in one-node `$scillm` HTTP probe. It does not import or execute `ScillmDagHarness`, does not prove deterministic model generation, does not prove a bounded semantic self-improvement loop, and does not prove no-paid/no-live enforcement.
- 2026-06-22: The first non-mocked `$scillm` HTTP/service call node now exists: `--include-scillm-probe --stop-after-scillm-probe` generates `scillm_oneshot_probe.py`, calls `POST http://localhost:4001/v1/chat/completions` via `httpx.AsyncClient`, and validates exact JSON. Last observed receipt: `/tmp/persona-dream-real-dag-i_7ogn11/repo/.loop/context/scillm-oneshot-probe-receipt.json` with HTTP 200, `ok: true`, model `gpt-5.5`, and parsed content `{"ok": true, "answer": "persona-dream-scillm-probe"}`. Do not add panels, WebGPT, voice, React Flow, Kling, provider packets, or multi-agent orchestration until the next rung, two concurrent `$scillm` calls, passes.
- 2026-06-22: The canonical human/project-agent review surface is `http://127.0.0.1:8892/full-report.html`, backed by `/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict`. Do not use stale `r13` run roots for Phase 5/6 proof.
- 2026-06-29: One downstream persona-dream slice now has local proof from real Scillm panel image generation through Scillm VLM review into the Tau serial creator/reviewer/repair-gate harness, ending at a dry-run one-scene Kling request. Evidence root: /tmp/persona-dream-scillm-panel-proof-20260629T1536. Scillm doctor receipt /home/graham/workspace/experiments/scillm/.scillm/proofs/project_agent_sanity/20260629T153621Z/receipt.json reports PASS for 13/13 lanes. Image receipt /tmp/persona-dream-scillm-panel-proof-20260629T1536/artifacts/images/panel_001_receipt.json reports ok=true, 1672x941, sha256=5d2456775e28b649bc82ce898751dd5e124366536282b8fb5d46f7ba9fe16366. VLM receipt /tmp/persona-dream-scillm-panel-proof-20260629T1536/receipts/live_scillm_vlm_visual_review_receipt.json reports status=PASS over Scillm gpt-5.5 image_url. Tau proof /tmp/persona-dream-scillm-panel-proof-20260629T1536/tau-proof-final/manifest.json reports mocked=false, live=true, selected agents panel-creator -> panel-reviewer -> persona-dream-panel-repair-gate, command_exit_codes=[0,0,0], first_blocker=null, and dry_run_one_scene_kling_request populated. This does not prove the full dream packet/story/contact-sheet/panel-prompt upstream, multi-panel while loop, public media publication, or live Kling call.
- 2026-06-29: The next backward-working Tau integration proof used real panel 01 upstream source `/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict/storyboard/panel_repair_gate/first_batch_work_orders_20260614T044000Z/panel_01_work_order.json` as the prompt source for `tau persona-dream-panel-proof --scillm-live-panel`. Evidence root: `/tmp/persona-dream-panel01-live-tau-upstream-proof-20260629T1745`. Tau generated `/tmp/persona-dream-panel01-live-tau-upstream-proof-20260629T1745/scillm-panel/panel_001.png`, VLM review receipt reports `status:PASS`, and Tau manifest reports `mocked:false`, `live:true`, `scillm_originated_inside_tau:true`, `command_exit_codes:[0,0,0]`, `first_blocker:null`, and dry-run `one_scene_kling_request.json`. The serial persona-dream pipeline still blocks because Tau's terminal repair receipt is not the canonical persona-dream repair-gate/source contract: `write-panel-source` exits `1` with `repair_gate_schema_not_persona_dream_panel_repair_gate_receipt_v1`, missing subgate statuses, `generated_image_path_missing`, and `claimed_media_hash_missing`; `pipeline-loop-run ... --max-iterations 1` exits `1` at `missing_panel_source_receipt_path`. Tracked in Tau issue https://github.com/grahama1970/tau/issues/33. No public upload or live Kling call was performed.
- 2026-06-29: After Tau issue #33 was resolved at Tau commit `b0131c1`, the canonical issue-33 proof root `/home/graham/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/issue-33-live-persona-dream-20260629T180606Z` advances through canonical Kling packet, local provider media lock, publication work order, and local provider-media staging. `pipeline-loop-run --max-iterations 1` wrote `storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_001_local_staging_receipt.json` with `status:PASS_PROVIDER_MEDIA_LOCAL_STAGING`, staged bytes at `/home/graham/workspace/experiments/agent-skills/skills/persona-dream/provider_media/issue-33-live-persona-dream-20260629T180606Z/panel_001.png`, and locked SHA-256 `sha256:3ef0ab7722d6742adf0c4e2b19a325f3e0cdaa761f8459e49329b2737a5d99fa`. The current first blocker is now `provider_media_publication_authorization`: missing `receipts/provider_media_publication_preflight.json`, requiring explicit authorization for public upload/git push or equivalent public asset publication. No public upload, live URL probe, live Kling call, or paid provider call was performed.
- 2026-07-03: Phase 04 Contact Sheets is live-wired but not complete. Tau ran the contact-sheet creator/reviewer/build/reviewer loop with live:true and mocked:false. A real Codex OAuth image generation created and indexed the Embry surfboard contact sheet at /mnt/storage12tb/skills/persona-dream/outputs/embry-kai-surf-phase04-contact-sheets-20260702/artifacts/images/contact_sheet_embry_surfboard.png with receipt /mnt/storage12tb/skills/persona-dream/outputs/embry-kai-surf-phase04-contact-sheets-20260702/artifacts/images/contact_sheet_embry_surfboard_receipt.json and sha256 d4052937952bb14e5be77c25b262e30d92822068f5af26dd6cb69d7f03240216. It was inserted into memory collection persona_dream_visual_assets and Qdrant collection persona_dream_visual_assets_v1. The Tau builder originally missed persisted contact sheets because semantic /recall is insufficient for exact visual-asset gates and _compact_memory_recall_item dropped image_path/asset_id. Tau was patched at /home/graham/workspace/experiments/tau/src/tau_coding/persona_dream_dream_packet_agent.py to exact-query persona_dream_visual_assets via /list filters entity_id and asset_id before semantic recall, and to preserve asset_id, entity_id, entity_type, title, image_path, url, and source in compacted recall items. Targeted Tau test /home/graham/workspace/experiments/tau/tests/test_persona_dream_dream_packet_agent.py passes with 7 passed. Post-patch build receipt /home/graham/workspace/experiments/agent-skills/skills/persona-dream/reports/pipeline-complete/phase_04_contact_sheets/contact_sheet_build_receipt.json remains BLOCKED_CONTACT_SHEET_BUILD with attached_asset_count 1 and blocked_asset_count 4. Remaining required sheets are Kai surfboard, June Swell, Lava Reef, and Kona Coast. Do not mark Phase 04 READY until those required assets are generated, indexed, attached, and the contact-sheet artifact gate passes.
- 2026-07-04: Phase 06 Script has a deterministic Tau script-writer/script-reviewer contract path wired into ux-lab, but it is not yet the full GPT-5.5/Kimi live creator-reviewer loop. Changed files include tau/src/tau_coding/persona_dream_dream_packet_agent.py, tau agent-command-specs/script-writer and script-reviewer, pi-mono/packages/ux-lab/server/index.ts, and skills/persona-dream/ui/src/DreamWorkspace.tsx. Current API evidence: GET http://127.0.0.1:3001/api/tau/dream/script-draft/latest returns ok=true, status=PASS_SCRIPT_CONTRACT, script length 2114 chars, 7 interaction-matrix coverage rows, and 15 asset-usage rows. Current artifact: /home/graham/workspace/experiments/tau/experiments/goal-locked-subagents/proofs/persona-dream-script-ui-dispatch/script-ui-20260703T230200Z/run/script_contract.json. CDP marker: /tmp/codex-ui-verification/agent-skills/dream-script-phase06-hydrated-script-after-vite-restart/20260703T232408Z.read.json. Remaining known UI issue: right sidebar may still show stale MISSING_EVIDENCE copy even when the central Script pane hydrates the PASS_SCRIPT_CONTRACT artifact.
- 2026-07-04 correction: A fresh status poll of GET http://127.0.0.1:3001/api/tau/dream/script-draft/latest after the Phase 06 knowledge update returned ok=true, status=PASS_SCRIPT_CONTRACT, script_chars=2114, coverage=7, assets=14. Treat 14 asset-usage rows as the current observed API count unless a newer script_contract.json receipt proves otherwise.
- 2026-07-06: Phase 07 storyboard failure mode: the multi-day blocker was not primarily a card/layout problem. The panel prompt and reviewer gate let character identity become secondary to wide establishing-shot composition, reef/location beauty, and crowd/lineup context. For identity-critical storyboard panels, priority must be: required character identity match > faces visible and reference-verifiable > character-readable composition > location/reef/cinematic details. Use medium-wide foreground two-shots when Embry/Kai are required, and pass Embry/Kai reference sheets as actual image inputs/attachments, not only local path text.
- 2026-07-06: If the human shows a visual counterexample for a persona-dream panel, stop UI/status-copy work and inspect the generated prompt, reference attachment route, reviewer schema, and acceptance gate. Do not spend further cycles styling around bad imagery. The next artifact must be a corrected Tau creator/reviewer run receipt or a precise blocker proving why regeneration cannot proceed.
- 2026-07-13: Historical qualification of `rev_repair_a8b93ffeca8f` is superseded by the July 15 semantic-lineage validator. That revision is a rejected semantic-mix counterexample, not the current active authority.
- 2026-07-15: The earlier Phase 11 receipt-only state at commit `972d1a2c` was
  not Memory-persisted or live-submittable. It is retained as the regression
  baseline and is superseded by the 2026-07-16 canonical compiler, adapter
  preflight, fail-closed validation, and Memory persistence evidence above.
- 2026-07-17: Phase 11 boundary restore exists as task commit `8ed796cb2 persona-dream: finish phase11 boundary restore`, but it is not on `origin/main` (`git merge-base --is-ancestor 8ed796cb2 origin/main` returned exit 1). A clean `origin/main` worktree cherry-pick attempt proved the commit is superseded, not simply missing: main already has newer Phase 11 lineage commits including `2638b7c persona-dream: add canonical phase 11 boundary`, `c53d68a persona-dream: make phase 11 artifacts portable`, `5214240 persona-dream: clear phase 11 technical blockers`, `5a30f24 persona-dream: add phase 11 canary adapter`, `bbc1c4c fix(persona-dream): bind revisions to explicit human idea`, `a4c9ca6 feat(persona-dream): bind and persist Phase 11 preflight`, `54aa25a fix(persona-dream): scope Phase 11 requests and memory evidence`, and `d249e36 fix(persona-dream): reject multi-prompt end image`. Do not cherry-pick `8ed796cb2` to main. The required main action is to push this knowledge correction after proving the current main Phase 11 path; this is not full pipeline progress, Dreamer readiness, or provider readiness.

## Recent Decisions

| Date | Decision | Why |
|------|----------|-----|
| 2026-06-16 | Initialize project knowledge | Enable shared human/agent context |
| 2026-06-16 | Panel beats must include explicit prop motion cues | Foreground prop behavior gate requires visible motion for tea steam, paper lift, screen reflections, sky-eye blink, umbrella ripple, Tyranid movement. Vague beats like 'Horus speaks' fail the gate. |
| 2026-06-16 | Combined creature/environment reference sheets accepted as PASS | Tyranids and void-world are visually inseparable. Single combined sheet serves visual continuity better than two disconnected sheets. Update validate_phase_05_contact_sheet_gate.py PARTIAL_IDS set when accepting combined sheets. |
| 2026-06-16 | Voice clone submission should be automatic in autonomous mode | SKILL.md now has automated voice clone submission after voice-segment-selector produces a 30s WAV. Manual listen review is optional — the selector candidate WAV IS the acceptance. In autonomous (non-dry-run) mode, the agent submits the Kling voice clone API call automatically without waiting for human approval. |
| 2026-06-16 | Kling voice clone API discovered and working | API base: api-singapore.klingai.com. Auth: JWT with HS256, no auth endpoint. Voice name max 20 chars. voice_url must be public URL (no file upload). Tested: auth OK, name too long returns 400, multipart unsupported. WAV files are local and need public hosting before clone call can succeed. |
| 2026-06-16 | Kling voice clone succeeded — voice IDs obtained | Horus voice_id=895864972788502540, Embry voice_id=895864973321830413. Cost: /usr/bin/zsh.05 each. The SKILL.md voice automation now includes the actual voice_id values so the agent uses them directly in downstream panel generation (<<<voice_1>>>, <<<voice_2>>>). The blocker is fully resolved. |
| 2026-06-16 | Panel auto-repair loop requires 8 validations per iteration | Subagent loops generate → validate → fix → re-validate with 8 specific checks: characters, props, environment, creatures, effects, script/dialogue, scale, motion cues. Max 5 retries per panel. Surgical fix only — never regenerate from scratch. FAILED_HARD after max retries. |
| 2026-06-16 | Panel repair uses $loop skill — not manual loop simulation | The $loop skill (skills/loop/) is the proper bounded harness for panel generation iteration. It owns explorer → coder → checks → code-reviewer → repair. The subagent provides objective, target file, and check command per panel. $loop handles retry and receipt. Never simulate the loop manually. |
| 2026-06-16 | review-panel skill created as CI runner | skills/review-panel/ is the CI harness for storyboard panel review. It invokes the panel-reviewer subagent ONCE per panel — the subagent owns all repair iteration context internally (up to 5 surgical retries via $loop + create-image). The runner patches index.html diagnostic table and emits SubagentSnapshot progress for ux-lab/subagent-monitor. FAILED_HARD after max retries. Never implement review or repair logic in the runner. |
| 2026-06-16 | Panel image generation uses /create-image — not bespoke API calls | The /create-image skill handles all image generation with backend fallback (FLUX, Gemini, scillm).  handles iteration. /scillm handles LLM proxy. Never call image APIs directly — always route through /create-image for dimension validation and fallback. |
| 2026-06-20 | Upstream changes invalidate downstream dream artifacts | Any change to idea, memories, story, characters, producer, scriptwriter, director, camera, lighting, contact sheets, script, panel intent, voice plan, provider constraints, or gate policy marks affected downstream artifacts stale. The agent must regenerate impacted story/script/references/prompts/panels/text/camera/lighting/provider packet from the current upstream revision, not merely reconcile receipts. Completion requires `unresolved_panel_image_errors == 0`, `unresolved_panel_text_errors == 0`, and `all_downstream_artifacts_match_current_upstream_revision == true`; otherwise Kling/provider readiness remains blocked with explicit findings. |
| 2026-06-22 | `medium_loop_dag_smoke.py` default scope narrowed to cheap real gates only | Default run excludes panel repair and voice clone because those paths triggered expensive, slow, stale WebGPT/panel activity during a harness sanity check. Default gates are Phase 2, Phase 5, and Phase 6 only. Optional flags may include panel repair or voice clone, but those are not part of the minimal harness proof. |
| 2026-06-22 | Added opt-in real `$scillm` httpx one-shot probe | `--include-scillm-probe --stop-after-scillm-probe` runs only `scillm_oneshot_probe`, calls localhost `:4001` with `httpx.AsyncClient`, validates exact JSON, streams JSONL events, and writes `scillm-oneshot-probe-receipt.json`. This is a service-call proof only, not ScillmDagHarness or Dreamer proof. |
| 2026-06-22 | Do not cite the local serial runner as ScillmDagHarness evidence | A reviewer correctly identified the runner as a bespoke serial subprocess recipe interpreter. It ignores or does not prove many DAG semantics such as topological scheduling, cycle detection, real retry behavior, strict schema validation, unconditional aggregation on failure, process-tree cleanup, and provider/network isolation. |
| 2026-06-22 | Final panel repair must not use Nano Banana/Gemini final imagery | Final panels must be photorealistic and match the accepted contact/reference sheets. Use `$create-image` / `$scillm` GPT image path with receipts for final repair. Nano Banana/Gemini/non-photorealistic storyboard images must fail panel review rather than be accepted or patched around in the report. |
| 2026-06-22 | Report/UI edits require source backup and visual proof | Prior edits repeatedly removed or degraded sections: sticky header/lucide navigation, Producer, Voice/Orpheus-TTS controls, complete Script, panel text prompts, and panel intent details. Future edits must start from backup/source truth, preserve sections, and verify with rendered screenshot before making any green/ready claim. |
| 2026-06-30 | Full persona-dream pipeline steps must not be omitted | The canonical pipeline includes Request Intake, Dreaming Persona, Memory, Residue Grounding, Dream Packet, Story/Video Plan, Producer, Director, Script Writer, Creative Authority Receipts, Look Lock, Script DNA, Storyboard, Panel Ledger, Panel Generate/Review/Repair, Provider Media, Kling Packet, Provider Final Gate, Paid Authorization, Kling execution/poll/retrieval, ffprobe, frame contact sheet, continuity review, audio handoff, final assembly, report, gate loop, upstream invalidation, and final acceptance boundary. Future status/report answers must label implemented vs intended/missing behavior instead of silently compressing this list. |
| 2026-06-30 | Multi-scene is the same loop only after path namespacing and aggregation are hardened | Reuse the one-scene validators per scene, but store scene receipts under scene-scoped paths and aggregate from immutable scene manifests. Singleton root receipts may be used only as derived rollups, not as authoritative mutable per-scene state. |
| 2026-06-30 | Live Kling remains a separate paid-call boundary | A prepared `kling.scene_packet.v1` with provider media is not a live execution. Live Kling requires an explicit paid-call authorization receipt plus submit/poll/download/ffprobe/frame-contact-sheet/continuity-review receipts. |
| 2026-07-03 | Phase 05 voice selection may be autonomous only through a creator/reviewer contract | Agents may discover candidate public/provided/local/synthetic voice references, extract clean clips, render Chatterbox demos, and select defaults, but the phase must write `voice_candidate_bundle.json` and `voice_selection_receipt.json` with provenance, rights notes, live non-mocked demo receipts, tone metadata, and reviewer rationale. Silent final voice locking is not accepted. |
| 2026-07-06 | Phase 07 storyboard prompts must be identity-first for character panels | Wide establishing-shot prompts caused plausible surf/location frames with wrong or unverifiable Embry/Kai identities. Character panels must require foreground, reference-matched, face-visible Embry and Kai before surf composition, reef visibility, crowd pressure, or cinematic beauty. Avoid weak wording like 'for continuity only' for identity references. |
| 2026-07-06 | Failed identity review invalidates accepted storyboard frames | A generated storyboard frame cannot remain ACCEPTED_START_FRAME or ACCEPTED_END_FRAME when identity_continuity_review.status is FAIL. Reviewer failure must downgrade the frame, write a blocker, and force Tau creator/reviewer regeneration instead of letting the UI display or package the image as accepted. |
| 2026-07-14 | Phases 01-10 require an immutable ACTIVE_CONSISTENT revision before acceptance | Accepted-looking local files are insufficient. Qualification requires hash-bound local artifacts, exact Memory records, Qdrant semantic sync, a deterministic active pointer, and a terminal repair event. Provider submission remains a separate Phase 11 boundary. |
| 2026-07-15 | Phase 11 receipt edits are not provider lifecycle implementation | Do not call the Phase 11 preflight complete from credential, price, schema, or payload receipt fields alone. Readiness requires a corrected compiler with audio-consistent prompts, tests and `run.sh` integration, fail-closed report validation, Memory persistence, exact payload-bound approvals, and submit-once/poll/download receipts. |
| 2026-07-16 | Phase 11 may await humans only after technical validation and Memory proof | `BLOCKED_AWAITING_HUMAN_APPROVAL` is valid only when the active revision chain, exact request, media bindings, fresh provider evidence, adapter preflight, submit-once fence, Memory exact reread, semantic sync, and dense recall pass with zero provider attempts. |
| 2026-07-16 | A failed authorized canary consumes the one-attempt authorization | Request `444a5a27...` was submitted once and rejected by fal result validation because all four shot prompts exceeded 512 characters. Never reset or reuse its ledger; a repaired request must have a new hash and separate explicit authorization. |
| 2026-07-16 | Phase 11 Memory identity is exact-request scoped | Run/revision-only keys collide when a repaired payload is compiled. New Phase 11 writes include `request_body_sha256` in the deterministic key so failed and corrected requests coexist without merge residue. |
| 2026-07-16 | `multi_prompt` and `end_image_url` are incompatible on the selected fal endpoint | Live request `9966f6b6...` returned HTTP 422: `End Image Url is not supported with Multi Prompt`. Keep the accepted end frame as continuity-only evidence, omit it from the request body, and reject this field combination before submission. |
| 2026-07-17 | Do not cherry-pick obsolete Phase 11 restore commit to `main` | The active branch `battle-ux8-live-contract` is dirty and `ahead 80, behind 203` relative to `origin/main`, so direct push is unsafe. A clean main worktree proved `8ed796cb2` conflicts with newer Phase 11 files already on main; treat it as superseded and integrate only the knowledge correction after focused proof. |
| 2026-07-18 | An identity-first qualified reference produces first-attempt storyboard passes | Regenerating the eight Phase 07 frames of `rev_successor_943b01ecd9a3` against the qualified `embry_contact_sheet_v3` identity source (not the rejected montage) yielded 8/8 frames PASS actual-pixel identity review on the first attempt each, with 7/7 inter-frame continuity pairs PASS and zero repair loops. Qualifying the identity reference before generation is what removed the repair-loop churn; the storyboard reviewer only needed to confirm, not correct. |
| 2026-07-18 | DECISION (future phase, not implemented): two-wave concurrent frame generation | Once the pipeline is stable, switch storyboard frame generation to a two-wave concurrent scheme — 4 start frames generated in parallel, then 4 end frames in parallel, with reviews pipelined. Full parallelism is forbidden because the continuity chain (each end frame binds to its start, each next start to the prior end) requires ordering between waves. The multiscene live smoke already proved parallel Scillm generation with per-scene namespacing, so the concurrency primitive exists; this is a scheduling change to adopt in a later phase, not now. |
| 2026-07-18 | LESSON: gates must be checked pairwise for satisfiability on the same artifact — the delta already held the answer | The step-38 lane C ran five attempts against two gates that had no overlap on one frame: a fail-closed full-frame identity reviewer needs Kai's face groundable, while the composition contract needs his mouth non-readable. No generation can satisfy both, so the loop exhausted. The resolution was not a better prompt or a bigger budget — it was already written in `step38_sb_003_composition_delta_proposal.v1.json`: the end frame set Kai's `face_required=false`, anchored to the unchanged start frame. The prior acceptance criterion (a) re-imposed the face check the delta had removed, recreating the contradiction. Implementing the delta's design as a scoped, fail-closed anchored-identity waiver (`scripts/anchored_identity_waiver.py`, 12 unit tests) made lane C PASS on the first attempt. Before burning attempts on a gate conflict, check whether the two gates can both hold on the same artifact and whether a prior decision already resolved it. A second lesson surfaced in the same run: the Embry-only end-frame review must be scoped to Embry — the shared reviewer prompt hard-requires both faces, so it re-failed over the waived, deliberately-turned-away character until scoped. A third: a genuine, pre-existing blocker (governance/audit memory records collide with the qualification prepare gate's exclusive-ownership requirement, and the Memory daemon exposes no deletion primitive) blocks requalification/rung v5; it was recorded fail-closed rather than forced by deleting audit records or weakening the gate. |

## Open Questions

- [x] Which exact `$scillm` localhost HTTP endpoint/model should the first non-mocked one-shot proof use? `POST /v1/chat/completions`, model `gpt-5.5`, `X-Caller-Skill: persona-dream`.
- [x] Two concurrent `$scillm` client calls rung (`scillm-two-concurrent`) — live PASS 2026-06-23 with overlap receipt.
- [ ] Where should the real ScillmDagHarness-backed runner live after the one-node `$scillm` proof passes?
- [ ] What is the canonical schema for streamed node events and receipts before adding concurrency or `$loop`?
- [ ] Which report generator owns `full-report.html` section restoration so manual HTML edits stop deleting work?
- [ ] Should Phase 07 panel-reviewer require a structured per-identity JSON schema with visible, matches_reference, confidence, face_visible, failure_code, and visible_evidence fields before PASS?

## Key Files

| File | Purpose |
|------|---------|
| PROJECT_KNOWLEDGE.md | Shared project knowledge |
| `scripts/medium_loop_dag_smoke.py` | Local serial proof ladder (fixture, scillm-one, scillm-two-concurrent, real-gates). Not ScillmDagHarness. |
| `/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict/pipeline_review_8892/full-report.html` | Human/project-agent report surface served at `http://127.0.0.1:8892/full-report.html`. |
| `/mnt/storage12tb/skills/persona-dream/outputs/20260612-horus-embry-storyboard-first-scillm-strict/pipeline_review_8892/panel_verdicts/summary.json` | Panel-review evidence summary; last known problematic repair run reported panel 06/08/09 blocked. |
| `local/HANDOFF.md` | Current handoff for the next model; overrides older stale handoff claims. |
| `scripts/install_dag_harness_artifacts.py` | Copy latest proof dirs into ux-lab `public/scillm-dag-runs/`. |
| `docs/DAG_SMOKE_AGENT_GUIDE.md` | Required claim language for each rung. |
| `pi-mono/.../personaDreamDagEvidenceAdapter.ts` | Artifact → TransportDagEvidence adapter for harness viewer. |
| `reports/pipeline-complete/report.html` | Historical one-scene report; its old 15/15 claim is superseded and must not be used as current Phase 11 readiness evidence. |
| `reports/pipeline-complete/status.json` | Machine-readable command evidence for the complete one-scene pipeline report. |
| `reports/pipeline-complete/validation.json` | Historical report validator output; checked-in state reports 12/15 and is not a current green boundary. |
| `scripts/run_multiscene_live_smoke.py` | Real Scillm/Codex OAuth multi-scene smoke. Generates scene-scoped contact sheets and panels, writes per-scene manifests, and refuses singleton receipt collisions. |
| `scripts/validate_multiscene_live_smoke.py` | Independent validator for multi-scene live smoke receipts, image hashes, scene manifests, and Kling boundary fields. |
| `scripts/write_multiscene_live_report.py` | Source-derived HTML report generator for multi-scene live smoke receipts. |
| `reports/multiscene-live-smoke/report.html` | Latest multi-scene live smoke report generated from `/tmp/persona-dream-multiscene-live-20260630T020933Z`. |

## Infrastructure State

<!-- Auto-populated from /project-state --quick -->

## Cognitive Loop 13-15 (appended 2026-07-18)

- 2026-07-18 (cognitive loop 13-15 implemented + live-slice proven on the
  historical return): persona-dream phases 13 (self-interpretation), 14 (ToM
  validation), and 15 (dream persistence) moved from Designed to Implemented.
  Interpretive drafting uses scillm gpt-5.5; grounding is enforced by
  DETERMINISTIC code, not the LLM. Phase 13 rejects any claim that does not cite
  at least one Watch observation id AND at least one source-memory id, and (the
  honesty rule) rejects any claim that reads a proven renderer defect (identity
  DRIFT) as psychological truth instead of favoring the renderer-defect
  explanation. Phase 14 lets the LLM propose bounded ToM candidates but rejects
  any whose citations are not a subset of their parent accepted interpretation.
  Phase 15 defaults to dry-run: it emits an exact canonical would-write plan
  (dream memory doc with `synthetic_origin:true, literal_historical_event:false`;
  `derived_from` / `observed_in_scene` / `supports_interpretation` edges; a Qdrant
  embedding note) with hashes and ZERO canonical writes.
- DECISIVE BOUNDARY: a canonical dream-memory write requires
  `--allow-canonical-write` AND a non-superseded return id, and HARD-FAILS
  (exit 1) on the historical `991c311f365f` return because it is a historical
  provider return, has a DEGRADED observation status, and carries an identity
  DRIFT verdict. The write path was instead proven by 16 exact-reread-matched
  documents in the non-canonical `persona_dream_loop_validation` collection.
  Enforcement is covered by `tests/test_cognitive_loop_phases.py`
  (`test_superseded_historical_return_is_blocked_even_with_allow_flag`).
- Live loop receipt: `run_cognitive_loop.py` -> `PASS_COGNITIVE_LOOP`; artifacts
  under `.persona-dream/revisions/rev_successor_943b01ecd9a3/cognitive_loop/991c311f365f/`.
  Governance persisted (write + exact reread) to `persona_dream_governance`.
  Note: `lessons` collection rejects writes without extractable taxonomy, so
  scoped governance uses a dedicated collection.
- NOT PROVEN: this is fixture-and-live-slice proof on a SUPERSEDED historical
  return. The closed-loop research claim (Acceptance items 4-8: canonical
  persistence, Qdrant recall, multi-hop traversal, later behavior) still requires
  a freshly authorized, non-superseded successor return.
