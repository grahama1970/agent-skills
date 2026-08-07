---
name: get-subtitles
description: >
  Ensure movie subtitles exist and are verified on disk. Use when the user says
  get subtitles, download subtitles, verify English SRT, ask Bazarr for subtitles,
  ensure movie subtitles, or find subtitle-backed movie candidates.
triggers:
  - get subtitles
  - download subtitles
  - verify English SRT
  - ask Bazarr for subtitles
  - ensure movie subtitles
  - find subtitle-backed movies
provides:
  - subtitle-acquisition
  - subtitle-verification
  - bazarr-integration
  - subtitle-backed-discovery
composes:
  - brave-search
  - memory
  - ingest-movie
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
taxonomy:
  - media
  - subtitles
  - validation
disciplines:
  - data-engineering
---

# Get Subtitles

Use this skill to ensure a movie has a verified subtitle artifact before Watch,
Orpheus, or ingest workflows trust it. Bazarr language metadata is not enough:
the skill must return a real local subtitle file path or a fail-closed receipt.

## Contract

- Use Bazarr first for local movie metadata and subtitle recovery.
- Use `X-API-KEY: $BAZARR_API_KEY`; never print the key.
- Verify an actual local subtitle file after every search/download attempt.
- Return JSON receipts by default for automation.
- Compose `brave-search` for external movie discovery and subtitle/transcript
  URL discovery. Brave snippets are candidate seeds only; a non-local movie is
  not recommendable until this skill fetches a subtitle/transcript artifact,
  stores it locally, scans it, and finds timecoded Orpheus cue markers.
- Do not access ArangoDB directly. Use `memory` when durable state is needed.

## Commands

```bash
./run.sh doctor --json
./run.sh movies --query "Bad Santa" --json
./run.sh verify-file --media-path /path/movie.mkv --language en --json
./run.sh ensure-radarr --radarr-id 149 --language en --json
./run.sh providers --radarr-id 149 --json
./run.sh download-provider --radarr-id 149 --provider OpenSubtitles --subtitle '<provider payload>' --original-format --json
./run.sh api-search-download --series-id 123 --episode-id 456 --language en --preferred-formats vtt,ass,srt --json
./run.sh discover --actor "Kristen Stewart" --genre comedy --emotion laugh --json
./run.sh orpheus-sanity --actor "Kristen Stewart" --genre comedy --all-orpheus-emotions --output out/kristen-stewart-orpheus-sanity.json --json
./run.sh scan-srt --subtitle /path/movie.en.srt --all-orpheus-emotions --json
./run.sh batch-ensure-radarr --radarr-ids 149,150 --all-orpheus-emotions --json
```

## Receipt Shape

Verified:

```json
{
  "status": "verified",
  "language": "en",
  "subtitle_path": "/path/movie.en.srt",
  "primary_subtitle_format": "srt",
  "subtitle_files": [
    {
      "path": "/path/movie.en.srt",
      "format": "srt",
      "verified": true,
      "speaker_metadata_status": "not_present"
    }
  ],
  "media_path": "/path/movie.mkv",
  "radarr_id": 149,
  "source": "filesystem",
  "safe_default": "allow_watch_processing"
}
```

Not verified:

```json
{
  "status": "not_verified",
  "reason": "english_srt_missing",
  "safe_default": "do_not_process_for_watch_or_orpheus"
}
```

## Bazarr Endpoints Used

The local Bazarr Swagger currently exposes:

- `GET /api/movies`
- `GET /api/system/searches?query=...`
- `GET /api/providers/movies?radarrid=...`
- `PATCH /api/movies/subtitles?radarrid=...&language=en&forced=False&hi=False`
- `POST /api/providers/movies?...provider=...&subtitle=...&original_format=True`
- `GET /api/subtitles?subtitlesPath=...&radarrMovieId=...`

The local Swagger does not expose a generic `GET /api/subtitles/search` plus
`POST /api/subtitles/download` workflow. The skill still exposes
`api-search-download` as a compatibility command for Bazarr versions that do
support the API shape:

```bash
./run.sh api-search-download \
  --series-id 123 \
  --episode-id 456 \
  --language en \
  --preferred-formats vtt,ass,srt \
  --json
```

When those generic endpoints are absent, the command fails closed with
`status: not_available` and points to the provider workflow. For this Bazarr
install, manual format-preserving selection is:

1. `GET /api/providers/movies?radarrid=...`
2. Filter the returned provider payload by available extension/format when the
   provider includes that field.
3. `POST /api/providers/movies` with `original_format=True`, `provider`, and
   the exact returned `subtitle` payload.
4. Verify the resulting local file on disk. The provider response alone is not
   sufficient evidence.

If a provider only offers `.srt`, do not invent `.vtt` or `.ass`. Preserve
`.vtt`, `.ass`, or `.ssa` only when Bazarr/provider actually supplies it.

## Orpheus Subtitle Coverage

`scan-srt` accepts `.srt`, `.vtt`, `.ass`, and `.ssa` files. It reads only
explicit bracketed or parenthetical cue markers and returns exact cue locations:

```json
{
  "emotion": "laugh",
  "marker": "(LAUGHS)",
  "timecode": "00:02:24,000 --> 00:02:26,200",
  "start_seconds": 144.0,
  "end_seconds": 146.2,
  "line": "(LAUGHS)"
}
```

The scan output also includes `metadata` with path/filename-derived title/year
and any obvious inline SRT metadata fields such as `Title:`, `Year:`, `Actors:`,
`IMDB:`, or `Source:`. These fields are extracted only when present or
path-derived; the skill must not infer actors from dialogue or hallucinate cast.

Speaker metadata is reported only when present in the subtitle artifact:

- `.ass/.ssa`: structured `Dialogue` `Name` field.
- `.vtt`: structured `<v Speaker Name>` cue tags.
- `.srt`: inline text labels like `Willie: ...` only.

Plain `.srt` subtitles generally do not carry reliable speaker identity. If
speaker identity is absent, report `speaker_metadata_status: not_present` and
let Watch/Memory/Brave verification handle speaker attribution as a separate
evidence step.

Ambient markers such as `[PEOPLE CHATTERING]`, `[MUSIC]`, and `[BACKGROUND
NOISE]` are rejected as Orpheus emotion evidence.

`batch-ensure-radarr` runs concurrent Bazarr ensure tasks and scans each SRT as
soon as it verifies, using `asyncio.as_completed`. Its output includes coverage
counts and `missing_emotions` so the project agent can decide which movies still
need acquisition through `ingest-movie`.

`orpheus-sanity` is the end-to-end subtitle/discovery-only sanity check. It:

1. Runs concurrent `brave-search` batch queries for each requested Orpheus
   emotion.
2. Deduplicates title/year candidate movies from Brave snippets.
3. Checks local Bazarr/Radarr inventory for those candidates.
4. For every local Bazarr/Radarr match, asks Bazarr to download missing English
   subtitles by default (`--download`; use `--no-download` only for a passive
   audit).
5. Verifies the resulting local subtitle file on disk.
6. Scans verified subtitle files for Orpheus cue markers.
7. Optionally runs external subtitle/tag probes for non-local candidates. These
   are leads only; they are not trusted until a subtitle file is downloaded and
   scanned.
8. Optionally fetches external subtitle/transcript URLs discovered through
   Brave. Supported direct fetches are stored under `out/external-subtitles/`;
   SubtitleCat HTML pages are followed to their English `*-en.srt` download
   when present. Fetched HTML transcript pages are stored as text but only
   timecoded subtitle artifacts are eligible for acquisition recommendations.
9. Optionally probes non-local candidates through Radarr/Bazarr metadata:
   `--probe-nonlocal-bazarr --create-radarr-stubs` adds an unmonitored Radarr
   metadata record with `searchForMovie=false`, triggers Bazarr `update_movies`,
   and then attempts Bazarr provider search only if Bazarr indexes the record.
   This does not download the movie.
10. Writes a final JSON artifact with separate fields for:
   - `local_verified_hits`
   - `local_bazarr_recovery`
   - `external_subtitle_candidates`
   - `external_fetched_subtitle_scans`
   - `external_verified_hits`
   - `movie_recommendations` (unified local + non-local recommendation list)
   - `ingest_movie_handoff` (normalized acquisition/extraction contract for
     `ingest-movie`)
   - `local_movie_recommendations`
   - `movie_download_recommendations`
   - `nonlocal_bazarr_subtitle_vetting`
   - `nonlocal_movie_download_recommendations`
   - `combined_emotion_coverage`
   - `unfound_emotion_tags`

It must not download movies. Acquisition remains a separate `ingest-movie`
step after subtitle coverage gaps are known. Bazarr subtitle recovery is part
of this sanity check for movies already present in local Radarr/Bazarr.

`movie_download_recommendations` must be fail-closed: a movie can appear there
only when a subtitle file has been verified and scanned and the requested
Orpheus tag exists in the subtitle text. External Brave/Bazarr/provider search
results can populate `external_subtitle_candidates`, but those entries remain
unvetted leads until the subtitle artifact is downloaded and scanned.

`movie_recommendations` is the unified consumer-facing list. It includes local
verified recommendations with `scope: local` and non-local acquisition
candidates with `scope: nonlocal`. Keep the older split fields for scripts that
need to distinguish local usable movies from acquisition candidates.

`ingest_movie_handoff` is the next-stage contract for `ingest-movie`. Each
entry must include normalized `title`, `year`, Orpheus-TTS acquisition profile,
subtitle-rich NZBGeek search commands, exact cue windows grouped under
`subtitle_evidence`, and post-import verification gates. The handoff is not a
training-ready claim; it remains blocked until local movie audio and local
English `.srt` are verified after import. Provider-only recommendations without
a concrete fetched or local subtitle path must not enter this handoff.

`nonlocal_movie_download_recommendations` is weaker and must be labeled as an
acquisition queue only. It may include movies when a fetched external subtitle
artifact contains timecoded Orpheus cue markers, or when Bazarr provider search
can see subtitle candidates for a Radarr metadata stub. Bazarr-provider-only
entries are still not Orpheus evidence until the movie is acquired, an actual
subtitle file is downloaded, and `scan-srt` verifies Orpheus cue markers with
timecodes.

On the current local Bazarr install, Bazarr does not index Radarr metadata-only
movie stubs that have no movie file. In that case `nonlocal_bazarr_subtitle_vetting`
must report `bazarr_did_not_index_radarr_metadata_stub_without_movie_file`, and
the safe default is no non-local movie recommendation from Bazarr.

## Failure Policy

Fail closed if:

- `BAZARR_API_KEY` is missing.
- Bazarr is unreachable.
- The movie cannot be identified.
- Bazarr reports subtitles but no real local subtitle file can be verified.
- Download returns success but no subtitle file appears on disk.

For Watch and Orpheus, Whisper-only transcripts or future subtitle availability
must not satisfy this skill's verification contract.
