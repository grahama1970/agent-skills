# Watch Streaming World Model Architecture Review Request

## Routing

Use this as a WebGPT architecture review for the `watch` skill in
`agent-skills`. The project agent should use your response to create/update a
UX Lab architecture diagram with `$create-architecture`.

## Safety Boundary

Design this as an evidence, triage, annotation, and human-review system for
streaming video understanding. Do not propose autonomous targeting, engagement,
or harm decisions. High-risk operational outputs must be bounded observations,
uncertainty estimates, evidence cases, and human-review recommendations.

## Objective

Define the next architecture for Watch as a memory-first streaming video
analysis system:

1. YOLOAnalytics/Ultralytics supplies first-stage object/person detections and
   track ids.
2. Watch owns identity/object labels, sequence stop/unassign/reassign semantics,
   interpolation, accepted/rejected evidence, and Qdrant/Memory recall.
3. Watch uses Memory/Qdrant multimodal crop recall to suggest tentative labels
   such as `Marcus? 0.82`.
4. Watch can escalate selected frame sequences to a project agent/Tau-style
   analysis step when detector boxes plus recall are insufficient.
5. Watch should eventually handle file videos and streaming sources such as
   RTSP/webcam/drone feeds on edge hardware such as two 128GB Jetsons.

## Current Source-Derived Step Model

1. **Input source acquisition**
   - Implemented: local video/movie report rows, scene clips, SRT/Whisper text.
   - Implemented/provisional: `live_ultralytics_tracking.py` accepts video,
     webcam, RTSP, or stream URL.
   - Missing: production streaming ingestion contract, backpressure, session
     lifecycle, and multi-stream operator workflow.

2. **First-stage detection/tracking**
   - Implemented: YOLO/ByteTrack person tracking via
     `skills/watch/scripts/track_yolo_bytetrack.py`.
   - Implemented/provisional: live Ultralytics tracking emits
     `watch.live_track_update.v1`.
   - Current default: person class id `0`.
   - Missing: object-class lane beyond person, detector coverage policy for
     every video segment, detector failure accounting.

3. **Detector event persistence**
   - Implemented: row materializer writes detector logs under
     `skills/watch/docs/architecture/generated/watch_yolo_bytetrack_rows/`.
   - Implemented: rows with no detections can be written as `NO_DETECTIONS`.
   - Missing/risky: all-row default materialization and live stream event store
     semantics are not fully settled.

4. **Watch annotation/identity UI**
   - Implemented: Watch report UI can show YOLO boxes, labels, and visible
     overlays; it has direct label interaction work in progress.
   - Implemented/proven once: click label, choose character, save, reload
     persistence, and reset/reject paths for row 9.
   - Missing/risky: broad coverage across identity flips and all row states.

5. **Identity sequence semantics**
   - Intended: Watch sits on top of YOLO tracks and stores keyframe/identity
     sequences.
   - Intended: unassigning a box creates a stop/control point; that track
     remains unassigned until reassigned; interpolation must respect stops.
   - Implemented partially: identity sequence ledger UI exists in
     `WatchReportView.tsx`.
   - Missing/risky: deterministic proof that stop/unassign/reassign works for
     all row 10 cases and does not accidentally create repeated bad keyframes.

6. **Crop generation and embedding**
   - Implemented: accepted boxes can be cropped and embedded.
   - Implemented evidence: Marcus/Willie accepted labels were embedded in
     Memory/Qdrant proof runs.
   - Missing/risky: live stream crop lifecycle, retention policy, and negative
     crop handling.

7. **Memory/Qdrant identity recall**
   - Implemented: Watch asks Memory/Qdrant through an identity suggestion proxy.
   - Evidence:
     - Marcus held-out recall: `11/12`.
     - Marcus/Willie held-out recall: `22/24`.
     - Tentative suggestion proven once with `Willie? 0.89`.
     - One high-confidence wrong-character result correctly showed that a
       track/interpolation handoff was needed.
   - Missing/risky: broader eval-led readiness counter and poisoning resistance
     for rejected/bad boxes.

8. **Transcript/audio/context fusion**
   - Implemented: Watch reports include SRT/Whisper text and scene context.
   - Intended: use transcript/audio/scene context to increase or decrease
     confidence, but not override visual evidence.
   - Missing: concrete confidence fusion contract.

9. **Agentic sequence analysis**
   - Intended: if detector boxes plus Memory recall are insufficient, Watch
     should package a bounded sequence of frames, crops, transcript, and
     detector events into an evidence case for a project agent/Tau-style
     reasoning step.
   - Missing: event schema, escalation trigger, cost/depth limits, evidence
     output contract.

10. **Edge/stream deployment**
    - Intended: run on local/edge hardware, potentially two 128GB Jetsons.
    - Missing: edge split between detector/tracker, crop embedding, Qdrant,
      Memory, UI, persistence, and agentic escalation.

## Existing Proof Artifacts

- Watch README:
  `skills/watch/README.md`
- Live tracking script:
  `skills/watch/scripts/live_ultralytics_tracking.py`
- YOLO/ByteTrack row tracker:
  `skills/watch/scripts/track_yolo_bytetrack.py`
- Identity gate receipt builder:
  `skills/watch/scripts/build_watch_identity_gate_receipt.py`
- Watch UI:
  `skills/watch/ui/components/WatchReportView.tsx`
- Watch UI server:
  `skills/watch/ui/server/index.ts`
- Current proof bundle:
  `skills/watch/docs/architecture/generated/watch_identity_qdrant_marcus_eval/20260705T155850Z_unfinished_goal_proof/`

Important proof files in that bundle:

- `identity_heldout_eval_24.json`
- `identity_handoff_stop_proof.json`
- `identity_readiness_include_eval.json`
- `browser_yolo_label_live_check.png`
- `browser_tentative_suggestion_live_check.png`
- `watch_identity_goal_proof_summary.json`

## Questions For WebGPT

1. What should the clean architecture be for Watch as a memory-first streaming
   video world model layered on YOLOAnalytics/Ultralytics?
2. What exact components and data contracts should separate:
   detector/tracker observations, identity sequence state, accepted/rejected
   labels, Qdrant/Memory recall, tentative suggestions, and agentic evidence
   cases?
3. How should stop/unassign/reassign semantics be modeled so a stable YOLO
   track can cross identity boundaries without poisoning labels?
4. Should Watch inherit/interpolate YOLO boxes directly, or should it store a
   separate identity sequence over detector events? What is the safest minimal
   model?
5. What object-detection lane should be added beside the current person lane?
   Should this remain Ultralytics class filtering, a separate YOLO model, or a
   pluggable detector registry?
6. How should crop embeddings and Qdrant/Memory recall be used to decide when
   a character/object is "ready" for tentative auto-suggestion?
7. What proof gates should the project agent implement next to prove:
   sequence stops, persistence, Qdrant suggestion quality, rejected-box
   poisoning resistance, and stream ingestion?
8. What should run on edge Jetsons versus central services?
9. What architecture-diagram components and connections should be created in
   UX Lab using `$create-architecture`?

## Requested Output

Please return:

1. A numbered architecture workflow, with each step labeled
   `implemented`, `partial`, `intended`, or `missing`.
2. A YAML-compatible component list and connection list suitable for
   `$create-architecture`, using component ids, labels, tech, latency, color,
   and relevant files.
3. Event/schema recommendations for detector observations, identity sequence
   events, label decisions, suggestion results, and evidence-case escalation.
4. The next 5 smallest implementation/proof slices, in order.
5. Failure modes and fail-closed rules.
6. Short project-knowledge bullets that should be recorded for Watch.

---

Completion contract for browser automation:

At the very end of your final answer, print exactly:

<<<WEBGPT_DONE:20260708T022434Z:f5da28cd>>>

Do not print anything after that marker.
