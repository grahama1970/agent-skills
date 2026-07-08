1. Numbered architecture workflow

Grounding from external docs: Ultralytics tracking is suitable as Watch’s first-stage observation layer: tracking works on videos/streaming sources, supports tracker backends such as ByteTrack and BoT-SORT, and persist=True is explicitly tied to consecutive frames from the same stream, not unrelated streams. Ultralytics also supports video files, RTSP/TCP/IP streams, multi-stream .streams files, and webcams as inference sources. 
Ultralytics Docs
 
Ultralytics Docs
 
Ultralytics Docs
 
Ultralytics Docs
 Qdrant fits the Memory layer because its point model stores vectors with payloads, supports vector similarity search, and supports payload indexes/filters that Watch can use to exclude rejected or quarantined crops. 
Qdrant
 
Qdrant
 Jetson Thor-class edge hardware is plausible for this architecture because NVIDIA lists Jetson Thor modules with 128 GB memory and high edge AI compute, while Jetson AI Services expose production-style video-analysis services, stream add/remove APIs, camera discovery, and a Redis message bus pattern. 
NVIDIA
 
NVIDIA Docs

Source/session acquisition — partial / missing
Watch should create a source_session for every file, webcam, RTSP, drone, or stream source. Current local video rows and provisional live Ultralytics support are enough for prototypes, but the production contract needs explicit session_id, stream_id, clock source, lifecycle state, frame sampling policy, backpressure policy, and operator ownership.

Frame clock and ingest adapter — intended / missing
Add a normalized frame clock before detection. Every frame/event should carry source_pts_ms, frame_index, optional wall-clock observed_at, stream_id, and session_id. This is what lets Watch replay file videos and live streams through the same identity/annotation engine.

First-stage detector/tracker lane — implemented / partial
YOLOAnalytics/Ultralytics should own raw object/person detection and tracker IDs. It should emit immutable observations only: class, confidence, bounding box, tracker ID, detector model, tracker config, and frame timing. Watch should not treat YOLO track_id as an identity.

Detector event materialization — partial
Keep the existing row materialization and NO_DETECTIONS records, but promote them into an append-only detector_observation event store. All rows/segments need coverage accounting: detected, no detections, skipped, failed decode, detector timeout, or dropped due to backpressure.

Watch observation normalizer — missing
Insert a normalization layer between YOLOAnalytics and UI/Memory. It should map raw detector outputs into stable observation_ids, normalize boxes, attach crop references, create NO_DETECTIONS/DETECTOR_GAP records, and deduplicate repeated live events.

Identity/object sequence ledger — partial
Watch should own a separate append-only sequence ledger above detector observations. A sequence can reference one or more detector observations, but the sequence state must not be derived solely from track_id. This ledger owns assign, unassign, stop, reassign, reject, reset, and human-review state.

Annotation UI and review workflow — partial
The Watch UI should render three visually distinct things: raw YOLO observation boxes, Watch identity/object sequence state, and tentative Memory suggestions. A suggestion such as Marcus? 0.82 should be visually tentative until a human accepts it.

Label decision store — partial / missing
Accepted labels, rejected labels, rejected crops, resets, and reviewer notes should be persisted as explicit label_decision events. These decisions should be separate from both detector observations and suggestions.

Crop generation and quality gate — partial
Crops should be generated from accepted or reviewable observations, but only accepted crops should enter the positive Memory collection. Rejected/bad crops should either not be embedded or should be embedded only into a quarantine/negative collection excluded from identity suggestions.

Embedding worker and Memory/Qdrant recall — partial
Memory/Qdrant should return candidates, not truth. Store every crop vector with payload fields such as identity_id, decision_id, source_video_id, sequence_id, quality, split, review_state, and quarantine. Payload filters should exclude rejected, quarantined, stale-model, and wrong-project points.

Suggestion readiness gate — partial / missing
Watch should maintain a readiness record per identity/object label. A label becomes eligible for tentative suggestions only after enough accepted examples, held-out recall, negative resistance, and margin tests pass. Until then, Memory recall may be shown only in debug/evidence mode.

Transcript/audio/context fusion — intended / missing
SRT/Whisper and scene context should adjust confidence, but never override visual evidence. The fusion layer should produce a bounded explanation such as: “visual recall weak, transcript mentions Marcus nearby, suggest human review,” not an automatic identity assignment.

Agentic evidence-case escalation — intended / missing
When detector boxes plus Memory recall are insufficient, Watch should package a bounded evidence case: selected frames, crops, detector events, sequence state, transcript snippets, uncertainty, and explicit questions. The project agent/Tau-style step should return observations, uncertainty, contradictions, and review recommendations only.

Object lane beside person lane — missing
Add a pluggable detector registry. Start with Ultralytics class filtering for common COCO-style objects, then allow domain-specific YOLO models and later open-vocabulary/VLM escalation. Do not hard-code object semantics into person identity logic.

Edge/central deployment — intended / missing
Edge Jetsons should run decode, frame sampling, detector/tracker, local crop generation, short-horizon buffering, and optionally local embedding/Qdrant cache. Central services should own canonical Memory, long-term event store, review UI, readiness evaluation, project-agent escalation, and audit receipts.

2. YAML-compatible component and connection list for $create-architecture
YAML
components:
  - id: source_session_controller
    label: Source / Session Controller
    status: partial
    tech: Watch Node/TypeScript + Python adapters
    latency: control-plane; seconds
    color: "#64748b"
    files:
      - skills/watch/ui/server/index.ts
      - skills/watch/scripts/live_ultralytics_tracking.py

  - id: frame_ingest_clock
    label: Frame Ingest + Clock Normalizer
    status: missing
    tech: Python/OpenCV/GStreamer/RTSP adapters
    latency: per-frame; 10-100ms target
    color: "#94a3b8"
    files:
      - skills/watch/scripts/live_ultralytics_tracking.py

  - id: yoloanalytics_tracker
    label: YOLOAnalytics / Ultralytics Detector + Tracker
    status: implemented_partial
    tech: Ultralytics YOLO + ByteTrack/BoT-SORT
    latency: realtime / near-realtime
    color: "#2563eb"
    files:
      - skills/watch/scripts/track_yolo_bytetrack.py
      - skills/watch/scripts/live_ultralytics_tracking.py

  - id: detector_event_bus
    label: Detector Observation Bus
    status: partial
    tech: JSONL now; Redis/NATS/Kafka later
    latency: sub-second
    color: "#0ea5e9"
    files:
      - skills/watch/scripts/live_ultralytics_tracking.py

  - id: detector_event_store
    label: Immutable Detector Event Store
    status: partial
    tech: JSONL/SQLite/Postgres/Object storage
    latency: write-through; replayable
    color: "#0284c7"
    files:
      - skills/watch/docs/architecture/generated/watch_yolo_bytetrack_rows/

  - id: watch_observation_normalizer
    label: Watch Observation Normalizer
    status: missing
    tech: Python/TypeScript schema adapter
    latency: sub-second
    color: "#38bdf8"
    files:
      - skills/watch/ui/server/index.ts

  - id: identity_sequence_ledger
    label: Identity/Object Sequence Ledger
    status: partial
    tech: append-only JSON/SQLite/Postgres
    latency: interactive; <100ms UI replay
    color: "#7c3aed"
    files:
      - skills/watch/ui/components/WatchReportView.tsx

  - id: annotation_review_ui
    label: Watch Annotation + Human Review UI
    status: partial
    tech: React/TypeScript
    latency: interactive
    color: "#a855f7"
    files:
      - skills/watch/ui/components/WatchReportView.tsx

  - id: label_decision_store
    label: Accepted / Rejected Label Decision Store
    status: partial_missing
    tech: append-only decisions + audit receipts
    latency: interactive; durable before Memory ingest
    color: "#9333ea"
    files:
      - skills/watch/ui/components/WatchReportView.tsx
      - skills/watch/scripts/build_watch_identity_gate_receipt.py

  - id: crop_quality_pipeline
    label: Crop Generation + Quality Gate
    status: partial
    tech: Python image cropper + quality metrics
    latency: async; seconds
    color: "#16a34a"
    files:
      - skills/watch/scripts/build_watch_identity_gate_receipt.py

  - id: embedding_worker
    label: Multimodal Crop Embedding Worker
    status: partial
    tech: Memory embedding proxy / CLIP-like embedding worker
    latency: async; seconds
    color: "#22c55e"
    files:
      - skills/watch/scripts/build_watch_identity_gate_receipt.py

  - id: qdrant_memory
    label: Memory / Qdrant Recall Store
    status: partial
    tech: Qdrant vectors + payload filters
    latency: online suggestion; <500ms target
    color: "#059669"
    files:
      - skills/watch/docs/architecture/generated/watch_identity_qdrant_marcus_eval/20260705T155850Z_unfinished_goal_proof/

  - id: suggestion_service
    label: Tentative Suggestion Service
    status: partial
    tech: Watch identity suggestion proxy
    latency: interactive; <500ms target
    color: "#10b981"
    files:
      - skills/watch/ui/server/index.ts
      - skills/watch/docs/architecture/generated/watch_identity_qdrant_marcus_eval/20260705T155850Z_unfinished_goal_proof/browser_tentative_suggestion_live_check.png

  - id: transcript_context_fusion
    label: Transcript / Scene Context Fusion
    status: intended
    tech: SRT/Whisper + scene metadata confidence adjuster
    latency: async / interactive
    color: "#f59e0b"
    files:
      - skills/watch/README.md

  - id: evidence_case_builder
    label: Evidence Case Builder
    status: missing
    tech: bounded frame/crop/transcript/event packager
    latency: async; bounded budget
    color: "#f97316"
    files:
      - skills/watch/docs/architecture/generated/watch_identity_qdrant_marcus_eval/20260705T155850Z_unfinished_goal_proof/

  - id: project_agent_tau
    label: Project Agent / Tau-Style Analysis
    status: intended
    tech: agentic reasoning over bounded evidence cases
    latency: async; cost/depth limited
    color: "#ea580c"
    files:
      - skills/watch/README.md

  - id: proof_gate_runner
    label: Proof Gate + Readiness Receipts
    status: partial
    tech: Python/TS deterministic tests + JSON receipts
    latency: CI / local proof run
    color: "#dc2626"
    files:
      - skills/watch/scripts/build_watch_identity_gate_receipt.py
      - skills/watch/docs/architecture/generated/watch_identity_qdrant_marcus_eval/20260705T155850Z_unfinished_goal_proof/identity_heldout_eval_24.json
      - skills/watch/docs/architecture/generated/watch_identity_qdrant_marcus_eval/20260705T155850Z_unfinished_goal_proof/identity_handoff_stop_proof.json
      - skills/watch/docs/architecture/generated/watch_identity_qdrant_marcus_eval/20260705T155850Z_unfinished_goal_proof/identity_readiness_include_eval.json

  - id: edge_jetson_runtime
    label: Edge Jetson Runtime
    status: intended
    tech: Jetson containers; decode/detect/track/crop/local cache
    latency: realtime edge loop
    color: "#475569"
    files:
      - skills/watch/scripts/live_ultralytics_tracking.py

  - id: central_watch_services
    label: Central Watch Services
    status: intended
    tech: Watch API + canonical store + Memory + UI + agent escalation
    latency: mixed realtime/async
    color: "#111827"
    files:
      - skills/watch/ui/server/index.ts
      - skills/watch/ui/components/WatchReportView.tsx
YAML
connections:
  - id: c01_start_session
    from: source_session_controller
    to: frame_ingest_clock
    label: starts/stops file, webcam, RTSP, stream sessions
    contract: watch.source_session.v1
    latency: seconds

  - id: c02_frames_to_detector
    from: frame_ingest_clock
    to: yoloanalytics_tracker
    label: timestamped frames
    contract: watch.frame_ref.v1
    latency: per-frame

  - id: c03_detector_events
    from: yoloanalytics_tracker
    to: detector_event_bus
    label: raw boxes, class ids, confidences, track ids
    contract: watch.detector_observation.v1
    latency: realtime

  - id: c04_event_persistence
    from: detector_event_bus
    to: detector_event_store
    label: append-only detector observations and no-detection rows
    contract: watch.detector_observation.v1
    latency: write-through

  - id: c05_normalize_observations
    from: detector_event_store
    to: watch_observation_normalizer
    label: replayable observation stream
    contract: watch.observation_index.v1
    latency: replay / online

  - id: c06_ui_reads_observations
    from: watch_observation_normalizer
    to: annotation_review_ui
    label: raw observation overlays
    contract: watch.overlay_observation.v1
    latency: interactive

  - id: c07_ui_writes_sequence_events
    from: annotation_review_ui
    to: identity_sequence_ledger
    label: assign, unassign, stop, reassign, keyframe
    contract: watch.identity_sequence_event.v1
    latency: interactive

  - id: c08_ui_writes_label_decisions
    from: annotation_review_ui
    to: label_decision_store
    label: accept, reject, reset, promote, demote
    contract: watch.label_decision.v1
    latency: durable before embed

  - id: c09_decisions_to_crops
    from: label_decision_store
    to: crop_quality_pipeline
    label: accepted/reviewable crop jobs; rejected quarantine
    contract: watch.crop_job.v1
    latency: async

  - id: c10_crop_embeddings
    from: crop_quality_pipeline
    to: embedding_worker
    label: quality-gated crops
    contract: watch.crop_artifact.v1
    latency: async

  - id: c11_embeddings_to_memory
    from: embedding_worker
    to: qdrant_memory
    label: vector + payload upsert for accepted crops
    contract: watch.memory_point.v1
    latency: async

  - id: c12_recall_query
    from: annotation_review_ui
    to: suggestion_service
    label: selected box/crop asks for tentative identity/object candidates
    contract: watch.suggestion_request.v1
    latency: interactive

  - id: c13_memory_candidates
    from: qdrant_memory
    to: suggestion_service
    label: filtered nearest neighbors and scores
    contract: watch.recall_result.v1
    latency: interactive

  - id: c14_tentative_overlay
    from: suggestion_service
    to: annotation_review_ui
    label: tentative suggestions only, e.g. Marcus? 0.82
    contract: watch.suggestion_result.v1
    latency: interactive

  - id: c15_context_adjustment
    from: transcript_context_fusion
    to: suggestion_service
    label: confidence adjustment and contradiction notes
    contract: watch.context_signal.v1
    latency: async / interactive

  - id: c16_uncertain_sequence_escalation
    from: suggestion_service
    to: evidence_case_builder
    label: low-confidence, ambiguous, contradictory, or missing-box cases
    contract: watch.evidence_case_request.v1
    latency: async

  - id: c17_agent_case
    from: evidence_case_builder
    to: project_agent_tau
    label: bounded evidence packet
    contract: watch.evidence_case.v1
    latency: bounded async

  - id: c18_agent_review_output
    from: project_agent_tau
    to: annotation_review_ui
    label: observations, uncertainty, review recommendations
    contract: watch.evidence_case_result.v1
    latency: async

  - id: c19_proof_inputs
    from: detector_event_store
    to: proof_gate_runner
    label: row fixtures, stream fixtures, no-detection coverage
    contract: watch.proof_fixture.v1
    latency: CI

  - id: c20_proof_decisions
    from: identity_sequence_ledger
    to: proof_gate_runner
    label: sequence stop/reassign replay checks
    contract: watch.sequence_replay_receipt.v1
    latency: CI

  - id: c21_edge_to_central
    from: edge_jetson_runtime
    to: central_watch_services
    label: events, crops, health, backpressure, review packets
    contract: watch.edge_sync.v1
    latency: realtime + async

  - id: c22_central_config_to_edge
    from: central_watch_services
    to: edge_jetson_runtime
    label: detector registry, class filters, thresholds, stream assignments
    contract: watch.edge_config.v1
    latency: control-plane
3. Event and schema recommendations
3.1 Detector observation: immutable raw evidence
YAML
watch.detector_observation.v1:
  purpose: immutable first-stage detector/tracker observation
  ownership: YOLOAnalytics/Ultralytics emits; Watch stores and normalizes
  required_fields:
    event_id: string
    schema_version: watch.detector_observation.v1
    session_id: string
    stream_id: string
    source_id: string
    frame_index: integer
    source_pts_ms: number
    observed_at: string
    detector:
      provider: ultralytics
      model_id: string
      model_version: string
      tracker: bytetrack | botsort | none | other
      tracker_config_hash: string
    observation:
      observation_id: string
      observation_type: DETECTION | NO_DETECTIONS | DETECTOR_GAP | DECODE_ERROR
      class_id: integer | null
      class_name: string | null
      track_id: string | null
      confidence: number | null
      bbox_xyxy_norm: [number, number, number, number] | null
      bbox_xyxy_px: [integer, integer, integer, integer] | null
      frame_width: integer
      frame_height: integer
    quality:
      occlusion: number | null
      blur: number | null
      crop_area_ratio: number | null
      detector_warning: string | null
    refs:
      frame_ref: string
      crop_ref: string | null
  invariants:
    - event_id is idempotent and content-addressable when possible
    - raw observation is never mutated by label decisions
    - track_id is a tracker-local hint, not identity truth
3.2 Identity sequence event: Watch-owned state above detector tracks
YAML
watch.identity_sequence_event.v1:
  purpose: append-only identity/object sequence control
  ownership: Watch
  required_fields:
    event_id: string
    schema_version: watch.identity_sequence_event.v1
    sequence_id: string
    subject_type: PERSON | OBJECT | SCENE_REGION
    stream_id: string
    session_id: string
    event_type: START | KEYFRAME | ASSIGN | UNASSIGN_STOP | REASSIGN_START | END | RESET
    effective_at:
      source_pts_ms: number
      frame_index: integer
      observation_id: string | null
    detector_refs:
      observation_id: string | null
      detector_track_id: string | null
    identity_state_after:
      state: ASSIGNED | UNASSIGNED | STOPPED | UNKNOWN
      identity_id: string | null
      display_label: string | null
      label_source: HUMAN | MEMORY_SUGGESTION | IMPORTED | NONE
    geometry:
      bbox_xyxy_norm: [number, number, number, number] | null
      geometry_source: DETECTOR_OBSERVATION | HUMAN_ADJUSTED | INTERPOLATED_PREVIEW | NONE
    policy:
      interpolation: NONE | HOLD_UNTIL_STOP | LINEAR_BETWEEN_KEYFRAMES
      propagate_across_stop: false
      persist_interpolated_as_keyframes: false
    actor:
      reviewer_id: string | null
      tool: watch_ui | script | migration
    audit:
      reason: string | null
      previous_event_id: string | null
  invariants:
    - UNASSIGN_STOP closes the active assigned segment at that frame/time
    - REASSIGN_START begins a new segment even if detector_track_id is unchanged
    - interpolation never crosses UNASSIGN_STOP, END, RESET, DETECTOR_GAP, or source-session boundary
    - derived preview boxes are not persisted as canonical keyframes
3.3 Label decision: acceptance/rejection audit
YAML
watch.label_decision.v1:
  purpose: human or policy decision about a label/crop/suggestion
  ownership: Watch human-review workflow
  required_fields:
    decision_id: string
    schema_version: watch.label_decision.v1
    decision_type: ACCEPT_LABEL | REJECT_LABEL | REJECT_CROP | RESET_LABEL | PROMOTE_SUGGESTION | DEMOTE_SUGGESTION
    subject_type: PERSON | OBJECT
    identity_id: string | null
    display_label: string | null
    sequence_id: string | null
    observation_id: string | null
    suggestion_id: string | null
    crop_ref: string | null
    reviewer:
      reviewer_id: string
      reviewed_at: string
    result:
      memory_ingest_allowed: boolean
      quarantine: boolean
      negative_example_allowed: boolean
      reason_code: CORRECT | WRONG_IDENTITY | BAD_BOX | OCCLUDED | LOW_QUALITY | AMBIGUOUS | DUPLICATE | OTHER
      notes: string | null
  invariants:
    - only ACCEPT_LABEL with memory_ingest_allowed true can create positive Memory points
    - rejected crops are excluded from suggestion queries by default
    - reset does not delete history; it appends a corrective event
3.4 Suggestion result: tentative, never canonical
YAML
watch.suggestion_result.v1:
  purpose: Memory/Qdrant candidate returned for human review
  ownership: Watch suggestion service
  required_fields:
    suggestion_id: string
    schema_version: watch.suggestion_result.v1
    requested_at: string
    request:
      observation_id: string
      crop_ref: string
      subject_type: PERSON | OBJECT
      stream_id: string
      session_id: string
    model:
      embedding_model_id: string
      qdrant_collection: string
      recall_profile_id: string
      readiness_version: string
    candidates:
      - identity_id: string
        display_label: string
        score: number
        margin_to_next: number
        support_count: integer
        nearest_points:
          - point_id: string
            score: number
            payload_summary:
              source_video_id: string
              sequence_id: string
              crop_quality: number
              reviewed: true
    gating:
      ready_for_suggestion: boolean
      blocked_reasons:
        - string
      display_mode: HIDDEN | DEBUG_ONLY | TENTATIVE_BADGE | HUMAN_REVIEW_REQUIRED
    output:
      label_text: string
      confidence: number
      uncertainty: string
      auto_apply_allowed: false
  invariants:
    - suggestions never write identity_sequence_event by themselves
    - suggestions never create Memory points
    - suggestions are invalidated if the underlying observation/sequence changes
3.5 Evidence case escalation: bounded agent input/output
YAML
watch.evidence_case.v1:
  purpose: bounded escalation when detector boxes and Memory recall are insufficient
  ownership: Watch evidence-case builder; project agent analyzes
  required_fields:
    case_id: string
    schema_version: watch.evidence_case.v1
    created_at: string
    trigger:
      trigger_type: LOW_RECALL | AMBIGUOUS_TOP2 | TRACK_HANDOFF | DETECTOR_GAP | USER_REQUEST | CONTEXT_CONTRADICTION
      observation_ids:
        - string
      sequence_ids:
        - string
    bounds:
      max_frames: integer
      max_crops: integer
      max_seconds: number
      max_tokens_or_cost: number
      allowed_outputs:
        - BOUNDED_OBSERVATION
        - UNCERTAINTY_ESTIMATE
        - EVIDENCE_SUMMARY
        - HUMAN_REVIEW_RECOMMENDATION
    evidence:
      frame_refs:
        - string
      crop_refs:
        - string
      detector_events:
        - string
      identity_sequence_events:
        - string
      transcript_spans:
        - text: string
          start_ms: number
          end_ms: number
      memory_candidates:
        - suggestion_id: string
      contradictions:
        - string
    questions:
      - string
  output_contract:
    schema_version: watch.evidence_case_result.v1
    case_id: string
    observations:
      - text: string
        evidence_refs:
          - string
        uncertainty: LOW | MEDIUM | HIGH
    recommended_review_actions:
      - ACCEPT | REJECT | SPLIT_SEQUENCE | ADD_STOP | REQUEST_MORE_FRAMES | NO_ACTION
    prohibited_outputs:
      - autonomous_targeting
      - engagement_decision
      - harm_decision
      - unreviewed_identity_assignment
4. Stop / unassign / reassign semantics

Use the separate identity sequence model, not YOLO-track inheritance.

The safest minimal model is:

YOLO track = detector-local continuity hint.
It helps Watch find likely adjacent boxes, but it is not an identity, label, or Memory key.

Watch sequence = identity/object assertion over time.
A sequence can reference the same YOLO track_id before and after a boundary, but the identity label must come from Watch events.

Assign creates an active segment.
Example: at frame 100, observation obs_A, YOLO track_id=7, human assigns Marcus.

Hold/interpolate only inside active segment.
Watch can hold the last visible keyframe or linearly interpolate between visible keyframes, but only until a stop boundary.

Unassign creates a stop/control point.
At frame 140, same YOLO track_id=7, user unassigns. Watch writes UNASSIGN_STOP. From frame 140 onward, track_id=7 is unassigned unless a later event starts a new sequence.

Reassign starts a new sequence segment.
At frame 160, same YOLO track_id=7, user assigns Willie. Watch writes REASSIGN_START or START for a new sequence_id.

Never write derived boxes as canonical labels.
Interpolated/held boxes are render-time projections. They must not become accepted keyframes, crop positives, or Qdrant points unless a human accepts them.

Memory ingestion follows label decisions, not track continuity.
Accepted Marcus crops before the stop go to Marcus. Accepted Willie crops after reassignment go to Willie. The stopped interval and rejected crops stay out of positive Memory.

5. Should Watch inherit YOLO boxes or store separate identity sequences?

Watch should reuse YOLO boxes as observation geometry, but store separate identity/object sequences over detector events.

Minimal safe model:

YAML
safe_minimal_model:
  detector_observation:
    immutable: true
    contains:
      - box geometry
      - class
      - confidence
      - tracker id
      - frame timing
  identity_sequence_event:
    immutable_append_only: true
    references:
      - observation_id
      - optional detector_track_id
    contains:
      - identity/object label state
      - stop/unassign/reassign semantics
      - interpolation policy
  label_decision:
    immutable_append_only: true
    references:
      - observation_id
      - sequence_id
      - crop_ref
      - suggestion_id
    controls:
      - memory_ingest_allowed
      - quarantine
      - accepted/rejected audit

This gives Watch the benefit of YOLO geometry and tracking without letting a detector-track error become an identity error.

6. Object-detection lane beside person lane

Use a pluggable detector registry, with Ultralytics class filtering as the first implementation.

YAML
detector_registry:
  lanes:
    - lane_id: person_lane
      current_status: implemented_partial
      default_detector: ultralytics_yolo
      default_classes:
        - person
      watch_semantics:
        - identity_sequence
        - crop_recall
        - human_label_review

    - lane_id: common_object_lane
      current_status: missing
      default_detector: ultralytics_yolo
      default_classes:
        - vehicle
        - bag
        - phone
        - laptop
        - animal
        - traffic_object
        - handheld_object
      watch_semantics:
        - object_sequence
        - object_label_review
        - object_crop_recall

    - lane_id: domain_object_lane
      current_status: intended
      default_detector: custom_yolo_or_domain_model
      default_classes:
        - project_defined
      watch_semantics:
        - detector_registry_config
        - readiness_eval_per_class
        - human_review_required_for_high_risk_classes

    - lane_id: open_vocab_escalation_lane
      current_status: intended
      default_detector: vlm_or_open_vocab_detector
      activation:
        - user_requested
        - detector_gap
        - evidence_case
      watch_semantics:
        - bounded_observation_only
        - no_autonomous_decisions

Recommendation: start with common_object_lane using Ultralytics class filters because it is the smallest change from the current person lane. Add the detector registry now so future custom YOLO or VLM/open-vocabulary detectors can be plugged in without changing the sequence ledger.

High-risk object classes should be treated as review-only observations with uncertainty and evidence references, never as operational recommendations.

7. Crop embeddings and readiness for tentative suggestions

A label should become eligible for Marcus? 0.82-style suggestions only when a watch.identity_readiness.v1 gate passes.

YAML
watch.identity_readiness.v1:
  identity_id: string
  display_label: string
  subject_type: PERSON | OBJECT
  embedding_model_id: string
  collection: string
  readiness_state: NOT_READY | DEBUG_ONLY | TENTATIVE_READY | QUARANTINED
  minimum_positive_examples:
    accepted_crop_count: 12
    distinct_sequences: 3
    distinct_scenes_or_segments: 3
    minimum_quality_score: 0.65
  heldout_eval:
    required: true
    min_top1_recall: 0.90
    min_top1_margin_median: 0.08
    max_high_conf_wrong_rate: 0.02
  negative_resistance:
    rejected_crops_excluded: true
    cross_identity_negative_set_required: true
    no_recent_poisoning_regression: true
  suggestion_thresholds:
    tentative_badge_min_score: 0.82
    human_review_required_below_score: 0.90
    min_margin_to_next: 0.08
    min_support_count: 3
  hard_blocks:
    - sequence_crosses_unassign_stop
    - crop_is_rejected_or_quarantined
    - detector_gap_at_frame
    - top2_margin_too_small
    - identity_under_quarantine
    - embedding_model_mismatch

Operational rule: even after readiness passes, Watch should display tentative suggestions only. Promotion to accepted identity/object state requires a PROMOTE_SUGGESTION or ACCEPT_LABEL decision.

8. Next 5 smallest implementation/proof slices

Sequence stop/reassign deterministic replay gate
Implement the pure helper for active sequence projection and wire it into WatchReportView.tsx. Add fixtures for row 10: same YOLO track, assign Marcus, unassign stop, reassigned identity later, playback/reload confirms no propagation across the stop.

Append-only detector observation contract
Promote current YOLO row materialization into watch.detector_observation.v1. Add all-row coverage: DETECTION, NO_DETECTIONS, DETECTOR_GAP, DECODE_ERROR, and SKIPPED_BY_BACKPRESSURE. Prove idempotent replay creates the same observation index.

Label decision + Memory quarantine proof
Split accepted/rejected labels into watch.label_decision.v1. Prove that rejected crops do not enter positive Qdrant recall and that quarantined/negative points are filtered out of suggestion queries.

Suggestion readiness receipt
Turn the Marcus/Willie held-out proof into a repeatable identity_readiness gate. Expand the eval set, preserve the known high-confidence wrong-character case as a regression fixture, and require score/margin/support thresholds before UI shows tentative suggestions.

Live stream session lifecycle + backpressure proof
Build a local stream simulator that can produce RTSP/webcam-like frames, dropouts, detector delays, no-detection spans, and reconnects. Prove Watch preserves event order, marks gaps, avoids cross-stream tracker carryover, and never propagates labels through dropped/gap intervals.

9. Failure modes and fail-closed rules
YAML
failure_modes:
  - mode: detector_no_detection_or_dropout
    fail_closed_rule: emit NO_DETECTIONS or DETECTOR_GAP; do not interpolate labels through the gap unless an explicit sequence policy allows it and no stop exists

  - mode: yolo_track_id_switch
    fail_closed_rule: treat track_id change as observation uncertainty; do not auto-transfer identity without Watch sequence continuity and human-reviewed evidence

  - mode: same_yolo_track_crosses_identity_boundary
    fail_closed_rule: UNASSIGN_STOP terminates the active identity segment; later reassignment starts a new segment

  - mode: memory_high_confidence_wrong_identity
    fail_closed_rule: show tentative badge at most; require human review; add regression fixture; do not ingest resulting crop unless accepted

  - mode: top2_memory_candidates_too_close
    fail_closed_rule: suppress label suggestion or show ambiguous review state; escalate evidence case if useful

  - mode: rejected_or_bad_crop_poisoning
    fail_closed_rule: rejected crops are quarantined/excluded by payload filters; positive collection only accepts reviewed ACCEPT_LABEL decisions

  - mode: duplicate_live_events
    fail_closed_rule: idempotent event ids; duplicate writes collapse to one observation

  - mode: stale_schema_or_model_mismatch
    fail_closed_rule: block Memory suggestion across incompatible embedding model, detector model, or schema version unless migrated

  - mode: backpressure_or_overload
    fail_closed_rule: drop/sample raw frames only according to policy; preserve lifecycle, gap, and detector health events; never fabricate continuous evidence

  - mode: transcript_context_contradicts_visual_recall
    fail_closed_rule: lower confidence or escalate; transcript cannot override visual evidence

  - mode: agentic_escalation_overconfidence
    fail_closed_rule: project agent may return bounded observations, uncertainty, and human-review recommendations only

  - mode: edge_offline_or_sync_lag
    fail_closed_rule: edge stores local append-only events; central UI marks data as stale/partial; no global Memory update until sync/audit succeeds

  - mode: high_risk_operational_interpretation
    fail_closed_rule: output evidence cases and human-review recommendations only; no autonomous targeting, engagement, or harm decisions
10. Edge Jetsons versus central services
YAML
edge_jetsons:
  should_run:
    - stream decode and frame sampling
    - YOLOAnalytics/Ultralytics detector/tracker
    - per-stream tracker instances
    - local detector event bus
    - crop generation and crop quality scoring
    - short-horizon frame/crop ring buffer
    - local health, backpressure, and session lifecycle reporting
    - optional local embedding worker
    - optional local Qdrant cache for low-latency suggestions
  should_not_be_canonical_for:
    - final accepted/rejected identity truth
    - long-term Memory readiness
    - global cross-video identity statistics
    - audit receipts
    - project-agent decisions

central_services:
  should_run:
    - canonical detector event store
    - canonical identity sequence ledger
    - canonical label decision store
    - Memory/Qdrant master collections
    - readiness/eval/proof gates
    - Watch review UI and UX Lab architecture views
    - evidence-case builder
    - project-agent/Tau-style bounded analysis
    - long-term retention, audit, and migration jobs

two_jetson_split:
  option_a_stream_shards:
    jetson_a: streams 1..N, detector/tracker/crop/local cache
    jetson_b: streams N+1..M, detector/tracker/crop/local cache
    central: canonical Memory/UI/proofs
  option_b_pipeline_split:
    jetson_a: decode + detector/tracker for latency-critical streams
    jetson_b: embedding + local recall cache + heavier object lane
    central: canonical event store and review workflow
  recommendation: start with option_a_stream_shards because it isolates tracker state by stream and makes failure accounting simpler
11. Architecture-diagram guidance for UX Lab

Create a left-to-right diagram with five zones:

YAML
diagram_zones:
  - id: inputs
    label: Sources
    components:
      - source_session_controller
      - frame_ingest_clock

  - id: first_stage_perception
    label: First-Stage Detection / Tracking
    components:
      - yoloanalytics_tracker
      - detector_event_bus
      - detector_event_store
      - watch_observation_normalizer

  - id: watch_world_model
    label: Watch-Owned World Model
    components:
      - identity_sequence_ledger
      - label_decision_store
      - annotation_review_ui
      - transcript_context_fusion

  - id: memory_recall
    label: Memory / Qdrant Recall
    components:
      - crop_quality_pipeline
      - embedding_worker
      - qdrant_memory
      - suggestion_service

  - id: escalation_and_deployment
    label: Escalation, Proofs, Edge Deployment
    components:
      - evidence_case_builder
      - project_agent_tau
      - proof_gate_runner
      - edge_jetson_runtime
      - central_watch_services

Important visual conventions:

YAML
visual_conventions:
  raw_detector_events:
    color: "#2563eb"
    meaning: immutable YOLOAnalytics observations
  watch_identity_state:
    color: "#7c3aed"
    meaning: Watch-owned sequence and label state
  memory_recall:
    color: "#059669"
    meaning: tentative recall and crop embeddings
  human_review:
    color: "#a855f7"
    meaning: accepted/rejected decisions
  escalation:
    color: "#f97316"
    meaning: bounded evidence cases
  proof_fail_closed:
    color: "#dc2626"
    meaning: gates, receipts, failure accounting
  edge_runtime:
    color: "#475569"
    meaning: Jetson/local realtime execution

The diagram should make one boundary unmistakable: YOLOAnalytics emits observations; Watch owns identity, object labels, sequence stops, accepted/rejected evidence, Memory eligibility, suggestions, and review/audit state.

12. Project-knowledge bullets to record for Watch

Watch is a memory-first streaming video understanding system layered on YOLOAnalytics/Ultralytics.

YOLO track_id is not identity truth; it is only a detector/tracker-local continuity hint.

Watch owns identity/object sequence semantics, including assign, unassign stop, reassign, reset, and interpolation boundaries.

Unassign must create a stop/control point; interpolation and label propagation must not cross it.

Interpolated/held boxes are render-time projections and must not become canonical keyframes or Memory positives without human acceptance.

Accepted labels, rejected labels, rejected crops, and resets must be explicit append-only decision events.

Memory/Qdrant recall produces tentative suggestions only, such as Marcus? 0.82.

Only accepted, quality-gated crops may enter positive Memory collections.

Rejected/bad crops must be excluded or quarantined so they cannot poison recall.

Transcript/audio/scene context may adjust confidence but cannot override visual evidence.

Agentic escalation must package bounded evidence cases and return observations, uncertainty, contradictions, and human-review recommendations only.

Object detection should be added as a pluggable detector lane, beginning with Ultralytics class filtering and later supporting custom YOLO or bounded open-vocabulary detectors.

Edge Jetsons should run realtime ingest/detect/track/crop/local cache; central Watch should own canonical Memory, audit, readiness, review UI, and project-agent escalation.

Proof gates should become first-class architecture components, not afterthought tests.

<<<WEBGPT_DONE:20260708T022434Z:f5da28cd>>>
