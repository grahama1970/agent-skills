---
name: extract-audiobook
description: >
  Create chapter-aware text and transcript JSONL artifacts from audiobook media.
  Use when an audiobook has embedded chapter metadata, when a flat transcript
  lost chapter boundaries, when users ask to split/transcribe an audiobook by
  chapter, or when fact extraction needs clean chapter text with reliable
  chapter_id provenance.
triggers:
  - extract audiobook
  - split audiobook by chapter
  - transcribe audiobook chapters
  - repair audiobook chapterization
  - create audiobook transcript jsonl
  - audiobook chapter text
provides:
  - audiobook-chapter-extraction
  - audiobook-transcript-jsonl
  - chapter-aware-text
composes:
  - ingest-audiobook
  - fact-extractor
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - extraction
  - precision
  - validation
---

# extract-audiobook

Use this skill to turn an audiobook file into resumable, chapter-aware text
artifacts. It is the bridge between `/ingest-audiobook` and `/fact-extractor`.

This skill does not write `persona_memory`, `lessons`, ArangoDB, or final QRA
collections.

## Contract

The skill owns deterministic audio/chapter handling:

- read embedded chapters with `ffprobe -show_chapters`
- split chapter audio with `ffmpeg`
- transcribe each chapter independently with faster-whisper when requested
- write one plain chapter text file and one transcript JSONL per chapter
- write `manifest.json` and memory-upsert-compatible `chapters.jsonl`
- resume safely after interruption by skipping valid existing artifacts
- fail closed when embedded chapters are missing unless fallback mode is explicit

## Output Modes

- `chapter-text`: write `cleaned_chapters/chapter_XX.txt`
- `transcript-jsonl`: write timestamped segment JSONL per chapter
- `both`: write both chapter text and transcript JSONL

The `audiobook-extractor` subagent may optionally run `/fact-extractor` after
this skill, but this skill itself only produces chapter-aware transcript
artifacts.

## Commands

Check dependencies:

```bash
skills/extract-audiobook/run.sh doctor --json
```

Probe chapter metadata:

```bash
skills/extract-audiobook/run.sh probe ./audio.m4b \
  --out /mnt/storage12tb/skills/extract-audiobook/outputs/book
```

Split chapter audio without transcription:

```bash
skills/extract-audiobook/run.sh split ./audio.m4b \
  --book "Galaxy in Flames" \
  --book-id galaxy_in_flames \
  --out /mnt/storage12tb/skills/extract-audiobook/outputs/galaxy_in_flames
```

Run the resumable chapter extraction:

```bash
skills/extract-audiobook/run.sh extract ./audio.m4b \
  --book "Galaxy in Flames" \
  --book-id galaxy_in_flames \
  --out /mnt/storage12tb/skills/extract-audiobook/outputs/galaxy_in_flames \
  --mode both \
  --model turbo
```

For fast canaries, use `--limit 1` or `--limit-seconds 90`.

Normalize an already-transcribed flat audiobook transcript without running
Whisper again:

```bash
skills/extract-audiobook/run.sh normalize-transcript ./audio.m4b \
  --transcript ./text.md \
  --book "Horus Rising" \
  --book-id horus_rising \
  --out /mnt/storage12tb/skills/extract-audiobook/outputs/horus_rising
```

This mode still uses embedded audio chapters for chapter count, timing, and
chapter ids, but it splits the flat transcript by chapter duration proportions.
It must mark `chapter_split_confidence: "estimated"` and add provenance warnings
because it is not a fresh per-chapter audio transcription.

## Resume Rules

Resume is the default. Unless `--force` is supplied:

- existing valid chapter audio files are not regenerated
- existing non-empty chapter text files are not retranscribed
- existing transcript JSONL files with at least one segment are not rewritten
- `manifest.json` records `skipped_existing`, `created`, or `failed` per chapter

If a run is interrupted, rerun the same command with the same `--out` directory.

## Artifact Layout

```text
<out>/
  manifest.json
  chapters.jsonl
  ffprobe_chapters.json
  audio_chapters/chapter_XX.m4a
  cleaned_chapters/chapter_XX.txt
  transcript_jsonl/chapter_XX.jsonl
```

`chapters.jsonl` rows include deterministic `_key`, `type`, `record_id`,
`record_type`, `memory_collection: "book_chapters"`, `text`, `retrieval_text`,
tags, status fields, chapter timing, and artifact paths. They are shaped for a
later `$memory` `/upsert`, but this skill does not perform memory writes and
must not emit inline embedding/vector fields.

## Boundaries

- Use `/ingest-audiobook` to acquire/decrypt raw audiobook assets.
- Use `/fact-extractor` only after this skill has produced reliable chapter
  text.
- Do not infer chapter boundaries from flat text when audio chapter metadata is
  available; use embedded audio chapters as the source of truth.
