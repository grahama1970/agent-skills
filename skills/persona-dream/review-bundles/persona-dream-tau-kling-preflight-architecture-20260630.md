# WebGPT Architecture Review Request: persona-dream Tau/Kling Preflight

## Objective

Review the proposed architecture for `persona-dream` as a Tau-orchestrated, creator/reviewer loop pipeline whose terminal report is a Kling preflight gate.

The current problem is not a cosmetic report issue. A compact HTML report omitted required pipeline steps, contact sheets, panels, reviewer checks, and the actual text/image payloads intended for Kling. The corrected system must expose the full creator/reviewer proof chain before any Kling API call is allowed.

## Required Answer From WebGPT

Please answer:

1. Is the architecture shape below coherent and fail-closed?
2. Are any mandatory pipeline steps missing from the preflight ledger?
3. What should the minimal implementable report/ledger schema be?
4. Where should Tau creator/reviewer receipts attach to each step?
5. What should block Kling even if a later artifact exists?
6. What should be rendered into the UX Lab architecture diagram?

Please be critical. Do not approve a generic dashboard, summary page, or report that omits loop receipts.

## Source-Derived Current Understanding

`skills/persona-dream/PROJECT_KNOWLEDGE.md` currently says the canonical no-omission pipeline is:

```text
Request / Idea Intake
-> Dreaming Persona Selection
-> Memory Recall
-> Residue Grounding
-> Dream Packet
-> Story / Video Plan
-> Producer Persona Selection
-> Producer selects Director
-> Producer selects Script Writer
-> Creative Authority Receipts
-> Look Lock
-> Script DNA
-> Storyboard Prompt Composition
-> Storyboard Panel Receipts
-> Panel Continuity And Repair Ledger
-> Panel Generation Loop
-> Panel Visual Review Loop
-> Surgical Panel Repair
-> Panel Repair Gate
-> Panel Source Receipt
-> Provider Media Publication Work Order
-> Local Provider Media Staging
-> Publication Preflight
-> Publication Authorization
-> Public URL Probe
-> Provider Media Handoff
-> Provider Media Lock
-> Kling Scene Packet
-> Provider Final Gate
-> Paid Call Authorization
-> Kling Submit
-> Kling Poll / Callback
-> Output Retrieval
-> FFprobe / Technical Validation
-> Frame Contact Sheet
-> Post-Kling Continuity Review
-> Voice / Audio Handoff Lane when voiced
-> Final Assembly / Movie Lane
-> Report Generation
-> Gate Validation Loop
-> Upstream Revision Invalidation
-> Final Acceptance Boundary
```

The user also gave a simpler preflight questionnaire that must be answered in the report:

```text
Do I have an idea?
What are my related memories?
Do I have a story that outlines all characters and objects as they exist in their environment as JSON?
Do I have producer attached?
Did that producer pick a script writer and director?
Do I have contact sheets per character and object?
Do I have Orpheus-TTS voices per speaking character?
Do I have a complete script?
Do I have a storyboard?
Do I have complete panels with all objects described in their environment?
Do I have complete panel-specific Kling-optimized JSON/other to send to Kling API?
What did I get back from Kling API?
```

## Proposed Architecture Shape

Every pipeline step is a bounded creator/reviewer loop:

```python
for step in pipeline:
    while step.verdict != "PASS":
        creator_result = run_creator_subagent(
            step=step,
            upstream_approved_artifacts=current_manifest,
            previous_review=step.last_review,
        )

        reviewer_result = run_reviewer_subagent(
            step=step,
            artifact=creator_result.artifact,
            contract=step.contract,
            upstream_artifacts=current_manifest,
        )

        persist_creator_receipt(step, creator_result)
        persist_reviewer_receipt(step, reviewer_result)

        if reviewer_result.verdict == "PASS":
            promote_artifact_to_manifest(step, creator_result.artifact)
            unlock_next_step(step)
            break

        if reviewer_result.verdict == "REPAIR":
            step.last_review = reviewer_result
            continue

        if reviewer_result.verdict == "BLOCKED":
            lock_downstream_steps(step)
            stop_pipeline()
```

Tau owns orchestration. Each step has:

- creator subagent identity
- reviewer subagent identity
- artifact contract
- reviewer contract
- repair loop max iterations
- creator receipt path
- reviewer receipt path
- approved artifact path
- upstream revision hash lock
- stale/downstream invalidation policy
- final verdict: `PASS`, `REPAIR`, `BLOCKED`, `STALE`, or `MISSING`

Kling can only be called if every preflight step has a current reviewed `PASS` artifact and paid-call authorization is explicit.

## Existing Local Tension

`skills/persona-dream/pipeline/README.md` still compresses the pipeline to seven directories:

```text
s01_idea
s02_memories
s03_story
s04_voice
s05_panels
s06_gate
s07_movie
```

But current project knowledge expands this into the longer no-omission serial gate. The architecture should reconcile this by treating the seven directories as implementation groupings, not the complete human-facing Kling preflight sequence.

## Proposed Preflight Ledger Row

Each human-facing row should include:

```json
{
  "step_id": "panels",
  "question": "Do I have complete panels with all objects described in their environment?",
  "status": "PASS|REPAIR|BLOCKED|STALE|MISSING",
  "creator": {
    "subagent": "panel-creator",
    "run_id": "...",
    "artifact_path": "...",
    "receipt_path": "..."
  },
  "reviewer": {
    "subagent": "panel-reviewer",
    "run_id": "...",
    "verdict": "...",
    "receipt_path": "...",
    "failed_checks": []
  },
  "approved_artifact_path": "...",
  "upstream_hashes": {},
  "repair_iteration": 2,
  "max_iterations": 5,
  "downstream_unlocked": false,
  "blocks_kling": true,
  "blocker": "..."
}
```

## Proposed UX Lab Architecture Diagram

Render a pipeline diagram with:

1. Tau Orchestrator as the top-level controller.
2. Sequential preflight steps as primary nodes.
3. Each step visually represented as a creator/reviewer loop.
4. A manifest/promotion boundary after each PASS.
5. A fail-closed downstream lock on BLOCKED/STALE/MISSING.
6. Provider/Kling boundary separated from dry-run packet generation.
7. Paid-call authorization separated from technical provider readiness.
8. Kling response lane showing submit, poll/callback, retrieval, ffprobe, frame contact sheet, and post-Kling continuity review.

## Known Evidence Boundary

This review request is architecture review only.

Current local evidence includes prior dry-run packets, contact sheets, some live Scillm panel/Tau proof slices, and reports. It does not prove a live Kling call. The report must therefore be able to say `DRY_RUN_NOT_LIVE_SUBMITTABLE`, `BLOCKED_PROVIDER_GATE`, or `BLOCKED_AWAITING_HUMAN_APPROVAL` without implying live readiness.

## Requested Deliverable

Return:

1. A corrected step list for the preflight ledger.
2. A minimal JSON schema for the ledger.
3. Architecture diagram node list and edges suitable for `$create-architecture`.
4. Implementation plan constraints: what must be source-derived, what must not be mocked, and what blocks Kling.
5. Any red flags in the proposed while-loop model.
