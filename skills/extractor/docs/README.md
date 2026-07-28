# Extractor Skill Maintainer Notes

This directory intentionally contains no extraction pipeline of its own. The
runtime delegates to the canonical Extractor project command:

```bash
uv run --project "$EXTRACTOR_ROOT" extractor extract <file>
```

Clean-install CI may instead set `EXTRACTOR_COMMAND` to an installed executable
and the wrapper will call that command directly.

Keep `SKILL.md`, `run.sh`, `extract.py`, and `sanity.sh` aligned with that
single-file wrapper contract. Add new extraction behavior in Extractor, not in
this skill.
