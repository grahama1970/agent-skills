# browser-oracle — Project Knowledge

**Status:** Active development (v0.1)

## Purpose

Separate tab-binding/registry concerns from the large `/ask` skill so project agents can `$browser-oracle resolve` without loading full ask oracle docs.

## Architecture

- `walkup.py` — dotenv-style parent walk for `.ask/browser-oracles.yaml`
- `registry.py` — yaml → project name (+ `by_relative_path`, `lanes`, `default`)
- `bindings.py` — `~/.pi/*-projects/*.json` tab id / URL storage
- `cli.py` — Typer entrypoints

## Known gaps

- `/ask` does not yet auto-call `browser-oracle resolve` before webgpt rounds
- Live surf verify requires Chrome + surf-cli extension (optional in unit tests)
- Gemini/Kimi project stores exist but are not wired to ask runtime yet

## Validation

```bash
./sanity.sh
```
