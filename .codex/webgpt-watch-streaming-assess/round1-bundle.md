# Watch Skill — Streaming-Readiness Assessment (Round 1)

current_gate: STREAMING_READINESS_RULING — may Watch open the real-time
streaming lane now, and if not, what is the ONE bounded slice that must land
first? Rule PASS_CURRENT_GATE only if starting streaming work now is justified
by the evidence below; otherwise BLOCKED_CURRENT_GATE with the single concrete
blocker.

stop condition: one DIAGNOSIS + one ruling. No code. No new architecture
documents. No RTSP/drone/F-36 design work.

forbidden adjacent scope: rewriting the batch pipeline, redesigning memory
schemas, UI redesign, Orpheus/TTS anything.

## Who is asking

The Watch project agent, after a live execution session (2026-07-18) that
closed every dry-run gate on the Bad Santa 02:48 Marcus canary. You have
reviewed this project before in this conversation project. Sources below are
pushed at the stated commit; inspect them rather than trusting this summary.

## What is now PROVEN (live, receipts committed)

1. Batch pipeline (frames, transcripts, SRT/Whisper divergence, reports,
   memory upsert/recall): mature, 20/20 sanity.
2. Sequence-ledger semantics at receipt/projection level: exact keyframes vs
   runtime overlays, UNASSIGN_STOP, same-track reassignment after stop,
   YOLO label receipts. NEW: broad handoff-stop smoke
   (`ui/scripts/watchYoloHandoffStopBroad.smoke.ts`) — multi-track,
   multi-cycle stop/reassign, rejection-before-accept, stale-label poisoning
   resistance. All smokes + typecheck green.
3. The 02:48 Marcus canary chain executed LIVE end-to-end:
   - Row text materialized 4/4 channels with hashes + entity spans (zero
     Marcus mentions).
   - Real external reference images downloaded, visually reviewed (6 Marcus
     approved, 4 Willie approved, 2 rejected), embedded, Qdrant-synced.
   - 10 tracker crops embedded; 100 crop/reference similarity comparisons;
     EVERY crop scores higher against Willie than Marcus.
   - Verdict: claim REFUTED. Evidence case WEC-BADSANTAMARCUS0248 filed live
     with ARTIFACT_WINDOW_MISALIGNMENT; recall proof receipts for the canary
     question by natural text, alias, and case lookup.
4. Root-cause bug found and fixed: persisted clips/audio were reused by index
   across runs with different sampling (stale-clip cache), which had silently
   paired rows with the previous run's media. `scripts/storage.py` now
   validates a per-asset `segments_manifest.json` and force-regenerates on
   window mismatch (functionally tested).

## What is OUTSTANDING (known, not streaming)

- Row-7 human Marcus keyframes carry misaligned timestamps (flagged in the
  case; need human re-anchoring).
- Rows ingested before the cache fix are suspect until re-run.
- Qdrant crop collection contains `codex-live-*` smoke-test debris; tests
  should use an isolated collection.
- Durable Memory/Qdrant outbox/retry hardening not started.
- Live-browser handoff-stop breadth: still only the single Qdrant-conflict
  browser proof; broad coverage is receipt/projection-level.
- ux-lab still lazy-imports its legacy Watch UI copy (skill now self-hosts).

## What is ASPIRATIONAL (contract-only, no runtime)

- Live `track_update` events streamed to the UI during playback.
- Source sessions, source PTS, reconnect/backpressure events.
- RTSP/webcam ingestion; multi-asset stream console; drone/telemetry/F-36.
- Watch Agent chat dynamic memory-pipeline status UX.

The standing rule in `local/HANDOFF.md`: "Do not start RTSP/drone/F-36
implementation until source-session contracts and sequence replay gates are
deterministic."

## The question to rule on

The sequence replay gates are now deterministic at the receipt/projection
level (broad smoke), and the canary chain is live-proven including honest
refutation. Source-session contracts exist only as architecture
(`watch_realtime_character_tracking_contract.md`, execution plan, P1 docs).

Given that: is the streaming lane now unblocked? If BLOCKED, name the single
concrete blocker and the one bounded slice (files + live proof) that would
clear it. Consider specifically whether the artifact-misalignment class of
bug (found in batch) implies a required invariant for streaming (e.g.,
window/PTS validation on every persisted observation) before any live source
is attached.

## Research context

Distilled from /brave-search (starting points, not limits):

- Ultralytics natively supports streaming multi-object tracking with
  ByteTrack/BoT-SORT configured via YAML; `model.track(stream=True)` is the
  supported real-time path (docs.ultralytics.com/modes/track). Watch already
  wraps this in `scripts/track_yolo_bytetrack.py`.
- ByteTrack's low-confidence re-association is the standard robustness
  mechanism under occlusion (trackers.roboflow.com/latest/trackers/bytetrack).
- Reference streaming-analytics practice: durable, ordered, partitioned event
  logs at ingestion (Kafka/Redpanda-class), replay capability, and explicit
  backpressure are the load-bearing properties for a trustworthy pipeline
  (redpanda.com fundamentals; mitzu.io analytics-stack writeup). Watch's
  "streamed tracking is provisional / bounded observations stored to memory"
  contract maps onto this, but Watch has no durable ordered event log or
  replay for live sources yet — only fixture JSONL files.
- Open-source RTSP+YOLO+ByteTrack reference implementations exist (e.g.
  aparsoft/yolo-streamlit-detection-tracking) supporting webcam/RTSP/YouTube;
  none address evidence-grade provenance, which is Watch's differentiator.

## Required deliverable

DIAGNOSIS (what is actually working vs outstanding vs aspirational for the
streaming direction, in your own reading of the pushed sources), then exactly
one ruling: PASS_CURRENT_GATE, BLOCKED_CURRENT_GATE: <one concrete blocker>,
or REJECTED_SCOPE_EXPANSION.
