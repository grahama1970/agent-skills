# DEPRECATED — Archived 2026-04-02

`/create-claude` was a FastAPI wrapper around `claude -p` subprocess calls.
Headless `claude -p` is unreliable (0% file write success). All LLM calls
now route through `/scillm` httpx API.

Archived to: `.archive/skills/create-claude/`
