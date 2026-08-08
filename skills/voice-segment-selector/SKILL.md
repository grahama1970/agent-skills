---
name: voice-segment-selector
description: >
  Select clean male/female speech segments from audio or video for voice-cloning
  and TTS datasets. Use when a project agent needs ranked voice clips with
  transcripts, gender buckets, human review, export to metadata.jsonl, or a best
  30-second male/female reference WAV. Normalizes input, splits 6-18s clips,
  scores quality, classifies vocal characteristics, transcribes each clip.
triggers:
  - voice segment selector
  - /voice-segment-selector
  - voice clone prep
  - gender voice segments
  - best 30 second female clip
  - best 30 second male clip
  - tts dataset prep
  - select voice clips
provides:
  - voice-segment-selection
  - tts-dataset-prep
composes:
  - extract-audiobook
  - ingest-youtube
  - tts-train
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - extraction
  - validation
  - audio
disciplines:
  - voice-audio
  - data-engineering
---

# voice-segment-selector

Prepare **ranked, gender-bucketed, transcript-backed** voice clips from audio or video for `/tts-train`.

This skill is **not** speaker diarization. Gender labels are **vocal characteristic guesses**, not identity. Human review is recommended before training export.

## Agent playbook (read this first)

Project agents should follow this exact sequence:

1. **Acquire source media** (if needed)
   - Local file: use path directly
   - YouTube URL: run `/ingest-youtube` first, or download audio yourself
   - Long audiobook: get `ffprobe_chapters.json` from `/extract-audiobook` first
2. **Prepare job** with an explicit `--job-dir` (do not rely on memory of `/tmp` names)
3. **Review** top candidates with the human (`review` API or `decide`)
4. **Export** accepted clips to `metadata.jsonl`
5. **Optional:** build one `--target-sec 30` bundle WAV
6. **Hand off** exported dataset path to `/tts-train`

Always capture and report these paths back to the human:

- `job_dir`
- `candidates.jsonl`
- `voice-dataset/metadata.jsonl`
- optional `female_best_30s.wav` / `male_best_30s.wav`

### Required first run

```bash
JOB=/tmp/voice-segment-selector-myjob
skills/voice-segment-selector/run.sh prepare \
  --input /absolute/path/to/source.mp4 \
  --job-dir "$JOB" \
  --classifier both
```

Read `manifest.json` after prepare. It contains `job_dir`, `candidate_count`, and gender counts.

Install extras before prepare when needed:

```bash
cd skills/voice-segment-selector
uv sync --extra transcribe --extra classify --extra review
```

System tools required: `ffmpeg`, `ffprobe`.

## Commands (from repo root)

```bash
# 1) Prepare ranked candidates
skills/voice-segment-selector/run.sh prepare \
  --input /path/to/interview.mp4 \
  --job-dir /tmp/voice-segment-selector-interview

# 2a) Human review via HTTP API
skills/voice-segment-selector/run.sh review \
  --job-dir /tmp/voice-segment-selector-interview \
  --port 8791
# POST /api/decide/{clip_id}/{accept|reject|maybe}

# 2b) Or record decisions from CLI
skills/voice-segment-selector/run.sh decide \
  --job-dir /tmp/voice-segment-selector-interview \
  --id 0001 --decision accept

# 3) Export accepted clips for TTS training
skills/voice-segment-selector/run.sh export \
  --job-dir /tmp/voice-segment-selector-interview \
  --gender female \
  --out-dir /tmp/voice-segment-selector-interview/voice-dataset

# 4) Optional single reference WAV (~30s)
skills/voice-segment-selector/run.sh bundle \
  --job-dir /tmp/voice-segment-selector-interview \
  --gender female \
  --target-sec 30 \
  --out /tmp/voice-segment-selector-interview/female_best_30s.wav
```

### CLI flags agents should know

| Flag | When to use |
|------|-------------|
| `--job-dir PATH` | **Always set this.** Makes review/export resumable. |
| `--classifier both` | Default for interviews / mixed voices |
| `--classifier f0` | Single-narrator audiobooks |
| `--classifier hf` | Force Norwood HF only |
| `--no-transcribe` | Fast canary / audiobook prep before Whisper |
| `--chapters-json PATH` | Required for long audiobooks (>2h default window) |
| `--min-clip-sec 6` | Default cloning clip minimum |
| `--max-clip-sec 18` | Default cloning clip maximum |
| `--auto-accept-top N` | **Only if human explicitly allows auto-export** |

## Scenario recipes

### A. Two-speaker interview (movie/video/audio)

Goal: female and/or male clip sets for cloning.

```bash
JOB=/tmp/voice-segment-selector-interview
skills/voice-segment-selector/run.sh prepare \
  --input /path/to/interview.mp4 \
  --job-dir "$JOB" \
  --classifier both

# Human reviews top candidates, then:
skills/voice-segment-selector/run.sh export --job-dir "$JOB" --gender female
skills/voice-segment-selector/run.sh export --job-dir "$JOB" --gender male

skills/voice-segment-selector/run.sh bundle --job-dir "$JOB" --gender female --target-sec 30 \
  --out "$JOB/female_best_30s.wav"
```

Tell the human: overlap and mis-gendering are possible; reject bad clips during review.

### B. YouTube source

Goal: download + segment + export.

```bash
# Step 1: get local audio (example)
cd skills/ingest-youtube
uv run python youtube_transcript.py get -i VIDEO_ID   # optional transcript metadata
# download audio separately via ingest-youtube / yt-dlp to /tmp/source.mp3

JOB=/tmp/voice-segment-selector-youtube
skills/voice-segment-selector/run.sh prepare \
  --input /tmp/source.mp3 \
  --job-dir "$JOB" \
  --classifier both
```

Do not skip human review before `/tts-train`.

### C. Single-narrator audiobook (e.g. Horus Rising)

Goal: quality-ranked narrator clips. Do **not** use gender HF as truth.

```bash
CH=/mnt/storage12tb/skills/extract-audiobook/outputs/horus_rising/ffprobe_chapters.json
AUDIO=/mnt/storage12tb/media/books/audiobooks/Horus_Rising_.../audio.m4b
JOB=/tmp/voice-segment-selector-horus

skills/voice-segment-selector/run.sh prepare \
  --input "$AUDIO" \
  --job-dir "$JOB" \
  --chapters-json "$CH" \
  --classifier f0 \
  --no-transcribe

skills/voice-segment-selector/run.sh bundle \
  --job-dir "$JOB" \
  --gender male \
  --target-sec 30 \
  --out "$JOB/male_best_30s.wav"
```

Source stays on 12TB read-only; job artifacts stay in `/tmp`.

## What the agent should tell the human

After `prepare`:

```text
Prepared {candidate_count} ranked clips in {job_dir}.
Review top clips at http://127.0.0.1:8791 (run review command) or tell me accept/reject by clip id.
I will not export for training until you approve clips.
```

After `export`:

```text
Exported {exported_clips} accepted clips to {metadata_jsonl}.
Ready for /tts-train handoff.
```

## Output layout

```text
/tmp/voice-segment-selector-<job>/
  manifest.json              # includes job_dir + counts
  candidates.jsonl           # ranked candidates with transcript fields
  decisions.jsonl            # after human review
  clips/raw/*.wav
  _work/source.mono16k.wav
  voice-dataset/             # after export
    clips/
    male/
    female/
    metadata.jsonl
  female_best_30s.wav        # optional bundle output
```

## metadata.jsonl contract (required for /tts-train)

Each exported row must include paired audio + text:

```json
{
  "clip": "clips/0001.wav",
  "bucket_clip": "female/0001.wav",
  "source": "interview.mp4",
  "start": 123.4,
  "end": 136.2,
  "duration_sec": 12.8,
  "transcript": "words spoken in this clip",
  "asr_confidence": 0.94,
  "quality_score": 0.91,
  "rank_score": 0.88,
  "gender_label": "female",
  "gender_score": 0.97,
  "accepted_by": "human"
}
```

If `transcript` is empty, do not export that clip for training unless the human explicitly accepts missing ASR.

## Handoff to /tts-train

After export, pass the dataset directory to `/tts-train`:

```bash
skills/tts-train/run.sh ingest-transcript \
  /tmp/voice-segment-selector-<job>/voice-dataset/clips \
  /tmp/voice-segment-selector-<job>/voice-dataset/metadata.jsonl \
  /tmp/voice-segment-selector-<job>/tts-handoff
```

Adapt the exact `/tts-train` subcommand to the training recipe in that skill.

## Defaults

| Setting | Default |
|---------|---------|
| Job dir | `/tmp/voice-segment-selector-<timestamp>/` if omitted |
| Clip length | 6–18 seconds |
| Classifier | `both` (Norwood HF + F0 fallback) |
| Transcript | faster-whisper per clip |
| Max duration without chapters | 7200 seconds |

## Boundaries

- Not `/tts-train` — this skill prepares datasets only
- Not LosslessCut — use `review` / `decide`
- Not guaranteed single-speaker separation in interviews
- Only use audio you have rights/consent to clone
- Do not write job artifacts to `/mnt/storage12tb` unless promoting a final training set

## Verification

```bash
cd skills/voice-segment-selector
./sanity.sh
```

For live proof on real media, run `prepare` on a short sample and confirm `candidates.jsonl` + at least one exported row in `metadata.jsonl`.
