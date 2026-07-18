# Watch Skill — Streaming-Readiness Assessment (Round 2 of 3)

current_gate: P0_SLICE_VALIDATION — your Round 1 ruling (same conversation)
was BLOCKED_CURRENT_GATE on SOURCE_SESSION_PROVENANCE_REPLAY_P0, with this
next step: modify `skills/watch/scripts/track_yolo_bytetrack.py` and
`skills/watch/scripts/run_realtime_identity_memory_loop.py`, add
`skills/watch/tests/test_watch_source_session_replay.py`; append-only event
journal (session id, sequence, source hash, source PTS/frame offset, window
bounds, frame/crop hash); kill/restart; replay must yield identical
observation IDs; one injected PTS/window mismatch must be rejected before any
Memory or Qdrant write.

This round rules on whether that P0 slice is right-sized and correctly
sequenced against the project's other outstanding debt. Do NOT produce code
or a full task plan. DIAGNOSIS + one ruling.

stop condition: DIAGNOSIS + classification table + one ruling.
forbidden adjacent scope: RTSP/drone implementation detail, UI redesign,
memory schema redesign, Orpheus.

## Questions to answer inside the DIAGNOSIS

1. Right-sizing: is the P0 slice above achievable as ONE bounded slice, or
   does it hide multiple gates (journal format vs replay determinism vs
   mismatch rejection)? If it must split, name the smallest first cut.
2. Journal placement: should the journal be written by the tracker adapter
   (`track_yolo_bytetrack.py`), by the persistence loop
   (`run_realtime_identity_memory_loop.py`), or as a separate module both
   compose? Watch's contract says frames/clips/etc. are immutable and
   corrections are overlays/cases — does the journal count as source evidence
   (immutable) or derived observation (correctable)?
3. Observation ID determinism: the persistence loop currently derives point
   ids/keys from overlay ids (uuid5 namespace). What must the ID be derived
   from so restart replay is provably identical (and collides on divergence)?
4. Sequencing of outstanding non-streaming debt — classify each as
   PREREQUISITE (blocks P0), PARALLEL (independent), or DEFERRED:
   a. Row-7 human Marcus keyframes need timestamp re-anchoring (case-flagged).
   b. Rows ingested before the stale-clip cache fix are suspect until re-run.
   c. Qdrant crop collection contains codex-live-* smoke-test debris; tests
      write to the live collection.
   d. Durable Memory/Qdrant outbox/retry hardening (not started).
   e. Live-browser handoff-stop breadth (only one Qdrant-conflict browser
      proof; broad coverage is receipt/projection level).
   f. ux-lab still lazy-imports its legacy Watch UI copy.
5. The live proof for P0: is "kill -9 mid-run, restart, byte-identical
   observation set, injected mismatch rejected pre-write" sufficient, or must
   the proof also include a UI consumption receipt (contract requires live
   overlay consumption eventually — is that THIS gate or the next)?

## Required deliverable

DIAGNOSIS covering the five questions, a classification table for 4a-4f,
then exactly one ruling for the P0 slice definition:
PASS_CURRENT_GATE (slice is right-sized; proceed),
BLOCKED_CURRENT_GATE: <what must change in the slice definition>, or
REJECTED_SCOPE_EXPANSION.
