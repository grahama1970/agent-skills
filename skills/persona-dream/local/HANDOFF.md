# Handoff Report: Persona Dream

**Timestamp**: 2026-07-17T14:05:00Z
**Active Agent**: Cursor (Fable)
**Operational status**: `BLOCKED_AWAITING_HUMAN_APPROVAL`

## 1. Immutable Goal

Produce a working Kling video from the `persona-dream` pipeline.

The goal is complete only when steps 31-36 positively prove a real Kling
submit, poll/callback, returned video, technical validation, contact sheet, and
post-Kling continuity; step 42 then cites those proofs; and all 42 pipeline step
states have durable Memory write and exact-reread evidence.

Canonical contract: `GOAL.md`. Do not resume Phase 13-16 cognition research,
UI, DAG harness, dashboard, or other adjacent work.

## 2. What Changed This Session

The 2026-07-17 morning handoff's "Next Gate" (new-revision upstream-contract
reconstruction) and "Later Gates" 1-4 are now complete. The only remaining
action before a new Kling attempt is Graham's five hash-bound approvals.

### Next Gate executed (upstream contract reconstruction)

- New immutable revision `rev_upstream_bf3b05d47fb8` was created with
  `sourceRevisionId=rev_idea_f3f9c48d5cc2` by
  `scripts/reconstruct_upstream_contract_revision.py` in one bounded local
  transaction (no provider work).
- The seven missing canonical upstream files now exist and validate:
  - Step 05: `phase_01_idea/dream_packet.json` (passes
    `validate_dream_packet.py`, 4 frame prompts bound one-to-one to the
    storyboard beats, residue items preserved with exact source ids),
    `phase_01_idea/dream_prompt.txt`.
  - Step 11: `phase_03_crew/technique_selection.json` (validates against the
    vendored selector schema), `phase_03_crew/look_lock.json`,
    `phase_03_crew/shot_bible.json`.
  - Step 12: `phase_03_crew/script_dna_selection.json` (validates against the
    vendored Script DNA schema).
  - Step 15: `phase_07_storyboard_live_tau/panel_continuity_and_repair_ledger.json`
    (one record per panel; sb_004 carries the commit-action and reef-boundary
    dynamic-behavior requirements plus the provider-return failure codes).
  All seven are deterministic reconstructions derived from accepted revision
  artifacts, with per-file provenance hashes and explicit
  `does_not_prove: live selector call` claims.
- Step-41 invalidation ledger
  (`upstream_contract_invalidation_ledger.v1.json`) marks every downstream
  step 06-42 stale, superseded, or blocked with named revalidation needs; the
  gate summary (`upstream_reconstruction_gate_summary.v1.json`) proves no
  downstream artifact was silently claimed current.
- Revision Memory prepare (`PASS_MEMORY_REVISION_PREPARED`), verify
  (`PASS_MEMORY_REVISION_VERIFIED`), pointer update, and activation
  (`PASS_ACTIVE_CONSISTENT`, 339/339 hash matches, 10/10 idea-lineage
  bindings) all passed. Activation transaction:
  `activation-1662abf63c5270c9d7ca17b46ef34c76`.
- All 42 revision-bound pipeline step records were written and exactly reread
  (42/42, 42 semantic syncs, 42 Qdrant pointers) in
  `persona_dream_pipeline_steps`.

### Later Gates 1-3 executed (revalidation and repaired request)

- Steps 06-20 were hash-revalidated against the new upstream contracts
  (`scripts/revalidate_downstream_steps.py`): byte-identity to the accepted
  source set (or semantic identity for the revision-id-rewritten story
  contract) plus 9/9 cross-artifact consistency checks; Memory records updated
  to `PASS_REVALIDATED_CURRENT` with exact reread.
- The SB_004 prompt was repaired in `scripts/phase11_payload_binding.py`
  (`PANEL_CONCISE_ACTIONS["sb_004"]`): the final beat now demands an
  unmistakable Embry-only forward commit (paddle, pop up, ride forward through
  the safe channel) with Kai holding position outside, and a sharply readable
  lava-reef boundary on both sides of Embry's line. 432 chars, passes all
  deterministic prompt gates. Wardrobe, boards, identity bindings, media, and
  the silent-audio contract are unchanged.
- The full zero-call Phase 11 preflight chain then passed for the new
  revision: payload binding bootstrap (publication commit
  `8b12d4c8c5af3fff6f0de2aa1a545b502ca71ed2` on `origin/main`), upstream
  validation reconciliation, live fal schema/pricing snapshot, live public
  media probes (6 request assets, `PASS_PROVIDER_MEDIA_TRANSITIONS_TECHNICAL`),
  canonical compile, and adapter preflight
  (`PASS_PHASE11_ADAPTER_PREFLIGHT`, zero technical blockers).
- Repaired request hash (fixed):
  `sha256:ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f`.
- Its request-scoped attempt ledger is initialized and unused:
  `state=PREFLIGHT_READY`, `actual_provider_call_attempts=0`,
  `submit_intent_count=0`.
- Request-scoped step records 21-30 and 40 were updated in Memory with exact
  reread (`PASS_EXACT_REREAD_REQUEST_SCOPED_STEPS`).

### Current 42-step state (revision `rev_upstream_bf3b05d47fb8`)

- 01-04 PASS (carried); 05, 11, 12, 15 PASS_RECONSTRUCTED.
- 06-10, 13-14, 16-20 PASS_REVALIDATED_CURRENT.
- 21-23, 25-28 PASS with new request-scoped evidence; 28 is the compiled
  zero-call packet.
- 24, 29, 30, 40 BLOCKED_AWAITING_HUMAN_APPROVAL for the exact repaired hash.
- 31-36 SUPERSEDED_PROVIDER_EVIDENCE_PRIOR_REVISION (the 2026-07-17 MP4 and
  its receipts stay bound to `rev_idea_f3f9c48d5cc2` and the consumed request).
- 37-39 stale until a new provider return exists; 41 PASS; 42 BLOCKED.
- `mocked: no` for all live checks named above; `live: yes` for Memory
  persistence, public media probes, and provider schema/pricing snapshots; no
  paid provider call was made this session.

## 3. Next Gate: Human Approval Only

Everything technical is staged. To authorize exactly one paid Kling attempt
(max spend $0.84, Standard 720p, audio off):

1. Review the compiled request:
   `reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8/phase_11_submit_return/canonical/phase11_live_request.v1.json`.
2. Copy the prepared template
   `.../preflight/phase11_authorization_packet.v1.pending.json` to
   `.../preflight/phase11_authorization_packet.v1.json`, set
   `decision: APPROVE`, `decision_source: EXPLICIT_HUMAN`, and fill
   `approved_at` / `expires_at`.
3. Write the five approval receipts:
   `uv run --project skills/persona-dream python skills/persona-dream/scripts/write_phase11_approval_receipts.py --run-root skills/persona-dream/reports/pipeline-complete --revision-id rev_upstream_bf3b05d47fb8 --authorization-packet <packet path> --json`
4. Execute the exactly-once submit and poll loop:
   `uv run --project skills/persona-dream python skills/persona-dream/scripts/phase11_fal_canary_adapter.py --execute --run-root skills/persona-dream/reports/pipeline-complete --revision-id rev_upstream_bf3b05d47fb8 --json`
5. After the return: ffprobe, contact sheet, post-Kling continuity review
   against the four-beat contract (especially the SB_004 Embry-only commit and
   readable reef boundary), then step 36/40/42 and Memory updates.

## 4. Stop Conditions (unchanged)

- Do not submit while any approval for the exact hash is missing.
- One attempt only; no automatic resubmission; an ambiguous submit requires
  human reconciliation.
- Do not claim completion until step 36 passes on a new live provider return
  and step 42 cites that positive evidence plus 42/42 Memory persistence.

## 5. Key Evidence

Revision-relative paths under
`reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8/`:

- `upstream_reconstruction_gate_summary.v1.json`
- `upstream_contract_invalidation_ledger.v1.json`
- `pipeline_step_records.v1.json`
- `phase_01_idea/dream_packet.json`, `phase_01_idea/dream_prompt.txt`
- `phase_03_crew/technique_selection.json`, `phase_03_crew/look_lock.json`,
  `phase_03_crew/shot_bible.json`, `phase_03_crew/script_dna_selection.json`
- `phase_07_storyboard_live_tau/panel_continuity_and_repair_ledger.json`
- `phase_11_submit_return/canonical/phase11_live_request.v1.json`
- `phase_11_submit_return/preflight/phase11_adapter_preflight_receipt.v1.json`
- `phase_11_submit_return/preflight/phase11_authorization_packet.v1.pending.json`
- `phase_11_submit_return/attempts/ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f/attempt_ledger.v1.json`

Run-root state receipts (outside the frozen revision) under
`reports/pipeline-complete/.persona-dream/state/`:

- `upstream_contract_reconstruction_receipt_rev_upstream_bf3b05d47fb8.json`
- `pipeline_step_memory_receipt_rev_upstream_bf3b05d47fb8.json`
- `downstream_revalidation_receipt_rev_upstream_bf3b05d47fb8.json`
- `downstream_revalidation_memory_receipt_rev_upstream_bf3b05d47fb8.json`
- `request_scoped_step_memory_receipt_rev_upstream_bf3b05d47fb8.json`

## 6. Git Safety

- Task worktree: `/tmp/agent-skills-main-persona-dream-uu5nMV`, branch
  `persona-dream-phase11-main-20260717070508`, pushed fast-forward to
  `origin/main`.
- The main checkout at `/home/graham/workspace/experiments/agent-skills` was
  not touched; pull `origin/main` there before expecting the 3002 dream UI to
  reflect the new revision.
- The frozen source revision `rev_idea_f3f9c48d5cc2` was not modified; its
  provider return, Watch observation, and final-acceptance evidence remain
  intact and hash-bound.
