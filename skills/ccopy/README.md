# ccopy

> **Disciplines:** developer-tooling

Copy the last complete Cursor **user + assistant** turn to the clipboard.

## Install

```bash
chmod +x ~/.cursor/skills/ccopy/{run.sh,sanity.sh,bin/ccopy,bin/cursor-copy}
pip install typer   # or uv pip install typer
~/.cursor/skills/ccopy/install.sh   # optional: ~/.local/bin/ccopy
```

## Usage

```bash
cd /path/to/your/project
ccopy --print
ccopy --diagnose
ccopy --source agent-transcript --print
```

## Tests

```bash
./run.sh test
./run.sh sanity
```

## Layout

```text
SKILL.md
run.sh / sanity.sh
bin/ccopy
scripts/ccopy/          Python package (Typer CLI)
tests/                  SQLite + JSONL fixtures
references/USAGE.md
```
