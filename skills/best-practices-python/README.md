# best-practices-python

Human-facing reference for the `best-practices-python` skill.

Agents should read `SKILL.md` first. The skill defines this repo's Python defaults:
Loguru logging, Typer CLIs, httpx for HTTP, uv with `pyproject.toml`, clear
module docstrings, functions-first structure, and non-mocked sanity evidence.

Useful entry points:

- `SKILL.md` - operational contract for agents.
- `AGENTS.md` - compiled rule reference from `rules/`.
- `docs/PACKAGES.md` - package reference and dependency guidance.
- `sanity.sh` - focused local sanity check for this skill.
