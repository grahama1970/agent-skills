# Movie-Ingest Skill

This skill searches NZBGeek for high-quality movie releases and turns scene clips into ingestion-ready PersonaPlex benchmarks.

## Why subtitles matter

Horus’s emotional overlays (anger, humor, respect) come from real performances, but we still need labeled cues—laughter, shouting, whispers. The fastest way is to ingest scene releases that ship **forced/dialog subtitles** with stage directions. `movie_ingest.py transcribe` now refuses to run unless it finds an `.srt` with cues like `[laughs]` or `(shouting)`.

When a release lacks subs, fetch them manually (OpenSubtitles, Blu-ray `.sup` converted to `.srt`), place them next to the clip, and pass `--subtitle path/to/file.srt`.

## Workflow

1. **Find a release with subs**
   ```bash
   ./movie-ingest.sh search "There Will Be Blood"  # look for WEB-DL / BluRay w/ subtitles
   ```
2. **Download video + .srt** via readarr-ops/NZB clients.
3. **Locate scene timestamps (optional)**
   ```bash
   ./movie-ingest.sh scenes find ./data/plainview_milkshake.srt \
     --query "milkshake" --window 10 \
     --video "/path/to/There.Will.Be.Blood...mkv"
   ```
   The helper prints clip-friendly windows and `ffmpeg` commands.
4. **Transcribe + annotate**
   ```bash
   ./movie-ingest.sh transcribe ./data/plainview_milkshake.mkv \
     --subtitle ./data/plainview_milkshake.forced.srt \
     --emotion rage \
     --scene "I drink your milkshake" \
     --characters "Plainview, Eli" \
     --movie-title "There Will Be Blood"
   ```
5. **Ingest into Horus**
   ```bash
   python horus_lore_ingest.py emotion --input ./transcripts --emotion rage
   ```

## Auto-tagging

- Subtitle parser captures cues → tags segments (`[laughs]` → `laugh`).
- Audio heuristics add `anger_candidate`, `rage_candidate`, or `whisper_candidate` when RMS levels spike or drop.
- Persona JSON (`*_persona.json`) includes `meta.subtitle_tags`, `meta.audio_tags`, and per-segment `tags` for downstream Theory-of-Mind logic.

## Dependencies

- `ffmpeg`, `whisper` CLI
- `soundfile`, `numpy` (optional but enables audio intensity tagging)
- `NZBD_GEEK_API_KEY` for search

Keep all clips and subtitles under `data/` and commit only the JSON manifests so we avoid shipping copyrighted video.
