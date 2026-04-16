# Code Review Request: movie-ingest skill

## Scope
- Files: `movie-ingest/movie_ingest.py`, `movie-ingest/SKILL.md`, `movie-ingest/run.sh`, `movie-ingest/sanity.sh`, shared `pyproject.toml`.
- Context: added canonical frontmatter/docs, new `scenes extract` command with manifest/clip emission, subtitle-first enforcement, NZB search hints, and soundfile/numpy deps for audio tagging.
- Goal: brutal 2-round review via GitHub Copilot GPT-5 focusing on robustness, edge cases (subtitle parsing, manifest generation, clip extraction, audio tagging), error handling, and CLI UX.

## Key Questions
1. Are there failure modes around missing subtitles / malformed cues we should harden?
2. Does the scenes helper/manifest pipeline handle overlapping matches and large files efficiently?
3. Are audio-tag heuristics + dependency fallbacks adequate now that numpy/soundfile are optional?
4. Any suggestions for separating responsibilities, reducing duplicated parsing logic, or improving testability?
5. Is the SKILL doc/run/sanity alignment sufficient for other agents invoking this skill?

Please provide concrete issues and, when possible, unified diff patches.
