# Review modularized youtube_transcripts package

## Repository and branch

- **Repo:** `grahama1970/pi-mono`
- **Branch:** `main`
- **Paths of interest:**
  - `.pi/skills/youtube-transcripts/youtube_transcripts/config.py`
  - `.pi/skills/youtube-transcripts/youtube_transcripts/utils.py`
  - `.pi/skills/youtube-transcripts/youtube_transcripts/downloader.py`
  - `.pi/skills/youtube-transcripts/youtube_transcripts/transcriber.py`
  - `.pi/skills/youtube-transcripts/youtube_transcripts/formatter.py`
  - `.pi/skills/youtube-transcripts/youtube_transcripts/batch.py`
  - `.pi/skills/youtube-transcripts/youtube_transcripts/__init__.py`
  - `.pi/skills/youtube-transcripts/cli.py`

## Summary

This is a newly modularized YouTube transcript extraction skill. The original 1182-line monolith was split into:
- config.py (183 lines) - Constants, paths, environment loading
- utils.py (170 lines) - Common utilities (video ID extraction, error checking)
- downloader.py (168 lines) - yt-dlp video/audio download
- transcriber.py (399 lines) - Whisper transcription (local and API)
- formatter.py (343 lines) - Output formatting and batch state management
- batch.py (214 lines) - Batch processing logic
- cli.py (383 lines) - Typer CLI entry point

## Objectives

### 1. Code Quality Review

Review all modules for:
- Proper type hints and docstrings
- Error handling patterns
- Code organization and separation of concerns
- Unused imports or dead code
- Potential bugs or edge cases

### 2. Import Structure Review

Verify:
- No circular imports between modules
- Clean dependency graph (config <- utils <- others)
- Proper use of absolute imports within package

### 3. API Consistency

Check:
- Consistent return types across similar functions
- Consistent error handling patterns
- Proper use of Optional types

## Constraints for the patch

- **Output format:** Unified diff only, inline inside a single fenced code block.
- Include a one-line commit subject on the first line of the patch.
- Hunk headers must be numeric only (`@@ -old,+new @@`); no symbolic headers.
- Patch must apply cleanly on branch `main`.
- No destructive defaults; retain existing behavior unless explicitly required by this change.
- No extra commentary, hosted links, or PR creation in the output.

## Acceptance criteria

- All modules have consistent docstrings
- No circular import issues
- Type hints are complete and accurate
- Error handling is robust

## Test plan

**After change:**

1. Run `bash sanity.sh` - should pass all checks
2. Run `python cli.py --help` - should display help
3. Import test: `python -c "from youtube_transcripts import *"`

## Implementation notes

- Focus on fixes that improve maintainability
- Do not change core functionality
- Keep fixes minimal and targeted

## Known touch points

- youtube_transcripts/config.py
- youtube_transcripts/utils.py
- youtube_transcripts/downloader.py
- youtube_transcripts/transcriber.py
- youtube_transcripts/formatter.py
- youtube_transcripts/batch.py
- cli.py

## Deliverable

- Reply with a single fenced code block containing a unified diff that meets the constraints above
