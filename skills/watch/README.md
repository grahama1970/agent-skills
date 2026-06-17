# watch — Multimodal Video Analysis for Agents

<p align="center">
  <img
    src="docs/assets/watch-banner.jpg"
    alt="watch skill banner showing a Blade Runner Black Out 2022 scene — replicant identification file on a glowing digital monitor"
    width="100%"
  />
</p>

Agents need to watch videos: YouTube URLs, local movie files, screen recordings,
Zoom calls. Until now, an agent given a video URL could only guess from the title
or read a text transcript with no visual context — missing scene changes, on-screen
text, character expressions, lighting, and soundtrack.

That is what `watch` is for. One entrypoint feeds a video URL or local path through
yt-dlp, ffmpeg scene-change detection, automatic speech recognition, and multimodal
LLM enrichment — producing timecode-aligned text, image, and audio descriptions
stored in `watch_content` for `/memory/recall`.

Use it for work like:

- "Watch this YouTube tutorial and tell me what the instructor's screen shows at 2:30."
- "Extract scene-change frames from this movie and describe what each scene looks like."
- "Find the part of this lecture where they discuss gradient descent."
- "What is the soundtrack mood during the chase scene in Blade Runner?"

```text
input: URL or local file
    ↓
yt-dlp download → ffmpeg scene-change frames → faster-whisper transcript
    ↓
deepseek-v4-flash → 3 QRA pairs (question/reasoning/answer)
mimo-v2-omni     → scene image descriptions (5 key frames)
gpt-5.5          → soundtrack descriptions (per scene chunk)
    ↓
all artifacts persisted to /mnt/storage12tb/media/watch-frames/<slug>/
    ↓
httpx POST /upsert → watch_content collection → Qdrant (text_mm + image_mm)
    ↓
/memory/recall finds everything by BM25 + dense vector search
```

**One core principle:** every modality is timecode-aligned. Every frame, transcript
segment, audio clip, and description references seconds from video start. Any agent
can ask "what happens at 3:12?" and get the frame, the dialogue, the scene description,
and the soundtrack mood — all pointing to the same moment.

## Architecture

```
agents/watch/              ← subagent transport wrapper (AGENTS.md + persona.yaml)
skills/watch/              ← skill implementation (watch.py, frames.py, transcribe.py)
  scripts/
    watch.py               ← main entry point (CLI)
    frames.py              ← ffmpeg scene-change + uniform frame extraction
    download.py            ← yt-dlp download (URLs) + local file probe
    transcribe.py          ← faster-whisper local transcription + SRT parsing
    scenes.py              ← SRT emotion/tag detection (from ingest-movie)
    report.py              ← structured JSON + markdown report generation
    recall_proof.py        ← e2e memory recall verification
  SKILL.md                 ← skill contract
  sanity.sh                ← 17 tests, 17 pass

memory service (modified):
  _schema_collections.py   ← watch_content + watch_edges collections
  _schema_views.py         ← watch_content_search view + unified_search link
  _declarations.py         ← watch_content RecallSource
  recall.py                ← question/reasoning/answer/frames in KEEP
  qdrant_recall.py         ← text_mm + image_mm query in dense scorer
  semantic_sync.py         ← image + audio embedding from frames/audio_path
```

## Try this first

```bash
# Watch a YouTube video (free captions, 5 frames)
uv run python scripts/watch.py "https://youtu.be/iYG5tiFfK3E"

# Watch with scene-change detection
uv run python scripts/watch.py movie.mkv --scene-change

# Watch a focused section
uv run python scripts/watch.py movie.mkv --start 180 --end 600

# All modalities: text QRA + scene images + soundtrack
uv run python scripts/watch.py movie.mkv --scene-change
```

## Modalities

| Modality | Model | What it produces | Status |
|----------|-------|-----------------|--------|
| **Text transcripts** | faster-whisper (local) | Timestamped transcript segments | ✅ |
| **Text QRA pairs** | deepseek-v4-flash | 3 question/reasoning/answer per watch | ✅ |
| **Scene images** | ffmpeg scene detection | JPEGs at each visual cut | ✅ |
| **Image descriptions** | mimo-v2-omni (Zen API) | 2-sentence descriptions of 5 key frames | ✅ concurrent |
| **Soundtrack descriptions** | gpt-5.5 (scillm) | Mood/SFX/dialogue per scene chunk | ✅ concurrent |
| **Audio embedding** | Jina v5 Omni | 1024d vector in image_mm slot | ⏳ needs service rebuild |
| **Memory recall** | BM25 + Qdrant dense | Text + image vectors searched | ✅ |

## Dependencies

```bash
uv pip install httpx rich faster-whisper
pip install pypdfium2 pillow  # for PDF embedding (via skills/embedding)
```

System: `ffmpeg`, `ffprobe`, `yt-dlp` (must be on PATH).

## Memory Schema

The `watch_content` collection stores each QRA pair as a separate document:

```
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

## Scene Markers

Scene-change detection via ffmpeg `select='gt(scene,0.3)'`. Falls back to uniform
sampling when <10 cuts detected or when detected cuts cover <10% of video duration.

## Limits

- **Frames:** max 100 per watch, 2 fps cap
- **Transcript:** faster-whisper base model (CPU ~2x realtime, GPU ~8x)
- **Image descriptions:** 5 key frames via mimo-v2-omni (concurrent, ~10s total)
- **Soundtrack:** 3 scene chunks via GPT-5.5 through scillm (concurrent, ~13s total)
- **Best accuracy:** videos under 10 minutes
- **Audio embedding:** needs embedding service Docker rebuild for audio MIME support

## Credits

`/watch` builds on scene-detection techniques from [claude-watch](https://github.com/taoufik123-collab/claude-watch)
by taoufik123-collab. The ingest-youtube and ingest-movie skills provide transcript
and SRT analysis. Memory schema additions follow the SPARTA QRA document pattern.
