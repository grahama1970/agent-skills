# Handoff: Rolling Window Frame Extraction

## Current State

The watch skill has a hard frame cap of 500 frames (`max_frames_capped = min(max_frames, 500)`). For long videos (>10 min), the auto-fps calculation or scene-change detection produces `target` frames that exceed this cap. The current behavior truncates: it caps at 500, which means long videos get undersampled (e.g., a 2-hour movie at 500 frames = one frame every 14 seconds).

The pipeline extracts frames in a single pass via ffmpeg, then builds scene elements aligned to those frames. The Whisper transcription covers the full audio regardless of frame count. The SRT captions are also full-length.

## Problem

Long videos hit the frame cap and lose temporal resolution. The 500-frame limit is arbitrary — it was raised from 100 to 500 as a quick fix. A 2-hour movie needs ~800-1200 scene-change frames for adequate coverage.

## Recent Changes

- Frame cap raised from 100 to 500
- Scene detection changed from single-pass with `-frames:v` to unlimited detection + subsampling
- Config moved to `config.py` with env vars
- Frame budget defaults changed

## Files in Scope

- `scripts/watch.py` — main pipeline orchestration
- `scripts/frames.py` — frame extraction functions
- `scripts/storage.py` — memory upsert
- `scripts/report.py` — report generation
- `scripts/config.py` — configuration

## What Must Not Be Disturbed

- The FSRCNN-based scene detection logic
- The Whisper Docker transcription pipeline
- The SRT auto-extraction
- The divergence intelligence (diff_intelligence.py)
- The memory upsert to watch_content + persona_memory
- The CLI flags and existing API

## Next Build Step

Design and implement a rolling window extraction mechanism that automatically splits long videos into chunks, processes each chunk independently, and merges the results into a unified report and memory store.
