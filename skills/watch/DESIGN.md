# Watch Skill — Design

## Purpose

Turn any video (URL, local file, or movie title) into inspectable evidence:
scene-change frames, transcript, SRT emotion/scene analysis, a scene element
table, and Memory-recallable `watch_content` records that let an agent answer
questions about the video like a human viewer — bounded by extracted evidence.

## Architecture

```text
run.sh (Typer CLI, scripts/watch.py)
  ├─ source resolution: URL | local path | movie title (library fuzzy match →
  │    ingest-movie search/Radarr → Bazarr English SRT)
  ├─ frames.py        ffmpeg scene-change / uniform extraction, rolling-window
  │                   chunking for ≥10min videos (300s chunks, 3s overlap)
  ├─ download.py      yt-dlp
  ├─ transcribe.py    captions (ingest-youtube) → SRT parse → scillm Whisper
  ├─ scenes.py        SRT emotion/tag/query analysis (adapted from ingest-movie)
  ├─ report.py        report.json + report.md + report.html + frames_manifest.json
  └─ video_memory.py  memory daemon (:8601) upsert/recall over watch_content;
                      brave-search corroboration (never authority)
ui/ (React TypeScript, mounted by ux-lab Express API :3001)
  └─ WatchReportView, Orpheus annotation, YOLO identity ledger, chat sidebar
proofs/immutable-goal/<sha>/manifest.json   live gate receipts
```

## Key decisions

- **Composition over reimplementation**: transcript → `ingest-youtube`,
  acquisition → `ingest-movie` only, Whisper → scillm, storage → `$memory`
  daemon only (no direct Arango/Qdrant).
- **Evidence layers stay separate**: SRT text, Whisper text, VLM frame
  descriptions, YOLO observations, pyannote speaker turns (contract defined),
  and human-accepted identity are distinct lanes; none may overwrite another.
- **Fail-closed answers**: appearance questions require frame-derived visual
  evidence; Brave corroboration can never override or substitute for extracted
  watch evidence.
- **Immutable YOLO identity ledger**: detector `track_id` is observation, not
  identity; human accept required; stops close segments; receipts persist
  locally before Memory sync. Proven by the live npm immutable-goal gate
  (`npm --prefix ui run prove:immutable-goal`), receipts under
  `proofs/immutable-goal/<git-sha>/`.
- **Heavy artifacts on 12TB**: frames/audio under `WATCH_MEDIA_ROOT`
  (defaults to `~/.local/share/agent-skills/watch-frames`; media library on
  `/mnt/storage12tb/media/`).

## Immutable goal

`docs/GOAL.md` (UI self-containment slice) plus the immutable YOLO identity
ledger contract in SKILL.md. Gate commands (must run live, not mocked):

```bash
npm --prefix skills/watch/ui test && npm --prefix skills/watch/ui run typecheck
npm --prefix skills/watch/ui run build
npm --prefix skills/watch/ui run test:memory-suggestion-live
npm --prefix skills/watch/ui run test:immutable-browser-live
npm --prefix skills/watch/ui run test:pyannote-immutable-live
npm --prefix skills/watch/ui run prove:immutable-goal
```

## Evaluation

- `sanity.sh` — 19-check e2e (imports, CLI, live memory recall proof, scene
  elements, persona records).
- `fixtures/agentic_eval.json` — retained $agentic-evals fixture: live
  sanity e2e with independent memory-daemon readback oracle
  (`watch.sanity.e2e_live`), negative/adversarial fail-closed source
  resolution cases (`watch.source_resolution.fail_closed`), per-feature
  pipeline checks, and backend immutable identity smoke tests.
- `docs/IDENTITY_PIPELINE_NEXT_STEPS.md` — WebGPT-reviewed sequence for
  landing segment-scoped identity promotion without treating model scores,
  diarization, SRT mentions, or Memory/Qdrant output as accepted identity.

## Current gaps

- Full immutable-goal proof needs a clean `wt` lane because the monorepo
  primary checkout is intentionally dirty; do not weaken `assertCleanWorktree`.
- Identity promotion is not enabled. Reference adjudication, shadow calibration,
  stale-evidence gates, and human review receipts must land first.
- Immutable-goal proof manifests are pinned to older commits; re-run the gate
  at HEAD in a clean lane after ledger-relevant changes.
