DIAGNOSIS: Watch is not blocked on detection, identity verification, or stop/reassignment semantics; it is blocked at the boundary between replaying prerecorded artifacts and attaching a trustworthy live source. The current live canary proves the evidence pipeline can honestly refute a bad identity claim, but it does not prove that incoming frames, tracker events, crops, and persisted observations remain bound to one source session and the correct media window across restart or reconnect.

EVIDENCE: At commit f9ede98d95dd10f264053d1a00ead3e368f91a1f, the tracking contract is still a candidate artifact: it defines stream_id, source clock, and provisional track_update events, while its completion requirements still include live playback events and UI live/provisional consumption. The execution plan says the current YOLO/ByteTrack log proves event emission and schema validity only, not real-time UI consumption, and its explicit non-completion list still ends with live stream event consumption. The live identity loop reads detached event JSONL and a crop manifest, then persists segment_id and media_time_seconds; the shown persistence path contains no runtime source-session identifier, source PTS/frame offset, source-content hash, or validated window binding. That omission is material because the batch system already silently reused index-matched clips from a different sampling run; the repair had to validate exact start/end windows through segments_manifest.json, and the resulting live case correctly refuted the canary as artifact-window misalignment. Ultralytics also states that tracker state is valid only for consecutive frames from the same stream, while GStreamer distinguishes source presentation timestamps from running time and requires segment-bound timestamp mapping; an ordered immutable log with stable offsets is the standard replay primitive. 
Ultralytics Docs
 
GStreamer
+2
GStreamer
+2

CURRENT_GATE: SOURCE_SESSION_PROVENANCE_REPLAY_P0 — before any RTSP, webcam, or other live source is attached, every emitted track_update and persisted bounded observation must be durably ordered and bound to one source_session_id, source identity hash, source PTS/frame offset, exact observation window, and frame/crop content hash, with deterministic restart replay and fail-closed mismatch detection.

NEXT_STEP: Land one recorded-file source-session canary by modifying skills/watch/scripts/track_yolo_bytetrack.py and skills/watch/scripts/run_realtime_identity_memory_loop.py and adding skills/watch/tests/test_watch_source_session_replay.py: write an append-only event journal containing session ID, event sequence, source hash, source PTS/frame offset, window bounds, and frame/crop hash; terminate and restart the process; replay the journal and require identical observation IDs; then inject one PTS/window mismatch and prove the run rejects it before any Memory or Qdrant write.

BLOCKED_CURRENT_GATE: No runtime source-session journal currently binds ordered tracker events and persisted observations to validated source PTS, media window, and content identity, so opening a real streaming source could reproduce the already-proven artifact-misalignment failure class.

<<<WEBGPT_DONE:20260718T212135Z:6b1afa71>>>
