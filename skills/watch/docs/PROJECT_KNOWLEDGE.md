# Watch Skill: Project Knowledge

## Architecture

- **Subagent:** `agents/watch/` — AGENTS.md + persona.yaml (best-practices-subagent compliant)
- **Skill:** `skills/watch/` — SKILL.md, run.sh, scripts/watch.py, sanity.sh
- **CLI:** Typer (converted from argparse for best-practices-skills compliance)
- **Collection:** `watch_content` (NOT `lessons`) with QRA format: `question`/`reasoning`/`answer`

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| `question`/`reasoning`/`answer` not `problem`/`solution` | QRA format enables structured recall alongside SPARTA QRA |
| `include_edges=False` | `lesson_edges` doesn't exist — AQL crashes |
| Time-coverage scene fallback | <10% of duration detected → uniform sampling |
| `image_mm` shared for images + audio | Jina unifies all modalities in same vector space |

## Composed Skills

- `ingest-youtube` — YouTube captions (3-tier: direct→proxy→Whisper)
- `ingest-movie` — SRT emotion/scene analysis for local files
- `doc2qra` — QRA extraction from transcripts (optional)
- `memory` — watch history upsert + recall via `/upsert`/`/recall`
- `embedding` — PDF embedding (pages rendered as images via pypdfium2)
- `brave-search` — movie title research

## API Dependencies

| API | Endpoint | Purpose |
|-----|----------|---------|
| Zen API | `opencode.ai/zen/go/v1/chat/completions` | QRA generation (deepseek-v4-flash), image descriptions (mimo-v2-omni) |
| scillm | `localhost:4001/v1/chat/completions` | Soundtrack description (gpt-5.5) |
| Memory daemon | `localhost:8601` | `/upsert` to watch_content, `/recall` for search |

## Known Gaps

- **Audio embedding** — needs `memory-embedding-mm` Docker rebuild for `data:audio/` MIME support
- **Scene-change timestamps** — ffmpeg pts_time parsing has edge cases with some video codecs
- **Concurrent LLM calls** — `ThreadPoolExecutor(5)` for image + audio descriptions

## E2E Sanity: 17/17 pass
