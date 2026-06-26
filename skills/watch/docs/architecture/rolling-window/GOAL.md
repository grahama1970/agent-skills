# Goal: Rolling Window Frame Extraction

## Primary Question

How should the watch pipeline split long videos into chunks, process each chunk independently, and merge results into a unified report?

## Goals

1. Automatically split videos exceeding the frame budget into N equal-duration chunks
2. Process each chunk independently: frame extraction, scene element building, memory upsert
3. Merge scene elements from all chunks into a single unified report
4. Tag each chunk's memory records with `chunk_index` and `total_chunks` for traceability
5. Handle chunk boundary overlap gracefully (no missing dialogue at seams)
6. Default: split at 5-minute intervals (300s) when estimated frame count exceeds budget

## Non-Goals

- Modifying the Whisper transcription pipeline (it already handles the full audio)
- Modifying the SRT auto-extraction (already full-length)
- Parallel processing of chunks (sequential is fine)
- Real-time or streaming processing
- Changing the scene detection algorithm

## Source-of-Truth Boundaries

| Concern | Owner |
|---------|-------|
| Frame extraction | `frames.py` |
| Scene element building | `report.py` > `build_scene_elements()` |
| Memory upsert | `storage.py` |
| Pipeline orchestration | `watch.py` > `run_watch()` |
| Divergence intelligence | `diff_intelligence.py` |

## Implemented vs Intended vs Missing

| Capability | Status |
|------------|--------|
| Frame extraction (single pass) | IMPLEMENTED |
| Scene elements from extracted frames | IMPLEMENTED |
| Memory upsert per scene | IMPLEMENTED |
| Frame budget calculation (auto_fps) | IMPLEMENTED |
| Rolling window: chunk splitting | MISSING |
| Rolling window: per-chunk processing | MISSING |
| Rolling window: result merging | MISSING |
| Rolling window: chunk metadata in DB | MISSING |

## Acceptance Gates

1. A 2-hour movie at default settings produces 600-1200 scene elements (vs current 500)
2. Scene elements are continuous across chunk boundaries (no gaps)
3. Each chunk's memory records include `chunk_index` and `total_chunks`
4. The unified report JSON has the same schema as a single-pass report
5. All existing tests pass unchanged
6. The Divergence Intelligence UI shows the merged result correctly

## Division of Labor

| Layer | Owns |
|-------|------|
| WebGPT (create-architecture) | Design the chunking algorithm, merge strategy, metadata schema, and acceptance tests |
| Project agent | Implement from the design, test, verify |

## Required Output

A solution zip containing:
1. `ARCHITECTURE.md` — chunking algorithm, merge strategy, chunk metadata schema
2. Modified `watch.py` with rolling window loop
3. Modified `report.py` for chunk-aware merging
4. Modified `storage.py` for chunk metadata
5. Tests for chunk boundary alignment and merge correctness
6. `prompt_improvements.md`
