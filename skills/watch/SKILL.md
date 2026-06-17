---
name: watch
description: >
  Watch any video (URL or local file) with scene-change frame extraction,
  transcript extraction (native captions or Whisper via scillm), SRT-based
  emotion/scene analysis, and structured reports. Merges capabilities from
  ingest-youtube (transcripts) and ingest-movie (scene/emotion analysis) with
  ffmpeg scene-change detection.
allowed-tools: Bash, Read
triggers:
  - watch video
  - extract frames
  - get video transcript
  - scene detection
  - analyze video
  - what happens in this video
  - watch this url
  - extract scenes from video
metadata:
  short-description: Video analysis with scene-change frames, transcripts, and SRT emotion detection
  requires:
    bins:
      - uv
      - ffmpeg
      - yt-dlp

provides:
  - watch
composes:
  - memory
  - brave-search          # Topic discovery: find what movie to watch
  - ingest-youtube
  - ingest-movie          # Acquisition + SRT scene analysis (owns search, Radarr, subtitle quality)
  - scillm
  - task-monitor
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-agent
  - best-practices-scillm
---

> STOP. READ THIS ENTIRE SKILL.MD BEFORE CALLING ANY ENDPOINT.

# Watch Skill

Watch any video (URL or local file) and get:
1. **Scene-change frames** — one JPEG per detected shot via ffmpeg `select=gt(scene,…)`
2. **Transcript** — native captions first, then Whisper via scillm
3. **SRT emotion/scene analysis** — for local files with subtitles
4. **Structured report** — frames manifest + transcript + pacing metrics

## Quick Start

```bash
cd /home/graham/workspace/experiments/agent-skills/skills/watch

# Watch a YouTube URL → auto-routes transcript to ingest-youtube (3-tier fallback)
uv run python scripts/watch.py "https://youtube.com/watch?v=dQw4w9WgXcQ"

# Watch a local movie with SRT → auto-routes emotion analysis to ingest-movie
uv run python scripts/watch.py /path/to/video.mp4 --subtitle /path/to/subtitles.srt --emotion rage

# Watch a local file, scene-change frames only
uv run python scripts/watch.py /path/to/video.mp4 --scene-change

# Focus on a specific section (denser frames, lower token cost)
uv run python scripts/watch.py video.mp4 --start 2:15 --end 2:45

# Uniform frame sampling (skip scene-change detection)
uv run python scripts/watch.py video.mp4 --fps 0.5
```

## Source Resolution

```
watch "https://youtube.com/watch?v=..."   → YouTube: ingest-youtube + yt-dlp frames
watch /path/to/video.mp4                  → Local file: direct processing
watch "There Will Be Blood"              → Movie title: disk → ingest-movie search → ingest-movie Radarr
```

**Movie resolution and acquisition:**

| Step | Task | Tool | Command |
|------|------|------|---------|
| 1 | **What to watch?** — discover movies about a topic | `brave-search` | `./run.sh web "revenge movies 2000s"` |
| 2 | **Is it on disk?** — check local library | watch built-in | Fuzzy match in `/mnt/storage12tb/media/movies/` |
| 3 | **Find a release** — search Usenet with subtitle checks | `ingest-movie` search | `./run.sh search "Bad Santa 2003"` |
| 4 | **Acquire** — download with quality enforcement | `ingest-movie` Radarr | `./run.sh acquire radarr --preset horus_standard --execute` |
| 5 | **Failure** — can't find or acquire | agent reports to user | Exit code 1 + context |

Rules:
- **Topic discovery** → `brave-search` (find *what* to watch)
- **Acquisition** → `ingest-movie` ONLY (find + download *a specific title*)
- Do NOT call ops-nzbgeek, Radarr API, or brave-search for acquisition —
  `ingest-movie` owns all of that and enforces subtitle quality.

## Composition Routing

`watch` automatically routes sub-tasks to the best existing skill:

| Source type | Transcript | Scene/emotion analysis | Download/acquisition |
|-------------|-----------|----------------------|---------------------|
| **YouTube URL** | `ingest-youtube` (captions via `--no-whisper`, then scillm Whisper on video) | Not applicable | `yt-dlp` for frames |
| **Local file with SRT** | Direct SRT parse or scillm Whisper | `ingest-movie` scenes analyze/find | N/A (local) |
| **Movie title** (name not found in library) | Direct SRT parse or scillm Whisper | `ingest-movie` scenes analyze/find | `ingest-movie` Radarr (SDH subs + English audio + 1080p enforced) |
| **Other URL / no SRT** | scillm Whisper fallback | Built-in SRT parser (fallback) | `yt-dlp` download |

## Pipeline

```
Source (URL or local)
  │
  ├─ yt-dlp download ──→ local video file (for frames)
  │
  ├─ ffmpeg scene-change or uniform frame extraction ──→ JPEG frames
  │
  ├─ Transcript routing:
  │   ├─ YouTube URL ──→ compose with ingest-youtube (uv subprocess, stdout JSON)
  │   ├─ Local SRT file ──→ parse directly (SSA/ASS/SRT)
  │   └─ Fallback ──→ scillm Whisper (httpx to localhost:4001, not raw API key)
  │
  ├─ SRT scene analysis routing:
  │   ├─ Local movie with SRT ──→ compose with ingest-movie (uv subprocess, temp JSON)
  │   └─ Fallback ──→ built-in scenes.py (adapted from ingest-movie)
  │
  └─ Structured report: frames_manifest.json + transcript.json + scenes.json + report.md
```

## Commands

### `watch.py` — Main entry point

```bash
uv run python scripts/watch.py <source> [options]
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `source` | Video URL (anything yt-dlp supports) or local file path |

**Options:**
| Option | Default | Description |
|--------|---------|-------------|
| `--scene-change` | `True` | Use ffmpeg scene-change detection (one frame per shot) |
| `--fps` | auto | Override frame rate (disables scene-change if set) |
| `--max-frames` | `100` | Maximum frames to extract |
| `--resolution` | `512` | Frame width in pixels |
| `--start` | — | Start time (SS, MM:SS, or HH:MM:SS) |
| `--end` | — | End time (SS, MM:SS, or HH:MM:SS) |
| `--subtitle` | — | Path to SRT subtitle file for local analysis |
| `--emotion` | — | Emotion tag for scene filtering (rage, anger, etc.) |
| `--tag` | — | SRT cue tag for scene filtering |
| `--query` | — | Free-text search in SRT |
| `--whisper` | `True` | Enable Whisper fallback via scillm |
| `--no-whisper` | — | Skip Whisper fallback |
| `--out-dir` | tmp | Working directory |
| `--json` | — | Output JSON instead of markdown |

### Scene analysis (SRT-based)

```bash
# Find scenes matching an emotion tag
uv run python scripts/watch.py movie.mkv --subtitle movie.srt --emotion rage

# Find scenes matching a text query
uv run python scripts/watch.py movie.mkv --subtitle movie.srt --query "explosion"

# Find scenes matching a cue tag
uv run python scripts/watch.py movie.mkv --subtitle movie.srt --tag shout
```

### Focused analysis (denser frames)

```bash
# Dense frames over a 30-second window
uv run python scripts/watch.py video.mp4 --start 1:30 --end 2:00

# Last 10 seconds
uv run python scripts/watch.py video.mp4 --start 50 --end 60
```

## Output

### Frames manifest (`frames_manifest.json`)

```json
{
  "source": "https://youtube.com/watch?v=...",
  "sampling_mode": "scene-change",
  "frame_count": 24,
  "fps": null,
  "max_frames": 100,
  "resolution": 512,
  "duration_seconds": 300.0,
  "frames": [
    {
      "index": 0,
      "timestamp_seconds": 0.0,
      "path": "/tmp/watch-xxx/frames/frame_0000.jpg"
    }
  ]
}
```

### Transcript (`transcript.json`)

```json
{
  "source": "captions",
  "segments": [
    {"text": "Hello world", "start": 0.0, "duration": 2.5}
  ],
  "full_text": "Hello world..."
}
```

### SRT scene analysis (`scenes.json`, when SRT provided)

```json
{
  "emotion": "rage",
  "tag": null,
  "matches": [
    {
      "start": 120.0,
      "end": 125.0,
      "text": "I WILL DESTROY YOU",
      "tags": ["shout", "rage"],
      "match_type": "emotion"
    }
  ]
}
```

## Frame Budget (Auto-Scaled)

| Duration | Uniform Mode | Focused Mode |
|----------|-------------|--------------|
| ≤30s | ~30 frames | ~60 frames |
| 30s-1min | ~40 frames | ~80 frames |
| 1-3min | ~60 frames | ~100 frames |
| 3-10min | ~80 frames | ~100 frames |
| >10min | 100 frames (sparse) | 100 frames |

Scene-change mode yields one frame per detected shot, bounded by `--max-frames`.

## Scene-Change Detection

Uses ffmpeg's `select='gt(scene,0.3)'` filter — one frame per detected visual
cut. Falls back to uniform sampling if <10 scene changes detected (static or
talking-head videos). Scene-change thresholds in [0,1]; 0.3 is permissive enough
to catch hard cuts and dissolves without firing on motion.

To force uniform sampling: `--fps <rate>` (disables scene-change).

## SRT Emotion Analysis

Reuses the emotion cue system from `ingest-movie`:
- **Tags**: rage, shout, laugh, anger_candidate, rage_candidate, whisper_candidate
- **Emotions**: rage, anger, sorrow, regret, camaraderie
- **Detection**: subtitle text parsing for [bracketed], (parenthesized), ALL-CAPS cues
- **Quality validation**: entry count, emotion cue presence, timing consistency

## Dependencies

```bash
uv pip install httpx rich
```

System: `ffmpeg`, `yt-dlp` (both must be on PATH)

## Composing with Other Skills

For **YouTube transcript-only** extraction (no frames), use `ingest-youtube`:
```bash
cd ../ingest-youtube
uv run python youtube_transcript.py get -u "https://youtube.com/watch?v=..."
```

For **bulk movie emotion extraction** (training data pipelines), use `ingest-movie`:
```bash
cd ../ingest-movie
./run.sh scenes extract --subtitle file.srt --tag rage --video movie.mkv
```

For **Whisper transcription**, use scillm:
```python
import httpx
resp = httpx.post("http://localhost:4001/v1/audio/transcriptions", ...)
```

## Sanity

```bash
./sanity.sh   # Verifies CLI + dependencies load
```
