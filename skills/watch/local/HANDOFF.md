# Handoff Report: Watch

**Generated**: 2026-07-16T15:42:36-04:00  
**Repository**: `/home/graham/workspace/experiments/agent-skills`  
**Local branch observed by handoff gatherer**: `battle-ux8-live-contract`  
**Canonical remote checked**: `origin/main`

## 1. Project Overview

Watch turns video into timecode-aligned evidence that agents and humans can inspect, annotate, recall, and later bind into evidence cases.

The project currently has three overlapping layers:

1. Batch video analysis: local/web video ingestion, frames, transcripts, QRA scenes, reports, and memory writes.
2. Watch annotation UX: human/YOLO-assisted annotation, exact keyframes, held/interpolated overlays, unassign stops, YOLO label receipts, Memory/Qdrant tentative suggestions.
3. Streaming/world-model direction: source sessions, detector observations, sequence events, evidence bundles, and later F-36/drone/Embry OS integration.

The immediate durable product object is the Watch sequence ledger: detector boxes are raw observations; Watch owns identity/subject assignment over time, including `UNASSIGN_STOP`, persistence, hydration, and reassignment.

## 2. Current State (Doc-Code Alignment)

### Implemented

- Batch pipeline exists under `skills/watch/scripts/`.
- Watch UI exists under `skills/watch/ui/`.
- UI smoke tests are wired in `skills/watch/ui/package.json`:
  - `scripts/watchAnnotationSession.smoke.ts`
  - `scripts/watchYoloSequenceProjection.smoke.ts`
  - `scripts/watchYoloLabelReceiptReplay.smoke.ts`
- Recent local Watch commits include:
  - `1d27db32c watch: prove yolo label receipt replay`
  - `15c4da3e6 watch: stop yolo label leakage across sequence events`
  - `90aaa4991 watch: expose row10 annotation smoke test`
  - `39f3d1e10 watch: reconcile batch contract drift`
- `origin/main` has newer Watch commits:
  - `13fa1e9ad watch: persist row 9 yolo stop restart receipt`
  - `cc12ba6e7 watch: restore row detector candidates in annotation modal`
  - `f3d596fca watch: preserve yolo stop ledger after hydration`
  - `4b61fbcd1 watch: register WebGPT browser oracle`
  - `7eb4dde9c watch: align runtime frame budget default`
  - `60e652179 watch: fail closed for disabled doc2qra option`
  - `0d8f69037 watch: repair cast lookup URL quoting`
  - `0e2e15a6a watch: delegate movie acquisition to ingest-movie`

### Proven Recently Outside This Local Branch

The row-9 immutable-goal proof was produced from a clean main checkout in `/tmp/agent-skills-watch-main`.

Important artifacts:

- Browser screenshot: `/tmp/codex-ui-verification/agent-skills-watch-main/watch-row9-yolo-stop-restart-proof/20260716T183818Z.png`
- Before/after browser-oracle JSON:
  - `/tmp/codex-ui-verification/agent-skills-watch-main/watch-row9-track2-restart-after-stop-corrected/20260716T183016Z.json`
  - `/tmp/codex-ui-verification/agent-skills-watch-main/watch-row9-track2-stop-before-restart-corrected/20260716T183157Z.json`
- WebGPT review response: `.codex/webgpt-watch-immutable-goal/round5-row9-stop-restart-proof-assess-response.md`
- Pushed commit on `origin/main`: `13fa1e9ad watch: persist row 9 yolo stop restart receipt`

That proof established the current row-9 gate on main: a YOLO track can be assigned, stopped/unassigned, restarted, and visibly rehydrated without leaking the prior identity across the stop.

### Drift / Misalignment

- This local checkout is not currently at `origin/main`; Watch status must distinguish local branch state from canonical main.
- `skills/watch/docs/PROJECT_KNOWLEDGE.md` contains both current facts and historical/planned statements. Treat it as useful context, not a single authoritative implementation map.
- Generated Watch artifacts under `skills/watch/docs/architecture/generated/` are mostly untracked in this checkout. Decide which receipts are durable project evidence before staging them.
- Streaming, generic object tracking, F-36 evidence contracts, Embry OS hosting, and live RTSP are still intended/architectural unless backed by a specific proof artifact.

## 3. What is Working Well

- Watch has a real local skill structure with CLI, scripts, UI, docs, and tests.
- The batch video path is materially implemented: frame extraction, transcripts, reports, visual descriptions, memory-facing records, and recall scoping.
- The annotation reducer has mature semantics compared with earlier states:
  - exact keyframes are separate from runtime-held/interpolated overlays;
  - runtime overlays are not canonical evidence;
  - `UNASSIGN_STOP` exists as a first-class sequence concept;
  - same detector track can be reassigned after a stop;
  - YOLO label receipts exist for replay/projection tests.
- `origin/main` contains the latest Watch repairs for ingest ownership, cast lookup, doc2qra fail-closed behavior, frame-budget alignment, browser-oracle registration, and row-9 YOLO stop/restart persistence.
- README documents the YOLO materializer and detector-candidates endpoint for row-level Watch annotation.

## 4. What is Currently Broken

### Local Environment / Repository State

- The full repository has unrelated merge conflicts in `skills/persona-dream/`:
  - `skills/persona-dream/run.sh`
  - `skills/persona-dream/scripts/write_phase11_dry_run_bundle.py`
  - `skills/persona-dream/scripts/write_phase11_media_requirement_manifest.py`
  - `skills/persona-dream/tests/test_phase11_dry_run_bundle.py`
  - `skills/persona-dream/tests/test_phase11_media_requirement_manifest.py`
- Those conflicts are outside Watch, but they can block committing from this checkout.
- This handoff does not resolve or touch those unrelated conflicts.

### Watch Proof Commands In This Checkout

Attempted narrow proof commands:

```bash
cd skills/watch/ui && npm test
cd skills/watch/ui && npm run typecheck
```

Result: both commands produced no stdout and became stuck as plain `npm` processes in uninterruptible sleep:

```text
590095 DNs npm   cwd=/home/graham/workspace/experiments/agent-skills/skills/watch/ui
590104 DNs npm   cwd=/home/graham/workspace/experiments/agent-skills/skills/watch/ui
```

`kill` and `kill -9` did not terminate them because they are in kernel `D` state. This is an environment/I/O blocker for local proof in this checkout, not evidence that the Watch tests passed or failed.

### Product / Feature Risks

- Broad identity reliability is still canary-grade. Row-9/row-10 sequence semantics are useful gates, not proof of production character recognition.
- Rejected-crop poisoning resistance is not broadly proven across all query paths.
- Durable Memory/Qdrant outbox and retry semantics remain an outstanding hardening item.
- General object tracking and configurable detector profiles are not complete production features.
- Live source sessions, source PTS, reconnect/backpressure events, and RTSP/webcam workflows are not complete.
- F-36/drone/Embry OS integration remains contract-first architecture work, not a completed runtime.

## 5. Next Steps

1. Update this working tree to the canonical Watch state on `origin/main` before new Watch work.
   - Key target: include `13fa1e9ad` and its preceding Watch commits.
2. Resolve or move away from unrelated `skills/persona-dream` merge conflicts before trying to commit from this checkout.
3. Re-run narrow Watch proofs from a clean state:

```bash
cd skills/watch/ui
npm test
npm run typecheck
```

4. Re-run the row-9 or row-10 browser-oracle proof after reload:
   - verify sequence ledger visible in UI;
   - verify stop/unassign persists;
   - verify the same YOLO track stays unassigned until explicit reassignment;
   - verify old identity does not leak over the stop.
5. Decide which generated receipts under `skills/watch/docs/architecture/generated/` are durable evidence and commit only those receipts intentionally.
6. Keep the next Watch code slice focused on one of these gates:
   - sequence ledger durability and UI visibility;
   - detector-candidate materialization for every report row;
   - Memory/Qdrant suggestion/readiness hardening;
   - contract reconciliation in `SKILL.md`, README, and project knowledge.
7. Do not start RTSP/drone/F-36 implementation until source-session contracts and sequence replay gates are deterministic.

## 6. Project Context for Success

### Key Files

- Skill contract: `skills/watch/SKILL.md`
- User-facing README: `skills/watch/README.md`
- Project knowledge: `skills/watch/docs/PROJECT_KNOWLEDGE.md`
- Batch runtime: `skills/watch/scripts/watch.py`
- CLI wrapper: `skills/watch/scripts/cli.py`
- Memory recall: `skills/watch/scripts/video_memory.py`
- YOLO materializer: `skills/watch/scripts/materialize_yolo_bytetrack_for_report.py`
- YOLO label sequence viewer: `skills/watch/scripts/show_yolo_label_sequence.py`
- UI package: `skills/watch/ui/package.json`
- UI server: `skills/watch/ui/server/index.ts`
- Annotation reducer/session logic: `skills/watch/ui/src/watchAnnotationSession.ts`
- Main report/annotation view: `skills/watch/ui/components/WatchReportView.tsx`
- Row-10 annotation smoke: `skills/watch/ui/scripts/watchAnnotationSession.smoke.ts`
- YOLO sequence projection smoke: `skills/watch/ui/scripts/watchYoloSequenceProjection.smoke.ts`
- YOLO label receipt replay smoke: `skills/watch/ui/scripts/watchYoloLabelReceiptReplay.smoke.ts`

### Operating Rules

- Detector output is not identity truth. YOLO/ByteTrack supplies detector observations and track IDs only.
- Watch owns subject sequences over detector observations.
- `UNASSIGN_STOP` closes an active identity segment at the effective time.
- A later Memory/Qdrant suggestion is tentative and must not restart assignment by itself.
- Reassignment starts a new Watch sequence segment, even if the detector `track_id` is the same.
- Runtime-held and runtime-interpolated boxes must not become canonical evidence records.
- Browser screenshots are required for UI-facing claims; DOM/text checks alone are insufficient.

### Current Best Overall Status

Watch is near a useful canary milestone for movie annotation and YOLO-assisted identity labeling, but not production-complete. The highest-value next step is to keep row-9/row-10 sequence replay as the invariant gate, then use that same sequence contract for broader object/asset tracking.

mocked: no  
live: partial  
actually exercised in this handoff: local source/docs inspection, git history inspection, remote main fetch, attempted Watch UI proof commands  
unverified in this handoff: current local UI test results, current local typecheck results, fresh browser screenshot from this checkout
