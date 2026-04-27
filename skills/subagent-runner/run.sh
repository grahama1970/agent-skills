#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/home/graham/workspace/experiments/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="python"
fi

if [[ "${1:-}" == "help" ]]; then
    shift
    exec "$PYTHON_BIN" "$SCRIPT_DIR/run.py" --help "$@"
fi

if [[ "${1:-}" == "layout" ]]; then
    python - <<'PY'
layout = [
    "spec.json",
    "status.json",
    "events.jsonl",
    "commands.jsonl",
    "transcript.log",
    "stdout.log",
    "stderr.log",
    "prompt.txt",
    "result.json",
]
print("\n".join(layout))
PY
    exit 0
fi

if [[ "$#" -eq 0 ]]; then
    exec "$PYTHON_BIN" "$SCRIPT_DIR/run.py" --help
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/run.py" "$@"
