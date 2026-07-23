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
  - voice-segment-selector # Orpheus candidate review/export and synthetic SFX gap-fill
  - unsloth-studio       # downstream train/eval loop ownership
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
4. **Scene element table** — timecode, transcript text, marker image, movie segment, and sound note per sampled scene
5. **HTML inspection table** — thumbnails, visual description status, playable video/audio controls where local paths are available
6. **Structured report** — frames manifest + transcript + pacing metrics

Planned diarization is a separate audio evidence lane, not a visual watcher and
not a character-identification model. See "Diarization Contract" below.

## Quick Start

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/watch

# Watch a YouTube URL → auto-routes transcript to ingest-youtube (3-tier fallback)
./run.sh "https://youtube.com/watch?v=dQw4w9WgXcQ"

# Watch a local movie with SRT → auto-routes emotion analysis to ingest-movie
./run.sh /path/to/video.mp4 --subtitle /path/to/subtitles.srt --emotion rage

# Watch a local file, scene-change frames only
./run.sh /path/to/video.mp4 --scene-change

# Focus on a specific section (denser frames, lower token cost)
./run.sh video.mp4 --start 2:15 --end 2:45

# Uniform frame sampling (skip scene-change detection)
./run.sh video.mp4 --fps 0.5
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
| 5 | **Subtitle recovery** — ensure English SRT exists beside media | Bazarr | `http://localhost:6767` connected to Radarr/Sonarr |
| 6 | **Failure** — can't find, acquire, or obtain English SRT | agent reports to user | Exit code 1 + context |

Rules:
- **Topic discovery** → `brave-search` (find *what* to watch)
- **Acquisition** → `ingest-movie` ONLY (find + download *a specific title*)
- **Post-import subtitles** → Bazarr connected to Radarr/Sonarr; expected output is
  an English `.srt` alongside the movie file
- Do NOT call ops-nzbgeek, Radarr API, or brave-search for acquisition —
  `ingest-movie` owns all of that and enforces subtitle quality.
- Do NOT treat Whisper as a replacement for the required English SRT column.

## Composition Routing

`watch` automatically routes sub-tasks to the best existing skill:

| Source type | Transcript | Scene/emotion analysis | Download/acquisition |
|-------------|-----------|----------------------|---------------------|
| **YouTube URL** | `ingest-youtube` (captions via `--no-whisper`, then scillm Whisper on video) | Not applicable | `yt-dlp` for frames |
| **Local file with SRT** | English SRT plus separate scillm Whisper | `ingest-movie` scenes analyze/find | N/A (local) |
| **Movie title** (name not found in library) | English SRT plus separate scillm Whisper | `ingest-movie` scenes analyze/find | `ingest-movie` Radarr + Bazarr English SRT recovery |
| **Other URL / no SRT** | scillm Whisper fallback | Built-in SRT parser (fallback) | `yt-dlp` download |

## Pipeline

```
Source (URL or local)
  │
  ├─ yt-dlp download ──→ local video file (for frames)
  │
  ├─ Rolling window planner (≥10min videos only)
  │   ├─ Split into 5-min chunks with 3s boundary overlap
  │   ├─ Extract frames per chunk via scene-change detection
  │   ├─ Merge and deduplicate (0.5s tolerance)
  │   └─ Global reindex → single flat frame list
  │
  ├─ ffmpeg scene-change or uniform frame extraction ──→ JPEG frames
  │   (single-pass for short/focused videos, chunked for long videos)
  │
  ├─ Transcript routing:
  │   ├─ YouTube URL ──→ compose with ingest-youtube (uv subprocess, stdout JSON)
  │   ├─ Local English SRT file ──→ parse directly (SSA/ASS/SRT)
  │   └─ Fallback ──→ scillm Whisper (httpx to localhost:4001, not raw API key)
  │      Note: Whisper is a separate transcript stream; it does not satisfy
  │      the English SRT requirement for movie canary/product runs.
  │
  ├─ SRT scene analysis routing:
  │   ├─ Local movie with SRT ──→ compose with ingest-movie (uv subprocess, temp JSON)
  │   └─ Fallback ──→ built-in scenes.py (adapted from ingest-movie)
  │
  └─ Structured report: frames_manifest.json + transcript.json + scenes.json + report.md
```

## Asking Questions About Watched Videos

Questions about previously watched videos must go through `$memory` recall, not
direct ArangoDB or Qdrant queries. The Watch subagent may answer movie questions
like a human viewer when the answer is supported by watched-video evidence
(`watch_content`, frames, transcript, scene table, or scene metadata).

```python
import httpx

client = httpx.Client(base_url="http://127.0.0.1:8601", timeout=httpx.Timeout(10.0, connect=2.0))
resp = client.post("/recall", json={
    "q": "What was on screen when the narrator mentioned deployment?",
    "collections": ["watch_content"],
    "k": 5,
})
data = resp.json()
items = data["items"]  # not "results"
```

Use natural-language questions, inspect `found`, `confidence`, `items`, and
source fields, and ask a clarifying question when recall is weak or ambiguous.
Do not answer video facts from memory when `watch_content` recall misses.
When the question targets a specific video, pass a media title/key/slug and
reject wrong-video hits even when `/recall` returns `found=true`.

Appearance questions require frame-derived visual evidence records. Transcript
QRA records are not sufficient to answer what a character, object, or scene
looked like. If no frame/VLM description exists, answer `not present in
extracted visual evidence` and regenerate visual descriptions instead of
guessing.

For public movie facts or expected-answer sanity checks, Watch may use
`$brave-search` to corroborate the likely answer:

```python
from video_memory import ask_movie_question

packet = ask_movie_question(
    "why does the character leave the apartment?",
    movie_title="Example Film",
)
```

Treat Brave Search as corroboration only. It must not override the watched
video evidence, and it must not be used as the only source for scene-specific
claims about what appeared in the watched video.

The answer contract is:

```text
extracted watch evidence first -> Brave corroboration second
```

If Brave finds a fact that extraction does not, that is a coverage gap, not an
answer.

## Diarization Contract

Status: `CONTRACT_DEFINED_NOT_IMPLEMENTED`.

Watch should use pyannote when the task includes determining who spoke when.
The contract is defined, but the runtime service and pipeline integration are
not implemented in this skill yet.

Evidence layers remain separate:

```text
SRT/captions = subtitle, script, and cue evidence
Whisper      = acoustic text evidence
pyannote     = anonymous who-spoke-when evidence
YOLO/tracks  = visual person observations
human review = accepted identity decision
```

The durable schemas are:

```text
docs/architecture/schemas/watch_diarization.schema.json
docs/architecture/schemas/watch_speaker_attribution.schema.json
```

The contract constants live in:

```text
scripts/diarization_contract.py
```

Boundary rules:

- `SPEAKER_00`, `SPEAKER_01`, and similar labels are anonymous acoustic
  clusters, stable only within one diarization artifact.
- Anonymous speaker labels are not actor, character, narrator, or real-world
  identity.
- Speaker-to-character mappings must remain candidate evidence until accepted
  through the existing Watch identity ledger.
- Pyannote must not mutate SRT text, Whisper text, YOLO receipts, accepted
  labels, or Memory identity state.
- Focused runs must persist source-timeline speaker timestamps, not
  clip-relative timestamps.
- Missing diarization must produce a structured receipt when diarization is
  attempted; auto mode may continue without speaker attribution.

Runtime support is implemented through the local pyannote Community-1 service
and the Watch CLI. The live immutable gate exercises real media, the Dockerized
CUDA pyannote service, Watch report generation, and anonymous speaker evidence.

Available CLI options:

```text
--diarization auto|pyannote|none
--num-speakers INTEGER
--min-speakers INTEGER
--max-speakers INTEGER
--require-diarization
```

Do not claim pyannote support from mocked tests alone. Runtime support requires
the live pyannote gate and its proof artifacts under the immutable goal proof
directory.

## Immutable YOLO Identity Ledger Contract

- Detector `track_id` values are observations, not identity truth.
- Watch owns accepted identity segments over detector observations.
- Memory/Qdrant suggestions are tentative and must render as suggestions until a human accepts them.
- Human accept is required before a character label is accepted identity.
- `reject_box` or `reset_box` closes the current segment for that detector track.
- No identity can propagate across a closed segment.
- Reassignment after a stop creates a new segment, even when the detector `track_id` is unchanged.
- Local YOLO label receipts persist before Memory sync is attempted.
- Failed Memory sync remains durable and retryable; it must not exist only in a transient HTTP response.
- Held/interpolated runtime boxes are UI state, not canonical identity evidence.

Required immutable-gate commands:

```bash
npm --prefix skills/watch/ui test
npm --prefix skills/watch/ui run typecheck
npm --prefix skills/watch/ui run build
npm --prefix skills/watch/ui run test:memory-suggestion-live
npm --prefix skills/watch/ui run test:immutable-browser-live
npm --prefix skills/watch/ui run test:pyannote-immutable-live
npm --prefix skills/watch/ui run prove:immutable-goal
```

`sanity.sh` does not replace the live immutable goal gate.

## Commands

### `run.sh` — Main Typer entry point

```bash
./run.sh <source> [options]
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
./run.sh movie.mkv --subtitle movie.srt --emotion rage

# Find scenes matching a text query
./run.sh movie.mkv --subtitle movie.srt --query "explosion"

# Find scenes matching a cue tag
./run.sh movie.mkv --subtitle movie.srt --tag shout
```

### Focused analysis (denser frames)

```bash
# Dense frames over a 30-second window
./run.sh video.mp4 --start 1:30 --end 2:00

# Last 10 seconds
./run.sh video.mp4 --start 50 --end 60
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

### Scene element table (`report.md` and `report.json`)

Every report includes a scene-by-scene table with:

| Field | Description |
|-------|-------------|
| `timecode` | Timestamp for the sampled scene marker |
| `text` | Transcript text overlapping the scene segment, or an explicit missing-transcript note |
| `scene_marker_image` | Extracted frame path for visual inspection |
| `visual_description` | VLM-derived description or `not_analyzed` |
| `visual_description_source` | Model/source receipt, or `none` |
| `visual_description_status` | `described` or `not_analyzed` |
| `movie_segment` | Start/end time range represented by the row |
| `sound` | Speech/source note or explicit unavailable/not-analyzed note |

### HTML report (`report.html`)

Every run writes `report.html` beside `report.md` and `report.json`. It renders
the same scene rows with:

- image thumbnails from actual frame paths
- visual description status and source
- local video media fragments for scene playback when the source is a local file
- audio controls when an extracted audio artifact exists
- explicit gaps such as `image_descriptions_missing`

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

## Orpheus Emotion Dataset Boundary

Watch helps find and curate movie-derived Orpheus evidence, but it does not own
synthetic SFX generation, LoRA training, or training self-improvement loops.

**Source-derived step model:**

1. **Search watched/local movie evidence** — `watch` parses SRT/Whisper/scene
   rows and finds candidate spans for Orpheus-native tags.
   - Status: implemented/intended in Watch.
2. **Create movie-curated candidates** — Watch report/UX selects exact audio
   windows and writes provenance as `source_type=movie_curated`.
   - Status: intended; movie clips are preferred for authenticity.
3. **Report missing/sparse tags** — Watch identifies tags with insufficient
   movie evidence.
   - Status: intended; the report should name missing tags directly.
4. **Generate synthetic gap-fill candidates** — delegate to
   `voice-segment-selector generate-orpheus-sfx`, not Watch.
   - Status: implemented in `voice-segment-selector`.
5. **Prompt review loop** — generated ElevenLabs prompts must be sent through a
   prompt-reviewer/skills-loop artifact before API generation.
   - Status: implemented as a prompt-review bundle emitted by Unsloth Studio;
     external reviewer/subagent consumes the bundle.
6. **Train/evaluate/promote** — owned by `voice-segment-selector` and, where
   Studio API training loops are used, `unsloth-studio`; not Watch.
   - Status: outside Watch scope.

Handoff command:

```bash
cd ${HOME}/workspace/experiments/agent-skills
skills/voice-segment-selector/run.sh generate-orpheus-sfx \
  --speaker embry \
  --samples-per-tag 40 \
  --job-dir /mnt/storage12tb/skills/voice-segment-selector/jobs/embry-lawson-orpheus-elevenlabs-sfx
```

Use `--dry-run` first to create only the prompt-review bundle and planned
manifest. Do not treat ElevenLabs samples as movie evidence; they are
`source_type=elevenlabs_sfx` synthetic gap-fill candidates.

## Rolling Window Extraction

Videos ≥10 minutes (full-video, scene-change mode only) are automatically split
into 5-minute chunks with 3s boundary overlap. Each chunk is processed
independently for frame extraction, then frames are merged and deduplicated
into a single global timeline.

- Triggered when: `effective_duration > 600s`, `not focused`, `fps is None`,
  `scene_change is True`
- Chunk size: 300s (configurable via `ROLLING_WINDOW_SECONDS`)
- Overlap: 3s (configurable via `ROLLING_WINDOW_OVERLAP_SECONDS`)
- Dedup tolerance: 0.5s
- Scene rows include: `chunk_index`, `total_chunks`, `chunk_start_seconds`,
  `chunk_end_seconds`

## Configuration

All environment variables are centralized in `scripts/config.py`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `WHISPER_API_URL` | `http://127.0.0.1:9000/v1/audio/transcriptions` | Docker Whisper endpoint |
| `WHISPER_API_KEY` | `""` | API key for Docker Whisper |
| `MEMORY_DAEMON_URL` | `http://127.0.0.1:8601` | Memory service for upsert/recall |
| `WATCH_MEDIA_ROOT` | `~/.local/share/agent-skills/watch-frames` | Persistent frame/audio storage |
| `WATCH_REPORT_PATH` | `""` | Default report path for the UI |

## PGS Subtitle OCR

BluRay PGS (image-based) subtitles are OCR'd via a batch approach:
1. `ffprobe` extracts subtitle event PTS values
2. `ffmpeg` overlay renders each subtitle on a scaled video frame
3. `tesseract` OCRs each frame (ThreadPoolExecutor with 4 workers)
4. Produces an SRT file with timing from the PTS metadata

Capped at 500 events (same as the single-pass frame budget). Falls back to
Whisper-only if OCR fails.

## Dependencies

```bash
uv pip install httpx rich loguru typer pillow
```

System: `ffmpeg`, `ffprobe`, `yt-dlp`, `tesseract` (for PGS OCR)

The CLI validates system deps at startup: missing `ffmpeg`, `ffprobe`, or
`yt-dlp` produces a clear error before any pipeline work begins.

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
