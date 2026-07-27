# Handoff Report: Watch

**Generated**: 2026-07-27T15:13:44-04:00
**Repository**: `/home/graham/workspace/experiments/agent-skills`
**Observed local branch**: `battle-adaptive-lineage-goal` at `6288f3c63`
**Observed upstream**: `origin/battle-adaptive-lineage-goal`
**Canonical proof branch checked**: `origin/main`

## 1. Project Overview

Watch turns video into timecode-aligned evidence: frames, captions/SRT,
Whisper transcripts, scene rows, reports, Memory records, YOLO detector
observations, human identity decisions, and browser-visible annotation state.

The most important invariant is the immutable identity ledger:

1. Detector track IDs and YOLO boxes are observations, not identity truth.
2. Memory/Qdrant recall may produce tentative suggestions only.
3. Human accept/reject/stop/reassign actions own accepted identity state.
4. A stop closes the current segment, and identity must not propagate across it.
5. Explicit reassignment starts a new segment, even for the same detector track.
6. Local receipts persist before remote Memory synchronization.
7. Reload and restart must replay the same projected identity state.

Pyannote now adds a separate audio-evidence lane for anonymous speaker topology.
`SPEAKER_00` style labels are acoustic clusters only; they must not be promoted
to actor, character, or real-world identity without separate accepted evidence.

## 2. Current State

### Immutable Goal Status

The Watch immutable goal has deterministic local proof artifacts on
`origin/main`:

- Latest pointer:
  `skills/watch/proofs/immutable-goal/latest.json`
- Manifest:
  `skills/watch/proofs/immutable-goal/04259f28d65124ba253dc60a88f0745b49ceb90e/manifest.json`
- Proof commit bound by manifest:
  `04259f28d65124ba253dc60a88f0745b49ceb90e`
- Durable proof commit on `origin/main`:
  `e6398fcb7ebe61af545a4e71b1ab0b34c4f42bb5`

Manifest facts from `origin/main`:

```json
{
  "schema": "watch.immutable_goal_proof.v1",
  "status": "PASS",
  "mocked": false,
  "live": true,
  "commit_sha": "04259f28d65124ba253dc60a88f0745b49ceb90e"
}
```

The manifest assertions include:

- live Qdrant-backed Memory suggestion
- tentative suggestion non-mutation
- human accept persistence
- stop persistence
- identity absent after stop
- explicit reassignment persistence
- reload hydration
- Memory sync stored
- pyannote live CUDA diarization
- anonymous speaker evidence written
- pyannote does not promote identity

Command receipt:
`skills/watch/proofs/immutable-goal/04259f28d65124ba253dc60a88f0745b49ceb90e/command-results.json`

All recorded subcommands exited `0` on 2026-07-23:

- `npm run test:backend-immutable`
- `npm run typecheck`
- `npm run build`
- `npm run test:memory-suggestion-live`
- `npm run test:immutable-browser-live`
- `npm run test:pyannote-immutable-live`

Committed proof artifacts include 18 files: row-9 suggestion JSON, row-10
projection/receipt JSON, five browser screenshots, command results, manifest,
and the pyannote e2e fixture outputs.

Pyannote proof artifacts:

- `skills/watch/proofs/immutable-goal/04259f28d65124ba253dc60a88f0745b49ceb90e/pyannote-immutable-e2e/pyannote-diarization.json`
- `skills/watch/proofs/immutable-goal/04259f28d65124ba253dc60a88f0745b49ceb90e/pyannote-immutable-e2e/pyannote-e2e-summary.json`
- `skills/watch/proofs/immutable-goal/04259f28d65124ba253dc60a88f0745b49ceb90e/pyannote-immutable-e2e/pyannote-report-speaker-rows.json`
- `skills/watch/proofs/immutable-goal/04259f28d65124ba253dc60a88f0745b49ceb90e/pyannote-immutable-e2e/source-audio.wav`
- `skills/watch/proofs/immutable-goal/04259f28d65124ba253dc60a88f0745b49ceb90e/pyannote-immutable-e2e/source-video.mp4`

### Local Branch State

This checkout is not a clean Watch integration branch. It is currently on
`battle-adaptive-lineage-goal`, and `git status --short -- skills/watch` shows
Watch-local modified files plus many untracked generated artifacts.

Modified Watch files observed:

- `skills/watch/docs/architecture/create-architecture/watch-reference-hydration-P0/solution/extracted/repo/skills/watch/tests/test_watch_reference_hydration_P0.py`
- `skills/watch/pyproject.toml`
- `skills/watch/tests/test_watch_live_ultralytics_tracking.py`
- `skills/watch/tests/test_watch_reference_download_review_approval_receipt.py`
- `skills/watch/tests/test_watch_source_session_replay.py`
- `skills/watch/tests/test_watch_visual_descriptions.py`

Untracked Watch areas observed include:

- `skills/watch/docs/architecture/generated/...`
- `skills/watch/out/`
- `skills/watch/services/`
- `skills/watch/tests/test_diarization_service_engine.py`
- `skills/watch/tests/test_watch_tracking_crop_extraction.py`

Treat those paths as existing local work. Do not clean, reset, stash, or stage
them broadly.

Recent Watch commits visible on this branch:

- `d3fffcbb2 watch: land P0C session-chained resume, P0D outbox, first live source`
- `73b5a4b56 watch: land UI live-event consumption gate with browser proof`
- `af6b82f72 watch: land P0A/P0B source-session journal + fail-closed replay`
- `cbcd81ea0 watch: record streaming gate from 3-round WebGPT assessment`
- `48bbca654 watch: execute Marcus canary live; refute 02:48 claim; fix stale-clip cache`
- `bfa3e87d1 watch: add handoff report`
- `13fa1e9ad watch: persist row 9 yolo stop restart receipt`
- `cc12ba6e7 watch: restore row detector candidates in annotation modal`

The source-session commits are branch-local context. Reconcile them deliberately
against `origin/main` before treating them as canonical Watch behavior.

## 3. Working Well

- Immutable backend receipts are covered by replay, concurrency, and detector
  isolation smokes.
- The browser immutable flow proves accept -> stop -> reassign -> reload for
  the tested row-10 path.
- The row-9 Memory/Qdrant suggestion path is live and remains tentative.
- Receipt projection returns null between stop and reassignment.
- Memory sync state is durable and included in persisted receipts.
- The pyannote live gate runs through Docker/CUDA service integration and
  writes anonymous speaker evidence without identity promotion.
- `origin/main` includes package scripts for:
  - `test:backend-immutable`
  - `test:memory-suggestion-live`
  - `test:immutable-browser-live`
  - `test:pyannote-immutable-live`
  - `test:immutable-goal-live`
  - `prove:immutable-goal`

## 4. Known Risks And Gaps

- The local workspace is dirty. Use a clean worktree from `origin/main` for
  proof reruns, mainline edits, or cherry-picks unless the current branch work
  is the explicit target.
- The immutable goal is proven for bounded canary paths, not for broad identity
  recognition, general tracking reliability, or paper-grade generalization.
- `skills/watch/scripts/watch.py` still fails closed for `--doc2qra`; optional
  scene-level doc2qra integration is not implemented.
- `skills/watch/docs/PROJECT_KNOWLEDGE.md` records a row-text materialization
  gap: `srt_text` has no source ref in the noted gate.
- Live gates depend on local services and assets:
  - Memory daemon on `http://127.0.0.1:8601`
  - pyannote service on `http://127.0.0.1:9001`
  - `HF_TOKEN` available for pyannote model access
  - Watch UI npm dependencies installed
- Generated receipts under `skills/watch/docs/architecture/generated/` are not
  automatically durable evidence. Commit only intentional proof artifacts.
- Streaming/source-session work is active but should not dilute or replace the
  immutable ledger gate.

## 5. Next Steps

1. For immutable-goal verification, use a clean `origin/main` worktree and
   inspect:

```bash
cat skills/watch/proofs/immutable-goal/latest.json
jq '{schema,status,mocked,live,commit_sha,assertions}' \
  skills/watch/proofs/immutable-goal/04259f28d65124ba253dc60a88f0745b49ceb90e/manifest.json
jq '[.[] | {name, command, exit_code}]' \
  skills/watch/proofs/immutable-goal/04259f28d65124ba253dc60a88f0745b49ceb90e/command-results.json
```

2. To rerun the full gate, first confirm Memory and pyannote health, then run:

```bash
npm --prefix skills/watch/ui run prove:immutable-goal
```

3. If continuing pyannote work, keep it scoped to anonymous speaker evidence:
   diarization quality, public fixture reproducibility, service health,
   transcript alignment, and report/Memory provenance. Do not auto-map speaker
   clusters to characters.

4. If continuing source-session P0 work from this branch, first inventory and
   preserve local Watch changes. Then reconcile the branch commits against
   `origin/main` without broad stash/reset/clean operations.

5. Keep new Watch changes on one proof ladder at a time:
   - immutable identity ledger
   - pyannote anonymous speaker topology
   - source-session replay/outbox/live events
   - report/documentation contract alignment

## 6. Key Files

- Skill contract: `skills/watch/SKILL.md`
- README: `skills/watch/README.md`
- Project knowledge: `skills/watch/docs/PROJECT_KNOWLEDGE.md`
- Batch runtime: `skills/watch/scripts/watch.py`
- CLI wrapper: `skills/watch/scripts/cli.py`
- Diarization client: `skills/watch/scripts/diarization.py`
- Speaker attribution: `skills/watch/scripts/speaker_attribution.py`
- Pyannote service: `skills/watch/services/diarization/`
- UI package scripts: `skills/watch/ui/package.json`
- Immutable runner: `skills/watch/ui/scripts/watchImmutableGoalLive.smoke.ts`
- Browser gate: `skills/watch/ui/scripts/watchImmutableGoalBrowserLive.smoke.ts`
- Pyannote gate: `skills/watch/ui/scripts/watchPyannoteImmutableLive.smoke.ts`
- Proof utilities: `skills/watch/ui/scripts/proofUtils.ts`
- Latest proof pointer: `skills/watch/proofs/immutable-goal/latest.json`

## 7. Operating Rules For The Next Agent

- Do not treat detector `track_id` as identity truth.
- Do not let Memory/Qdrant suggestions mutate accepted identity.
- Do not propagate identity across a stop.
- Do not auto-promote pyannote speaker clusters to character identity.
- Do not claim UI behavior from DOM assertions alone; use screenshots/browser
  evidence for visible-state claims.
- Do not use mocked tests as final proof for live Memory, pyannote, or browser
  claims.
- Do not clean or reset the current dirty workspace. Stage only task-relevant
  files.

## 8. Current Handoff Evidence

mocked: no
live: no fresh live rerun in this handoff refresh
actually exercised: local handoff/watch skill reads, Watch git history
inspection, `origin/main` proof manifest inspection, command receipt inspection,
Watch path dirty-state inspection
remaining unverified here: fresh local rerun of `prove:immutable-goal`, fresh
browser screenshot from this checkout, reconciliation of dirty local branch work
against `origin/main`
