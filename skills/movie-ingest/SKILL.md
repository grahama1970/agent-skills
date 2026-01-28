# Movie-Ingest Skill

Automated pipeline for searching movie segments on Usenet (NZBGeek) and extracting high-fidelity transcripts/audio for Horus's PersonaPlex.

## Features

- **NZB Search**: Search NZBGeek for specific movie titles and high-fidelity releases.
- **Whisper + Subtitle Ingestion**: Transcribe local movie files using Whisper and require aligned `.srt` subtitle tracks so we can auto-tag laughter/shouting cues.
- **Rhythmic + Cue Metadata**: Output word-level timestamps, pause counts, and subtitle-derived emotion tags for Horus’s Theory-of-Mind training clips.

## Usage

```bash
# Search for a movie release that ships with subtitles
./movie-ingest.sh search "Gladiator"

# Transcribe a local segment with explicit subtitle file
./movie-ingest.sh transcribe ./data/gladiator_rage.mkv \
  --subtitle ./data/gladiator_rage.forced.srt \
  --emotion rage \
  --scene "Maximus confronts Commodus" \
  --characters "Maximus, Commodus"
```

> Tip: Always choose scene releases that include high-quality `.srt` or `.sup` files. Without subtitle cues (e.g., `[laughs]`, `(shouting)`), the tool will refuse to ingest because PersonaPlex needs those emotional markers.

## Dependencies

- `ffmpeg`: For audio extraction.
- `whisper`: Local CLI for transcription.
- `NZBD_GEEK_API_KEY`: Set in `.env` for NZB search.
- `.srt` subtitles with emotion annotations (bundled or downloaded separately).
