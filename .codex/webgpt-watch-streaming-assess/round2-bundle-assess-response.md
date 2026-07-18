DIAGNOSIS: The P0 slice is directionally correct but not right-sized as written because it conflates two different crash boundaries:

Tracker/acquisition restart: restoring YOLO/ByteTrack state, source cursor, and track IDs after a producer process dies.

Journal-consumer restart: replaying already acquired immutable events into deterministic bounded observations and idempotent persistence.

At the pinned commit, track_yolo_bytetrack.py calls model.track(..., stream=True) but accumulates the resulting events into a list and writes the JSONL only after tracking finishes. It synthesizes source_frame_index from the emitted-result index and stride, then derives media time from FPS; it does not capture source PTS, a durable event sequence, frame hash, or an incrementally durable journal. Ultralytics documents that persistent track IDs depend on consecutive frames from the same stream and retained tracker state; process-level tracker restart is therefore a separate continuity problem, not something the persistence replay proof can safely assume away. 
Ultralytics Docs

The smallest first cut should be:

SOURCE_SESSION_JOURNAL_PREFLIGHT_P0A

Produce one complete recorded-file source-session journal.

Validate its source identity, monotonically increasing event sequence, source PTS or frame offset, declared window, and frame/crop digest.

Derive a deterministic, side-effect-free observation plan.

Inject one same-position PTS/window/content mismatch and reject it before probe_services, embedding, Qdrant, or Memory is called.

Crash/restart persistence replay should be the immediately following P0B slice. Killing and restarting the tracker itself should not be part of P0A or P0B; tracker-state resume is a later live-source continuity gate.

Journal placement: use one shared journal module composed by both scripts. The tracker adapter is the only append writer, because it owns acquisition order and the frame/PTS boundary. The persistence loop is a read-only validator and consumer. The journal is immutable source-derived acquisition evidence; bounded observations are derived records that may later be superseded or corrected through overlays and evidence cases. This matches the Watch contract’s rule that frame/clip/telemetry evidence is immutable while corrections are separate overlays or cases.

Observation identity: do not derive durable IDs from overlay_id, crop path, wall-clock time, mutable candidate labels, or the evidence digest itself. The current loop derives Qdrant IDs and Memory keys from overlay IDs or crop paths, which does not establish source-session replay identity. Use:

event_id =
  uuid5(namespace,
        schema_version |
        source_session_id |
        event_sequence)

observation_id =
  uuid5(namespace,
        schema_version |
        source_session_id |
        track_id |
        first_event_sequence |
        last_event_sequence |
        window_start_pts |
        window_end_pts)

Store a separate canonical evidence digest covering source hash, PTS/frame offset, window bounds, bbox, and frame/crop hash. Replay of the same journal produces the same ID and digest; changed evidence at the same natural position produces the same ID but a different digest and must fail closed. Namespace/name UUID generation is deterministic, while an ordered append log needs stable sequence positions that do not change during replay. 
Python documentation
+1

Valid PTS/window checking is load-bearing rather than optional: GStreamer defines synchronization from buffer PTS/DTS and the active segment, and treats buffers outside the segment boundaries as invalid for that segment. 
GStreamer
+1
 Watch’s own stale-clip repair demonstrates the same invariant in batch mode: index equality was insufficient, so persisted media is reused only when its recorded start and end window match.

Outstanding debt	Classification	Relation to P0
a. Row-7 Marcus keyframe re-anchoring	PARALLEL	Required before trusting those human timestamps, but P0A should use a fresh recorded-file session and no row-7 evidence.
b. Re-run pre-fix suspect rows	PARALLEL	Batch-data remediation is independent of the source-session journal mechanism.
c. codex-live-* Qdrant debris and live test collection	PREREQUISITE	P0B must use dedicated isolated collection names; historical debris cleanup itself can proceed separately.
d. Durable Memory/Qdrant outbox and retry	PARALLEL	Necessary before production streaming, but journal replay can first rely on stable idempotent keys and isolated sinks.
e. Live-browser handoff-stop breadth	DEFERRED	UI consumption is the gate after source-session replay is trustworthy.
f. ux-lab legacy Watch import	DEFERRED	Hosting consolidation does not affect source-session provenance or replay.

The proposed live proof is sufficient only after its crash boundary is corrected:

P0A: completed journal, deterministic no-write observation plan, and injected mismatch rejected before any external call.

P0B: kill run_realtime_identity_memory_loop.py mid-consumption, restart it against the unchanged journal, and require identical canonical observation IDs and evidence digests in isolated Qdrant/Memory targets.

Do not require byte-identical timestamped receipts; compare the canonical observation set, excluding operational fields such as updated_at.

Do not require a UI consumption receipt in P0. The architecture explicitly separates provisional live events from bounded persisted observations, and UI live-event consumption remains the next gate.

EVIDENCE: The exact detached SHA f9ede98d95dd10f264053d1a00ead3e368f91a1f was used for all repository reads. The tracker currently has neither incremental journal durability nor authoritative PTS provenance; the persistence loop consumes completed JSONL/crop manifests and begins Qdrant writes before constructing Memory observations; the batch cache defect already proved that source-window misbinding can produce convincing but false identity evidence.

CURRENT_GATE: SOURCE_SESSION_JOURNAL_PREFLIGHT_P0A

NEXT_STEP: Amend the slice definition so the first bounded implementation adds the shared immutable journal writer/reader and a side-effect-free preflight test that proves deterministic IDs plus fail-closed PTS/window/content mismatch rejection; move kill/restart persistence replay into P0B and leave tracker process-resume and UI consumption for later gates.

BLOCKED_CURRENT_GATE: The current P0 slice conflates tracker-state crash recovery with deterministic journal-consumer replay; split it so immutable journal creation and pre-write mismatch validation land before kill/restart persistence replay.
