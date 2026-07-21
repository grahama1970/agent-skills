# watch

![Watch card](../../docs/assets/project-cards/watch.webp)

Turn video into timecode-aligned evidence that agents can inspect, report on,
and later recall from memory.

`watch` accepts a YouTube URL, local video file, or resolvable movie title. It
extracts frames, transcript text, subtitle scene cues, audio notes, and structured
reports. The result is not just a summary: it is a set of timestamped artifacts
that can support later questions such as "what was on screen when the narrator
mentioned deployment?"

Agents must treat [`SKILL.md`](SKILL.md) as the runtime contract. This README is
the operator guide.

## What You Get

Every useful run should produce some combination of:

| Artifact | Purpose |
|---|---|
| `frames/` | JPEG scene markers or uniform samples |
| `frames_manifest.json` | Frame paths, timestamps, sampling mode, duration, and budget |
| `transcript.json` | Caption/SRT/Whisper transcript segments |
| `scenes.json` | Optional SRT emotion, tag, or query matches |
| `report.md` | Human-readable run report |
| `report.json` | Structured scene element table and run metadata |
| `report.html` | Inspectable table with thumbnails and local media controls when available |
| `/mnt/storage12tb/media/watch-frames/<slug>/` | Persistent frame/audio storage for memory-backed recall |

Start with `report.md`. It tells you what was actually processed before you ask
questions about the video.

## Quick Start

```bash
cd ${HOME}/workspace/experiments/agent-skills/skills/watch

# YouTube URL
./run.sh "https://youtube.com/watch?v=dQw4w9WgXcQ"

# Local file
./run.sh /path/to/video.mp4

# Focus a long recording on the part that matters
./run.sh /path/to/video.mp4 --start 2:15 --end 2:45

# Local movie with subtitles and emotion filtering
./run.sh /path/to/movie.mkv --subtitle /path/to/movie.srt --emotion rage

# Static screen recording or slide deck
./run.sh /path/to/recording.mp4 --fps 0.5
```

Use focused ranges for long videos whenever possible. A five-minute evidence
bundle is easier to verify than a two-hour archive.

## Source Routing

| Source | What watch does |
|---|---|
| YouTube URL | Uses `yt-dlp` for local media and composes `ingest-youtube` for captions before Whisper fallback |
| Local video | Processes directly with ffmpeg and optional SRT/SSA/ASS subtitles |
| Movie title | Checks local movie storage, then routes acquisition through `ingest-movie` only |
| Other URL | Downloads with `yt-dlp`, then falls back to local transcript and scene analysis paths |

Rules that matter:

- Topic discovery may use `brave-search`; acquisition of a specific movie belongs
  to `ingest-movie`.
- `watch` must not call Radarr, NZBGeek, or ad hoc acquisition APIs directly.
- Whisper is useful transcript evidence, but it does not replace the required
  English SRT column for movie canary/product runs.
- Public web facts can corroborate movie expectations; they cannot override
  extracted watch evidence.

## How The Pipeline Works

```text
source URL, file, or title
  -> local media path
  -> scene-change or uniform frame extraction
  -> transcript routing
       YouTube captions / local SRT / scillm Whisper fallback
  -> optional SRT emotion, tag, or query matching
  -> scene element table
  -> report.md, report.json, report.html, frames_manifest.json
  -> optional memory upsert for watch_content and persona_memory
```

For videos at least 10 minutes long, full-video scene-change extraction uses
rolling windows: 5-minute chunks with 3-second overlap, then merge and
deduplicate. Focused clips and explicit `--fps` runs do not use rolling windows.

## Choosing Frame Sampling

| Material | Best first choice | Why |
|---|---|---|
| Edited video or film | default scene-change mode | Captures cuts, dissolves, and visual transitions |
| Talk with slides | default scene-change mode | Slide changes usually create useful markers |
| Static screen recording | `--fps 0.5` or another uniform rate | There may be too few visual cuts |
| Short critical segment | `--start` and `--end` | Denser, cheaper, and easier to inspect |
| Fast action | raise `--max-frames` or focus the range | Important moments may be missed by a sparse budget |

Scene-change mode uses ffmpeg's scene filter and falls back to uniform sampling
when the video has too few detected changes.

## Common Commands

```bash
# Find scenes matching an emotion tag
./run.sh movie.mkv --subtitle movie.srt --emotion rage

# Search subtitle text
./run.sh movie.mkv --subtitle movie.srt --query "explosion"

# Match a cue tag
./run.sh movie.mkv --subtitle movie.srt --tag shout

# Keep artifacts in a predictable directory
./run.sh video.mp4 --out-dir /tmp/watch-demo

# JSON output for automation
./run.sh video.mp4 --json
```

Key options:

| Option | Use |
|---|---|
| `--start`, `--end` | Analyze a bounded time range |
| `--scene-change` | Use one frame per visual cut, bounded by frame budget |
| `--fps` | Force uniform sampling and disable scene-change mode |
| `--max-frames` | Cap extracted frames |
| `--resolution` | Set frame width |
| `--subtitle` | Provide local SRT/SSA/ASS subtitles |
| `--emotion`, `--tag`, `--query` | Filter subtitle scene evidence |
| `--whisper`, `--no-whisper` | Enable or skip Whisper fallback |
| `--out-dir` | Preserve work artifacts in a known path |

## Asking Questions Later

Questions about watched videos should go through `$memory` recall against
`watch_content`. Do not query ArangoDB or Qdrant directly.

```python
import httpx

client = httpx.Client(
    base_url="http://127.0.0.1:8601",
    timeout=httpx.Timeout(10.0, connect=2.0),
)
resp = client.post("/recall", json={
    "q": "What was on screen when the narrator mentioned deployment?",
    "collections": ["watch_content"],
    "k": 5,
})
items = resp.json()["items"]
```

Use natural-language questions and inspect `found`, `confidence`, `items`, and
source fields. If a question targets a specific video, reject wrong-video hits
even when recall returns `found=true`.

Appearance questions require frame-derived visual evidence. Transcript-only QRA
records do not prove what a person, object, or scene looked like. If no visual
record exists, report that the detail is not present in extracted visual evidence
and regenerate visual descriptions instead of guessing.

## YOLO Person Boxes For Watch Rows

The Watch annotation UI expects first-stage person boxes from YOLO/ByteTrack
before character identity work starts. Materialize detector boxes for every row
in the current report, not only the row currently open in the browser:

```bash
cd skills/watch
python3 scripts/materialize_yolo_bytetrack_for_report.py --report /tmp/watch-wex5uxs_/report.json
```

The materializer reads `report.json`, runs the existing
`track_yolo_bytetrack.py` adapter for each `scene_elements` clip, and writes
row-specific tracker logs under:

```text
skills/watch/docs/architecture/generated/watch_yolo_bytetrack_rows/
```

Rows with no detector events are written as explicit `NO_DETECTIONS` artifacts
so a missing box set is distinguishable from a row that was never processed.
Use a focused rerun while debugging one row:

```bash
python3 scripts/materialize_yolo_bytetrack_for_report.py --report /tmp/watch-wex5uxs_/report.json --rows 4 --force
```

After materialization, verify the UX server can see a row's detector candidates:

```bash
curl -sS "http://127.0.0.1:3002/api/projects/watch/detector-candidates?row_index=4&asset_uid=bad_santa_unrated_2003_brrip_xvidhd_720p_npw" \
  | jq '{row_index,total,source_log_count}'
```

## Setup

System dependencies:

```bash
ffmpeg
ffprobe
yt-dlp
tesseract   # only for PGS subtitle OCR
```

Python dependencies are managed by the skill environment. The quick manual
install path is:

```bash
cd skills/watch
uv pip install httpx rich loguru typer pillow
```

Docker services for Whisper and the Watch UI:

```bash
cd skills/watch/docker
docker compose --profile all up -d
docker exec watch-whisper whisper_manage --showkey
```

Whisper environment:

```bash
export WHISPER_API_URL="http://127.0.0.1:9000/v1/audio/transcriptions"
export WHISPER_API_KEY="$(docker exec watch-whisper whisper_manage --showkey | grep -m1 -oP 'whisper-[a-f0-9]+')"
```

Without Docker Whisper, local extraction still works, but transcript fallback may
be slower or weaker depending on available services.

## Watch UI

```bash
cd skills/watch/ui
npm install
npm run dev:all
```

Open `http://localhost:3002/#watch`.

The UI is an inspection surface for reports and scene rows. It is not proof by
itself; source artifacts, report JSON, frame paths, and memory recall remain the
evidence.

## YOLO Person Boxes And Character Identity

Watch can use YOLOAnalytics person boxes as the source regions for character
annotation. The intended loop is:

1. YOLOAnalytics supplies person boxes and stable track ids such as
   `track_2`.
2. A human accepts, rejects, or resets a character label on the YOLO box.
3. Watch crops accepted boxes, embeds them, and stores the identity evidence for
   Memory/Qdrant recall.
4. Future YOLO crops are queried against that evidence and rendered as tentative
   suggestions, for example `Marcus? 0.82`.
5. Suggestions stay tentative until accepted. Rejected or reset boxes are tracked
   separately and must not become training evidence.
6. If Qdrant recall finds a high-confidence different character on an accepted
   track, Watch must treat that as an identity handoff/stop requirement rather
   than blindly propagating the old label.

Current Bad Santa row 9 proof artifacts live under:

```text
docs/architecture/generated/watch_identity_qdrant_marcus_eval/20260705T155850Z_unfinished_goal_proof/
```

The current proof state is:

| Check | Current result |
|---|---|
| Marcus held-out identity recall | `11/12` correct |
| Marcus/Willie held-out recall | `22/24` correct |
| Tentative UI suggestion | Proven once with `Willie? 0.89` |
| Reset/reject path | Proven for one live browser path |
| Identity handoff stop | Proven for one live Qdrant conflict |
| Broad handoff-stop coverage | Still pending |

Use this feature for tentative auto-labeling, not silent auto-accept. The point
is to reduce human labeling work while keeping a fast accept/reject/reset path
for the wrong cases.

Immutable backend and live browser gates:

```bash
npm --prefix skills/watch/ui run test:backend-immutable
npm --prefix skills/watch/ui run test:memory-suggestion-live
npm --prefix skills/watch/ui run test:immutable-browser-live
npm --prefix skills/watch/ui run prove:immutable-goal
```

Proof screenshots must be committed under `skills/watch/proofs/immutable-goal/`
or uploaded as workflow artifacts. Proof manifests must use repo-relative paths
and SHA256 hashes; temporary paths are not durable proof.

## Orpheus Dataset Boundary

`watch` can find and curate movie-derived Orpheus evidence, but it does not own
synthetic SFX generation, LoRA training, or training promotion.

| Step | Owner |
|---|---|
| Search watched/local movie evidence | `watch` |
| Select exact movie clip windows | `watch` report/UI, when implemented |
| Report missing or sparse tags | `watch` |
| Generate synthetic gap-fill candidates | `voice-segment-selector` |
| Prompt review before paid/API generation | prompt-reviewer/skills-loop artifact |
| Train, evaluate, promote | `voice-segment-selector` and `unsloth-studio` |

Do not treat ElevenLabs samples as movie evidence. They are synthetic
`source_type=elevenlabs_sfx` gap-fill candidates.

## Real-Time Tracking Direction

Watch is evolving from single-video indexing into a multi-asset evidence stream
console. Movies are the controlled canary; later sources can include RTSP,
drone feeds, web videos, and telemetry-aligned operational footage.

The live tracking rule is:

```text
streamed tracking is provisional
bounded observations and evidence cases are stored to memory
```

Planned tracking lanes use YOLO/ByteTrack/OpenCV, optional re-identification
embeddings, domain reference packages, and `$memory` recall. Domain sources such
as Brave Search or movie databases are priors only. A character or object label
is supported only after frame/clip crops, transcript or scene corroboration,
reference receipts, negative controls, and memory recall evidence agree.

Architecture notes and canary fixtures live under `docs/architecture/`.

## Sanity

```bash
cd skills/watch
./sanity.sh
```

The sanity check verifies CLI and dependency loading. A passing sanity check is
not proof that a specific video was processed correctly; inspect the generated
report and artifacts for that.

## Troubleshooting

| Problem | Likely cause | What to do |
|---|---|---|
| `yt-dlp` cannot download | Site auth, format change, or blocked URL | Update `yt-dlp`, try a local file, or provide authenticated media another way |
| `ffmpeg` or `ffprobe` missing | System dependency not installed | Install and verify with `ffmpeg -version` and `ffprobe -version` |
| Too few useful frames | Wrong sampling mode for the material | Switch between scene-change and uniform sampling, or focus the range |
| Transcript is weak | Audio quality, overlap, noise, or missing model service | Check audio, use focused ranges, inspect `transcript.json` |
| Recall misses a moment | Moment not sampled, transcript missing, or memory upsert failed | Inspect `report.md`, then memory service/upsert logs |
| Visual descriptions missing | VLM/model service unavailable or skipped | Treat as a coverage gap; do not answer appearance questions from transcript |
| Persistent artifacts fail | Media root missing or unwritable | Check `/mnt/storage12tb/media/watch-frames` or configure/symlink storage |

## Credits

`watch` builds on scene-detection ideas from
[claude-watch](https://github.com/taoufik123-collab/claude-watch) by
taoufik123-collab. `ingest-youtube` and `ingest-movie` provide transcript and
SRT-analysis paths. Memory schema additions follow the SPARTA QRA document
pattern.
