---
id: voice-segment-selector
kind: worker
title: Voice segment selector
surface: opencode_transport
transport_role: patch
opencode_agent: build
mode: workspace_write
composes:
- voice-segment-selector
- tts-train
- extract-audiobook
- ingest-youtube
consult_personas: []
icon: audio-lines
---

# Voice segment selector

Prepare ranked, gender-bucketed, transcript-backed voice clips from audio or video
for voice cloning and `/tts-train`.

## Mission

1. Run `skills/voice-segment-selector/run.sh prepare`
2. Ask the human to review top candidates (`review` or `decide`)
3. Run `export` to produce `metadata.jsonl`
4. Optionally run `bundle --target-sec 30`
5. Hand exported dataset paths to `/tts-train`

## Storage contract

- Job artifacts default to `/tmp/voice-segment-selector-<timestamp>/`
- Do not write job outputs to `/mnt/storage12tb` unless explicitly promoting a final training set
- Large source audiobooks may be read from `/mnt/storage12tb` read-only

## Required outputs

```json
{
  "job_dir": "/tmp/voice-segment-selector-...",
  "candidate_count": 42,
  "metadata_jsonl": "/tmp/.../voice-dataset/metadata.jsonl",
  "bundle_wav": "/tmp/.../female_best_30s.wav"
}
```

## Boundaries

- Auto-rank only; human accept/reject before training export unless user explicitly allows `--auto-accept-top`
- Gender labels are vocal characteristic guesses, not identity
- Long audiobooks require `--chapters-json`
