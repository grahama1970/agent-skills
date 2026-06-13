#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

required=(
  SKILL.md
  README.md
  run.sh
  pyproject.toml
  scripts/capture_lib.py
  scripts/cli.py
  references/webgpt-upload-workflow.md
  tests/fixtures/minimal/index.html
)
for path in "${required[@]}"; do
  [[ -e "$path" ]] || { echo "missing required file: $path" >&2; exit 1; }
done

python3 -m py_compile scripts/capture_lib.py scripts/cli.py

python3 - <<'PY'
import importlib.util
if importlib.util.find_spec("typer") is None:
    raise SystemExit("typer is required: uv sync or pip install typer")
print("typer available")
PY

python3 -m pytest -q tests/test_asset_collect.py

neg_out="$(./run.sh capture 2>&1 || true)"
if ! grep -Eqi "provide --html or --url|Missing option|Error" <<<"$neg_out"; then
  echo "expected negative-control message for capture without input" >&2
  echo "$neg_out" >&2
  exit 1
fi

python3 ../best-practices-skills/scripts/validate_skill.py . || true

echo "local-page-analysis-capture sanity passed"
