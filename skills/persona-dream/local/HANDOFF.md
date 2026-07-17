# Handoff Report: Persona Dream

**Timestamp**: 2026-07-17T12:59:23Z
**Active Agent**: Codex
**Operational status**: `BLOCKED_FINAL_ACCEPTANCE`

## 1. Immutable Goal

Produce a working Kling video from the `persona-dream` pipeline.

The goal is complete only when steps 31-36 positively prove a real Kling
submit, poll/callback, returned video, technical validation, contact sheet, and
post-Kling continuity; step 42 then cites those proofs; and all 42 pipeline step
states have durable Memory write and exact-reread evidence.

Canonical contract: `GOAL.md`.

Do not resume Phase 13-16 cognition research, UI, DAG harness, dashboard, or
other adjacent work. Those are outside the current immutable-goal gate.

## 2. Current State

- Run: `pipeline-complete`.
- Active audited revision: `rev_idea_f3f9c48d5cc2`.
- Request SHA-256:
  `ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41`.
- Provider request ID: `019f6bef-0c0f-7921-8a5e-a1f12890fb75`.
- Corrected request provider calls: `1`; polls: `43`.
- Returned MP4: 18,520,578 bytes, H.264, 1280x720, 24 fps,
  10.041667 seconds.
- Returned MP4 SHA-256:
  `2545394fb8e48694acb2751b25cbf6fc55a4dfdbde66e241deecfb5f2f1ecd33`.
- Contact sheet: 12 frames, 4x3, 1312x564.
- Contact sheet SHA-256:
  `de37f319b3834ae37fe08217c4848d891adf234017c59a64295f01f96d660dfa`.
- Memory collection: `persona_dream_pipeline_steps`.
- Memory exact reread: 42/42 unique step keys.
- Semantic syncs: 42; Qdrant pointers: 42.
- Final audit: 35 passing/not-required, 6 blocked, 1 failed.
- Non-passing steps: 05, 11, 12, 15, 36, 40, 42.
- `mocked: no`; `live: yes` for the provider return, technical checks,
  continuity inspection, and Memory persistence.

The goal is not accepted. A technically readable MP4 and 42/42 persisted step
states do not prove that those step states passed.

## 3. What Works

- The exact corrected Kling request was submitted once and returned a real MP4.
- Polling, download, ffprobe, frame extraction, and contact-sheet generation
  produced deterministic receipts.
- Post-Kling review positively preserved Embry/Kai identity within the return,
  navy/black wardrobe, white surfboards, shoreline/daylight continuity,
  SB_001 setup, SB_003 Kai hand signal, and the silent-audio contract.
- Every pipeline step state, including blocked and failed states, is durably
  present under exact run/revision filters in Memory.
- Commit `0173356aab080fd2e59c6304bdc1d1cb45930551` contains the immutable-goal
  audit and is present on `origin/main`.

## 4. What Is Broken

### Step 36 continuity failure

The final 7.0-10.041667-second beat fails two requirements:

- `MISSING_SB004_COMMIT_ACTION`: Embry does not visibly commit forward through
  the safe channel while Kai remains outside the main action.
- `LAVA_REEF_BOUNDARY_NOT_VISUALLY_READABLE`: no readable lava-reef boundary
  or safe-channel geometry anchors the final decision.

Automatic resubmission is forbidden. The consumed one-attempt authorization
does not authorize another request.

### Missing upstream contracts

- Step 05: `dream_packet.json`, `dream_prompt.txt`.
- Step 11: `technique_selection.json`, `look_lock.json`, `shot_bible.json`.
- Step 12: `script_dna_selection.json`.
- Step 15: `panel_continuity_and_repair_ledger.json`.

Steps 40 and 42 are blocked downstream by those missing contracts and the step
36 failure.

### Lineage rule

Do not backfill these files into `rev_idea_f3f9c48d5cc2`. That revision is
frozen and hash-qualified. In-place additions would either change its bound
manifest/index or leave new files outside the qualified artifact set, silently
reusing downstream evidence created without the new upstream hashes.

## 5. External Review

The human-requested `$browser-oracle` binding is ready:

- Project name: `dream`.
- Tab ID: `837359230`.
- KDE desktop: `2`.
- URL:
  `https://chatgpt.com/g/g-p-6a2d6f0882fc8191b3d9c40b349dd193-dream/c/6a5a1f1c-8bcc-83ea-b3fc-5b1c3f706c04`.
- Machine binding: `~/.pi/webgpt-projects/dream.json`.
- Project registry: `.ask/browser-oracles.yaml`.

WebGPT assess artifacts are outside the repository:

- Bundle: `/tmp/persona-dream-next-gate-20260717.md`.
- Response: `/tmp/persona-dream-next-gate-20260717-assess-response.md`.
- Metadata: `/tmp/persona-dream-next-gate-20260717-assess-response.meta.json`.

Routing proof:

```text
requested_tab_id: 837359230
controlled_tab_id: 837359230
controlled_tab_id_mismatch: false
tab_was_created: false
response_proof_status: response_proven
```

Transport metadata is degraded because focus changed despite `--no-activate`.
The exact tab and URL still matched and the response was recovered. The first
submission attempt was rejected because the bundle contained unreadable local
paths; it auto-filed GitHub issue `#166`. The corrected self-contained bundle
then returned successfully.

WebGPT diagnosis: gate-order inversion. The lineage repair must precede the
SB_004 paid-request repair. Its `PASS_CURRENT_GATE` ruling applies only to the
assessment deliverable; it does not mean the pipeline or immutable goal passed.

## 6. Next Gate

Execute one local new-revision upstream-contract reconstruction and invalidation
transaction rooted at `rev_idea_f3f9c48d5cc2`:

1. Create a new immutable revision with
   `sourceRevisionId=rev_idea_f3f9c48d5cc2`.
2. Produce and validate the seven missing canonical files for steps 05, 11,
   12, and 15.
3. Emit step-41 invalidation evidence for affected downstream steps 06-42,
   marking each stale or superseded and naming regeneration/revalidation needs.
4. Recompute the new artifact index and manifest.
5. Run revision Memory prepare, exact verify, semantic verification, active
   pointer update, and activation.
6. Write and exact-reread the new revision-bound pipeline step records.
7. Stop before compiling or submitting another Kling request unless this
   transaction passes completely.

Minimum gate evidence:

- New `revision_manifest.json` and revision artifact index.
- The seven canonical upstream files.
- Step-41 invalidation ledger covering affected steps 06-42.
- Revision Memory prepare, verify, and activation receipts.
- Pipeline-step Memory write and exact-reread receipts for the new revision.
- Gate summary showing steps 05, 11, 12, and 15 passing with no downstream
  artifact silently claimed current.

## 7. Later Gates

After the new revision gate passes:

1. Regenerate or hash-revalidate steps 06-29 in dependency order.
2. Compile a repaired SB_004 request preserving accepted identity/media,
   wardrobe, boards, daylight, and silent-audio constraints while adding an
   unmistakable Embry-only forward commit and readable reef/channel geometry.
3. Fix the new request SHA-256 and initialize an unused request-scoped attempt
   ledger with zero provider calls.
4. Stop at step 30 with `BLOCKED_AWAITING_HUMAN_APPROVAL` for that exact hash.
5. Only a separate human hash-bound paid-call authorization may permit another
   Kling submission.

## 8. Stop Conditions

Do not submit another paid request while any affected record is stale, any step
05-29 gate is non-passing, the repaired request hash is not fixed, its attempt
ledger is not unused with zero calls, or step 30 lacks explicit authorization
for that exact hash.

Do not claim completion until step 36 passes on a new live provider return and
step 42 cites that positive evidence plus 42/42 Memory persistence.

## 9. Key Evidence

All paths below are relative to
`reports/pipeline-complete/.persona-dream/revisions/rev_idea_f3f9c48d5cc2/`:

- `phase_11_submit_return/provider_return/ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41/phase11_provider_return_envelope.v1.json`
- `phase_11_submit_return/provider_return/ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41/phase11_download_ffprobe_receipt.v1.json`
- `phase_11_submit_return/provider_return/ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41/frame_contact_sheet.png`
- `phase_11_submit_return/provider_return/ff2ce7f310fdda2d4900bcec5767ddaef46d592e55ef3900d9384813be0a6f41/post_kling_continuity_review_receipt.v1.json`
- `phase_13_final_acceptance/final_gate_validation_summary.v1.json`
- `phase_13_final_acceptance/pipeline_step_memory_write_receipt.v1.json`
- `phase_13_final_acceptance/final_acceptance_receipt.v1.json`
- `phase_13_final_acceptance/final_report.md`

## 10. Git Safety

- Clean task worktree:
  `/tmp/agent-skills-main-persona-dream-uu5nMV`.
- Branch: `persona-dream-phase11-main-20260717070508`, tracking `origin/main`.
- Do not reset, stash, clean, rebase, or overwrite unrelated work in the main
  checkout at `/home/graham/workspace/experiments/agent-skills`.
- Stage and commit only relevant `skills/persona-dream` paths.
