# Formats and troubleshooting

## Output formats

- `markdown` (default): `## User` / `## Assistant`
- `plain`: `USER:` / `ASSISTANT:`
- `json`: `{ "messages": [...] }` with optional `meta`
- `xml`: minimal `<cursor_copy>` wrapper

## Session vs composer IDs

- **Agent transcripts** use session UUIDs under `agent-transcripts/<session>/`.
- **SQLite composer** entries use different UUIDs in `composer.composerHeaders`.
- Prefer cwd-based project matching; use `--composer` with the transcript session id when forcing `--source agent-transcript`.

## Clipboard tools

Linux: `wl-copy`, `xclip`, or `xsel`. Use `--print` if clipboard tools are missing.

## Dependencies

- Python 3.10+
- `typer` for CLI

Install Typer if missing: `pip install typer` or `uv pip install typer`.
