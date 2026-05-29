# Deprecated: use phart-dag-chart

This nested subproject moved to **`skills/phart-dag-chart/`** with:

- `./run.sh validate <dag.json>`
- `./run.sh chart <dag.json>`
- Typer CLI, shared validation messages, exit codes 0/1/2

Ask dry-run calls the sibling skill via `uv run --directory ../phart-dag-chart phart-dag-chart chart`.
