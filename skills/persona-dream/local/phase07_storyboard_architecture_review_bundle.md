# Phase 07 Storyboard DAG Architecture Review Bundle

## Objective

Complete Persona Dream Phase 07 Storyboard through sequential generation and Tau reviewer approval:

1. `sb_001` accepted end frame feeds `sb_002`.
2. `sb_002` accepted end frame feeds `sb_003`.
3. `sb_003` accepted end frame feeds `sb_004`.
4. Final no-target reviewer pass approves the full four-panel storyboard.

Tau reviewer approval is the acceptance boundary. The project agent must not claim storyboard completion without local deterministic artifacts: DAG receipts, reviewer receipts, accepted frame evidence, and UI/browser proof after syncing artifacts.

## Current Run State

Primary run root:

`/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard`

Important artifacts:

- Sequential manifest: `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard/sequential_storyboard_run_manifest.json`
- Shared packet: `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard/work/storyboard_packet.json`
- `sb_002` accepted DAG receipt: `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard/run-sb_002-attempt3/dag-receipt.json`
- `sb_002` reviewer verdict: `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard/work/receipts/storyboard_review_verdict.json`
- `sb_002` identity receipts:
  - `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard/work/receipts/storyboard_identity_review/sb_002_start_frame_identity_continuity_review.json`
  - `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard/work/receipts/storyboard_identity_review/sb_002_end_frame_identity_continuity_review.json`

`sb_002` is the first downstream panel accepted in sequence after repairing prompt/adapter mismatch. `sb_003` is currently running under Tau and must not unlock `sb_004` unless `sb_003.end_frame` is reviewer-accepted.

## What Went Wrong

1. Targeted generation was not actually target-safe.
   - `_ensure_optimum_identity_contract()` unconditionally overwrote `generation_scope` to `sb_001`.
   - Creator/reviewer validation walked every panel even when a target scope existed.
   - Result: a targeted `sb_002` run could block on `sb_003` before `sb_002` had reviewer acceptance.

2. DAG retry routing was under-modeled.
   - First `sb_002` DAG allowed `panel-creator -> panel-reviewer -> human`.
   - The reviewer correctly routed `panel-reviewer -> panel-creator` after rejecting identity continuity.
   - Tau blocked the run with `unexpected_edge` and `max_steps_exhausted`.
   - Repair: allow `panel-reviewer -> panel-creator` with a bounded retry budget.

3. The prompt claimed both Embry and Kai were mandatory, but the adapter did not always attach both identity references.
   - `sb_002` originally listed Embry but not Kai in panel `required_entities`.
   - The generation prompt still demanded both Embry and Kai.
   - The reviewer failed both frames because Kai was not reference-verifiable and Embry read generic.
   - Repair: every generated/reviewed panel now carries `required_entities += ["Embry", "Kai"]` and `required_identities = ["Embry", "Kai"]` before identity references are attached.

4. The prompt is still overloaded.
   - It asks for reference identity, two-shot composition, action mechanics, reef, heat, wax, swell timing, emotion, continuity, and negative constraints in one frame.
   - The accepted repair worked for `sb_002`, but this is fragile.
   - Architecture should separate acceptance-critical identity directives from optional scene detail and keep reviewer questions aligned to the same priority order.

5. Generation latency is high because the image route nests a live Codex/image tool call.
   - The Scillm image wrapper invokes a nested `codex exec` with the built-in `image_gen` tool.
   - One panel attempt can take several minutes for two frames plus review.
   - This is not a reason to parallelize storyboard panels; it is a reason to optimize the DAG, prompt payload, and retry strategy.

## Current Code Patch Under Review

File:

`skills/persona-dream/scripts/phase07_storyboard_tau_node.py`

Patch intent:

- Preserve explicit `generation_scope`; default to `sb_001` only when no scope exists.
- Skip non-target panels during target-scoped validation, generation, and review promotion.
- Force every generated/reviewed panel to include both Embry and Kai as required identities before attaching references.
- Keep final no-target review as the all-panel approval gate.

## Architecture Questions For Reviewer

1. Should the storyboard pipeline use one full DAG with explicit per-panel nodes, or separate Tau DAG runs per panel with a shared packet and final no-target review?
2. Should prompt construction be split into structured prompt blocks with hard priority ordering, such as:
   - identity attachment manifest
   - temporal continuity reference
   - panel action
   - environment details
   - negative constraints
3. Should the creator generate only one frame at a time so the reviewer can reject the start frame before paying for the end frame?
4. Should identity review run immediately after each frame rather than after both frames?
5. Should a rejected identity frame rewrite the next prompt with reviewer findings before regeneration?
6. Should Tau DAG contracts encode reviewer repair edges by default for panel generation DAGs?
7. Should the final full-storyboard approval run be separate and no-target only, to avoid targeted-scope false closure?

## Required Output From Architecture Review

Return a proposed optimized DAG architecture that preserves these invariants:

- Sequential only: no panel can generate until previous panel end frame is reviewer-accepted.
- Reviewer-owned acceptance only: creator cannot write `accepted_frame`.
- Identity-first: Embry/Kai reference verification outranks action, reef, and beauty.
- Live evidence only: mocked checks are wiring-only and cannot approve storyboard panels.
- Final approval is full-storyboard, no-target reviewer pass.
- Failure modes must produce concrete receipts, not narrative status.

## Current Local Evidence Status

- `mocked: no`
- `live: yes`
- `sb_001`: accepted from prior targeted Tau proof.
- `sb_002`: accepted in current sequential run after prompt/adapter repair.
- `sb_003`: accepted in current sequential run after `sb_002.end_frame` continuity.
- `sb_004`: not started until `sb_003` is accepted.
- Final full-storyboard approval: not yet run.
- UI sync/browser proof: not yet run.

## WebGPT Submission Status

Requested WebGPT architecture review is prepared but not submitted.

Artifacts:

- Request: `skills/persona-dream/local/phase07_storyboard_webgpt_request.md`
- Compact attachment: `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard/phase07_storyboard_architecture_webgpt_compact.zip`
- Receipt: `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard/architecture-review-webgpt/webgpt_submit_receipt.json`
- Meta: `/mnt/storage12tb/persona-dream/phase07_tau_runs/run-20260707T204134Z-sequential-storyboard/architecture-review-webgpt/webgpt_response.meta.json`

Transport result:

- `submitted_to_chatgpt: false`
- first attempt failed because `--create-tab` could not provision a reviewer window for project `persona-dream`
- project-binding attempt failed tab identity preflight: stale remembered tab was not an open ChatGPT tab
- explicit `persona-dream` binding tab `837357010` also failed preflight: no open ChatGPT tab with that id
- direct URL attempt failed because no open Chrome tab matched the conversation URL

This is not external review evidence. It is only a prepared review packet plus a failed transport receipt.
