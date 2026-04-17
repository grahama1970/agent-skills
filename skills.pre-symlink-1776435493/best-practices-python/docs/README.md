# python-best-practices

A Vercel-style agent skill for **Python best practices**, tailored to this repo’s conventions:
Loguru, Typer, uv + pyproject.toml, httpx, functions-first, required module docstrings, max 800 LOC per file,
and non-mocked sanity tests.

## Structure

- `SKILL.md` — when to apply + priority order + quick reference
- `rules/` — atomic rules (one per file) with Incorrect/Correct examples
- `AGENTS.md` — compiled single-document version (generated)
- `scripts/` — helper scripts (compile + checks)
- `assets/` — example configs/snippets (ruff, pyproject)

## Add a new rule (2 minutes)

1. Copy `rules/_template.md` → `rules/<prefix>-<short-name>.md`
2. Fill frontmatter: `title`, `impact`, `impactDescription`, `tags`
3. Add **Incorrect** and **Correct** code examples
4. Keep it single-purpose (one enforceable idea)
5. Run `python scripts/compile_agents.py` to rebuild `AGENTS.md`

## Compile

```bash
python scripts/compile_agents.py
```

## Quality gates (optional)

- `python scripts/check_file_limits.py` — fails if any `.py` file exceeds 800 LOC
