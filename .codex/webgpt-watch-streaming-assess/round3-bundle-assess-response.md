DIAGNOSIS: The consolidated forward path is accurate and no new gate belongs before P0A. The P0A/P0B split resolves the prior overloading: P0A proves immutable acquisition provenance and side-effect-free mismatch rejection; P0B proves idempotent consumer recovery. The journal remains immutable source-derived evidence written only by the tracker boundary, while observations, labels, and cases remain derived records that can be corrected or superseded without altering the journal.

Two corrections should be carried into P0A’s acceptance criteria:

Do not describe the current tracker clock as source PTS. At the pinned commit, media_time_seconds is synthesized from the enumerated result index, frame stride, and reported FPS. P0A must explicitly record clock_mode and use either authoritative decoded PTS or a declared frame-offset clock bound to the source hash and FPS; the two modes must never be mixed. GStreamer’s synchronization model confirms that buffer timestamps are meaningful only relative to the active segment and that out-of-segment timestamps must be rejected or clipped. 
GStreamer
+1

Keep event and observation identity formulas distinct. An event ID should identify one journal position within a source session. An observation ID should additionally bind the track and its first/last event sequence plus the bounded clock window. Mutable evidence values—bbox, crop bytes, candidate identity, and scores—belong in the separate canonical evidence digest so the same natural observation ID collides on divergent evidence rather than silently producing another record.

The debt classification is correct with one sequencing qualification:

Debt	Final classification
Row-7 keyframe re-anchoring	PARALLEL
Re-run pre-fix suspect rows	PARALLEL
Isolated Qdrant/Memory test collections	PREREQUISITE for P0B
Durable Memory/Qdrant outbox/retry	PARALLEL to P0A/P0B, but PREREQUISITE before the first unbounded live source
Live-browser handoff-stop breadth	DEFERRED until after P0B
ux-lab legacy import removal	DEFERRED

Two material items were missing from the consolidated P0A definition:

Journal integrity and finalization: define a session header, committed record framing/checksums, a finalized-session marker, and fail-closed handling of a truncated final record. An append-only filename alone does not make a kill-safe evidence journal.

Producer and crop lineage binding: the session header must bind the source hash, model/version, tracker configuration, confidence/image-size settings, sampling rate/stride, and the crop manifest; every crop consumed by the persistence loop must reference a journal event ID and matching evidence digest. The current persistence loop reads event JSONL and the crop manifest independently and derives Qdrant/Memory identity primarily from overlay IDs or crop paths.

The live proof sequence remains correct. P0A does not require UI consumption. P0B should kill and restart the journal consumer, not the tracker producer, and compare canonical IDs and evidence digests rather than timestamp-bearing receipt bytes. Ultralytics confirms that persistent tracker IDs rely on retained state across consecutive frames from the same stream, so producer-process resume correctly remains a later continuity gate. 
Ultralytics Docs

EVIDENCE: The exact pushed commit f9ede98d95dd10f264053d1a00ead3e368f91a1f and the three declared files were inspected. The tracker currently buffers model.track(stream=True) output into a list and writes the JSONL only after tracking completes; it has no durable per-event sequence, source-session header, authoritative PTS, content digest, or incremental journal commit. The persistence loop reads completed event and crop artifacts, probes services, then performs embedding, Qdrant, and Memory operations, so P0A’s validation must run before that boundary. Project knowledge records both the successful live refutation and the stale-window cache defect, demonstrating that fail-closed provenance is necessary even when downstream identity and recall machinery appears healthy.

CURRENT_GATE: SOURCE_SESSION_JOURNAL_PREFLIGHT_P0A

NEXT_STEP: Proceed with the single recorded-file P0A slice, adding the authoritative clock-mode rule, finalized journal integrity, producer-configuration binding, and event-to-crop digest validation to its existing deterministic-ID and pre-write mismatch proof.

PASS_CURRENT_GATE
