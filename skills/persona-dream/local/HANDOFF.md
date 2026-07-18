# Handoff Report: Persona Dream

**Timestamp:** 2026-07-18
**Repository:** `/home/graham/workspace/experiments/agent-skills-main` (branch `main`)
**Skill root:** `skills/persona-dream`
**Immutable goal status:** `BLOCKED_FINAL_ACCEPTANCE`
**Active revision:** `rev_upstream_bf3b05d47fb8`

## 1. Project Overview

The immutable goal is to produce a working, human-accepted Kling video through
the 42-step Persona Dream pipeline. Every step must have a durable Memory write
and exact reread. A voiced run also requires an exact transcript render, forced
alignment, audible muxed output, and accepted visible-speaker lip sync.

The current run crossed the paid Kling boundary exactly once and returned a
technically valid 10-second video. It is not acceptable final output:

- Step 36 fails because Embry changes identity between the opening frames and
  approximately 3 seconds.
- Step 38 fails because Kai's visible mouth is not synchronized to the exact
  post-muxed line.
- Steps 39, 40, and 42 cannot close while those gates fail.

The old Embry character montage was subsequently proven internally
inconsistent. A new GPT Image 2 contact sheet passed a live Tau creator/reviewer
qualification and was persisted to Memory/Qdrant. That accepted reference does
not repair storyboard frames or video generated from the rejected montage.

Canonical objective and step contract: `GOAL.md`.

## 2. Documentation And Code Alignment

### Aligned

- `SKILL.md` and `GOAL.md` require fail-closed contact-sheet, panel,
  post-provider continuity, audio, and Memory gates.
- The active run has real submit, poll, download, ffprobe, contact-sheet,
  continuity, voice, mux, alignment, and Memory artifacts.
- The current failure state in `GOAL.md` matches the returned media evidence:
  identity continuity and visible-speaker lip sync are unresolved.
- Upstream changes invalidate downstream artifacts. Replacing Embry's identity
  source therefore requires a successor revision and regenerated storyboard
  frames, provider packet, and provider return.

### Drift Or Missing Behavior

- `README.md` is stale. It still says there is no live provider return and
  describes `rev_idea_f3f9c48d5cc2`/pre-submit approval state. Do not use its
  current proof-boundary table as operational status.
- The old `local/HANDOFF.md` was stale. It stopped at five approvals before the
  paid submit and omitted the returned video, audio mux, failed continuity, and
  replacement contact-sheet work. This file replaces that status.
- The frozen active revision was changed by later audio/lineage repairs. Running
  `prepare_revision_qualification.py` against it now fails
  `BLOCKED_MEMORY_PREPARE_RECEIPT_STALE`; activation qualification reports
  `BLOCKED_ACTIVATION_REFERENCED_HASH_MISMATCH`. Do not mutate it again.
- Historical Phase 07-11 artifacts still derive from the rejected Embry montage.
  Existing PASS labels for those artifacts are not evidence against the newly
  qualified identity source.
- Tau's native contact-sheet roles historically checked contract/file presence,
  not actual pixels. The narrow Tau patch permits a hash-recorded custom visual
  review prompt, and the replacement sheet was reviewed from pixels. Do not
  infer that every older contact-sheet receipt received equivalent pixel review.
- The Tau contact-sheet command-loop receipt ends `BLOCKED` because `max_steps=2`
  stopped before a panel-specific third node. The terminal GPT-5.5 reviewer
  artifact is PASS for the intended contact-sheet rung. This is not a full
  storyboard or video PASS. The successor Tau run should raise `max_steps` so
  the panel-specific node actually executes.
- `state/active_revision.json` has `revisionRoot` pointing at a volatile temp
  worktree (`/tmp/agent-skills-main-persona-dream-uu5nMV/...`). The directory
  still exists (verified 2026-07-18) but a reboot or tmp cleanup silently
  invalidates the active pointer even though the same revision tree lives in
  the repo under `reports/pipeline-complete/.persona-dream/revisions/`. The
  successor pointer must use the durable repo path, and activation should fail
  closed if `revisionRoot` resolves outside the repository.
- There is no dedicated "create successor revision from a new identity source"
  script. `scripts/reconstruct_upstream_contract_revision.py` is the closest
  precedent (it built `rev_upstream_bf3b05d47fb8` and wrote the upstream
  invalidation ledger); the successor tooling should follow that pattern and
  emit a stale-marking ledger for Phase 07-11 artifacts.

## 3. What Is Working

### Live Kling Return

- Repaired request SHA-256:
  `ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f`.
- Provider request ID: `019f70ac-3864-7d81-9e86-5fae6a676e0d`.
- Exactly one submit and 54 polls; no resubmit.
- Downloaded source MP4: 16,957,429 bytes.
- ffprobe: H.264, 1280x720, 24 fps, 10.041667 seconds.
- Returned-video contact sheet: 12 sampled frames in a 4x3 image.
- `mocked: no`; `live: yes` for the provider lifecycle and returned media.

### Audio Lane

- The canonical Kai line was rendered and post-muxed with ocean ambience.
- Local Whisper large-v3-turbo forced alignment finds the exact line from
  5.00-7.70 seconds.
- Final muxed MP4 SHA-256:
  `991c311f365f84832b274aad7b8ff757372914f7c516e595a31b1bd05edf4c59`.
- Audio stream is present; measured mean is -35.5 dB and max is -16.8 dB.
- This proves transcript timing and audible output, not acceptable delivery or
  visible-speaker synchronization.

### Replacement Embry Contact Sheet

- Rejected source montage:
  `/mnt/storage12tb/media/personas/embry/assets/character_sheet_montage.jpg`.
- Rejection receipt:
  `reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8/phase_07_storyboard_live_tau/receipts/identity_reference_qualification.v1.json`.
- Rejection status: `FAIL_IDENTITY_REFERENCE_INCONSISTENT`.
- Accepted replacement:
  `/mnt/storage12tb/media/personas/embry/assets/contact_sheets/embry-gpt-image-2-v3/images/embry_contact_sheet_v3.png`.
- Replacement dimensions: 1254x1254.
- Replacement SHA-256:
  `3ce40b3b6839ebba0f468d75a1adbb7f82e0d95457aefd3627e222eb569de00c`.
- Live creator: GPT Image 2 through Tau/Scillm, no fallback.
- Live reviewer: GPT-5.5 actual-pixel review, 9/9 cells accepted, zero blockers.
- Qualification receipt:
  `reports/embry-contact-sheet-qualification-20260717.json`.
- Durable generation/review receipts:
  `/mnt/storage12tb/media/personas/embry/assets/contact_sheets/embry-gpt-image-2-v3/receipts/`.
- Memory exact lookup `embry_contact_sheet_v3`: found, confidence 1.0,
  `semantic_sync_state=synced`; record key
  `b11474f2fd5b54f332223a253fd743d1`.
- `mocked: no`; `live: yes`; Kling calls for this qualification: zero.

### Persistence And Idea Surface

- The current run previously wrote and exactly reread 42/42 pipeline-step
  records with 42 semantic syncs and 42 Qdrant pointers. Failed steps are stored
  as failures; that count is persistence proof, not final acceptance.
- The Phase 06 lineage mismatch that emptied `#dream/idea` was repaired by
  rebuilding ten phase bindings, the lineage manifest, and artifact index.
- Idea lineage validates 10/10; artifact index validates 422 artifacts and 16
  required artifacts.
- Live API again returns the exact human idea, and fresh CDP screenshot
  `/tmp/codex-ui-verification/agent-skills-main/persona-dream-idea-and-contact-sheet-final-20260717/20260717T190507Z.png`
  visibly shows it.
- Persona Dream server suite: 22 passed, 0 failed.
- Tau panel-agent suite: 5 passed.
- Mock-evidence mechanical check: 445 test files, no violations.

## 4. What Is Broken Or Blocked

1. **Frozen revision cannot be safely refreshed in place.**
   `prepare_revision_qualification.py` exits 2 with
   `BLOCKED_MEMORY_PREPARE_RECEIPT_STALE`. A successor immutable revision is
   required.
2. **Storyboard identity evidence is stale.** The eight Phase 07 start/end
   frames were generated from the rejected montage and must be regenerated from
   `embry_contact_sheet_v3`.
3. **Post-Kling Embry continuity fails.** Step 36 reports
   `EMBRY_IDENTITY_DRIFT_00_03`.
4. **Visible-speaker lip sync fails.** Step 38 reports
   `FAIL_VISIBLE_SPEAKER_NOT_LIPSYNCED` despite passing forced alignment.
5. **Final acceptance is blocked.** Steps 39, 40, and 42 need regenerated
   evidence from an accepted successor run.
6. **No authorization applies to a successor request.** The consumed approval
   was bound to the historical request hash. Any new paid submit requires a new
   compiled hash and explicit hash-bound authorization.
7. **README operational status is stale.** Update it only after the successor
   rung is proven; do not use documentation edits to imply pipeline progress.
8. **Active pointer depends on a temp worktree.** `revisionRoot` in
   `state/active_revision.json` targets `/tmp/agent-skills-main-persona-dream-uu5nMV`;
   it currently resolves but is one reboot away from dangling. Fix in the
   successor pointer, not by mutating the frozen revision's files.
9. **Workspace is not clean.** Uncommitted Phase 13 webgpt review-bundle
   artifacts sit in `review-bundles/` (a code-review request for a
   `check-phase13-grounded` validator, dated 2026-07-15/16, plus heartbeat
   churn), and the repo has ~33 dirty paths overall. Commit or archive them
   before starting the successor revision so its receipts land on a clean
   baseline.

There are zero `TODO`, `FIXME`, or `XXX` markers in Persona Dream Python/TS/TSX
sources. The blockers are evidence and revision-state failures, not untracked
TODO comments.

## 5. Exact Next Steps

0. Commit or archive the uncommitted `review-bundles/` Phase 13 artifacts and
   other dirty paths so the successor run starts from a clean git baseline.
1. Create a successor immutable revision from
   `rev_upstream_bf3b05d47fb8`; do not modify the frozen revision. Build a
   dedicated script modeled on `reconstruct_upstream_contract_revision.py`
   rather than assembling the revision by hand, and write the successor
   `active_revision.json` with a durable repo-rooted `revisionRoot` (never a
   `/tmp` worktree path).
2. Bind the successor to the accepted `embry_contact_sheet_v3` SHA-256 and its
   live qualification/Memory receipts.
3. Mark stale every Phase 07-11 artifact derived from the rejected montage.
4. Regenerate all eight Phase 07 storyboard start/end frames with GPT Image 2.
5. Run Tau creator/reviewer actual-pixel checks on every generated frame for
   Embry identity, Kai identity, wardrobe/equipment, lighting, reef boundary,
   dialogue intent, panel action, and inter-frame continuity. Raise the Tau
   command-loop `max_steps` above 2 so the panel-specific node executes.
6. Fail closed if any frame drifts. Persist repair attempts and final frame
   statuses to Memory and exact-reread them.
7. Rebuild the successor artifact index, phase bindings, and active-revision
   qualification. Require Memory verification before proceeding.
8. **Stop before Kling.** The immediate acceptance rung is: successor revision
   active/consistent, Memory exact reread succeeds, and 8/8 storyboard frames
   pass actual-pixel continuity review.
9. Only after that rung passes, compile a new provider request and obtain a new
   hash-bound paid authorization.
10. Submit at most one new Kling job, then poll, download, ffprobe, create a
    frame sheet, and run post-Kling identity/action continuity review.
11. Render/mux the exact Kai line and use the authorized lip-sync lane whenever
    Kai's face is visible. Require both forced alignment and visual lip-sync
    acceptance.
12. Regenerate steps 39, 40, and 42; persist and exactly reread all 42 step
    states. Final acceptance remains blocked until steps 36 and 38 pass.

## 6. Key Files And Recent Changes

### Operational Contracts

- `GOAL.md` - immutable 42-step goal and current evidence boundary.
- `SKILL.md` - Persona Dream runtime and ownership contract.
- `PROJECT_KNOWLEDGE.md` - durable lessons and pipeline history.
- `local/HANDOFF.md` - this operational continuation point.

### Active Run

- `reports/pipeline-complete/.persona-dream/state/active_revision.json`
- `reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8/revision_artifact_index.json`
- `reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8/phase_07_storyboard_live_tau/receipts/identity_reference_qualification.v1.json`
- `reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8/phase_11_submit_return/provider_return/ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f/post_kling_continuity_review_receipt.v2.json`
- `reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8/phase_11_submit_return/provider_return/ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f/dialogue_forced_alignment_receipt.v1.json`
- `reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8/phase_11_submit_return/provider_return/ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f/visible_speaker_lipsync_review.v1.json`

### Recent Relevant Commits

Current `main` history (verified 2026-07-18; earlier handoff hashes were from a
pre-rebase worktree):

- `fecff7aa`: `Update Persona Dream operational handoff`.
- `655efa86`: `Qualify replacement Embry contact sheet`.
- `a33b45d7`: `fix(persona-dream): gate voiced returns on alignment and lip sync`.
- `1f041b87`: `persona-dream: complete live Kling return and audio mux`.
- Tau `416edc5a48f0faec049b2952eca60e5c343f0590` on
  `issue-74-ready-queue-condition-block`: permits a custom hash-recorded visual
  review prompt in the existing panel reviewer; targeted tests 5/5.

## Resume Command And Stop Condition

Start by inspecting the active pointer, contact-sheet qualification receipt,
identity-reference failure receipt, and `GOAL.md`. Then clean the workspace,
create the successor revision (durable `revisionRoot`, no `/tmp` paths), and
regenerate the eight frames. Do not run a paid provider command.

The next handoff may advance only when deterministic receipts show an
active/consistent successor revision, exact Memory reread, and 8/8 accepted
actual-pixel storyboard frames. Otherwise report the exact failing frame and
gate code.
