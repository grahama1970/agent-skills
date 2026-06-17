# watch — Video Memory for Agents

<p align="center">
  <img
    src="docs/assets/watch-banner.jpg"
    alt="excited vintage robot labeled WATCH sitting on a couch and watching television in a colorful retro living room"
    width="100%"
  />
</p>

> Watch any video. Remember what happened. Ask about any moment later.

Agents need to understand video the way a person does: not just the words, but the
screen, the cuts, the timing, the mood, and the little visual details that never
show up in a transcript. A YouTube title is not enough. A caption file is not
enough. If the important clue is on a slide, in a screen recording, in a facial
expression, or in the soundtrack, a text-only agent will miss it.

That is what `/watch` is for. Give it a YouTube URL or a local video file and it
turns the video into searchable, timecode-aligned memory. It downloads or probes
the video, pulls key frames, transcribes speech, describes what is on screen,
summarizes the soundtrack, and stores the result in `watch_content` so
`/memory/recall` can find it later.

Use it for work like:

- "Watch this YouTube tutorial and tell me what the instructor's screen shows at 2:30."
- "Find the part of this lecture where they start explaining gradient descent."
- "Extract the scene changes from this movie and describe what each scene looks like."
- "Summarize this Zoom recording, but include the moments where the slides changed."
- "What is the soundtrack mood during the chase scene?"
- "Index this screen recording so another agent can ask about exact moments later."

```text
video URL or local file
    ↓
yt-dlp / local probe → ffmpeg frames → faster-whisper transcript
    ↓
text QRA pairs + scene image descriptions + soundtrack descriptions
    ↓
timecode-aligned artifacts saved under /mnt/storage12tb/media/watch-frames/<slug>/
    ↓
/upsert → watch_content → Qdrant text + image search
    ↓
/memory/recall can answer: "what happened at 3:12?"
```

**One core principle:** every modality points back to the same clock. Frames,
transcript segments, audio chunks, scene descriptions, and soundtrack notes all
reference seconds from the start of the video. That means an agent can ask
"what happens at 3:12?" and get the frame, dialogue, scene description, and audio
mood for that exact moment.

## Try this first

You do not need to understand the whole pipeline before using `watch`. Start with
the shape of the job: give it a video, choose how much visual detail you want, and
let it persist the result.

```bash
cd skills/watch

# Watch a YouTube video using captions/transcription plus 5 key frames
uv run python scripts/watch.py "https://youtu.be/iYG5tiFfK3E"

# Watch a local movie or screen recording with scene-change detection
uv run python scripts/watch.py movie.mkv --scene-change

# Watch only the useful part of a long video
uv run python scripts/watch.py movie.mkv --start 180 --end 600

# Full multimodal pass: transcript, scene frames, image descriptions, soundtrack notes
uv run python scripts/watch.py movie.mkv --scene-change
```

Agents should read `SKILL.md` before calling the skill programmatically. Humans
and operators can use this README for setup, mental model, and troubleshooting.

## What `watch` gives you

`watch` turns an opaque video file into artifacts an agent can inspect, cite, and
remember.

| You get | Why it matters |
| --- | --- |
| Timestamped transcript | Find what was said and when it was said. |
| Scene-change frames | See visual transitions, slides, screens, cuts, and camera changes. |
| Image descriptions | Search the visual content, not just spoken words. |
| Soundtrack descriptions | Capture mood, music, silence, effects, and audio texture. |
| QRA memory records | Store useful question/reasoning/answer summaries for recall. |
| Local artifacts | Keep frames, audio, reports, and metadata available for later review. |
| `/memory/recall` integration | Ask natural-language questions later and retrieve the relevant moments. |

The practical difference is simple: instead of asking an agent to "guess what is
in this video," you give it a real memory of the video.

## When to use it

| Situation | Reach for `watch` when you need... |
| --- | --- |
| YouTube tutorials | The spoken explanation plus what is visible on the instructor's screen. |
| Screen recordings | UI steps, cursor context, menus, dialogs, and timing. |
| Lectures and talks | Searchable explanations tied to slide changes and timestamps. |
| Meetings and Zoom calls | A transcript plus visual context from shared screens. |
| Films and clips | Scene boundaries, key frames, dialogue, and soundtrack mood. |
| Agent memory | A reusable video index that another agent can recall later. |

For very long videos, use `--start` and `--end` to focus the pass. The best
results come from videos under 10 minutes or from focused clips of longer videos.

## What happens under the hood

The pipeline is deliberately plain:

1. **Input** — accepts a YouTube URL or local file path.
2. **Download / probe** — uses `yt-dlp` for URLs and local probing for files.
3. **Frame extraction** — uses `ffmpeg` to detect scene changes or sample frames.
4. **Speech transcription** — uses `faster-whisper` to produce timestamped speech.
5. **Text enrichment** — creates question/reasoning/answer records for memory.
6. **Image enrichment** — describes key scene frames so visuals become searchable.
7. **Soundtrack enrichment** — describes mood, music, sound effects, and silence.
8. **Persistence** — saves artifacts locally and upserts searchable records into memory.

```text
skills/watch/
├── SKILL.md                 agent-facing contract
├── sanity.sh                test suite
└── scripts/
    ├── cli.py               Typer CLI (recommended entry point)
    ├── watch.py             core pipeline orchestration
    ├── download.py          yt-dlp download + local file probe
    ├── frames.py            ffmpeg scene-change + uniform frame extraction
    ├── transcribe.py        faster-whisper transcription + SRT parsing
    ├── qra.py               LLM-based QRA + image/audio description
    ├── storage.py           artifact persistence + memory upsert
    ├── scenes.py            SRT emotion/tag detection
    ├── report.py            JSON + markdown report generation
    └── recall_proof.py      end-to-end memory recall verification
```

The memory service adds `watch_content` and `watch_edges`, exposes a
`watch_content_search` view, and links the results into unified recall. Text and
image vectors are searched together so a question can match either spoken content
or visual evidence.

## Modalities

| Modality | Model / tool | What it produces | Status |
| --- | --- | --- | --- |
| Text transcripts | `faster-whisper` local | Timestamped transcript segments | ✅ |
| Text QRA pairs | `deepseek-v4-flash` | 3 question/reasoning/answer records per watch | ✅ |
| Scene images | `ffmpeg` scene detection | JPEGs at visual cuts or sampled intervals | ✅ |
| Image descriptions | `mimo-v2-omni` via Zen API | Two-sentence descriptions of 5 key frames | ✅ concurrent |
| Soundtrack descriptions | `gpt-5.5` through `scillm` | Mood, SFX, silence, and dialogue notes per scene chunk | ✅ concurrent |
| Audio embedding | Jina v5 Omni | 1024-dimensional vector in `image_mm` slot | ⏳ needs service rebuild |
| Memory recall | BM25 + Qdrant dense search | Text and image vectors retrieved together | ✅ |

## Timecodes are the product

The most important output is not the transcript, the frames, or the summary by
itself. The important output is the alignment between them.

A useful memory record can say:

```text
At 03:12:
- the transcript says the instructor is explaining the loss curve
- the frame shows a plotted graph on the screen
- the scene description mentions a code editor and terminal
- the soundtrack is quiet except for narration
```

That alignment is what lets an agent answer specific video questions instead of
returning a vague summary.

## Outputs and storage

Each run writes artifacts under:

```text
/mnt/storage12tb/media/watch-frames/<slug>/
```

A typical run can include:

```text
frames/                 extracted scene or sample frames
audio.wav               audio track used for transcription and soundtrack chunks
transcript.srt          timestamped transcript
watch_report.json       structured machine-readable report
watch_report.md         human-readable report
recall_proof.json       optional end-to-end recall verification
```

Each QRA pair is also stored as its own `watch_content` document:

```json
{
  "_key": "watch-<sha256>",
  "question": "what is this video about",
  "reasoning": "{source, duration, frame_count, ...}",
  "answer": "2-4 sentence summary",
  "title": "...",
  "frames": "[{path, timestamp_seconds}, ...]",
  "audio_path": "/mnt/storage12tb/.../audio.wav",
  "frame_dir": "/mnt/storage12tb/media/watch-frames/<slug>/",
  "scope": "watch_history",
  "tags": ["watch_history", "scene-change", "<slug>"]
}
```

## Scene detection

Scene-change detection uses `ffmpeg` with:

```text
select='gt(scene,0.3)'
```

If too few cuts are detected, or if the detected cuts cover too little of the
video, `watch` falls back to uniform sampling. This keeps the output useful even
for videos with long static shots, screen recordings, or slide decks.

## Limits

| Area | Current limit / behavior |
| --- | --- |
| Frames | Maximum 100 frames per watch, capped at 2 fps. |
| Transcript | `faster-whisper` base model. CPU is roughly 2x realtime; GPU is roughly 8x. |
| Image descriptions | 5 key frames, processed concurrently. |
| Soundtrack descriptions | 3 scene chunks, processed concurrently. |
| Best accuracy | Focused clips and videos under 10 minutes. |
| Audio embedding | Requires embedding service Docker rebuild for audio MIME support. |

## Dependencies

Python packages:

```bash
uv pip install httpx rich loguru typer pillow faster-whisper
# For PDF embedding (via skills/embedding):
uv pip install pypdfium2
```

System tools that must be on `PATH`:

```text
ffmpeg
ffprobe
yt-dlp
```

## Sanity check

Run the skill test suite before trusting a new setup:

```bash
cd skills/watch
./sanity.sh
```

The current suite contains 17 tests.

## Troubleshooting

**The video has almost no frames**

Use `--scene-change` for visually active videos. For slide decks, screen
recordings, or static camera footage, allow the uniform sampling fallback to do
its job.

**The answer misses something visible on screen**

Make sure the relevant moment is inside the watched range. For long files, rerun
with a tighter `--start` / `--end` window around the section you care about.

**The transcript is weak**

Check audio quality first. Background noise, music over speech, and quiet speakers
will reduce transcription quality. A focused clip often works better than a full
long recording.

**Recall cannot find the watched moment**

Run `scripts/recall_proof.py` to verify that artifacts were written, records were
upserted, and `watch_content` is visible to `/memory/recall`.

## Credits

`/watch` builds on scene-detection techniques from
[claude-watch](https://github.com/taoufik123-collab/claude-watch) by
taoufik123-collab. The ingest-youtube and ingest-movie skills provide transcript
and SRT analysis. Memory schema additions follow the SPARTA QRA document pattern.

## The short version

`watch` makes videos usable by agents.

It does not just summarize a file. It builds a timecode-aligned memory of what was
said, what was shown, what changed, and what the audio felt like — then stores
that memory so an agent can ask about the video later.
