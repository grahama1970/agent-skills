# Watch Skill — Streaming-Readiness Assessment (Round 3 of 3, reconciliation)

current_gate: FINAL_STATE_RECONCILIATION — confirm or correct the consolidated
state below, name anything MISSING from it (completeness check), and issue one
final ruling on the agreed forward path. No code, no plan document.

stop condition: corrections + at-most-3 missing items + one ruling.
forbidden adjacent scope: new architecture, RTSP detail, UI redesign.

## Consolidated state (from rounds 1-2 plus live receipts; correct if wrong)

WORKING (live-proven):
- Batch video->evidence pipeline (frames, SRT/Whisper divergence, reports,
  memory upsert/recall), 20/20 sanity.
- Sequence-ledger semantics incl. broad handoff-stop smoke (multi-track,
  multi-cycle, rejection-before-accept, stale-label poisoning resistance).
- Live identity evidence chain: row-text materialization, reviewed external
  references (Marcus 6 / Willie 4 approved), 100 live similarity comparisons,
  honest REFUTED verdict on the 02:48 canary, evidence case
  WEC-BADSANTAMARCUS0248 filed with recall receipts.
- Stale-clip cache root cause fixed (segments_manifest.json window
  validation).
- Skill-owned self-hosted UI with barrel export and green typecheck/tests.

OUTSTANDING (agreed classification):
- PREREQUISITE for streaming P0B: isolated Qdrant/Memory collections for
  tests (codex-live-* debris demonstrates the hazard).
- PARALLEL: row-7 keyframe re-anchoring; re-run of pre-fix suspect rows;
  Memory/Qdrant outbox hardening.
- DEFERRED: live-browser handoff-stop breadth (next gate after replay);
  ux-lab legacy import removal.

ASPIRATIONAL (contract-only until P0A/P0B/UI gates pass):
- Live track_update streaming to UI; source sessions over RTSP/webcam;
  multi-asset console; drone/telemetry/F-36 lanes.

NEXT STEPS (agreed sequence):
1. P0A SOURCE_SESSION_JOURNAL_PREFLIGHT: shared immutable journal module
   (tracker adapter = only append writer; persistence loop = read-only
   consumer); deterministic event_id/observation_id from
   schema_version|source_session_id|sequence|window PTS; canonical evidence
   digest separate from ID; injected same-position PTS/window/content
   mismatch rejected before probe_services/embedding/Qdrant/Memory.
2. P0B JOURNAL_CONSUMER_REPLAY: kill mid-consumption, restart against
   unchanged journal, identical canonical observation IDs+digests in
   isolated collections; compare canonical set, not timestamped bytes.
3. Then UI live-event consumption gate; then tracker process-resume
   continuity; only then first live source (webcam/RTSP).

## Completeness check

Name up to 3 material items MISSING from the consolidated state above —
modality not covered, unverified claim, or risk not represented. If none,
say so.

## Required deliverable

DIAGNOSIS (corrections + missing items), then exactly one ruling:
PASS_CURRENT_GATE (consolidated state and sequence are accurate; proceed
with P0A), BLOCKED_CURRENT_GATE: <the correction that must land first>, or
REJECTED_SCOPE_EXPANSION.
