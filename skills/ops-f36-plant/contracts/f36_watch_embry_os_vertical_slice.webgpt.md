# WebGPT Architecture Review Request

## Objective

Review the proposed first integration slice for `ops-f36-plant`, `skills/watch`, `embry-os`, Memory/Qdrant, and SPARTA Explorer.

The intended approach is not three independent projects. It is one shared vertical contract:

```text
SPARTA/F-36 semantic package
→ shared evidence contracts
→ ops-f36-plant test orchestration
→ Watch visual/temporal evidence
→ Memory/Qdrant tentative recall
→ SPARTA evidence-case link
→ Embry OS operator surface and shift handoff
→ human QA disposition
```

## Context Applied

Memory recall for Embry OS says the plant and product should run the same Embry OS and same datastore pattern, avoiding a sync boundary. This review should evaluate the plan with that assumption: Embry OS hosts the runtime/context surface, while `agent-skills` remains the canonical skill source.

## Architecture Artifact

Source artifact:

```text
skills/ops-f36-plant/contracts/f36_watch_embry_os_vertical_slice.architecture.yaml
```

The artifact models:

- a bounded F-36 visual-inspection domain package;
- versioned contracts for F-36 workflow, Watch observations/sequences, visual evidence bundles, and SPARTA evidence links;
- Embry OS plant context and watch-daemon hosting;
- `ops-f36-plant` orchestration and a deterministic plant-test-runner;
- Watch source sessions, YOLOAnalytics detector observations, subject sequences, and `UNASSIGN_STOP`;
- Memory/Qdrant tentative crop recall;
- SPARTA evidence-case linking;
- human QA review/disposition;
- integration gates.

## Review Questions

1. Is the component ownership boundary correct?
   - SPARTA owns semantics and evidence-case links.
   - `ops-f36-plant` owns workflow orchestration.
   - Watch owns video/session/detector/sequence/evidence.
   - Embry OS owns secure runtime, shared context, and operator surface.
   - QA owns disposition.

2. Is the first canary narrow enough?
   - Recorded F-36 visual inspection.
   - One part family.
   - One procedure revision.
   - One visual evidence bundle.
   - One SPARTA evidence-case link.

3. Are the required schemas/events sufficient for the first coding slice?
   - `f36.work_context.v1`
   - `f36.asset_registry.v1`
   - `f36.test_run.v1`
   - `f36.test_phase_event.v1`
   - `watch.source_session.v1`
   - `watch.detector_observation.v1`
   - `watch.sequence_event.v1`
   - `watch.label_decision.v1`
   - `watch.coverage_event.v1`
   - `f36.visual_evidence_bundle.v1`
   - `f36.review_decision.v1`
   - `sparta.evidence_case_link.v1`

4. What should be changed before implementation begins?

5. What is the smallest deterministic proof ladder?
   Proposed:
   - Contract fixtures validate.
   - Watch row-10 `UNASSIGN_STOP` save/reload gate passes.
   - Recorded visual-inspection fixture produces source-timestamped observations.
   - Human accepts/rejects one observation.
   - Watch evidence bundle validates.
   - SPARTA link resolves to one requirement/control/QRA.
   - Embry OS surface shows the same test context and survives restart.

## Constraints

- Do not route physical tests through `quality-audit`.
- Do not let Watch issue PASS/FAIL manufacturing disposition.
- Do not let tentative Memory/Qdrant suggestions mutate sequence state.
- Do not let detector tracks imply identity without Watch sequence events.
- Do not let rejected crops support positive recall.
- Do not begin with live RTSP or a production plant line.

## Desired Output

Return:

1. `KEEP` boundaries.
2. `CHANGE` boundaries.
3. missing contracts or events.
4. first implementation slice.
5. risks that would cause false confidence.
